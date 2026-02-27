"""add sessions person_id index

Revision ID: 006_sessions_person_id_index
Revises: 005_schoolnet
Create Date: 2026-02-27 00:00:00.000000
"""

from alembic import op

revision = "006_sessions_person_id_index"
down_revision = "005_schoolnet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_sessions_person_id", "sessions", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_person_id", table_name="sessions")
