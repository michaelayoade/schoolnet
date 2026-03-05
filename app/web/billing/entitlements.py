"""Admin web routes for Entitlement management."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.billing import EntitlementCreate, EntitlementUpdate
from app.services import billing as billing_service
from app.services.branding_context import load_branding_context
from app.templates import templates
from app.web.form_utils import as_int
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/billing/entitlements", tags=["web-billing-entitlements"]
)

PAGE_SIZE = 25

VALUE_TYPES = ["boolean", "numeric", "string", "unlimited"]


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
def list_entitlements(
    request: Request,
    page: int = 1,
    product_id: str | None = None,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """List entitlements with pagination and optional product_id filter."""
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    items, total = billing_service.entitlements.list(
        db,
        product_id=product_id,
        feature_key=None,
        order_by="created_at",
        order_dir="desc",
        limit=PAGE_SIZE,
        offset=offset,
    )
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    # Load products for filter display
    all_products, _ = billing_service.products.list(
        db,
        is_active=None,
        order_by="name",
        order_dir="asc",
        limit=500,
        offset=0,
    )
    ctx = _base_context(
        request, db, auth, title="Entitlements", page_title="Entitlements"
    )
    ctx.update(
        {
            "entitlements": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "products": all_products,
            "product_id_filter": product_id or "",
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse("admin/billing/entitlements/list.html", ctx)


@router.get("/create", response_class=HTMLResponse)
def create_entitlement_form(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the create entitlement form."""
    all_products, _ = billing_service.products.list(
        db,
        is_active=True,
        order_by="name",
        order_dir="asc",
        limit=500,
        offset=0,
    )
    ctx = _base_context(
        request, db, auth, title="Create Entitlement", page_title="Create Entitlement"
    )
    ctx["products"] = all_products
    ctx["value_types"] = VALUE_TYPES
    return templates.TemplateResponse("admin/billing/entitlements/create.html", ctx)


@router.post("/create", response_model=None)
def create_entitlement_submit(
    request: Request,
    product_id: str = Form(...),
    feature_key: str = Form(""),
    value_type: str = Form("boolean"),
    value_text: str | None = Form(None),
    value_numeric: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle entitlement creation form submission."""
    _ = csrf_token
    data = {
        "product_id": product_id,
        "feature_key": feature_key,
        "value_type": value_type,
        "value_text": value_text,
        "value_numeric": value_numeric,
    }

    try:
        payload = EntitlementCreate(
            product_id=UUID(product_id),
            feature_key=feature_key,
            value_type=value_type,  # type: ignore[arg-type]
            value_text=value_text if value_text else None,
            value_numeric=as_int(value_numeric) if value_numeric else None,
        )
        billing_service.entitlements.create(db, payload)
        db.commit()
        logger.info("Created entitlement via web: %s", payload.feature_key)
        return RedirectResponse(
            url="/admin/billing/entitlements?success=Entitlement+created+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to create entitlement: %s", exc)
        all_products, _ = billing_service.products.list(
            db,
            is_active=True,
            order_by="name",
            order_dir="asc",
            limit=500,
            offset=0,
        )
        ctx = _base_context(
            request,
            db,
            auth,
            title="Create Entitlement",
            page_title="Create Entitlement",
        )
        ctx["products"] = all_products
        ctx["value_types"] = VALUE_TYPES
        ctx["error"] = str(exc)
        ctx["form_data"] = data
        return templates.TemplateResponse("admin/billing/entitlements/create.html", ctx)


@router.get("/{item_id}", response_class=HTMLResponse)
def entitlement_detail(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Show entitlement detail view."""
    item = billing_service.entitlements.get(db, str(item_id))
    product = billing_service.products.get(db, str(item.product_id))
    ctx = _base_context(
        request,
        db,
        auth,
        title=f"Entitlement - {item.feature_key}",
        page_title="Entitlement Detail",
    )
    ctx["entitlement"] = item
    ctx["product"] = product
    ctx["success"] = request.query_params.get("success")
    ctx["error"] = request.query_params.get("error")
    return templates.TemplateResponse("admin/billing/entitlements/detail.html", ctx)


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def edit_entitlement_form(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the edit entitlement form."""
    item = billing_service.entitlements.get(db, str(item_id))
    all_products, _ = billing_service.products.list(
        db,
        is_active=None,
        order_by="name",
        order_dir="asc",
        limit=500,
        offset=0,
    )
    ctx = _base_context(
        request, db, auth, title="Edit Entitlement", page_title="Edit Entitlement"
    )
    ctx["entitlement"] = item
    ctx["products"] = all_products
    ctx["value_types"] = VALUE_TYPES
    return templates.TemplateResponse("admin/billing/entitlements/edit.html", ctx)


@router.post("/{item_id}/edit", response_model=None)
def edit_entitlement_submit(
    request: Request,
    item_id: UUID,
    feature_key: str | None = Form(None),
    value_type: str | None = Form(None),
    value_text: str | None = Form(None),
    value_numeric: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle entitlement edit form submission."""
    _ = csrf_token
    data = {  # noqa: F841
        "feature_key": feature_key,
        "value_type": value_type,
        "value_text": value_text,
        "value_numeric": value_numeric,
    }

    try:
        payload = EntitlementUpdate(
            feature_key=feature_key if feature_key else None,
            value_type=value_type if value_type else None,  # type: ignore[arg-type]
            value_text=value_text if value_text else None,
            value_numeric=as_int(value_numeric) if value_numeric else None,
        )
        billing_service.entitlements.update(db, str(item_id), payload)
        db.commit()
        logger.info("Updated entitlement via web: %s", item_id)
        return RedirectResponse(
            url=f"/admin/billing/entitlements/{item_id}?success=Entitlement+updated+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to update entitlement %s: %s", item_id, exc)
        item = billing_service.entitlements.get(db, str(item_id))
        all_products, _ = billing_service.products.list(
            db,
            is_active=None,
            order_by="name",
            order_dir="asc",
            limit=500,
            offset=0,
        )
        ctx = _base_context(
            request,
            db,
            auth,
            title="Edit Entitlement",
            page_title="Edit Entitlement",
        )
        ctx["entitlement"] = item
        ctx["products"] = all_products
        ctx["value_types"] = VALUE_TYPES
        ctx["error"] = str(exc)
        return templates.TemplateResponse("admin/billing/entitlements/edit.html", ctx)


@router.post("/{item_id}/delete", response_model=None)
def delete_entitlement(
    request: Request,
    item_id: UUID,
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse:
    """Handle entitlement deletion."""
    _ = csrf_token

    try:
        billing_service.entitlements.delete(db, str(item_id))
        db.commit()
        logger.info("Deleted entitlement via web: %s", item_id)
        return RedirectResponse(
            url="/admin/billing/entitlements?success=Entitlement+deleted+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to delete entitlement %s: %s", item_id, exc)
        return RedirectResponse(
            url=f"/admin/billing/entitlements?error={quote_plus(str(exc))}",
            status_code=302,
        )
