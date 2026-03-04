from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.schemas.common import ListResponse
from app.schemas.rbac import (
    PermissionCreate,
    PermissionRead,
    PermissionUpdate,
    PersonRoleCreate,
    PersonRoleRead,
    PersonRoleUpdate,
    RoleCreate,
    RolePermissionCreate,
    RolePermissionRead,
    RolePermissionUpdate,
    RoleRead,
    RoleUpdate,
)
from app.services import rbac as rbac_service

router = APIRouter(prefix="/rbac", tags=["rbac"], dependencies=[Depends(require_role("admin"))])


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleCreate, db: Session = Depends(get_db)):
    try:
        role = rbac_service.roles.create(db, payload)
        db.commit()
        return role
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/roles/{role_id}", response_model=RoleRead)
def get_role(role_id: str, db: Session = Depends(get_db)):
    try:
        return rbac_service.roles.get(db, role_id)
    except rbac_service.RoleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/roles", response_model=ListResponse[RoleRead])
def list_roles(
    is_active: bool | None = None,
    order_by: str = Query(default="name"),
    order_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return rbac_service.roles.list_response(
            db, is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/roles/{role_id}", response_model=RoleRead)
def update_role(role_id: str, payload: RoleUpdate, db: Session = Depends(get_db)):
    try:
        role = rbac_service.roles.update(db, role_id, payload)
        db.commit()
        return role
    except rbac_service.RoleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: str, db: Session = Depends(get_db)):
    try:
        rbac_service.roles.delete(db, role_id)
        db.commit()
    except rbac_service.RoleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/permissions", response_model=PermissionRead, status_code=status.HTTP_201_CREATED
)
def create_permission(payload: PermissionCreate, db: Session = Depends(get_db)):
    try:
        permission = rbac_service.permissions.create(db, payload)
        db.commit()
        return permission
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/permissions/{permission_id}", response_model=PermissionRead)
def get_permission(permission_id: str, db: Session = Depends(get_db)):
    try:
        return rbac_service.permissions.get(db, permission_id)
    except rbac_service.PermissionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/permissions", response_model=ListResponse[PermissionRead])
def list_permissions(
    is_active: bool | None = None,
    order_by: str = Query(default="key"),
    order_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return rbac_service.permissions.list_response(
            db, is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/permissions/{permission_id}", response_model=PermissionRead)
def update_permission(
    permission_id: str, payload: PermissionUpdate, db: Session = Depends(get_db)
):
    try:
        permission = rbac_service.permissions.update(db, permission_id, payload)
        db.commit()
        return permission
    except rbac_service.PermissionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission(permission_id: str, db: Session = Depends(get_db)):
    try:
        rbac_service.permissions.delete(db, permission_id)
        db.commit()
    except rbac_service.PermissionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/role-permissions",
    response_model=RolePermissionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_role_permission(
    payload: RolePermissionCreate, db: Session = Depends(get_db)
):
    try:
        role_permission = rbac_service.role_permissions.create(db, payload)
        db.commit()
        return role_permission
    except (rbac_service.RoleNotFoundError, rbac_service.PermissionNotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/role-permissions/{link_id}", response_model=RolePermissionRead)
def get_role_permission(link_id: str, db: Session = Depends(get_db)):
    try:
        return rbac_service.role_permissions.get(db, link_id)
    except rbac_service.RolePermissionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/role-permissions", response_model=ListResponse[RolePermissionRead])
def list_role_permissions(
    role_id: str | None = None,
    permission_id: str | None = None,
    order_by: str = Query(default="role_id"),
    order_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return rbac_service.role_permissions.list_response(
            db, role_id, permission_id, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/role-permissions/{link_id}", response_model=RolePermissionRead)
def update_role_permission(
    link_id: str, payload: RolePermissionUpdate, db: Session = Depends(get_db)
):
    try:
        role_permission = rbac_service.role_permissions.update(db, link_id, payload)
        db.commit()
        return role_permission
    except rbac_service.RolePermissionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (rbac_service.RoleNotFoundError, rbac_service.PermissionNotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/role-permissions/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role_permission(link_id: str, db: Session = Depends(get_db)):
    try:
        rbac_service.role_permissions.delete(db, link_id)
        db.commit()
    except rbac_service.RolePermissionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/person-roles", response_model=PersonRoleRead, status_code=status.HTTP_201_CREATED
)
def create_person_role(payload: PersonRoleCreate, db: Session = Depends(get_db)):
    try:
        person_role = rbac_service.person_roles.create(db, payload)
        db.commit()
        return person_role
    except (rbac_service.PersonNotFoundError, rbac_service.RoleNotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/person-roles/{link_id}", response_model=PersonRoleRead)
def get_person_role(link_id: str, db: Session = Depends(get_db)):
    try:
        return rbac_service.person_roles.get(db, link_id)
    except rbac_service.PersonRoleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/person-roles", response_model=ListResponse[PersonRoleRead])
def list_person_roles(
    person_id: str | None = None,
    role_id: str | None = None,
    order_by: str = Query(default="assigned_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return rbac_service.person_roles.list_response(
            db, person_id, role_id, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/person-roles/{link_id}", response_model=PersonRoleRead)
def update_person_role(
    link_id: str, payload: PersonRoleUpdate, db: Session = Depends(get_db)
):
    try:
        person_role = rbac_service.person_roles.update(db, link_id, payload)
        db.commit()
        return person_role
    except rbac_service.PersonRoleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (rbac_service.PersonNotFoundError, rbac_service.RoleNotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/person-roles/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person_role(link_id: str, db: Session = Depends(get_db)):
    try:
        rbac_service.person_roles.delete(db, link_id)
        db.commit()
    except rbac_service.PersonRoleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
