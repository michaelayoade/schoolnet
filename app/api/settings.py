from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.schemas.common import ListResponse
from app.schemas.settings import DomainSettingRead, DomainSettingUpdate
from app.services import settings_api as settings_service

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_role("admin"))])


@router.get(
    "/auth", response_model=ListResponse[DomainSettingRead], tags=["settings-auth"]
)
def list_auth_settings(
    is_active: bool | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return settings_service.list_auth_settings_response(
            db, is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/auth/{key}",
    response_model=DomainSettingRead,
    status_code=status.HTTP_200_OK,
    tags=["settings-auth"],
)
def upsert_auth_setting(
    key: str, payload: DomainSettingUpdate, db: Session = Depends(get_db)
):
    try:
        setting = settings_service.upsert_auth_setting(db, key, payload)
        db.commit()
        return setting
    except ValueError as exc:
        db.rollback()
        status_code = 404 if settings_service.is_not_found_error(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get(
    "/auth/{key}",
    response_model=DomainSettingRead,
    tags=["settings-auth"],
)
def get_auth_setting(key: str, db: Session = Depends(get_db)):
    try:
        return settings_service.get_auth_setting(db, key)
    except ValueError as exc:
        status_code = 404 if settings_service.is_not_found_error(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get(
    "/audit",
    response_model=ListResponse[DomainSettingRead],
    tags=["settings-audit"],
)
def list_audit_settings(
    is_active: bool | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return settings_service.list_audit_settings_response(
            db, is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/audit/{key}",
    response_model=DomainSettingRead,
    status_code=status.HTTP_200_OK,
    tags=["settings-audit"],
)
def upsert_audit_setting(
    key: str, payload: DomainSettingUpdate, db: Session = Depends(get_db)
):
    try:
        setting = settings_service.upsert_audit_setting(db, key, payload)
        db.commit()
        return setting
    except ValueError as exc:
        db.rollback()
        status_code = 404 if settings_service.is_not_found_error(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get(
    "/audit/{key}",
    response_model=DomainSettingRead,
    tags=["settings-audit"],
)
def get_audit_setting(key: str, db: Session = Depends(get_db)):
    try:
        return settings_service.get_audit_setting(db, key)
    except ValueError as exc:
        status_code = 404 if settings_service.is_not_found_error(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get(
    "/scheduler",
    response_model=ListResponse[DomainSettingRead],
    tags=["settings-scheduler"],
)
def list_scheduler_settings(
    is_active: bool | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return settings_service.list_scheduler_settings_response(
            db, is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/scheduler/{key}",
    response_model=DomainSettingRead,
    status_code=status.HTTP_200_OK,
    tags=["settings-scheduler"],
)
def upsert_scheduler_setting(
    key: str, payload: DomainSettingUpdate, db: Session = Depends(get_db)
):
    try:
        setting = settings_service.upsert_scheduler_setting(db, key, payload)
        db.commit()
        return setting
    except ValueError as exc:
        db.rollback()
        status_code = 404 if settings_service.is_not_found_error(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get(
    "/scheduler/{key}",
    response_model=DomainSettingRead,
    tags=["settings-scheduler"],
)
def get_scheduler_setting(key: str, db: Session = Depends(get_db)):
    try:
        return settings_service.get_scheduler_setting(db, key)
    except ValueError as exc:
        status_code = 404 if settings_service.is_not_found_error(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
