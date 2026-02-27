"""School admin — admission form management."""

import logging
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.admission_form import AdmissionFormService
from app.services.common import require_uuid
from app.templates import templates
from app.web.schoolnet_deps import get_school_for_admin, require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/school/forms", tags=["school-forms"])


@router.get("")
def list_forms(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    current_user = SimpleNamespace(person_id=require_uuid(auth["person_id"]))
    school = get_school_for_admin(db, current_user)
    if not school:
        return templates.TemplateResponse(
            "school/forms/list.html",
            {"request": request, "auth": auth, "forms": [], "school": None,
             "error_message": "No school found. Please register a school first."},
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
    current_user = SimpleNamespace(person_id=require_uuid(auth["person_id"]))
    school = get_school_for_admin(db, current_user)
    if not school:
        return RedirectResponse(url="/school/forms?error=No+school+found", status_code=303)
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
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    current_user = SimpleNamespace(person_id=require_uuid(auth["person_id"]))
    school = get_school_for_admin(db, current_user)
    if not school:
        return RedirectResponse(url="/school/forms?error=No+school+found", status_code=303)

    from app.schemas.school import AdmissionFormCreate

    payload = AdmissionFormCreate(
        school_id=school.id,
        title=title,
        academic_year=academic_year,
        price_amount=price_amount * 100,  # Convert naira to kobo
        description=description if description else None,
        max_submissions=max_submissions,
    )
    svc = AdmissionFormService(db)
    svc.create(payload)
    db.commit()
    return RedirectResponse(url="/school/forms?success=Form+created+successfully", status_code=303)


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
        return RedirectResponse(url="/school/forms?error=Form+not+found", status_code=303)
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
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = AdmissionFormService(db)
    form = svc.get_by_id(require_uuid(form_id))
    if not form:
        return RedirectResponse(url="/school/forms?error=Form+not+found", status_code=303)

    from app.schemas.school import AdmissionFormUpdate

    payload = AdmissionFormUpdate(
        title=title,
        description=description if description else None,
        max_submissions=max_submissions,
        price_amount=price_amount * 100 if price_amount else None,
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
        return RedirectResponse(url="/school/forms?error=Form+not+found", status_code=303)
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
        return RedirectResponse(url="/school/forms?error=Form+not+found", status_code=303)
    svc.close(form)
    db.commit()
    return RedirectResponse(url="/school/forms?success=Form+closed", status_code=303)
