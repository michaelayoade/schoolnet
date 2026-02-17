"""Parent portal — dashboard, payments, profile, settings."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.models.auth import UserCredential
from app.models.billing import Customer, Invoice, InvoiceItem, PaymentIntent
from app.services.application import ApplicationService
from app.services.auth_flow import hash_password, verify_password
from app.services.common import coerce_uuid, require_uuid
from app.templates import templates
from app.web.schoolnet_deps import require_parent_auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["parent-dashboard"])


@router.get("/parent")
def parent_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    svc = ApplicationService(db)
    applications = svc.list_for_parent(parent_id)

    total = len(applications)
    drafts = sum(1 for a in applications if a.status.value == "draft")
    submitted = sum(
        1 for a in applications if a.status.value in ("submitted", "under_review")
    )
    accepted = sum(1 for a in applications if a.status.value == "accepted")

    return templates.TemplateResponse(
        "parent/dashboard.html",
        {
            "request": request,
            "auth": auth,
            "total_applications": total,
            "draft_count": drafts,
            "submitted_count": submitted,
            "accepted_count": accepted,
            "recent_applications": applications[:5],
        },
    )


@router.get("/parent/payments")
def payment_history(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    customer = db.scalar(select(Customer).where(Customer.person_id == parent_id))

    invoices = []
    if customer:
        stmt = (
            select(Invoice)
            .where(Invoice.customer_id == customer.id)
            .order_by(Invoice.created_at.desc())
        )
        invoices = list(db.scalars(stmt).all())

    return templates.TemplateResponse(
        "parent/payments/list.html",
        {"request": request, "auth": auth, "invoices": invoices},
    )


@router.get("/parent/payments/{invoice_id}")
def payment_detail(
    request: Request,
    invoice_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])

    # Look up the invoice
    invoice = db.get(Invoice, coerce_uuid(invoice_id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Verify the invoice belongs to this parent via customer.person_id
    customer = db.get(Customer, invoice.customer_id)
    if not customer or customer.person_id != parent_id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Load invoice items
    items_stmt = (
        select(InvoiceItem)
        .where(InvoiceItem.invoice_id == invoice.id)
        .order_by(InvoiceItem.created_at.asc())
    )
    invoice_items = list(db.scalars(items_stmt).all())

    # Load payment intents for this invoice
    pi_stmt = (
        select(PaymentIntent)
        .where(PaymentIntent.invoice_id == invoice.id)
        .order_by(PaymentIntent.created_at.desc())
    )
    payment_intents = list(db.scalars(pi_stmt).all())

    return templates.TemplateResponse(
        "parent/payments/detail.html",
        {
            "request": request,
            "auth": auth,
            "invoice": invoice,
            "invoice_items": invoice_items,
            "payment_intents": payment_intents,
        },
    )


@router.get("/parent/profile")
def profile_page(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    from app.models.person import Person

    person = db.get(Person, require_uuid(auth["person_id"]))
    return templates.TemplateResponse(
        "parent/profile/edit.html",
        {"request": request, "auth": auth, "person": person},
    )


@router.post("/parent/profile")
def profile_update(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(""),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    from app.models.person import Person

    person = db.get(Person, require_uuid(auth["person_id"]))
    if person:
        person.first_name = first_name
        person.last_name = last_name
        person.phone = phone if phone else None
        db.commit()
    return RedirectResponse(
        url="/parent/profile?success=Profile+updated", status_code=303
    )


@router.get("/parent/settings")
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    from app.models.person import Person

    person = db.get(Person, require_uuid(auth["person_id"]))
    return templates.TemplateResponse(
        "parent/settings.html",
        {"request": request, "auth": auth, "person": person},
    )


@router.post("/parent/settings/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])

    if new_password != confirm_password:
        return RedirectResponse(
            url="/parent/settings?error=New+passwords+do+not+match",
            status_code=303,
        )

    if len(new_password) < 8:
        return RedirectResponse(
            url="/parent/settings?error=Password+must+be+at+least+8+characters",
            status_code=303,
        )

    credential = db.scalar(
        select(UserCredential).where(UserCredential.person_id == parent_id)
    )
    if not credential:
        return RedirectResponse(
            url="/parent/settings?error=Account+credentials+not+found",
            status_code=303,
        )

    if not verify_password(current_password, credential.password_hash):
        return RedirectResponse(
            url="/parent/settings?error=Current+password+is+incorrect",
            status_code=303,
        )

    credential.password_hash = hash_password(new_password)
    credential.password_updated_at = datetime.now(UTC)
    db.commit()
    logger.info("Password changed for person %s", parent_id)

    return RedirectResponse(
        url="/parent/settings?success=Password+changed+successfully",
        status_code=303,
    )
