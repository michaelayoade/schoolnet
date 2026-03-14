"""Add budget_cents and spent_cents columns to ads table.

Revision ID: 013_ad_budget
Revises: 012_ads_table
"""

import sqlalchemy as sa

from alembic import op

revision = "013_ad_budget"
down_revision = "012_ads_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ads", sa.Column("budget_cents", sa.Integer(), nullable=True))
    op.add_column(
        "ads",
        sa.Column("spent_cents", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("ads", "spent_cents")
    op.drop_column("ads", "budget_cents")
