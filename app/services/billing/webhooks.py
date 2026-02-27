import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import WebhookEvent, WebhookEventStatus
from app.schemas.billing import WebhookEventCreate, WebhookEventUpdate
from app.services.common import coerce_uuid
from app.services.query_utils import apply_ordering, apply_pagination, validate_enum
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


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
        query = db.query(WebhookEvent)
        if provider:
            query = query.filter(WebhookEvent.provider == provider)
        if event_type:
            query = query.filter(WebhookEvent.event_type == event_type)
        if status:
            query = query.filter(
                WebhookEvent.status
                == validate_enum(status, WebhookEventStatus, "status")
            )
        total = query.count()
        query = apply_ordering(
            query,
            order_by,
            order_dir,
            {"created_at": WebhookEvent.created_at},
        )
        items = list(apply_pagination(query, limit, offset).all())
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


webhook_events = WebhookEvents()
