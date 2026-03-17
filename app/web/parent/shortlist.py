"""Parent portal — school shortlist management."""

import logging
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.exc import IntegrityError
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
router = APIRouter(prefix="/parent/shortlist", tags=["parent-shortlist"])


@router.get("")
def shortlist_list(
    request: Request,
    ward_id: str = "",
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    ward_svc = WardService(db)
    wards = ward_svc.list_for_parent(parent_id)
    svc = ShortlistService(db)

    selected_ward_id = None
    if ward_id:
        selected_ward_id = require_uuid(ward_id)
        shortlists = svc.list_for_parent_ward(parent_id, selected_ward_id)
    else:
        shortlists = svc.list_for_parent(parent_id)

    enriched = svc.enrich_for_display(shortlists, parent_id)

    return templates.TemplateResponse(
        request,
        "parent/shortlist/list.html",
        {
            "auth": auth,
            "shortlists": enriched,
            "wards": wards,
            "selected_ward_id": str(selected_ward_id) if selected_ward_id else "",
        },
    )


@router.get("/add/{school_id}")
def add_shortlist_page(
    request: Request,
    school_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    school_svc = SchoolService(db)
    school = school_svc.get_by_id(require_uuid(school_id))
    if not school:
        return RedirectResponse(url="/schools?error=School+not+found", status_code=303)

    ward_svc = WardService(db)
    wards = ward_svc.list_for_parent(parent_id)

    return templates.TemplateResponse(
        request,
        "parent/shortlist/add.html",
        {"auth": auth, "school": school, "wards": wards},
    )


@router.post("/add/{school_id}")
def add_shortlist_submit(
    request: Request,
    school_id: str,
    ward_id: str = Form(...),
    notes_general: str = Form(""),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    school_uuid = require_uuid(school_id)
    ward_uuid = require_uuid(ward_id)

    # Verify ward belongs to this parent
    ward_svc = WardService(db)
    ward = ward_svc.get_by_id(ward_uuid)
    if not ward or ward.parent_id != parent_id or not ward.is_active:
        return RedirectResponse(
            url=f"/parent/shortlist/add/{school_id}?error=Invalid+ward",
            status_code=303,
        )

    svc = ShortlistService(db)
    notes = {"general": notes_general} if notes_general else None

    try:
        shortlist = svc.create(
            parent_id=parent_id,
            ward_id=ward_uuid,
            school_id=school_uuid,
            notes=notes,
        )

        # Auto-create calendar events from admission forms
        school_svc = SchoolService(db)
        cal_svc = AdmissionsCalendarService(db)
        forms = school_svc.list_admission_forms(school_uuid)
        for form in forms:
            cal_svc.auto_create_from_admission_form(parent_id, shortlist, form)

        # Run conflict detection
        cal_svc.flag_conflicts(parent_id)

        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            url=f"/parent/shortlist/add/{school_id}?error=School+already+shortlisted+for+this+ward",
            status_code=303,
        )
    except (ValueError, RuntimeError) as e:
        db.rollback()
        logger.warning("Failed to create shortlist: %s", e)
        return RedirectResponse(
            url=f"/parent/shortlist/add/{school_id}?error={quote_plus(str(e))}",
            status_code=303,
        )

    return RedirectResponse(
        url="/parent/shortlist?success=School+added+to+shortlist",
        status_code=303,
    )


@router.get("/{shortlist_id}")
def shortlist_detail(
    request: Request,
    shortlist_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    svc = ShortlistService(db)
    shortlist = svc.get_by_id(require_uuid(shortlist_id))

    if not shortlist or shortlist.parent_id != parent_id or not shortlist.is_active:
        return RedirectResponse(
            url="/parent/shortlist?error=Shortlist+entry+not+found", status_code=303
        )

    school_svc = SchoolService(db)
    school = school_svc.get_by_id(shortlist.school_id)
    ward_svc = WardService(db)
    ward = ward_svc.get_by_id(shortlist.ward_id)
    forms = school_svc.list_admission_forms(shortlist.school_id)

    return templates.TemplateResponse(
        request,
        "parent/shortlist/detail.html",
        {
            "auth": auth,
            "shortlist": shortlist,
            "school": school,
            "ward": ward,
            "admission_forms": forms,
        },
    )


@router.post("/{shortlist_id}")
def shortlist_update(
    request: Request,
    shortlist_id: str,
    status: str = Form(""),
    rank: str = Form(""),
    religious_fit: str = Form(""),
    curriculum_fit: str = Form(""),
    proximity_score: str = Form(""),
    special_needs_fit: str = Form(""),
    overall_fit: str = Form(""),
    exam_registration_status: str = Form(""),
    exam_prep_checklist_json: str = Form(""),
    notes_pros: str = Form(""),
    notes_concerns: str = Form(""),
    notes_general: str = Form(""),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    svc = ShortlistService(db)
    shortlist = svc.get_by_id(require_uuid(shortlist_id))

    if not shortlist or shortlist.parent_id != parent_id or not shortlist.is_active:
        return RedirectResponse(
            url="/parent/shortlist?error=Shortlist+entry+not+found", status_code=303
        )

    def _int_or_none(val: str) -> int | None:
        if val and val.strip():
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return None

    notes = {
        "pros": [p.strip() for p in notes_pros.split("\n") if p.strip()]
        if notes_pros
        else [],
        "concerns": [c.strip() for c in notes_concerns.split("\n") if c.strip()]
        if notes_concerns
        else [],
        "general": notes_general,
    }

    import json

    # Validate enum values
    valid_statuses = {
        "researching",
        "shortlisted",
        "applying",
        "applied",
        "accepted",
        "rejected",
        "enrolled",
        "dropped",
    }
    valid_exam_reg = {"not_required", "pending", "registered"}
    if status and status not in valid_statuses:
        return RedirectResponse(
            url=f"/parent/shortlist/{shortlist_id}?error=Invalid+status",
            status_code=303,
        )
    if exam_registration_status and exam_registration_status not in valid_exam_reg:
        return RedirectResponse(
            url=f"/parent/shortlist/{shortlist_id}?error=Invalid+exam+registration+status",
            status_code=303,
        )

    checklist = None
    if exam_prep_checklist_json:
        try:
            checklist = json.loads(exam_prep_checklist_json)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Invalid exam prep checklist JSON: %s", e)

    svc.update(
        shortlist,
        status=status if status else None,
        rank=_int_or_none(rank),
        religious_fit=_int_or_none(religious_fit),
        curriculum_fit=_int_or_none(curriculum_fit),
        proximity_score=_int_or_none(proximity_score),
        special_needs_fit=_int_or_none(special_needs_fit),
        overall_fit=_int_or_none(overall_fit),
        exam_registration_status=exam_registration_status
        if exam_registration_status
        else None,
        exam_prep_checklist=checklist,
        notes=notes,
    )
    db.commit()

    return RedirectResponse(
        url=f"/parent/shortlist/{shortlist_id}?success=Shortlist+updated",
        status_code=303,
    )


@router.post("/{shortlist_id}/remove")
def shortlist_remove(
    request: Request,
    shortlist_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    svc = ShortlistService(db)
    shortlist = svc.get_by_id(require_uuid(shortlist_id))

    if not shortlist or shortlist.parent_id != parent_id or not shortlist.is_active:
        return RedirectResponse(
            url="/parent/shortlist?error=Shortlist+entry+not+found", status_code=303
        )

    svc.remove(shortlist)
    db.commit()

    return RedirectResponse(
        url="/parent/shortlist?success=School+removed+from+shortlist",
        status_code=303,
    )
