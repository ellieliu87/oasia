"""
Pure-computation tools used by the New Volume Agent.

These are deterministic functions with no LLM calls. They are also
exposed as OpenAI Agents SDK function_tools so agents can invoke them.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd

from agents import RunContextWrapper, function_tool
from workflow.models.workflow_state import MonthlyVolume, WorkflowState


# ---------------------------------------------------------------------------
# Helper: DataFrame → serialisable summary
# ---------------------------------------------------------------------------

def _df_to_monthly_volumes(portfolio_df: pd.DataFrame) -> List[MonthlyVolume]:
    records = []
    for _, row in portfolio_df.iterrows():
        records.append(MonthlyVolume(
            date=str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"]),
            target_total_balance_mm=float(row["target_total_balance_mm"]),
            predicted_existing_balance_mm=float(row["predicted_existing_balance_mm"]),
            new_volume_mm=float(row["new_volume_mm"]),
        ))
    return records


# ---------------------------------------------------------------------------
# Agent-callable tools
# ---------------------------------------------------------------------------

@function_tool
def compute_new_volume_schedule(
    wrapper: RunContextWrapper[WorkflowState],
) -> str:
    """
    Calculate the monthly new-volume purchase schedule from the workflow state.
    Populates state.monthly_volumes, state.next_12m_new_volume_mm,
    and state.total_10yr_new_volume_mm.
    Returns a JSON summary of the first 24 months and annual totals.
    """
    state: WorkflowState = wrapper.context

    if not state.monthly_volumes:
        return json.dumps({"error": "monthly_volumes not loaded into state yet."})

    vols = state.monthly_volumes
    next12 = sum(v.new_volume_mm for v in vols[:12])
    total10yr = sum(v.new_volume_mm for v in vols)

    state.next_12m_new_volume_mm = round(next12, 2)
    state.total_10yr_new_volume_mm = round(total10yr, 2)

    # Annual totals
    annual: Dict[str, float] = {}
    for i, v in enumerate(vols):
        year = f"Year {i // 12 + 1}"
        annual[year] = round(annual.get(year, 0) + v.new_volume_mm, 2)

    first_24 = [
        {
            "date": v.date,
            "target_mm": v.target_total_balance_mm,
            "predicted_existing_mm": v.predicted_existing_balance_mm,
            "new_volume_mm": v.new_volume_mm,
        }
        for v in vols[:24]
    ]

    return json.dumps(
        {
            "next_12m_new_volume_mm": next12,
            "total_10yr_new_volume_mm": total10yr,
            "annual_totals_mm": annual,
            "first_24_months": first_24,
        },
        indent=2,
    )


@function_tool
def summarise_pool_universe(
    wrapper: RunContextWrapper[WorkflowState],
) -> str:
    """
    Return a statistical summary of the current pool universe stored in
    state.pool_summary. Useful for risk assessment and allocation decisions.
    """
    state: WorkflowState = wrapper.context

    if not state.pool_summary:
        return json.dumps({"error": "pool_summary not loaded into state yet."})

    return json.dumps(state.pool_summary, indent=2)


@function_tool
def compute_volume_timing_analysis(
    wrapper: RunContextWrapper[WorkflowState],
    horizon_months: int = 36,
) -> str:
    """
    Analyse the purchase timing: when is new volume highest / most urgent?
    Returns monthly buckets grouped into 3 periods (0-12m, 13-24m, 25-36m).

    Args:
        horizon_months: How many months forward to analyse (max 120).
    """
    state: WorkflowState = wrapper.context
    vols = state.monthly_volumes
    if not vols:
        return json.dumps({"error": "No volume data in state."})

    horizon_months = min(horizon_months, len(vols))
    buckets: Dict[str, Dict[str, Any]] = {}
    for i, v in enumerate(vols[:horizon_months]):
        label = f"Months {(i // 12) * 12 + 1}–{(i // 12 + 1) * 12}"
        if label not in buckets:
            buckets[label] = {"total_mm": 0.0, "avg_monthly_mm": 0.0, "months": []}
        buckets[label]["total_mm"] = round(buckets[label]["total_mm"] + v.new_volume_mm, 2)
        buckets[label]["months"].append({"date": v.date, "new_volume_mm": v.new_volume_mm})

    for k, b in buckets.items():
        n = len(b["months"])
        b["avg_monthly_mm"] = round(b["total_mm"] / n, 2) if n else 0.0

    return json.dumps(
        {
            "horizon_months": horizon_months,
            "buckets": buckets,
        },
        indent=2,
    )
