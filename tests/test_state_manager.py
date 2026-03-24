"""
Tests for workflow/persistence/state_manager.py.

Verifies:
- Save/load roundtrip
- No _latest.json is written
- load_latest() returns the most-recently-modified session (by mtime)
- list_sessions() returns correct metadata
"""
import asyncio
import time
import pytest
from pathlib import Path

from workflow.persistence.state_manager import StateManager
from workflow.models.workflow_state import WorkflowPhase, RiskAppetite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine synchronously (compatible with pytest without asyncio plugin)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "states"


@pytest.fixture
def mgr(state_dir):
    return StateManager(state_dir=str(state_dir), username="testuser")


# ---------------------------------------------------------------------------
# Save / Load roundtrip
# ---------------------------------------------------------------------------

class TestSaveLoad:

    def test_save_creates_session_file(self, mgr, state_dir):
        state = mgr.new_state(trader_name="Alice")
        _run(mgr.save(state))
        expected = state_dir / "testuser" / f"{state.session_id}.json"
        assert expected.exists(), f"Session file not found: {expected}"

    def test_load_returns_same_state(self, mgr):
        state = mgr.new_state(trader_name="Bob")
        _run(mgr.save(state))
        loaded = _run(mgr.load(state.session_id))
        assert loaded is not None
        assert loaded.session_id == state.session_id
        assert loaded.trader_name == "Bob"

    def test_load_nonexistent_returns_none(self, mgr):
        result = _run(mgr.load("no-such-session-id"))
        assert result is None

    def test_save_sets_updated_at(self, mgr):
        """save() should write updated_at; just verify it is a non-empty string."""
        state = mgr.new_state()
        _run(mgr.save(state))
        loaded = _run(mgr.load(state.session_id))
        assert loaded.updated_at is not None
        assert len(loaded.updated_at) > 0

    def test_load_after_phase_change(self, mgr):
        state = mgr.new_state()
        state.phase = WorkflowPhase.NEW_VOLUME
        _run(mgr.save(state))
        loaded = _run(mgr.load(state.session_id))
        assert loaded.phase == WorkflowPhase.NEW_VOLUME


# ---------------------------------------------------------------------------
# No _latest.json
# ---------------------------------------------------------------------------

class TestNoLatestJson:

    def test_save_does_not_write_latest_json(self, mgr, state_dir):
        state = mgr.new_state()
        _run(mgr.save(state))
        latest_path = state_dir / "testuser" / "_latest.json"
        assert not latest_path.exists(), "_latest.json should not be written"

    def test_only_session_id_json_written(self, mgr, state_dir):
        state = mgr.new_state()
        _run(mgr.save(state))
        user_dir = state_dir / "testuser"
        all_json = list(user_dir.glob("*.json"))
        assert len(all_json) == 1
        assert all_json[0].name == f"{state.session_id}.json"

    def test_multiple_saves_no_latest_json(self, mgr, state_dir):
        for i in range(3):
            state = mgr.new_state(trader_name=f"Trader{i}")
            _run(mgr.save(state))
        user_dir = state_dir / "testuser"
        latest_path = user_dir / "_latest.json"
        assert not latest_path.exists()
        # Exactly 3 session files
        assert len(list(user_dir.glob("*.json"))) == 3


# ---------------------------------------------------------------------------
# load_latest uses mtime
# ---------------------------------------------------------------------------

class TestLoadLatest:

    def test_load_latest_returns_none_when_empty(self, mgr):
        result = _run(mgr.load_latest())
        assert result is None

    def test_load_latest_returns_only_session(self, mgr):
        state = mgr.new_state(trader_name="Solo")
        _run(mgr.save(state))
        loaded = _run(mgr.load_latest())
        assert loaded is not None
        assert loaded.session_id == state.session_id

    def test_load_latest_uses_mtime(self, mgr, state_dir):
        """load_latest should return the most recently modified session."""
        state_a = mgr.new_state(trader_name="First")
        _run(mgr.save(state_a))

        # Small sleep ensures mtime difference
        time.sleep(0.05)

        state_b = mgr.new_state(trader_name="Second")
        _run(mgr.save(state_b))

        latest = _run(mgr.load_latest())
        assert latest is not None
        assert latest.session_id == state_b.session_id, (
            "load_latest should return the most recently saved session"
        )

    def test_load_latest_after_re_save(self, mgr, state_dir):
        """Re-saving an older session makes it the latest."""
        state_a = mgr.new_state(trader_name="OldButResaved")
        state_b = mgr.new_state(trader_name="Newer")
        _run(mgr.save(state_a))
        time.sleep(0.05)
        _run(mgr.save(state_b))
        time.sleep(0.05)
        # Re-save state_a — it should now be "latest"
        state_a.phase = WorkflowPhase.RISK_ASSESSMENT
        _run(mgr.save(state_a))

        latest = _run(mgr.load_latest())
        assert latest.session_id == state_a.session_id


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

class TestListSessions:

    def test_list_sessions_empty(self, mgr):
        assert mgr.list_sessions() == []

    def test_list_sessions_returns_metadata(self, mgr):
        state = mgr.new_state(trader_name="Carol", risk_appetite=RiskAppetite.AGGRESSIVE)
        _run(mgr.save(state))
        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        entry = sessions[0]
        assert entry["session_id"] == state.session_id
        assert entry["trader_name"] == "Carol"

    def test_list_sessions_count(self, mgr):
        for i in range(4):
            state = mgr.new_state(trader_name=f"T{i}")
            _run(mgr.save(state))
        sessions = mgr.list_sessions()
        assert len(sessions) == 4

    def test_save_does_not_write_latest_json_globally(self, mgr, state_dir):
        """save() must never produce a _latest.json file."""
        for i in range(2):
            state = mgr.new_state(trader_name=f"T{i}")
            _run(mgr.save(state))
        user_dir = state_dir / "testuser"
        assert not (user_dir / "_latest.json").exists(), \
            "save() must not write _latest.json"
