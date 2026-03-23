"""
ToolRegistry — maps string tool names (as declared in skill .md files)
to the actual callable function_tool objects used by the Agents SDK.

Adding a new tool:
  1. Define it with @function_tool in the appropriate tools/*.py module.
  2. Import it here and add it to _ALL_TOOLS.
  3. Reference it by name in any skill .md frontmatter.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from workflow.tools.allocation_tools import (
    build_purchase_schedule,
    decompose_mbs_allocation,
    generate_allocation_scenarios,
    select_allocation_scenario,
)
from workflow.tools.computation import (
    compute_new_volume_schedule,
    compute_volume_timing_analysis,
    summarise_pool_universe,
)
from workflow.tools.risk_tools import (
    assess_portfolio_risk,
    estimate_duration_impact,
    get_risk_constraints_summary,
)

# All tools available for agents to use, keyed by their function name.
# The key MUST match what is written in the skill .md frontmatter.
_ALL_TOOLS: Dict[str, Callable[..., Any]] = {
    # ── Computation ──────────────────────────────────────────────────────────
    "compute_new_volume_schedule":     compute_new_volume_schedule,
    "compute_volume_timing_analysis":  compute_volume_timing_analysis,
    "summarise_pool_universe":         summarise_pool_universe,
    # ── Risk ─────────────────────────────────────────────────────────────────
    "assess_portfolio_risk":           assess_portfolio_risk,
    "estimate_duration_impact":        estimate_duration_impact,
    "get_risk_constraints_summary":    get_risk_constraints_summary,
    # ── Allocation ───────────────────────────────────────────────────────────
    "generate_allocation_scenarios":   generate_allocation_scenarios,
    "select_allocation_scenario":      select_allocation_scenario,
    "decompose_mbs_allocation":        decompose_mbs_allocation,
    "build_purchase_schedule":         build_purchase_schedule,
}


class ToolRegistry:
    def __init__(self, tools: Dict[str, Callable[..., Any]] | None = None):
        self._tools = dict(tools or _ALL_TOOLS)

    # ── Singleton default ────────────────────────────────────────────────────

    _default: "ToolRegistry | None" = None

    @classmethod
    def default(cls) -> "ToolRegistry":
        if cls._default is None:
            cls._default = cls()
        return cls._default

    # ── Resolution ───────────────────────────────────────────────────────────

    def resolve(self, names: List[str]) -> List[Callable[..., Any]]:
        """
        Return the list of function_tool objects for the given names.
        Raises ValueError for any unknown name.
        """
        missing = [n for n in names if n not in self._tools]
        if missing:
            raise ValueError(
                f"Unknown tool(s): {missing}. "
                f"Available: {sorted(self._tools.keys())}"
            )
        return [self._tools[n] for n in names]

    def available(self) -> List[str]:
        return sorted(self._tools.keys())

    def register(self, name: str, tool: Callable[..., Any]) -> None:
        """Register a new tool at runtime."""
        self._tools[name] = tool
