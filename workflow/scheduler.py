"""
PortfolioScheduler — wraps APScheduler for periodic workflow execution.

Usage
-----
    from workflow.scheduler import get_scheduler

    sched = get_scheduler()
    sched.start()                                    # call once at app startup
    sched.configure("daily", hour=6)                 # save + activate schedule
    sched.run_now()                                  # trigger immediately
    status = sched.get_status()                      # dict for UI rendering

Config is persisted to data/schedule_config.json so it survives restarts.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nexus.workflow.scheduler")

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "schedule_config.json"

_DEFAULTS: dict = {
    "enabled":      False,
    "frequency":    "daily",     # daily | weekly | monthly
    "hour":         6,           # 0–23 UTC
    "day_of_week":  0,           # 0=Mon … 6=Sun  (weekly only)
    "day_of_month": 1,           # 1–28            (monthly only)
}

_DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class PortfolioScheduler:
    """
    Manages a BackgroundScheduler that periodically runs the analytics pipeline.
    All public methods are thread-safe.
    """

    def __init__(self) -> None:
        self._lock        = threading.RLock()
        self._status      = "idle"            # idle | running | success | partial | failed
        self._last_result = None              # WorkflowResult | None
        self._scheduler   = None             # APScheduler BackgroundScheduler | None
        self._config: dict = dict(_DEFAULTS)
        self._progress: dict = {"done": 0, "total": 0, "pct": 0.0, "message": ""}
        self._load_config()

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background scheduler (call once at app startup)."""
        if self._config.get("enabled"):
            self._restart_scheduler()

    def shutdown(self) -> None:
        """Graceful shutdown — call when app exits."""
        with self._lock:
            if self._scheduler and self._scheduler.running:
                self._scheduler.shutdown(wait=False)

    def configure(
        self,
        frequency: str,
        hour: int,
        day_of_week: int = 0,
        day_of_month: int = 1,
    ) -> None:
        """Persist schedule config and (re)start the APScheduler job."""
        with self._lock:
            self._config = {
                "enabled":      True,
                "frequency":    frequency.lower(),
                "hour":         max(0, min(23, int(hour))),
                "day_of_week":  max(0, min(6, int(day_of_week))),
                "day_of_month": max(1, min(28, int(day_of_month))),
            }
            self._save_config()
        self._restart_scheduler()
        logger.info(
            "Schedule configured: %s at %02d:00", frequency, hour
        )

    def run_now(self) -> None:
        """Trigger an immediate pipeline run in a daemon background thread."""
        t = threading.Thread(target=self._execute, daemon=True, name="workflow-run-now")
        t.start()

    def get_status(self) -> dict:
        """Return a serialisable status dict for the UI."""
        with self._lock:
            out: dict = {
                "status":      self._status,
                "config":      dict(self._config),
                "last_result": None,
                "next_run":    self._next_run_str(),
                "progress":    dict(self._progress),
            }
            if self._last_result is not None:
                r = self._last_result
                out["last_result"] = {
                    "started_at":       r.started_at.strftime("%Y-%m-%d %H:%M"),
                    "finished_at":      r.finished_at.strftime("%Y-%m-%d %H:%M"),
                    "status":           r.status,
                    "pools_processed":  r.pools_processed,
                    "pools_failed":     r.pools_failed,
                    "duration_secs":    round(r.duration_secs),
                    "error":            r.error,
                }
            return out

    # ── Internals ────────────────────────────────────────────────────────────

    def _restart_scheduler(self) -> None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            logger.error(
                "apscheduler not installed — run `uv add apscheduler` to enable scheduling"
            )
            return

        with self._lock:
            if self._scheduler and self._scheduler.running:
                self._scheduler.shutdown(wait=False)

            freq = self._config.get("frequency", "daily")
            hour = self._config.get("hour", 6)
            dow  = self._config.get("day_of_week", 0)
            dom  = self._config.get("day_of_month", 1)

            if freq == "weekly":
                trigger = CronTrigger(day_of_week=dow, hour=hour, minute=0)
            elif freq == "monthly":
                trigger = CronTrigger(day=dom, hour=hour, minute=0)
            else:  # daily
                trigger = CronTrigger(hour=hour, minute=0)

            self._scheduler = BackgroundScheduler(timezone="UTC")
            self._scheduler.add_job(
                self._execute, trigger, id="workflow", replace_existing=True
            )
            self._scheduler.start()
            logger.info("Scheduler active: %s at %02d:00 UTC", freq, hour)

    def _update_progress(self, done: int, total: int, message: str) -> None:
        pct = round(100.0 * done / total, 1) if total > 0 else 0.0
        with self._lock:
            self._progress = {"done": done, "total": total, "pct": pct, "message": message}

    def _execute(self) -> None:
        """Run the pipeline; called by APScheduler or run_now()."""
        with self._lock:
            if self._status == "running":
                logger.warning("Workflow already running — skipping trigger")
                return
            self._status   = "running"
            self._progress = {"done": 0, "total": 0, "pct": 0.0, "message": "Starting…"}

        logger.info("Workflow pipeline started")
        try:
            from workflow.runner import WorkflowRunner
            result = WorkflowRunner(progress_cb=self._update_progress).run()
        except Exception as ex:
            from workflow.runner import WorkflowResult
            result = WorkflowResult(
                started_at  = datetime.now(),
                finished_at = datetime.now(),
                status      = "failed",
                error       = str(ex),
            )
            logger.error("Workflow raised: %s", ex, exc_info=True)

        with self._lock:
            self._last_result = result
            self._status      = result.status

        logger.info(
            "Workflow finished: %s  pools=%d  failed=%d  duration=%.0fs",
            result.status, result.pools_processed, result.pools_failed, result.duration_secs,
        )

    def _next_run_str(self) -> str:
        try:
            if self._scheduler and self._scheduler.running:
                job = self._scheduler.get_job("workflow")
                if job and job.next_run_time:
                    return job.next_run_time.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pass
        return ""

    # ── Config persistence ───────────────────────────────────────────────────

    def _load_config(self) -> None:
        try:
            if _CONFIG_PATH.exists():
                saved = json.loads(_CONFIG_PATH.read_text())
                self._config = {**_DEFAULTS, **saved}
        except Exception as ex:
            logger.warning("Could not load schedule config: %s", ex)

    def _save_config(self) -> None:
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CONFIG_PATH.write_text(json.dumps(self._config, indent=2))
        except Exception as ex:
            logger.warning("Could not save schedule config: %s", ex)


# ── Module-level singleton ───────────────────────────────────────────────────

_instance: Optional[PortfolioScheduler] = None


def get_scheduler() -> PortfolioScheduler:
    """Return the process-wide scheduler singleton."""
    global _instance
    if _instance is None:
        _instance = PortfolioScheduler()
    return _instance
