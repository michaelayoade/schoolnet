"""Admissions management models — shortlists and calendar events."""

import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ShortlistStatus(str, enum.Enum):
    researching = "researching"
    shortlisted = "shortlisted"
    applying = "applying"
    applied = "applied"
    accepted = "accepted"
    rejected = "rejected"
    enrolled = "enrolled"
    dropped = "dropped"


class ExamRegistrationStatus(str, enum.Enum):
    not_required = "not_required"
    pending = "pending"
    registered = "registered"


class CalendarEventType(str, enum.Enum):
    application_deadline = "application_deadline"
    exam = "exam"
    interview = "interview"
    orientation = "orientation"
    follow_up = "follow_up"
    custom = "custom"


class SchoolShortlist(Base):
    __tablename__ = "school_shortlists"
    __table_args__ = (
        UniqueConstraint(
            "parent_id",
            "ward_id",
            "school_id",
            name="uq_shortlists_parent_ward_school",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False, index=True
    )
    ward_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wards.id"), nullable=False, index=True
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True
    )

    status: Mapped[ShortlistStatus] = mapped_column(
        Enum(ShortlistStatus), default=ShortlistStatus.researching
    )
    rank: Mapped[int | None] = mapped_column(Integer)

    # Criteria scores (1-5)
    religious_fit: Mapped[int | None] = mapped_column(Integer)
    curriculum_fit: Mapped[int | None] = mapped_column(Integer)
    proximity_score: Mapped[int | None] = mapped_column(Integer)
    special_needs_fit: Mapped[int | None] = mapped_column(Integer)
    overall_fit: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[dict | None] = mapped_column(JSON)
    # [{item: str, done: bool}] — populated from AdmissionForm.exam_requirements
    exam_prep_checklist: Mapped[list | None] = mapped_column(JSON)

    exam_registration_status: Mapped[ExamRegistrationStatus] = mapped_column(
        Enum(ExamRegistrationStatus), default=ExamRegistrationStatus.not_required
    )

    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id")
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    parent = relationship("Person", foreign_keys=[parent_id])
    ward = relationship("Ward", foreign_keys=[ward_id])
    school = relationship("School", back_populates="shortlists")
    application = relationship("Application", foreign_keys=[application_id])


class AdmissionsCalendarEvent(Base):
    __tablename__ = "admissions_calendar_events"
    __table_args__ = (Index("ix_cal_events_parent_date", "parent_id", "event_date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False, index=True
    )
    ward_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wards.id")
    )
    school_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id")
    )
    shortlist_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("school_shortlists.id")
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id")
    )

    event_type: Mapped[CalendarEventType] = mapped_column(
        Enum(CalendarEventType), default=CalendarEventType.custom
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[str | None] = mapped_column(String(50))
    end_date: Mapped[date | None] = mapped_column(Date)
    venue: Mapped[str | None] = mapped_column(String(255))

    is_reminder_set: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=3)
    buffer_days_before: Mapped[int] = mapped_column(Integer, default=1)
    buffer_days_after: Mapped[int] = mapped_column(Integer, default=0)

    has_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_notes: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    parent = relationship("Person", foreign_keys=[parent_id])
    ward = relationship("Ward", foreign_keys=[ward_id])
    school = relationship("School", foreign_keys=[school_id])
    shortlist = relationship("SchoolShortlist", foreign_keys=[shortlist_id])
    application = relationship("Application", foreign_keys=[application_id])
