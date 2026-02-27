from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.person import Person, PersonStatus
from app.schemas.person import PersonCreate, PersonUpdate
from app.services.common import coerce_uuid
from app.services.query_utils import apply_ordering, apply_pagination, validate_enum
from app.services.response import ListResponseMixin


class People(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: PersonCreate):
        person = Person(**payload.model_dump())
        db.add(person)
        db.commit()
        db.refresh(person)
        return person

    @staticmethod
    def get(db: Session, person_id: str):
        person = db.get(Person, coerce_uuid(person_id))
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        return person

    @staticmethod
    def list(
        db: Session,
        email: str | None,
        status: str | None,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(Person)
        if email:
            stmt = stmt.where(Person.email.ilike(f"%{email}%"))
        if status:
            stmt = stmt.where(
                Person.status == validate_enum(status, PersonStatus, "status")
            )
        if is_active is not None:
            stmt = stmt.where(Person.is_active == is_active)
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {
                "created_at": Person.created_at,
                "last_name": Person.last_name,
                "email": Person.email,
            },
        )
        return list(db.scalars(apply_pagination(stmt, limit, offset)).all())

    @staticmethod
    def update(db: Session, person_id: str, payload: PersonUpdate):
        person = db.get(Person, coerce_uuid(person_id))
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(person, key, value)
        db.commit()
        db.refresh(person)
        return person

    @staticmethod
    def delete(db: Session, person_id: str):
        person = db.get(Person, coerce_uuid(person_id))
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        db.delete(person)
        db.commit()


people = People()
