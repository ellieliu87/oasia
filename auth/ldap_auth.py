"""
auth/ldap_auth.py
Authenticate users against a corporate LDAP / Active Directory server.

Mock mode
─────────
Set LDAP_SERVER=mock:// in .env to bypass real LDAP during local development.
In mock mode any username is accepted; the password must match LDAP_MOCK_PASSWORD
(default: "nexus-dev").  Never use mock:// in production.
"""
from __future__ import annotations
import logging
import os
from config import Config

logger = logging.getLogger("nexus.auth.ldap")

_MOCK_SCHEME = "mock://"


def _mock_verify(username: str, password: str) -> bool:
    """Accept any non-empty username with the configured mock password."""
    expected = os.getenv("LDAP_MOCK_PASSWORD", "nexus-dev")
    ok = bool(username) and password == expected
    logger.info(
        "MOCK auth %s for user '%s' (set LDAP_SERVER to a real server for production)",
        "SUCCESS" if ok else "FAILED",
        username,
    )
    return ok


def verify_credentials(username: str, password: str) -> bool:
    """
    Attempt an LDAP bind with the supplied credentials.
    Returns True if bind succeeds, False otherwise.
    Never raises — all exceptions are logged and treated as auth failure.

    If LDAP_SERVER starts with 'mock://' the built-in mock authenticator is
    used instead of a real LDAP server (development / CI use only).
    """
    if not username or not password:
        return False

    if Config.LDAP_SERVER.startswith(_MOCK_SCHEME):
        return _mock_verify(username, password)

    try:
        import ldap3
        server = ldap3.Server(
            Config.LDAP_SERVER,
            use_ssl=Config.LDAP_USE_SSL,
            connect_timeout=5,
        )
        user_dn = Config.LDAP_USER_DN_TEMPLATE.format(username=username)
        conn = ldap3.Connection(
            server,
            user=user_dn,
            password=password,
            auto_bind=True,
            receive_timeout=5,
        )
        bound = conn.bound
        conn.unbind()
        logger.info("LDAP auth %s for user '%s'", "SUCCESS" if bound else "FAILED", username)
        return bound
    except Exception as exc:
        logger.warning("LDAP auth error for user '%s': %s", username, exc)
        return False
