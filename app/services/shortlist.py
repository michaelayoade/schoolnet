"""Shortlist service — manage school shortlists for parents."""

import logging
import math
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admissions import (
    AdmissionsCalendarEvent,
    SchoolShortlist,
    ShortlistStatus,
)
from app.models.person import Person
from app.models.school import Application, School
from app.models.ward import Ward
from app.schemas.admissions import TrackingTableRow

logger = logging.getLogger(__name__)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lng points."""
    r = 6371.0  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class ShortlistService:
    """Service for managing school shortlists."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        parent_id: UUID,
        ward_id: UUID,
        school_id: UUID,
        status: str = "researching",
        rank: int | None = None,
        notes: dict | None = None,
    ) -> SchoolShortlist:
        # Auto-populate exam prep checklist from school's admission forms
        from app.models.school import AdmissionForm

        checklist: list[dict[str, object]] = []
        forms = list(
            self.db.scalars(
                select(AdmissionForm).where(
                    AdmissionForm.school_id == school_id,
                    AdmissionForm.is_active.is_(True),
                )
            ).all()
        )
        for form in forms:
            if form.exam_requirements:
                for item in form.exam_requirements:
                    label = (
                        str(item)
                        if not isinstance(item, dict)
                        else item.get("name", str(item))
                    )
                    checklist.append({"item": label, "done": False})

        shortlist = SchoolShortlist(
            parent_id=parent_id,
            ward_id=ward_id,
            school_id=school_id,
            status=status,
            rank=rank,
            notes=notes,
            exam_prep_checklist=checklist if checklist else None,
        )
        self.db.add(shortlist)
        self.db.flush()
        logger.info(
            "Created shortlist %s for parent %s, ward %s, school %s",
            shortlist.id,
            parent_id,
            ward_id,
            school_id,
        )
        return shortlist

    def get_by_id(self, shortlist_id: UUID) -> SchoolShortlist | None:
        return self.db.get(SchoolShortlist, shortlist_id)

    def list_for_parent_ward(
        self, parent_id: UUID, ward_id: UUID
    ) -> list[SchoolShortlist]:
        stmt = (
            select(SchoolShortlist)
            .where(
                SchoolShortlist.parent_id == parent_id,
                SchoolShortlist.ward_id == ward_id,
                SchoolShortlist.is_active.is_(True),
            )
            .order_by(
                SchoolShortlist.rank.asc().nulls_last(), SchoolShortlist.created_at
            )
        )
        return list(self.db.scalars(stmt).all())

    def list_for_parent(self, parent_id: UUID) -> list[SchoolShortlist]:
        stmt = (
            select(SchoolShortlist)
            .where(
                SchoolShortlist.parent_id == parent_id,
                SchoolShortlist.is_active.is_(True),
            )
            .order_by(
                SchoolShortlist.rank.asc().nulls_last(), SchoolShortlist.created_at
            )
        )
        return list(self.db.scalars(stmt).all())

    def update(
        self,
        shortlist: SchoolShortlist,
        status: str | None = None,
        rank: int | None = None,
        religious_fit: int | None = None,
        curriculum_fit: int | None = None,
        proximity_score: int | None = None,
        special_needs_fit: int | None = None,
        overall_fit: int | None = None,
        notes: dict | None = None,
        exam_registration_status: str | None = None,
        exam_prep_checklist: list | None = None,
    ) -> SchoolShortlist:
        if status is not None:
            shortlist.status = ShortlistStatus(status)
        if rank is not None:
            shortlist.rank = rank
        if religious_fit is not None:
            shortlist.religious_fit = religious_fit
        if curriculum_fit is not None:
            shortlist.curriculum_fit = curriculum_fit
        if proximity_score is not None:
            shortlist.proximity_score = proximity_score
        if special_needs_fit is not None:
            shortlist.special_needs_fit = special_needs_fit
        if overall_fit is not None:
            shortlist.overall_fit = overall_fit
        if notes is not None:
            shortlist.notes = notes
        if exam_registration_status is not None:
            from app.models.admissions import ExamRegistrationStatus

            shortlist.exam_registration_status = ExamRegistrationStatus(exam_registration_status)
        if exam_prep_checklist is not None:
            shortlist.exam_prep_checklist = exam_prep_checklist
        self.db.flush()
        logger.info("Updated shortlist %s", shortlist.id)
        return shortlist

    def link_application(
        self, shortlist: SchoolShortlist, application_id: UUID
    ) -> SchoolShortlist:
        shortlist.application_id = application_id
        shortlist.status = ShortlistStatus.applied
        self.db.flush()
        logger.info(
            "Linked application %s to shortlist %s", application_id, shortlist.id
        )
        return shortlist

    def remove(self, shortlist: SchoolShortlist) -> SchoolShortlist:
        shortlist.is_active = False
        self.db.flush()
        logger.info("Removed shortlist %s", shortlist.id)
        return shortlist

    def enrich_for_display(
        self, shortlists: list[SchoolShortlist], parent_id: UUID
    ) -> list[dict]:
        """Enrich shortlists with school, ward, and distance data for display."""
        if not shortlists:
            return []

        parent: Person | None = self.db.get(Person, parent_id)
        parent_lat = parent.latitude if parent else None
        parent_lng = parent.longitude if parent else None

        # Batch-load schools and wards
        school_ids = list({sl.school_id for sl in shortlists})
        ward_ids = list({sl.ward_id for sl in shortlists})
        schools_map: dict = (
            {
                s.id: s
                for s in self.db.scalars(
                    select(School).where(School.id.in_(school_ids))
                ).all()
            }
            if school_ids
            else {}
        )
        wards_map: dict = (
            {
                w.id: w
                for w in self.db.scalars(
                    select(Ward).where(Ward.id.in_(ward_ids))
                ).all()
            }
            if ward_ids
            else {}
        )

        enriched = []
        for sl in shortlists:
            school = schools_map.get(sl.school_id)
            ward = wards_map.get(sl.ward_id)
            dist = None
            if (
                parent_lat is not None
                and parent_lng is not None
                and school
                and school.latitude is not None
                and school.longitude is not None
            ):
                dist = round(
                    _haversine_km(
                        parent_lat, parent_lng, school.latitude, school.longitude
                    ),
                    1,
                )
            enriched.append(
                {"shortlist": sl, "school": school, "ward": ward, "distance_km": dist}
            )
        return enriched

    def get_tracking_table(
        self, parent_id: UUID, ward_id: UUID | None = None
    ) -> list[TrackingTableRow]:
        stmt = (
            select(SchoolShortlist)
            .where(
                SchoolShortlist.parent_id == parent_id,
                SchoolShortlist.is_active.is_(True),
            )
            .order_by(
                SchoolShortlist.rank.asc().nulls_last(), SchoolShortlist.created_at
            )
        )
        if ward_id:
            stmt = stmt.where(SchoolShortlist.ward_id == ward_id)

        shortlists = list(self.db.scalars(stmt).all())
        if not shortlists:
            return []

        # ── Batch-load all related data (eliminates N+1) ───────
        shortlist_ids = [sl.id for sl in shortlists]
        school_ids = list({sl.school_id for sl in shortlists})
        ward_ids = list({sl.ward_id for sl in shortlists})
        app_ids = [sl.application_id for sl in shortlists if sl.application_id]

        # Parent for distance calc
        parent: Person | None = self.db.get(Person, parent_id)
        parent_lat = parent.latitude if parent else None
        parent_lng = parent.longitude if parent else None

        # Schools
        schools_map: dict = {
            s.id: s
            for s in self.db.scalars(
                select(School).where(School.id.in_(school_ids))
            ).all()
        }

        # Wards
        wards_map: dict = {
            w.id: w
            for w in self.db.scalars(select(Ward).where(Ward.id.in_(ward_ids))).all()
        }

        # Applications
        apps_map: dict = {}
        if app_ids:
            apps_map = {
                a.id: a
                for a in self.db.scalars(
                    select(Application).where(Application.id.in_(app_ids))
                ).all()
            }

        # Calendar events — one query, then group by shortlist_id + type
        all_events = list(
            self.db.scalars(
                select(AdmissionsCalendarEvent)
                .where(
                    AdmissionsCalendarEvent.shortlist_id.in_(shortlist_ids),
                    AdmissionsCalendarEvent.is_active.is_(True),
                )
                .order_by(AdmissionsCalendarEvent.event_date)
            ).all()
        )

        # Build lookup: shortlist_id → {event_type → first event}
        from collections import defaultdict

        events_by_sl: dict[object, dict[str, AdmissionsCalendarEvent]] = defaultdict(
            dict
        )
        conflicts_by_sl: set = set()
        for ev in all_events:
            ev_type = (
                ev.event_type.value
                if hasattr(ev.event_type, "value")
                else str(ev.event_type)
            )
            if ev_type not in events_by_sl[ev.shortlist_id]:
                events_by_sl[ev.shortlist_id][ev_type] = ev
            if ev.has_conflict:
                conflicts_by_sl.add(ev.shortlist_id)

        # ── Build rows ─────────────────────────────────────────
        rows: list[TrackingTableRow] = []
        for sl in shortlists:
            school = schools_map.get(sl.school_id)
            ward = wards_map.get(sl.ward_id)
            school_name = school.name if school else "Unknown"
            ward_name = f"{ward.first_name} {ward.last_name}" if ward else "Unknown"

            # Distance
            distance_km: float | None = None
            if (
                parent_lat is not None
                and parent_lng is not None
                and school
                and school.latitude is not None
                and school.longitude is not None
            ):
                distance_km = round(
                    _haversine_km(
                        parent_lat, parent_lng, school.latitude, school.longitude
                    ),
                    1,
                )

            # Events from lookup
            sl_events = events_by_sl.get(sl.id, {})
            deadline_event = sl_events.get("application_deadline")
            exam_event = sl_events.get("exam")
            interview_event = sl_events.get("interview")

            # Application status
            app_status = None
            if sl.application_id:
                app = apps_map.get(sl.application_id)
                if app:
                    app_status = (
                        app.status.value
                        if hasattr(app.status, "value")
                        else str(app.status)
                    )

            rows.append(
                TrackingTableRow(
                    shortlist_id=sl.id,
                    school_name=school_name,
                    ward_name=ward_name,
                    status=sl.status.value
                    if hasattr(sl.status, "value")
                    else str(sl.status),
                    rank=sl.rank,
                    deadline=deadline_event.event_date if deadline_event else None,
                    exam_date=exam_event.event_date if exam_event else None,
                    exam_time=exam_event.event_time if exam_event else None,
                    interview_date=interview_event.event_date
                    if interview_event
                    else None,
                    interview_time=interview_event.event_time
                    if interview_event
                    else None,
                    has_conflict=sl.id in conflicts_by_sl,
                    overall_fit=sl.overall_fit,
                    distance_km=distance_km,
                    exam_registration_status=sl.exam_registration_status.value
                    if hasattr(sl.exam_registration_status, "value")
                    else str(sl.exam_registration_status),
                    notes=sl.notes,
                    application_id=sl.application_id,
                    application_status=app_status,
                )
            )

        return rows
