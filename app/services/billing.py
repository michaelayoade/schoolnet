import logging
from enum import Enum

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
from app.services.common import coerce_uuid, escape_like
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class ProductNotFoundError(ValueError):
    pass


class PriceNotFoundError(ValueError):
    pass


class CustomerNotFoundError(ValueError):
    pass


class SubscriptionNotFoundError(ValueError):
    pass


class SubscriptionItemNotFoundError(ValueError):
    pass


class InvoiceNotFoundError(ValueError):
    pass


class InvoiceItemNotFoundError(ValueError):
    pass


class PaymentMethodNotFoundError(ValueError):
    pass


class PaymentIntentNotFoundError(ValueError):
    pass


class UsageRecordNotFoundError(ValueError):
    pass


class CouponNotFoundError(ValueError):
    pass


class DiscountNotFoundError(ValueError):
    pass


class EntitlementNotFoundError(ValueError):
    pass


class WebhookEventNotFoundError(ValueError):
    pass


def _parse_enum(value: str | None, enum_cls: type[Enum], label: str):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {label}") from exc


# ── Products ─────────────────────────────────────────────


class Products(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Product.created_at,
            "name": Product.name,
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
    def create(db: Session, payload: ProductCreate) -> Product:
        item = Product(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created Product: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Product:
        item = db.get(Product, coerce_uuid(item_id))
        if not item:
            raise ProductNotFoundError("Product not found")
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
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = Products._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: ProductUpdate) -> Product:
        item = db.get(Product, coerce_uuid(item_id))
        if not item:
            raise ProductNotFoundError("Product not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", Product.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Product, coerce_uuid(item_id))
        if not item:
            raise ProductNotFoundError("Product not found")
        item.is_active = False
        db.flush()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Product.__name__, item.id)


# ── Prices ───────────────────────────────────────────────


class Prices(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Price.created_at,
            "unit_amount": Price.unit_amount,
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
    def create(db: Session, payload: PriceCreate) -> Price:
        if not db.get(Product, coerce_uuid(payload.product_id)):
            raise ProductNotFoundError("Product not found")
        item = Price(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created Price: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Price:
        item = db.get(Price, coerce_uuid(item_id))
        if not item:
            raise PriceNotFoundError("Price not found")
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
        if product_id:
            stmt = stmt.where(Price.product_id == coerce_uuid(product_id))
        if type:
            stmt = stmt.where(Price.type == _parse_enum(type, PriceType, "type"))
        if currency:
            stmt = stmt.where(Price.currency == currency)
        if is_active is not None:
            stmt = stmt.where(Price.is_active == is_active)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = Prices._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: PriceUpdate) -> Price:
        item = db.get(Price, coerce_uuid(item_id))
        if not item:
            raise PriceNotFoundError("Price not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", Price.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Price, coerce_uuid(item_id))
        if not item:
            raise PriceNotFoundError("Price not found")
        item.is_active = False
        db.flush()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Price.__name__, item.id)


# ── Customers ────────────────────────────────────────────


class Customers(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Customer.created_at,
            "name": Customer.name,
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
    def create(db: Session, payload: CustomerCreate) -> Customer:
        item = Customer(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created Customer: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Customer:
        item = db.get(Customer, coerce_uuid(item_id))
        if not item:
            raise CustomerNotFoundError("Customer not found")
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
        if person_id:
            stmt = stmt.where(Customer.person_id == coerce_uuid(person_id))
        if email:
            stmt = stmt.where(Customer.email.ilike(f"%{escape_like(email)}%"))
        if is_active is not None:
            stmt = stmt.where(Customer.is_active == is_active)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = Customers._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: CustomerUpdate) -> Customer:
        item = db.get(Customer, coerce_uuid(item_id))
        if not item:
            raise CustomerNotFoundError("Customer not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", Customer.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Customer, coerce_uuid(item_id))
        if not item:
            raise CustomerNotFoundError("Customer not found")
        item.is_active = False
        db.flush()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Customer.__name__, item.id)


# ── Subscriptions ────────────────────────────────────────


class Subscriptions(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Subscription.created_at,
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
    def create(db: Session, payload: SubscriptionCreate) -> Subscription:
        if not db.get(Customer, coerce_uuid(payload.customer_id)):
            raise CustomerNotFoundError("Customer not found")
        item = Subscription(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created Subscription: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Subscription:
        item = db.get(Subscription, coerce_uuid(item_id))
        if not item:
            raise SubscriptionNotFoundError("Subscription not found")
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
        if customer_id:
            stmt = stmt.where(Subscription.customer_id == coerce_uuid(customer_id))
        if status:
            stmt = stmt.where(
                Subscription.status
                == _parse_enum(status, SubscriptionStatus, "status")
            )
        if is_active is not None:
            stmt = stmt.where(Subscription.is_active == is_active)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = Subscriptions._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: SubscriptionUpdate) -> Subscription:
        item = db.get(Subscription, coerce_uuid(item_id))
        if not item:
            raise SubscriptionNotFoundError("Subscription not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", Subscription.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Subscription, coerce_uuid(item_id))
        if not item:
            raise SubscriptionNotFoundError("Subscription not found")
        item.is_active = False
        db.flush()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Subscription.__name__, item.id)


# ── Subscription Items ───────────────────────────────────


class SubscriptionItems(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": SubscriptionItem.created_at,
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
    def create(db: Session, payload: SubscriptionItemCreate) -> SubscriptionItem:
        if not db.get(Subscription, coerce_uuid(payload.subscription_id)):
            raise SubscriptionNotFoundError("Subscription not found")
        if not db.get(Price, coerce_uuid(payload.price_id)):
            raise PriceNotFoundError("Price not found")
        item = SubscriptionItem(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created SubscriptionItem: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> SubscriptionItem:
        item = db.get(SubscriptionItem, coerce_uuid(item_id))
        if not item:
            raise SubscriptionItemNotFoundError("Subscription item not found")
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
        if subscription_id:
            stmt = stmt.where(
                SubscriptionItem.subscription_id == coerce_uuid(subscription_id)
            )
        if price_id:
            stmt = stmt.where(SubscriptionItem.price_id == coerce_uuid(price_id))
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = SubscriptionItems._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(
        db: Session, item_id: str, payload: SubscriptionItemUpdate
    ) -> SubscriptionItem:
        item = db.get(SubscriptionItem, coerce_uuid(item_id))
        if not item:
            raise SubscriptionItemNotFoundError("Subscription item not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", SubscriptionItem.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(SubscriptionItem, coerce_uuid(item_id))
        if not item:
            raise SubscriptionItemNotFoundError("Subscription item not found")
        item.is_active = False
        db.flush()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", SubscriptionItem.__name__, item.id)


# ── Invoices ─────────────────────────────────────────────


class Invoices(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Invoice.created_at,
            "total": Invoice.total,
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
    def create(db: Session, payload: InvoiceCreate) -> Invoice:
        if not db.get(Customer, coerce_uuid(payload.customer_id)):
            raise CustomerNotFoundError("Customer not found")
        if payload.subscription_id and not db.get(
            Subscription, coerce_uuid(payload.subscription_id)
        ):
            raise SubscriptionNotFoundError("Subscription not found")
        item = Invoice(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created Invoice: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Invoice:
        item = db.get(Invoice, coerce_uuid(item_id))
        if not item:
            raise InvoiceNotFoundError("Invoice not found")
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
        if customer_id:
            stmt = stmt.where(Invoice.customer_id == coerce_uuid(customer_id))
        if subscription_id:
            stmt = stmt.where(
                Invoice.subscription_id == coerce_uuid(subscription_id)
            )
        if status:
            stmt = stmt.where(
                Invoice.status == _parse_enum(status, InvoiceStatus, "status")
            )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = Invoices._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: InvoiceUpdate) -> Invoice:
        item = db.get(Invoice, coerce_uuid(item_id))
        if not item:
            raise InvoiceNotFoundError("Invoice not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", Invoice.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Invoice, coerce_uuid(item_id))
        if not item:
            raise InvoiceNotFoundError("Invoice not found")
        item.is_active = False
        db.flush()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", Invoice.__name__, item.id)


# ── Invoice Items ────────────────────────────────────────


class InvoiceItems(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": InvoiceItem.created_at,
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
    def create(db: Session, payload: InvoiceItemCreate) -> InvoiceItem:
        if not db.get(Invoice, coerce_uuid(payload.invoice_id)):
            raise InvoiceNotFoundError("Invoice not found")
        if payload.price_id and not db.get(Price, coerce_uuid(payload.price_id)):
            raise PriceNotFoundError("Price not found")
        if payload.subscription_item_id and not db.get(
            SubscriptionItem, coerce_uuid(payload.subscription_item_id)
        ):
            raise SubscriptionItemNotFoundError("Subscription item not found")
        item = InvoiceItem(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created InvoiceItem: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> InvoiceItem:
        item = db.get(InvoiceItem, coerce_uuid(item_id))
        if not item:
            raise InvoiceItemNotFoundError("Invoice item not found")
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
        if invoice_id:
            stmt = stmt.where(InvoiceItem.invoice_id == coerce_uuid(invoice_id))
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = InvoiceItems._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: InvoiceItemUpdate) -> InvoiceItem:
        item = db.get(InvoiceItem, coerce_uuid(item_id))
        if not item:
            raise InvoiceItemNotFoundError("Invoice item not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", InvoiceItem.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(InvoiceItem, coerce_uuid(item_id))
        if not item:
            raise InvoiceItemNotFoundError("Invoice item not found")
        db.delete(item)
        db.flush()
        logger.info("Deleted %s: %s", InvoiceItem.__name__, item_id)


# ── Payment Methods ──────────────────────────────────────


class PaymentMethods(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": PaymentMethod.created_at,
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
    def create(db: Session, payload: PaymentMethodCreate) -> PaymentMethod:
        if not db.get(Customer, coerce_uuid(payload.customer_id)):
            raise CustomerNotFoundError("Customer not found")
        item = PaymentMethod(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created PaymentMethod: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> PaymentMethod:
        item = db.get(PaymentMethod, coerce_uuid(item_id))
        if not item:
            raise PaymentMethodNotFoundError("Payment method not found")
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
        if customer_id:
            stmt = stmt.where(PaymentMethod.customer_id == coerce_uuid(customer_id))
        if type:
            stmt = stmt.where(
                PaymentMethod.type == _parse_enum(type, PaymentMethodType, "type")
            )
        if is_active is not None:
            stmt = stmt.where(PaymentMethod.is_active == is_active)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = PaymentMethods._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(
        db: Session, item_id: str, payload: PaymentMethodUpdate
    ) -> PaymentMethod:
        item = db.get(PaymentMethod, coerce_uuid(item_id))
        if not item:
            raise PaymentMethodNotFoundError("Payment method not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", PaymentMethod.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(PaymentMethod, coerce_uuid(item_id))
        if not item:
            raise PaymentMethodNotFoundError("Payment method not found")
        item.is_active = False
        db.flush()
        db.refresh(item)
        logger.info("Soft-deleted %s: %s", PaymentMethod.__name__, item.id)


# ── Payment Intents ──────────────────────────────────────


class PaymentIntents(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": PaymentIntent.created_at,
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
    def create(db: Session, payload: PaymentIntentCreate) -> PaymentIntent:
        if not db.get(Customer, coerce_uuid(payload.customer_id)):
            raise CustomerNotFoundError("Customer not found")
        if payload.invoice_id and not db.get(Invoice, coerce_uuid(payload.invoice_id)):
            raise InvoiceNotFoundError("Invoice not found")
        if payload.payment_method_id and not db.get(
            PaymentMethod, coerce_uuid(payload.payment_method_id)
        ):
            raise PaymentMethodNotFoundError("Payment method not found")
        item = PaymentIntent(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created PaymentIntent: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> PaymentIntent:
        item = db.get(PaymentIntent, coerce_uuid(item_id))
        if not item:
            raise PaymentIntentNotFoundError("Payment intent not found")
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
        if customer_id:
            stmt = stmt.where(PaymentIntent.customer_id == coerce_uuid(customer_id))
        if invoice_id:
            stmt = stmt.where(PaymentIntent.invoice_id == coerce_uuid(invoice_id))
        if status:
            stmt = stmt.where(
                PaymentIntent.status
                == _parse_enum(status, PaymentIntentStatus, "status")
            )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = PaymentIntents._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(
        db: Session, item_id: str, payload: PaymentIntentUpdate
    ) -> PaymentIntent:
        item = db.get(PaymentIntent, coerce_uuid(item_id))
        if not item:
            raise PaymentIntentNotFoundError("Payment intent not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", PaymentIntent.__name__, item.id)
        return item


# ── Usage Records ────────────────────────────────────────


class UsageRecords(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": UsageRecord.created_at,
            "recorded_at": UsageRecord.recorded_at,
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
    def create(db: Session, payload: UsageRecordCreate) -> UsageRecord:
        if not db.get(SubscriptionItem, coerce_uuid(payload.subscription_item_id)):
            raise SubscriptionItemNotFoundError("Subscription item not found")
        item = UsageRecord(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created UsageRecord: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> UsageRecord:
        item = db.get(UsageRecord, coerce_uuid(item_id))
        if not item:
            raise UsageRecordNotFoundError("Usage record not found")
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
        if subscription_item_id:
            stmt = stmt.where(
                UsageRecord.subscription_item_id == coerce_uuid(subscription_item_id)
            )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = UsageRecords._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total


# ── Coupons ──────────────────────────────────────────────


class Coupons(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Coupon.created_at,
            "name": Coupon.name,
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
    def create(db: Session, payload: CouponCreate) -> Coupon:
        item = Coupon(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created Coupon: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Coupon:
        item = db.get(Coupon, coerce_uuid(item_id))
        if not item:
            raise CouponNotFoundError("Coupon not found")
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
        if valid is not None:
            stmt = stmt.where(Coupon.valid == valid)
        if code:
            stmt = stmt.where(Coupon.code == code)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = Coupons._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: CouponUpdate) -> Coupon:
        item = db.get(Coupon, coerce_uuid(item_id))
        if not item:
            raise CouponNotFoundError("Coupon not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", Coupon.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Coupon, coerce_uuid(item_id))
        if not item:
            raise CouponNotFoundError("Coupon not found")
        item.valid = False
        db.flush()
        db.refresh(item)
        logger.info("Soft-deleted Coupon: %s", item.id)


# ── Discounts ────────────────────────────────────────────


class Discounts(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Discount.created_at,
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
    def create(db: Session, payload: DiscountCreate) -> Discount:
        if not db.get(Coupon, coerce_uuid(payload.coupon_id)):
            raise CouponNotFoundError("Coupon not found")
        if payload.customer_id and not db.get(
            Customer, coerce_uuid(payload.customer_id)
        ):
            raise CustomerNotFoundError("Customer not found")
        if payload.subscription_id and not db.get(
            Subscription, coerce_uuid(payload.subscription_id)
        ):
            raise SubscriptionNotFoundError("Subscription not found")
        item = Discount(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created Discount: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Discount:
        item = db.get(Discount, coerce_uuid(item_id))
        if not item:
            raise DiscountNotFoundError("Discount not found")
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
        if customer_id:
            stmt = stmt.where(Discount.customer_id == coerce_uuid(customer_id))
        if subscription_id:
            stmt = stmt.where(
                Discount.subscription_id == coerce_uuid(subscription_id)
            )
        if coupon_id:
            stmt = stmt.where(Discount.coupon_id == coerce_uuid(coupon_id))
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = Discounts._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Discount, coerce_uuid(item_id))
        if not item:
            raise DiscountNotFoundError("Discount not found")
        db.delete(item)
        db.flush()
        logger.info("Deleted %s: %s", Discount.__name__, item_id)


# ── Entitlements ─────────────────────────────────────────


class Entitlements(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Entitlement.created_at,
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
    def create(db: Session, payload: EntitlementCreate) -> Entitlement:
        if not db.get(Product, coerce_uuid(payload.product_id)):
            raise ProductNotFoundError("Product not found")
        item = Entitlement(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created Entitlement: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> Entitlement:
        item = db.get(Entitlement, coerce_uuid(item_id))
        if not item:
            raise EntitlementNotFoundError("Entitlement not found")
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
        if product_id:
            stmt = stmt.where(Entitlement.product_id == coerce_uuid(product_id))
        if feature_key:
            stmt = stmt.where(Entitlement.feature_key == feature_key)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = Entitlements._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: EntitlementUpdate) -> Entitlement:
        item = db.get(Entitlement, coerce_uuid(item_id))
        if not item:
            raise EntitlementNotFoundError("Entitlement not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
        db.refresh(item)
        logger.info("Updated %s: %s", Entitlement.__name__, item.id)
        return item

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Entitlement, coerce_uuid(item_id))
        if not item:
            raise EntitlementNotFoundError("Entitlement not found")
        db.delete(item)
        db.flush()
        logger.info("Deleted %s: %s", Entitlement.__name__, item_id)


# ── Webhook Events ───────────────────────────────────────


class WebhookEvents(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": WebhookEvent.created_at,
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
    def create(db: Session, payload: WebhookEventCreate) -> WebhookEvent:
        item = WebhookEvent(**payload.model_dump())
        db.add(item)
        db.flush()
        db.refresh(item)
        logger.info("Created WebhookEvent: %s", item.id)
        return item

    @staticmethod
    def get(db: Session, item_id: str) -> WebhookEvent:
        item = db.get(WebhookEvent, coerce_uuid(item_id))
        if not item:
            raise WebhookEventNotFoundError("Webhook event not found")
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
        if provider:
            stmt = stmt.where(WebhookEvent.provider == provider)
        if event_type:
            stmt = stmt.where(WebhookEvent.event_type == event_type)
        if status:
            stmt = stmt.where(
                WebhookEvent.status
                == _parse_enum(status, WebhookEventStatus, "status")
            )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0
        stmt = WebhookEvents._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, item_id: str, payload: WebhookEventUpdate) -> WebhookEvent:
        item = db.get(WebhookEvent, coerce_uuid(item_id))
        if not item:
            raise WebhookEventNotFoundError("Webhook event not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        db.flush()
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
