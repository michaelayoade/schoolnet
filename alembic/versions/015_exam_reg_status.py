"""Add exam_registration_status to school_shortlists.

Revision ID: 013_exam_registration_status
Revises: 012_admissions_management
Create Date: 2026-03-17
"""

import sqlalchemy as sa

from alembic import op

revision = "015_exam_reg_status"
down_revision = "014_admissions_mgmt"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("school_shortlists") and not _has_column(
        inspector, "school_shortlists", "exam_registration_status"
    ):
        op.add_column(
            "school_shortlists",
            sa.Column(
                "exam_registration_status",
                sa.String(20),
                nullable=False,
                server_default="not_required",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("school_shortlists") and _has_column(
        inspector, "school_shortlists", "exam_registration_status"
    ):
        op.drop_column("school_shortlists", "exam_registration_status")
