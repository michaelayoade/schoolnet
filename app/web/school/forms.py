"""School admin — admission form management."""

import json
import logging

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.models.school import School
from app.services.admission_form import AdmissionFormService
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/school/forms", tags=["school-forms"])


def _parse_form_fields_json(raw: str) -> list[dict] | None:
    """Parse form_fields JSON from form submission.

    Returns a list of field dicts (possibly empty), or None if input is missing.
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Invalid form_fields_json: %s", e)
        return None
    if not isinstance(parsed, list):
        return None
    # Filter out incomplete entries (must have a label)
    return [f for f in parsed if isinstance(f, dict) and f.get("label")]


def _parse_required_documents_json(raw: str) -> list[str] | None:
    """Parse required_documents JSON from form submission.

    Returns a list of document name strings (possibly empty), or None if input is missing.
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Invalid required_documents_json: %s", e)
        return None
    if not isinstance(parsed, list):
        return None
    return [d for d in parsed if isinstance(d, str) and d.strip()]


def _get_school_for_admin(db: Session, auth: dict) -> School | None:
    svc = SchoolService(db)
    schools = svc.get_schools_for_owner(require_uuid(auth["person_id"]))
    return schools[0] if schools else None


@router.get("")
def list_forms(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school = _get_school_for_admin(db, auth)
    if not school:
        return templates.TemplateResponse(
            "school/forms/list.html",
            {
                "request": request,
                "auth": auth,
                "forms": [],
                "school": None,
                "error_message": "No school found. Please register a school first.",
            },
        )
    svc = AdmissionFormService(db)
    forms = svc.list_for_school(school.id)
    # Enrich with price
    enriched = []
    for form in forms:
        price_amount = svc.get_price_amount(form)
        enriched.append({"form": form, "price_amount": price_amount})
    return templates.TemplateResponse(
        "school/forms/list.html",
        {"request": request, "auth": auth, "forms": enriched, "school": school},
    )


@router.get("/create")
def create_form_page(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school = _get_school_for_admin(db, auth)
    if not school:
        return RedirectResponse(
            url="/school/forms?error=No+school+found", status_code=303
        )
    return templates.TemplateResponse(
        "school/forms/create.html",
        {"request": request, "auth": auth, "school": school},
    )


@router.post("/create")
def create_form_submit(
    request: Request,
    title: str = Form(...),
    academic_year: str = Form(...),
    price_amount: int = Form(...),
    description: str = Form(""),
    max_submissions: int | None = Form(default=None),
    form_fields_json: str = Form(""),
    required_documents_json: str = Form(""),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school = _get_school_for_admin(db, auth)
    if not school:
        return RedirectResponse(
            url="/school/forms?error=No+school+found", status_code=303
        )

    from app.schemas.school import AdmissionFormCreate

    form_fields = _parse_form_fields_json(form_fields_json)
    required_documents = _parse_required_documents_json(required_documents_json)

    payload = AdmissionFormCreate(
        school_id=school.id,
        title=title,
        academic_year=academic_year,
        price_amount=price_amount * 100,  # Convert naira to kobo
        description=description if description else None,
        max_submissions=max_submissions,
        form_fields=form_fields,
        required_documents=required_documents,
    )
    svc = AdmissionFormService(db)
    svc.create(payload)
    db.commit()
    return RedirectResponse(
        url="/school/forms?success=Form+created+successfully", status_code=303
    )


@router.get("/{form_id}/edit")
def edit_form_page(
    request: Request,
    form_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = AdmissionFormService(db)
    form = svc.get_by_id(require_uuid(form_id))
    if not form:
        return RedirectResponse(
            url="/school/forms?error=Form+not+found", status_code=303
        )
    price_amount = svc.get_price_amount(form)
    return templates.TemplateResponse(
        "school/forms/edit.html",
        {"request": request, "auth": auth, "form": form, "price_amount": price_amount},
    )


@router.post("/{form_id}/edit")
def edit_form_submit(
    request: Request,
    form_id: str,
    title: str = Form(...),
    description: str = Form(""),
    max_submissions: int | None = Form(default=None),
    price_amount: int | None = Form(default=None),
    form_fields_json: str = Form(""),
    required_documents_json: str = Form(""),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = AdmissionFormService(db)
    form = svc.get_by_id(require_uuid(form_id))
    if not form:
        return RedirectResponse(
            url="/school/forms?error=Form+not+found", status_code=303
        )

    from app.schemas.school import AdmissionFormUpdate

    form_fields = _parse_form_fields_json(form_fields_json)
    required_documents = _parse_required_documents_json(required_documents_json)

    payload = AdmissionFormUpdate(
        title=title,
        description=description if description else None,
        max_submissions=max_submissions,
        price_amount=price_amount * 100 if price_amount else None,
        form_fields=form_fields,
        required_documents=required_documents,
    )
    svc.update(form, payload)
    db.commit()
    return RedirectResponse(url="/school/forms?success=Form+updated", status_code=303)


@router.post("/{form_id}/activate")
def activate_form(
    request: Request,
    form_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = AdmissionFormService(db)
    form = svc.get_by_id(require_uuid(form_id))
    if not form:
        return RedirectResponse(
            url="/school/forms?error=Form+not+found", status_code=303
        )
    svc.activate(form)
    db.commit()
    return RedirectResponse(url="/school/forms?success=Form+activated", status_code=303)


@router.post("/{form_id}/close")
def close_form(
    request: Request,
    form_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = AdmissionFormService(db)
    form = svc.get_by_id(require_uuid(form_id))
    if not form:
        return RedirectResponse(
            url="/school/forms?error=Form+not+found", status_code=303
        )
    svc.close(form)
    db.commit()
    return RedirectResponse(url="/school/forms?success=Form+closed", status_code=303)
