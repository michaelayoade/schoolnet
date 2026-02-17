"""Platform admin school management web routes."""

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/schools", tags=["admin-schools"])


@router.get("")
def list_schools(
    request: Request,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    from sqlalchemy import func, select

    from app.models.school import School

    limit = 20
    offset = (page - 1) * limit

    base = select(School).where(School.is_active.is_(True))
    if status:
        base = base.where(School.status == status)
    total: int = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = base.order_by(School.created_at.desc()).limit(limit).offset(offset)
    schools = list(db.scalars(stmt).all())
    total_pages = (total + limit - 1) // limit if total else 1

    return templates.TemplateResponse(
        "admin/schools/list.html",
        {
            "request": request,
            "schools": schools,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "status_filter": status or "",
            "auth": auth,
        },
    )


@router.get("/{school_id}")
def school_detail(
    request: Request,
    school_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    svc = SchoolService(db)
    school = svc.get_by_id(require_uuid(school_id))
    if not school:
        return RedirectResponse(url="/admin/schools?error=School+not+found", status_code=303)

    stats = svc.get_dashboard_stats(school.id)
    avg_rating = svc.get_average_rating(school.id)

    return templates.TemplateResponse(
        "admin/schools/detail.html",
        {
            "request": request,
            "school": school,
            "stats": stats,
            "avg_rating": avg_rating,
            "auth": auth,
        },
    )


@router.post("/{school_id}/approve")
def approve_school(
    request: Request,
    school_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    svc = SchoolService(db)
    school = svc.get_by_id(require_uuid(school_id))
    if not school:
        return RedirectResponse(url="/admin/schools?error=School+not+found", status_code=303)
    svc.approve(school, approved_by=require_uuid(auth["person_id"]))
    db.commit()
    return RedirectResponse(url=f"/admin/schools/{school_id}?success=School+approved", status_code=303)


@router.post("/{school_id}/suspend")
def suspend_school(
    request: Request,
    school_id: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> Response:
    svc = SchoolService(db)
    school = svc.get_by_id(require_uuid(school_id))
    if not school:
        return RedirectResponse(url="/admin/schools?error=School+not+found", status_code=303)
    svc.suspend(school)
    db.commit()
    return RedirectResponse(url=f"/admin/schools/{school_id}?success=School+suspended", status_code=303)
