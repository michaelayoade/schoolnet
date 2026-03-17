"""Schemas for admissions management — shortlists, calendar, tracking."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Shortlist ───────────────────────────────────────────


class ShortlistCreate(BaseModel):
    ward_id: UUID
    school_id: UUID
    status: str = "researching"
    rank: int | None = None
    notes: dict | None = None


class ShortlistUpdate(BaseModel):
    status: str | None = None
    rank: int | None = None
    religious_fit: int | None = Field(default=None, ge=1, le=5)
    curriculum_fit: int | None = Field(default=None, ge=1, le=5)
    proximity_score: int | None = Field(default=None, ge=1, le=5)
    special_needs_fit: int | None = Field(default=None, ge=1, le=5)
    overall_fit: int | None = Field(default=None, ge=1, le=5)
    notes: dict | None = None
    exam_registration_status: str | None = None
    exam_prep_checklist: list | None = None


class ShortlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: UUID
    ward_id: UUID
    school_id: UUID
    status: str
    rank: int | None = None
    religious_fit: int | None = None
    curriculum_fit: int | None = None
    proximity_score: int | None = None
    special_needs_fit: int | None = None
    overall_fit: int | None = None
    notes: dict | None = None
    exam_prep_checklist: list | None = None
    exam_registration_status: str = "not_required"
    application_id: UUID | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


# ── Calendar Event ──────────────────────────────────────


class CalendarEventCreate(BaseModel):
    ward_id: UUID | None = None
    school_id: UUID | None = None
    shortlist_id: UUID | None = None
    application_id: UUID | None = None
    event_type: str = "custom"
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    event_date: date
    event_time: str | None = None
    end_date: date | None = None
    venue: str | None = None
    is_reminder_set: bool = True
    reminder_days_before: int = 3
    buffer_days_before: int = 1
    buffer_days_after: int = 0


class CalendarEventUpdate(BaseModel):
    event_type: str | None = None
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    event_date: date | None = None
    event_time: str | None = None
    end_date: date | None = None
    venue: str | None = None
    is_reminder_set: bool | None = None
    reminder_days_before: int | None = None
    buffer_days_before: int | None = None
    buffer_days_after: int | None = None


class CalendarEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: UUID
    ward_id: UUID | None = None
    school_id: UUID | None = None
    shortlist_id: UUID | None = None
    application_id: UUID | None = None
    event_type: str
    title: str
    description: str | None = None
    event_date: date
    event_time: str | None = None
    end_date: date | None = None
    venue: str | None = None
    is_reminder_set: bool = True
    reminder_days_before: int = 3
    buffer_days_before: int = 1
    buffer_days_after: int = 0
    has_conflict: bool = False
    conflict_notes: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


# ── Tracking Table ──────────────────────────────────────


class TrackingTableRow(BaseModel):
    shortlist_id: UUID
    school_name: str
    ward_name: str
    status: str
    rank: int | None = None
    deadline: date | None = None
    exam_date: date | None = None
    exam_time: str | None = None
    interview_date: date | None = None
    interview_time: str | None = None
    has_conflict: bool = False
    overall_fit: int | None = None
    distance_km: float | None = None
    exam_registration_status: str = "not_required"
    notes: dict | None = None
    application_id: UUID | None = None
    application_status: str | None = None
