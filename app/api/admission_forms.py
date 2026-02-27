"""Admission forms REST API — thin wrappers."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.schemas.school import (
    AdmissionFormCreate,
    AdmissionFormRead,
    AdmissionFormUpdate,
)
from app.services.admission_form import AdmissionFormService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admission-forms", tags=["admission-forms"])


@router.get("/{form_id}", response_model=AdmissionFormRead)
def get_form(form_id: UUID, db: Session = Depends(get_db)) -> AdmissionFormRead:
    svc = AdmissionFormService(db)
    form = svc.get_by_id(form_id)
    if not form:
        raise HTTPException(status_code=404, detail="Admission form not found")
    return form  # type: ignore[return-value]


@router.get("/school/{school_id}", response_model=list[AdmissionFormRead])
def list_school_forms(school_id: UUID, db: Session = Depends(get_db)) -> list:
    svc = AdmissionFormService(db)
    return svc.list_active_for_school(school_id)


@router.post("/", response_model=AdmissionFormRead, status_code=status.HTTP_201_CREATED)
def create_form(
    payload: AdmissionFormCreate,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("admission_forms:write")),
) -> AdmissionFormRead:
    svc = AdmissionFormService(db)
    try:
        svc.assert_school_owner(payload.school_id, UUID(auth["person_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="School not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Not your school") from exc

    form = svc.create(payload)
    db.commit()
    return form  # type: ignore[return-value]


@router.patch("/{form_id}", response_model=AdmissionFormRead)
def update_form(
    form_id: UUID,
    payload: AdmissionFormUpdate,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("admission_forms:write")),
) -> AdmissionFormRead:
    svc = AdmissionFormService(db)
    form = svc.get_by_id(form_id)
    if not form:
        raise HTTPException(status_code=404, detail="Admission form not found")

    try:
        svc.assert_school_owner(form.school_id, UUID(auth["person_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="School not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Not your school") from exc

    form = svc.update(form, payload)
    db.commit()
    return form  # type: ignore[return-value]


@router.post("/{form_id}/close", response_model=AdmissionFormRead)
def close_form(
    form_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("admission_forms:write")),
) -> AdmissionFormRead:
    svc = AdmissionFormService(db)
    form = svc.get_by_id(form_id)
    if not form:
        raise HTTPException(status_code=404, detail="Admission form not found")

    try:
        svc.assert_school_owner(form.school_id, UUID(auth["person_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="School not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Not your school") from exc

    form = svc.close(form)
    db.commit()
    return form  # type: ignore[return-value]
