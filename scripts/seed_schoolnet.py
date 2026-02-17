"""Seed SchoolNet-specific RBAC roles and permissions."""

from dotenv import load_dotenv

from app.db import SessionLocal
from app.models.rbac import Permission, PersonRole, Role, RolePermission

SCHOOLNET_PERMISSIONS = [
    ("schools:read", "View school profiles"),
    ("schools:write", "Create and edit schools"),
    ("schools:approve", "Approve or suspend schools"),
    ("admission_forms:read", "View admission forms"),
    ("admission_forms:write", "Create and edit admission forms"),
    ("applications:read", "View applications"),
    ("applications:write", "Submit and update applications"),
    ("applications:review", "Review and decide on applications"),
    ("payments:read", "View payment records"),
    ("payments:write", "Initiate payments"),
    ("ratings:read", "View ratings"),
    ("ratings:write", "Create ratings"),
]

SCHOOLNET_ROLES = [
    ("parent", "Parent or guardian seeking school admission"),
    ("school_admin", "School administrator managing admissions"),
    ("platform_admin", "Platform administrator overseeing all schools"),
]

ROLE_PERMISSIONS = {
    "parent": [
        "schools:read",
        "admission_forms:read",
        "applications:read",
        "applications:write",
        "payments:read",
        "payments:write",
        "ratings:read",
        "ratings:write",
    ],
    "school_admin": [
        "schools:read",
        "schools:write",
        "admission_forms:read",
        "admission_forms:write",
        "applications:read",
        "applications:review",
        "payments:read",
        "ratings:read",
    ],
    "platform_admin": [perm for perm, _ in SCHOOLNET_PERMISSIONS],
}


def _ensure_role(db, name: str, description: str) -> Role:  # type: ignore[return]
    role = db.query(Role).filter(Role.name == name).first()
    if not role:
        role = Role(name=name, description=description, is_active=True)
        db.add(role)
    else:
        if not role.is_active:
            role.is_active = True
        if description and not role.description:
            role.description = description
    return role


def _ensure_permission(db, key: str, description: str) -> Permission:  # type: ignore[return]
    perm = db.query(Permission).filter(Permission.key == key).first()
    if not perm:
        perm = Permission(key=key, description=description, is_active=True)
        db.add(perm)
    else:
        if not perm.is_active:
            perm.is_active = True
        if description and not perm.description:
            perm.description = description
    return perm


def _ensure_role_permission(db, role_id, permission_id) -> RolePermission:  # type: ignore[return]
    link = (
        db.query(RolePermission)
        .filter(RolePermission.role_id == role_id)
        .filter(RolePermission.permission_id == permission_id)
        .first()
    )
    if not link:
        link = RolePermission(role_id=role_id, permission_id=permission_id)
        db.add(link)
    return link


def main() -> None:
    load_dotenv()
    db = SessionLocal()
    try:
        # Create roles and permissions
        for name, description in SCHOOLNET_ROLES:
            _ensure_role(db, name, description)
        for key, description in SCHOOLNET_PERMISSIONS:
            _ensure_permission(db, key, description)
        db.commit()

        # Link permissions to roles
        roles = {r.name: r for r in db.query(Role).all()}
        permissions = {p.key: p for p in db.query(Permission).all()}
        for role_name, perm_keys in ROLE_PERMISSIONS.items():
            role = roles.get(role_name)
            if not role:
                continue
            for key in perm_keys:
                perm = permissions.get(key)
                if not perm:
                    continue
                _ensure_role_permission(db, role.id, perm.id)
        db.commit()
        print("SchoolNet RBAC seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
