"""
BaseAgent — company SDK version (agents + OpenAIChatCompletionsModel).

Changes from original:
  - Replaces openai.OpenAI(api_key=...) + manual tool-calling loop
    with OpenAIChatCompletionsModel + Agent + await Runner.run()
  - chat() is now async
  - api_key param kept for call-site compatibility but is no longer used
  - _execute_tool removed; tool dispatch handled by Runner via FunctionTool
"""
from __future__ import annotations

import json
import traceback

from agent.skill_loader import AgentSkill
from weave_config import weave_op

_op = weave_op()


class BaseAgent:

    def __init__(
        self,
        skill: AgentSkill,
        openai_tools: list[dict],
        tool_handler,
        api_key: str | None = None,   # no longer used; kept for call-site compatibility
        extra_context: str = "",
    ):
        from agents import Agent, FunctionTool, OpenAIChatCompletionsModel, set_tracing_disabled
        from openai import AsyncOpenAI

        set_tracing_disabled(True)   # use Weave for tracing instead

        self.skill = skill
        self.tool_handler = tool_handler
        self.extra_context = extra_context
        self._history: list[dict] = []

        # ── Company model — no API key required ──────────────────────────────
        _model = OpenAIChatCompletionsModel(
            model=skill.model,          # read from skill frontmatter, e.g. "gpt-oss-120b"
            openai_client=AsyncOpenAI(),
        )

        # ── Convert OpenAI tool dicts → FunctionTool objects ─────────────────
        def _make_tool(tool_dict: dict) -> FunctionTool:
            fn   = tool_dict["function"]
            name = fn["name"]
            desc = fn.get("description", "")
            schema = fn.get("parameters", {"type": "object", "properties": {}})

            async def _invoke(ctx, input: str) -> str:
                try:
                    args = json.loads(input) if input else {}
                except json.JSONDecodeError:
                    args = {}
                try:
                    return tool_handler(name, args)
                except Exception as exc:
                    return json.dumps({
                        "error": str(exc),
                        "traceback": traceback.format_exc()[-400:],
                    })

            return FunctionTool(
                name=name,
                description=desc,
                params_json_schema=schema,
                on_invoke_tool=_invoke,
            )

        if skill.tools:
            tool_names = set(skill.tools)
            agent_tools = [
                _make_tool(t) for t in openai_tools
                if t.get("function", {}).get("name") in tool_names
            ]
        else:
            agent_tools = []

        self._agent = Agent(
            name=skill.name,
            instructions=skill.system_prompt,
            model=_model,
            tools=agent_tools,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    @_op
    async def chat(
        self,
        user_message: str,
        extra_context: str = "",
        fresh: bool = True,
    ) -> str:
        from agents import Runner

        if fresh:
            self._history = []

        context = extra_context or self.extra_context
        prompt   = user_message
        if context:
            prompt = f"{user_message}\n\n---\n## Runtime Context\n{context}"

        try:
            result = await Runner.run(self._agent, prompt)
            return result.final_output or ""
        except Exception as exc:
            return json.dumps({
                "error": str(exc),
                "traceback": traceback.format_exc()[-400:],
            })

    def reset(self) -> None:
        """Clear conversation history."""
        self._history = []
