"""Web authentication routes — login and logout pages."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.auth import AuthProvider, UserCredential
from app.models.person import Person
from app.services.branding_context import load_branding_context
from app.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["web-auth"])


def _is_secure_request(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    return forwarded_proto.split(",", 1)[0].strip().lower() == "https"


def _safe_next_url(next_url: str | None, default: str = "/admin") -> str:
    candidate = (next_url or "").strip()
    if not candidate:
        return default
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return default
    if not candidate.startswith("/") or candidate.startswith("//"):
        return default
    return candidate


def _access_cookie_max_age_seconds() -> int:
    raw = os.getenv("JWT_ACCESS_TTL_MINUTES", "15")
    try:
        minutes = int(raw)
    except ValueError:
        minutes = 15
    return max(minutes, 1) * 60


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next: str = "/admin",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    branding = load_branding_context(db)
    safe_next = _safe_next_url(next)
    return templates.TemplateResponse(
        "admin/login.html",
        {
            "request": request,
            "title": "Login",
            "next_url": safe_next,
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
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/admin"),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    email = email.strip()
    next_url = _safe_next_url(next)
    secure_cookie = _is_secure_request(request)

    if not email or not password:
        return _login_error(request, db, "Email and password are required", next_url)

    # Resolve email to credential username
    login_id = email
    person = db.scalar(select(Person).where(Person.email == email))
    if person:
        credential = db.scalar(
            select(UserCredential).where(
                UserCredential.person_id == person.id,
                UserCredential.provider == AuthProvider.local,
                UserCredential.is_active.is_(True),
            )
        )
        if credential and credential.username:
            login_id = credential.username

        # Check email verification before proceeding with login
        if credential and not person.email_verified:
            from app.services.auth_flow import verify_password

            if verify_password(password, credential.password_hash):
                return _login_error(
                    request,
                    db,
                    "Please verify your email address before logging in. Check your inbox for a verification link.",
                    next_url,
                )

    from app.services.auth_flow import AuthFlow, AuthFlowServiceError

    try:
        result = AuthFlow.login(db, login_id, password, request, None)
        db.commit()
    except AuthFlowServiceError as exc:
        if str(exc.detail) == "Invalid credentials":
            db.commit()
        else:
            db.rollback()
        return _login_error(request, db, "Invalid email or password", next_url)

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
    access_max_age = _access_cookie_max_age_seconds()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
        max_age=access_max_age,
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=secure_cookie,
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
    from app.services.auth_flow import AuthFlow, AuthFlowServiceError

    next_url = _safe_next_url(next_url)
    secure_cookie = _is_secure_request(request)

    try:
        result = AuthFlow.mfa_verify(db, mfa_token, code, request)
        db.commit()
    except AuthFlowServiceError as e:
        db.rollback()
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
    access_max_age = _access_cookie_max_age_seconds()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
        max_age=access_max_age,
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
            path="/",
            max_age=30 * 24 * 3600,
        )
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    from app.services.auth_flow import (
        AuthFlowServiceError,
        decode_access_token,
        revoke_sessions_for_person,
    )

    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = decode_access_token(db, access_token)
            person_id = payload.get("sub")
            if person_id:
                revoke_sessions_for_person(db, person_id)
                db.commit()
        except AuthFlowServiceError:
            pass
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("logged_in", path="/")
    return response
