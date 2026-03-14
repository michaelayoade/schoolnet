"""Celery tasks for email and notification delivery."""

import logging
from html import escape

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def send_notification_email_task(
    self,
    recipient_email: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
) -> dict:
    """Send an email notification via SMTP. Retries on transient failures."""
    db: Session | None = None
    try:
        db = SessionLocal()
        from app.services.email import send_email

        success = send_email(db, recipient_email, subject, body_html, body_text)
        logger.info(
            "Notification email %s to %s",
            "sent" if success else "failed",
            recipient_email,
        )
        return {"success": success, "recipient": recipient_email}
    except (OSError, ConnectionError) as exc:
        logger.warning("Email send failed (retrying): %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
    finally:
        if db:
            db.close()


@celery_app.task(bind=True, max_retries=3)
def send_application_status_email_task(
    self,
    recipient_email: str,
    parent_name: str,
    application_number: str,
    decision: str,
    school_name: str,
) -> dict:
    """Send application review decision email to parent."""
    db: Session | None = None
    try:
        db = SessionLocal()
        from app.services.email import send_email

        status_text = "accepted" if decision == "accepted" else "not accepted"
        subject = f"Application {escape(application_number)} - {status_text.title()}"
        body_html = (
            f"<p>Dear {escape(parent_name)},</p>"
            f"<p>Your application <strong>{escape(application_number)}</strong> to "
            f"<strong>{escape(school_name)}</strong> has been "
            f"<strong>{escape(status_text)}</strong>.</p>"
            f"<p>Please log in to your SchoolNet account for more details.</p>"
        )
        success = send_email(db, recipient_email, subject, body_html)
        logger.info(
            "Application status email sent to %s: %s %s",
            recipient_email,
            application_number,
            decision,
        )
        return {"success": success, "recipient": recipient_email}
    except (OSError, ConnectionError) as exc:
        logger.warning("Application status email failed (retrying): %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
    finally:
        if db:
            db.close()


@celery_app.task(bind=True, max_retries=3)
def send_payment_receipt_email_task(
    self,
    recipient_email: str,
    parent_name: str,
    amount: str,
    reference: str,
    school_name: str,
) -> dict:
    """Send payment receipt email to parent."""
    db: Session | None = None
    try:
        db = SessionLocal()
        from app.services.email import send_email

        subject = f"Payment Receipt - {escape(reference)}"
        body_html = (
            f"<p>Dear {escape(parent_name)},</p>"
            f"<p>Your payment of <strong>&#8358;{escape(amount)}</strong> "
            f"for an admission form at <strong>{escape(school_name)}</strong> "
            f"has been received.</p>"
            f"<p>Reference: <strong>{escape(reference)}</strong></p>"
            f"<p>You can now fill out your application in your SchoolNet account.</p>"
        )
        success = send_email(db, recipient_email, subject, body_html)
        logger.info(
            "Payment receipt email sent to %s: ref=%s",
            recipient_email,
            reference,
        )
        return {"success": success, "recipient": recipient_email}
    except (OSError, ConnectionError) as exc:
        logger.warning("Payment receipt email failed (retrying): %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
    finally:
        if db:
            db.close()


@celery_app.task(bind=True, max_retries=3)
def archive_old_notifications_task(self) -> dict:
    """Archive notifications older than 90 days."""
    db: Session | None = None
    try:
        db = SessionLocal()
        from app.services.notification import NotificationService

        svc = NotificationService(db)
        count = svc.archive_old(days=90)
        db.commit()
        logger.info("archive_old_notifications_task completed: %d archived", count)
        return {"success": True, "archived_count": count}
    except (OSError, ConnectionError) as exc:
        logger.warning("archive_old_notifications_task failed (retrying): %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
    finally:
        if db:
            db.close()


@celery_app.task(bind=True, max_retries=3)
def send_new_application_email_task(
    self,
    recipient_email: str,
    school_admin_name: str,
    application_number: str,
    parent_name: str,
    school_name: str,
) -> dict:
    """Notify school admin of a new application submission via email."""
    db: Session | None = None
    try:
        db = SessionLocal()
        from app.services.email import send_email

        subject = f"New Application: {escape(application_number)}"
        body_html = (
            f"<p>Dear {escape(school_admin_name)},</p>"
            f"<p><strong>{escape(parent_name)}</strong> has submitted a new "
            f"application (<strong>{escape(application_number)}</strong>) to "
            f"<strong>{escape(school_name)}</strong>.</p>"
            f"<p>Please log in to review the application.</p>"
        )
        success = send_email(db, recipient_email, subject, body_html)
        logger.info(
            "New application email sent to %s: %s",
            recipient_email,
            application_number,
        )
        return {"success": success, "recipient": recipient_email}
    except (OSError, ConnectionError) as exc:
        logger.warning("New application email failed (retrying): %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
    finally:
        if db:
            db.close()
