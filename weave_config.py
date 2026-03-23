"""
Weave tracing configuration for Oasia.

Usage
-----
    from weave_config import init_weave, get_dashboard_url

    url = init_weave()          # call once at app startup
    print("Weave dashboard:", url)

Environment variables
---------------------
    WANDB_API_KEY   — required  (your W&B API key)
    WANDB_ENTITY    — optional  (your W&B username or team; auto-detected if omitted)
    WANDB_PROJECT   — optional  (default: "nexus")
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("nexus.weave")

_PROJECT: str | None = None   # set after successful init
_ENTITY:  str | None = None


def init_weave(project: str | None = None) -> str:
    """
    Initialise Weave tracing and return the dashboard URL.

    * Automatically patches the OpenAI Python SDK so that every
      chat.completions.create() call is captured in Weave.
    * Safe to call multiple times — subsequent calls are no-ops.

    Parameters
    ----------
    project : str | None
        Weave project name.  Defaults to WANDB_PROJECT env-var or "nexus".

    Returns
    -------
    str — clickable Weave dashboard URL.

    Raises
    ------
    RuntimeError  if WANDB_API_KEY is not set.
    ImportError   if the `weave` package is not installed.
    """
    global _PROJECT, _ENTITY

    if _PROJECT is not None:          # already initialised
        return get_dashboard_url()

    api_key = os.getenv("WANDB_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "WANDB_API_KEY is not set.\n"
            "Add it to your .env file:\n"
            "    WANDB_API_KEY=your_key_here\n"
            "Get your key at: https://wandb.ai/authorize"
        )

    import weave  # noqa: PLC0415

    resolved_project = project or os.getenv("WANDB_PROJECT", "nexus")
    entity = os.getenv("WANDB_ENTITY", "")

    # weave.init() accepts "entity/project" or just "project"
    init_arg = f"{entity}/{resolved_project}" if entity else resolved_project
    weave.init(init_arg)

    _PROJECT = resolved_project
    _ENTITY  = entity or None

    url = get_dashboard_url()
    logger.info("Weave initialised — dashboard: %s", url)
    return url


def get_dashboard_url() -> str:
    """Return the Weave dashboard URL for the current project."""
    project = _PROJECT or os.getenv("WANDB_PROJECT", "nexus")
    entity  = _ENTITY  or os.getenv("WANDB_ENTITY", "")
    if entity:
        return f"https://wandb.ai/{entity}/projects/{project}/weave"
    return f"https://wandb.ai/<your-entity>/projects/{project}/weave"


def weave_op():
    """
    Return the weave.op decorator if Weave is installed, else a no-op.
    Used to conditionally instrument functions without hard-depending on Weave.
    """
    try:
        import weave  # noqa: PLC0415
        return weave.op
    except ImportError:
        def _noop(fn=None, **_kwargs):
            return (lambda f: f) if fn is None else fn
        return _noop
