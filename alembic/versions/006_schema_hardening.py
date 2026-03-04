"""Schema hardening: wards table and missing constraints/indexes.

Revision ID: 006_schema_hardening
Revises: 005_schoolnet
Create Date: 2026-02-25
"""

from alembic import op
import sqlalchemy as sa

revision = "006_schema_hardening"
down_revision = "005_schoolnet"
branch_labels = None
depends_on = None


def _has_fk(inspector, table: str, constrained_columns: list[str]) -> bool:
    return any(
        fk.get("constrained_columns") == constrained_columns
        for fk in inspector.get_foreign_keys(table)
    )


def _has_check(inspector, table: str, name: str) -> bool:
    return any(c.get("name") == name for c in inspector.get_check_constraints(table))


def _has_index(
    inspector, table: str, name: str, columns: list[str] | None = None
) -> bool:
    for idx in inspector.get_indexes(table):
        if idx.get("name") != name:
            continue
        if columns is None:
            return True
        return idx.get("column_names") == columns
    return False


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("file_uploads"):
        if not _has_fk(inspector, "file_uploads", ["uploaded_by"]):
            op.create_foreign_key(
                "fk_file_uploads_uploaded_by_people",
                "file_uploads",
                "people",
                ["uploaded_by"],
                ["id"],
            )
        if _has_index(inspector, "file_uploads", "ix_file_uploads_entity"):
            if not _has_index(
                inspector,
                "file_uploads",
                "ix_file_uploads_entity",
                ["entity_type", "entity_id", "is_active"],
            ):
                op.drop_index("ix_file_uploads_entity", table_name="file_uploads")
                op.create_index(
                    "ix_file_uploads_entity",
                    "file_uploads",
                    ["entity_type", "entity_id", "is_active"],
                )
        else:
            op.create_index(
                "ix_file_uploads_entity",
                "file_uploads",
                ["entity_type", "entity_id", "is_active"],
            )
        if not _has_check(
            inspector, "file_uploads", "ck_file_uploads_file_size_positive"
        ):
            op.create_check_constraint(
                "ck_file_uploads_file_size_positive",
                "file_uploads",
                "file_size > 0",
            )

    if inspector.has_table("notifications"):
        if not _has_fk(inspector, "notifications", ["recipient_id"]):
            op.create_foreign_key(
                "fk_notifications_recipient_id_people",
                "notifications",
                "people",
                ["recipient_id"],
                ["id"],
            )
        if not _has_fk(inspector, "notifications", ["sender_id"]):
            op.create_foreign_key(
                "fk_notifications_sender_id_people",
                "notifications",
                "people",
                ["sender_id"],
                ["id"],
            )
        if not _has_index(
            inspector,
            "notifications",
            "ix_notifications_recipient_created",
            ["recipient_id", "created_at"],
        ):
            op.create_index(
                "ix_notifications_recipient_created",
                "notifications",
                ["recipient_id", "created_at"],
            )

    if inspector.has_table("applications"):
        if not _has_index(
            inspector,
            "applications",
            "ix_applications_form_status",
            ["admission_form_id", "status"],
        ):
            op.create_index(
                "ix_applications_form_status",
                "applications",
                ["admission_form_id", "status"],
            )
        if not _has_index(
            inspector,
            "applications",
            "ix_applications_parent_status",
            ["parent_id", "status"],
        ):
            op.create_index(
                "ix_applications_parent_status",
                "applications",
                ["parent_id", "status"],
            )

    if inspector.has_table("ratings"):
        if not _has_check(inspector, "ratings", "ck_ratings_score_range"):
            op.create_check_constraint(
                "ck_ratings_score_range",
                "ratings",
                "score >= 1 AND score <= 5",
            )
        if not _has_index(
            inspector,
            "ratings",
            "ix_ratings_school_active",
            ["school_id", "is_active"],
        ):
            op.create_index(
                "ix_ratings_school_active",
                "ratings",
                ["school_id", "is_active"],
            )


def _has_constraint(inspector, table: str, name: str) -> bool:
    """Check if a named foreign key or check constraint exists."""
    for fk in inspector.get_foreign_keys(table):
        if fk.get("name") == name:
            return True
    for ck in inspector.get_check_constraints(table):
        if ck.get("name") == name:
            return True
    return False


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("ratings"):
        if _has_index(inspector, "ratings", "ix_ratings_school_active"):
            op.drop_index("ix_ratings_school_active", table_name="ratings")
        if _has_constraint(inspector, "ratings", "ck_ratings_score_range"):
            op.drop_constraint("ck_ratings_score_range", "ratings", type_="check")

    if inspector.has_table("applications"):
        if _has_index(inspector, "applications", "ix_applications_parent_status"):
            op.drop_index("ix_applications_parent_status", table_name="applications")
        if _has_index(inspector, "applications", "ix_applications_form_status"):
            op.drop_index("ix_applications_form_status", table_name="applications")

    if inspector.has_table("notifications"):
        if _has_index(inspector, "notifications", "ix_notifications_recipient_created"):
            op.drop_index("ix_notifications_recipient_created", table_name="notifications")
        if _has_constraint(inspector, "notifications", "fk_notifications_sender_id_people"):
            op.drop_constraint("fk_notifications_sender_id_people", "notifications", type_="foreignkey")
        if _has_constraint(inspector, "notifications", "fk_notifications_recipient_id_people"):
            op.drop_constraint("fk_notifications_recipient_id_people", "notifications", type_="foreignkey")

    if inspector.has_table("file_uploads"):
        if _has_constraint(inspector, "file_uploads", "ck_file_uploads_file_size_positive"):
            op.drop_constraint("ck_file_uploads_file_size_positive", "file_uploads", type_="check")
        if _has_constraint(inspector, "file_uploads", "fk_file_uploads_uploaded_by_people"):
            op.drop_constraint("fk_file_uploads_uploaded_by_people", "file_uploads", type_="foreignkey")
