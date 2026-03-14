"""Add is_featured column to schools.

Revision ID: 008_featured_schools
Revises: 007_branding_domain
Create Date: 2026-02-25
"""

import sqlalchemy as sa

from alembic import op

revision = "008_featured_schools"
down_revision = "007_branding_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("schools")]

    if "is_featured" not in columns:
        op.add_column(
            "schools",
            sa.Column(
                "is_featured",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("schools")]

    if "is_featured" in columns:
        op.drop_column("schools", "is_featured")
