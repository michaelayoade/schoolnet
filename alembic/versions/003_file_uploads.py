"""003 – file_uploads table

Revision ID: 003_file_uploads
Revises: 002_billing
Create Date: 2026-02-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "003_file_uploads"
down_revision = "002_billing"
branch_labels = None
depends_on = None


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


def _has_fk(
    inspector, table: str, constrained_columns: list[str], referred_table: str
) -> bool:
    return _fk_name(inspector, table, constrained_columns, referred_table) is not None


def _fk_name(
    inspector, table: str, constrained_columns: list[str], referred_table: str
) -> str | None:
    for fk in inspector.get_foreign_keys(table):
        if fk.get("referred_table") != referred_table:
            continue
        if fk.get("constrained_columns") == constrained_columns:
            return fk.get("name")
    return None


def _has_check_constraint(inspector, table: str, name: str) -> bool:
    return any(
        constraint.get("name") == name
        for constraint in inspector.get_check_constraints(table)
    )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("file_uploads"):
        # Create enum type if it doesn't exist
        file_upload_status = postgresql.ENUM(
            "pending", "active", "deleted", name="fileuploadstatus", create_type=False
        )
        file_upload_status.create(conn, checkfirst=True)

        op.create_table(
            "file_uploads",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("original_filename", sa.String(512), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("storage_backend", sa.String(20), server_default="local"),
            sa.Column("storage_key", sa.String(512), nullable=False),
            sa.Column("url", sa.Text(), nullable=True),
            sa.Column("category", sa.String(40), server_default="document"),
            sa.Column("entity_type", sa.String(80), nullable=True),
            sa.Column("entity_id", sa.String(120), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM(
                    "pending",
                    "active",
                    "deleted",
                    name="fileuploadstatus",
                    create_type=False,
                ),
                server_default="active",
            ),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
    if inspector.has_table("file_uploads") and not _has_fk(
        inspector,
        "file_uploads",
        ["uploaded_by"],
        "people",
    ):
        op.create_foreign_key(
            "fk_file_uploads_uploaded_by_people",
            "file_uploads",
            "people",
            ["uploaded_by"],
            ["id"],
        )

    if inspector.has_table("file_uploads") and not _has_index(
        inspector,
        "file_uploads",
        "ix_file_uploads_uploaded_by",
        ["uploaded_by"],
    ):
        op.create_index("ix_file_uploads_uploaded_by", "file_uploads", ["uploaded_by"])

    if inspector.has_table("file_uploads") and not _has_index(
        inspector,
        "file_uploads",
        "ix_file_uploads_category",
        ["category"],
    ):
        op.create_index("ix_file_uploads_category", "file_uploads", ["category"])

    if inspector.has_table("file_uploads") and not _has_index(
        inspector,
        "file_uploads",
        "ix_file_uploads_entity",
        ["entity_type", "entity_id", "is_active"],
    ):
        if _has_index(
            inspector,
            "file_uploads",
            "ix_file_uploads_entity",
            ["entity_type", "entity_id"],
        ):
            op.drop_index("ix_file_uploads_entity", table_name="file_uploads")
        op.create_index(
            "ix_file_uploads_entity",
            "file_uploads",
            ["entity_type", "entity_id", "is_active"],
        )

    if inspector.has_table("file_uploads") and not _has_check_constraint(
        inspector,
        "file_uploads",
        "ck_file_uploads_file_size_positive",
    ):
        op.create_check_constraint(
            "ck_file_uploads_file_size_positive",
            "file_uploads",
            "file_size > 0",
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("file_uploads"):
        if _has_check_constraint(
            inspector,
            "file_uploads",
            "ck_file_uploads_file_size_positive",
        ):
            op.drop_constraint(
                "ck_file_uploads_file_size_positive",
                "file_uploads",
                type_="check",
            )
        fk_name = _fk_name(
            inspector,
            "file_uploads",
            ["uploaded_by"],
            "people",
        )
        if fk_name:
            op.drop_constraint(
                fk_name,
                "file_uploads",
                type_="foreignkey",
            )
        if _has_index(
            inspector,
            "file_uploads",
            "ix_file_uploads_entity",
        ):
            op.drop_index("ix_file_uploads_entity", table_name="file_uploads")
        if _has_index(
            inspector,
            "file_uploads",
            "ix_file_uploads_category",
        ):
            op.drop_index("ix_file_uploads_category", table_name="file_uploads")
        if _has_index(
            inspector,
            "file_uploads",
            "ix_file_uploads_uploaded_by",
        ):
            op.drop_index("ix_file_uploads_uploaded_by", table_name="file_uploads")
        op.drop_table("file_uploads")
    op.execute("DROP TYPE IF EXISTS fileuploadstatus")
