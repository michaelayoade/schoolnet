"""Ward service — CRUD operations for parent's wards (children)."""

import logging
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ward import Ward

logger = logging.getLogger(__name__)


class WardService:
    """Service for managing ward (child) operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        parent_id: UUID,
        first_name: str,
        last_name: str,
        date_of_birth: date | None = None,
        gender: str | None = None,
        passport_url: str | None = None,
    ) -> Ward:
        """Create a new ward for a parent."""
        ward = Ward(
            parent_id=parent_id,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            gender=gender,
            passport_url=passport_url,
        )
        self.db.add(ward)
        self.db.flush()
        logger.info("Created ward %s for parent %s", ward.id, parent_id)
        return ward

    def get_by_id(self, ward_id: UUID) -> Ward | None:
        """Get a ward by ID."""
        ward: Ward | None = self.db.get(Ward, ward_id)
        return ward

    def list_for_parent(self, parent_id: UUID) -> list[Ward]:
        """List all active wards for a parent."""
        stmt = (
            select(Ward)
            .where(Ward.parent_id == parent_id, Ward.is_active.is_(True))
            .order_by(Ward.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def update(
        self,
        ward: Ward,
        first_name: str | None = None,
        last_name: str | None = None,
        date_of_birth: date | None = None,
        gender: str | None = None,
        passport_url: str | None = None,
    ) -> Ward:
        """Update an existing ward's details."""
        if first_name is not None:
            ward.first_name = first_name
        if last_name is not None:
            ward.last_name = last_name
        if date_of_birth is not None:
            ward.date_of_birth = date_of_birth
        if gender is not None:
            ward.gender = gender
        if passport_url is not None:
            ward.passport_url = passport_url
        self.db.flush()
        logger.info("Updated ward %s", ward.id)
        return ward

    def delete(self, ward: Ward) -> Ward:
        """Soft-delete a ward by setting is_active to False."""
        ward.is_active = False
        self.db.flush()
        logger.info("Soft-deleted ward %s", ward.id)
        return ward
