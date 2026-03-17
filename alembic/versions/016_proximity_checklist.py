"""Add lat/lng to schools and people, exam_prep_checklist to shortlists.

Revision ID: 014_proximity_and_exam_checklist
Revises: 013_exam_registration_status
Create Date: 2026-03-17
"""

import sqlalchemy as sa

from alembic import op

revision = "016_proximity_checklist"
down_revision = "015_exam_reg_status"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Schools: lat/lng
    for col_name in ("latitude", "longitude"):
        if not _has_column(inspector, "schools", col_name):
            op.add_column("schools", sa.Column(col_name, sa.Float(), nullable=True))

    # People: lat/lng
    for col_name in ("latitude", "longitude"):
        if not _has_column(inspector, "people", col_name):
            op.add_column("people", sa.Column(col_name, sa.Float(), nullable=True))

    # Shortlists: exam prep checklist
    if inspector.has_table("school_shortlists") and not _has_column(
        inspector, "school_shortlists", "exam_prep_checklist"
    ):
        op.add_column(
            "school_shortlists",
            sa.Column("exam_prep_checklist", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("school_shortlists") and _has_column(
        inspector, "school_shortlists", "exam_prep_checklist"
    ):
        op.drop_column("school_shortlists", "exam_prep_checklist")

    for col_name in ("longitude", "latitude"):
        if _has_column(inspector, "people", col_name):
            op.drop_column("people", col_name)
        if _has_column(inspector, "schools", col_name):
            op.drop_column("schools", col_name)
