"""SchoolNet portal authentication dependencies."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.school import School
from app.models.rbac import PersonRole, Role
from app.services.common import require_uuid
from app.services.school import SchoolService
from app.web.deps import WebAuthRedirect, require_web_auth

logger = logging.getLogger(__name__)


def _has_role(db: Session, person_id: str, role_name: str) -> bool:
    """Check if a person has a specific role."""
    stmt = select(Role).where(Role.name == role_name, Role.is_active.is_(True))
    role = db.scalar(stmt)
    if not role:
        return False
    link_stmt = select(PersonRole).where(
        PersonRole.person_id == require_uuid(person_id),
        PersonRole.role_id == role.id,
    )
    return db.scalar(link_stmt) is not None


def get_school_for_admin(db: Session, current_user: Any) -> School | None:
    schools = SchoolService(db).get_schools_for_owner(current_user.person_id)
    return schools[0] if schools else None


def require_parent_auth(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_web_auth),
) -> dict:
    """Require authenticated user with parent role."""
    roles = auth.get("roles", [])
    person_id = auth["person_id"]
    if "parent" not in roles and not _has_role(db, person_id, "parent"):
        raise WebAuthRedirect(next_url="/login")
    return auth


def require_school_admin_auth(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_web_auth),
) -> dict:
    """Require authenticated user with school_admin role."""
    roles = auth.get("roles", [])
    person_id = auth["person_id"]
    if "school_admin" not in roles and not _has_role(db, person_id, "school_admin"):
        raise WebAuthRedirect(next_url="/login")
    return auth


def require_platform_admin_auth(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_web_auth),
) -> dict:
    """Require authenticated user with platform_admin or admin role."""
    roles = auth.get("roles", [])
    person_id = auth["person_id"]
    if (
        "platform_admin" not in roles
        and "admin" not in roles
        and not _has_role(db, person_id, "platform_admin")
        and not _has_role(db, person_id, "admin")
    ):
        raise WebAuthRedirect(next_url="/login")
    return auth
