"""Schools REST API — thin wrappers around SchoolService."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission, require_user_auth
from app.schemas.school import (
    RatingCreate,
    RatingRead,
    SchoolCreate,
    SchoolRead,
    SchoolUpdate,
)
from app.services.school import SchoolService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/schools", tags=["schools"])


@router.get("/search", response_model=list[SchoolRead])
def search_schools(
    q: str | None = None,
    state: str | None = None,
    city: str | None = None,
    school_type: str | None = None,
    category: str | None = None,
    gender: str | None = None,
    fee_min: int | None = None,
    fee_max: int | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list:
    svc = SchoolService(db)
    schools, _ = svc.search(
        query=q,
        state=state,
        city=city,
        school_type=school_type,
        category=category,
        gender=gender,
        fee_min=fee_min,
        fee_max=fee_max,
        limit=limit,
        offset=offset,
    )
    return schools


@router.get("/{school_id}", response_model=SchoolRead)
def get_school(school_id: UUID, db: Session = Depends(get_db)) -> SchoolRead:
    svc = SchoolService(db)
    school = svc.get_by_id(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    return school  # type: ignore[return-value]


@router.post("/", response_model=SchoolRead, status_code=status.HTTP_201_CREATED)
def create_school(
    payload: SchoolCreate,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("schools:write")),
) -> SchoolRead:
    from app.services.common import require_uuid

    svc = SchoolService(db)
    school = svc.create(payload, owner_id=require_uuid(auth["person_id"]))
    db.commit()
    return school  # type: ignore[return-value]


@router.patch("/{school_id}", response_model=SchoolRead)
def update_school(
    school_id: UUID,
    payload: SchoolUpdate,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("schools:write")),
) -> SchoolRead:
    svc = SchoolService(db)
    school = svc.get_by_id(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    if str(school.owner_id) != auth["person_id"]:
        raise HTTPException(status_code=403, detail="Not your school")
    school = svc.update(school, payload)
    db.commit()
    return school  # type: ignore[return-value]


@router.get("/my/list", response_model=list[SchoolRead])
def my_schools(
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission("schools:write")),
) -> list:
    from app.services.common import require_uuid

    svc = SchoolService(db)
    return svc.get_schools_for_owner(require_uuid(auth["person_id"]))


@router.post(
    "/{school_id}/ratings",
    response_model=RatingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_rating(
    school_id: UUID,
    payload: RatingCreate,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_user_auth),
) -> RatingRead:
    from app.services.rating import RatingService

    svc = RatingService(db)
    from app.services.common import require_uuid

    rating = svc.create(
        school_id=school_id,
        parent_id=require_uuid(auth["person_id"]),
        score=payload.score,
        comment=payload.comment,
    )
    db.commit()
    return rating  # type: ignore[return-value]
