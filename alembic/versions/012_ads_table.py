"""Create ads table.

Revision ID: 012_ads_table
Revises: 011_wards_table
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "012_ads_table"
down_revision = "011_wards_table"
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


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Create enums
    existing = [e["name"] for e in inspector.get_enums()]

    if "adslot" not in existing:
        sa.Enum(
            "homepage_hero", "homepage_featured", "search_sidebar",
            "search_top", "profile_footer",
            name="adslot",
        ).create(conn)

    if "adtype" not in existing:
        sa.Enum("banner", "sponsored_school", "featured", name="adtype").create(conn)

    if "adstatus" not in existing:
        sa.Enum("draft", "active", "paused", "expired", name="adstatus").create(conn)

    if not inspector.has_table("ads"):
        op.create_table(
            "ads",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("slot", ENUM(
                "homepage_hero", "homepage_featured", "search_sidebar",
                "search_top", "profile_footer",
                name="adslot", create_type=False,
            ), nullable=False),
            sa.Column("ad_type", ENUM(
                "banner", "sponsored_school", "featured",
                name="adtype", create_type=False,
            ), nullable=False),
            sa.Column("status", ENUM(
                "draft", "active", "paused", "expired",
                name="adstatus", create_type=False,
            ), nullable=False, server_default="draft"),
            sa.Column("image_url", sa.String(512), nullable=True),
            sa.Column("target_url", sa.String(512), nullable=True),
            sa.Column("html_content", sa.Text(), nullable=True),
            sa.Column("alt_text", sa.String(255), nullable=True),
            sa.Column("school_id", UUID(as_uuid=True),
                      sa.ForeignKey("schools.id"), nullable=True),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False,
                      server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
        )

    # Indexes
    if inspector.has_table("ads"):
        if not _has_index(inspector, "ads", "ix_ads_slot_status"):
            op.create_index("ix_ads_slot_status", "ads", ["slot", "status"])
        if not _has_index(inspector, "ads", "ix_ads_status_schedule"):
            op.create_index("ix_ads_status_schedule", "ads",
                            ["status", "starts_at", "ends_at"])
        if not _has_index(inspector, "ads", "ix_ads_school_id"):
            op.create_index("ix_ads_school_id", "ads", ["school_id"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("ads"):
        for idx_name in ("ix_ads_school_id", "ix_ads_status_schedule", "ix_ads_slot_status"):
            if _has_index(inspector, "ads", idx_name):
                op.drop_index(idx_name, table_name="ads")
        op.drop_table("ads")

    existing = [e["name"] for e in inspector.get_enums()]
    for enum_name in ("adstatus", "adtype", "adslot"):
        if enum_name in existing:
            sa.Enum(name=enum_name).drop(conn)
