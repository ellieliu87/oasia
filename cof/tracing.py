"""
Unified tracing initialisation — Arize Phoenix + W&B Weave.

This is the single entry point for all observability setup in the company
environment. It initialises both tracing backends and provides a combined
decorator that layers Weave's input/output capture on top of a Phoenix span.

Usage (in app.py)
-----------------
    from cof.tracing import init_tracing

    init_tracing()   # call once, before any LLM calls

Usage (in agent files)
----------------------
    from cof.tracing import tracing_op

    _op = tracing_op()

    @_op
    async def chat(self, message: str) -> str:
        ...

How the two backends divide responsibilities
--------------------------------------------
    Arize Phoenix (via auto_instrumentation):
        - Automatically traces every OpenAI SDK call (model, latency, tokens).
        - Provides the Phoenix / OTEL span hierarchy for request waterfall views.

    W&B Weave (via @weave.op):
        - Captures the *business-level* function inputs and outputs
          (e.g., the full user question and the final agent answer).
        - Powers Weave Evaluations — the dataset + scorer framework.
        - Shows token costs per call in the Weave dashboard.

    Together they give a full picture:
        Phoenix  →  low-level API call timing and span waterfall
        Weave    →  high-level function I/O, cost tracking, and evals

Environment variables
---------------------
    See cof/weave_config.py   (WANDB_API_KEY, WANDB_ENTITY_PROJECT, INFERENCE_PROVIDER)
    See cof/phoenix_config.py (PHOENIX_ENDPOINT, ENVIRONMENT)
"""
from __future__ import annotations

import logging

logger = logging.getLogger("nexus.tracing")


# ── Initialisation ────────────────────────────────────────────────────────────

def init_tracing() -> dict[str, str]:
    """
    Initialise both Arize Phoenix and W&B Weave.

    Safe to call multiple times — both backends are no-ops on repeated calls.
    Either backend failing to init does not prevent the other from starting.

    Returns
    -------
    dict with keys "weave_url" and "phoenix_endpoint" for logging / display.
    """
    result: dict[str, str] = {}

    # ── W&B Weave ────────────────────────────────────────────────────────────
    try:
        from cof.weave_config import init_weave  # noqa: PLC0415
        weave_url = init_weave()
        result["weave_url"] = weave_url or "(not configured)"
    except Exception as exc:
        logger.warning("Weave init raised an unexpected error: %s", exc)
        result["weave_url"] = "(error)"

    # ── Arize Phoenix ─────────────────────────────────────────────────────────
    try:
        from cof.phoenix_config import init_phoenix  # noqa: PLC0415
        init_phoenix()
        import os  # noqa: PLC0415
        result["phoenix_endpoint"] = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")
    except Exception as exc:
        logger.warning("Phoenix init raised an unexpected error: %s", exc)
        result["phoenix_endpoint"] = "(error)"

    if result.get("weave_url") and result["weave_url"] != "(not configured)":
        logger.info("Weave dashboard:    %s", result["weave_url"])
    logger.info("Phoenix endpoint:   %s", result.get("phoenix_endpoint"))

    return result


# ── Combined Decorator ────────────────────────────────────────────────────────

def tracing_op():
    """
    Return a combined decorator that applies both Weave and Phoenix tracing.

    Stacking order (outer → inner):
        Phoenix span  →  weave.op  →  original function

    This means:
      - Phoenix opens a span around the entire call (visible in OTEL waterfall).
      - Weave captures the function's inputs and outputs (visible in Weave UI).
      - Both see the same latency for the decorated function.

    Gracefully degrades:
      - If only Weave is available  → applies weave.op only.
      - If only Phoenix is available → applies Phoenix span only.
      - If neither is available     → returns the function unchanged (no-op).

    Usage
    -----
        _op = tracing_op()

        @_op
        async def chat(self, message: str) -> str:
            ...
    """
    from cof.weave_config import weave_op      # noqa: PLC0415
    from cof.phoenix_config import phoenix_op  # noqa: PLC0415

    _weave   = weave_op()
    _phoenix = phoenix_op()

    def _combined(fn):
        # Inner layer: Weave captures inputs/outputs of the original function.
        weave_wrapped = _weave(fn)
        # Outer layer: Phoenix span wraps the Weave-instrumented call.
        return _phoenix(weave_wrapped)

    return _combined
