"""Admissions calendar service — event management and conflict detection."""

import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admissions import (
    AdmissionsCalendarEvent,
    CalendarEventType,
    SchoolShortlist,
)
from app.models.school import AdmissionForm, School

logger = logging.getLogger(__name__)


class AdmissionsCalendarService:
    """Service for managing admissions calendar events."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_event(
        self,
        parent_id: UUID,
        title: str,
        event_date: date,
        event_type: str = "custom",
        ward_id: UUID | None = None,
        school_id: UUID | None = None,
        shortlist_id: UUID | None = None,
        application_id: UUID | None = None,
        description: str | None = None,
        event_time: str | None = None,
        end_date: date | None = None,
        venue: str | None = None,
        is_reminder_set: bool = True,
        reminder_days_before: int = 3,
        buffer_days_before: int = 1,
        buffer_days_after: int = 0,
    ) -> AdmissionsCalendarEvent:
        event = AdmissionsCalendarEvent(
            parent_id=parent_id,
            ward_id=ward_id,
            school_id=school_id,
            shortlist_id=shortlist_id,
            application_id=application_id,
            event_type=event_type,
            title=title,
            description=description,
            event_date=event_date,
            event_time=event_time,
            end_date=end_date,
            venue=venue,
            is_reminder_set=is_reminder_set,
            reminder_days_before=reminder_days_before,
            buffer_days_before=buffer_days_before,
            buffer_days_after=buffer_days_after,
        )
        self.db.add(event)
        self.db.flush()
        logger.info("Created calendar event %s: %s", event.id, title)
        return event

    def get_by_id(self, event_id: UUID) -> AdmissionsCalendarEvent | None:
        return self.db.get(AdmissionsCalendarEvent, event_id)

    def list_for_parent(
        self,
        parent_id: UUID,
        ward_id: UUID | None = None,
        month: int | None = None,
        year: int | None = None,
    ) -> list[AdmissionsCalendarEvent]:
        stmt = (
            select(AdmissionsCalendarEvent)
            .where(
                AdmissionsCalendarEvent.parent_id == parent_id,
                AdmissionsCalendarEvent.is_active.is_(True),
            )
            .order_by(AdmissionsCalendarEvent.event_date)
        )
        if ward_id:
            stmt = stmt.where(AdmissionsCalendarEvent.ward_id == ward_id)
        if month and year:
            from calendar import monthrange

            start = date(year, month, 1)
            _, last_day = monthrange(year, month)
            end = date(year, month, last_day)
            stmt = stmt.where(
                AdmissionsCalendarEvent.event_date >= start,
                AdmissionsCalendarEvent.event_date <= end,
            )
        return list(self.db.scalars(stmt).all())

    def list_upcoming(
        self, parent_id: UUID, days: int = 30
    ) -> list[AdmissionsCalendarEvent]:
        today = date.today()
        end = today + timedelta(days=days)
        stmt = (
            select(AdmissionsCalendarEvent)
            .where(
                AdmissionsCalendarEvent.parent_id == parent_id,
                AdmissionsCalendarEvent.is_active.is_(True),
                AdmissionsCalendarEvent.event_date >= today,
                AdmissionsCalendarEvent.event_date <= end,
            )
            .order_by(AdmissionsCalendarEvent.event_date)
        )
        return list(self.db.scalars(stmt).all())

    def update_event(
        self,
        event: AdmissionsCalendarEvent,
        **kwargs: object,
    ) -> AdmissionsCalendarEvent:
        allowed_fields = {
            "event_type",
            "title",
            "description",
            "event_date",
            "event_time",
            "end_date",
            "venue",
            "is_reminder_set",
            "reminder_days_before",
            "buffer_days_before",
            "buffer_days_after",
        }
        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                setattr(event, key, value)
        self.db.flush()
        logger.info("Updated calendar event %s", event.id)
        return event

    def delete_event(self, event: AdmissionsCalendarEvent) -> AdmissionsCalendarEvent:
        event.is_active = False
        self.db.flush()
        logger.info("Soft-deleted calendar event %s", event.id)
        return event

    def detect_conflicts(
        self,
        parent_id: UUID,
        events: list[AdmissionsCalendarEvent] | None = None,
    ) -> list[tuple[AdmissionsCalendarEvent, AdmissionsCalendarEvent, str]]:
        """Find overlapping events including cross-ward family-level clashes.

        Returns tuples of (event1, event2, conflict_type) where conflict_type
        is 'same_ward' or 'cross_ward'.
        Pass pre-fetched events to avoid a redundant query.
        """
        if events is None:
            events = list(
                self.db.scalars(
                    select(AdmissionsCalendarEvent)
                    .where(
                        AdmissionsCalendarEvent.parent_id == parent_id,
                        AdmissionsCalendarEvent.is_active.is_(True),
                    )
                    .order_by(AdmissionsCalendarEvent.event_date)
                ).all()
            )

        # Event types that require parent presence (cross-ward conflicts)
        attendance_types = {
            CalendarEventType.exam,
            CalendarEventType.interview,
            CalendarEventType.orientation,
        }

        conflicts: list[
            tuple[AdmissionsCalendarEvent, AdmissionsCalendarEvent, str]
        ] = []
        for i, e1 in enumerate(events):
            e1_start = e1.event_date - timedelta(days=e1.buffer_days_before)
            e1_end = (e1.end_date or e1.event_date) + timedelta(
                days=e1.buffer_days_after
            )
            for e2 in events[i + 1 :]:
                e2_start = e2.event_date - timedelta(days=e2.buffer_days_before)
                e2_end = (e2.end_date or e2.event_date) + timedelta(
                    days=e2.buffer_days_after
                )
                if not (e1_start <= e2_end and e2_start <= e1_end):
                    continue

                if e1.ward_id is not None and e1.ward_id == e2.ward_id:
                    # Same ward: always a conflict
                    conflicts.append((e1, e2, "same_ward"))
                elif (
                    e1.event_type in attendance_types
                    and e2.event_type in attendance_types
                ):
                    # Different wards but parent must attend both
                    conflicts.append((e1, e2, "cross_ward"))
        return conflicts

    def flag_conflicts(self, parent_id: UUID) -> int:
        """Run conflict detection and update has_conflict + conflict_notes."""
        # Reset all conflict flags first
        all_events = list(
            self.db.scalars(
                select(AdmissionsCalendarEvent).where(
                    AdmissionsCalendarEvent.parent_id == parent_id,
                    AdmissionsCalendarEvent.is_active.is_(True),
                )
            ).all()
        )
        for ev in all_events:
            ev.has_conflict = False
            ev.conflict_notes = None

        conflicts = self.detect_conflicts(parent_id, events=all_events)
        for e1, e2, ctype in conflicts:
            label = "Cross-ward overlap" if ctype == "cross_ward" else "Overlaps"
            e1.has_conflict = True
            e1.conflict_notes = f"{label} with: {e2.title} on {e2.event_date}"
            e2.has_conflict = True
            e2.conflict_notes = f"{label} with: {e1.title} on {e1.event_date}"

        self.db.flush()
        logger.info("Flagged %d conflicts for parent %s", len(conflicts), parent_id)
        return len(conflicts)

    def auto_create_from_admission_form(
        self,
        parent_id: UUID,
        shortlist: SchoolShortlist,
        admission_form: AdmissionForm,
    ) -> list[AdmissionsCalendarEvent]:
        """Auto-create calendar events from admission form details."""
        events: list[AdmissionsCalendarEvent] = []
        school: School | None = self.db.get(School, shortlist.school_id)
        school_name = school.name if school else "School"

        # Application deadline
        if admission_form.closes_at:
            ev = self.create_event(
                parent_id=parent_id,
                title=f"Deadline: {school_name} - {admission_form.title}",
                event_date=admission_form.closes_at.date(),
                event_type=CalendarEventType.application_deadline,
                ward_id=shortlist.ward_id,
                school_id=shortlist.school_id,
                shortlist_id=shortlist.id,
            )
            events.append(ev)

        # Exam
        if admission_form.has_entrance_exam and admission_form.exam_date:
            ev = self.create_event(
                parent_id=parent_id,
                title=f"Exam: {school_name}",
                event_date=admission_form.exam_date.date(),
                event_type=CalendarEventType.exam,
                ward_id=shortlist.ward_id,
                school_id=shortlist.school_id,
                shortlist_id=shortlist.id,
                event_time=admission_form.exam_time,
                venue=admission_form.exam_venue,
            )
            events.append(ev)

        # Interview
        if admission_form.interview_date:
            ev = self.create_event(
                parent_id=parent_id,
                title=f"Interview: {school_name}",
                event_date=admission_form.interview_date.date(),
                event_type=CalendarEventType.interview,
                ward_id=shortlist.ward_id,
                school_id=shortlist.school_id,
                shortlist_id=shortlist.id,
                event_time=admission_form.interview_time,
                venue=admission_form.interview_venue,
            )
            events.append(ev)

        return events
