"""Parent portal — applications and purchases."""

import logging

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.models.school import AdmissionFormStatus
from app.services.admission_form import AdmissionFormService
from app.services.application import ApplicationService
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_parent_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parent/applications", tags=["parent-applications"])


@router.get("")
def list_applications(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    svc = ApplicationService(db)
    applications = svc.list_for_parent(require_uuid(auth["person_id"]))

    # Enrich with school/form names
    enriched = []
    for app in applications:
        form = app.admission_form
        school_name = ""
        form_title = ""
        if form:
            form_title = form.title
            if form.school:
                school_name = form.school.name
        enriched.append({
            "app": app,
            "school_name": school_name,
            "form_title": form_title,
        })

    return templates.TemplateResponse(
        "parent/applications/list.html",
        {"request": request, "auth": auth, "applications": enriched},
    )


@router.get("/purchase/{form_id}")
def purchase_page(
    request: Request,
    form_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    form_svc = AdmissionFormService(db)
    form = form_svc.get_by_id(require_uuid(form_id))
    if not form:
        return RedirectResponse(url="/schools?error=Form+not+found", status_code=303)
    if form.status != AdmissionFormStatus.active:
        return RedirectResponse(url="/schools?error=Form+not+available", status_code=303)

    price_amount = form_svc.get_price_amount(form)
    school_svc = SchoolService(db)
    school = school_svc.get_by_id(form.school_id)

    return templates.TemplateResponse(
        "parent/applications/purchase.html",
        {
            "request": request,
            "auth": auth,
            "form": form,
            "school": school,
            "price_amount": price_amount,
        },
    )


@router.post("/purchase/{form_id}")
def purchase_submit(
    request: Request,
    form_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    form_uuid = require_uuid(form_id)
    form_svc = AdmissionFormService(db)
    form = form_svc.get_by_id(form_uuid)
    if not form:
        return RedirectResponse(url="/schools?error=Form+not+found", status_code=303)
    if form.status != AdmissionFormStatus.active:
        return RedirectResponse(url="/schools?error=Form+not+available", status_code=303)

    svc = ApplicationService(db)
    try:
        result = svc.initiate_purchase(
            parent_id=require_uuid(auth["person_id"]),
            admission_form_id=form_uuid,
            callback_url=str(request.url_for("payment_callback")),
        )
        db.commit()
    except ValueError as e:
        return RedirectResponse(
            url=f"/parent/applications/purchase/{form_id}?error={e}",
            status_code=303,
        )

    auth_url = result.get("authorization_url", "")
    if auth_url:
        return RedirectResponse(url=auth_url, status_code=303)
    return RedirectResponse(url="/parent/applications?success=Purchase+completed", status_code=303)


@router.get("/fill/{app_id}")
def fill_application_page(
    request: Request,
    app_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    svc = ApplicationService(db)
    application = svc.get_by_id(require_uuid(app_id))
    if not application:
        return RedirectResponse(url="/parent/applications?error=Application+not+found", status_code=303)
    if str(application.parent_id) != auth["person_id"]:
        return RedirectResponse(url="/parent/applications?error=Not+your+application", status_code=303)

    form = application.admission_form
    school = form.school if form else None

    return templates.TemplateResponse(
        "parent/applications/fill.html",
        {
            "request": request,
            "auth": auth,
            "application": application,
            "form": form,
            "school": school,
        },
    )


@router.post("/fill/{app_id}")
def fill_application_submit(
    request: Request,
    app_id: str,
    ward_first_name: str = Form(...),
    ward_last_name: str = Form(...),
    ward_date_of_birth: str = Form(...),
    ward_gender: str = Form(...),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    svc = ApplicationService(db)
    application = svc.get_by_id(require_uuid(app_id))
    if not application:
        return RedirectResponse(url="/parent/applications?error=Application+not+found", status_code=303)
    if str(application.parent_id) != auth["person_id"]:
        return RedirectResponse(url="/parent/applications?error=Not+your+application", status_code=303)

    from datetime import date

    try:
        dob = date.fromisoformat(ward_date_of_birth)
    except (ValueError, TypeError):
        return RedirectResponse(
            url=f"/parent/applications/fill/{app_id}?error=Invalid+date+of+birth",
            status_code=303,
        )

    try:
        svc.submit(
            application,
            ward_first_name=ward_first_name,
            ward_last_name=ward_last_name,
            ward_date_of_birth=dob,
            ward_gender=ward_gender,
        )
        db.commit()
    except ValueError as e:
        return RedirectResponse(
            url=f"/parent/applications/fill/{app_id}?error={e}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/parent/applications/{app_id}?success=Application+submitted+successfully",
        status_code=303,
    )


@router.get("/{app_id}")
def application_detail(
    request: Request,
    app_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    svc = ApplicationService(db)
    application = svc.get_by_id(require_uuid(app_id))
    if not application:
        return RedirectResponse(url="/parent/applications?error=Application+not+found", status_code=303)
    if str(application.parent_id) != auth["person_id"]:
        logger.warning(
            "IDOR attempt: parent %s tried to access application %s owned by parent %s",
            auth["person_id"],
            app_id,
            application.parent_id,
        )
        return RedirectResponse(url="/parent/applications?error=Not+your+application", status_code=303)

    form = application.admission_form
    school = form.school if form else None

    return templates.TemplateResponse(
        "parent/applications/detail.html",
        {
            "request": request,
            "auth": auth,
            "application": application,
            "form": form,
            "school": school,
        },
    )


@router.post("/{app_id}/withdraw")
def withdraw_application(
    request: Request,
    app_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    svc = ApplicationService(db)
    application = svc.get_by_id(require_uuid(app_id))
    if not application:
        return RedirectResponse(url="/parent/applications?error=Application+not+found", status_code=303)
    if str(application.parent_id) != auth["person_id"]:
        return RedirectResponse(url="/parent/applications?error=Not+your+application", status_code=303)
    try:
        svc.withdraw(application)
        db.commit()
    except ValueError as e:
        return RedirectResponse(
            url=f"/parent/applications/{app_id}?error={e}",
            status_code=303,
        )
    return RedirectResponse(url="/parent/applications?success=Application+withdrawn", status_code=303)
