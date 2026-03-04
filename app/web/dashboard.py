"""Admin dashboard with summary stats."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.branding_context import load_branding_context
from app.services.platform_stats import PlatformStatsService
from app.templates import templates
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["web-admin"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    branding = load_branding_context(db)
    person = auth["person"]

    svc = PlatformStatsService(db)
    stats = svc.get_dashboard_stats(person_id=person.id)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "page_title": "Dashboard",
            "current_user": person,
            "brand": branding["brand"],
            "org_branding": branding["org_branding"],
            "brand_mark": branding["brand"].get("mark", "A"),
            "stats": stats,
        },
    )
