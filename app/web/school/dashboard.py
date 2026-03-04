"""School admin — dashboard and profile."""

import logging
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.schemas.school import SchoolUpdate
from app.services.common import require_uuid
from app.services.file_upload import FileUploadService
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["school-dashboard"])


def _get_school(db: Session, auth: dict):
    svc = SchoolService(db)
    schools = svc.get_schools_for_owner(require_uuid(auth["person_id"]))
    return schools[0] if schools else None


@router.get("/school")
def school_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school = _get_school(db, auth)
    if not school:
        return templates.TemplateResponse(
            "school/dashboard.html",
            {
                "request": request,
                "auth": auth,
                "school": None,
                "stats": None,
                "error_message": "No school found. Please register a school.",
            },
        )

    svc = SchoolService(db)
    stats = svc.get_dashboard_stats(school.id)

    return templates.TemplateResponse(
        "school/dashboard.html",
        {"request": request, "auth": auth, "school": school, "stats": stats},
    )


@router.get("/school/profile")
def school_profile_page(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school = _get_school(db, auth)
    return templates.TemplateResponse(
        "school/profile/edit.html",
        {"request": request, "auth": auth, "school": school},
    )


@router.post("/school/profile")
def school_profile_update(
    request: Request,
    description: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    website: str = Form(""),
    fee_range_min: int | None = Form(default=None),
    fee_range_max: int | None = Form(default=None),
    bank_code: str = Form(""),
    account_number: str = Form(""),
    account_name: str = Form(""),
    logo: UploadFile | None = File(default=None),
    cover_image: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    school = _get_school(db, auth)
    if not school:
        return RedirectResponse(
            url="/school/profile?error=School+not+found", status_code=303
        )

    # Handle file uploads
    logo_url: str | None = None
    cover_image_url: str | None = None
    person_id = require_uuid(auth["person_id"])

    if logo and logo.filename:
        try:
            upload_svc = FileUploadService(db)
            content = logo.file.read()
            upload = upload_svc.upload(
                content=content,
                filename=logo.filename,
                content_type=logo.content_type or "image/png",
                uploaded_by=person_id,
                category="logo",
                entity_type="school",
                entity_id=str(school.id),
            )
            logo_url = upload.url
        except (ValueError, RuntimeError) as e:
            logger.warning("Logo upload failed: %s", e)
            return RedirectResponse(
                url=f"/school/profile?error={quote_plus('Logo upload failed')}",
                status_code=303,
            )

    if cover_image and cover_image.filename:
        try:
            upload_svc = FileUploadService(db)
            content = cover_image.file.read()
            upload = upload_svc.upload(
                content=content,
                filename=cover_image.filename,
                content_type=cover_image.content_type or "image/png",
                uploaded_by=person_id,
                category="cover_image",
                entity_type="school",
                entity_id=str(school.id),
            )
            cover_image_url = upload.url
        except (ValueError, RuntimeError) as e:
            logger.warning("Cover image upload failed: %s", e)
            return RedirectResponse(
                url=f"/school/profile?error={quote_plus('Cover image upload failed')}",
                status_code=303,
            )

    svc = SchoolService(db)
    payload = SchoolUpdate(
        description=description if description else None,
        address=address if address else None,
        city=city if city else None,
        state=state if state else None,
        phone=phone if phone else None,
        email=email if email else None,
        website=website if website else None,
        fee_range_min=fee_range_min * 100 if fee_range_min else None,
        fee_range_max=fee_range_max * 100 if fee_range_max else None,
        bank_code=bank_code if bank_code else None,
        account_number=account_number if account_number else None,
        account_name=account_name if account_name else None,
        logo_url=logo_url,
        cover_image_url=cover_image_url,
    )
    svc.update(school, payload)
    db.commit()
    return RedirectResponse(
        url="/school/profile?success=Profile+updated", status_code=303
    )
