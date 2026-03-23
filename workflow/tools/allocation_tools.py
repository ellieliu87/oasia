"""
Allocation and MBS decomposition tools.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agents import RunContextWrapper, function_tool
from workflow.models.workflow_state import (
    AllocationScenario,
    MBSBreakdown,
    PurchaseScheduleItem,
    RiskAppetite,
    WorkflowState,
)


# ---------------------------------------------------------------------------
# Allocation scenarios
# ---------------------------------------------------------------------------

_SCENARIO_TEMPLATES: Dict[str, Dict[str, Any]] = {
    RiskAppetite.CONSERVATIVE: {
        "mbs_pct":      45.0,
        "cmbs_pct":     15.0,
        "treasury_pct": 40.0,
        "dur":          5.0,
        "liq":          9.0,
        "yield_add":   -0.30,   # relative to moderate
        "rationale": (
            "Conservative allocation maximises Treasuries and high-grade agency MBS "
            "to control interest-rate risk and maintain liquidity. "
            "Suitable when duration must stay near lower bound or when market "
            "volatility is elevated."
        ),
    },
    RiskAppetite.MODERATE: {
        "mbs_pct":      60.0,
        "cmbs_pct":     22.0,
        "treasury_pct": 18.0,
        "dur":          5.3,
        "liq":          8.2,
        "yield_add":    0.0,
        "rationale": (
            "Balanced allocation providing solid yield pickup over Treasuries "
            "through agency MBS and investment-grade CMBS, while keeping "
            "liquidity and duration within comfortable bounds."
        ),
    },
    RiskAppetite.AGGRESSIVE: {
        "mbs_pct":      65.0,
        "cmbs_pct":     28.0,
        "treasury_pct":  7.0,
        "dur":          5.7,
        "liq":          7.2,
        "yield_add":    0.35,
        "rationale": (
            "Aggressive allocation tilts heavily toward higher-spread MBS and CMBS "
            "to maximise yield. Duration approaches upper bound. "
            "Suitable when the yield curve is steep and credit quality is strong."
        ),
    },
}

_BASE_YIELD = 5.15  # approximate blended yield for moderate scenario


@function_tool
def generate_allocation_scenarios(
    wrapper: RunContextWrapper[WorkflowState],
) -> str:
    """
    Generate three allocation scenarios (conservative / moderate / aggressive)
    for the new purchase volume, calibrated to the trader's risk appetite and
    current risk constraints.

    Populates state.allocation_scenarios and returns JSON with all three options.
    """
    state: WorkflowState = wrapper.context
    volume_mm = state.next_12m_new_volume_mm or 1_000.0
    rc = state.risk_constraints

    scenarios = []
    for appetite, tpl in _SCENARIO_TEMPLATES.items():
        mbs_mm      = round(volume_mm * tpl["mbs_pct"] / 100, 1)
        cmbs_mm     = round(volume_mm * tpl["cmbs_pct"] / 100, 1)
        treasury_mm = round(volume_mm * tpl["treasury_pct"] / 100, 1)

        # Clamp CMBS to constraint
        if rc and tpl["cmbs_pct"] > rc.max_cmbs_pct:
            excess = tpl["cmbs_pct"] - rc.max_cmbs_pct
            cmbs_mm     = round(volume_mm * rc.max_cmbs_pct / 100, 1)
            treasury_mm = round(treasury_mm + volume_mm * excess / 100, 1)

        proj_dur = tpl["dur"]
        if rc:
            proj_dur = max(rc.duration_min + 0.1, min(rc.duration_max - 0.1, proj_dur))

        s = AllocationScenario(
            scenario_id=appetite,
            label=appetite.capitalize(),
            mbs_pct=tpl["mbs_pct"],
            cmbs_pct=tpl["cmbs_pct"],
            treasury_pct=tpl["treasury_pct"],
            mbs_mm=mbs_mm,
            cmbs_mm=cmbs_mm,
            treasury_mm=treasury_mm,
            total_new_volume_mm=volume_mm,
            projected_duration=round(proj_dur, 2),
            projected_liquidity_score=tpl["liq"],
            projected_yield_pct=round(_BASE_YIELD + tpl["yield_add"], 2),
            rationale=tpl["rationale"],
        )
        scenarios.append(s)

    state.allocation_scenarios = scenarios

    result = [s.model_dump() for s in scenarios]
    return json.dumps(result, indent=2)


@function_tool
def select_allocation_scenario(
    wrapper: RunContextWrapper[WorkflowState],
    scenario_id: str,
) -> str:
    """
    Confirm the selected allocation scenario and store it in state.

    Args:
        scenario_id: One of 'conservative', 'moderate', 'aggressive',
                     or 'custom' (the trader may have set custom values).
    """
    state: WorkflowState = wrapper.context

    match = next(
        (s for s in state.allocation_scenarios if s.scenario_id == scenario_id), None
    )
    if match is None:
        return json.dumps({"error": f"Scenario '{scenario_id}' not found."})

    state.selected_scenario = match
    return json.dumps(
        {"status": "selected", "scenario": match.model_dump()}, indent=2
    )


# ---------------------------------------------------------------------------
# MBS decomposition
# ---------------------------------------------------------------------------

_MBS_DECOMP_TEMPLATES: Dict[str, Dict[str, Any]] = {
    RiskAppetite.CONSERVATIVE: {
        "fnma_fixed_30yr_pct": 35.0,
        "fhlmc_fixed_30yr_pct": 20.0,
        "gnma_fixed_30yr_pct": 15.0,
        "fnma_fixed_15yr_pct": 20.0,
        "fhlmc_fixed_15yr_pct": 10.0,
        "arm_pct": 0.0,
        "rationale": (
            "Conservative MBS mix avoids ARMs to minimise coupon reset risk. "
            "15YR exposure reduces duration. "
            "GNMA provides highest credit quality. No ARM exposure."
        ),
    },
    RiskAppetite.MODERATE: {
        "fnma_fixed_30yr_pct": 40.0,
        "fhlmc_fixed_30yr_pct": 20.0,
        "gnma_fixed_30yr_pct": 15.0,
        "fnma_fixed_15yr_pct": 15.0,
        "fhlmc_fixed_15yr_pct":  5.0,
        "arm_pct": 5.0,
        "rationale": (
            "Balanced MBS mix: 30YR agency MBS dominates for yield, "
            "15YR ladders provide shorter duration, small ARM sleeve "
            "benefits if rates fall. Mix of FNMA/FHLMC/GNMA for diversification."
        ),
    },
    RiskAppetite.AGGRESSIVE: {
        "fnma_fixed_30yr_pct": 45.0,
        "fhlmc_fixed_30yr_pct": 20.0,
        "gnma_fixed_30yr_pct": 10.0,
        "fnma_fixed_15yr_pct": 10.0,
        "fhlmc_fixed_15yr_pct":  5.0,
        "arm_pct": 10.0,
        "rationale": (
            "Aggressive MBS mix maximises spread income with higher 30YR "
            "allocation and meaningful ARM exposure for carry. "
            "Higher prepayment sensitivity – suitable when prepays are expected low."
        ),
    },
}


@function_tool
def decompose_mbs_allocation(
    wrapper: RunContextWrapper[WorkflowState],
) -> str:
    """
    Break down the MBS allocation into Fixed/ARM, FNFH/GNMA, and 30YR/15YR
    sub-buckets, calibrated to the selected allocation scenario and risk appetite.

    Requires state.selected_scenario to be set.
    Populates state.mbs_breakdown and returns a JSON breakdown.
    """
    state: WorkflowState = wrapper.context

    if state.selected_scenario is None:
        return json.dumps({"error": "No allocation scenario selected yet."})

    mbs_mm  = state.selected_scenario.mbs_mm
    tpl     = _MBS_DECOMP_TEMPLATES[state.risk_appetite]

    bd = MBSBreakdown(
        fnma_fixed_30yr_pct=tpl["fnma_fixed_30yr_pct"],
        fhlmc_fixed_30yr_pct=tpl["fhlmc_fixed_30yr_pct"],
        gnma_fixed_30yr_pct=tpl["gnma_fixed_30yr_pct"],
        fnma_fixed_15yr_pct=tpl["fnma_fixed_15yr_pct"],
        fhlmc_fixed_15yr_pct=tpl["fhlmc_fixed_15yr_pct"],
        arm_pct=tpl["arm_pct"],
        fnma_fixed_30yr_mm=round(mbs_mm * tpl["fnma_fixed_30yr_pct"] / 100, 1),
        fhlmc_fixed_30yr_mm=round(mbs_mm * tpl["fhlmc_fixed_30yr_pct"] / 100, 1),
        gnma_fixed_30yr_mm=round(mbs_mm * tpl["gnma_fixed_30yr_pct"] / 100, 1),
        fnma_fixed_15yr_mm=round(mbs_mm * tpl["fnma_fixed_15yr_pct"] / 100, 1),
        fhlmc_fixed_15yr_mm=round(mbs_mm * tpl["fhlmc_fixed_15yr_pct"] / 100, 1),
        arm_mm=round(mbs_mm * tpl["arm_pct"] / 100, 1),
        rationale=tpl["rationale"],
    )
    state.mbs_breakdown = bd
    return bd.model_dump_json(indent=2)


@function_tool
def build_purchase_schedule(
    wrapper: RunContextWrapper[WorkflowState],
) -> str:
    """
    Compile the final purchase schedule from the approved allocation and
    MBS decomposition. Populates state.purchase_schedule.
    """
    state: WorkflowState = wrapper.context

    if state.selected_scenario is None or state.mbs_breakdown is None:
        return json.dumps({"error": "Allocation and MBS breakdown must be complete first."})

    sc = state.selected_scenario
    mb = state.mbs_breakdown

    schedule = [
        # MBS sub-buckets
        PurchaseScheduleItem(product_type="MBS", sub_type="FNMA Fixed 30YR",
                             amount_mm=mb.fnma_fixed_30yr_mm,
                             target_coupon_range="4.50–5.50%",
                             target_duration=6.5, target_oas_bps=70.0, priority=1),
        PurchaseScheduleItem(product_type="MBS", sub_type="FHLMC Fixed 30YR",
                             amount_mm=mb.fhlmc_fixed_30yr_mm,
                             target_coupon_range="4.50–5.50%",
                             target_duration=6.4, target_oas_bps=72.0, priority=2),
        PurchaseScheduleItem(product_type="MBS", sub_type="GNMA Fixed 30YR",
                             amount_mm=mb.gnma_fixed_30yr_mm,
                             target_coupon_range="4.25–5.25%",
                             target_duration=6.6, target_oas_bps=55.0, priority=3),
        PurchaseScheduleItem(product_type="MBS", sub_type="FNMA Fixed 15YR",
                             amount_mm=mb.fnma_fixed_15yr_mm,
                             target_coupon_range="4.00–5.00%",
                             target_duration=3.8, target_oas_bps=60.0, priority=4),
        PurchaseScheduleItem(product_type="MBS", sub_type="FHLMC Fixed 15YR",
                             amount_mm=mb.fhlmc_fixed_15yr_mm,
                             target_coupon_range="4.00–5.00%",
                             target_duration=3.7, target_oas_bps=62.0, priority=5),
        PurchaseScheduleItem(product_type="MBS", sub_type="ARM (FNMA 5/1)",
                             amount_mm=mb.arm_mm,
                             target_coupon_range="4.00–4.75%",
                             target_duration=4.5, target_oas_bps=85.0, priority=6),
        # CMBS
        PurchaseScheduleItem(product_type="CMBS", sub_type="Conduit AAA",
                             amount_mm=round(sc.cmbs_mm * 0.65, 1),
                             target_coupon_range="4.75–5.50%",
                             target_duration=5.8, target_oas_bps=100.0, priority=7),
        PurchaseScheduleItem(product_type="CMBS", sub_type="Conduit AA/A",
                             amount_mm=round(sc.cmbs_mm * 0.35, 1),
                             target_coupon_range="5.25–6.00%",
                             target_duration=5.5, target_oas_bps=150.0, priority=8),
        # Treasuries
        PurchaseScheduleItem(product_type="TREASURY", sub_type="UST 10YR",
                             amount_mm=round(sc.treasury_mm * 0.60, 1),
                             target_coupon_range="4.25–4.50%",
                             target_duration=8.0, target_oas_bps=0.0, priority=9),
        PurchaseScheduleItem(product_type="TREASURY", sub_type="UST 5YR",
                             amount_mm=round(sc.treasury_mm * 0.40, 1),
                             target_coupon_range="4.40–4.65%",
                             target_duration=4.4, target_oas_bps=0.0, priority=10),
    ]
    # Remove zero-amount items
    schedule = [s for s in schedule if s.amount_mm > 0]
    state.purchase_schedule = schedule

    total = sum(s.amount_mm for s in schedule)
    return json.dumps(
        {
            "total_purchase_amount_mm": round(total, 1),
            "items": [s.model_dump() for s in schedule],
        },
        indent=2,
    )
