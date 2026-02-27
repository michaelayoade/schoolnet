import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import Entitlement, Product
from app.schemas.billing import (
    EntitlementCreate,
    EntitlementUpdate,
    ProductCreate,
    ProductUpdate,
)
from app.services.common import coerce_uuid
from app.services.query_utils import apply_ordering, apply_pagination
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class Products(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: ProductCreate) -> Product:
        item = Product(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created Product: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Product:
        item = db.get(Product, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Product not found")
        return item

    @staticmethod
    def list(
        db: Session,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Product], int]:
        query = db.query(Product)
        if is_active is not None:
            query = query.filter(Product.is_active == is_active)
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": Product.created_at, "name": Product.name},
        )
        items = list(apply_pagination(query, limit, offset).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: ProductUpdate) -> Product:
        item = db.get(Product, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Product not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", Product.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Product, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Product not found")
        item.is_active = False
        db.commit()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Product.__name__, item.id)


class Entitlements(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: EntitlementCreate) -> Entitlement:
        if not db.get(Product, coerce_uuid(payload.product_id)):
            raise HTTPException(status_code=404, detail="Product not found")
        item = Entitlement(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created Entitlement: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Entitlement:
        item = db.get(Entitlement, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Entitlement not found")
        return item

    @staticmethod
    def list(
        db: Session,
        product_id: str | None,
        feature_key: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Entitlement], int]:
        query = db.query(Entitlement)
        if product_id:
            query = query.filter(Entitlement.product_id == coerce_uuid(product_id))
        if feature_key:
            query = query.filter(Entitlement.feature_key == feature_key)
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": Entitlement.created_at},
        )
        items = list(apply_pagination(query, limit, offset).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: EntitlementUpdate) -> Entitlement:
        item = db.get(Entitlement, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Entitlement not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", Entitlement.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Entitlement, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Entitlement not found")
        db.delete(item)
        db.commit()
        logger.info("Deleted %s: %s", Entitlement.__name__, item_id)


products = Products()
entitlements = Entitlements()
