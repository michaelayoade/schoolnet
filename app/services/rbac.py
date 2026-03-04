import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.person import Person
from app.models.rbac import Permission, PersonRole, Role, RolePermission
from app.schemas.rbac import (
    PermissionCreate,
    PermissionUpdate,
    PersonRoleCreate,
    PersonRoleUpdate,
    RoleCreate,
    RolePermissionCreate,
    RolePermissionUpdate,
    RoleUpdate,
)
from app.services.common import coerce_uuid
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class RoleNotFoundError(ValueError):
    pass


class PermissionNotFoundError(ValueError):
    pass


class RolePermissionNotFoundError(ValueError):
    pass


class PersonRoleNotFoundError(ValueError):
    pass


class PersonNotFoundError(ValueError):
    pass


class Roles(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Role.created_at,
            "name": Role.name,
        }
        column = allowed_columns.get(order_by)
        if column is None:
            raise ValueError(
                f"Invalid order_by. Allowed: {', '.join(sorted(allowed_columns))}"
            )
        if order_dir == "desc":
            return stmt.order_by(column.desc())
        return stmt.order_by(column.asc())

    @staticmethod
    def create(db: Session, payload: RoleCreate):
        role = Role(**payload.model_dump())
        db.add(role)
        db.flush()
        db.refresh(role)
        return role

    @staticmethod
    def get(db: Session, role_id: str):
        role = db.get(Role, coerce_uuid(role_id))
        if not role:
            raise RoleNotFoundError("Role not found")
        return role

    @staticmethod
    def list(
        db: Session,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(Role)
        if is_active is None:
            stmt = stmt.where(Role.is_active.is_(True))
        else:
            stmt = stmt.where(Role.is_active == is_active)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0

        stmt = Roles._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, role_id: str, payload: RoleUpdate):
        role = db.get(Role, coerce_uuid(role_id))
        if not role:
            raise RoleNotFoundError("Role not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(role, key, value)
        db.flush()
        db.refresh(role)
        return role

    @staticmethod
    def delete(db: Session, role_id: str):
        role = db.get(Role, coerce_uuid(role_id))
        if not role:
            raise RoleNotFoundError("Role not found")
        role.is_active = False
        db.flush()


class Permissions(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": Permission.created_at,
            "key": Permission.key,
        }
        column = allowed_columns.get(order_by)
        if column is None:
            raise ValueError(
                f"Invalid order_by. Allowed: {', '.join(sorted(allowed_columns))}"
            )
        if order_dir == "desc":
            return stmt.order_by(column.desc())
        return stmt.order_by(column.asc())

    @staticmethod
    def create(db: Session, payload: PermissionCreate):
        permission = Permission(**payload.model_dump())
        db.add(permission)
        db.flush()
        db.refresh(permission)
        return permission

    @staticmethod
    def get(db: Session, permission_id: str):
        permission = db.get(Permission, coerce_uuid(permission_id))
        if not permission:
            raise PermissionNotFoundError("Permission not found")
        return permission

    @staticmethod
    def list(
        db: Session,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(Permission)
        if is_active is None:
            stmt = stmt.where(Permission.is_active.is_(True))
        else:
            stmt = stmt.where(Permission.is_active == is_active)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0

        stmt = Permissions._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update(db: Session, permission_id: str, payload: PermissionUpdate):
        permission = db.get(Permission, coerce_uuid(permission_id))
        if not permission:
            raise PermissionNotFoundError("Permission not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(permission, key, value)
        db.flush()
        db.refresh(permission)
        return permission

    @staticmethod
    def delete(db: Session, permission_id: str):
        permission = db.get(Permission, coerce_uuid(permission_id))
        if not permission:
            raise PermissionNotFoundError("Permission not found")
        permission.is_active = False
        db.flush()


class RolePermissions(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "role_id": RolePermission.role_id,
        }
        column = allowed_columns.get(order_by)
        if column is None:
            raise ValueError(
                f"Invalid order_by. Allowed: {', '.join(sorted(allowed_columns))}"
            )
        if order_dir == "desc":
            return stmt.order_by(column.desc())
        return stmt.order_by(column.asc())

    @staticmethod
    def create(db: Session, payload: RolePermissionCreate):
        role = db.get(Role, coerce_uuid(str(payload.role_id)))
        if not role:
            raise RoleNotFoundError("Role not found")
        permission = db.get(Permission, coerce_uuid(str(payload.permission_id)))
        if not permission:
            raise PermissionNotFoundError("Permission not found")

        link = RolePermission(**payload.model_dump())
        db.add(link)
        db.flush()
        db.refresh(link)
        return link

    @staticmethod
    def get(db: Session, link_id: str):
        link = db.get(RolePermission, coerce_uuid(link_id))
        if not link:
            raise RolePermissionNotFoundError("Role permission not found")
        return link

    @staticmethod
    def list(
        db: Session,
        role_id: str | None,
        permission_id: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(RolePermission)
        if role_id:
            stmt = stmt.where(RolePermission.role_id == coerce_uuid(role_id))
        if permission_id:
            stmt = stmt.where(RolePermission.permission_id == coerce_uuid(permission_id))

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0

        stmt = RolePermissions._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def _validate_link_ids(db: Session, role_id: UUID | None, permission_id: UUID | None):
        if role_id is not None:
            role = db.get(Role, role_id)
            if not role:
                raise RoleNotFoundError("Role not found")
        if permission_id is not None:
            permission = db.get(Permission, permission_id)
            if not permission:
                raise PermissionNotFoundError("Permission not found")

    @staticmethod
    def update(db: Session, link_id: str, payload: RolePermissionUpdate):
        link = db.get(RolePermission, coerce_uuid(link_id))
        if not link:
            raise RolePermissionNotFoundError("Role permission not found")
        data = payload.model_dump(exclude_unset=True)
        RolePermissions._validate_link_ids(
            db,
            role_id=data.get("role_id"),
            permission_id=data.get("permission_id"),
        )
        for key, value in data.items():
            setattr(link, key, value)
        db.flush()
        db.refresh(link)
        return link

    @staticmethod
    def delete(db: Session, link_id: str):
        link = db.get(RolePermission, coerce_uuid(link_id))
        if not link:
            raise RolePermissionNotFoundError("Role permission not found")
        db.delete(link)
        db.flush()


class PersonRoles(ListResponseMixin):
    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "assigned_at": PersonRole.assigned_at,
        }
        column = allowed_columns.get(order_by)
        if column is None:
            raise ValueError(
                f"Invalid order_by. Allowed: {', '.join(sorted(allowed_columns))}"
            )
        if order_dir == "desc":
            return stmt.order_by(column.desc())
        return stmt.order_by(column.asc())

    @staticmethod
    def create(db: Session, payload: PersonRoleCreate):
        person = db.get(Person, coerce_uuid(str(payload.person_id)))
        if not person:
            raise PersonNotFoundError("Person not found")
        role = db.get(Role, coerce_uuid(str(payload.role_id)))
        if not role:
            raise RoleNotFoundError("Role not found")

        link = PersonRole(**payload.model_dump())
        db.add(link)
        db.flush()
        db.refresh(link)
        return link

    @staticmethod
    def get(db: Session, link_id: str):
        link = db.get(PersonRole, coerce_uuid(link_id))
        if not link:
            raise PersonRoleNotFoundError("Person role not found")
        return link

    @staticmethod
    def list(
        db: Session,
        person_id: str | None,
        role_id: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(PersonRole)
        if person_id:
            stmt = stmt.where(PersonRole.person_id == coerce_uuid(person_id))
        if role_id:
            stmt = stmt.where(PersonRole.role_id == coerce_uuid(role_id))

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = db.scalar(count_stmt) or 0

        stmt = PersonRoles._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def _validate_link_ids(db: Session, person_id: UUID | None, role_id: UUID | None):
        if person_id is not None:
            person = db.get(Person, person_id)
            if not person:
                raise PersonNotFoundError("Person not found")
        if role_id is not None:
            role = db.get(Role, role_id)
            if not role:
                raise RoleNotFoundError("Role not found")

    @staticmethod
    def update(db: Session, link_id: str, payload: PersonRoleUpdate):
        link = db.get(PersonRole, coerce_uuid(link_id))
        if not link:
            raise PersonRoleNotFoundError("Person role not found")
        data = payload.model_dump(exclude_unset=True)
        PersonRoles._validate_link_ids(
            db,
            person_id=data.get("person_id"),
            role_id=data.get("role_id"),
        )
        for key, value in data.items():
            setattr(link, key, value)
        db.flush()
        db.refresh(link)
        return link

    @staticmethod
    def delete(db: Session, link_id: str):
        link = db.get(PersonRole, coerce_uuid(link_id))
        if not link:
            raise PersonRoleNotFoundError("Person role not found")
        db.delete(link)
        db.flush()


roles = Roles()
permissions = Permissions()
role_permissions = RolePermissions()
person_roles = PersonRoles()
