"""Platform admin ad management web routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.models.ad import Ad, AdSlot, AdStatus, AdType
from app.schemas.ad import AdCreate, AdUpdate
from app.services.ad import AdService
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/ads", tags=["admin-ads"])


# ── Helpers ──────────────────────────────────────────────


def _parse_datetime(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# ── List ─────────────────────────────────────────────────


@router.get("")
def list_ads(
    request: Request,
    status: str | None = None,
    slot: str | None = None,
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    svc = AdService(db)
    limit = 20
    offset = (page - 1) * limit

    status_filter = AdStatus(status) if status and status in AdStatus.__members__ else None
    slot_filter = AdSlot(slot) if slot and slot in AdSlot.__members__ else None

    total = svc.count(status=status_filter, slot=slot_filter)
    ads = svc.list_all(status=status_filter, slot=slot_filter, limit=limit, offset=offset)
    total_pages = (total + limit - 1) // limit if total else 1

    return templates.TemplateResponse(
        "admin/ads/list.html",
        {
            "request": request,
            "ads": ads,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "status_filter": status or "",
            "slot_filter": slot or "",
            "ad_slots": AdSlot,
            "ad_statuses": AdStatus,
            "auth": auth,
        },
    )


# ── Create ───────────────────────────────────────────────


@router.get("/create")
def create_ad_form(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    schools = SchoolService(db).list_active()
    return templates.TemplateResponse(
        "admin/ads/create.html",
        {
            "request": request,
            "ad_slots": AdSlot,
            "ad_types": AdType,
            "schools": schools,
            "auth": auth,
        },
    )


@router.post("/create")
async def create_ad(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
    title: str = Form(...),
    slot: str = Form(...),
    ad_type: str = Form(...),
    image_url: str = Form(default=""),
    target_url: str = Form(default=""),
    html_content: str = Form(default=""),
    alt_text: str = Form(default=""),
    school_id: str = Form(default=""),
    starts_at: str = Form(default=""),
    ends_at: str = Form(default=""),
    priority: int = Form(default=0),
) -> Response:
    try:
        data = AdCreate(
            title=title,
            slot=AdSlot(slot),
            ad_type=AdType(ad_type),
            image_url=image_url or None,
            target_url=target_url or None,
            html_content=html_content or None,
            alt_text=alt_text or None,
            school_id=require_uuid(school_id) if school_id else None,
            starts_at=_parse_datetime(starts_at),
            ends_at=_parse_datetime(ends_at),
            priority=priority,
        )
        svc = AdService(db)
        ad = svc.create(data)
        db.commit()
        return RedirectResponse(
            url=f"/admin/ads?success=Ad+created", status_code=303
        )
    except (ValueError, TypeError, KeyError) as e:
        db.rollback()
        logger.warning("Ad create error: %s", e)
        schools = SchoolService(db).list_active()
        return templates.TemplateResponse(
            "admin/ads/create.html",
            {
                "request": request,
                "error": str(e),
                "ad_slots": AdSlot,
                "ad_types": AdType,
                "schools": schools,
                "auth": auth,
            },
        )


# ── Edit ─────────────────────────────────────────────────


@router.get("/{ad_id}/edit")
def edit_ad_form(
    request: Request,
    ad_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    svc = AdService(db)
    ad = svc.get_by_id(require_uuid(ad_id))
    if not ad:
        return RedirectResponse(url="/admin/ads?error=Ad+not+found", status_code=303)

    schools = SchoolService(db).list_active()
    return templates.TemplateResponse(
        "admin/ads/edit.html",
        {
            "request": request,
            "ad": ad,
            "ad_slots": AdSlot,
            "ad_types": AdType,
            "ad_statuses": AdStatus,
            "schools": schools,
            "auth": auth,
        },
    )


@router.post("/{ad_id}/edit")
async def edit_ad(
    request: Request,
    ad_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
    title: str = Form(...),
    slot: str = Form(...),
    ad_type: str = Form(...),
    status: str = Form(...),
    image_url: str = Form(default=""),
    target_url: str = Form(default=""),
    html_content: str = Form(default=""),
    alt_text: str = Form(default=""),
    school_id: str = Form(default=""),
    starts_at: str = Form(default=""),
    ends_at: str = Form(default=""),
    priority: int = Form(default=0),
) -> Response:
    svc = AdService(db)
    ad = svc.get_by_id(require_uuid(ad_id))
    if not ad:
        return RedirectResponse(url="/admin/ads?error=Ad+not+found", status_code=303)

    try:
        data = AdUpdate(
            title=title,
            slot=AdSlot(slot),
            ad_type=AdType(ad_type),
            status=AdStatus(status),
            image_url=image_url or None,
            target_url=target_url or None,
            html_content=html_content or None,
            alt_text=alt_text or None,
            school_id=require_uuid(school_id) if school_id else None,
            starts_at=_parse_datetime(starts_at),
            ends_at=_parse_datetime(ends_at),
            priority=priority,
        )
        svc.update(ad, data)
        db.commit()
        return RedirectResponse(
            url=f"/admin/ads/{ad_id}/edit?success=Ad+updated", status_code=303
        )
    except (ValueError, TypeError, KeyError) as e:
        db.rollback()
        logger.warning("Ad update error: %s", e)
        schools = SchoolService(db).list_active()
        return templates.TemplateResponse(
            "admin/ads/edit.html",
            {
                "request": request,
                "ad": ad,
                "error": str(e),
                "ad_slots": AdSlot,
                "ad_types": AdType,
                "ad_statuses": AdStatus,
                "schools": schools,
                "auth": auth,
            },
        )


# ── Status actions ───────────────────────────────────────


@router.post("/{ad_id}/activate")
def activate_ad(
    request: Request,
    ad_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    svc = AdService(db)
    ad = svc.get_by_id(require_uuid(ad_id))
    if not ad:
        return RedirectResponse(url="/admin/ads?error=Ad+not+found", status_code=303)
    svc.activate(ad)
    db.commit()
    return RedirectResponse(
        url=f"/admin/ads?success=Ad+activated", status_code=303
    )


@router.post("/{ad_id}/pause")
def pause_ad(
    request: Request,
    ad_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    svc = AdService(db)
    ad = svc.get_by_id(require_uuid(ad_id))
    if not ad:
        return RedirectResponse(url="/admin/ads?error=Ad+not+found", status_code=303)
    svc.pause(ad)
    db.commit()
    return RedirectResponse(
        url=f"/admin/ads?success=Ad+paused", status_code=303
    )


@router.post("/{ad_id}/delete")
def delete_ad(
    request: Request,
    ad_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    svc = AdService(db)
    ad = svc.get_by_id(require_uuid(ad_id))
    if not ad:
        return RedirectResponse(url="/admin/ads?error=Ad+not+found", status_code=303)
    svc.delete(ad)
    db.commit()
    return RedirectResponse(
        url="/admin/ads?success=Ad+deleted", status_code=303
    )


# ── Click tracking (public, no auth) ─────────────────────

public_router = APIRouter(tags=["ads-public"])


@public_router.get("/ads/{ad_id}/click")
def track_click(
    request: Request,
    ad_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Public endpoint: record click and redirect to target URL."""
    svc = AdService(db)
    ad = svc.get_by_id(require_uuid(ad_id))
    if not ad or not ad.target_url:
        return RedirectResponse(url="/", status_code=302)
    client_ip = request.client.host if request.client else None
    svc.record_click(ad.id, ip=client_ip)
    db.commit()
    return RedirectResponse(url=ad.target_url, status_code=302)
