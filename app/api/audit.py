from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_audit_auth
from app.schemas.audit import AuditEventRead
from app.schemas.common import ListResponse
from app.services import audit as audit_service

router = APIRouter(
    prefix="/audit-events",
    tags=["audit-events"],
    dependencies=[Depends(require_audit_auth)],
)


@router.get("/{event_id}", response_model=AuditEventRead)
def get_audit_event(event_id: str, db: Session = Depends(get_db)):
    try:
        return audit_service.AuditEvents(db).get(event_id)
    except audit_service.AuditEventNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=ListResponse[AuditEventRead])
def list_audit_events(
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    request_id: str | None = None,
    is_success: bool | None = None,
    status_code: int | None = None,
    is_active: bool | None = None,
    order_by: str = Query(default="occurred_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        resolved_actor_type = audit_service.AuditEvents.parse_actor_type(actor_type)
        return audit_service.AuditEvents(db).list_response(
            actor_id,
            resolved_actor_type,
            action,
            entity_type,
            request_id,
            is_success,
            status_code,
            is_active,
            order_by,
            order_dir,
            limit,
            offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_audit_event(event_id: str, db: Session = Depends(get_db)):
    try:
        audit_service.AuditEvents(db).delete(event_id)
        db.commit()
    except audit_service.AuditEventNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
