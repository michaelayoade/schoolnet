"""004 – notifications table

Revision ID: 004_notifications
Revises: 003_file_uploads
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_notifications"
down_revision = "003_file_uploads"
branch_labels = None
depends_on = None


def _has_index(inspector, table: str, name: str, columns: list[str] | None = None) -> bool:
    for idx in inspector.get_indexes(table):
        if idx.get("name") != name:
            continue
        if columns is None:
            return True
        return idx.get("column_names") == columns
    return False


def _has_fk(inspector, table: str, constrained_columns: list[str], referred_table: str) -> bool:
    return _fk_name(inspector, table, constrained_columns, referred_table) is not None


def _fk_name(
    inspector, table: str, constrained_columns: list[str], referred_table: str
) -> str | None:
    for fk in inspector.get_foreign_keys(table):
        if fk.get("referred_table") != referred_table:
            continue
        if fk.get("constrained_columns") == constrained_columns:
            return fk.get("name")
    return None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("notifications"):
        notification_type = postgresql.ENUM(
            "info", "success", "warning", "error", "system",
            name="notificationtype", create_type=False,
        )
        notification_type.create(conn, checkfirst=True)

        op.create_table(
            "notifications",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column(
                "type",
                postgresql.ENUM("info", "success", "warning", "error", "system",
                                name="notificationtype", create_type=False),
                server_default="info",
            ),
            sa.Column("entity_type", sa.String(80), nullable=True),
            sa.Column("entity_id", sa.String(120), nullable=True),
            sa.Column("action_url", sa.String(512), nullable=True),
            sa.Column("is_read", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
    if inspector.has_table("notifications") and not _has_fk(
        inspector,
        "notifications",
        ["recipient_id"],
        "people",
    ):
        op.create_foreign_key(
            "fk_notifications_recipient_id_people",
            "notifications",
            "people",
            ["recipient_id"],
            ["id"],
        )

    if inspector.has_table("notifications") and not _has_fk(
        inspector,
        "notifications",
        ["sender_id"],
        "people",
    ):
        op.create_foreign_key(
            "fk_notifications_sender_id_people",
            "notifications",
            "people",
            ["sender_id"],
            ["id"],
        )

    if inspector.has_table("notifications") and not _has_index(
        inspector,
        "notifications",
        "ix_notifications_recipient_id",
        ["recipient_id"],
    ):
        op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])

    if inspector.has_table("notifications") and not _has_index(
        inspector,
        "notifications",
        "ix_notifications_recipient_read",
        ["recipient_id", "is_read"],
    ):
        op.create_index(
            "ix_notifications_recipient_read",
            "notifications",
            ["recipient_id", "is_read"],
        )

    if inspector.has_table("notifications") and not _has_index(
        inspector,
        "notifications",
        "ix_notifications_recipient_created",
        ["recipient_id", "created_at"],
    ):
        op.create_index(
            "ix_notifications_recipient_created",
            "notifications",
            ["recipient_id", "created_at"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("notifications"):
        if _has_index(inspector, "notifications", "ix_notifications_recipient_created"):
            op.drop_index("ix_notifications_recipient_created", table_name="notifications")
        if _has_index(inspector, "notifications", "ix_notifications_recipient_read"):
            op.drop_index("ix_notifications_recipient_read", table_name="notifications")
        if _has_index(inspector, "notifications", "ix_notifications_recipient_id"):
            op.drop_index("ix_notifications_recipient_id", table_name="notifications")
        sender_fk = _fk_name(inspector, "notifications", ["sender_id"], "people")
        if sender_fk:
            op.drop_constraint(
                sender_fk,
                "notifications",
                type_="foreignkey",
            )
        recipient_fk = _fk_name(inspector, "notifications", ["recipient_id"], "people")
        if recipient_fk:
            op.drop_constraint(
                recipient_fk,
                "notifications",
                type_="foreignkey",
            )
        op.drop_table("notifications")
    op.execute("DROP TYPE IF EXISTS notificationtype")
