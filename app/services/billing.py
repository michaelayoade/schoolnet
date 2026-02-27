import logging

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.billing import (
    Coupon,
    Customer,
    Discount,
    Entitlement,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    PaymentIntent,
    PaymentIntentStatus,
    PaymentMethod,
    PaymentMethodType,
    Price,
    PriceType,
    Product,
    Subscription,
    SubscriptionItem,
    SubscriptionStatus,
    UsageRecord,
    WebhookEvent,
    WebhookEventStatus,
)
from app.schemas.billing import (
    CouponCreate,
    CouponUpdate,
    CustomerCreate,
    CustomerUpdate,
    DiscountCreate,
    EntitlementCreate,
    EntitlementUpdate,
    InvoiceCreate,
    InvoiceItemCreate,
    InvoiceItemUpdate,
    InvoiceUpdate,
    PaymentIntentCreate,
    PaymentIntentUpdate,
    PaymentMethodCreate,
    PaymentMethodUpdate,
    PriceCreate,
    PriceUpdate,
    ProductCreate,
    ProductUpdate,
    SubscriptionCreate,
    SubscriptionItemCreate,
    SubscriptionItemUpdate,
    SubscriptionUpdate,
    UsageRecordCreate,
    WebhookEventCreate,
    WebhookEventUpdate,
)
from app.services.common import coerce_uuid
from app.services.query_utils import apply_ordering, apply_pagination, validate_enum
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


# ── Products ─────────────────────────────────────────────


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
        stmt = select(Product)
        count_stmt = select(func.count()).select_from(Product)
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
            count_stmt = count_stmt.where(Product.is_active == is_active)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": Product.created_at, "name": Product.name},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
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


# ── Prices ───────────────────────────────────────────────


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
        stmt = select(Price)
        count_stmt = select(func.count()).select_from(Price)
        if product_id:
            condition = Price.product_id == coerce_uuid(product_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if type:
            condition = Price.type == validate_enum(type, PriceType, "type")
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if currency:
            condition = Price.currency == currency
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if is_active is not None:
            condition = Price.is_active == is_active
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": Price.created_at, "unit_amount": Price.unit_amount},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
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


# ── Customers ────────────────────────────────────────────


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
        stmt = select(Customer)
        count_stmt = select(func.count()).select_from(Customer)
        if person_id:
            condition = Customer.person_id == coerce_uuid(person_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if email:
            condition = Customer.email.ilike(f"%{email}%")
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if is_active is not None:
            condition = Customer.is_active == is_active
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": Customer.created_at, "name": Customer.name},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
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


# ── Subscriptions ────────────────────────────────────────


class Subscriptions(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: SubscriptionCreate) -> Subscription:
        if not db.get(Customer, coerce_uuid(payload.customer_id)):
            raise HTTPException(status_code=404, detail="Customer not found")
        item = Subscription(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created Subscription: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Subscription:
        item = db.get(Subscription, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return item

    @staticmethod
    def list(
        db: Session,
        customer_id: str | None,
        status: str | None,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Subscription], int]:
        stmt = select(Subscription)
        count_stmt = select(func.count()).select_from(Subscription)
        if customer_id:
            condition = Subscription.customer_id == coerce_uuid(customer_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            condition = Subscription.status == validate_enum(
                status, SubscriptionStatus, "status"
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if is_active is not None:
            condition = Subscription.is_active == is_active
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": Subscription.created_at},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: SubscriptionUpdate) -> Subscription:
        item = db.get(Subscription, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Subscription not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", Subscription.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Subscription, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Subscription not found")
        item.is_active = False
        db.commit()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Subscription.__name__, item.id)


# ── Subscription Items ───────────────────────────────────


class SubscriptionItems(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: SubscriptionItemCreate) -> SubscriptionItem:
        if not db.get(Subscription, coerce_uuid(payload.subscription_id)):
            raise HTTPException(status_code=404, detail="Subscription not found")
        if not db.get(Price, coerce_uuid(payload.price_id)):
            raise HTTPException(status_code=404, detail="Price not found")
        item = SubscriptionItem(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created SubscriptionItem: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> SubscriptionItem:
        item = db.get(SubscriptionItem, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Subscription item not found")
        return item

    @staticmethod
    def list(
        db: Session,
        subscription_id: str | None,
        price_id: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[SubscriptionItem], int]:
        stmt = select(SubscriptionItem)
        count_stmt = select(func.count()).select_from(SubscriptionItem)
        if subscription_id:
            condition = SubscriptionItem.subscription_id == coerce_uuid(subscription_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if price_id:
            condition = SubscriptionItem.price_id == coerce_uuid(price_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": SubscriptionItem.created_at},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
        return items, total

    @staticmethod
    def update(
        db: Session, item_id: str, payload: SubscriptionItemUpdate
    ) -> SubscriptionItem:
        item = db.get(SubscriptionItem, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Subscription item not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", SubscriptionItem.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(SubscriptionItem, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Subscription item not found")
        item.is_active = False
        db.commit()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", SubscriptionItem.__name__, item.id)


# ── Invoices ─────────────────────────────────────────────


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
        stmt = select(Invoice)
        count_stmt = select(func.count()).select_from(Invoice)
        if customer_id:
            condition = Invoice.customer_id == coerce_uuid(customer_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if subscription_id:
            condition = Invoice.subscription_id == coerce_uuid(subscription_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            condition = Invoice.status == validate_enum(status, InvoiceStatus, "status")
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": Invoice.created_at, "total": Invoice.total},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
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


# ── Invoice Items ────────────────────────────────────────


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
            raise HTTPException(
                status_code=404, detail="Subscription item not found"
            )
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
        stmt = select(InvoiceItem)
        count_stmt = select(func.count()).select_from(InvoiceItem)
        if invoice_id:
            condition = InvoiceItem.invoice_id == coerce_uuid(invoice_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": InvoiceItem.created_at},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
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


# ── Payment Methods ──────────────────────────────────────


class PaymentMethods(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: PaymentMethodCreate) -> PaymentMethod:
        if not db.get(Customer, coerce_uuid(payload.customer_id)):
            raise HTTPException(status_code=404, detail="Customer not found")
        item = PaymentMethod(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created PaymentMethod: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> PaymentMethod:
        item = db.get(PaymentMethod, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Payment method not found")
        return item

    @staticmethod
    def list(
        db: Session,
        customer_id: str | None,
        type: str | None,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[PaymentMethod], int]:
        stmt = select(PaymentMethod)
        count_stmt = select(func.count()).select_from(PaymentMethod)
        if customer_id:
            condition = PaymentMethod.customer_id == coerce_uuid(customer_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if type:
            condition = PaymentMethod.type == validate_enum(
                type, PaymentMethodType, "type"
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if is_active is not None:
            condition = PaymentMethod.is_active == is_active
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": PaymentMethod.created_at},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
        return items, total

    @staticmethod
    def update(
        db: Session, item_id: str, payload: PaymentMethodUpdate
    ) -> PaymentMethod:
        item = db.get(PaymentMethod, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Payment method not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", PaymentMethod.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(PaymentMethod, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Payment method not found")
        item.is_active = False
        db.commit()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", PaymentMethod.__name__, item.id)


# ── Payment Intents ──────────────────────────────────────


class PaymentIntents(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: PaymentIntentCreate) -> PaymentIntent:
        if not db.get(Customer, coerce_uuid(payload.customer_id)):
            raise HTTPException(status_code=404, detail="Customer not found")
        if payload.invoice_id and not db.get(
            Invoice, coerce_uuid(payload.invoice_id)
        ):
            raise HTTPException(status_code=404, detail="Invoice not found")
        if payload.payment_method_id and not db.get(
            PaymentMethod, coerce_uuid(payload.payment_method_id)
        ):
            raise HTTPException(status_code=404, detail="Payment method not found")
        item = PaymentIntent(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created PaymentIntent: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> PaymentIntent:
        item = db.get(PaymentIntent, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Payment intent not found")
        return item

    @staticmethod
    def list(
        db: Session,
        customer_id: str | None,
        invoice_id: str | None,
        status: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[PaymentIntent], int]:
        stmt = select(PaymentIntent)
        count_stmt = select(func.count()).select_from(PaymentIntent)
        if customer_id:
            condition = PaymentIntent.customer_id == coerce_uuid(customer_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if invoice_id:
            condition = PaymentIntent.invoice_id == coerce_uuid(invoice_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            condition = PaymentIntent.status == validate_enum(
                status, PaymentIntentStatus, "status"
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": PaymentIntent.created_at},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
        return items, total

    @staticmethod
    def update(
        db: Session, item_id: str, payload: PaymentIntentUpdate
    ) -> PaymentIntent:
        item = db.get(PaymentIntent, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Payment intent not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", PaymentIntent.__name__, item.id)
        return item


# ── Usage Records ────────────────────────────────────────


class UsageRecords(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: UsageRecordCreate) -> UsageRecord:
        if not db.get(SubscriptionItem, coerce_uuid(payload.subscription_item_id)):
            raise HTTPException(
                status_code=404, detail="Subscription item not found"
            )
        item = UsageRecord(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created UsageRecord: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> UsageRecord:
        item = db.get(UsageRecord, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Usage record not found")
        return item

    @staticmethod
    def list(
        db: Session,
        subscription_item_id: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[UsageRecord], int]:
        stmt = select(UsageRecord)
        count_stmt = select(func.count()).select_from(UsageRecord)
        if subscription_item_id:
            condition = UsageRecord.subscription_item_id == coerce_uuid(
                subscription_item_id
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {
                "created_at": UsageRecord.created_at,
                "recorded_at": UsageRecord.recorded_at,
            },
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
        return items, total


# ── Coupons ──────────────────────────────────────────────


class Coupons(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: CouponCreate) -> Coupon:
        item = Coupon(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created Coupon: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Coupon:
        item = db.get(Coupon, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Coupon not found")
        return item

    @staticmethod
    def list(
        db: Session,
        valid: bool | None,
        code: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Coupon], int]:
        stmt = select(Coupon)
        count_stmt = select(func.count()).select_from(Coupon)
        if valid is not None:
            condition = Coupon.valid == valid
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if code:
            condition = Coupon.code == code
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": Coupon.created_at, "name": Coupon.name},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: CouponUpdate) -> Coupon:
        item = db.get(Coupon, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Coupon not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", Coupon.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Coupon, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Coupon not found")
        item.valid = False
        db.commit()
        db.refresh(item)
        logger.info("Soft-deleted Coupon: %s", item.id)


# ── Discounts ────────────────────────────────────────────


class Discounts(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: DiscountCreate) -> Discount:
        if not db.get(Coupon, coerce_uuid(payload.coupon_id)):
            raise HTTPException(status_code=404, detail="Coupon not found")
        if payload.customer_id and not db.get(
            Customer, coerce_uuid(payload.customer_id)
        ):
            raise HTTPException(status_code=404, detail="Customer not found")
        if payload.subscription_id and not db.get(
            Subscription, coerce_uuid(payload.subscription_id)
        ):
            raise HTTPException(status_code=404, detail="Subscription not found")
        item = Discount(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created Discount: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Discount:
        item = db.get(Discount, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Discount not found")
        return item

    @staticmethod
    def list(
        db: Session,
        customer_id: str | None,
        subscription_id: str | None,
        coupon_id: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Discount], int]:
        stmt = select(Discount)
        count_stmt = select(func.count()).select_from(Discount)
        if customer_id:
            condition = Discount.customer_id == coerce_uuid(customer_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if subscription_id:
            condition = Discount.subscription_id == coerce_uuid(subscription_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if coupon_id:
            condition = Discount.coupon_id == coerce_uuid(coupon_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": Discount.created_at},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
        return items, total

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Discount, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Discount not found")
        db.delete(item)
        db.commit()
        logger.info("Deleted %s: %s", Discount.__name__, item_id)


# ── Entitlements ─────────────────────────────────────────


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
        stmt = select(Entitlement)
        count_stmt = select(func.count()).select_from(Entitlement)
        if product_id:
            condition = Entitlement.product_id == coerce_uuid(product_id)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if feature_key:
            condition = Entitlement.feature_key == feature_key
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": Entitlement.created_at},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
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


# ── Webhook Events ───────────────────────────────────────


class WebhookEvents(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: WebhookEventCreate) -> WebhookEvent:
        item = WebhookEvent(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Created WebhookEvent: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> WebhookEvent:
        item = db.get(WebhookEvent, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Webhook event not found")
        return item

    @staticmethod
    def list(
        db: Session,
        provider: str | None,
        event_type: str | None,
        status: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> tuple[list[WebhookEvent], int]:
        stmt = select(WebhookEvent)
        count_stmt = select(func.count()).select_from(WebhookEvent)
        if provider:
            condition = WebhookEvent.provider == provider
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if event_type:
            condition = WebhookEvent.event_type == event_type
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            condition = WebhookEvent.status == validate_enum(
                status, WebhookEventStatus, "status"
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        stmt = apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": WebhookEvent.created_at},
        )
        items = list(db.scalars(apply_pagination(stmt, limit, offset)).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: WebhookEventUpdate) -> WebhookEvent:
        item = db.get(WebhookEvent, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Webhook event not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        logger.info("Updated %s: %s", WebhookEvent.__name__, item.id)
        return item


# ── Singletons ───────────────────────────────────────────

products = Products()
prices = Prices()
customers = Customers()
subscriptions = Subscriptions()
subscription_items = SubscriptionItems()
invoices = Invoices()
invoice_items = InvoiceItems()
payment_methods = PaymentMethods()
payment_intents = PaymentIntents()
usage_records = UsageRecords()
coupons = Coupons()
discounts = Discounts()
entitlements = Entitlements()
webhook_events = WebhookEvents()
