"""
Async JSON persistence for WorkflowState.

Each session gets its own file: <state_dir>/<session_id>.json
A latest-session symlink / copy is maintained for convenience.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles

from workflow.models.workflow_state import WorkflowState, WorkflowPhase, RiskAppetite

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = os.getenv("WORKFLOW_STATE_DIR", "./workflow_states")


class StateManager:
    def __init__(self, state_dir: str = DEFAULT_STATE_DIR, username: str = "default"):
        self.state_dir = Path(state_dir) / username
        self.state_dir.mkdir(parents=True, exist_ok=True)

    # ── Path helpers ─────────────────────────────────────────────────────────

    def _path(self, session_id: str) -> Path:
        return self.state_dir / f"{session_id}.json"

    def _latest_path(self) -> Path:
        return self.state_dir / "_latest.json"

    # ── Save ─────────────────────────────────────────────────────────────────

    async def save(self, state: WorkflowState) -> None:
        state.updated_at = datetime.utcnow().isoformat()
        data = state.model_dump_json(indent=2)

        session_path = self._path(state.session_id)
        async with aiofiles.open(session_path, "w", encoding="utf-8") as f:
            await f.write(data)

        # Also write a "latest" pointer for easy resume
        async with aiofiles.open(self._latest_path(), "w", encoding="utf-8") as f:
            await f.write(data)

        logger.debug("State saved → %s (phase=%s)", session_path.name, state.phase)

    # ── Load ─────────────────────────────────────────────────────────────────

    async def load(self, session_id: str) -> Optional[WorkflowState]:
        path = self._path(session_id)
        if not path.exists():
            return None
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        return WorkflowState.model_validate_json(raw)

    async def load_latest(self) -> Optional[WorkflowState]:
        path = self._latest_path()
        if not path.exists():
            return None
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        return WorkflowState.model_validate_json(raw)

    # ── Create new session ───────────────────────────────────────────────────

    def new_state(
        self,
        trader_name: str = "Trader",
        risk_appetite: RiskAppetite = RiskAppetite.MODERATE,
    ) -> WorkflowState:
        session_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        return WorkflowState(
            session_id=session_id,
            trader_name=trader_name,
            risk_appetite=risk_appetite,
            phase=WorkflowPhase.INIT,
        )

    # ── List sessions ────────────────────────────────────────────────────────

    def list_sessions(self) -> list[dict]:
        results = []
        for p in sorted(self.state_dir.glob("*.json")):
            if p.name.startswith("_"):
                continue
            try:
                with open(p) as f:
                    raw = json.load(f)
                results.append({
                    "session_id": raw.get("session_id"),
                    "phase": raw.get("phase"),
                    "trader_name": raw.get("trader_name"),
                    "updated_at": raw.get("updated_at"),
                    "file": p.name,
                })
            except Exception:
                pass
        return results
