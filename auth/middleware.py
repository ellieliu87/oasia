"""
auth/middleware.py
Starlette middleware that enforces authentication on every request.
Unauthenticated requests are redirected to /login.
"""
from __future__ import annotations
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
from auth.session import get_username, COOKIE_NAME

# Paths that do NOT require a valid session
_PUBLIC = frozenset({"/login", "/logout", "/favicon.ico"})


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow public paths and static assets
        if path in _PUBLIC or path.startswith((
            "/static", "/_", "/assets", "/svelte",
            "/gradio_api/",
            "/queue", "/run", "/info", "/heartbeat", "/stream",
            "/config", "/monitoring",
        )) or path in {"/theme.css", "/robots.txt", "/manifest.json"}:
            return await call_next(request)

        token    = request.cookies.get(COOKIE_NAME)
        username = get_username(token)

        if not username:
            # Preserve the original destination so we can redirect back after login
            return RedirectResponse(url="/login", status_code=302)

        # Make username available to downstream handlers
        request.state.username = username
        return await call_next(request)
