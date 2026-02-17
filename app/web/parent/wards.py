"""Parent portal — ward (child) management."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.common import require_uuid
from app.services.ward import WardService
from app.templates import templates
from app.web.schoolnet_deps import require_parent_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parent/wards", tags=["parent-wards"])


@router.get("")
def list_wards(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    """List all wards for the authenticated parent."""
    parent_id = require_uuid(auth["person_id"])
    svc = WardService(db)
    wards = svc.list_for_parent(parent_id)
    return templates.TemplateResponse(
        "parent/wards/list.html",
        {"request": request, "auth": auth, "wards": wards},
    )


@router.get("/create")
def create_ward_page(
    request: Request,
    auth: dict = Depends(require_parent_auth),
) -> Response:
    """Show the create ward form."""
    return templates.TemplateResponse(
        "parent/wards/form.html",
        {"request": request, "auth": auth, "ward": None},
    )


@router.post("/create")
def create_ward_submit(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    date_of_birth: str = Form(""),
    gender: str = Form(""),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    """Handle ward creation form submission."""
    parent_id = require_uuid(auth["person_id"])

    dob: date | None = None
    if date_of_birth:
        try:
            dob = date.fromisoformat(date_of_birth)
        except (ValueError, TypeError):
            return RedirectResponse(
                url="/parent/wards/create?error=Invalid+date+of+birth",
                status_code=303,
            )

    svc = WardService(db)
    svc.create(
        parent_id=parent_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        date_of_birth=dob,
        gender=gender if gender else None,
    )
    db.commit()

    return RedirectResponse(
        url="/parent/wards?success=Ward+added+successfully",
        status_code=303,
    )


@router.get("/edit/{ward_id}")
def edit_ward_page(
    request: Request,
    ward_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    """Show the edit ward form."""
    parent_id = require_uuid(auth["person_id"])
    svc = WardService(db)
    ward = svc.get_by_id(require_uuid(ward_id))

    if not ward or ward.parent_id != parent_id or not ward.is_active:
        return RedirectResponse(
            url="/parent/wards?error=Ward+not+found", status_code=303
        )

    return templates.TemplateResponse(
        "parent/wards/form.html",
        {"request": request, "auth": auth, "ward": ward},
    )


@router.post("/edit/{ward_id}")
def edit_ward_submit(
    request: Request,
    ward_id: str,
    first_name: str = Form(...),
    last_name: str = Form(...),
    date_of_birth: str = Form(""),
    gender: str = Form(""),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    """Handle ward edit form submission."""
    parent_id = require_uuid(auth["person_id"])
    svc = WardService(db)
    ward = svc.get_by_id(require_uuid(ward_id))

    if not ward or ward.parent_id != parent_id or not ward.is_active:
        return RedirectResponse(
            url="/parent/wards?error=Ward+not+found", status_code=303
        )

    dob: date | None = None
    if date_of_birth:
        try:
            dob = date.fromisoformat(date_of_birth)
        except (ValueError, TypeError):
            return RedirectResponse(
                url=f"/parent/wards/edit/{ward_id}?error=Invalid+date+of+birth",
                status_code=303,
            )

    svc.update(
        ward,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        date_of_birth=dob,
        gender=gender if gender else None,
    )
    db.commit()

    return RedirectResponse(
        url="/parent/wards?success=Ward+updated+successfully",
        status_code=303,
    )


@router.post("/delete/{ward_id}")
def delete_ward(
    request: Request,
    ward_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    """Soft-delete a ward."""
    parent_id = require_uuid(auth["person_id"])
    svc = WardService(db)
    ward = svc.get_by_id(require_uuid(ward_id))

    if not ward or ward.parent_id != parent_id or not ward.is_active:
        return RedirectResponse(
            url="/parent/wards?error=Ward+not+found", status_code=303
        )

    svc.delete(ward)
    db.commit()

    return RedirectResponse(
        url="/parent/wards?success=Ward+removed+successfully",
        status_code=303,
    )
