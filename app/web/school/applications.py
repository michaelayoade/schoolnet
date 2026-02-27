"""School admin — application review."""

import logging
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.application import ApplicationService
from app.services.common import require_uuid
from app.templates import templates
from app.web.schoolnet_deps import get_school_for_admin, require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/school/applications", tags=["school-applications"])


@router.get("")
def list_applications(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    current_user = SimpleNamespace(person_id=require_uuid(auth["person_id"]))
    school = get_school_for_admin(db, current_user)
    school_id = getattr(school, "school_id", None) if school else None
    if school and school_id is None:
        school_id = school.id
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
    except ValueError as e:
        return RedirectResponse(
            url=f"/school/applications/{app_id}?error={e}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/school/applications/{app_id}?success=Application+{decision}",
        status_code=303,
    )
