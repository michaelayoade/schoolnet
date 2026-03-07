"""Admin web routes for Price management."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.billing import PriceCreate, PriceUpdate
from app.services import billing as billing_service
from app.services.branding_context import load_branding_context
from app.templates import templates
from app.web.form_utils import as_int, as_str
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/billing/prices", tags=["web-billing-prices"])

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
def list_prices(
    request: Request,
    page: int = 1,
    product_id: str | None = None,
    is_active: str | None = None,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """List prices with pagination and optional filters."""
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    active_filter: bool | None = None
    if is_active == "true":
        active_filter = True
    elif is_active == "false":
        active_filter = False
    items, total = billing_service.prices.list(
        db,
        product_id=product_id,
        type=None,
        currency=None,
        is_active=active_filter,
        order_by="created_at",
        order_dir="desc",
        limit=PAGE_SIZE,
        offset=offset,
    )
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    # Load products for display
    all_products, _ = billing_service.products.list(
        db,
        is_active=None,
        order_by="name",
        order_dir="asc",
        limit=500,
        offset=0,
    )
    ctx = _base_context(request, db, auth, title="Prices", page_title="Prices")
    ctx.update(
        {
            "prices": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "products": all_products,
            "product_id_filter": product_id or "",
            "is_active_filter": is_active or "",
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse("admin/billing/prices/list.html", ctx)


@router.get("/create", response_class=HTMLResponse)
def create_price_form(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the create price form."""
    all_products, _ = billing_service.products.list(
        db,
        is_active=True,
        order_by="name",
        order_dir="asc",
        limit=500,
        offset=0,
    )
    ctx = _base_context(
        request, db, auth, title="Create Price", page_title="Create Price"
    )
    ctx["products"] = all_products
    return templates.TemplateResponse("admin/billing/prices/create.html", ctx)


@router.post("/create", response_model=None)
def create_price_submit(
    request: Request,
    product_id: str = Form(...),
    currency: str = Form("usd"),
    unit_amount: str | None = Form(None),
    type: str = Form("one_time"),
    billing_scheme: str = Form("per_unit"),
    recurring_interval: str | None = Form(None),
    recurring_interval_count: str | None = Form(None),
    trial_period_days: str | None = Form(None),
    lookup_key: str | None = Form(None),
    is_active: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle price creation form submission."""
    _ = csrf_token
    data = {
        "product_id": product_id,
        "currency": currency,
        "unit_amount": unit_amount,
        "type": type,
        "billing_scheme": billing_scheme,
        "recurring_interval": recurring_interval,
        "recurring_interval_count": recurring_interval_count,
        "trial_period_days": trial_period_days,
        "lookup_key": lookup_key,
        "is_active": is_active,
    }

    try:
        payload = PriceCreate(
            product_id=UUID(product_id),
            currency=currency,
            unit_amount=as_int(unit_amount) or 0,
            type=type,  # type: ignore[arg-type]
            billing_scheme=billing_scheme,  # type: ignore[arg-type]
            recurring_interval=as_str(recurring_interval)
            if recurring_interval
            else None,  # type: ignore[arg-type]
            recurring_interval_count=as_int(recurring_interval_count) or 1,
            trial_period_days=as_int(trial_period_days) if trial_period_days else None,
            lookup_key=as_str(lookup_key) if lookup_key else None,
            is_active=is_active == "on",
        )
        billing_service.prices.create(db, payload)
        db.commit()
        logger.info("Created price via web for product: %s", payload.product_id)
        return RedirectResponse(
            url="/admin/billing/prices?success=Price+created+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to create price: %s", exc)
        all_products, _ = billing_service.products.list(
            db,
            is_active=True,
            order_by="name",
            order_dir="asc",
            limit=500,
            offset=0,
        )
        ctx = _base_context(
            request, db, auth, title="Create Price", page_title="Create Price"
        )
        ctx["products"] = all_products
        ctx["error"] = str(exc)
        ctx["form_data"] = data
        return templates.TemplateResponse("admin/billing/prices/create.html", ctx)


@router.get("/{item_id}", response_class=HTMLResponse)
def price_detail(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Show price detail view."""
    item = billing_service.prices.get(db, str(item_id))
    product = billing_service.products.get(db, str(item.product_id))
    ctx = _base_context(
        request,
        db,
        auth,
        title=f"Price - {product.name}",
        page_title="Price Detail",
    )
    ctx["price"] = item
    ctx["product"] = product
    ctx["success"] = request.query_params.get("success")
    ctx["error"] = request.query_params.get("error")
    return templates.TemplateResponse("admin/billing/prices/detail.html", ctx)


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def edit_price_form(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the edit price form."""
    item = billing_service.prices.get(db, str(item_id))
    all_products, _ = billing_service.products.list(
        db,
        is_active=None,
        order_by="name",
        order_dir="asc",
        limit=500,
        offset=0,
    )
    ctx = _base_context(request, db, auth, title="Edit Price", page_title="Edit Price")
    ctx["price"] = item
    ctx["products"] = all_products
    return templates.TemplateResponse("admin/billing/prices/edit.html", ctx)


@router.post("/{item_id}/edit", response_model=None)
def edit_price_submit(
    request: Request,
    item_id: UUID,
    currency: str | None = Form(None),
    unit_amount: str | None = Form(None),
    type: str | None = Form(None),
    billing_scheme: str | None = Form(None),
    recurring_interval: str | None = Form(None),
    recurring_interval_count: str | None = Form(None),
    trial_period_days: str | None = Form(None),
    lookup_key: str | None = Form(None),
    is_active: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle price edit form submission."""
    _ = csrf_token
    _data = {
        "currency": currency,
        "unit_amount": unit_amount,
        "type": type,
        "billing_scheme": billing_scheme,
        "recurring_interval": recurring_interval,
        "recurring_interval_count": recurring_interval_count,
        "trial_period_days": trial_period_days,
        "lookup_key": lookup_key,
        "is_active": is_active,
    }

    try:
        payload = PriceUpdate(
            currency=currency if currency else None,
            unit_amount=as_int(unit_amount) if unit_amount else None,
            type=type if type else None,  # type: ignore[arg-type]
            billing_scheme=billing_scheme if billing_scheme else None,  # type: ignore[arg-type]
            recurring_interval=recurring_interval if recurring_interval else None,  # type: ignore[arg-type]
            recurring_interval_count=as_int(recurring_interval_count)
            if recurring_interval_count
            else None,
            trial_period_days=as_int(trial_period_days) if trial_period_days else None,
            lookup_key=lookup_key if lookup_key else None,
            is_active=is_active == "on",
        )
        billing_service.prices.update(db, str(item_id), payload)
        db.commit()
        logger.info("Updated price via web: %s", item_id)
        return RedirectResponse(
            url=f"/admin/billing/prices/{item_id}?success=Price+updated+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to update price %s: %s", item_id, exc)
        item = billing_service.prices.get(db, str(item_id))
        all_products, _ = billing_service.products.list(
            db,
            is_active=None,
            order_by="name",
            order_dir="asc",
            limit=500,
            offset=0,
        )
        ctx = _base_context(
            request, db, auth, title="Edit Price", page_title="Edit Price"
        )
        ctx["price"] = item
        ctx["products"] = all_products
        ctx["error"] = str(exc)
        return templates.TemplateResponse("admin/billing/prices/edit.html", ctx)


@router.post("/{item_id}/delete", response_model=None)
def delete_price(
    request: Request,
    item_id: UUID,
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse:
    """Handle price deletion."""
    _ = csrf_token

    try:
        billing_service.prices.delete(db, str(item_id))
        db.commit()
        logger.info("Deleted price via web: %s", item_id)
        return RedirectResponse(
            url="/admin/billing/prices?success=Price+deleted+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to delete price %s: %s", item_id, exc)
        return RedirectResponse(
            url=f"/admin/billing/prices?error={quote_plus(str(exc))}",
            status_code=302,
        )
