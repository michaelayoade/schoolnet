"""Parent portal — admissions tracking table."""

import csv
import io
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response, StreamingResponse

from app.api.deps import get_db
from app.services.common import require_uuid
from app.services.shortlist import ShortlistService
from app.services.ward import WardService
from app.templates import templates
from app.web.schoolnet_deps import require_parent_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parent/tracking", tags=["parent-tracking"])


@router.get("")
def tracking_table(
    request: Request,
    ward_id: str = "",
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    ward_svc = WardService(db)
    wards = ward_svc.list_for_parent(parent_id)

    svc = ShortlistService(db)
    ward_uuid = require_uuid(ward_id) if ward_id else None
    rows = svc.get_tracking_table(parent_id, ward_id=ward_uuid)

    return templates.TemplateResponse(
        request,
        "parent/tracking/table.html",
        {
            "auth": auth,
            "rows": rows,
            "wards": wards,
            "selected_ward_id": ward_id,
        },
    )


@router.get("/export")
def tracking_export(
    request: Request,
    ward_id: str = "",
    db: Session = Depends(get_db),
    auth: dict = Depends(require_parent_auth),
) -> Response:
    parent_id = require_uuid(auth["person_id"])
    svc = ShortlistService(db)
    ward_uuid = require_uuid(ward_id) if ward_id else None
    rows = svc.get_tracking_table(parent_id, ward_id=ward_uuid)

    if not rows:
        return RedirectResponse(
            url="/parent/tracking?error=No+data+to+export", status_code=303
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "School",
            "Ward",
            "Status",
            "Rank",
            "Distance (km)",
            "Deadline",
            "Exam Date",
            "Exam Time",
            "Interview Date",
            "Interview Time",
            "Conflict",
            "Overall Fit",
            "Exam Registration",
            "Application Status",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.school_name,
                row.ward_name,
                row.status.replace("_", " ").title(),
                row.rank if row.rank else "",
                f"{row.distance_km}" if row.distance_km is not None else "",
                row.deadline.isoformat() if row.deadline else "",
                row.exam_date.isoformat() if row.exam_date else "",
                row.exam_time if row.exam_time else "",
                row.interview_date.isoformat() if row.interview_date else "",
                row.interview_time if row.interview_time else "",
                "Yes" if row.has_conflict else "No",
                f"{row.overall_fit}/5" if row.overall_fit else "",
                row.exam_registration_status.replace("_", " ").title(),
                row.application_status.replace("_", " ").title()
                if row.application_status
                else "",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=admissions-tracking.csv"},
    )
