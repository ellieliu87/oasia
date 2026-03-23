"""
Tool Registry
=============
Aggregates all tool schemas and handlers from the individual tool modules.

Usage:
    from tool.registry import OPENAI_TOOLS, handle_tool_call

    # Pass OPENAI_TOOLS to the OpenAI client's `tools` parameter.
    # Use handle_tool_call(name, args_dict) to dispatch calls.
"""
from __future__ import annotations

import json
import traceback
from typing import Any

from weave_config import weave_op
from tool import (
    term_structure_tool,
    prepay_tool,
    interest_income_tool,
    analytics_tool,
    data_tool,
    portfolio_tool,
    scenario_tool,
    db_tool,
)

# ── Aggregate all schemas ──────────────────────────────────────────────────────

OPENAI_TOOLS: list[dict] = (
    data_tool.TOOL_SCHEMAS              # screen_securities, get_pool_details,
                                        # get_market_data, get_universe_summary
    + db_tool.TOOL_SCHEMAS              # query_risk_metrics, query_prepay_speeds,
                                        # query_interest_income, get_cache_status,
                                        # run_sql_query
    + term_structure_tool.TOOL_SCHEMAS  # generate_rate_paths, get_rate_path_summary
    + prepay_tool.TOOL_SCHEMAS          # forecast_prepayment, compare_prepayment_scenarios
    + interest_income_tool.TOOL_SCHEMAS # compute_interest_income,
                                        # compute_portfolio_interest_income
    + analytics_tool.TOOL_SCHEMAS       # compute_bond_analytics, batch_compute_analytics
    + portfolio_tool.TOOL_SCHEMAS       # get_portfolio_summary, get_portfolio_positions,
                                        # compute_eve_profile, get_attribution
    + scenario_tool.TOOL_SCHEMAS        # run_scenario_analysis, run_what_if
)

# Backwards-compatible alias (used in agent/tools.py and tests)
TOOLS = OPENAI_TOOLS

# ── Aggregate all handlers ────────────────────────────────────────────────────

_HANDLERS: dict[str, Any] = {
    **data_tool.HANDLERS,
    **db_tool.HANDLERS,
    **term_structure_tool.HANDLERS,
    **prepay_tool.HANDLERS,
    **interest_income_tool.HANDLERS,
    **analytics_tool.HANDLERS,
    **portfolio_tool.HANDLERS,
    **scenario_tool.HANDLERS,
}


@weave_op()
def handle_tool_call(tool_name: str, tool_input: dict) -> str:
    """
    Dispatch a tool call to the appropriate handler.

    Parameters
    ----------
    tool_name  : str  — OpenAI function name.
    tool_input : dict — Parsed JSON arguments.

    Returns
    -------
    str — JSON-encoded result or error.
    """
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: '{tool_name}'.  "
                           f"Available: {sorted(_HANDLERS.keys())}"})
    try:
        return handler(tool_input)
    except Exception as exc:
        return json.dumps({
            "error":     str(exc),
            "traceback": traceback.format_exc()[-800:],
        })


def list_tools() -> list[str]:
    """Return all registered tool names."""
    return sorted(_HANDLERS.keys())
