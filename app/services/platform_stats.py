"""Platform-wide statistics for the admin dashboard."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.billing import Invoice, InvoiceStatus
from app.models.file_upload import FileUpload, FileUploadStatus
from app.models.notification import Notification
from app.models.person import Person
from app.models.rbac import Role
from app.models.scheduler import ScheduledTask
from app.models.school import Application, School, SchoolStatus

logger = logging.getLogger(__name__)


class PlatformStatsService:
    """Gathers platform-wide statistics for the admin dashboard."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_dashboard_stats(self, person_id: UUID) -> dict:
        """Return all dashboard stat counts."""
        people = self._count(select(func.count()).select_from(Person))
        roles = self._count(select(func.count()).select_from(Role))
        tasks = self._count(
            select(func.count())
            .select_from(ScheduledTask)
            .where(ScheduledTask.enabled.is_(True))
        )
        uploads = self._count(
            select(func.count())
            .select_from(FileUpload)
            .where(FileUpload.status == FileUploadStatus.active)
        )
        audit = self._count(select(func.count()).select_from(AuditEvent))
        notifications = self._count(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == person_id,
                Notification.is_read.is_(False),
                Notification.is_active.is_(True),
            )
        )

        total_schools = self._count(
            select(func.count()).select_from(School).where(School.is_active.is_(True))
        )
        active_schools = self._count(
            select(func.count())
            .select_from(School)
            .where(School.status == SchoolStatus.active, School.is_active.is_(True))
        )
        pending_schools = self._count(
            select(func.count())
            .select_from(School)
            .where(School.status == SchoolStatus.pending, School.is_active.is_(True))
        )
        total_applications = self._count(
            select(func.count())
            .select_from(Application)
            .where(Application.is_active.is_(True))
        )
        total_revenue: int = (
            self.db.execute(
                select(func.coalesce(func.sum(Invoice.amount_paid), 0)).where(
                    Invoice.status == InvoiceStatus.paid,
                )
            ).scalar()
            or 0
        )

        return {
            "people": people,
            "roles": roles,
            "tasks": tasks,
            "uploads": uploads,
            "audit": audit,
            "notifications": notifications,
            "total_schools": total_schools,
            "active_schools": active_schools,
            "pending_schools": pending_schools,
            "total_applications": total_applications,
            "total_revenue": total_revenue,
        }

    def _count(self, stmt) -> int:  # type: ignore[type-arg]
        return self.db.execute(stmt).scalar() or 0
