"""Applications REST API — thin wrappers."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission, require_user_auth
from app.models.school import AdmissionForm, School
from app.schemas.school import (
    ApplicationRead,
    ApplicationReview,
    ApplicationSubmit,
    PurchaseInitiate,
)
from app.services.application import ApplicationService
from app.services.common import require_uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("/purchase", status_code=status.HTTP_201_CREATED)
def purchase_form(
    payload: PurchaseInitiate,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_user_auth),
) -> dict:
    svc = ApplicationService(db)
    result = svc.initiate_purchase(
        parent_id=require_uuid(auth["person_id"]),
        admission_form_id=payload.admission_form_id,
        callback_url=payload.callback_url or "/parent/applications",
    )
    db.commit()
    return result


@router.get("/my", response_model=list[ApplicationRead])
def my_applications(
    db: Session = Depends(get_db),
    auth: dict = Depends(require_user_auth),
) -> list:
    svc = ApplicationService(db)
    return svc.list_for_parent(require_uuid(auth["person_id"]))


@router.get("/{app_id}", response_model=ApplicationRead)
def get_application(
    app_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_user_auth),
) -> ApplicationRead:
    svc = ApplicationService(db)
    application = svc.get_by_id(app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    # Parents can view their own; school admins checked via roles/permissions
    if str(application.parent_id) != auth["person_id"]:
        form = db.get(AdmissionForm, application.admission_form_id)
        school = db.get(School, form.school_id) if form else None
        if not school or str(school.owner_id) != auth["person_id"]:
            raise HTTPException(status_code=403, detail="Forbidden")
    return application  # type: ignore[return-value]


@router.patch("/{app_id}", response_model=ApplicationRead)
def submit_application(
    app_id: UUID,
    payload: ApplicationSubmit,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_user_auth),
) -> ApplicationRead:
    svc = ApplicationService(db)
    application = svc.get_by_id(app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if str(application.parent_id) != auth["person_id"]:
        raise HTTPException(status_code=403, detail="Not your application")
    application = svc.submit(
        application,
        ward_first_name=payload.ward_first_name,
        ward_last_name=payload.ward_last_name,
        ward_date_of_birth=payload.ward_date_of_birth,
        ward_gender=payload.ward_gender,
        form_responses=payload.form_responses,
        document_urls=payload.document_urls,
    )
    db.commit()
    return application  # type: ignore[return-value]


@router.post("/{app_id}/withdraw", response_model=ApplicationRead)
def withdraw_application(
    app_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_user_auth),
) -> ApplicationRead:
    svc = ApplicationService(db)
    application = svc.get_by_id(app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if str(application.parent_id) != auth["person_id"]:
        raise HTTPException(status_code=403, detail="Not your application")
    application = svc.withdraw(application)
    db.commit()
    return application  # type: ignore[return-value]


@router.get("/school/{school_id}", response_model=list[ApplicationRead])
def school_applications(
    school_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("applications:review")),
) -> list:
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    # Only school owner or admin can list applications
    roles = set(auth.get("roles") or [])
    if str(school.owner_id) != auth["person_id"] and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Forbidden")
    svc = ApplicationService(db)
    return svc.list_for_school(school_id)


@router.post("/{app_id}/review", response_model=ApplicationRead)
def review_application(
    app_id: UUID,
    payload: ApplicationReview,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("applications:review")),
) -> ApplicationRead:
    svc = ApplicationService(db)
    application = svc.get_by_id(app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    # Verify reviewer owns the school this application belongs to
    form = db.get(AdmissionForm, application.admission_form_id)
    school = db.get(School, form.school_id) if form else None
    roles = set(auth.get("roles") or [])
    if not school or (str(school.owner_id) != auth["person_id"] and "admin" not in roles):
        raise HTTPException(status_code=403, detail="Forbidden")
    application = svc.review(
        application,
        decision=payload.decision,
        reviewer_id=require_uuid(auth["person_id"]),
        review_notes=payload.review_notes,
    )
    db.commit()
    return application  # type: ignore[return-value]
