"""Celery task for daily admissions event reminders."""

import logging
from datetime import date, timedelta
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def send_daily_admissions_reminders_task(self) -> dict:
    """Scan upcoming admissions events and send reminder notifications.

    Runs daily via Celery beat. For each event where:
    - is_reminder_set is True
    - event_date minus reminder_days_before equals today
    Creates an in-app notification and queues a reminder email.
    """
    db: Session | None = None
    sent_count = 0
    try:
        db = SessionLocal()
        from app.models.admissions import AdmissionsCalendarEvent
        from app.models.person import Person
        from app.schemas.notification import NotificationCreate
        from app.services.notification import NotificationService

        today = date.today()
        notif_svc = NotificationService(db)

        # Find events whose reminder date is today
        # event_date - reminder_days_before = today
        # → event_date = today + reminder_days_before
        # We check a range of reminder_days (1–30) to be safe
        events = list(
            db.scalars(
                select(AdmissionsCalendarEvent).where(
                    AdmissionsCalendarEvent.is_active.is_(True),
                    AdmissionsCalendarEvent.is_reminder_set.is_(True),
                    AdmissionsCalendarEvent.event_date >= today,
                    AdmissionsCalendarEvent.event_date <= today + timedelta(days=30),
                )
            ).all()
        )

        for event in events:
            reminder_date = event.event_date - timedelta(
                days=event.reminder_days_before
            )
            if reminder_date != today:
                continue

            days_until = (event.event_date - today).days
            parent = db.get(Person, event.parent_id)
            if not parent:
                continue

            # Build notification
            event_type_label = (
                event.event_type.value.replace("_", " ").title()
                if hasattr(event.event_type, "value")
                else str(event.event_type).replace("_", " ").title()
            )
            title = f"Reminder: {event.title} in {days_until} day{'s' if days_until != 1 else ''}"
            message = f"{event_type_label} on {event.event_date}"
            if event.event_time:
                message += f" at {event.event_time}"
            if event.venue:
                message += f" — {event.venue}"

            notif_svc.create(
                NotificationCreate(
                    recipient_id=event.parent_id,
                    title=title,
                    message=message,
                    type="warning",
                    entity_type="admissions_calendar_event",
                    entity_id=str(event.id),
                    action_url="/parent/calendar",
                )
            )
            sent_count += 1

            # Queue email if parent has an email
            if parent.email:
                from app.tasks.notifications import send_notification_email_task

                email_html = (
                    f"<p>Dear {escape(parent.first_name if parent.first_name else 'Parent')},</p>"
                    f"<p>This is a reminder that <strong>{escape(event.title)}</strong> "
                    f"is coming up on <strong>{event.event_date}</strong>"
                )
                if event.event_time:
                    email_html += f" at <strong>{escape(event.event_time)}</strong>"
                if event.venue:
                    email_html += f" at <strong>{escape(event.venue)}</strong>"
                email_html += (
                    ".</p><p>Log in to your SchoolNet account for details.</p>"
                )

                send_notification_email_task.delay(
                    recipient_email=parent.email,
                    subject=title,
                    body_html=email_html,
                )

        db.commit()
        logger.info("Sent %d admissions reminders", sent_count)
        return {"sent": sent_count, "scanned": len(events)}

    except (OSError, ConnectionError) as exc:
        logger.warning("Admissions reminders task failed (retrying): %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
    finally:
        if db:
            db.close()
