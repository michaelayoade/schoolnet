"""Admission forms REST API — thin wrappers."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
def list_school_forms(
    school_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list:
    svc = AdmissionFormService(db)
    return svc.list_for_school(school_id, limit=limit, offset=offset)


@router.post("/", response_model=AdmissionFormRead, status_code=status.HTTP_201_CREATED)
def create_form(
    payload: AdmissionFormCreate,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("admission_forms:write")),
) -> AdmissionFormRead:
    from app.models.school import School

    school = db.get(School, payload.school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    roles = set(auth.get("roles") or [])
    if str(school.owner_id) != auth["person_id"] and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Not your school")
    svc = AdmissionFormService(db)
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
    from app.models.school import School

    svc = AdmissionFormService(db)
    form = svc.get_by_id(form_id)
    if not form:
        raise HTTPException(status_code=404, detail="Admission form not found")
    school = db.get(School, form.school_id)
    roles = set(auth.get("roles") or [])
    if not school or (str(school.owner_id) != auth["person_id"] and "admin" not in roles):
        raise HTTPException(status_code=403, detail="Not your school")
    form = svc.update(form, payload)
    db.commit()
    return form  # type: ignore[return-value]


@router.post("/{form_id}/close", response_model=AdmissionFormRead)
def close_form(
    form_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("admission_forms:write")),
) -> AdmissionFormRead:
    from app.models.school import School

    svc = AdmissionFormService(db)
    form = svc.get_by_id(form_id)
    if not form:
        raise HTTPException(status_code=404, detail="Admission form not found")
    school = db.get(School, form.school_id)
    roles = set(auth.get("roles") or [])
    if not school or (str(school.owner_id) != auth["person_id"] and "admin" not in roles):
        raise HTTPException(status_code=403, detail="Not your school")
    form = svc.close(form)
    db.commit()
    return form  # type: ignore[return-value]
