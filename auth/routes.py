"""
auth/routes.py
FastAPI routes for login and logout.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth.ldap_auth import verify_credentials
from auth.session import create, delete, COOKIE_NAME, SESSION_HOURS
from auth.login_page import render_login_page

logger  = logging.getLogger("nexus.auth.routes")
router  = APIRouter()

_MAX_AGE = SESSION_HOURS * 3600


@router.get("/login", response_class=HTMLResponse)
async def login_get(error: str = ""):
    return render_login_page(error)


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if verify_credentials(username.strip(), password):
        token = create(username.strip())
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=_MAX_AGE,
        )
        logger.info("User '%s' signed in", username.strip())
        return response
    return RedirectResponse(
        url="/login?error=Invalid+credentials.+Please+try+again.",
        status_code=303,
    )


@router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    delete(token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
