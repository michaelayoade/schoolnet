"""Add indexes for audit_events table.

Revision ID: 009_audit_event_indexes
Revises: 008_featured_schools
Create Date: 2026-02-25
"""

import sqlalchemy as sa

from alembic import op

revision = "009_audit_event_indexes"
down_revision = "008_featured_schools"
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

    if not inspector.has_table("audit_events"):
        return

    if not _has_index(
        inspector,
        "audit_events",
        "ix_audit_events_occurred_at",
        ["occurred_at"],
    ):
        op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])

    if not _has_index(
        inspector,
        "audit_events",
        "ix_audit_events_actor_occurred",
        ["actor_id", "occurred_at"],
    ):
        op.create_index(
            "ix_audit_events_actor_occurred",
            "audit_events",
            ["actor_id", "occurred_at"],
        )

    if not _has_index(
        inspector,
        "audit_events",
        "ix_audit_events_entity",
        ["entity_type", "entity_id"],
    ):
        op.create_index(
            "ix_audit_events_entity",
            "audit_events",
            ["entity_type", "entity_id"],
        )

    if not _has_index(
        inspector,
        "audit_events",
        "ix_audit_events_request_id",
        ["request_id"],
    ):
        op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("audit_events"):
        return

    if _has_index(inspector, "audit_events", "ix_audit_events_request_id"):
        op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    if _has_index(inspector, "audit_events", "ix_audit_events_entity"):
        op.drop_index("ix_audit_events_entity", table_name="audit_events")
    if _has_index(inspector, "audit_events", "ix_audit_events_actor_occurred"):
        op.drop_index("ix_audit_events_actor_occurred", table_name="audit_events")
    if _has_index(inspector, "audit_events", "ix_audit_events_occurred_at"):
        op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
