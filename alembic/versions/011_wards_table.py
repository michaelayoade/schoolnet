"""Create wards table.

Revision ID: 011_wards_table
Revises: 010_auth_person_id_indexes
Create Date: 2026-02-25
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "011_wards_table"
down_revision = "010_auth_person_id_indexes"
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


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("wards"):
        op.create_table(
            "wards",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "parent_id",
                UUID(as_uuid=True),
                sa.ForeignKey("people.id"),
                nullable=False,
            ),
            sa.Column("first_name", sa.String(length=100), nullable=False),
            sa.Column("last_name", sa.String(length=100), nullable=False),
            sa.Column("date_of_birth", sa.Date(), nullable=True),
            sa.Column("gender", sa.String(length=20), nullable=True),
            sa.Column("passport_url", sa.String(length=512), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    if inspector.has_table("wards") and not _has_index(
        inspector,
        "wards",
        "ix_wards_parent_id",
        ["parent_id"],
    ):
        op.create_index("ix_wards_parent_id", "wards", ["parent_id"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("wards") and _has_index(
        inspector,
        "wards",
        "ix_wards_parent_id",
    ):
        op.drop_index("ix_wards_parent_id", table_name="wards")

    if inspector.has_table("wards"):
        op.drop_table("wards")
