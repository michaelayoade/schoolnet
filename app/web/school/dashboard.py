"""School admin — dashboard and profile."""

import logging

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.schemas.school import SchoolUpdate
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["school-dashboard"])


def _get_school(db: Session, auth: dict):
    svc = SchoolService(db)
    schools = svc.get_schools_for_owner(require_uuid(auth["person_id"]))
    return schools[0] if schools else None


@router.get("/school")
def school_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school = _get_school(db, auth)
    if not school:
        return templates.TemplateResponse(
            "school/dashboard.html",
            {"request": request, "auth": auth, "school": None, "stats": None,
             "error_message": "No school found. Please register a school."},
        )

    svc = SchoolService(db)
    stats = svc.get_dashboard_stats(school.id)

    return templates.TemplateResponse(
        "school/dashboard.html",
        {"request": request, "auth": auth, "school": school, "stats": stats},
    )


@router.get("/school/profile")
def school_profile_page(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school = _get_school(db, auth)
    return templates.TemplateResponse(
        "school/profile/edit.html",
        {"request": request, "auth": auth, "school": school},
    )


@router.post("/school/profile")
def school_profile_update(
    request: Request,
    description: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    website: str = Form(""),
    fee_range_min: int | None = Form(default=None),
    fee_range_max: int | None = Form(default=None),
    bank_code: str = Form(""),
    account_number: str = Form(""),
    account_name: str = Form(""),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school = _get_school(db, auth)
    if not school:
        return RedirectResponse(url="/school/profile?error=School+not+found", status_code=303)

    svc = SchoolService(db)
    payload = SchoolUpdate(
        description=description if description else None,
        address=address if address else None,
        city=city if city else None,
        state=state if state else None,
        phone=phone if phone else None,
        email=email if email else None,
        website=website if website else None,
        fee_range_min=fee_range_min * 100 if fee_range_min else None,
        fee_range_max=fee_range_max * 100 if fee_range_max else None,
        bank_code=bank_code if bank_code else None,
        account_number=account_number if account_number else None,
        account_name=account_name if account_name else None,
    )
    svc.update(school, payload)
    db.commit()
    return RedirectResponse(url="/school/profile?success=Profile+updated", status_code=303)
