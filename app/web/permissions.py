"""Admin web routes for Permission management."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.rbac import Permission
from app.schemas.rbac import PermissionCreate, PermissionUpdate
from app.services.branding_context import load_branding_context
from app.services.rbac import permissions
from app.templates import templates
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/permissions", tags=["web-permissions"])

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
def list_permissions(
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """List permissions with pagination."""
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE

    query = (
        select(Permission)
        .where(Permission.is_active.is_(True))
        .order_by(Permission.key.asc())
    )
    total = (
        db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        or 0
    )
    items = list(db.scalars(query.limit(PAGE_SIZE).offset(offset)).all())
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    ctx = _base_context(
        request, db, auth, title="Permissions", page_title="Permissions"
    )
    ctx.update(
        {
            "permissions": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse("admin/permissions/list.html", ctx)


@router.get("/create", response_class=HTMLResponse)
def create_permission_form(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the create permission form."""
    ctx = _base_context(
        request, db, auth, title="Create Permission", page_title="Create Permission"
    )
    return templates.TemplateResponse("admin/permissions/create.html", ctx)


@router.post("/create", response_model=None)
def create_permission_submit(
    request: Request,
    key: str = Form(""),
    description: str | None = Form(None),
    is_active: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle permission creation form submission."""
    _ = csrf_token
    data = {
        "key": key,
        "description": description,
        "is_active": is_active,
    }

    try:
        payload = PermissionCreate(
            key=key,
            description=description if description else None,
            is_active=is_active == "on",
        )
        permissions.create(db, payload)
        db.commit()
        logger.info("Created permission via web: %s", payload.key)
        return RedirectResponse(
            url="/admin/permissions?success=Permission+created+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to create permission: %s", exc)
        ctx = _base_context(
            request,
            db,
            auth,
            title="Create Permission",
            page_title="Create Permission",
        )
        ctx["error"] = str(exc)
        ctx["form_data"] = data
        return templates.TemplateResponse("admin/permissions/create.html", ctx)


@router.get("/{permission_id}/edit", response_class=HTMLResponse)
def edit_permission_form(
    request: Request,
    permission_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the edit permission form."""
    permission = permissions.get(db, str(permission_id))
    ctx = _base_context(
        request, db, auth, title="Edit Permission", page_title="Edit Permission"
    )
    ctx["permission"] = permission
    return templates.TemplateResponse("admin/permissions/edit.html", ctx)


@router.post("/{permission_id}/edit", response_model=None)
def edit_permission_submit(
    request: Request,
    permission_id: UUID,
    key: str | None = Form(None),
    description: str | None = Form(None),
    is_active: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle permission edit form submission."""
    _ = csrf_token

    try:
        payload = PermissionUpdate(
            key=key if key else None,
            description=description if description else None,
            is_active=is_active == "on",
        )
        permissions.update(db, str(permission_id), payload)
        db.commit()
        logger.info("Updated permission via web: %s", permission_id)
        return RedirectResponse(
            url="/admin/permissions?success=Permission+updated+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to update permission %s: %s", permission_id, exc)
        permission = db.get(Permission, permission_id)
        ctx = _base_context(
            request, db, auth, title="Edit Permission", page_title="Edit Permission"
        )
        ctx["permission"] = permission
        ctx["error"] = str(exc)
        return templates.TemplateResponse("admin/permissions/edit.html", ctx)


@router.post("/{permission_id}/delete", response_model=None)
def delete_permission(
    request: Request,
    permission_id: UUID,
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse:
    """Handle permission deletion (soft delete via is_active=False)."""
    _ = csrf_token

    try:
        permissions.delete(db, str(permission_id))
        db.commit()
        logger.info("Deleted permission via web: %s", permission_id)
        return RedirectResponse(
            url="/admin/permissions?success=Permission+deleted+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to delete permission %s: %s", permission_id, exc)
        return RedirectResponse(
            url=f"/admin/permissions?error={quote_plus(str(exc))}",
            status_code=302,
        )
