"""School admin — payment/earnings dashboard."""

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.api.deps import get_db
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/school/payments", tags=["school-payments"])


@router.get("")
def list_payments(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = SchoolService(db)
    school = svc.get_school_for_owner(require_uuid(auth["person_id"]))
    if not school:
        return templates.TemplateResponse(
            "school/payments/list.html",
            {
                "request": request,
                "auth": auth,
                "payments": [],
                "pagination": {},
                "stats": {},
                "error_message": "No school found",
            },
        )

    stats = svc.get_dashboard_stats(school.id)
    result = svc.list_payments(school.id, page=page)

    return templates.TemplateResponse(
        "school/payments/list.html",
        {
            "request": request,
            "auth": auth,
            "payments": result["items"],
            "pagination": {
                "page": result["page"],
                "pages": result["pages"],
                "total": result["total"],
                "page_size": result["page_size"],
            },
            "stats": {
                "total_revenue": stats.total_revenue,
                "total_applications": stats.total_applications,
                "commission_rate": school.commission_rate or 0,
            },
            "school": school,
        },
    )
