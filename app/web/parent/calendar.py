"""Parent portal — admissions calendar management."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.admissions_calendar import AdmissionsCalendarService
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.services.shortlist import ShortlistService
from app.services.ward import WardService
from app.templates import templates
from app.web.schoolnet_deps import require_parent_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parent/calendar", tags=["parent-calendar"])


@router.get("")
def calendar_index(
    request: Request,
    month: int | None = None,
    year: int | None = None,
    ward_id: str = "",
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    today = date.today()
    display_month = month or today.month
    display_year = year or today.year

    cal_svc = AdmissionsCalendarService(db)
    ward_uuid = require_uuid(ward_id) if ward_id else None
    events = cal_svc.list_for_parent(
        parent_id, ward_id=ward_uuid, month=display_month, year=display_year
    )

    ward_svc = WardService(db)
    wards = ward_svc.list_for_parent(parent_id)

    # Build events by date for calendar grid
    events_by_date: dict[str, list] = {}
    for ev in events:
        key = ev.event_date.isoformat()
        if key not in events_by_date:
            events_by_date[key] = []
        events_by_date[key].append(ev)

    return templates.TemplateResponse(
        request,
        "parent/calendar/index.html",
        {
            "auth": auth,
            "events": events,
            "events_by_date": events_by_date,
            "wards": wards,
            "selected_ward_id": ward_id,
            "display_month": display_month,
            "display_year": display_year,
            "today": today,
        },
    )


@router.get("/events")
def calendar_events_partial(
    request: Request,
    month: int | None = None,
    year: int | None = None,
    ward_id: str = "",
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    today = date.today()
    display_month = month or today.month
    display_year = year or today.year

    cal_svc = AdmissionsCalendarService(db)
    ward_uuid = require_uuid(ward_id) if ward_id else None
    events = cal_svc.list_for_parent(
        parent_id, ward_id=ward_uuid, month=display_month, year=display_year
    )

    events_by_date: dict[str, list] = {}
    for ev in events:
        key = ev.event_date.isoformat()
        if key not in events_by_date:
            events_by_date[key] = []
        events_by_date[key].append(ev)

    return templates.TemplateResponse(
        request,
        "parent/calendar/_events_partial.html",
        {
            "events": events,
            "events_by_date": events_by_date,
            "display_month": display_month,
            "display_year": display_year,
            "today": today,
        },
    )


@router.get("/add")
def add_event_page(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    ward_svc = WardService(db)
    wards = ward_svc.list_for_parent(parent_id)
    shortlist_svc = ShortlistService(db)
    shortlists = shortlist_svc.list_for_parent(parent_id)

    # Enrich shortlists with school names
    school_svc = SchoolService(db)
    enriched_shortlists = []
    for sl in shortlists:
        school = school_svc.get_by_id(sl.school_id)
        enriched_shortlists.append({"shortlist": sl, "school": school})

    return templates.TemplateResponse(
        request,
        "parent/calendar/event_form.html",
        {
            "auth": auth,
            "event": None,
            "wards": wards,
            "shortlists": enriched_shortlists,
        },
    )


@router.post("/add")
def add_event_submit(
    request: Request,
    title: str = Form(...),
    event_date: str = Form(...),
    event_type: str = Form("custom"),
    ward_id: str = Form(""),
    shortlist_id: str = Form(""),
    description: str = Form(""),
    event_time: str = Form(""),
    venue: str = Form(""),
    reminder_days_before: str = Form("3"),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])

    try:
        ev_date = date.fromisoformat(event_date)
    except (ValueError, TypeError):
        return RedirectResponse(
            url="/parent/calendar/add?error=Invalid+date", status_code=303
        )

    cal_svc = AdmissionsCalendarService(db)

    ward_uuid = require_uuid(ward_id) if ward_id else None
    shortlist_uuid = require_uuid(shortlist_id) if shortlist_id else None

    # Verify ward ownership if provided
    if ward_uuid:
        ward_svc = WardService(db)
        ward_obj = ward_svc.get_by_id(ward_uuid)
        if not ward_obj or ward_obj.parent_id != parent_id or not ward_obj.is_active:
            return RedirectResponse(
                url="/parent/calendar/add?error=Invalid+ward", status_code=303
            )

    # Get school_id from shortlist if available, verify ownership
    school_id = None
    if shortlist_uuid:
        sl_svc = ShortlistService(db)
        sl = sl_svc.get_by_id(shortlist_uuid)
        if sl and sl.parent_id == parent_id:
            school_id = sl.school_id
            if not ward_uuid:
                ward_uuid = sl.ward_id
        else:
            shortlist_uuid = None

    try:
        reminder = int(reminder_days_before)
    except (ValueError, TypeError):
        reminder = 3

    cal_svc.create_event(
        parent_id=parent_id,
        title=title.strip(),
        event_date=ev_date,
        event_type=event_type,
        ward_id=ward_uuid,
        school_id=school_id,
        shortlist_id=shortlist_uuid,
        description=description if description else None,
        event_time=event_time if event_time else None,
        venue=venue if venue else None,
        reminder_days_before=reminder,
    )
    cal_svc.flag_conflicts(parent_id)
    db.commit()

    return RedirectResponse(url="/parent/calendar?success=Event+added", status_code=303)


@router.get("/{event_id}/edit")
def edit_event_page(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    cal_svc = AdmissionsCalendarService(db)
    event = cal_svc.get_by_id(require_uuid(event_id))

    if not event or event.parent_id != parent_id or not event.is_active:
        return RedirectResponse(
            url="/parent/calendar?error=Event+not+found", status_code=303
        )

    ward_svc = WardService(db)
    wards = ward_svc.list_for_parent(parent_id)
    shortlist_svc = ShortlistService(db)
    shortlists = shortlist_svc.list_for_parent(parent_id)

    school_svc = SchoolService(db)
    enriched_shortlists = []
    for sl in shortlists:
        school = school_svc.get_by_id(sl.school_id)
        enriched_shortlists.append({"shortlist": sl, "school": school})

    return templates.TemplateResponse(
        request,
        "parent/calendar/event_form.html",
        {
            "auth": auth,
            "event": event,
            "wards": wards,
            "shortlists": enriched_shortlists,
        },
    )


@router.post("/{event_id}/edit")
def edit_event_submit(
    request: Request,
    event_id: str,
    title: str = Form(...),
    event_date: str = Form(...),
    event_type: str = Form("custom"),
    description: str = Form(""),
    event_time: str = Form(""),
    venue: str = Form(""),
    reminder_days_before: str = Form("3"),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    cal_svc = AdmissionsCalendarService(db)
    event = cal_svc.get_by_id(require_uuid(event_id))

    if not event or event.parent_id != parent_id or not event.is_active:
        return RedirectResponse(
            url="/parent/calendar?error=Event+not+found", status_code=303
        )

    try:
        ev_date = date.fromisoformat(event_date)
    except (ValueError, TypeError):
        return RedirectResponse(
            url=f"/parent/calendar/{event_id}/edit?error=Invalid+date",
            status_code=303,
        )

    try:
        reminder = int(reminder_days_before)
    except (ValueError, TypeError):
        reminder = 3

    cal_svc.update_event(
        event,
        title=title.strip(),
        event_date=ev_date,
        event_type=event_type,
        description=description if description else None,
        event_time=event_time if event_time else None,
        venue=venue if venue else None,
        reminder_days_before=reminder,
    )
    cal_svc.flag_conflicts(parent_id)
    db.commit()

    return RedirectResponse(
        url="/parent/calendar?success=Event+updated", status_code=303
    )


@router.post("/{event_id}/delete")
def delete_event(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    cal_svc = AdmissionsCalendarService(db)
    event = cal_svc.get_by_id(require_uuid(event_id))

    if not event or event.parent_id != parent_id or not event.is_active:
        return RedirectResponse(
            url="/parent/calendar?error=Event+not+found", status_code=303
        )

    cal_svc.delete_event(event)
    cal_svc.flag_conflicts(parent_id)
    db.commit()

    return RedirectResponse(
        url="/parent/calendar?success=Event+deleted", status_code=303
    )


@router.post("/check-conflicts")
def check_conflicts(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    cal_svc = AdmissionsCalendarService(db)
    conflict_count = cal_svc.flag_conflicts(parent_id)
    db.commit()

    # Get events with conflicts
    conflicts = [ev for ev in cal_svc.list_for_parent(parent_id) if ev.has_conflict]

    return templates.TemplateResponse(
        request,
        "parent/calendar/_conflicts.html",
        {
            "conflicts": conflicts,
            "conflict_count": conflict_count,
        },
    )
