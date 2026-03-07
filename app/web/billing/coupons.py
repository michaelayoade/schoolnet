"""Admin web routes for Coupon management."""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.billing import CouponCreate, CouponUpdate
from app.services import billing as billing_service
from app.services.branding_context import load_branding_context
from app.templates import templates
from app.web.form_utils import as_int
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/billing/coupons", tags=["web-billing-coupons"])

PAGE_SIZE = 25

COUPON_DURATIONS = ["once", "repeating", "forever"]


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
def list_coupons(
    request: Request,
    page: int = 1,
    valid: str | None = None,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """List coupons with pagination and optional valid filter."""
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    valid_filter: bool | None = None
    if valid == "true":
        valid_filter = True
    elif valid == "false":
        valid_filter = False
    items, total = billing_service.coupons.list(
        db,
        valid=valid_filter,
        code=None,
        order_by="created_at",
        order_dir="desc",
        limit=PAGE_SIZE,
        offset=offset,
    )
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    ctx = _base_context(request, db, auth, title="Coupons", page_title="Coupons")
    ctx.update(
        {
            "coupons": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "valid_filter": valid or "",
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse("admin/billing/coupons/list.html", ctx)


@router.get("/create", response_class=HTMLResponse)
def create_coupon_form(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the create coupon form."""
    ctx = _base_context(
        request, db, auth, title="Create Coupon", page_title="Create Coupon"
    )
    ctx["durations"] = COUPON_DURATIONS
    return templates.TemplateResponse("admin/billing/coupons/create.html", ctx)


@router.post("/create", response_model=None)
def create_coupon_submit(
    request: Request,
    name: str = Form(""),
    code: str = Form(""),
    percent_off: str | None = Form(None),
    amount_off: str | None = Form(None),
    currency: str | None = Form(None),
    duration: str = Form("once"),
    duration_in_months: str | None = Form(None),
    max_redemptions: str | None = Form(None),
    valid: str | None = Form(None),
    redeem_by: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle coupon creation form submission."""
    _ = csrf_token
    data = {
        "name": name,
        "code": code,
        "percent_off": percent_off,
        "amount_off": amount_off,
        "currency": currency,
        "duration": duration,
        "duration_in_months": duration_in_months,
        "max_redemptions": max_redemptions,
        "valid": valid,
        "redeem_by": redeem_by,
    }

    try:
        redeem_by_val: datetime | None = None
        if redeem_by:
            redeem_by_val = datetime.fromisoformat(redeem_by)

        payload = CouponCreate(
            name=name,
            code=code,
            percent_off=as_int(percent_off) if percent_off else None,
            amount_off=as_int(amount_off) if amount_off else None,
            currency=currency if currency else None,
            duration=duration,  # type: ignore[arg-type]
            duration_in_months=as_int(duration_in_months)
            if duration_in_months
            else None,
            max_redemptions=as_int(max_redemptions) if max_redemptions else None,
            valid=valid == "on",
            redeem_by=redeem_by_val,
        )
        billing_service.coupons.create(db, payload)
        db.commit()
        logger.info("Created coupon via web: %s", payload.code)
        return RedirectResponse(
            url="/admin/billing/coupons?success=Coupon+created+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to create coupon: %s", exc)
        ctx = _base_context(
            request, db, auth, title="Create Coupon", page_title="Create Coupon"
        )
        ctx["durations"] = COUPON_DURATIONS
        ctx["error"] = str(exc)
        ctx["form_data"] = data
        return templates.TemplateResponse("admin/billing/coupons/create.html", ctx)


@router.get("/{item_id}", response_class=HTMLResponse)
def coupon_detail(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Show coupon detail view."""
    item = billing_service.coupons.get(db, str(item_id))
    ctx = _base_context(request, db, auth, title=item.name, page_title="Coupon Detail")
    ctx["coupon"] = item
    ctx["success"] = request.query_params.get("success")
    ctx["error"] = request.query_params.get("error")
    return templates.TemplateResponse("admin/billing/coupons/detail.html", ctx)


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def edit_coupon_form(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the edit coupon form."""
    item = billing_service.coupons.get(db, str(item_id))
    ctx = _base_context(
        request, db, auth, title="Edit Coupon", page_title="Edit Coupon"
    )
    ctx["coupon"] = item
    ctx["durations"] = COUPON_DURATIONS
    return templates.TemplateResponse("admin/billing/coupons/edit.html", ctx)


@router.post("/{item_id}/edit", response_model=None)
def edit_coupon_submit(
    request: Request,
    item_id: UUID,
    name: str | None = Form(None),
    percent_off: str | None = Form(None),
    amount_off: str | None = Form(None),
    currency: str | None = Form(None),
    duration: str | None = Form(None),
    duration_in_months: str | None = Form(None),
    max_redemptions: str | None = Form(None),
    valid: str | None = Form(None),
    redeem_by: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle coupon edit form submission."""
    _ = csrf_token
    _data = {
        "name": name,
        "percent_off": percent_off,
        "amount_off": amount_off,
        "currency": currency,
        "duration": duration,
        "duration_in_months": duration_in_months,
        "max_redemptions": max_redemptions,
        "valid": valid,
        "redeem_by": redeem_by,
    }

    try:
        redeem_by_val: datetime | None = None
        if redeem_by:
            redeem_by_val = datetime.fromisoformat(redeem_by)

        payload = CouponUpdate(
            name=name if name else None,
            percent_off=as_int(percent_off) if percent_off else None,
            amount_off=as_int(amount_off) if amount_off else None,
            currency=currency if currency else None,
            duration=duration if duration else None,  # type: ignore[arg-type]
            duration_in_months=as_int(duration_in_months)
            if duration_in_months
            else None,
            max_redemptions=as_int(max_redemptions) if max_redemptions else None,
            valid=valid == "on",
            redeem_by=redeem_by_val,
        )
        billing_service.coupons.update(db, str(item_id), payload)
        db.commit()
        logger.info("Updated coupon via web: %s", item_id)
        return RedirectResponse(
            url=f"/admin/billing/coupons/{item_id}?success=Coupon+updated+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to update coupon %s: %s", item_id, exc)
        item = billing_service.coupons.get(db, str(item_id))
        ctx = _base_context(
            request, db, auth, title="Edit Coupon", page_title="Edit Coupon"
        )
        ctx["coupon"] = item
        ctx["durations"] = COUPON_DURATIONS
        ctx["error"] = str(exc)
        return templates.TemplateResponse("admin/billing/coupons/edit.html", ctx)


@router.post("/{item_id}/delete", response_model=None)
def delete_coupon(
    request: Request,
    item_id: UUID,
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse:
    """Handle coupon deletion (soft-delete by setting valid=False)."""
    _ = csrf_token

    try:
        billing_service.coupons.delete(db, str(item_id))
        db.commit()
        logger.info("Deleted coupon via web: %s", item_id)
        return RedirectResponse(
            url="/admin/billing/coupons?success=Coupon+deleted+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to delete coupon %s: %s", item_id, exc)
        return RedirectResponse(
            url=f"/admin/billing/coupons?error={quote_plus(str(exc))}",
            status_code=302,
        )
