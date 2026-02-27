import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import (
    Coupon,
    Customer,
    Discount,
    Invoice,
    PaymentIntent,
    PaymentIntentStatus,
    PaymentMethod,
    PaymentMethodType,
    Subscription,
)
from app.schemas.billing import (
    CouponCreate,
    CouponUpdate,
    DiscountCreate,
    PaymentIntentCreate,
    PaymentIntentUpdate,
    PaymentMethodCreate,
    PaymentMethodUpdate,
)
from app.services.common import coerce_uuid
from app.services.query_utils import apply_ordering, apply_pagination, validate_enum
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


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
        query = db.query(PaymentMethod)
        if customer_id:
            query = query.filter(PaymentMethod.customer_id == coerce_uuid(customer_id))
        if type:
            query = query.filter(
                PaymentMethod.type == validate_enum(type, PaymentMethodType, "type")
            )
        if is_active is not None:
            query = query.filter(PaymentMethod.is_active == is_active)
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": PaymentMethod.created_at},
        )
        items = list(apply_pagination(query, limit, offset).all())
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


class PaymentIntents(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: PaymentIntentCreate) -> PaymentIntent:
        if not db.get(Customer, coerce_uuid(payload.customer_id)):
            raise HTTPException(status_code=404, detail="Customer not found")
        if payload.invoice_id and not db.get(Invoice, coerce_uuid(payload.invoice_id)):
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
        query = db.query(PaymentIntent)
        if customer_id:
            query = query.filter(PaymentIntent.customer_id == coerce_uuid(customer_id))
        if invoice_id:
            query = query.filter(PaymentIntent.invoice_id == coerce_uuid(invoice_id))
        if status:
            query = query.filter(
                PaymentIntent.status
                == validate_enum(status, PaymentIntentStatus, "status")
            )
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": PaymentIntent.created_at},
        )
        items = list(apply_pagination(query, limit, offset).all())
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
        query = db.query(Coupon)
        if valid is not None:
            query = query.filter(Coupon.valid == valid)
        if code:
            query = query.filter(Coupon.code == code)
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": Coupon.created_at, "name": Coupon.name},
        )
        items = list(apply_pagination(query, limit, offset).all())
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


class Discounts(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: DiscountCreate) -> Discount:
        if not db.get(Coupon, coerce_uuid(payload.coupon_id)):
            raise HTTPException(status_code=404, detail="Coupon not found")
        if payload.customer_id and not db.get(Customer, coerce_uuid(payload.customer_id)):
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
        query = db.query(Discount)
        if customer_id:
            query = query.filter(Discount.customer_id == coerce_uuid(customer_id))
        if subscription_id:
            query = query.filter(Discount.subscription_id == coerce_uuid(subscription_id))
        if coupon_id:
            query = query.filter(Discount.coupon_id == coerce_uuid(coupon_id))
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": Discount.created_at},
        )
        items = list(apply_pagination(query, limit, offset).all())
        return items, total

    @staticmethod
    def delete(db: Session, item_id: str) -> None:
        item = db.get(Discount, coerce_uuid(item_id))
        if not item:
            raise HTTPException(status_code=404, detail="Discount not found")
        db.delete(item)
        db.commit()
        logger.info("Deleted %s: %s", Discount.__name__, item_id)


payment_methods = PaymentMethods()
payment_intents = PaymentIntents()
coupons = Coupons()
discounts = Discounts()
