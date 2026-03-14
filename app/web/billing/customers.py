"""Admin web routes for Customer management."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.billing import CustomerCreate, CustomerUpdate
from app.services import billing as billing_service
from app.services.branding_context import load_branding_context
from app.templates import templates
from app.web.form_utils import as_int
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/billing/customers", tags=["web-billing-customers"])

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
def list_customers(
    request: Request,
    page: int = 1,
    email: str | None = None,
    is_active: str | None = None,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """List customers with pagination and optional email search."""
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    active_filter: bool | None = None
    if is_active == "true":
        active_filter = True
    elif is_active == "false":
        active_filter = False
    items, total = billing_service.customers.list(
        db,
        person_id=None,
        email=email,
        is_active=active_filter,
        order_by="created_at",
        order_dir="desc",
        limit=PAGE_SIZE,
        offset=offset,
    )
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    ctx = _base_context(request, db, auth, title="Customers", page_title="Customers")
    ctx.update(
        {
            "customers": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "email_filter": email or "",
            "is_active_filter": is_active or "",
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse("admin/billing/customers/list.html", ctx)


@router.get("/create", response_class=HTMLResponse)
def create_customer_form(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the create customer form."""
    ctx = _base_context(
        request, db, auth, title="Create Customer", page_title="Create Customer"
    )
    return templates.TemplateResponse("admin/billing/customers/create.html", ctx)


@router.post("/create", response_model=None)
def create_customer_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    currency: str = Form("usd"),
    balance: str | None = Form(None),
    tax_id: str | None = Form(None),
    external_id: str | None = Form(None),
    is_active: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle customer creation form submission."""
    _ = csrf_token
    data = {
        "name": name,
        "email": email,
        "currency": currency,
        "balance": balance,
        "tax_id": tax_id,
        "external_id": external_id,
        "is_active": is_active,
    }

    try:
        payload = CustomerCreate(
            name=name,
            email=email,
            currency=currency,
            balance=as_int(balance) or 0,
            tax_id=tax_id if tax_id else None,
            external_id=external_id if external_id else None,
            is_active=is_active == "on",
        )
        billing_service.customers.create(db, payload)
        db.commit()
        logger.info("Created customer via web: %s", payload.email)
        return RedirectResponse(
            url="/admin/billing/customers?success=Customer+created+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to create customer: %s", exc)
        ctx = _base_context(
            request, db, auth, title="Create Customer", page_title="Create Customer"
        )
        ctx["error"] = str(exc)
        ctx["form_data"] = data
        return templates.TemplateResponse("admin/billing/customers/create.html", ctx)


@router.get("/{item_id}", response_class=HTMLResponse)
def customer_detail(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Show customer detail view with subscriptions and payment methods."""
    item = billing_service.customers.get(db, str(item_id))
    ctx = _base_context(
        request, db, auth, title=item.name, page_title="Customer Detail"
    )
    ctx["customer"] = item
    # Load related subscriptions
    subs, _ = billing_service.subscriptions.list(
        db,
        customer_id=str(item_id),
        status=None,
        is_active=None,
        order_by="created_at",
        order_dir="desc",
        limit=50,
        offset=0,
    )
    ctx["subscriptions"] = subs
    # Load related payment methods
    pms, _ = billing_service.payment_methods.list(
        db,
        customer_id=str(item_id),
        type=None,
        is_active=None,
        order_by="created_at",
        order_dir="desc",
        limit=50,
        offset=0,
    )
    ctx["payment_methods"] = pms
    ctx["success"] = request.query_params.get("success")
    ctx["error"] = request.query_params.get("error")
    return templates.TemplateResponse("admin/billing/customers/detail.html", ctx)


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def edit_customer_form(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the edit customer form."""
    item = billing_service.customers.get(db, str(item_id))
    ctx = _base_context(
        request, db, auth, title="Edit Customer", page_title="Edit Customer"
    )
    ctx["customer"] = item
    return templates.TemplateResponse("admin/billing/customers/edit.html", ctx)


@router.post("/{item_id}/edit", response_model=None)
def edit_customer_submit(
    request: Request,
    item_id: UUID,
    name: str | None = Form(None),
    email: str | None = Form(None),
    currency: str | None = Form(None),
    balance: str | None = Form(None),
    tax_id: str | None = Form(None),
    external_id: str | None = Form(None),
    is_active: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle customer edit form submission."""
    _ = csrf_token

    try:
        payload = CustomerUpdate(
            name=name if name else None,
            email=email if email else None,
            currency=currency if currency else None,
            balance=as_int(balance) if balance else None,
            tax_id=tax_id if tax_id else None,
            external_id=external_id if external_id else None,
            is_active=is_active == "on",
        )
        billing_service.customers.update(db, str(item_id), payload)
        db.commit()
        logger.info("Updated customer via web: %s", item_id)
        return RedirectResponse(
            url=f"/admin/billing/customers/{item_id}?success=Customer+updated+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to update customer %s: %s", item_id, exc)
        item = billing_service.customers.get(db, str(item_id))
        ctx = _base_context(
            request, db, auth, title="Edit Customer", page_title="Edit Customer"
        )
        ctx["customer"] = item
        ctx["error"] = str(exc)
        return templates.TemplateResponse("admin/billing/customers/edit.html", ctx)


@router.post("/{item_id}/delete", response_model=None)
def delete_customer(
    request: Request,
    item_id: UUID,
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse:
    """Handle customer deletion."""
    _ = csrf_token

    try:
        billing_service.customers.delete(db, str(item_id))
        db.commit()
        logger.info("Deleted customer via web: %s", item_id)
        return RedirectResponse(
            url="/admin/billing/customers?success=Customer+deleted+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to delete customer %s: %s", item_id, exc)
        return RedirectResponse(
            url=f"/admin/billing/customers?error={quote_plus(str(exc))}",
            status_code=302,
        )
