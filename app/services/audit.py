import logging

from fastapi import Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditActorType, AuditEvent
from app.schemas.audit import AuditEventCreate
from app.services.common import coerce_uuid
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class AuditEventNotFoundError(ValueError):
    pass


class AuditEvents(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "occurred_at": AuditEvent.occurred_at,
            "action": AuditEvent.action,
            "entity_type": AuditEvent.entity_type,
            "status_code": AuditEvent.status_code,
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
    def parse_actor_type(value: str | None) -> AuditActorType | None:
        if value is None:
            return None
        try:
            return AuditActorType(value)
        except ValueError as exc:
            allowed = ", ".join(sorted(a.value for a in AuditActorType))
            raise ValueError(f"Invalid actor_type. Allowed: {allowed}") from exc

    @staticmethod
    def create(db: Session, payload: AuditEventCreate):
        data = payload.model_dump()
        if payload.occurred_at is None:
            data.pop("occurred_at", None)
        event = AuditEvent(**data)
        db.add(event)
        db.flush()
        db.refresh(event)
        return event

    @staticmethod
    def get(db: Session, event_id: str):
        event = db.get(AuditEvent, coerce_uuid(event_id))
        if not event:
            raise AuditEventNotFoundError("Audit event not found")
        return event

    @staticmethod
    def list(
        db: Session,
        actor_id: str | None,
        actor_type: AuditActorType | None,
        action: str | None,
        entity_type: str | None,
        request_id: str | None,
        is_success: bool | None,
        status_code: int | None,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(AuditEvent)
        if actor_id:
            stmt = stmt.where(AuditEvent.actor_id == actor_id)
        if actor_type:
            stmt = stmt.where(AuditEvent.actor_type == actor_type)
        if action:
            stmt = stmt.where(AuditEvent.action == action)
        if entity_type:
            stmt = stmt.where(AuditEvent.entity_type == entity_type)
        if request_id:
            stmt = stmt.where(AuditEvent.request_id == request_id)
        if is_success is not None:
            stmt = stmt.where(AuditEvent.is_success == is_success)
        if status_code is not None:
            stmt = stmt.where(AuditEvent.status_code == status_code)
        if is_active is None:
            stmt = stmt.where(AuditEvent.is_active.is_(True))
        else:
            stmt = stmt.where(AuditEvent.is_active == is_active)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0

        stmt = AuditEvents._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def log_request(db: Session, request: Request, response: Response):
        actor_type = request.headers.get("x-actor-type", AuditActorType.system.value)
        actor_id = request.headers.get("x-actor-id")
        request_id = request.headers.get("x-request-id")
        entity_id = request.headers.get("x-entity-id")
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        try:
            resolved_actor_type = AuditActorType(actor_type)
        except ValueError:
            resolved_actor_type = AuditActorType.system
        try:
            query_params = dict(request.query_params)
        except KeyError:
            query_params = {}
        payload = AuditEventCreate(
            actor_type=resolved_actor_type,
            actor_id=actor_id,
            action=request.method,
            entity_type=request.url.path,
            entity_id=entity_id,
            status_code=response.status_code,
            is_success=response.status_code < 400,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            metadata_={
                "path": request.url.path,
                "query": query_params,
            },
        )
        event = AuditEvent(**payload.model_dump())
        db.add(event)
        db.flush()

    @staticmethod
    def delete(db: Session, event_id: str):
        event = db.get(AuditEvent, coerce_uuid(event_id))
        if not event:
            raise AuditEventNotFoundError("Audit event not found")
        event.is_active = False
        db.flush()


audit_events = AuditEvents()
