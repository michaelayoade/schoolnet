from app.schemas.rbac import (
    PermissionCreate,
    PermissionUpdate,
    RoleCreate,
    RolePermissionCreate,
    RoleUpdate,
)
from app.services.rbac import Permissions, RolePermissions, Roles


def test_role_permission_link_flow(db_session):
    role = Roles(db_session).create(RoleCreate(name="Support"))
    permission = Permissions(db_session).create(
        PermissionCreate(key="people:read", description="Read People")
    )
    link = RolePermissions(db_session).create(
        RolePermissionCreate(role_id=role.id, permission_id=permission.id),
    )
    items, total = RolePermissions(db_session).list(
        role_id=role.id,
        permission_id=None,
        order_by="role_id",
        order_dir="desc",
        limit=10,
        offset=0,
    )
    assert total == 1
    assert items[0].id == link.id


def test_role_permission_soft_delete_filters(db_session):
    role = Roles(db_session).create(RoleCreate(name="Settings"))
    Roles(db_session).update(str(role.id), RoleUpdate(name="Settings Ops"))
    Roles(db_session).delete(str(role.id))
    active, active_total = Roles(db_session).list(
        is_active=None,
        order_by="created_at",
        order_dir="desc",
        limit=10,
        offset=0,
    )
    inactive, inactive_total = Roles(db_session).list(
        is_active=False,
        order_by="created_at",
        order_dir="desc",
        limit=10,
        offset=0,
    )
    assert active_total >= 0
    assert inactive_total >= 1
    assert role not in active
    assert any(item.id == role.id for item in inactive)


def test_permission_update(db_session):
    permission = Permissions(db_session).create(
        PermissionCreate(key="settings:write", description="Settings Write")
    )
    updated = Permissions(db_session).update(
        str(permission.id),
        PermissionUpdate(description="Settings Write Access"),
    )
    assert updated.description == "Settings Write Access"
