from app.tasks.admissions_reminders import (
    send_daily_admissions_reminders_task,
)
from app.tasks.ads import expire_stale_ads_task
from app.tasks.notifications import (
    archive_old_notifications_task,
    send_application_status_email_task,
    send_new_application_email_task,
    send_notification_email_task,
    send_payment_receipt_email_task,
)

__all__: list[str] = [
    "expire_stale_ads_task",
    "archive_old_notifications_task",
    "send_notification_email_task",
    "send_application_status_email_task",
    "send_payment_receipt_email_task",
    "send_new_application_email_task",
    "send_daily_admissions_reminders_task",
]
