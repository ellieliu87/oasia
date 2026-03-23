"""
tool/ — Oasia agent tool package.

Each sub-module exposes:
  TOOL_SCHEMAS : list[dict]            — OpenAI function-calling schemas
  HANDLERS     : dict[str, callable]   — name → handler(inp: dict) -> str (JSON)

Import from tool.registry to avoid circular imports at package init time.

    from tool.registry import OPENAI_TOOLS, handle_tool_call
"""
# Sub-modules are imported directly; avoid importing registry here to prevent
# circular-import chains (registry imports sub-modules, sub-modules may import
# from each other through tool/).
from tool import (  # noqa: F401 — make sub-modules importable as tool.<name>
    term_structure_tool,
    prepay_tool,
    interest_income_tool,
    analytics_tool,
    data_tool,
    portfolio_tool,
    scenario_tool,
    db_tool,
)

__all__ = [
    "term_structure_tool",
    "prepay_tool",
    "interest_income_tool",
    "analytics_tool",
    "data_tool",
    "portfolio_tool",
    "scenario_tool",
    "db_tool",
]
