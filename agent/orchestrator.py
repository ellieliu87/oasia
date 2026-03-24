"""
Multi-agent orchestrator for Oasia — powered by the OpenAI SDK.

Architecture
────────────
                     User message
                          │
              ┌───────────▼───────────┐
              │   OrchestratorAgent   │  (orchestrator.md skill)
              │   gpt-4o              │
              │                       │
              │  delegate_to_*  tools │
              └──┬──────┬──────┬──────┘
                 │      │      │  ...
        ┌────────▼─┐ ┌──▼───┐ ┌▼──────────────┐
        │ Security │ │Portf.│ │ Attribution   │  ...
        │Selection │ │Anal. │ │               │
        │(BaseAgent│ │      │ │               │
        │ gpt-4o)  │ │      │ │               │
        └──────────┘ └──────┘ └───────────────┘

1. The orchestrator LLM receives the user message.
2. It calls one or more `delegate_to_<agent>` tools.
3. For each delegation the corresponding BaseAgent runs its own
   agentic loop (calling analytics tools, resolving results).
4. The sub-agent's text response is returned to the orchestrator
   as a tool result.
5. The orchestrator synthesises a final response.

All agents use skills loaded from agent/skills/*.md files.
The MockIntexClient is used automatically when INTEX_API_KEY is not set.
"""
from __future__ import annotations

import json
import os
import traceback
from datetime import date
from typing import Any

from agent.skill_loader import load_all_skills, AgentSkill
from agent.base_agent import BaseAgent
from agent.tools import OPENAI_TOOLS, handle_tool_call
from agent.prompts import QUICK_QUERIES
from weave_config import weave_op

_op = weave_op()


# ---------------------------------------------------------------------------
# Sub-agent registry
# ---------------------------------------------------------------------------

# Maps skill name (normalised) → which analytics tool names the agent may use
# (mirrors the `tools:` list in each skill's frontmatter, kept here for clarity)
_SUB_AGENT_SKILLS = [
    "security_selection",
    "what_if_analysis",
    "portfolio_analytics",
    "attribution",
    "market_data",
    "dashboard",
]


def _build_delegate_tools(sub_agent_skills: list[AgentSkill]) -> list[dict]:
    """
    Build OpenAI-format delegate tools: one per sub-agent.

    Each tool is named `delegate_to_<name>` and accepts a single
    `query` string parameter that is forwarded verbatim to the sub-agent.
    """
    tools = []
    for skill in sub_agent_skills:
        safe_name = skill.name.replace("-", "_")
        tools.append({
            "type": "function",
            "function": {
                "name": f"delegate_to_{safe_name}",
                "description": skill.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                f"The full query to send to the {skill.name} specialist agent. "
                                "Include all relevant context — the sub-agent does not see the "
                                "conversation history, only this query."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        })
    return tools


# ---------------------------------------------------------------------------
# AgentOrchestrator
# ---------------------------------------------------------------------------

class AgentOrchestrator:
    """
    Multi-agent orchestrator for Oasia.

    Public API is identical to the original single-agent version so that
    ui/agent_panel.py and tests require no changes:
        .chat(message) -> str
        .run_quick_query(name) -> str
        .clear_history() -> None
        .check_alerts(portfolio_summary) -> list[str]
    """

    MAX_ITERATIONS = 8

    def __init__(self, api_key: str | None = None):
        # Resolve API key
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY", "")

        self._api_key = api_key
        self._has_api = bool(api_key)

        # Load all skills from markdown files
        self._skills = load_all_skills()

        # Build sub-agents (one per specialist skill)
        self._sub_agents: dict[str, BaseAgent] = {}
        for name in _SUB_AGENT_SKILLS:
            skill = self._skills.get(name)
            if skill is None:
                continue
            self._sub_agents[name] = BaseAgent(
                skill=skill,
                openai_tools=OPENAI_TOOLS,
                tool_handler=handle_tool_call,
                api_key=api_key or None,
            )

        # Build orchestrator agent
        orch_skill = self._skills.get("orchestrator")
        sub_agent_list = [
            self._skills[n] for n in _SUB_AGENT_SKILLS if n in self._skills
        ]
        delegate_tools = _build_delegate_tools(sub_agent_list)

        if orch_skill and self._has_api:
            import openai as _openai
            self._orch_client = _openai.OpenAI(api_key=api_key)
        else:
            self._orch_client = None
        self._orch_skill = orch_skill
        self._delegate_tools = delegate_tools

        self._history: list[dict] = []
        self._portfolio_context: dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @_op
    def chat(self, user_message: str, portfolio_context: dict | None = None) -> str:
        """Send a message through the multi-agent workflow and return the response."""
        if portfolio_context:
            self._portfolio_context = portfolio_context

        if not self._has_api:
            return self._stub_response(user_message)

        try:
            from agents import trace as agents_trace
            _trace_ctx = agents_trace("nexus_orchestrator")
        except Exception:
            _trace_ctx = None

        def _run() -> str:
            self._history.append({"role": "user", "content": user_message})
            system_prompt = self._build_orch_system_prompt()

            for _ in range(self.MAX_ITERATIONS):
                response = self._orch_client.chat.completions.create(
                    model=self._orch_skill.model if self._orch_skill else "gpt-4o",
                    max_tokens=self._orch_skill.max_tokens if self._orch_skill else 1024,
                    messages=[{"role": "system", "content": system_prompt}] + self._history,
                    tools=self._delegate_tools,
                    tool_choice="auto",
                )
                msg = response.choices[0].message
                self._history.append(msg.model_dump(exclude_unset=True))

                finish = response.choices[0].finish_reason

                if finish == "tool_calls" and msg.tool_calls:
                    tool_results = []
                    for tc in msg.tool_calls:
                        result = self._dispatch_delegation(tc.function.name, tc.function.arguments)
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })
                    self._history.extend(tool_results)
                else:
                    return msg.content or ""

            return "Reached the maximum orchestration limit. Please try a more specific query."

        if _trace_ctx is not None:
            with _trace_ctx:
                return _run()
        return _run()

    def run_quick_query(self, query_name: str) -> str:
        """Run a pre-wired quick query by name."""
        prompt = QUICK_QUERIES.get(query_name)
        if prompt is None:
            return f"Unknown query: {query_name}. Available: {list(QUICK_QUERIES.keys())}"
        self._history = []
        return self.chat(prompt.strip())

    def clear_history(self) -> None:
        """Clear orchestrator conversation history and reset all sub-agents."""
        self._history = []
        for agent in self._sub_agents.values():
            agent.reset()

    def check_alerts(self, portfolio_summary: dict) -> list[str]:
        """Return proactive alert messages based on portfolio state."""
        alerts = []

        eve_pct = portfolio_summary.get("eve_up200_bps_change_pct", 0.0)
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_orch_system_prompt(self) -> str:
        """Inject current portfolio + market context into the orchestrator system prompt."""
        base = (self._orch_skill.system_prompt if self._orch_skill
                else "You are the Oasia orchestrator.")

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
        return f"{base}\n\n---\n## Session Context\n{context}"

    @_op
    def _dispatch_delegation(self, tool_name: str, arguments_json: str) -> str:
        """
        Route a delegate_to_<agent> call to the appropriate sub-agent.

        The sub-agent runs its full agentic loop and returns a text response,
        which is passed back to the orchestrator as the tool result.
        """
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError:
            args = {}

        query = args.get("query", "")

        # Map delegate tool name back to sub-agent key
        # e.g. "delegate_to_security_selection" → "security_selection"
        prefix = "delegate_to_"
        if tool_name.startswith(prefix):
            agent_key = tool_name[len(prefix):]
        else:
            return json.dumps({"error": f"Unknown delegate tool: {tool_name}"})

        agent = self._sub_agents.get(agent_key)
        if agent is None:
            return json.dumps({"error": f"No sub-agent registered for '{agent_key}'"})

        try:
            from agents.tracing import custom_span
            _span_ctx = custom_span(f"delegate:{agent_key}", {"query": query[:200]})
        except Exception:
            _span_ctx = None

        try:
            if _span_ctx is not None:
                with _span_ctx:
                    response = agent.chat(query, fresh=True)
            else:
                response = agent.chat(query, fresh=True)
            return response
        except Exception as exc:
            return json.dumps({
                "error": f"Sub-agent '{agent_key}' failed: {exc}",
                "traceback": traceback.format_exc()[-400:],
            })

    def _stub_response(self, user_message: str) -> str:
        """Helpful stub when OPENAI_API_KEY is not configured."""
        msg = user_message.lower()
        if any(w in msg for w in ["morning", "brief", "risk"]):
            return (
                "Good morning. Portfolio snapshot (demo data):\n"
                "  OAS:  52.3 bps\n"
                "  OAD:  4.21 yr\n"
                "  Yield: 6.15%\n"
                "  EVE +200bp: -7.2%  [EXCEEDS -5.0% LIMIT]\n\n"
                "Set OPENAI_API_KEY in .env to enable the full multi-agent workflow."
            )
        elif any(w in msg for w in ["oas", "cheap", "screen"]):
            return (
                "I would screen for cheap pools using OAS > 55 bps, OAD 3.5–5.5 yr, FICO ≥ 700. "
                "Set OPENAI_API_KEY to run the live security-selection agent."
            )
        elif "eve" in msg:
            return (
                "At +200 bp, portfolio EVE changes by approximately -7.2% of book value, "
                "breaching the -5.0% limit. Set OPENAI_API_KEY for full EVE analysis."
            )
        else:
            available = ", ".join(list(QUICK_QUERIES.keys()))
            return (
                f"Oasia multi-agent workflow is ready.\n"
                f"Set OPENAI_API_KEY in .env to activate.\n\n"
                f"Available quick queries: {available}"
            )
