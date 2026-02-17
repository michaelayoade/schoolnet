"""Public-facing web routes — landing, school search, school profiles, auth."""

import logging

from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.api.deps import get_db
from app.services.auth_flow import (
    AuthFlow,
    decode_access_token,
    issue_email_verification_token,
    request_password_reset,
    reset_password,
    revoke_sessions_for_person,
    verify_email_token,
)
from app.services.common import require_uuid
from app.services.email import send_password_reset_email, send_verification_email
from app.services.registration import RegistrationService
from app.services.school import SchoolService
from app.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter(tags=["public"])


@router.get("/")
def landing_page(request: Request, db: Session = Depends(get_db)) -> Response:
    svc = SchoolService(db)
    featured, _ = svc.search(limit=6, offset=0)
    return templates.TemplateResponse(
        "public/index.html",
        {"request": request, "featured_schools": featured},
    )


@router.get("/schools")
def school_search(
    request: Request,
    q: str | None = None,
    state: str | None = None,
    city: str | None = None,
    school_type: str | None = None,
    category: str | None = None,
    gender: str | None = None,
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
) -> Response:
    limit = 12
    offset = (page - 1) * limit
    svc = SchoolService(db)
    schools, total = svc.search(
        query=q,
        state=state,
        city=city,
        school_type=school_type,
        category=category,
        gender=gender,
        limit=limit,
        offset=offset,
    )
    total_pages = (total + limit - 1) // limit if total else 1
    return templates.TemplateResponse(
        "public/schools/search.html",
        {
            "request": request,
            "schools": schools,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "q": q or "",
            "state": state or "",
            "city": city or "",
            "school_type": school_type or "",
            "category": category or "",
            "gender": gender or "",
        },
    )


@router.get("/schools/{slug}")
def school_profile(
    request: Request, slug: str, db: Session = Depends(get_db)
) -> Response:
    svc = SchoolService(db)
    school = svc.get_by_slug(slug)
    if not school:
        return templates.TemplateResponse(
            "public/schools/search.html",
            {
                "request": request,
                "schools": [],
                "total": 0,
                "page": 1,
                "total_pages": 1,
                "q": "",
                "state": "",
                "city": "",
                "school_type": "",
                "category": "",
                "gender": "",
                "error_message": "School not found",
            },
        )

    avg_rating = svc.get_average_rating(school.id)
    ratings = svc.get_ratings(school.id)

    from app.services.admission_form import AdmissionFormService

    form_svc = AdmissionFormService(db)
    forms = form_svc.list_active_for_school(school.id)

    # Check if logged-in parent can rate
    can_rate = False
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = decode_access_token(db, access_token)
            person_id = payload.get("sub")
            roles = payload.get("roles", [])
            if person_id and "parent" in roles:
                from app.services.rating import RatingService

                rating_svc = RatingService(db)
                can_rate = rating_svc.can_rate(
                    require_uuid(school.id),
                    require_uuid(person_id),
                )
        except Exception:
            pass

    return templates.TemplateResponse(
        "public/schools/profile.html",
        {
            "request": request,
            "school": school,
            "avg_rating": avg_rating,
            "ratings": ratings,
            "admission_forms": forms,
            "can_rate": can_rate,
        },
    )


@router.post("/schools/{slug}/rate")
def school_rate_submit(
    request: Request,
    slug: str,
    score: int = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
) -> Response:
    from app.services.rating import RatingService

    # Verify logged-in parent
    access_token = request.cookies.get("access_token")
    if not access_token:
        return RedirectResponse(url="/login", status_code=303)
    try:
        payload = decode_access_token(db, access_token)
        person_id = payload.get("sub")
    except Exception:
        return RedirectResponse(url="/login", status_code=303)

    svc = SchoolService(db)
    school = svc.get_by_slug(slug)
    if not school:
        return RedirectResponse(url="/schools?error=School+not+found", status_code=303)

    rating_svc = RatingService(db)
    try:
        rating_svc.create(
            school_id=school.id,
            parent_id=require_uuid(person_id),
            score=score,
            comment=comment if comment else None,
        )
        db.commit()
    except ValueError as e:
        return RedirectResponse(
            url=f"/schools/{slug}?error={e}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/schools/{slug}?success=Rating+submitted",
        status_code=303,
    )


# ── Auth routes (register + login) ──────────────────────


@router.get("/register")
def register_choice(request: Request) -> Response:
    return templates.TemplateResponse(
        "public/auth/register_choice.html", {"request": request}
    )


@router.get("/register/parent")
def register_parent_form(request: Request) -> Response:
    return templates.TemplateResponse(
        "public/auth/register_parent.html", {"request": request}
    )


@router.post("/register/parent")
def register_parent_submit(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    reg = RegistrationService(db)
    try:
        reg.register_parent(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
            phone=phone if phone else None,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "public/auth/register_parent.html",
            {"request": request, "error_message": str(e)},
        )

    db.commit()

    # Send verification email
    try:
        from app.models.person import Person

        person = db.query(Person).filter(Person.email == email).first()
        if person:
            token = issue_email_verification_token(db, str(person.id), email)
            send_verification_email(db, email, token, first_name)
    except Exception as e:
        logger.warning("Failed to send verification email: %s", e)

    return RedirectResponse(
        url="/login?success=Registration+successful.+Please+check+your+email+to+verify+your+account.",
        status_code=303,
    )


@router.get("/register/school")
def register_school_form(request: Request) -> Response:
    return templates.TemplateResponse(
        "public/auth/register_school.html", {"request": request}
    )


@router.post("/register/school")
def register_school_submit(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    password: str = Form(...),
    school_name: str = Form(...),
    school_type: str = Form(...),
    category: str = Form(...),
    state: str = Form(""),
    city: str = Form(""),
    address: str = Form(""),
    db: Session = Depends(get_db),
) -> Response:
    reg = RegistrationService(db)
    try:
        reg.register_school_admin(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
            school_name=school_name,
            school_type=school_type,
            category=category,
            phone=phone if phone else None,
            state=state if state else None,
            city=city if city else None,
            address=address if address else None,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "public/auth/register_school.html",
            {"request": request, "error_message": str(e)},
        )

    db.commit()
    return RedirectResponse(
        url="/login?success=Registration+successful.+Your+school+is+pending+approval.",
        status_code=303,
    )


@router.get("/login")
def login_form(request: Request) -> Response:
    return templates.TemplateResponse("public/auth/login.html", {"request": request})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    try:
        result = AuthFlow.login(db, email, password, request, "local")
    except Exception as e:
        logger.warning("Login failed for %s: %s", email, e)
        return templates.TemplateResponse(
            "public/auth/login.html",
            {"request": request, "error_message": "Invalid email or password"},
        )

    # Check email verification
    from app.models.person import Person

    person = db.query(Person).filter(Person.email == email).first()
    if person and not person.email_verified:
        # Send new verification email
        try:
            token = issue_email_verification_token(db, str(person.id), email)
            send_verification_email(db, email, token, person.first_name)
        except Exception:
            pass
        return templates.TemplateResponse(
            "public/auth/login.html",
            {
                "request": request,
                "error_message": "Please verify your email first. A new verification link has been sent.",
            },
        )

    if result.get("mfa_required"):
        return templates.TemplateResponse(
            "public/auth/mfa_verify.html",
            {"request": request, "mfa_token": result.get("mfa_token", "")},
        )

    access_token = result.get("access_token", "")
    refresh_token = result.get("refresh_token", "")

    # Determine redirect based on roles in the JWT
    redirect_url = "/parent"
    try:
        payload = decode_access_token(db, access_token)
        roles = payload.get("roles", [])
        if "platform_admin" in roles or "admin" in roles:
            redirect_url = "/admin/schools"
        elif "school_admin" in roles:
            redirect_url = "/school"
    except Exception:
        logger.debug("Could not decode access token for redirect")

    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=900,
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            max_age=30 * 24 * 3600,
        )
    response.set_cookie(
        key="logged_in",
        value="1",
        httponly=False,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return response


@router.post("/mfa-verify")
def mfa_verify_submit(
    request: Request,
    mfa_token: str = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    try:
        result = AuthFlow.mfa_verify(db, mfa_token, code, request)
    except Exception as e:
        logger.warning("MFA verification failed: %s", e)
        return templates.TemplateResponse(
            "public/auth/mfa_verify.html",
            {
                "request": request,
                "mfa_token": mfa_token,
                "error_message": "Invalid or expired code. Please try again.",
            },
        )

    access_token = result.get("access_token", "")
    refresh_token = result.get("refresh_token", "")

    # Determine redirect based on roles in the JWT
    redirect_url = "/parent"
    try:
        payload = decode_access_token(db, access_token)
        roles = payload.get("roles", [])
        if "platform_admin" in roles or "admin" in roles:
            redirect_url = "/admin/schools"
        elif "school_admin" in roles:
            redirect_url = "/school"
    except Exception:
        logger.debug("Could not decode access token for redirect")

    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=900,
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            max_age=30 * 24 * 3600,
        )
    response.set_cookie(
        key="logged_in",
        value="1",
        httponly=False,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return response


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = decode_access_token(db, access_token)
            person_id = payload.get("sub")
            if person_id:
                revoke_sessions_for_person(db, person_id)
                db.commit()
        except Exception:
            pass  # Still delete cookies even if revocation fails
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("logged_in")
    return response


@router.post("/auth/web-refresh")
def web_refresh(request: Request, db: Session = Depends(get_db)) -> Response:
    """Refresh access token using the refresh_token cookie."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return JSONResponse(
            status_code=401, content={"detail": "Missing refresh token"}
        )

    try:
        result = AuthFlow.refresh(db, refresh_token, request)
    except Exception:
        return JSONResponse(
            status_code=401, content={"detail": "Invalid refresh token"}
        )

    new_access = result.get("access_token", "")
    new_refresh = result.get("refresh_token", "")

    response = JSONResponse(status_code=200, content={"ok": True})
    response.set_cookie(
        key="access_token",
        value=new_access,
        httponly=True,
        samesite="lax",
        max_age=900,
    )
    if new_refresh:
        response.set_cookie(
            key="refresh_token",
            value=new_refresh,
            httponly=True,
            samesite="lax",
            max_age=30 * 24 * 3600,
        )
    response.set_cookie(
        key="logged_in",
        value="1",
        httponly=False,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return response


# ── Password Reset ─────────────────────────────────────


@router.get("/forgot-password")
def forgot_password_page(request: Request) -> Response:
    return templates.TemplateResponse(
        "public/auth/forgot_password.html", {"request": request}
    )


@router.post("/forgot-password")
def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    result = request_password_reset(db, email)
    if result:
        send_password_reset_email(
            db,
            result["email"],
            result["token"],
            result.get("person_name"),
        )
    # Always show success to avoid email enumeration
    return templates.TemplateResponse(
        "public/auth/forgot_password.html",
        {
            "request": request,
            "success_message": "If an account with that email exists, a reset link has been sent.",
        },
    )


@router.get("/reset-password")
def reset_password_page(
    request: Request,
    token: str = Query(""),
) -> Response:
    return templates.TemplateResponse(
        "public/auth/reset_password.html",
        {"request": request, "token": token},
    )


@router.post("/reset-password")
def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    if new_password != confirm_password:
        return templates.TemplateResponse(
            "public/auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "error_message": "Passwords do not match",
            },
        )
    try:
        reset_password(db, token, new_password)
    except Exception:
        return templates.TemplateResponse(
            "public/auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "error_message": "Invalid or expired reset link",
            },
        )
    return RedirectResponse(
        url="/login?success=Password+reset+successfully.+Please+log+in.",
        status_code=303,
    )


# ── Email verification ──────────────────────────────────


@router.get("/verify-email")
def verify_email_page(
    request: Request,
    token: str = Query(""),
    db: Session = Depends(get_db),
) -> Response:
    if not token:
        return templates.TemplateResponse(
            "public/auth/verify_email.html", {"request": request}
        )
    try:
        verify_email_token(db, token)
        db.commit()
    except Exception:
        return templates.TemplateResponse(
            "public/auth/verify_email.html",
            {
                "request": request,
                "error_message": "Invalid or expired verification link.",
            },
        )
    return templates.TemplateResponse(
        "public/auth/verify_email.html",
        {
            "request": request,
            "success_message": "Your email has been verified. You can now sign in.",
        },
    )
