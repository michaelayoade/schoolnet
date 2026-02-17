"""Parent portal — applications and purchases."""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.admission_form import AdmissionFormService
from app.services.application import ApplicationService
from app.services.common import require_uuid
from app.services.file_upload import FileUploadService
from app.services.school import SchoolService
from app.services.ward import WardService
from app.templates import templates
from app.web.schoolnet_deps import require_parent_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parent/applications", tags=["parent-applications"])


def _get_form_str(form_data: Mapping[str, Any], key: str) -> str:
    """Extract a string value from form data.

    Starlette's FormData can contain both text values and UploadFile objects.
    For text fields, treat non-string values as empty.
    """
    value = form_data.get(key)
    if value is None or isinstance(value, UploadFile):
        return ""
    return str(value)


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
        enriched.append(
            {
                "app": app,
                "school_name": school_name,
                "form_title": form_title,
            }
        )

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
    svc = ApplicationService(db)
    try:
        result = svc.initiate_purchase(
            parent_id=require_uuid(auth["person_id"]),
            admission_form_id=require_uuid(form_id),
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
    return RedirectResponse(
        url="/parent/applications?success=Purchase+completed", status_code=303
    )


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
        return RedirectResponse(
            url="/parent/applications?error=Application+not+found", status_code=303
        )
    if str(application.parent_id) != auth["person_id"]:
        return RedirectResponse(
            url="/parent/applications?error=Not+your+application", status_code=303
        )

    form = application.admission_form
    school = form.school if form else None

    # Load parent's saved wards for the ward selector
    parent_id = require_uuid(auth["person_id"])
    ward_svc = WardService(db)
    ward_list = ward_svc.list_for_parent(parent_id)
    wards_data = [
        {
            "id": str(w.id),
            "first_name": w.first_name,
            "last_name": w.last_name,
            "date_of_birth": w.date_of_birth.isoformat() if w.date_of_birth else "",
            "gender": w.gender if w.gender else "",
        }
        for w in ward_list
    ]

    return templates.TemplateResponse(
        "parent/applications/fill.html",
        {
            "request": request,
            "auth": auth,
            "application": application,
            "form": form,
            "school": school,
            "existing_responses": application.form_responses or {},
            "wards": wards_data,
        },
    )


@router.post("/fill/{app_id}")
async def fill_application_submit(
    request: Request,
    app_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    svc = ApplicationService(db)
    application = svc.get_by_id(require_uuid(app_id))
    if not application:
        return RedirectResponse(
            url="/parent/applications?error=Application+not+found", status_code=303
        )
    if str(application.parent_id) != auth["person_id"]:
        return RedirectResponse(
            url="/parent/applications?error=Not+your+application", status_code=303
        )

    # Parse multipart form data for dynamic fields + file uploads
    form_data = await request.form()

    # Check if an existing ward was selected
    ward_id_str = form_data.get("ward_id", "")
    if ward_id_str:
        from app.services.common import coerce_uuid

        ward_svc = WardService(db)
        ward_uuid = coerce_uuid(str(ward_id_str))
        ward = ward_svc.get_by_id(ward_uuid) if ward_uuid else None
        if (
            ward
            and ward.parent_id == require_uuid(auth["person_id"])
            and ward.is_active
        ):
            ward_first_name = ward.first_name
            ward_last_name = ward.last_name
            ward_date_of_birth = (
                ward.date_of_birth.isoformat() if ward.date_of_birth else ""
            )
            ward_gender = ward.gender or ""
        else:
            ward_first_name = _get_form_str(form_data, "ward_first_name")
            ward_last_name = _get_form_str(form_data, "ward_last_name")
            ward_date_of_birth = _get_form_str(form_data, "ward_date_of_birth")
            ward_gender = _get_form_str(form_data, "ward_gender")
    else:
        ward_first_name = _get_form_str(form_data, "ward_first_name")
        ward_last_name = _get_form_str(form_data, "ward_last_name")
        ward_date_of_birth = _get_form_str(form_data, "ward_date_of_birth")
        ward_gender = _get_form_str(form_data, "ward_gender")

    from datetime import date

    try:
        dob = date.fromisoformat(str(ward_date_of_birth))
    except (ValueError, TypeError):
        return RedirectResponse(
            url=f"/parent/applications/fill/{app_id}?error=Invalid+date+of+birth",
            status_code=303,
        )

    # Collect dynamic form field responses (field_* keys)
    form_responses: dict[str, str] = {}
    for key in form_data:
        if key.startswith("field_"):
            field_name = key[6:]  # strip "field_" prefix
            form_responses[field_name] = str(form_data[key])

    # Process document uploads (doc_* keys)
    document_urls: dict[str, str] = dict(application.document_urls or {})
    upload_svc = FileUploadService(db)
    person_uuid = require_uuid(auth["person_id"])
    for key in form_data:
        if key.startswith("doc_"):
            doc_name = key[4:]  # strip "doc_" prefix
            value = form_data[key]
            if isinstance(value, UploadFile) and value.filename:
                upload_file = value
                filename = upload_file.filename
                if not filename:
                    continue
                try:
                    content = await upload_file.read()
                    if content:
                        record = upload_svc.upload(
                            content=content,
                            filename=filename,
                            content_type=upload_file.content_type
                            or "application/octet-stream",
                            uploaded_by=person_uuid,
                            category="application_document",
                            entity_type="application",
                            entity_id=str(application.id),
                        )
                        document_urls[doc_name] = record.url or ""
                except ValueError as e:
                    return RedirectResponse(
                        url=f"/parent/applications/fill/{app_id}?error={e}",
                        status_code=303,
                    )

    try:
        svc.submit(
            application,
            ward_first_name=str(ward_first_name),
            ward_last_name=str(ward_last_name),
            ward_date_of_birth=dob,
            ward_gender=str(ward_gender),
            form_responses=form_responses if form_responses else None,
            document_urls=document_urls if document_urls else None,
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
        return RedirectResponse(
            url="/parent/applications?error=Application+not+found", status_code=303
        )

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
        return RedirectResponse(
            url="/parent/applications?error=Application+not+found", status_code=303
        )
    if str(application.parent_id) != auth["person_id"]:
        return RedirectResponse(
            url="/parent/applications?error=Not+your+application", status_code=303
        )
    try:
        svc.withdraw(application)
        db.commit()
    except ValueError as e:
        return RedirectResponse(
            url=f"/parent/applications/{app_id}?error={e}",
            status_code=303,
        )
    return RedirectResponse(
        url="/parent/applications?success=Application+withdrawn", status_code=303
    )
