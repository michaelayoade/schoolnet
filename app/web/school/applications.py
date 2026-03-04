"""School admin — application review."""

import contextlib
import csv
import io
import logging
from typing import Any
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response, StreamingResponse

from app.api.deps import get_db
from app.models.school import Application, ApplicationStatus
from app.services.application import ApplicationService
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/school/applications", tags=["school-applications"])


def _get_school_id(db: Session, auth: dict) -> UUID | None:
    svc = SchoolService(db)
    schools = svc.get_schools_for_owner(require_uuid(auth["person_id"]))
    return schools[0].id if schools else None


def _get_app_for_school(
    db: Session, app_id: str, school_id: UUID
) -> Application | None:
    """Fetch application and verify it belongs to the school admin's school."""
    svc = ApplicationService(db)
    application = svc.get_by_id(require_uuid(app_id))
    if not application:
        return None
    form = application.admission_form
    if not form or form.school_id != school_id:
        return None
    return application


@router.get("")
def list_applications(
    request: Request,
    status: str | None = Query(None),
    form_id: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school_id = _get_school_id(db, auth)
    if not school_id:
        return templates.TemplateResponse(
            "school/applications/list.html",
            {
                "request": request,
                "auth": auth,
                "applications": [],
                "pagination": {},
                "forms": [],
                "current_status": None,
                "current_form_id": None,
                "current_search": None,
                "error_message": "No school found",
            },
        )

    # Parse status filter
    status_filter: ApplicationStatus | None = None
    if status:
        with contextlib.suppress(ValueError):
            status_filter = ApplicationStatus(status)

    # Parse form filter
    form_id_filter: UUID | None = None
    if form_id:
        with contextlib.suppress(ValueError):
            form_id_filter = require_uuid(form_id)

    svc = ApplicationService(db)
    result: dict[str, Any] = svc.list_for_school(
        school_id,
        status=status_filter,
        form_id=form_id_filter,
        search=q,
        page=page,
    )

    enriched = []
    for app in result["items"]:
        form = app.admission_form
        enriched.append(
            {
                "app": app,
                "form_title": form.title if form else "",
                "parent": app.parent,
            }
        )

    school_svc = SchoolService(db)
    forms = school_svc.list_admission_forms(school_id)

    return templates.TemplateResponse(
        "school/applications/list.html",
        {
            "request": request,
            "auth": auth,
            "applications": enriched,
            "pagination": {
                "page": result["page"],
                "pages": result["pages"],
                "total": result["total"],
                "page_size": result["page_size"],
            },
            "forms": forms,
            "current_status": status,
            "current_form_id": form_id,
            "current_search": q if q else "",
            "statuses": [s.value for s in ApplicationStatus],
        },
    )


@router.get("/export/csv")
def export_applications_csv(
    request: Request,
    status: str | None = Query(None),
    form_id: str | None = Query(None),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    """Export applications as CSV with current filters applied."""
    school_id = _get_school_id(db, auth)
    if not school_id:
        return RedirectResponse(url="/school/applications?error=No+school+found", status_code=303)

    status_filter: ApplicationStatus | None = None
    if status:
        with contextlib.suppress(ValueError):
            status_filter = ApplicationStatus(status)

    form_id_filter: UUID | None = None
    if form_id:
        with contextlib.suppress(ValueError):
            form_id_filter = require_uuid(form_id)

    svc = ApplicationService(db)
    result: dict[str, Any] = svc.list_for_school(
        school_id,
        status=status_filter,
        form_id=form_id_filter,
        search=q,
        page=1,
        page_size=10000,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Application #",
        "Ward First Name",
        "Ward Last Name",
        "Ward DOB",
        "Ward Gender",
        "Parent Name",
        "Parent Email",
        "Parent Phone",
        "Form",
        "Status",
        "Submitted At",
        "Reviewed At",
        "Review Notes",
    ])

    for app in result["items"]:
        form = app.admission_form
        parent = app.parent
        writer.writerow([
            app.application_number,
            app.ward_first_name or "",
            app.ward_last_name or "",
            str(app.ward_date_of_birth) if app.ward_date_of_birth else "",
            app.ward_gender or "",
            f"{parent.first_name} {parent.last_name}" if parent else "",
            parent.email if parent else "",
            parent.phone if parent else "",
            form.title if form else "",
            app.status.value if app.status else "",
            app.submitted_at.strftime("%Y-%m-%d %H:%M") if app.submitted_at else "",
            app.reviewed_at.strftime("%Y-%m-%d %H:%M") if app.reviewed_at else "",
            app.review_notes or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )


@router.get("/{app_id}")
def application_detail(
    request: Request,
    app_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school_id = _get_school_id(db, auth)
    if not school_id:
        return RedirectResponse(url="/school/applications?error=No+school+found", status_code=303)

    application = _get_app_for_school(db, app_id, school_id)
    if not application:
        return RedirectResponse(
            url="/school/applications?error=Application+not+found", status_code=303
        )

    return templates.TemplateResponse(
        "school/applications/detail.html",
        {
            "request": request,
            "auth": auth,
            "application": application,
            "form": application.admission_form,
            "parent": application.parent,
        },
    )


@router.post("/{app_id}/verify-document")
def verify_document(
    request: Request,
    app_id: str,
    doc_name: str = Form(...),
    doc_status: str = Form(...),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    """Mark an individual document as verified or rejected."""
    school_id = _get_school_id(db, auth)
    if not school_id:
        return RedirectResponse(url="/school/applications?error=No+school+found", status_code=303)

    application = _get_app_for_school(db, app_id, school_id)
    if not application:
        return RedirectResponse(
            url="/school/applications?error=Application+not+found", status_code=303
        )

    svc = ApplicationService(db)
    try:
        svc.verify_document(application, doc_name=doc_name, doc_status=doc_status)
        db.commit()
    except ValueError as e:
        return RedirectResponse(
            url=f"/school/applications/{app_id}?error={quote_plus(str(e))}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/school/applications/{app_id}?success=Document+{quote_plus(doc_status)}",
        status_code=303,
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
    school_id = _get_school_id(db, auth)
    if not school_id:
        return RedirectResponse(url="/school/applications?error=No+school+found", status_code=303)

    application = _get_app_for_school(db, app_id, school_id)
    if not application:
        return RedirectResponse(
            url="/school/applications?error=Application+not+found", status_code=303
        )

    svc = ApplicationService(db)
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
            url=f"/school/applications/{app_id}?error={quote_plus(str(e))}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/school/applications/{app_id}?success=Application+{quote_plus(decision)}",
        status_code=303,
    )
