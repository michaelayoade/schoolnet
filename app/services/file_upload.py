"""File upload service — CRUD + storage integration."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.file_upload import FileUpload, FileUploadStatus
from app.models.person import Person
from app.models.school import Application, School
from app.services.common import require_uuid
from app.services.storage import StorageBackend, get_storage_backend

logger = logging.getLogger(__name__)


class FileUploadService:
    """Manages file upload records and storage."""

    ALLOWED_ENTITY_TYPES = frozenset({"application", "school", "user"})

    def __init__(self, db: Session, storage: StorageBackend | None = None) -> None:
        self.db = db
        self.storage = storage or get_storage_backend()

    @staticmethod
    def _normalize_roles(
        roles: list[str] | set[str] | tuple[str, ...] | None,
    ) -> set[str]:
        return {
            str(role).strip().lower() for role in (roles or []) if str(role).strip()
        }

    def _validate_entity_ownership(
        self,
        *,
        actor_id: UUID | None,
        entity_type: str | None,
        entity_id: str | None,
    ) -> tuple[str | None, str | None]:
        if entity_type is None and entity_id is None:
            return None, None
        if not entity_type or not entity_id:
            raise ValueError("entity_type and entity_id must both be provided")
        if actor_id is None:
            raise PermissionError(
                "Authenticated caller required for entity-linked upload"
            )

        normalized_entity_type = entity_type.strip().lower()
        if normalized_entity_type not in self.ALLOWED_ENTITY_TYPES:
            allowed = ", ".join(sorted(self.ALLOWED_ENTITY_TYPES))
            raise ValueError(
                f"Unsupported entity_type '{entity_type}'. Allowed: {allowed}"
            )

        try:
            entity_uuid = require_uuid(entity_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("entity_id must be a valid UUID") from exc

        if normalized_entity_type == "application":
            application = self.db.get(Application, entity_uuid)
            if not application or not application.is_active:
                raise ValueError("Application not found")
            if application.parent_id != actor_id:
                raise PermissionError(
                    "Not allowed to upload files for this application"
                )
        elif normalized_entity_type == "school":
            school = self.db.get(School, entity_uuid)
            if not school or not school.is_active:
                raise ValueError("School not found")
            if school.owner_id != actor_id:
                raise PermissionError("Not allowed to upload files for this school")
        else:
            user = self.db.get(Person, entity_uuid)
            if not user or not user.is_active:
                raise ValueError("User not found")
            if user.id != actor_id:
                raise PermissionError("Not allowed to upload files for this user")

        return normalized_entity_type, str(entity_uuid)

    def upload(
        self,
        content: bytes,
        filename: str,
        content_type: str,
        uploaded_by: UUID | None = None,
        category: str = "document",
        entity_type: str | None = None,
        entity_id: str | None = None,
        metadata_: dict | None = None,
        actor_id: UUID | None = None,
    ) -> FileUpload:
        """Upload a file and create a database record."""
        allowed = {t.strip() for t in settings.upload_allowed_types.split(",")}
        if content_type not in allowed:
            raise ValueError(f"File type '{content_type}' not allowed")
        if len(content) > settings.upload_max_size_bytes:
            max_mb = settings.upload_max_size_bytes // (1024 * 1024)
            raise ValueError(f"File too large. Maximum size: {max_mb}MB")

        normalized_entity_type, normalized_entity_id = self._validate_entity_ownership(
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        storage_key = self.storage.save(content, filename, content_type)
        url = self.storage.get_url(storage_key)

        record = FileUpload(
            uploaded_by=uploaded_by or actor_id,
            original_filename=filename,
            content_type=content_type,
            file_size=len(content),
            storage_backend=settings.storage_backend,
            storage_key=storage_key,
            url=url,
            category=category,
            entity_type=normalized_entity_type,
            entity_id=normalized_entity_id,
            status=FileUploadStatus.active,
            metadata_=metadata_,
        )
        self.db.add(record)
        self.db.flush()
        logger.info("Uploaded file: %s (id=%s)", filename, record.id)
        return record

    def get_by_id(self, file_id: UUID) -> FileUpload | None:
        """Get a file upload by ID."""
        return self.db.get(FileUpload, file_id)

    def list_uploads(
        self,
        *,
        uploaded_by: UUID | None = None,
        category: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FileUpload]:
        """List file uploads with optional filters."""
        stmt = select(FileUpload).where(
            FileUpload.is_active.is_(True),
            FileUpload.status == FileUploadStatus.active,
        )
        if uploaded_by is not None:
            stmt = stmt.where(FileUpload.uploaded_by == uploaded_by)
        if category is not None:
            stmt = stmt.where(FileUpload.category == category)
        if entity_type is not None:
            stmt = stmt.where(FileUpload.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(FileUpload.entity_id == entity_id)
        stmt = stmt.order_by(FileUpload.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())

    def count(
        self,
        *,
        uploaded_by: UUID | None = None,
        category: str | None = None,
    ) -> int:
        """Count active file uploads."""
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(FileUpload)
            .where(
                FileUpload.is_active.is_(True),
                FileUpload.status == FileUploadStatus.active,
            )
        )
        if uploaded_by is not None:
            stmt = stmt.where(FileUpload.uploaded_by == uploaded_by)
        if category is not None:
            stmt = stmt.where(FileUpload.category == category)
        result = self.db.execute(stmt).scalar()
        return result or 0

    def delete(
        self,
        file_id: UUID,
        *,
        actor_id: UUID,
        roles: list[str] | set[str] | tuple[str, ...] | None = None,
    ) -> None:
        """Soft-delete a file upload and remove from storage."""
        record = self.db.get(FileUpload, file_id)
        if not record:
            raise ValueError("File upload not found")

        is_admin = "admin" in self._normalize_roles(roles)
        if not is_admin and record.uploaded_by != actor_id:
            raise PermissionError("Not allowed to delete this file upload")

        try:
            self.storage.delete(record.storage_key)
        except Exception:
            logger.exception(
                "Failed to delete file from storage: %s", record.storage_key
            )
        record.status = FileUploadStatus.deleted
        record.is_active = False
        self.db.flush()
        logger.info("Deleted file upload: %s", file_id)
