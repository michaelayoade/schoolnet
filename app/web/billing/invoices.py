"""Admin web routes for Invoice management."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.billing import InvoiceUpdate
from app.services import billing as billing_service
from app.services.branding_context import load_branding_context
from app.templates import templates
from app.web.form_utils import as_int
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/billing/invoices", tags=["web-billing-invoices"])

PAGE_SIZE = 25

INVOICE_STATUSES = ["draft", "open", "paid", "void", "uncollectible"]


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
def list_invoices(
    request: Request,
    page: int = 1,
    customer_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """List invoices with pagination and optional filters."""
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    items, total = billing_service.invoices.list(
        db,
        customer_id=customer_id,
        subscription_id=None,
        status=status,
        order_by="created_at",
        order_dir="desc",
        limit=PAGE_SIZE,
        offset=offset,
    )
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    # Load customers for filter display
    all_customers, _ = billing_service.customers.list(
        db,
        person_id=None,
        email=None,
        is_active=None,
        order_by="name",
        order_dir="asc",
        limit=500,
        offset=0,
    )
    ctx = _base_context(request, db, auth, title="Invoices", page_title="Invoices")
    ctx.update(
        {
            "invoices": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "customers": all_customers,
            "customer_id_filter": customer_id or "",
            "status_filter": status or "",
            "statuses": INVOICE_STATUSES,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse("admin/billing/invoices/list.html", ctx)


@router.get("/{item_id}", response_class=HTMLResponse)
def invoice_detail(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Show invoice detail view with items and payment intents."""
    item = billing_service.invoices.get(db, str(item_id))
    customer = billing_service.customers.get(db, str(item.customer_id))
    ctx = _base_context(
        request,
        db,
        auth,
        title=f"Invoice {item.number if item.number else str(item_id)[:8]}",
        page_title="Invoice Detail",
    )
    ctx["invoice"] = item
    ctx["customer"] = customer
    # Load invoice items
    inv_items, _ = billing_service.invoice_items.list(
        db,
        invoice_id=str(item_id),
        order_by="created_at",
        order_dir="asc",
        limit=100,
        offset=0,
    )
    ctx["invoice_items"] = inv_items
    # Load payment intents
    pi_items, _ = billing_service.payment_intents.list(
        db,
        customer_id=str(item.customer_id),
        invoice_id=str(item_id),
        status=None,
        order_by="created_at",
        order_dir="desc",
        limit=50,
        offset=0,
    )
    ctx["payment_intents"] = pi_items
    ctx["statuses"] = INVOICE_STATUSES
    ctx["success"] = request.query_params.get("success")
    ctx["error"] = request.query_params.get("error")
    return templates.TemplateResponse("admin/billing/invoices/detail.html", ctx)


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def edit_invoice_form(
    request: Request,
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the edit invoice form."""
    item = billing_service.invoices.get(db, str(item_id))
    customer = billing_service.customers.get(db, str(item.customer_id))
    ctx = _base_context(
        request, db, auth, title="Edit Invoice", page_title="Edit Invoice"
    )
    ctx["invoice"] = item
    ctx["customer"] = customer
    ctx["statuses"] = INVOICE_STATUSES
    return templates.TemplateResponse("admin/billing/invoices/edit.html", ctx)


@router.post("/{item_id}/edit", response_model=None)
def edit_invoice_submit(
    request: Request,
    item_id: UUID,
    number: str | None = Form(None),
    status: str | None = Form(None),
    currency: str | None = Form(None),
    subtotal: str | None = Form(None),
    tax: str | None = Form(None),
    total: str | None = Form(None),
    amount_due: str | None = Form(None),
    amount_paid: str | None = Form(None),
    external_id: str | None = Form(None),
    is_active: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle invoice edit form submission."""
    _ = csrf_token

    try:
        payload = InvoiceUpdate(
            number=number if number else None,
            status=status if status else None,  # type: ignore[arg-type]
            currency=currency if currency else None,
            subtotal=as_int(subtotal) if subtotal else None,
            tax=as_int(tax) if tax else None,
            total=as_int(total) if total else None,
            amount_due=as_int(amount_due) if amount_due else None,
            amount_paid=as_int(amount_paid) if amount_paid else None,
            external_id=external_id if external_id else None,
            is_active=is_active == "on",
        )
        billing_service.invoices.update(db, str(item_id), payload)
        db.commit()
        logger.info("Updated invoice via web: %s", item_id)
        return RedirectResponse(
            url=f"/admin/billing/invoices/{item_id}?success=Invoice+updated+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to update invoice %s: %s", item_id, exc)
        item = billing_service.invoices.get(db, str(item_id))
        customer = billing_service.customers.get(db, str(item.customer_id))
        ctx = _base_context(
            request, db, auth, title="Edit Invoice", page_title="Edit Invoice"
        )
        ctx["invoice"] = item
        ctx["customer"] = customer
        ctx["statuses"] = INVOICE_STATUSES
        ctx["error"] = str(exc)
        return templates.TemplateResponse("admin/billing/invoices/edit.html", ctx)


@router.post("/{item_id}/delete", response_model=None)
def delete_invoice(
    request: Request,
    item_id: UUID,
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse:
    """Handle invoice deletion."""
    _ = csrf_token

    try:
        billing_service.invoices.delete(db, str(item_id))
        db.commit()
        logger.info("Deleted invoice via web: %s", item_id)
        return RedirectResponse(
            url="/admin/billing/invoices?success=Invoice+deleted+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to delete invoice %s: %s", item_id, exc)
        return RedirectResponse(
            url=f"/admin/billing/invoices?error={quote_plus(str(exc))}",
            status_code=302,
        )
