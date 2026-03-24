"""
Run Weave evaluations for the Portfolio Planning workflow agents.

Each of the four planning phases is evaluated independently:
  new_volume        — monthly purchase-schedule builder
  risk_assessment   — duration / liquidity / concentration checker
  allocation        — product-mix scenario generator
  mbs_decomposition — MBS sub-bucket allocator

Usage
-----
    # Ensure .env has WANDB_API_KEY and OPENAI_API_KEY, then:
    python -m evals.run_workflow_evals

    # Filter to a single planning phase:
    python -m evals.run_workflow_evals --agent new_volume

    # Use a specific Weave project:
    python -m evals.run_workflow_evals --project nexus-planning-evals

After the run, open the printed Weave URL to view:
  - Per-question scores for each judge
  - Pass/fail breakdowns
  - Side-by-side response viewer
  - Trace waterfall: run_phase → Runner.run → OpenAI API
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# ── Bootstrap project path ────────────────────────────────────────────────────
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Portfolio Planning Weave evaluation")
    p.add_argument("--project", default=None,
                   help="Weave project name (default: WANDB_PROJECT env or 'nexus')")
    p.add_argument("--agent", default=None,
                   help="Filter to one agent_name (e.g. 'new_volume')")
    p.add_argument("--judge-model", default=None,
                   help="OpenAI model for LLM judges (default: WEAVE_JUDGE_MODEL env or gpt-4o)")
    return p.parse_args()


def _build_state(overrides: dict):
    """Construct a WorkflowState fixture from a dict of overrides."""
    from workflow.models.workflow_state import (
        WorkflowState,
        RiskConstraints,
        AllocationScenario,
        RiskAppetite,
    )
    import uuid

    # Unwrap nested dicts into typed sub-models
    if "risk_constraints" in overrides and isinstance(overrides["risk_constraints"], dict):
        overrides = dict(overrides)
        overrides["risk_constraints"] = RiskConstraints(**overrides["risk_constraints"])

    if "selected_scenario" in overrides and isinstance(overrides["selected_scenario"], dict):
        overrides = dict(overrides)
        overrides["selected_scenario"] = AllocationScenario(**overrides["selected_scenario"])

    return WorkflowState(
        session_id=str(uuid.uuid4()),
        risk_appetite=RiskAppetite.MODERATE,
        **overrides,
    )


async def main() -> None:
    args = _parse_args()

    # ── Init Weave ────────────────────────────────────────────────────────────
    from weave_config import init_weave, get_dashboard_url
    import weave

    try:
        url = init_weave(project=args.project)
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print(f"\n  Weave project   : {url}")
    print(  "  Starting planning-workflow evaluation...\n")

    if args.judge_model:
        os.environ["WEAVE_JUDGE_MODEL"] = args.judge_model

    # ── Load dataset ──────────────────────────────────────────────────────────
    from evals.dataset import PLANNING_EVAL_DATASET
    from evals.judges import (
        RelevanceScorer,
        FinancialAccuracyScorer,
        ActionabilityScorer,
        ToolCoverageScorer,
    )

    dataset = PLANNING_EVAL_DATASET
    if args.agent:
        dataset = [r for r in dataset if r.get("agent_name") == args.agent]
        if not dataset:
            print(f"[ERROR] No eval cases found for agent_name='{args.agent}'")
            sys.exit(1)
        print(f"  Filtered to {len(dataset)} cases for agent '{args.agent}'")

    # ── Load planning agents (mirrors ui/portfolio_planning.py setup) ─────────
    def _load_agents() -> dict:
        """
        Build the same agents dict that portfolio_planning.py uses.
        Uses workflow.skills.skill_loader.SkillLoader + Skill.build() which
        resolves each skill's markdown file and attached tools via ToolRegistry.
        Returns a mapping of agent_name -> agents.Agent (OpenAI Agents SDK).
        """
        from workflow.skills.skill_loader import SkillLoader

        _phase_skill_files = {
            "new_volume":        "new_volume_agent",
            "risk_assessment":   "risk_agent",
            "allocation":        "allocation_agent",
            "mbs_decomposition": "mbs_decomposition_agent",
        }

        agents_map: dict = {}
        for agent_name, skill_file in _phase_skill_files.items():
            try:
                skill = SkillLoader.load(skill_file)
                agents_map[agent_name] = skill.build()
            except (FileNotFoundError, Exception) as exc:
                print(f"  [WARN] Could not load skill '{skill_file}': {exc}")

        return agents_map

    agents_map = _load_agents()
    if not agents_map:
        print("[ERROR] No planning agents could be loaded. Check workflow/skills/ directory.")
        sys.exit(1)

    # ── Build the predict function ─────────────────────────────────────────────
    from workflow.weave_runner import run_phase

    @weave.op()
    async def predict(
        prompt: str,
        agent_name: str,
        state_overrides: dict | None = None,
        **kwargs,
    ) -> str:
        """
        The model under evaluation: one portfolio-planning agent phase.

        Mirrors the call pattern in ui/portfolio_planning.py:
            result = await run_phase(agent_name, agent, prompt, context=state)
        """
        agent = agents_map.get(agent_name)
        if agent is None:
            return f"[Agent '{agent_name}' not available]"

        state = _build_state(state_overrides or {})
        result = await run_phase(agent_name, agent, prompt, context=state)

        # RunResult.final_output is the agent's text response
        output = getattr(result, "final_output", None)
        if output is None:
            output = str(result)
        return output

    # ── Configure scorers ─────────────────────────────────────────────────────
    scorers = [
        RelevanceScorer(),
        FinancialAccuracyScorer(),
        ActionabilityScorer(),
        ToolCoverageScorer(),
    ]

    # ── Run evaluation ────────────────────────────────────────────────────────
    evaluation = weave.Evaluation(
        name="planning_workflow_eval",
        dataset=dataset,
        scorers=scorers,
    )

    print("  Running evaluation (calls each agent + 4 judges per question)…\n")
    results = await evaluation.evaluate(predict)

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Planning workflow evaluation complete")
    print("=" * 60)

    if isinstance(results, dict):
        for scorer_name, metrics in results.items():
            if isinstance(metrics, dict):
                avg = metrics.get("score", metrics.get("mean_score", "—"))
                pct = metrics.get("passed", "—")
                print(f"  {scorer_name:<30} score={avg}  passed={pct}")

    print(f"\n  Full results in Weave: {get_dashboard_url()}\n")


if __name__ == "__main__":
    asyncio.run(main())
