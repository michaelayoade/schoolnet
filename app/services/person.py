import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.person import Person, PersonStatus
from app.schemas.person import PersonCreate, PersonUpdate
from app.services.common import coerce_uuid, escape_like
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class PersonNotFoundError(ValueError):
    pass


class People(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Person.created_at,
            "last_name": Person.last_name,
            "email": Person.email,
        }
        column = allowed_columns.get(order_by)
        if column is None:
            raise ValueError(
                f"Invalid order_by. Allowed: {', '.join(sorted(allowed_columns))}"
            )
        if order_dir == "desc":
            return stmt.order_by(column.desc())
        return stmt.order_by(column.asc())

    @staticmethod
    def create(db: Session, payload: PersonCreate):
        person = Person(**payload.model_dump())
        db.add(person)
        db.flush()
        db.refresh(person)
        return person

    @staticmethod
    def get(db: Session, person_id: str):
        person = db.get(Person, coerce_uuid(person_id))
        if not person:
            raise PersonNotFoundError("Person not found")
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
            stmt = stmt.where(Person.email.ilike(f"%{escape_like(email)}%"))
        if status:
            try:
                resolved_status = PersonStatus(status)
            except ValueError as exc:
                raise ValueError("Invalid status") from exc
            stmt = stmt.where(Person.status == resolved_status)
        if is_active is not None:
            stmt = stmt.where(Person.is_active == is_active)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0

        stmt = People._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, person_id: str, payload: PersonUpdate):
        person = db.get(Person, coerce_uuid(person_id))
        if not person:
            raise PersonNotFoundError("Person not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(person, key, value)
        db.flush()
        db.refresh(person)
        return person

    @staticmethod
    def delete(db: Session, person_id: str):
        person = db.get(Person, coerce_uuid(person_id))
        if not person:
            raise PersonNotFoundError("Person not found")
        db.delete(person)
        db.flush()


people = People()
