"""
Weave evaluation utilities — company SDK version.

Provides a weave.Model wrapper for the Oasia AgentOrchestrator and helpers for
running Weave evaluations against the existing eval datasets in evals/dataset.py.

Based on the company's Weave evaluation pattern:
  - weave.Model subclass with @weave.op on predict()
  - weave.Evaluation(name=..., dataset=..., scorers=[...])
  - await eval.evaluate(model)

Usage — quick eval run
----------------------
    import asyncio
    from cof.weave_evals import run_chat_eval

    asyncio.run(run_chat_eval())

Usage — custom scorers
----------------------
    import weave
    from cof.weave_evals import NexusAgentModel

    @weave.op
    def my_scorer(question: str, output: str, expected: str) -> dict:
        return {"correct": expected.lower() in output.lower()}

    model = NexusAgentModel()
    eval  = weave.Evaluation(
        name="my-eval",
        dataset=[{"question": "...", "expected": "..."}],
        scorers=[my_scorer],
    )
    import asyncio
    asyncio.run(eval.evaluate(model))

Environment variables (same as cof/weave_config.py)
-----------------------------------------------------
    WANDB_API_KEY, WANDB_ENTITY_PROJECT, INFERENCE_PROVIDER
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger("nexus.weave_evals")


# ── Nexus Agent Model ─────────────────────────────────────────────────────────

class NexusAgentModel:
    """
    weave.Model wrapper around AgentOrchestrator.chat().

    Instantiated lazily — the orchestrator is created on first predict() call
    so that Weave / Phoenix tracing is already active before agents are built.

    Parameters
    ----------
    model_name : str
        Human-readable label shown in the Weave eval UI.
        Defaults to the INFERENCE_PROVIDER + skill model read at runtime.
    """

    # Class-level model name shown in the Weave eval dashboard.
    # Overridden at __init__ time.
    model_name: str = "nexus-orchestrator"

    def __init__(self, model_name: str | None = None):
        import os  # noqa: PLC0415
        provider = os.getenv("INFERENCE_PROVIDER", "openai")
        self.model_name = model_name or f"nexus-orchestrator ({provider})"
        self._orchestrator = None

        # Apply weave.Model behaviour if weave is installed
        try:
            import weave  # noqa: PLC0415
            # Dynamically make this instance a weave.Model
            # (avoids hard inheritance which would break if weave is absent)
            self.__class__ = type(
                "NexusAgentModel",
                (weave.Model,),
                dict(self.__class__.__dict__),
            )
            weave.Model.__init__(self)
        except ImportError:
            pass

    def _get_orchestrator(self):
        if self._orchestrator is None:
            from cof.orchestrator import AgentOrchestrator  # noqa: PLC0415
            self._orchestrator = AgentOrchestrator()
        return self._orchestrator

    def predict(self, question: str) -> str:
        """
        Synchronous wrapper — runs orchestrator.chat() in an event loop.

        Weave's Evaluation.evaluate() calls predict() and expects either a
        sync return value or a coroutine. We expose the sync version here
        and call the async orchestrator internally.
        """
        return asyncio.run(self._get_orchestrator().chat(question))


# Apply @weave.op to predict at class definition time if weave is available.
try:
    import weave as _weave  # noqa: PLC0415
    NexusAgentModel.predict = _weave.op(NexusAgentModel.predict)
except (ImportError, Exception):
    pass


# ── Built-in Scorers ──────────────────────────────────────────────────────────

def _make_scorers():
    """
    Build and return the standard Nexus eval scorers.

    Each scorer is a @weave.op function (or plain function if weave is absent).
    Returns a list of callables compatible with weave.Evaluation(scorers=[...]).
    """
    try:
        import weave as _w  # noqa: PLC0415
        op = _w.op
    except ImportError:
        def op(fn):
            return fn

    @op
    def contains_expected(question: str, output: str, expected: str) -> dict[str, bool]:
        """Checks whether the expected answer fragment appears in the output."""
        return {"contains_expected": expected.lower().strip() in output.lower()}

    @op
    def not_empty(question: str, output: str) -> dict[str, bool]:
        """Checks that the agent returned a non-empty, non-error response."""
        is_ok = bool(output) and not output.strip().startswith("[Orchestrator error")
        return {"not_empty": is_ok}

    @op
    def no_tool_error(question: str, output: str) -> dict[str, bool]:
        """Checks that no tool execution error surfaces in the output."""
        has_error = '"error"' in output and '"traceback"' in output
        return {"no_tool_error": not has_error}

    return [contains_expected, not_empty, no_tool_error]


# ── Convenience Runners ───────────────────────────────────────────────────────

async def run_chat_eval(
    eval_name: str = "nexus-chat-eval",
    dataset: list[dict[str, Any]] | None = None,
    scorers: list | None = None,
) -> dict[str, Any]:
    """
    Run a Weave evaluation of the chat panel agents.

    Parameters
    ----------
    eval_name : str
        Name shown in the Weave eval UI.
    dataset : list[dict] | None
        List of {"question": "...", "expected": "..."} records.
        Defaults to EVAL_DATASET from evals/dataset.py.
    scorers : list | None
        Weave-compatible scorer callables.
        Defaults to the built-in nexus scorers (contains_expected, not_empty,
        no_tool_error).

    Returns
    -------
    dict — summary results returned by weave.Evaluation.evaluate().
    """
    try:
        import weave  # noqa: PLC0415
    except ImportError:
        logger.error(
            "'weave' package is not installed — cannot run Weave evaluations.\n"
            "  Install with: pip install wandb weave"
        )
        return {}

    # Load default dataset from evals/dataset.py
    if dataset is None:
        try:
            from evals.dataset import EVAL_DATASET  # noqa: PLC0415
            dataset = [
                {"question": item["input"], "expected": item.get("expected_contains", "")}
                for item in EVAL_DATASET
            ]
        except ImportError:
            logger.warning(
                "evals/dataset.py not found — using a minimal placeholder dataset."
            )
            dataset = [
                {"question": "What is my portfolio OAD?", "expected": "OAD"},
                {"question": "Show me cheap CC30 pools", "expected": "OAS"},
            ]

    if scorers is None:
        scorers = _make_scorers()

    model = NexusAgentModel()
    evaluation = weave.Evaluation(
        name=eval_name,
        dataset=weave.Dataset.from_pandas(_to_dataframe(dataset)),
        scorers=scorers,
    )

    logger.info("Running Weave evaluation '%s' on %d examples…", eval_name, len(dataset))
    results = await evaluation.evaluate(model)
    logger.info("Weave evaluation complete. Results: %s", results)
    return results


def _to_dataframe(records: list[dict]) -> Any:
    """Convert a list of dicts to a pandas DataFrame (required by weave.Dataset)."""
    try:
        import pandas as pd  # noqa: PLC0415
        return pd.DataFrame(records)
    except ImportError:
        # Return records as-is; weave.Dataset.from_pandas may accept a list too
        return records
