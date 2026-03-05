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
from app.services.rbac import (
    PermissionNotFoundError,
    Permissions,
    PersonNotFoundError,
    PersonRoleNotFoundError,
    PersonRoles,
    RoleNotFoundError,
    RolePermissionNotFoundError,
    RolePermissions,
    Roles,
)

router = APIRouter(prefix="/rbac", tags=["rbac"], dependencies=[Depends(require_role("admin"))])


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleCreate, db: Session = Depends(get_db)):
    try:
        role = Roles(db).create(payload)
        db.commit()
        return role
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/roles/{role_id}", response_model=RoleRead)
def get_role(role_id: str, db: Session = Depends(get_db)):
    try:
        return Roles(db).get(role_id)
    except RoleNotFoundError as exc:
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
        return Roles(db).list_response(
            is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/roles/{role_id}", response_model=RoleRead)
def update_role(role_id: str, payload: RoleUpdate, db: Session = Depends(get_db)):
    try:
        role = Roles(db).update(role_id, payload)
        db.commit()
        return role
    except RoleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: str, db: Session = Depends(get_db)):
    try:
        Roles(db).delete(role_id)
        db.commit()
    except RoleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/permissions", response_model=PermissionRead, status_code=status.HTTP_201_CREATED
)
def create_permission(payload: PermissionCreate, db: Session = Depends(get_db)):
    try:
        permission = Permissions(db).create(payload)
        db.commit()
        return permission
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/permissions/{permission_id}", response_model=PermissionRead)
def get_permission(permission_id: str, db: Session = Depends(get_db)):
    try:
        return Permissions(db).get(permission_id)
    except PermissionNotFoundError as exc:
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
        return Permissions(db).list_response(
            is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/permissions/{permission_id}", response_model=PermissionRead)
def update_permission(
    permission_id: str, payload: PermissionUpdate, db: Session = Depends(get_db)
):
    try:
        permission = Permissions(db).update(permission_id, payload)
        db.commit()
        return permission
    except PermissionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission(permission_id: str, db: Session = Depends(get_db)):
    try:
        Permissions(db).delete(permission_id)
        db.commit()
    except PermissionNotFoundError as exc:
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
        role_permission = RolePermissions(db).create(payload)
        db.commit()
        return role_permission
    except (RoleNotFoundError, PermissionNotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/role-permissions/{link_id}", response_model=RolePermissionRead)
def get_role_permission(link_id: str, db: Session = Depends(get_db)):
    try:
        return RolePermissions(db).get(link_id)
    except RolePermissionNotFoundError as exc:
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
        return RolePermissions(db).list_response(
            role_id, permission_id, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/role-permissions/{link_id}", response_model=RolePermissionRead)
def update_role_permission(
    link_id: str, payload: RolePermissionUpdate, db: Session = Depends(get_db)
):
    try:
        role_permission = RolePermissions(db).update(link_id, payload)
        db.commit()
        return role_permission
    except RolePermissionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RoleNotFoundError, PermissionNotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/role-permissions/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role_permission(link_id: str, db: Session = Depends(get_db)):
    try:
        RolePermissions(db).delete(link_id)
        db.commit()
    except RolePermissionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/person-roles", response_model=PersonRoleRead, status_code=status.HTTP_201_CREATED
)
def create_person_role(payload: PersonRoleCreate, db: Session = Depends(get_db)):
    try:
        person_role = PersonRoles(db).create(payload)
        db.commit()
        return person_role
    except (PersonNotFoundError, RoleNotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/person-roles/{link_id}", response_model=PersonRoleRead)
def get_person_role(link_id: str, db: Session = Depends(get_db)):
    try:
        return PersonRoles(db).get(link_id)
    except PersonRoleNotFoundError as exc:
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
        return PersonRoles(db).list_response(
            person_id, role_id, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/person-roles/{link_id}", response_model=PersonRoleRead)
def update_person_role(
    link_id: str, payload: PersonRoleUpdate, db: Session = Depends(get_db)
):
    try:
        person_role = PersonRoles(db).update(link_id, payload)
        db.commit()
        return person_role
    except PersonRoleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PersonNotFoundError, RoleNotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/person-roles/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person_role(link_id: str, db: Session = Depends(get_db)):
    try:
        PersonRoles(db).delete(link_id)
        db.commit()
    except PersonRoleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
