"""
workflow/weave_runner.py
-----------------------
Thin Weave-instrumented wrapper around the OpenAI Agents SDK Runner.

Each portfolio-planning phase is run through ``run_phase()``, which is
decorated with ``@weave.op`` so that every invocation — agent name,
prompt, final output, latency — is captured in the Weave trace tree and
appears alongside the NEXUS chat-panel traces in the same project.

Usage (in portfolio_planning.py)::

    from workflow.weave_runner import run_phase

    result = await run_phase("new_volume", agents["new_volume"], prompt, context=state)
"""
from __future__ import annotations

from weave_config import weave_op

_op = weave_op()


@_op
async def run_phase(agent_name: str, agent, prompt: str, context=None):
    """
    Run a single planning-workflow agent phase and return the RunResult.

    Parameters
    ----------
    agent_name : str
        Human-readable name logged in Weave (e.g. ``"new_volume"``).
    agent : agents.Agent
        The OpenAI Agents SDK Agent object to run.
    prompt : str
        The user/system message forwarded to the agent.
    context : WorkflowState | None
        Optional context object passed through to the agent's tools.

    Returns
    -------
    agents.RunResult
        The SDK run result; ``.final_output`` holds the agent's text response.
    """
    from agents import Runner
    return await Runner.run(agent, prompt, context=context)
