"""School verification document upload and status."""

import logging

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.common import require_uuid
from app.services.file_upload import FileUploadService
from app.services.school import SchoolService
from app.templates import templates
from app.web.schoolnet_deps import require_school_admin_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/school/verification", tags=["school-verification"])


@router.get("")
def verification_page(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = SchoolService(db)
    school = svc.get_school_for_owner(require_uuid(auth["person_id"]))
    if not school:
        return RedirectResponse(url="/school?error=School+not+found", status_code=303)

    docs = (school.metadata_ or {}).get("verification_documents", [])
    return templates.TemplateResponse(
        "school/verification.html",
        {
            "request": request,
            "auth": auth,
            "school": school,
            "verification_documents": docs,
        },
    )


@router.post("/upload")
async def verification_upload(
    request: Request,
    document: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = SchoolService(db)
    school = svc.get_school_for_owner(require_uuid(auth["person_id"]))
    if not school:
        return RedirectResponse(url="/school?error=School+not+found", status_code=303)

    upload_svc = FileUploadService(db)
    try:
        content = await document.read()
        record = upload_svc.upload(
            content=content,
            filename=document.filename or "document",
            content_type=document.content_type or "application/octet-stream",
            uploaded_by=require_uuid(auth["person_id"]),
            category="verification",
            entity_type="school",
            entity_id=str(school.id),
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/school/verification?error={e}",
            status_code=303,
        )

    # Store reference in school metadata
    meta = dict(school.metadata_ or {})
    docs = list(meta.get("verification_documents", []))
    docs.append(
        {
            "file_id": str(record.id),
            "filename": document.filename,
            "url": record.url,
        }
    )
    meta["verification_documents"] = docs
    school.metadata_ = meta
    db.commit()

    return RedirectResponse(
        url="/school/verification?success=Document+uploaded+successfully",
        status_code=303,
    )
