"""Add missing auth person_id indexes.

Revision ID: 010_auth_person_id_indexes
Revises: 009_audit_event_indexes
Create Date: 2026-02-25
"""

import sqlalchemy as sa

from alembic import op

revision = "010_auth_person_id_indexes"
down_revision = "009_audit_event_indexes"
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

    if inspector.has_table("user_credentials") and not _has_index(
        inspector,
        "user_credentials",
        "ix_user_credentials_person_id",
        ["person_id"],
    ):
        op.create_index(
            "ix_user_credentials_person_id",
            "user_credentials",
            ["person_id"],
        )

    if inspector.has_table("mfa_methods") and not _has_index(
        inspector,
        "mfa_methods",
        "ix_mfa_methods_person_id",
        ["person_id"],
    ):
        op.create_index("ix_mfa_methods_person_id", "mfa_methods", ["person_id"])

    if inspector.has_table("sessions") and not _has_index(
        inspector,
        "sessions",
        "ix_sessions_person_id",
        ["person_id"],
    ):
        op.create_index("ix_sessions_person_id", "sessions", ["person_id"])

    if inspector.has_table("api_keys") and not _has_index(
        inspector,
        "api_keys",
        "ix_api_keys_person_id",
        ["person_id"],
    ):
        op.create_index("ix_api_keys_person_id", "api_keys", ["person_id"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("api_keys") and _has_index(
        inspector, "api_keys", "ix_api_keys_person_id"
    ):
        op.drop_index("ix_api_keys_person_id", table_name="api_keys")

    if inspector.has_table("sessions") and _has_index(
        inspector, "sessions", "ix_sessions_person_id"
    ):
        op.drop_index("ix_sessions_person_id", table_name="sessions")

    if inspector.has_table("mfa_methods") and _has_index(
        inspector, "mfa_methods", "ix_mfa_methods_person_id"
    ):
        op.drop_index("ix_mfa_methods_person_id", table_name="mfa_methods")

    if inspector.has_table("user_credentials") and _has_index(
        inspector, "user_credentials", "ix_user_credentials_person_id"
    ):
        op.drop_index("ix_user_credentials_person_id", table_name="user_credentials")
