"""
data/watchlist_store.py

Persistent watchlist storage — saved as JSON next to this module.
Each entry: {"cusip": str, "pool_id": str, "added_at": str, "notes": str}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("nexus.data.watchlist")


def _watchlist_path(username: str = "default") -> Path:
    d = Path(__file__).parent / "watchlists"
    d.mkdir(exist_ok=True)
    return d / f"{username}.json"


def load_watchlist(username: str = "default") -> list[dict]:
    """Return current watchlist entries for the given user (empty list if none saved)."""
    path = _watchlist_path(username)
    if not path.exists():
        return []
    try:
        with open(path, "r") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception as ex:
        logger.warning("load_watchlist failed: %s", ex)
        return []


def save_watchlist(items: list[dict], username: str = "default") -> None:
    """Persist watchlist to disk for the given user."""
    try:
        with open(_watchlist_path(username), "w") as fh:
            json.dump(items, fh, indent=2, default=str)
    except Exception as ex:
        logger.warning("save_watchlist failed: %s", ex)


def add_to_watchlist(cusip: str, pool_id: str = "", notes: str = "", username: str = "default") -> tuple[bool, str]:
    """
    Add entry. Returns (True, "Added") or (False, reason).
    """
    cusip = cusip.strip().upper()
    if not cusip:
        return False, "CUSIP is required"
    items = load_watchlist(username)
    if any(item.get("cusip") == cusip for item in items):
        return False, f"{cusip} is already in watchlist"
    items.append({
        "cusip":    cusip,
        "pool_id":  pool_id,
        "notes":    notes,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    save_watchlist(items, username)
    return True, f"Added {cusip}"


def remove_from_watchlist(cusip: str, username: str = "default") -> tuple[bool, str]:
    """Remove entry by CUSIP. Returns (True, msg) or (False, msg)."""
    cusip = cusip.strip().upper()
    items = load_watchlist(username)
    new_items = [i for i in items if i.get("cusip") != cusip]
    if len(new_items) == len(items):
        return False, f"{cusip} not found in watchlist"
    save_watchlist(new_items, username)
    return True, f"Removed {cusip}"


def is_in_watchlist(cusip: str, username: str = "default") -> bool:
    return any(i.get("cusip") == cusip.strip().upper() for i in load_watchlist(username))
