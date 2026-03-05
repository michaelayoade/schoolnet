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
    def __init__(self, db: Session) -> None:
        self.db = db

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

    def create(self, payload: PersonCreate):
        person = Person(**payload.model_dump())
        self.db.add(person)
        self.db.flush()
        self.db.refresh(person)
        return person

    def get(self, person_id: str):
        person = self.db.get(Person, coerce_uuid(person_id))
        if not person:
            raise PersonNotFoundError("Person not found")
        return person

    def list(
        self,
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
        total = self.db.scalar(count_stmt) or 0

        stmt = People._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def update(self, person_id: str, payload: PersonUpdate):
        person = self.db.get(Person, coerce_uuid(person_id))
        if not person:
            raise PersonNotFoundError("Person not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(person, key, value)
        self.db.flush()
        self.db.refresh(person)
        return person

    def delete(self, person_id: str):
        person = self.db.get(Person, coerce_uuid(person_id))
        if not person:
            raise PersonNotFoundError("Person not found")
        self.db.delete(person)
        self.db.flush()
