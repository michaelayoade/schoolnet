"""Add branding setting domain and migrate branding record scope.

Revision ID: 007_branding_domain
Revises: 006_schema_hardening
Create Date: 2026-02-25
"""

from alembic import op

revision = "007_branding_domain"
down_revision = "006_schema_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE settingdomain ADD VALUE IF NOT EXISTS 'branding'")
    op.execute(
        """
        UPDATE domain_settings
        SET domain = 'branding'
        WHERE domain = 'scheduler'
          AND key = 'ui_branding'
        """
    )


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place.
    # Move branding record back to scheduler for logical rollback.
    op.execute(
        """
        UPDATE domain_settings
        SET domain = 'scheduler'
        WHERE domain = 'branding'
          AND key = 'ui_branding'
        """
    )
