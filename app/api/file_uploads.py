from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_user_auth
from app.schemas.common import ListResponse
from app.schemas.file_upload import FileUploadRead
from app.services.common import require_uuid
from app.services.file_upload import FileUploadService

router = APIRouter(prefix="/file-uploads", tags=["file-uploads"])


@router.post("", response_model=FileUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form(default="document"),
    entity_type: str | None = Form(default=None),
    entity_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_user_auth),
) -> FileUploadRead:
    content = await file.read()
    svc = FileUploadService(db)
    actor_id = require_uuid(auth["person_id"])
    try:
        record = svc.upload(
            content=content,
            filename=file.filename or "unknown",
            content_type=file.content_type or "application/octet-stream",
            uploaded_by=actor_id,
            category=category,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return FileUploadRead.model_validate(record)


@router.get("/{file_id}", response_model=FileUploadRead)
def get_file_upload(file_id: UUID, db: Session = Depends(get_db)) -> FileUploadRead:
    svc = FileUploadService(db)
    record = svc.get_by_id(file_id)
    if not record or not record.is_active:
        raise HTTPException(status_code=404, detail="File upload not found")
    return FileUploadRead.model_validate(record)


@router.get("", response_model=ListResponse[FileUploadRead])
def list_file_uploads(
    category: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ListResponse[FileUploadRead]:
    svc = FileUploadService(db)
    items = svc.list_uploads(
        category=category,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
    total = svc.count(category=category)
    return ListResponse(
        items=[FileUploadRead.model_validate(i) for i in items],
        count=len(items),
        limit=limit,
        offset=offset,
        total=total,
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file_upload(
    file_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_user_auth),
) -> None:
    svc = FileUploadService(db)
    actor_id = require_uuid(auth["person_id"])
    try:
        svc.delete(
            file_id,
            actor_id=actor_id,
            roles=auth.get("roles"),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
