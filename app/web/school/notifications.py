"""School admin portal — notification routes."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.api.deps import get_db
from app.services.common import require_uuid
from app.services.notification import NotificationService
from app.templates import templates
from app.web.schoolnet_deps import require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/school/notifications", tags=["school-notifications"])


@router.get("")
def list_notifications(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    """List notifications for the school admin."""
    svc = NotificationService(db)
    person_uuid = require_uuid(auth["person_id"])
    notifications = svc.list_for_recipient(person_uuid, limit=50)
    unread_count = svc.unread_count(person_uuid)
    return templates.TemplateResponse(
        "school/notifications/list.html",
        {
            "request": request,
            "auth": auth,
            "notifications": notifications,
            "unread_count": unread_count,
        },
    )


@router.get("/bell")
def notification_bell(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    """HTMX fragment returning bell with unread count."""
    svc = NotificationService(db)
    count = svc.unread_count(require_uuid(auth["person_id"]))
    badge = ""
    if count > 0:
        badge = (
            '<span class="absolute top-0.5 right-0.5 flex h-4 w-4'
            " items-center justify-center rounded-full bg-red-500"
            ' text-[10px] font-bold text-white">'
            f"{count}</span>"
        )
    html = (
        '<a href="/school/notifications" class="relative p-2 rounded-lg'
        " text-slate-600 dark:text-slate-300 hover:bg-slate-100"
        ' dark:hover:bg-slate-700/50">'
        '<svg class="w-5 h-5" fill="none" stroke="currentColor"'
        ' viewBox="0 0 24 24">'
        '<path stroke-linecap="round" stroke-linejoin="round"'
        ' stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0'
        " 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4"
        " 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214"
        ' 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/>'
        "</svg>"
        f"{badge}"
        "</a>"
    )
    return HTMLResponse(content=html)


@router.post("/{notification_id}/read")
def mark_notification_read(
    request: Request,
    notification_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    """Mark a single notification as read."""
    svc = NotificationService(db)
    svc.mark_read(
        require_uuid(notification_id),
        require_uuid(auth["person_id"]),
    )
    db.commit()
    return RedirectResponse(
        url="/school/notifications?success=Notification+marked+as+read",
        status_code=303,
    )


@router.post("/mark-all-read")
def mark_all_notifications_read(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    """Mark all notifications as read for the school admin."""
    svc = NotificationService(db)
    count = svc.mark_all_read(require_uuid(auth["person_id"]))
    db.commit()
    logger.info("School admin marked %d notifications as read", count)
    return RedirectResponse(
        url="/school/notifications?success=All+notifications+marked+as+read",
        status_code=303,
    )
