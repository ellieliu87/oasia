"""
Oasia — Agency MBS Trading Desk Analytics Platform

Launch:
    python app.py

Environment:
    Copy .env.example to .env and fill in your API keys before launching.
    The app runs without API keys (using mock data and stub models).
"""
from __future__ import annotations

import sys
import os
import asyncio
import logging
from pathlib import Path

# Ensure the repo root is always on sys.path so that `data.*`, `db.*`, etc.
# resolve correctly regardless of which directory the app is launched from.
_REPO_ROOT = str(Path(__file__).resolve().parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Windows asyncio: switch to SelectorEventLoop to avoid the ProactorEventLoop
# bug where browser disconnects log spurious ConnectionResetError tracebacks.
# Must be set before uvicorn creates its event loop.
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ---------------------------------------------------------------------------
# Configure logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nexus")


def _check_dependencies() -> None:
    """Check that required packages are installed."""
    missing = []
    required = [
        "gradio", "openai", "numpy", "scipy", "pandas",
        "requests", "dotenv", "diskcache", "plotly", "dateutil",
    ]
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        logger.error(
            "Missing dependencies: %s\n"
            "Run: pip install -r requirements.txt",
            ", ".join(missing),
        )
        sys.exit(1)


def _init_directories() -> None:
    """Create required data directories."""
    try:
        from config import Config
        Config.ensure_dirs()
        logger.info("Data directories initialized: %s", Config.MARKET_DATA_DIR)
    except Exception as e:
        logger.warning("Could not initialize directories: %s", e)


def _init_weave() -> str | None:
    """Initialise Weave tracing; return dashboard URL or None if not configured."""
    try:
        from weave_config import init_weave
        url = init_weave()
        return url
    except RuntimeError as e:
        logger.info("Weave tracing disabled: %s", e)
        return None
    except ImportError:
        logger.info("Weave tracing disabled: package not installed")
        return None
    except Exception as e:
        logger.warning("Weave init failed: %s", e)
        return None


def _print_banner() -> None:
    """Print startup banner."""
    try:
        from config import Config
        has_openai = Config.has_openai_key()
        has_intex = Config.has_intex_key()
        port = Config.GRADIO_PORT
    except Exception:
        has_openai = False
        has_intex = False
        port = 7860

    banner = f"""
+--------------------------------------------------------------+
|          Oasia -- Fixed Income Portfolio Copilot             |
+--------------------------------------------------------------+
|  Status:                                                     |
|    OpenAI API : {"OK - Configured" if has_openai else "Not set (using stub responses)  "}          |
|    Intex API  : {"OK - Configured" if has_intex else "Not set (using mock client)      "}          |
|    Port       : {port:<46}|
+--------------------------------------------------------------+
|  Workflows:                                                  |
|    1. Security Selection -- screen universe for value        |
|    2. What-If Sandbox    -- modify & reprice pools           |
|    3. Portfolio Analytics -- KPIs, EVE, book yield           |
|    4. Attribution        -- OAS/OAD/yield/EVE drivers        |
+--------------------------------------------------------------+
"""
    print(banner)

    if not has_openai:
        print("  NOTE: Set OPENAI_API_KEY in .env to enable AI agent capabilities.\n")


def _init_scheduler() -> None:
    """Start the workflow scheduler (loads saved config, activates cron if enabled)."""
    try:
        from workflow.scheduler import get_scheduler
        sched = get_scheduler()
        sched.start()
        cfg = sched._config
        if cfg.get("enabled"):
            logger.info(
                "Workflow scheduler active: %s at %02d:00 UTC",
                cfg.get("frequency", "daily"),
                cfg.get("hour", 6),
            )
        else:
            logger.info("Workflow scheduler loaded (no active schedule)")
    except ImportError:
        logger.info("apscheduler not installed — workflow scheduling disabled")
    except Exception as ex:
        logger.warning("Could not start workflow scheduler: %s", ex)


def main() -> None:
    """Main entry point."""
    _check_dependencies()
    _init_directories()
    _print_banner()
    weave_url = _init_weave()
    if weave_url:
        logger.info("Weave dashboard: %s", weave_url)
        print(f"\n  Weave dashboard : {weave_url}\n")

    try:
        import gradio as gr
        import uvicorn
        from fastapi import FastAPI
        from ui.layout import create_layout, _INIT_JS
        from ui.theme import CUSTOM_CSS, get_theme
        from config import Config
        from auth.middleware import AuthMiddleware
        from auth.routes import router as auth_router
    except ImportError as e:
        logger.error("Failed to import modules: %s", e)
        sys.exit(1)

    _init_scheduler()

    logger.info("Building Gradio layout...")
    demo = create_layout()

    logger.info("Building FastAPI app with auth middleware...")
    fastapi_app = FastAPI(title="Oasia")
    fastapi_app.add_middleware(AuthMiddleware)
    fastapi_app.include_router(auth_router)

    logger.info("Mounting Gradio on FastAPI...")
    gr.mount_gradio_app(
        fastapi_app, demo, path="/",
        theme=get_theme(),
        css=CUSTOM_CSS,
        js=_INIT_JS,
    )

    logger.info("Launching Oasia on port %d...", Config.GRADIO_PORT)

    async def _serve() -> None:
        config = uvicorn.Config(
            fastapi_app,
            host="0.0.0.0",
            port=Config.GRADIO_PORT,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        await server.serve()

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        logger.info("Oasia stopped.")


if __name__ == "__main__":
    main()
