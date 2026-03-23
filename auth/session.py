"""
auth/session.py
In-memory session store.  Each session token maps to a username + expiry.
Tokens are cryptographically random and stored only server-side;
the client holds only the opaque token in an httponly cookie.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone

COOKIE_NAME     = "nexus_session"
SESSION_HOURS   = 8          # session lifetime

# {token: {"username": str, "expires": datetime}}
_store: dict[str, dict] = {}


def create(username: str) -> str:
    token = secrets.token_urlsafe(32)
    _store[token] = {
        "username": username,
        "expires":  datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS),
    }
    _purge_expired()
    return token


def get_username(token: str | None) -> str | None:
    if not token:
        return None
    entry = _store.get(token)
    if not entry:
        return None
    if datetime.now(timezone.utc) > entry["expires"]:
        _store.pop(token, None)
        return None
    return entry["username"]


def delete(token: str | None) -> None:
    if token:
        _store.pop(token, None)


def _purge_expired() -> None:
    now = datetime.now(timezone.utc)
    expired = [t for t, e in _store.items() if now > e["expires"]]
    for t in expired:
        del _store[t]
