"""School admin — application review."""

import logging

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.application import ApplicationService
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/school/applications", tags=["school-applications"])


def _get_school_id(db: Session, auth: dict):
    svc = SchoolService(db)
    schools = svc.get_schools_for_owner(require_uuid(auth["person_id"]))
    return schools[0].id if schools else None


@router.get("")
def list_applications(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school_id = _get_school_id(db, auth)
    if not school_id:
        return templates.TemplateResponse(
            "school/applications/list.html",
            {"request": request, "auth": auth, "applications": [],
             "error_message": "No school found"},
        )

    svc = ApplicationService(db)
    applications = svc.list_for_school(school_id)

    enriched = []
    for app in applications:
        form = app.admission_form
        enriched.append({
            "app": app,
            "form_title": form.title if form else "",
            "parent": app.parent,
        })

    return templates.TemplateResponse(
        "school/applications/list.html",
        {"request": request, "auth": auth, "applications": enriched},
    )


@router.get("/{app_id}")
def application_detail(
    request: Request,
    app_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = ApplicationService(db)
    application = svc.get_by_id(require_uuid(app_id))
    if not application:
        return RedirectResponse(url="/school/applications?error=Application+not+found", status_code=303)

    form = application.admission_form
    parent = application.parent

    return templates.TemplateResponse(
        "school/applications/detail.html",
        {
            "request": request,
            "auth": auth,
            "application": application,
            "form": form,
            "parent": parent,
        },
    )


@router.post("/{app_id}/review")
def review_application(
    request: Request,
    app_id: str,
    decision: str = Form(...),
    review_notes: str = Form(""),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = ApplicationService(db)
    application = svc.get_by_id(require_uuid(app_id))
    if not application:
        return RedirectResponse(url="/school/applications?error=Application+not+found", status_code=303)

    try:
        svc.review(
            application,
            decision=decision,
            reviewer_id=require_uuid(auth["person_id"]),
            review_notes=review_notes if review_notes else None,
        )
        db.commit()
    except ValueError:
        logger.exception("Failed to review application %s", app_id)
        return RedirectResponse(
            url=f"/school/applications/{app_id}?error=An+unexpected+error+occurred",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/school/applications/{app_id}?success=Application+{decision}",
        status_code=303,
    )
