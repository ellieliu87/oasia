"""
Multi-agent orchestrator for Oasia — company SDK version.

Changes from original:
  - Replaces openai.OpenAI(api_key=...) + manual tool-calling loop
    with OpenAIChatCompletionsModel + Agent + await Runner.run()
  - Delegate tools built as FunctionTool objects (replacing _build_delegate_tools dicts)
  - _dispatch_delegation removed; delegation handled inside FunctionTool closures
  - chat() and run_quick_query() are now async
  - _has_api guard and _stub_response removed (no API key required)
  - api_key param kept in __init__ for call-site compatibility
"""
from __future__ import annotations

import json
import traceback
from datetime import date

from agent.skill_loader import load_all_skills
from agent.base_agent import BaseAgent
from agent.tools import OPENAI_TOOLS, handle_tool_call
from agent.prompts import QUICK_QUERIES
from weave_config import weave_op

_op = weave_op()

_SUB_AGENT_SKILLS = [
    "security_selection",
    "what_if_analysis",
    "portfolio_analytics",
    "attribution",
    "market_data",
    "dashboard",
]


class AgentOrchestrator:
    """
    Multi-agent orchestrator for Oasia.

    Public API (async):
        await .chat(message) -> str
        await .run_quick_query(name) -> str
        .clear_history() -> None
        .check_alerts(portfolio_summary) -> list[str]
    """

    def __init__(self, api_key: str | None = None):  # api_key kept for compatibility
        from agents import Agent, FunctionTool, OpenAIChatCompletionsModel, set_tracing_disabled
        from openai import AsyncOpenAI

        set_tracing_disabled(True)   # use Weave for tracing instead

        self._skills = load_all_skills()

        # ── Build sub-agents ─────────────────────────────────────────────────
        self._sub_agents: dict[str, BaseAgent] = {}
        for name in _SUB_AGENT_SKILLS:
            skill = self._skills.get(name)
            if skill is None:
                continue
            self._sub_agents[name] = BaseAgent(
                skill=skill,
                openai_tools=OPENAI_TOOLS,
                tool_handler=handle_tool_call,
            )

        # ── Build delegate FunctionTools — one per sub-agent ─────────────────
        orch_skill = self._skills.get("orchestrator")
        delegate_tools = []

        for agent_key, sub_agent in self._sub_agents.items():
            skill     = self._skills[agent_key]
            safe_name = skill.name.replace("-", "_")

            def _make_delegate(key: str, agent: BaseAgent, sk) -> FunctionTool:
                async def _invoke(ctx, input: str) -> str:
                    try:
                        args = json.loads(input) if input else {}
                    except json.JSONDecodeError:
                        args = {}
                    query = args.get("query", "")
                    try:
                        return await agent.chat(query, fresh=True)
                    except Exception as exc:
                        return json.dumps({
                            "error": f"Sub-agent '{key}' failed: {exc}",
                            "traceback": traceback.format_exc()[-400:],
                        })

                return FunctionTool(
                    name=f"delegate_to_{key}",
                    description=sk.description,
                    params_json_schema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": (
                                    f"The full query to send to the {sk.name} specialist agent. "
                                    "Include all relevant context — the sub-agent does not see the "
                                    "conversation history, only this query."
                                ),
                            }
                        },
                        "required": ["query"],
                    },
                    on_invoke_tool=_invoke,
                )

            delegate_tools.append(_make_delegate(safe_name, sub_agent, skill))

        # ── Build orchestrator Agent ─────────────────────────────────────────
        _model = OpenAIChatCompletionsModel(
            model=orch_skill.model if orch_skill else "gpt-oss-120b",
            openai_client=AsyncOpenAI(),
        )
        self._orch_agent = Agent(
            name="orchestrator",
            instructions=(
                orch_skill.system_prompt if orch_skill
                else "You are the Oasia orchestrator."
            ),
            model=_model,
            tools=delegate_tools,
        )
        self._orch_skill       = orch_skill
        self._history: list    = []
        self._portfolio_context: dict = {}

    # ── Public API ────────────────────────────────────────────────────────────

    @_op
    async def chat(self, user_message: str, portfolio_context: dict | None = None) -> str:
        """Send a message through the multi-agent workflow and return the response."""
        from agents import Runner

        if portfolio_context:
            self._portfolio_context = portfolio_context

        # Inject portfolio + date context into the prompt
        context_parts = [f"Today's date: {date.today()}"]
        if self._portfolio_context:
            p = self._portfolio_context
            context_parts.append(
                f"Portfolio: OAS={p.get('weighted_oas_bps', 'N/A')} bps, "
                f"OAD={p.get('weighted_oad_years', 'N/A')} yr, "
                f"Yield={p.get('total_yield_pct', 'N/A')}%, "
                f"EVE+200={p.get('eve_up200_bps_change_pct', 'N/A')}%"
            )
        context = "\n".join(context_parts)
        prompt  = f"{user_message}\n\n---\n## Session Context\n{context}"

        try:
            result = await Runner.run(self._orch_agent, prompt)
            return result.final_output or ""
        except Exception as exc:
            return f"[Orchestrator error: {exc}]"

    async def run_quick_query(self, query_name: str) -> str:
        """Run a pre-wired quick query by name."""
        prompt = QUICK_QUERIES.get(query_name)
        if prompt is None:
            return f"Unknown query: {query_name}. Available: {list(QUICK_QUERIES.keys())}"
        self._history = []
        return await self.chat(prompt.strip())

    def clear_history(self) -> None:
        """Clear orchestrator conversation history and reset all sub-agents."""
        self._history = []
        for agent in self._sub_agents.values():
            agent.reset()

    def check_alerts(self, portfolio_summary: dict) -> list[str]:
        """Return proactive alert messages based on portfolio state. Unchanged."""
        alerts = []

        eve_pct   = portfolio_summary.get("eve_up200_bps_change_pct", 0.0)
        eve_limit = portfolio_summary.get("eve_limit_pct", -5.0)
        if isinstance(eve_pct, (int, float)) and eve_pct < eve_limit:
            alerts.append(
                f"EVE BREACH: +200 bp EVE change = {eve_pct:.1f}% vs limit {eve_limit:.1f}%. "
                "Immediate rebalancing required."
            )

        oad = portfolio_summary.get("weighted_oad_years", 0.0)
        if isinstance(oad, (int, float)) and oad > 6.0:
            alerts.append(
                f"DURATION ALERT: Portfolio OAD {oad:.2f} yr is elevated (>6.0 yr). "
                "Consider reducing premium CC30 exposure."
            )

        oas = portfolio_summary.get("weighted_oas_bps", 0.0)
        if isinstance(oas, (int, float)) and oas < 30.0:
            alerts.append(
                f"VALUATION: Portfolio OAS {oas:.1f} bps is historically tight. "
                "New purchase yield pickup may be limited."
            )

        return alerts
