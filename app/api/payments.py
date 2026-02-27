"""Payment webhook and callback API routes."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.application import ApplicationService
from app.services.payment_gateway import paystack_gateway

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/webhook/paystack")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """Handle Paystack webhook — no auth required, signature verified."""
    if not paystack_gateway.is_configured():
        raise HTTPException(status_code=503, detail="Payment gateway not configured")

    body = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    if not paystack_gateway.validate_webhook_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("event", "")
    event_id = payload.get("data", {}).get("id", str(hash(body)))

    svc = ApplicationService(db)
    svc.handle_webhook(event_type, str(event_id), payload)
    db.commit()

    return {"status": "ok"}


@router.get("/callback")
def payment_callback(
    request: Request,
    reference: str | None = None,
    trxref: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Handle redirect from Paystack after payment."""
    ref = reference or trxref
    if not ref:
        return RedirectResponse(url="/parent/applications?error=No+payment+reference", status_code=303)

    svc = ApplicationService(db)
    application = svc.handle_payment_success(ref)
    db.commit()

    if application:
        return RedirectResponse(
            url=f"/parent/applications/fill/{application.id}?success=Payment+successful.+Fill+your+application.",
            status_code=303,
        )
    return RedirectResponse(url="/parent/applications?success=Payment+processed", status_code=303)
