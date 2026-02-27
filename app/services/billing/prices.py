import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import Price, PriceType, Product
from app.schemas.billing import PriceCreate, PriceUpdate
from app.services.common import coerce_uuid
from app.services.query_utils import apply_ordering, apply_pagination, validate_enum
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class Prices(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: PriceCreate) -> Price:
        if not db.get(Product, coerce_uuid(payload.product_id)):
            raise HTTPException(status_code=404, detail="Product not found")
        item = Price(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created Price: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Price:
        item = db.get(Price, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Price not found")
        return item

    @staticmethod
    def list(
        db: Session,
        product_id: str | None,
        type: str | None,
        currency: str | None,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Price], int]:
        query = db.query(Price)
        if product_id:
            query = query.filter(Price.product_id == coerce_uuid(product_id))
        if type:
            query = query.filter(Price.type == validate_enum(type, PriceType, "type"))
        if currency:
            query = query.filter(Price.currency == currency)
        if is_active is not None:
            query = query.filter(Price.is_active == is_active)
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": Price.created_at, "unit_amount": Price.unit_amount},
        )
        items = list(apply_pagination(query, limit, offset).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: PriceUpdate) -> Price:
        item = db.get(Price, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Price not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", Price.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Price, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Price not found")
        item.is_active = False
        db.commit()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Price.__name__, item.id)


prices = Prices()
