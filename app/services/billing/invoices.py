import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import (
    Customer,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Price,
    Subscription,
    SubscriptionItem,
)
from app.schemas.billing import (
    InvoiceCreate,
    InvoiceItemCreate,
    InvoiceItemUpdate,
    InvoiceUpdate,
)
from app.services.common import coerce_uuid
from app.services.query_utils import apply_ordering, apply_pagination, validate_enum
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class Invoices(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: InvoiceCreate) -> Invoice:
        if not db.get(Customer, coerce_uuid(payload.customer_id)):
            raise HTTPException(status_code=404, detail="Customer not found")
        if payload.subscription_id and not db.get(
            Subscription, coerce_uuid(payload.subscription_id)
        ):
            raise HTTPException(status_code=404, detail="Subscription not found")
        item = Invoice(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created Invoice: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Invoice:
        item = db.get(Invoice, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return item

    @staticmethod
    def list(
        db: Session,
        customer_id: str | None,
        subscription_id: str | None,
        status: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Invoice], int]:
        query = db.query(Invoice)
        if customer_id:
            query = query.filter(Invoice.customer_id == coerce_uuid(customer_id))
        if subscription_id:
            query = query.filter(Invoice.subscription_id == coerce_uuid(subscription_id))
        if status:
            query = query.filter(
                Invoice.status == validate_enum(status, InvoiceStatus, "status")
            )
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": Invoice.created_at, "total": Invoice.total},
        )
        items = list(apply_pagination(query, limit, offset).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: InvoiceUpdate) -> Invoice:
        item = db.get(Invoice, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Invoice not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", Invoice.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Invoice, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Invoice not found")
        item.is_active = False
        db.commit()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Invoice.__name__, item.id)


class InvoiceItems(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: InvoiceItemCreate) -> InvoiceItem:
        if not db.get(Invoice, coerce_uuid(payload.invoice_id)):
            raise HTTPException(status_code=404, detail="Invoice not found")
        if payload.price_id and not db.get(Price, coerce_uuid(payload.price_id)):
            raise HTTPException(status_code=404, detail="Price not found")
        if payload.subscription_item_id and not db.get(
            SubscriptionItem, coerce_uuid(payload.subscription_item_id)
        ):
            raise HTTPException(status_code=404, detail="Subscription item not found")
        item = InvoiceItem(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created InvoiceItem: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> InvoiceItem:
        item = db.get(InvoiceItem, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Invoice item not found")
        return item

    @staticmethod
    def list(
        db: Session,
        invoice_id: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[InvoiceItem], int]:
        query = db.query(InvoiceItem)
        if invoice_id:
            query = query.filter(InvoiceItem.invoice_id == coerce_uuid(invoice_id))
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": InvoiceItem.created_at},
        )
        items = list(apply_pagination(query, limit, offset).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: InvoiceItemUpdate) -> InvoiceItem:
        item = db.get(InvoiceItem, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Invoice item not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", InvoiceItem.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(InvoiceItem, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Invoice item not found")
        db.delete(item)
        db.commit()
        logger.info("Deleted %s: %s", InvoiceItem.__name__, item_id)


invoices = Invoices()
invoice_items = InvoiceItems()
