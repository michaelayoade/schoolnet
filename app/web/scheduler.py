"""Admin web routes for Scheduled Task management."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.scheduler import ScheduledTask
from app.schemas.scheduler import ScheduledTaskCreate, ScheduledTaskUpdate
from app.services.branding_context import load_branding_context
from app.services.scheduler import ScheduledTasks
from app.templates import templates
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/scheduler", tags=["web-scheduler"])

PAGE_SIZE = 25


def _base_context(
    request: Request,
    db: Session,
    auth: dict,
    *,
    title: str,
    page_title: str,
) -> dict:
    branding = load_branding_context(db)
    person = auth["person"]
    return {
        "request": request,
        "title": title,
        "page_title": page_title,
        "current_user": person,
        "brand": branding["brand"],
        "org_branding": branding["org_branding"],
        "brand_mark": branding["brand"].get("mark", "A"),
    }


@router.get("", response_class=HTMLResponse)
def list_scheduled_tasks(
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """List scheduled tasks with pagination."""
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE

    query = select(ScheduledTask).order_by(ScheduledTask.created_at.desc())
    total = (
        db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        or 0
    )
    items = list(db.scalars(query.limit(PAGE_SIZE).offset(offset)).all())
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    ctx = _base_context(
        request, db, auth, title="Scheduled Tasks", page_title="Scheduled Tasks"
    )
    ctx.update(
        {
            "tasks": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse("admin/scheduler/list.html", ctx)


@router.get("/create", response_class=HTMLResponse)
def create_task_form(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the create scheduled task form."""
    ctx = _base_context(
        request,
        db,
        auth,
        title="Create Scheduled Task",
        page_title="Create Scheduled Task",
    )
    return templates.TemplateResponse("admin/scheduler/create.html", ctx)


@router.post("/create", response_model=None)
def create_task_submit(
    request: Request,
    name: str = Form(""),
    task_name: str = Form(""),
    interval_seconds: str = Form("3600"),
    enabled: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle scheduled task creation form submission."""
    _ = csrf_token
    data = {
        "name": name,
        "task_name": task_name,
        "interval_seconds": interval_seconds,
        "enabled": enabled,
    }

    try:
        interval = int(interval_seconds)
        payload = ScheduledTaskCreate(
            name=name,
            task_name=task_name,
            interval_seconds=interval,
            enabled=enabled == "on",
        )
        ScheduledTasks(db).create(payload)
        db.commit()
        logger.info("Created scheduled task via web: %s", payload.name)
        return RedirectResponse(
            url="/admin/scheduler?success=Task+created+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to create scheduled task: %s", exc)
        ctx = _base_context(
            request,
            db,
            auth,
            title="Create Scheduled Task",
            page_title="Create Scheduled Task",
        )
        ctx["error"] = str(exc)
        ctx["form_data"] = data
        return templates.TemplateResponse("admin/scheduler/create.html", ctx)


@router.get("/{task_id}/edit", response_class=HTMLResponse)
def edit_task_form(
    request: Request,
    task_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the edit scheduled task form."""
    task = ScheduledTasks(db).get(str(task_id))
    ctx = _base_context(
        request,
        db,
        auth,
        title="Edit Scheduled Task",
        page_title="Edit Scheduled Task",
    )
    ctx["task"] = task
    return templates.TemplateResponse("admin/scheduler/edit.html", ctx)


@router.post("/{task_id}/edit", response_model=None)
def edit_task_submit(
    request: Request,
    task_id: UUID,
    name: str | None = Form(None),
    task_name: str | None = Form(None),
    interval_seconds: str | None = Form(None),
    enabled: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle scheduled task edit form submission."""
    _ = csrf_token
    data = {  # noqa: F841
        "name": name,
        "task_name": task_name,
        "interval_seconds": interval_seconds,
        "enabled": enabled,
    }

    try:
        interval = int(interval_seconds) if interval_seconds else None
        payload = ScheduledTaskUpdate(
            name=name if name else None,
            task_name=task_name if task_name else None,
            interval_seconds=interval,
            enabled=enabled == "on",
        )
        ScheduledTasks(db).update(str(task_id), payload)
        db.commit()
        logger.info("Updated scheduled task via web: %s", task_id)
        return RedirectResponse(
            url="/admin/scheduler?success=Task+updated+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to update scheduled task %s: %s", task_id, exc)
        task = db.get(ScheduledTask, task_id)
        ctx = _base_context(
            request,
            db,
            auth,
            title="Edit Scheduled Task",
            page_title="Edit Scheduled Task",
        )
        ctx["task"] = task
        ctx["error"] = str(exc)
        return templates.TemplateResponse("admin/scheduler/edit.html", ctx)


@router.post("/{task_id}/delete", response_model=None)
def delete_task(
    request: Request,
    task_id: UUID,
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse:
    """Handle scheduled task deletion."""
    _ = csrf_token

    try:
        ScheduledTasks(db).delete(str(task_id))
        db.commit()
        logger.info("Deleted scheduled task via web: %s", task_id)
        return RedirectResponse(
            url="/admin/scheduler?success=Task+deleted+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to delete scheduled task %s: %s", task_id, exc)
        return RedirectResponse(
            url=f"/admin/scheduler?error={quote_plus(str(exc))}",
            status_code=302,
        )
