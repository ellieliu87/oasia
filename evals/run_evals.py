"""
Run the Oasia LLM-as-judge evaluation suite via Weave.

Usage
-----
    # Ensure .env has WANDB_API_KEY and OPENAI_API_KEY, then:
    python -m evals.run_evals

    # Run a subset by agent type:
    python -m evals.run_evals --agent portfolio_analytics

    # Use a specific Weave project:
    python -m evals.run_evals --project nexus-evals

After the run completes, open the printed Weave URL to view:
  - Per-question scores for each judge
  - Pass/fail breakdowns
  - Side-by-side response viewer
  - Trace waterfall: orchestrator → sub-agent → tool calls → OpenAI API
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# ── Bootstrap project path ────────────────────────────────────────────────────
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Oasia Weave evaluation")
    p.add_argument("--project", default=None,
                   help="Weave project name (default: WANDB_PROJECT env or 'nexus')")
    p.add_argument("--agent", default=None,
                   help="Filter to a specific agent_type (e.g. 'portfolio_analytics')")
    p.add_argument("--model", default="gpt-4o",
                   help="OpenAI model for the agent under test (default: gpt-4o)")
    p.add_argument("--judge-model", default=None,
                   help="OpenAI model for the LLM judges (default: WEAVE_JUDGE_MODEL env or gpt-4o)")
    return p.parse_args()


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
    print(  "  Starting evaluation...\n")

    # ── Override judge model if requested ─────────────────────────────────────
    if args.judge_model:
        os.environ["WEAVE_JUDGE_MODEL"] = args.judge_model

    # ── Load dataset ──────────────────────────────────────────────────────────
    from evals.dataset import EVAL_DATASET
    from evals.judges import (
        RelevanceScorer,
        FinancialAccuracyScorer,
        ActionabilityScorer,
        ToolCoverageScorer,
    )

    dataset = EVAL_DATASET
    if args.agent:
        dataset = [r for r in dataset if r.get("agent_type") == args.agent]
        if not dataset:
            print(f"[ERROR] No eval cases found for agent_type='{args.agent}'")
            sys.exit(1)
        print(f"  Filtered to {len(dataset)} cases for agent '{args.agent}'")

    # ── Build the model function (the agent under test) ───────────────────────
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator()

    @weave.op()
    def predict(question: str, **kwargs) -> str:
        """The model under evaluation: Oasia multi-agent orchestrator."""
        return orchestrator.chat(question)

    # ── Configure scorers ─────────────────────────────────────────────────────
    scorers = [
        RelevanceScorer(),
        FinancialAccuracyScorer(),
        ActionabilityScorer(),
        ToolCoverageScorer(),
    ]

    # ── Run evaluation ────────────────────────────────────────────────────────
    evaluation = weave.Evaluation(
        name="nexus_agent_eval",
        dataset=dataset,
        scorers=scorers,
    )

    print("  Running evaluation (this calls the agent + 4 judges per question)…\n")
    results = await evaluation.evaluate(predict)

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Evaluation complete")
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
