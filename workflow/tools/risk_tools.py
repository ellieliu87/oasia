"""
Risk analysis tools for the Risk Assessment Agent.

Computes portfolio duration, liquidity scores, and constraint envelopes.
"""

from __future__ import annotations

import json
import math
from typing import Dict, List

from agents import RunContextWrapper, function_tool
from workflow.models.workflow_state import RiskConstraints, WorkflowState


# ---------------------------------------------------------------------------
# Duration / convexity math helpers
# ---------------------------------------------------------------------------

def _weighted_avg(values: List[float], weights: List[float]) -> float:
    total_w = sum(weights)
    if total_w == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_w


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@function_tool
def assess_portfolio_risk(
    wrapper: RunContextWrapper[WorkflowState],
) -> str:
    """
    Evaluate the current portfolio's risk profile using pool summary data
    in state.pool_summary. Produces duration, liquidity, concentration,
    and spread risk metrics. Populates state.risk_constraints.

    Returns a detailed JSON risk report.
    """
    state: WorkflowState = wrapper.context
    summary = state.pool_summary

    if not summary:
        return json.dumps({"error": "pool_summary not loaded."})

    by_type = summary.get("by_product_type", {})
    total_balance = summary.get("total_balance_mm", 1.0)

    # ── Current portfolio duration (balance-weighted) ─────────────────────
    durations, balances = [], []
    for pt, stats in by_type.items():
        durations.append(stats.get("avg_duration", 5.0))
        balances.append(stats.get("total_balance_mm", 0.0))
    current_duration = _weighted_avg(durations, balances)

    # ── Liquidity score ───────────────────────────────────────────────────
    liq_scores, liq_balances = [], []
    for pt, stats in by_type.items():
        liq_scores.append(stats.get("avg_liquidity_score", 7.0))
        liq_balances.append(stats.get("total_balance_mm", 0.0))
    liquidity_score = _weighted_avg(liq_scores, liq_balances)

    # ── Concentration ─────────────────────────────────────────────────────
    concentration: Dict[str, float] = {}
    for pt, stats in by_type.items():
        pct = stats.get("total_balance_mm", 0.0) / total_balance * 100
        concentration[pt] = round(pct, 1)

    mbs_pct  = concentration.get("MBS", 0.0)
    cmbs_pct = concentration.get("CMBS", 0.0)
    tsy_pct  = concentration.get("TREASURY", 0.0)

    # ── OAS / spread risk ─────────────────────────────────────────────────
    oas_by_type: Dict[str, float] = {}
    for pt, stats in by_type.items():
        oas_by_type[pt] = stats.get("avg_oas_bps", 0.0)

    # ── Risk flags ────────────────────────────────────────────────────────
    flags: List[str] = []
    if current_duration > 6.0:
        flags.append("⚠  Portfolio duration > 6.0 – elevated interest-rate risk")
    if current_duration < 3.5:
        flags.append("⚠  Portfolio duration < 3.5 – reinvestment risk if rates fall")
    if cmbs_pct > 30:
        flags.append("⚠  CMBS concentration > 30% – credit spread risk elevated")
    if liquidity_score < 6.5:
        flags.append("⚠  Liquidity score below 6.5 – bid-ask costs may be elevated")
    if mbs_pct < 40:
        flags.append("ℹ  MBS below 40% – consider increasing agency exposure for yield")

    # ── Build constraints ─────────────────────────────────────────────────
    dur_min = max(3.0, current_duration - 1.5)
    dur_max = min(8.0, current_duration + 1.5)
    constraints = RiskConstraints(
        duration_min=round(dur_min, 2),
        duration_max=round(dur_max, 2),
        current_portfolio_duration=round(current_duration, 3),
        projected_duration_after_purchase=round(current_duration, 3),
        liquidity_score_min=6.0,
        projected_liquidity_score=round(liquidity_score, 2),
        max_cmbs_pct=30.0,
        max_arm_pct=20.0,
        notes=flags,
    )
    state.risk_constraints = constraints

    report = {
        "current_portfolio": {
            "total_balance_mm": total_balance,
            "duration_years": round(current_duration, 3),
            "liquidity_score": round(liquidity_score, 2),
            "concentration_pct": concentration,
            "avg_oas_by_type_bps": oas_by_type,
        },
        "risk_constraints": constraints.model_dump(),
        "flags": flags,
        "recommendation": (
            "Portfolio duration is within acceptable bounds. "
            "Focus new purchases on maintaining duration 4.5–5.5 years. "
            "Prefer agency MBS for liquidity; limit CMBS to 25% of new volume."
        ) if not flags else (
            "Address flagged risks before finalising allocation. "
            "Consider Treasuries to reduce duration if elevated; "
            "FNMA/GNMA agency MBS to improve liquidity."
        ),
    }
    state.risk_report = json.dumps(report, indent=2)
    return state.risk_report


@function_tool
def estimate_duration_impact(
    wrapper: RunContextWrapper[WorkflowState],
    mbs_pct: float,
    cmbs_pct: float,
    treasury_pct: float,
    new_volume_mm: float,
) -> str:
    """
    Estimate the portfolio duration impact of a proposed allocation.

    Args:
        mbs_pct: Percentage allocated to MBS (0–100).
        cmbs_pct: Percentage allocated to CMBS (0–100).
        treasury_pct: Percentage allocated to Treasuries (0–100).
        new_volume_mm: Total new purchase volume in $MM.

    Returns JSON with projected portfolio duration and liquidity score.
    """
    state: WorkflowState = wrapper.context

    if abs(mbs_pct + cmbs_pct + treasury_pct - 100) > 0.5:
        return json.dumps({"error": "Percentages must sum to 100."})

    # Typical durations for each asset class (mid-point estimates)
    MBS_DUR      = 5.2   # agency MBS 30YR blend
    CMBS_DUR     = 5.8   # conduit CMBS
    TREASURY_DUR = 6.0   # 10YR TSY proxy

    MBS_LIQ  = 8.8
    CMBS_LIQ = 6.0
    TSY_LIQ  = 10.0

    new_dur = (
        MBS_DUR      * mbs_pct / 100
        + CMBS_DUR   * cmbs_pct / 100
        + TREASURY_DUR * treasury_pct / 100
    )
    new_liq = (
        MBS_LIQ  * mbs_pct / 100
        + CMBS_LIQ * cmbs_pct / 100
        + TSY_LIQ  * treasury_pct / 100
    )

    rc = state.risk_constraints
    if rc:
        existing_balance = state.monthly_volumes[0].predicted_existing_balance_mm if state.monthly_volumes else 9000.0
        blended_dur = (
            rc.current_portfolio_duration * existing_balance
            + new_dur * new_volume_mm
        ) / (existing_balance + new_volume_mm)
        blended_liq = (
            rc.projected_liquidity_score * existing_balance
            + new_liq * new_volume_mm
        ) / (existing_balance + new_volume_mm)
    else:
        blended_dur = new_dur
        blended_liq = new_liq

    within_bounds = (
        rc.duration_min <= blended_dur <= rc.duration_max
        if rc else True
    )

    return json.dumps(
        {
            "new_purchase_duration": round(new_dur, 3),
            "projected_portfolio_duration": round(blended_dur, 3),
            "projected_liquidity_score": round(blended_liq, 2),
            "within_duration_bounds": within_bounds,
            "duration_min": rc.duration_min if rc else None,
            "duration_max": rc.duration_max if rc else None,
        },
        indent=2,
    )


@function_tool
def get_risk_constraints_summary(
    wrapper: RunContextWrapper[WorkflowState],
) -> str:
    """Return the current risk constraints stored in the workflow state."""
    state: WorkflowState = wrapper.context
    if state.risk_constraints is None:
        return json.dumps({"error": "Risk constraints not yet computed. Run assess_portfolio_risk first."})
    return state.risk_constraints.model_dump_json(indent=2)
