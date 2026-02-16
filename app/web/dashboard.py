"""Admin dashboard with summary stats."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.audit import AuditEvent
from app.models.file_upload import FileUpload, FileUploadStatus
from app.models.notification import Notification
from app.models.person import Person
from app.models.rbac import Role
from app.models.scheduler import ScheduledTask
from app.services.branding_context import load_branding_context
from app.templates import templates
from app.web.deps import require_web_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["web-admin"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_web_auth),
) -> HTMLResponse:
    branding = load_branding_context(db)
    person = auth["person"]

    people_count = db.execute(select(func.count()).select_from(Person)).scalar() or 0
    roles_count = db.execute(select(func.count()).select_from(Role)).scalar() or 0
    tasks_count = db.execute(
        select(func.count()).select_from(ScheduledTask).where(ScheduledTask.enabled.is_(True))
    ).scalar() or 0
    uploads_count = db.execute(
        select(func.count()).select_from(FileUpload).where(
            FileUpload.status == FileUploadStatus.active
        )
    ).scalar() or 0
    audit_count = db.execute(select(func.count()).select_from(AuditEvent)).scalar() or 0
    unread_notifications = db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.recipient_id == person.id,
            Notification.is_read.is_(False),
            Notification.is_active.is_(True),
        )
    ).scalar() or 0

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "page_title": "Dashboard",
            "current_user": person,
            "brand": branding["brand"],
            "org_branding": branding["org_branding"],
            "brand_mark": branding["brand"].get("mark", "A"),
            "stats": {
                "people": people_count,
                "roles": roles_count,
                "tasks": tasks_count,
                "uploads": uploads_count,
                "audit": audit_count,
                "notifications": unread_notifications,
            },
        },
    )
