"""
BaseAgent — generic OpenAI agentic loop driven by a loaded AgentSkill.

Each BaseAgent:
  - Holds a skill (system prompt + allowed tools list)
  - Runs the full tool-calling loop via the OpenAI chat completions API
  - Returns a text response after all tool calls are resolved
"""
from __future__ import annotations

import json
import traceback
from typing import Any

from agent.skill_loader import AgentSkill
from weave_config import weave_op

_op = weave_op()   # weave.op if Weave installed + inited, else no-op


class BaseAgent:
    """
    An OpenAI-powered agent whose behaviour is defined by an AgentSkill.

    The skill specifies:
    - system_prompt  : the agent's instructions (from the skill markdown body)
    - tools          : which analytics tools this agent may call
    - model          : which OpenAI model to use
    - max_tokens     : maximum tokens in a single completion
    """

    MAX_ITERATIONS = 10  # safety cap on tool-call loops

    def __init__(
        self,
        skill: AgentSkill,
        openai_tools: list[dict],           # full OPENAI_TOOLS list from tools.py
        tool_handler,                        # callable: (name, args_dict) -> str
        api_key: str | None = None,
        extra_context: str = "",            # injected at runtime (portfolio state, market data)
    ):
        import openai as _openai

        self.skill = skill
        self.tool_handler = tool_handler
        self.extra_context = extra_context
        self._history: list[dict] = []

        # Filter the global tool list to only the tools permitted by this skill
        if skill.tools:
            tool_names = set(skill.tools)
            self._tools = [
                t for t in openai_tools
                if t.get("function", {}).get("name") in tool_names
            ]
        else:
            self._tools = []  # orchestrator-level agents define their own delegate tools

        # OpenAI client — only created when an API key is available
        if api_key:
            self._client = _openai.OpenAI(api_key=api_key)
        else:
            self._client = None  # will raise clearly on .chat() if no key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @_op
    def chat(
        self,
        user_message: str,
        extra_context: str = "",
        fresh: bool = True,
    ) -> str:
        """
        Send a message to this agent, resolve all tool calls, and return the
        final text response.

        Parameters
        ----------
        user_message : str
        extra_context : str
            Additional runtime context to append to the system prompt
            (e.g. current portfolio state injected by the orchestrator).
        fresh : bool
            If True (default), clear conversation history before this call
            so each invocation is stateless. Set False to maintain context
            across turns within the same sub-agent.

        Returns
        -------
        str  — final text response from the model.
        """
        if fresh:
            self._history = []

        if self._client is None:
            return "[Agent unavailable: OPENAI_API_KEY not set]"

        self._history.append({"role": "user", "content": user_message})

        system_prompt = self._build_system_prompt(extra_context or self.extra_context)

        for iteration in range(self.MAX_ITERATIONS):
            kwargs: dict[str, Any] = {
                "model": self.skill.model,
                "max_tokens": self.skill.max_tokens,
                "messages": [{"role": "system", "content": system_prompt}] + self._history,
            }
            if self._tools:
                kwargs["tools"] = self._tools
                kwargs["tool_choice"] = "auto"

            response = self._client.chat.completions.create(**kwargs)
            msg = response.choices[0].message

            # Append assistant message to history
            self._history.append(msg.model_dump(exclude_unset=True))

            finish = response.choices[0].finish_reason

            if finish == "tool_calls" and msg.tool_calls:
                # Execute all tool calls and collect results
                tool_results = []
                for tc in msg.tool_calls:
                    result = self._execute_tool(tc.function.name, tc.function.arguments)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                self._history.extend(tool_results)

            else:
                # Done — extract text
                return msg.content or ""

        return "Reached maximum iteration limit. Please try a more specific query."

    def reset(self) -> None:
        """Clear conversation history."""
        self._history = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self, extra_context: str) -> str:
        parts = [self.skill.system_prompt]
        if extra_context:
            parts.append(f"\n\n---\n## Runtime Context\n{extra_context}")
        return "\n".join(parts)

    @_op
    def _execute_tool(self, tool_name: str, arguments_json: str) -> str:
        """Parse arguments and dispatch to the tool handler."""
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError:
            args = {}

        try:
            return self.tool_handler(tool_name, args)
        except Exception as exc:
            return json.dumps({
                "error": str(exc),
                "traceback": traceback.format_exc()[-400:],
            })
