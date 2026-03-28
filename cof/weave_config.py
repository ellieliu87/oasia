"""
Weave tracing and evaluation configuration — company SDK version.

Based on the company's Weave setup pattern. Key differences from root weave_config.py:
  - Uses WANDB_ENTITY_PROJECT (combined "entity/project") instead of separate
    WANDB_ENTITY + WANDB_PROJECT environment variables.
  - Supports W&B Inference endpoint as an alternative to direct OpenAI access,
    controlled by the INFERENCE_PROVIDER environment variable.
  - Returns "" / warns instead of raising when WANDB_API_KEY is absent, so the
    app can still start when only Arize Phoenix is configured.

Usage
-----
    from cof.weave_config import init_weave, weave_op, get_async_openai_client

    init_weave()                        # call once at app startup
    client = get_async_openai_client()  # returns the correct AsyncOpenAI client

    _op = weave_op()

    @_op
    async def chat(self, message: str) -> str:
        ...

Prefer importing from cof.tracing, which initialises BOTH Weave and Phoenix
in a single call and provides a combined tracing_op() decorator.

Environment variables
---------------------
    WANDB_API_KEY          — required
    WANDB_ENTITY_PROJECT   — required  (format: "entity/project",
                                        e.g. "acme-corp/nexus-mbs")
    INFERENCE_PROVIDER     — optional  ("openai" | "wandb"; default: "openai")
                                        "wandb"  → routes calls through the W&B
                                                   inference endpoint
                                        "openai" → calls OpenAI directly
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("nexus.weave")

_INITIALIZED: bool = False

# W&B Inference base URL (used when INFERENCE_PROVIDER=wandb)
_WANDB_INFERENCE_BASE_URL = "https://api.inference.wandb.ai/v1"


# ── Public API ────────────────────────────────────────────────────────────────

def init_weave() -> str:
    """
    Initialise Weave tracing and return the dashboard URL.

    * Calls weave.init(WANDB_ENTITY_PROJECT) using the company env-var pattern.
    * Automatically patches the OpenAI Python SDK so that every
      chat.completions.create() call is captured in Weave.
    * Safe to call multiple times — subsequent calls are no-ops.
    * Returns "" and logs a warning (instead of raising) when WANDB_API_KEY or
      WANDB_ENTITY_PROJECT are not set, so the app can start with Phoenix only.

    Returns
    -------
    str — clickable Weave dashboard URL, or "" if init was skipped.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return get_dashboard_url()

    api_key = os.getenv("WANDB_API_KEY", "")
    if not api_key:
        logger.warning(
            "WANDB_API_KEY is not set — Weave tracing will be inactive.\n"
            "  Add to .env:  WANDB_API_KEY=your_key_here\n"
            "  Get your key: https://wandb.ai/authorize"
        )
        return ""

    entity_project = os.getenv("WANDB_ENTITY_PROJECT", "")
    if not entity_project:
        logger.warning(
            "WANDB_ENTITY_PROJECT is not set — Weave tracing will be inactive.\n"
            "  Add to .env:  WANDB_ENTITY_PROJECT=your-entity/your-project\n"
            "  Example:      WANDB_ENTITY_PROJECT=acme-corp/nexus-mbs"
        )
        return ""

    try:
        import weave  # noqa: PLC0415
    except ImportError:
        logger.warning(
            "'weave' package is not installed — Weave tracing inactive.\n"
            "  Install with: pip install wandb weave"
        )
        return ""

    try:
        weave.init(entity_project)
    except Exception as exc:
        logger.warning("weave.init() failed: %s — Weave tracing inactive.", exc)
        return ""

    _INITIALIZED = True
    url = get_dashboard_url()
    logger.info("Weave initialised — dashboard: %s", url)
    return url


def get_dashboard_url() -> str:
    """Return the Weave dashboard URL for the current project."""
    entity_project = os.getenv("WANDB_ENTITY_PROJECT", "<your-entity>/<your-project>")
    return f"https://wandb.ai/{entity_project}/weave"


def weave_op():
    """
    Return the weave.op decorator if Weave is installed, otherwise a no-op.

    Instruments a function so that its inputs, outputs, and token costs are
    captured in Weave without hard-depending on the package being installed.

    Usage
    -----
        _op = weave_op()

        @_op
        async def chat(self, message: str) -> str:
            ...
    """
    try:
        import weave  # noqa: PLC0415
        return weave.op
    except ImportError:
        pass

    def _noop(fn=None, **_kwargs):
        return (lambda f: f) if fn is None else fn

    return _noop


def get_openai_client():
    """
    Return a synchronous OpenAI client configured for the active inference provider.

    INFERENCE_PROVIDER=openai (default)
        Standard OpenAI client — uses OPENAI_API_KEY.

    INFERENCE_PROVIDER=wandb
        W&B Inference client — routes calls through W&B's hosted endpoint,
        authenticated with WANDB_API_KEY and scoped to WANDB_ENTITY_PROJECT.
    """
    from openai import OpenAI  # noqa: PLC0415

    provider = os.getenv("INFERENCE_PROVIDER", "openai").lower()
    if provider == "wandb":
        return OpenAI(
            base_url=_WANDB_INFERENCE_BASE_URL,
            api_key=os.environ["WANDB_API_KEY"],
            project=os.getenv("WANDB_ENTITY_PROJECT", ""),
        )
    return OpenAI()


def get_async_openai_client():
    """
    Return an asynchronous OpenAI client configured for the active inference provider.

    Used by OpenAIChatCompletionsModel inside the company SDK agents.
    See get_openai_client() for provider details.
    """
    from openai import AsyncOpenAI  # noqa: PLC0415

    provider = os.getenv("INFERENCE_PROVIDER", "openai").lower()
    if provider == "wandb":
        return AsyncOpenAI(
            base_url=_WANDB_INFERENCE_BASE_URL,
            api_key=os.environ["WANDB_API_KEY"],
            project=os.getenv("WANDB_ENTITY_PROJECT", ""),
        )
    return AsyncOpenAI()
