import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import Customer
from app.schemas.billing import CustomerCreate, CustomerUpdate
from app.services.common import coerce_uuid
from app.services.query_utils import apply_ordering, apply_pagination
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class Customers(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: CustomerCreate) -> Customer:
        item = Customer(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created Customer: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Customer:
        item = db.get(Customer, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Customer not found")
        return item

    @staticmethod
    def list(
        db: Session,
        person_id: str | None,
        email: str | None,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Customer], int]:
        query = db.query(Customer)
        if person_id:
            query = query.filter(Customer.person_id == coerce_uuid(person_id))
        if email:
            query = query.filter(Customer.email.ilike(f"%{email}%"))
        if is_active is not None:
            query = query.filter(Customer.is_active == is_active)
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": Customer.created_at, "name": Customer.name},
        )
        items = list(apply_pagination(query, limit, offset).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: CustomerUpdate) -> Customer:
        item = db.get(Customer, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Customer not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", Customer.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Customer, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Customer not found")
        item.is_active = False
        db.commit()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Customer.__name__, item.id)


customers = Customers()
