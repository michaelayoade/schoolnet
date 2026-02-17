"""Web authentication routes — login and logout pages."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.branding_context import load_branding_context
from app.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["web-auth"])


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next: str = "/admin",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    branding = load_branding_context(db)
    return templates.TemplateResponse(
        "admin/login.html",
        {
            "request": request,
            "title": "Login",
            "next_url": next,
            "brand": branding["brand"],
            "org_branding": branding["org_branding"],
        },
    )


def _login_error(
    request: Request, db: Session, message: str, next_url: str
) -> HTMLResponse:
    branding = load_branding_context(db)
    return templates.TemplateResponse(
        "admin/login.html",
        {
            "request": request,
            "title": "Login",
            "error": message,
            "next_url": next_url,
            "brand": branding["brand"],
            "org_branding": branding["org_branding"],
        },
    )


@router.post("/login", response_model=None)
async def login_submit(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    next_url = str(form.get("next", "/admin"))

    if not username or not password:
        return _login_error(request, db, "Username and password are required", next_url)

    from app.services.auth_flow import AuthFlow

    try:
        result = AuthFlow.login(db, username, password, request, None)
    except HTTPException:
        return _login_error(request, db, "Invalid username or password", next_url)

    if result.get("mfa_required"):
        return templates.TemplateResponse(
            "public/auth/mfa_verify.html",
            {
                "request": request,
                "mfa_token": result.get("mfa_token", ""),
                "form_action": "/admin/mfa-verify",
                "back_url": "/admin/login",
                "next_url": next_url,
            },
        )

    access_token = result.get("access_token", "")
    refresh_token = result.get("refresh_token", "")

    if not access_token:
        return _login_error(request, db, "Login failed", next_url)

    response = RedirectResponse(url=next_url, status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=3600,
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=30 * 24 * 3600,
        )
    return response


@router.post("/mfa-verify", response_model=None)
def admin_mfa_verify_submit(
    request: Request,
    mfa_token: str = Form(...),
    code: str = Form(...),
    next_url: str = Form("/admin"),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    from app.services.auth_flow import AuthFlow

    try:
        result = AuthFlow.mfa_verify(db, mfa_token, code, request)
    except Exception as e:
        logger.warning("Admin MFA verification failed: %s", e)
        return templates.TemplateResponse(
            "public/auth/mfa_verify.html",
            {
                "request": request,
                "mfa_token": mfa_token,
                "form_action": "/admin/mfa-verify",
                "back_url": "/admin/login",
                "next_url": next_url,
                "error_message": "Invalid or expired code. Please try again.",
            },
        )

    access_token = result.get("access_token", "")
    refresh_token = result.get("refresh_token", "")

    if not access_token:
        return _login_error(request, db, "Login failed", next_url)

    response = RedirectResponse(url=next_url, status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=3600,
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=30 * 24 * 3600,
        )
    return response


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    from app.services.auth_flow import decode_access_token, revoke_sessions_for_person

    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = decode_access_token(db, access_token)
            person_id = payload.get("sub")
            if person_id:
                revoke_sessions_for_person(db, person_id)
                db.commit()
        except Exception:
            pass
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("logged_in", path="/")
    return response
