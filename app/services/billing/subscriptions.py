import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import (
    Customer,
    Price,
    Subscription,
    SubscriptionItem,
    SubscriptionStatus,
    UsageRecord,
)
from app.schemas.billing import (
    SubscriptionCreate,
    SubscriptionItemCreate,
    SubscriptionItemUpdate,
    SubscriptionUpdate,
    UsageRecordCreate,
)
from app.services.common import coerce_uuid
from app.services.query_utils import apply_ordering, apply_pagination, validate_enum
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


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
        query = db.query(Subscription)
        if customer_id:
            query = query.filter(Subscription.customer_id == coerce_uuid(customer_id))
        if status:
            query = query.filter(
                Subscription.status
                == validate_enum(status, SubscriptionStatus, "status")
            )
        if is_active is not None:
            query = query.filter(Subscription.is_active == is_active)
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": Subscription.created_at},
        )
        items = list(apply_pagination(query, limit, offset).all())
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
        query = db.query(SubscriptionItem)
        if subscription_id:
            query = query.filter(
                SubscriptionItem.subscription_id == coerce_uuid(subscription_id)
            )
        if price_id:
            query = query.filter(SubscriptionItem.price_id == coerce_uuid(price_id))
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": SubscriptionItem.created_at},
        )
        items = list(apply_pagination(query, limit, offset).all())
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


class UsageRecords(ListResponseMixin):
    @staticmethod
    def create(db: Session, payload: UsageRecordCreate) -> UsageRecord:
        if not db.get(SubscriptionItem, coerce_uuid(payload.subscription_item_id)):
            raise HTTPException(status_code=404, detail="Subscription item not found")
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
        query = db.query(UsageRecord)
        if subscription_item_id:
            query = query.filter(
                UsageRecord.subscription_item_id == coerce_uuid(subscription_item_id)
            )
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {
                "created_at": UsageRecord.created_at,
                "recorded_at": UsageRecord.recorded_at,
            },
        )
        items = list(apply_pagination(query, limit, offset).all())
        return items, total


subscriptions = Subscriptions()
subscription_items = SubscriptionItems()
usage_records = UsageRecords()
