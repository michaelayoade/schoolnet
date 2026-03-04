"""School verification document upload and status."""

import logging
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.api.deps import get_db
from app.services.common import require_uuid
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
def verification_upload(
    request: Request,
    document: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_school_admin_auth),
) -> Response:
    svc = SchoolService(db)
    person_id = require_uuid(auth["person_id"])
    school = svc.get_school_for_owner(person_id)
    if not school:
        return RedirectResponse(url="/school?error=School+not+found", status_code=303)

    try:
        svc.upload_verification_document(school, document, person_id)
        db.commit()
    except ValueError as e:
        db.rollback()
        return RedirectResponse(
            url=f"/school/verification?error={quote_plus(str(e))}",
            status_code=303,
        )

    return RedirectResponse(
        url="/school/verification?success=Document+uploaded+successfully",
        status_code=303,
    )
