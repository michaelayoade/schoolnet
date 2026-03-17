"""Backfill UserCredential.username from person email where null.

Revision ID: 016_backfill_username
Revises: 015_seed_reminder_task
Create Date: 2026-03-17
"""

import sqlalchemy as sa

from alembic import op

revision = "018_backfill_username"
down_revision = "017_seed_reminder_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE user_credentials "
            "SET username = p.email "
            "FROM people p "
            "WHERE user_credentials.person_id = p.id "
            "AND user_credentials.username IS NULL "
            "AND user_credentials.provider = 'local'"
        )
    )


def downgrade() -> None:
    # No-op — backfill is safe to leave in place
    pass
