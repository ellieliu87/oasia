"""
Arize Phoenix observability configuration — company SDK version.

Replaces weave_config.py when running in the company environment.

Initializes two company packages at startup:
  1. c1.genai.telemetry.web_server      — starts the Phoenix collector/UI server
  2. c1.aiml.observability.instrumentation.auto_instrumentation
                                        — auto-instruments the OpenAI SDK (and
                                          any other frameworks listed in the YAML)

Usage
-----
    # In app.py, call once at startup (before any LLM calls):
    from cof.phoenix_config import init_phoenix
    init_phoenix()

    # In agent files, use the decorator for manual span tracking:
    from cof.phoenix_config import phoenix_op
    _op = phoenix_op()

    @_op
    async def chat(self, user_message: str) -> str:
        ...

Config file
-----------
    cof/observability-config.yaml   (passed to auto_instrumentation.initialize)

Required packages (install via pip)
------------------------------------
    pip install c1-aiml-observability-instrumentation
    pip install c1-genai-telemetry
    pip install c1-arize-phoenix

Environment variables
---------------------
    PHOENIX_ENDPOINT   — Phoenix collector URL (default: http://localhost:6006)
    ENVIRONMENT        — deployment environment label, e.g. "production" (default: "development")
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import os
from pathlib import Path

logger = logging.getLogger("nexus.phoenix")

_INITIALIZED: bool = False

# Default config path: same directory as this file
_DEFAULT_CONFIG = Path(__file__).parent / "observability-config.yaml"


# ── Public API ────────────────────────────────────────────────────────────────

def init_phoenix(config_path: str | Path | None = None) -> None:
    """
    Start the company Phoenix web server and initialize auto-instrumentation.

    Safe to call multiple times — subsequent calls are no-ops.

    Parameters
    ----------
    config_path : str | Path | None
        Path to the observability YAML config file.
        Defaults to ``cof/observability-config.yaml``.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    resolved = str(Path(config_path) if config_path else _DEFAULT_CONFIG)

    # Step 1 — start the Phoenix collector / web UI
    try:
        from c1.genai.telemetry import web_server  # noqa: PLC0415
        web_server.start()
        logger.info("Phoenix web server started.")
    except ImportError:
        logger.warning(
            "c1-genai-telemetry is not installed — Phoenix web server not started.\n"
            "  Install with: pip install c1-genai-telemetry"
        )
    except Exception as exc:
        logger.warning("Phoenix web server failed to start: %s", exc)

    # Step 2 — auto-instrument the OpenAI SDK (and others defined in the YAML)
    try:
        from c1.aiml.observability.instrumentation import auto_instrumentation  # noqa: PLC0415
        auto_instrumentation.initialize(resolved)
        logger.info("Auto-instrumentation initialized from: %s", resolved)
    except ImportError:
        logger.warning(
            "c1-aiml-observability-instrumentation is not installed — "
            "auto-instrumentation not active.\n"
            "  Install with: pip install c1-aiml-observability-instrumentation"
        )
    except Exception as exc:
        logger.warning("Auto-instrumentation failed to initialize: %s", exc)

    _INITIALIZED = True


def phoenix_op():
    """
    Return a function/method decorator that wraps calls in an Arize Phoenix span.

    Tries three options in order:
      1. ``c1.arize.phoenix.span``          — company Phoenix decorator
      2. ``opentelemetry.trace``            — raw OTEL span (fallback if OTEL
                                             is present but c1 package is not)
      3. No-op decorator                   — if neither is available

    The returned decorator handles both sync and async functions.

    Usage
    -----
        _op = phoenix_op()

        @_op
        async def chat(self, message: str) -> str:
            ...
    """
    # Option 1: company Phoenix span decorator
    try:
        from c1.arize.phoenix import span  # noqa: PLC0415
        return span
    except ImportError:
        pass

    # Option 2: raw OpenTelemetry tracer span
    try:
        from opentelemetry import trace  # noqa: PLC0415
        _tracer = trace.get_tracer("nexus")

        def _otel_decorator(fn=None, *, name: str | None = None):
            """Wraps fn in an OTEL span. Can be used as @_op or @_op(name="...")."""
            def _wrap(f):
                span_name = name or f.__qualname__
                if asyncio.iscoroutinefunction(f) or inspect.iscoroutinefunction(f):
                    @functools.wraps(f)
                    async def _async(*args, **kwargs):
                        with _tracer.start_as_current_span(span_name):
                            return await f(*args, **kwargs)
                    return _async
                else:
                    @functools.wraps(f)
                    def _sync(*args, **kwargs):
                        with _tracer.start_as_current_span(span_name):
                            return f(*args, **kwargs)
                    return _sync

            # Called as @_op (fn is passed directly)
            if fn is not None:
                return _wrap(fn)
            # Called as @_op(name="...") (returns a decorator)
            return _wrap

        return _otel_decorator
    except ImportError:
        pass

    # Option 3: no-op — tracing silently disabled
    logger.debug(
        "Neither c1-arize-phoenix nor opentelemetry is installed. "
        "Manual span decoration is a no-op."
    )

    def _noop(fn=None, **_kwargs):
        return (lambda f: f) if fn is None else fn

    return _noop
