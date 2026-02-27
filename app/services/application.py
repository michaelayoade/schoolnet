"""Application service — purchase, submission, review, state machine."""

import logging
import secrets
from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.billing import (
    Customer,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    PaymentIntent,
    PaymentIntentStatus,
    WebhookEvent,
    WebhookEventStatus,
)
from app.models.person import Person
from app.models.school import (
    AdmissionForm,
    AdmissionFormStatus,
    Application,
    ApplicationStatus,
    School,
)
from app.services.payment_gateway import paystack_gateway

logger = logging.getLogger(__name__)

# Valid state transitions
VALID_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.draft: {ApplicationStatus.submitted},
    ApplicationStatus.submitted: {ApplicationStatus.under_review, ApplicationStatus.withdrawn},
    ApplicationStatus.under_review: {ApplicationStatus.accepted, ApplicationStatus.rejected},
    ApplicationStatus.accepted: set(),
    ApplicationStatus.rejected: set(),
    ApplicationStatus.withdrawn: set(),
}


def _generate_application_number(persist_application: Callable[[str], None] | None = None) -> str:
    """Generate an application number, retrying on collisions when a persist callback is supplied."""
    last_collision_error: IntegrityError | None = None

    for attempt in range(1, 6):
        year = datetime.now(UTC).year
        suffix = secrets.token_hex(3)[:5]
        application_number = f"SCH-{year}-{suffix}"

        if persist_application is None:
            return application_number

        try:
            persist_application(application_number)
            return application_number
        except IntegrityError as error:
            if not _is_application_number_collision(error):
                raise
            last_collision_error = error
            logger.warning("Application number collision on attempt %d/5", attempt)

    raise RuntimeError(
        "Failed to generate a unique application number after 5 attempts"
    ) from last_collision_error


def _is_application_number_collision(error: IntegrityError) -> bool:
    """Return True when IntegrityError is a duplicate application number."""
    original = getattr(error, "orig", None)
    diag = getattr(original, "diag", None)
    if getattr(diag, "constraint_name", None) == "uq_applications_number":
        return True

    message = str(original or error).lower()
    return "uq_applications_number" in message or "applications.application_number" in message


def _generate_reference() -> str:
    return f"SN-{secrets.token_hex(12)}"


class ApplicationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _create_application_with_retry(
        self,
        *,
        admission_form_id: UUID,
        parent_id: UUID,
        invoice_id: UUID | None,
    ) -> Application:
        """Create an application and retry on application-number collisions."""
        application: Application | None = None

        def _persist_application(application_number: str) -> None:
            nonlocal application
            candidate = Application(
                admission_form_id=admission_form_id,
                parent_id=parent_id,
                invoice_id=invoice_id,
                application_number=application_number,
                status=ApplicationStatus.draft,
            )
            # Savepoint prevents rolling back the whole transaction on one duplicate key.
            with self.db.begin_nested():
                self.db.add(candidate)
                self.db.flush()
            application = candidate

        _generate_application_number(_persist_application)
        if application is None:
            raise RuntimeError("Failed to create application after generating a number")
        return application

    # ── Purchase flow ────────────────────────────────────

    def _get_or_create_customer(self, person: Person) -> Customer:
        stmt = select(Customer).where(Customer.person_id == person.id)
        existing: Customer | None = self.db.scalar(stmt)
        if existing:
            return existing
        customer = Customer(
            person_id=person.id,
            name=f"{person.first_name} {person.last_name}".strip(),
            email=person.email,
            currency=settings.schoolnet_currency,
        )
        self.db.add(customer)
        self.db.flush()
        logger.info("Created customer: %s for person %s", customer.id, person.id)
        return customer

    def initiate_purchase(
        self,
        parent_id: UUID,
        admission_form_id: UUID,
        callback_url: str,
    ) -> dict:
        """Initialize form purchase: create billing records + Paystack transaction."""
        person = self.db.get(Person, parent_id)
        if not person:
            raise ValueError("Parent not found")

        form = self.db.get(AdmissionForm, admission_form_id)
        if not form:
            raise ValueError("Admission form not found")
        if form.status != AdmissionFormStatus.active:
            raise ValueError("This form is not currently accepting applications")
        if form.max_submissions and form.current_submissions >= form.max_submissions:
            raise ValueError("This form has reached maximum submissions")

        # Get price
        from app.models.billing import Price

        price = self.db.get(Price, form.price_id) if form.price_id else None
        if not price:
            raise ValueError("Form price not configured")
        amount = price.unit_amount  # in kobo

        # Get school for subaccount
        school = self.db.get(School, form.school_id)

        # Create/get customer
        customer = self._get_or_create_customer(person)

        # Create invoice
        reference = _generate_reference()
        invoice = Invoice(
            customer_id=customer.id,
            number=reference,
            status=InvoiceStatus.open,
            currency=settings.schoolnet_currency,
            subtotal=amount,
            total=amount,
            amount_due=amount,
            metadata_={
                "admission_form_id": str(admission_form_id),
                "school_id": str(form.school_id),
            },
        )
        self.db.add(invoice)
        self.db.flush()

        # Create invoice item
        invoice_item = InvoiceItem(
            invoice_id=invoice.id,
            price_id=price.id,
            description=f"Admission form: {form.title}",
            quantity=1,
            unit_amount=amount,
            amount=amount,
        )
        self.db.add(invoice_item)

        # Create payment intent
        payment_intent = PaymentIntent(
            customer_id=customer.id,
            invoice_id=invoice.id,
            amount=amount,
            currency=settings.schoolnet_currency,
            status=PaymentIntentStatus.requires_payment_method,
            external_id=reference,
            metadata_={
                "admission_form_id": str(admission_form_id),
                "parent_id": str(parent_id),
            },
        )
        self.db.add(payment_intent)
        self.db.flush()

        # Initialize Paystack transaction
        paystack_data = {}
        if paystack_gateway.is_configured():
            try:
                paystack_data = paystack_gateway.initialize_transaction(
                    amount=amount,
                    email=person.email,
                    reference=reference,
                    callback_url=callback_url,
                    subaccount_code=school.paystack_subaccount_code if school else None,
                    bearer="account",
                )
                payment_intent.status = PaymentIntentStatus.requires_action
            except (ValueError, RuntimeError) as e:
                logger.error("Paystack init failed: %s", e)
                raise ValueError(f"Payment initialization failed: {e}")
        else:
            # Dev mode: skip Paystack, mark as succeeded
            payment_intent.status = PaymentIntentStatus.succeeded
            invoice.status = InvoiceStatus.paid
            invoice.paid_at = datetime.now(UTC)
            invoice.amount_paid = amount
            invoice.amount_due = 0
            # Create application directly in dev mode
            application = self._create_application_with_retry(
                admission_form_id=admission_form_id,
                parent_id=parent_id,
                invoice_id=invoice.id,
            )
            form.current_submissions += 1
            paystack_data = {"authorization_url": f"/parent/applications/fill/{application.id}"}

        self.db.flush()
        logger.info("Initiated purchase: ref=%s, parent=%s, form=%s", reference, parent_id, admission_form_id)

        return {
            "reference": reference,
            "invoice_id": str(invoice.id),
            "payment_intent_id": str(payment_intent.id),
            "authorization_url": paystack_data.get("authorization_url", ""),
            "access_code": paystack_data.get("access_code", ""),
        }

    def handle_payment_success(self, reference: str, paystack_data: dict | None = None) -> Application | None:
        """Process successful payment — update billing records, create draft application."""
        # Find payment intent by reference
        stmt = select(PaymentIntent).where(PaymentIntent.external_id == reference)
        payment_intent = self.db.scalar(stmt)
        if not payment_intent:
            logger.warning("Payment intent not found for ref: %s", reference)
            return None

        if payment_intent.status == PaymentIntentStatus.succeeded:
            logger.info("Payment already processed: %s", reference)
            # Find existing application
            stmt2 = select(Application).where(Application.invoice_id == payment_intent.invoice_id)
            existing_app: Application | None = self.db.scalar(stmt2)
            return existing_app

        # Update payment intent
        payment_intent.status = PaymentIntentStatus.succeeded

        # Update invoice
        if payment_intent.invoice_id:
            invoice = self.db.get(Invoice, payment_intent.invoice_id)
            if invoice:
                invoice.status = InvoiceStatus.paid
                invoice.paid_at = datetime.now(UTC)
                invoice.amount_paid = invoice.total
                invoice.amount_due = 0

        # Get form info from metadata
        meta = payment_intent.metadata_ or {}
        admission_form_id = meta.get("admission_form_id")
        parent_id = meta.get("parent_id")
        if not admission_form_id or not parent_id:
            logger.error("Missing metadata on payment intent %s", payment_intent.id)
            return None

        from app.services.common import coerce_uuid

        form_uuid = coerce_uuid(admission_form_id)
        parent_uuid = coerce_uuid(parent_id)

        # Create application
        application = self._create_application_with_retry(
            admission_form_id=form_uuid,
            parent_id=parent_uuid,
            invoice_id=payment_intent.invoice_id,
        )

        # Increment form submissions
        form = self.db.get(AdmissionForm, form_uuid)
        if form:
            form.current_submissions += 1

        self.db.flush()
        logger.info("Payment success: created application %s for ref %s", application.id, reference)
        return application

    # ── Application lifecycle ────────────────────────────

    def get_by_id(self, app_id: UUID) -> Application | None:
        application: Application | None = self.db.get(Application, app_id)
        return application

    def submit(
        self,
        application: Application,
        ward_first_name: str,
        ward_last_name: str,
        ward_date_of_birth: date,
        ward_gender: str,
        form_responses: dict | None = None,
        document_urls: list[str] | None = None,
        ward_passport_url: str | None = None,
    ) -> Application:
        """Fill and submit an application (draft → submitted)."""
        self._validate_transition(application.status, ApplicationStatus.submitted)

        application.ward_first_name = ward_first_name
        application.ward_last_name = ward_last_name
        application.ward_date_of_birth = ward_date_of_birth
        application.ward_gender = ward_gender
        application.form_responses = form_responses
        application.document_urls = document_urls
        application.ward_passport_url = ward_passport_url
        application.status = ApplicationStatus.submitted
        application.submitted_at = datetime.now(UTC)

        self.db.flush()
        logger.info("Application submitted: %s", application.id)
        return application

    def review(
        self,
        application: Application,
        decision: str,
        reviewer_id: UUID,
        review_notes: str | None = None,
    ) -> Application:
        """Review an application (submitted/under_review → accepted/rejected)."""
        # First transition to under_review if not already
        if application.status == ApplicationStatus.submitted:
            self._validate_transition(application.status, ApplicationStatus.under_review)
            application.status = ApplicationStatus.under_review

        target = ApplicationStatus.accepted if decision == "accepted" else ApplicationStatus.rejected
        self._validate_transition(application.status, target)

        application.status = target
        application.reviewed_at = datetime.now(UTC)
        application.reviewed_by = reviewer_id
        application.review_notes = review_notes

        self.db.flush()
        logger.info("Application %s: %s by %s", application.id, decision, reviewer_id)
        return application

    def withdraw(self, application: Application) -> Application:
        """Withdraw an application (submitted → withdrawn)."""
        self._validate_transition(application.status, ApplicationStatus.withdrawn)
        application.status = ApplicationStatus.withdrawn
        self.db.flush()
        logger.info("Application withdrawn: %s", application.id)
        return application

    def _validate_transition(self, current: ApplicationStatus, target: ApplicationStatus) -> None:
        allowed = VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(f"Cannot transition from {current.value} to {target.value}")

    # ── Queries ──────────────────────────────────────────

    def list_for_parent(self, parent_id: UUID) -> list[Application]:
        stmt = (
            select(Application)
            .where(Application.parent_id == parent_id, Application.is_active.is_(True))
            .order_by(Application.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_for_school(self, school_id: UUID) -> list[Application]:
        form_ids_stmt = select(AdmissionForm.id).where(AdmissionForm.school_id == school_id)
        stmt = (
            select(Application)
            .where(
                Application.admission_form_id.in_(form_ids_stmt),
                Application.is_active.is_(True),
            )
            .order_by(Application.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def handle_webhook(self, event_type: str, event_id: str, payload: dict) -> None:
        """Process a Paystack webhook event."""
        # Store webhook
        webhook = WebhookEvent(
            provider="paystack",
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            status=WebhookEventStatus.pending,
        )
        self.db.add(webhook)
        self.db.flush()

        if event_type == "charge.success":
            reference = payload.get("data", {}).get("reference")
            if reference:
                self.handle_payment_success(reference, payload.get("data"))
                webhook.status = WebhookEventStatus.processed
                webhook.processed_at = datetime.now(UTC)
            else:
                webhook.status = WebhookEventStatus.failed
                webhook.error_message = "No reference in payload"
        else:
            webhook.status = WebhookEventStatus.processed
            webhook.processed_at = datetime.now(UTC)

        self.db.flush()
        logger.info("Processed webhook: %s %s", event_type, event_id)
