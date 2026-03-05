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
    def __init__(self, db: Session) -> None:
        self.db = db

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

    def create(self, payload: RoleCreate):
        role = Role(**payload.model_dump())
        self.db.add(role)
        self.db.flush()
        self.db.refresh(role)
        return role

    def get(self, role_id: str):
        role = self.db.get(Role, coerce_uuid(role_id))
        if not role:
            raise RoleNotFoundError("Role not found")
        return role

    def list(
        self,
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
        total = self.db.scalar(count_stmt) or 0

        stmt = Roles._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def update(self, role_id: str, payload: RoleUpdate):
        role = self.db.get(Role, coerce_uuid(role_id))
        if not role:
            raise RoleNotFoundError("Role not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(role, key, value)
        self.db.flush()
        self.db.refresh(role)
        return role

    def delete(self, role_id: str):
        role = self.db.get(Role, coerce_uuid(role_id))
        if not role:
            raise RoleNotFoundError("Role not found")
        role.is_active = False
        self.db.flush()


class Permissions(ListResponseMixin):
    def __init__(self, db: Session) -> None:
        self.db = db

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

    def create(self, payload: PermissionCreate):
        permission = Permission(**payload.model_dump())
        self.db.add(permission)
        self.db.flush()
        self.db.refresh(permission)
        return permission

    def get(self, permission_id: str):
        permission = self.db.get(Permission, coerce_uuid(permission_id))
        if not permission:
            raise PermissionNotFoundError("Permission not found")
        return permission

    def list(
        self,
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
        total = self.db.scalar(count_stmt) or 0

        stmt = Permissions._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def update(self, permission_id: str, payload: PermissionUpdate):
        permission = self.db.get(Permission, coerce_uuid(permission_id))
        if not permission:
            raise PermissionNotFoundError("Permission not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(permission, key, value)
        self.db.flush()
        self.db.refresh(permission)
        return permission

    def delete(self, permission_id: str):
        permission = self.db.get(Permission, coerce_uuid(permission_id))
        if not permission:
            raise PermissionNotFoundError("Permission not found")
        permission.is_active = False
        self.db.flush()


class RolePermissions(ListResponseMixin):
    def __init__(self, db: Session) -> None:
        self.db = db

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

    def create(self, payload: RolePermissionCreate):
        role = self.db.get(Role, coerce_uuid(str(payload.role_id)))
        if not role:
            raise RoleNotFoundError("Role not found")
        permission = self.db.get(Permission, coerce_uuid(str(payload.permission_id)))
        if not permission:
            raise PermissionNotFoundError("Permission not found")

        link = RolePermission(**payload.model_dump())
        self.db.add(link)
        self.db.flush()
        self.db.refresh(link)
        return link

    def get(self, link_id: str):
        link = self.db.get(RolePermission, coerce_uuid(link_id))
        if not link:
            raise RolePermissionNotFoundError("Role permission not found")
        return link

    def list(
        self,
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
        total = self.db.scalar(count_stmt) or 0

        stmt = RolePermissions._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def _validate_link_ids(self, role_id: UUID | None, permission_id: UUID | None):
        if role_id is not None:
            role = self.db.get(Role, role_id)
            if not role:
                raise RoleNotFoundError("Role not found")
        if permission_id is not None:
            permission = self.db.get(Permission, permission_id)
            if not permission:
                raise PermissionNotFoundError("Permission not found")

    def update(self, link_id: str, payload: RolePermissionUpdate):
        link = self.db.get(RolePermission, coerce_uuid(link_id))
        if not link:
            raise RolePermissionNotFoundError("Role permission not found")
        data = payload.model_dump(exclude_unset=True)
        self._validate_link_ids(
            role_id=data.get("role_id"),
            permission_id=data.get("permission_id"),
        )
        for key, value in data.items():
            setattr(link, key, value)
        self.db.flush()
        self.db.refresh(link)
        return link

    def delete(self, link_id: str):
        link = self.db.get(RolePermission, coerce_uuid(link_id))
        if not link:
            raise RolePermissionNotFoundError("Role permission not found")
        self.db.delete(link)
        self.db.flush()


class PersonRoles(ListResponseMixin):
    def __init__(self, db: Session) -> None:
        self.db = db

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

    def create(self, payload: PersonRoleCreate):
        person = self.db.get(Person, coerce_uuid(str(payload.person_id)))
        if not person:
            raise PersonNotFoundError("Person not found")
        role = self.db.get(Role, coerce_uuid(str(payload.role_id)))
        if not role:
            raise RoleNotFoundError("Role not found")

        link = PersonRole(**payload.model_dump())
        self.db.add(link)
        self.db.flush()
        self.db.refresh(link)
        return link

    def get(self, link_id: str):
        link = self.db.get(PersonRole, coerce_uuid(link_id))
        if not link:
            raise PersonRoleNotFoundError("Person role not found")
        return link

    def list(
        self,
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
        total = self.db.scalar(count_stmt) or 0

        stmt = PersonRoles._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def _validate_link_ids(self, person_id: UUID | None, role_id: UUID | None):
        if person_id is not None:
            person = self.db.get(Person, person_id)
            if not person:
                raise PersonNotFoundError("Person not found")
        if role_id is not None:
            role = self.db.get(Role, role_id)
            if not role:
                raise RoleNotFoundError("Role not found")

    def update(self, link_id: str, payload: PersonRoleUpdate):
        link = self.db.get(PersonRole, coerce_uuid(link_id))
        if not link:
            raise PersonRoleNotFoundError("Person role not found")
        data = payload.model_dump(exclude_unset=True)
        self._validate_link_ids(
            person_id=data.get("person_id"),
            role_id=data.get("role_id"),
        )
        for key, value in data.items():
            setattr(link, key, value)
        self.db.flush()
        self.db.refresh(link)
        return link

    def delete(self, link_id: str):
        link = self.db.get(PersonRole, coerce_uuid(link_id))
        if not link:
            raise PersonRoleNotFoundError("Person role not found")
        self.db.delete(link)
        self.db.flush()
