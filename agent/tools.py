"""
Agent tools — thin shim that delegates to the `tool/` package.

All schemas and handler logic live in tool/<name>_tool.py.
This module preserves the public API used by agent/base_agent.py and tests:

    from agent.tools import OPENAI_TOOLS, TOOLS, handle_tool_call
"""
from __future__ import annotations

from tool.registry import OPENAI_TOOLS, handle_tool_call, list_tools

# Backwards-compatible alias
TOOLS = OPENAI_TOOLS

__all__ = ["OPENAI_TOOLS", "TOOLS", "handle_tool_call", "list_tools"]
