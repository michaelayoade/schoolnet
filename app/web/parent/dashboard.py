"""Parent portal — dashboard, payments, profile."""

import logging

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.models.billing import Invoice
from app.services.application import ApplicationService
from app.services.common import require_uuid
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
    from app.models.billing import Customer

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
