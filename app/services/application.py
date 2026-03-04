"""Application service — purchase, submission, review, state machine."""

import logging
import math
import secrets
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

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
from app.services.common import coerce_uuid, escape_like
from app.services.file_upload import FileUploadService
from app.services.payment_gateway import paystack_gateway
from app.services.ward import WardService

logger = logging.getLogger(__name__)

# Valid state transitions
VALID_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.draft: {ApplicationStatus.submitted},
    ApplicationStatus.submitted: {
        ApplicationStatus.under_review,
        ApplicationStatus.withdrawn,
    },
    ApplicationStatus.under_review: {
        ApplicationStatus.accepted,
        ApplicationStatus.rejected,
    },
    ApplicationStatus.accepted: set(),
    ApplicationStatus.rejected: set(),
    ApplicationStatus.withdrawn: set(),
}


def _generate_application_number(db: Session) -> str:
    """Generate a unique application number like SCH-2026-XXXXX."""
    for _ in range(10):
        year = datetime.now(UTC).year
        suffix = secrets.token_hex(4).upper()[:6]
        number = f"SCH-{year}-{suffix}"
        existing = db.scalar(
            select(Application).where(Application.application_number == number)
        )
        if not existing:
            return number
    raise RuntimeError("Failed to generate unique application number")


def _generate_reference() -> str:
    return f"SN-{secrets.token_hex(12)}"


class ApplicationService:
    def __init__(self, db: Session) -> None:
        self.db = db

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
                raise ValueError("Payment initialization failed. Please try again later.")
        else:
            # Dev mode: skip Paystack, mark as succeeded
            payment_intent.status = PaymentIntentStatus.succeeded
            invoice.status = InvoiceStatus.paid
            invoice.paid_at = datetime.now(UTC)
            invoice.amount_paid = amount
            invoice.amount_due = 0
            # Create application directly in dev mode
            app_number = _generate_application_number(self.db)
            application = Application(
                admission_form_id=admission_form_id,
                parent_id=parent_id,
                invoice_id=invoice.id,
                application_number=app_number,
                status=ApplicationStatus.draft,
            )
            self.db.add(application)
            form.current_submissions += 1
            self.db.flush()
            paystack_data = {
                "authorization_url": f"/parent/applications/fill/{application.id}"
            }

        self.db.flush()
        logger.info(
            "Initiated purchase: ref=%s, parent=%s, form=%s",
            reference,
            parent_id,
            admission_form_id,
        )

        return {
            "reference": reference,
            "invoice_id": str(invoice.id),
            "payment_intent_id": str(payment_intent.id),
            "authorization_url": paystack_data.get("authorization_url", ""),
            "access_code": paystack_data.get("access_code", ""),
        }

    def handle_payment_success(
        self, reference: str, paystack_data: dict | None = None
    ) -> Application | None:
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
            stmt2 = select(Application).where(
                Application.invoice_id == payment_intent.invoice_id
            )
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
        app_number = _generate_application_number(self.db)
        application = Application(
            admission_form_id=form_uuid,
            parent_id=parent_uuid,
            invoice_id=payment_intent.invoice_id,
            application_number=app_number,
            status=ApplicationStatus.draft,
        )
        self.db.add(application)

        # Increment form submissions
        form = self.db.get(AdmissionForm, form_uuid)
        if form:
            form.current_submissions += 1

        self.db.flush()
        logger.info(
            "Payment success: created application %s for ref %s",
            application.id,
            reference,
        )

        # Notify school owner of payment received
        try:
            from app.services.notification import NotificationService

            notif_svc = NotificationService(self.db)
            if form and form.school and form.school.owner_id:
                parent = self.db.get(Person, parent_uuid)
                parent_name = (
                    f"{parent.first_name} {parent.last_name}" if parent else "A parent"
                )
                amount_str = str(payment_intent.amount / 100)
                notif_svc.notify_payment_received(
                    school_owner_id=form.school.owner_id,
                    parent_name=parent_name,
                    school_name=form.school.name,
                    amount=amount_str,
                )
        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning("Failed to send payment notification: %s", e)

        # Queue payment receipt email via Celery
        try:
            from app.tasks.notifications import send_payment_receipt_email_task

            parent = self.db.get(Person, parent_uuid)
            if parent and parent.email:
                parent_name = (
                    f"{parent.first_name} {parent.last_name}".strip()
                    if parent.first_name
                    else "Parent"
                )
                school_name = form.school.name if form and form.school else "the school"
                send_payment_receipt_email_task.delay(
                    recipient_email=parent.email,
                    parent_name=parent_name,
                    amount=str(payment_intent.amount / 100),
                    reference=reference,
                    school_name=school_name,
                )
        except Exception as e:
            logger.warning("Failed to queue payment receipt email: %s", e)

        return application

    # ── Application lifecycle ────────────────────────────

    def get_by_id(self, app_id: UUID) -> Application | None:
        application: Application | None = self.db.get(Application, app_id)
        return application

    @staticmethod
    def _form_text_value(form_data: Mapping[str, Any], key: str) -> str:
        value = form_data.get(key)
        if value is None or isinstance(value, UploadFile):
            return ""
        return str(value)

    def resolve_ward_profile(
        self, form_data: Mapping[str, Any], parent_id: UUID
    ) -> tuple[str, str, date, str]:
        """Resolve ward data from selected ward_id or raw form fields."""
        ward_first_name = self._form_text_value(form_data, "ward_first_name")
        ward_last_name = self._form_text_value(form_data, "ward_last_name")
        ward_date_of_birth = self._form_text_value(form_data, "ward_date_of_birth")
        ward_gender = self._form_text_value(form_data, "ward_gender")

        ward_id_raw = form_data.get("ward_id")
        ward_id = str(ward_id_raw) if ward_id_raw is not None else ""
        ward_uuid = coerce_uuid(ward_id)
        if ward_uuid:
            ward = WardService(self.db).get_by_id(ward_uuid)
            if ward and ward.parent_id == parent_id and ward.is_active:
                ward_first_name = ward.first_name
                ward_last_name = ward.last_name
                ward_date_of_birth = (
                    ward.date_of_birth.isoformat() if ward.date_of_birth else ""
                )
                ward_gender = ward.gender or ""

        try:
            dob = date.fromisoformat(ward_date_of_birth)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid date of birth") from exc

        return ward_first_name, ward_last_name, dob, ward_gender

    def collect_form_responses(self, form_data: Mapping[str, Any]) -> dict[str, str]:
        responses: dict[str, str] = {}
        for key in form_data:
            if key.startswith("field_"):
                field_name = key[6:]
                responses[field_name] = str(form_data[key])
        return responses

    def collect_document_upload_urls(
        self,
        form_data: Mapping[str, Any],
        application: Application,
        parent_id: UUID,
    ) -> dict[str, str]:
        urls: dict[str, str] = dict(application.document_urls or {})
        upload_svc = FileUploadService(self.db)
        for key in form_data:
            if not key.startswith("doc_"):
                continue
            doc_name = key[4:]
            value = form_data[key]
            if not isinstance(value, UploadFile) or not value.filename:
                continue
            content = value.file.read()
            record = upload_svc.upload(
                content=content,
                filename=value.filename,
                content_type=value.content_type or "application/octet-stream",
                uploaded_by=parent_id,
                category="application_document",
                entity_type="application",
                entity_id=str(application.id),
            )
            urls[doc_name] = record.url or ""
        return urls

    def verify_document(
        self,
        application: Application,
        *,
        doc_name: str,
        doc_status: str,
    ) -> None:
        """Mark a document as verified, rejected, or pending."""
        if doc_status not in ("verified", "rejected", "pending"):
            raise ValueError(f"Invalid document status: {doc_status}")

        metadata = application.metadata_ or {}
        doc_statuses: dict = metadata.get("document_statuses", {})
        doc_statuses[doc_name] = {"status": doc_status}
        metadata["document_statuses"] = doc_statuses
        application.metadata_ = metadata
        self.db.flush()
        logger.info(
            "Document %s marked as %s for app %s",
            doc_name,
            doc_status,
            application.id,
        )

    def submit(
        self,
        application: Application,
        ward_first_name: str,
        ward_last_name: str,
        ward_date_of_birth: date,
        ward_gender: str,
        form_responses: dict | None = None,
        document_urls: dict[str, str] | None = None,
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

        # Notify school admin of new submission
        try:
            from app.services.notification import NotificationService

            notif_svc = NotificationService(self.db)
            form = application.admission_form
            if form and form.school and form.school.owner_id:
                parent = self.db.get(Person, application.parent_id)
                parent_name = (
                    f"{parent.first_name} {parent.last_name}" if parent else "A parent"
                )
                notif_svc.notify_application_submitted(
                    school_owner_id=form.school.owner_id,
                    application_number=application.application_number,
                    parent_name=parent_name,
                    school_name=form.school.name,
                )
        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning("Failed to send submission notification: %s", e)

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
            self._validate_transition(
                application.status, ApplicationStatus.under_review
            )
            application.status = ApplicationStatus.under_review

        target = (
            ApplicationStatus.accepted
            if decision == "accepted"
            else ApplicationStatus.rejected
        )
        self._validate_transition(application.status, target)

        application.status = target
        application.reviewed_at = datetime.now(UTC)
        application.reviewed_by = reviewer_id
        application.review_notes = review_notes

        self.db.flush()
        logger.info("Application %s: %s by %s", application.id, decision, reviewer_id)

        # Notify parent of decision
        try:
            from app.services.notification import NotificationService

            notif_svc = NotificationService(self.db)
            form = application.admission_form
            school_name = form.school.name if form and form.school else "the school"
            notif_svc.notify_application_reviewed(
                parent_id=application.parent_id,
                application_number=application.application_number,
                decision=decision,
                school_name=school_name,
            )
        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning("Failed to send review notification: %s", e)

        # Queue application status email via Celery
        try:
            from app.tasks.notifications import send_application_status_email_task

            parent = self.db.get(Person, application.parent_id)
            if parent and parent.email:
                parent_name = (
                    f"{parent.first_name} {parent.last_name}".strip()
                    if parent.first_name
                    else "Parent"
                )
                form = application.admission_form
                school_name = (
                    form.school.name if form and form.school else "the school"
                )
                send_application_status_email_task.delay(
                    recipient_email=parent.email,
                    parent_name=parent_name,
                    application_number=application.application_number,
                    decision=decision,
                    school_name=school_name,
                )
        except Exception as e:
            logger.warning("Failed to queue review status email: %s", e)

        return application

    def withdraw(self, application: Application) -> Application:
        """Withdraw an application (submitted → withdrawn)."""
        self._validate_transition(application.status, ApplicationStatus.withdrawn)
        application.status = ApplicationStatus.withdrawn
        self.db.flush()
        logger.info("Application withdrawn: %s", application.id)
        return application

    def _validate_transition(
        self, current: ApplicationStatus, target: ApplicationStatus
    ) -> None:
        allowed = VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"Cannot transition from {current.value} to {target.value}"
            )

    # ── Queries ──────────────────────────────────────────

    def list_for_parent(self, parent_id: UUID) -> list[Application]:
        stmt = (
            select(Application)
            .where(Application.parent_id == parent_id, Application.is_active.is_(True))
            .order_by(Application.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_for_school(
        self,
        school_id: UUID,
        *,
        status: ApplicationStatus | None = None,
        form_id: UUID | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List applications for a school with filtering, search, and pagination."""
        form_ids_stmt = select(AdmissionForm.id).where(
            AdmissionForm.school_id == school_id
        )
        stmt = select(Application).where(
            Application.admission_form_id.in_(form_ids_stmt),
            Application.is_active.is_(True),
        )

        if status is not None:
            stmt = stmt.where(Application.status == status)
        if form_id is not None:
            stmt = stmt.where(Application.admission_form_id == form_id)
        if search:
            term = f"%{escape_like(search.strip())}%"
            stmt = stmt.where(
                or_(
                    Application.ward_first_name.ilike(term),
                    Application.ward_last_name.ilike(term),
                    Application.application_number.ilike(term),
                )
            )

        stmt = stmt.order_by(Application.created_at.desc())

        total: int = (
            self.db.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
            or 0
        )

        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        items = list(self.db.scalars(stmt.limit(page_size).offset(offset)).all())

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": math.ceil(total / page_size) if page_size else 0,
        }

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
