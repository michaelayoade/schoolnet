"""SchoolNet schema – schools, admission_forms, applications, ratings.

Revision ID: 005_schoolnet
Revises: 004_notifications
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "005_schoolnet"
down_revision = "004_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # ── Enum types ───────────────────────────────────────
    for enum_name, values in [
        ("schoolstatus", ("pending", "active", "suspended", "verification_expired")),
        ("schooltype", ("primary", "secondary", "primary_secondary", "nursery", "nursery_primary")),
        ("schoolcategory", ("public", "private", "federal", "missionary")),
        ("schoolgender", ("mixed", "boys_only", "girls_only")),
        ("admissionformstatus", ("draft", "active", "closed", "archived")),
        ("applicationstatus", ("draft", "submitted", "under_review", "accepted", "rejected", "withdrawn")),
    ]:
        existing = [e["name"] for e in inspector.get_enums()]
        if enum_name not in existing:
            sa.Enum(*values, name=enum_name).create(conn)

    # ── Schools ──────────────────────────────────────────
    if not inspector.has_table("schools"):
        op.create_table(
            "schools",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("people.id"), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("slug", sa.String(255), nullable=False),
            sa.Column("school_type", sa.Enum("primary", "secondary", "primary_secondary", "nursery", "nursery_primary", name="schooltype", create_type=False), nullable=False),
            sa.Column("category", sa.Enum("public", "private", "federal", "missionary", name="schoolcategory", create_type=False), nullable=False),
            sa.Column("gender", sa.Enum("mixed", "boys_only", "girls_only", name="schoolgender", create_type=False), default="mixed"),
            sa.Column("description", sa.Text),
            sa.Column("address", sa.String(255)),
            sa.Column("city", sa.String(120)),
            sa.Column("state", sa.String(120)),
            sa.Column("lga", sa.String(120)),
            sa.Column("country_code", sa.String(2), default="NG"),
            sa.Column("phone", sa.String(40)),
            sa.Column("email", sa.String(255)),
            sa.Column("website", sa.String(512)),
            sa.Column("fee_range_min", sa.Integer),
            sa.Column("fee_range_max", sa.Integer),
            sa.Column("logo_url", sa.String(512)),
            sa.Column("cover_image_url", sa.String(512)),
            sa.Column("status", sa.Enum("pending", "active", "suspended", "verification_expired", name="schoolstatus", create_type=False), default="pending"),
            sa.Column("verified_at", sa.DateTime(timezone=True)),
            sa.Column("verified_by", UUID(as_uuid=True), sa.ForeignKey("people.id")),
            sa.Column("year_established", sa.Integer),
            sa.Column("student_capacity", sa.Integer),
            sa.Column("paystack_subaccount_code", sa.String(255)),
            sa.Column("bank_code", sa.String(20)),
            sa.Column("bank_name", sa.String(255)),
            sa.Column("account_number", sa.String(20)),
            sa.Column("account_name", sa.String(255)),
            sa.Column("commission_rate", sa.Integer),
            sa.Column("settlement_bank_verified", sa.Boolean, default=False),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("metadata", sa.JSON),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("slug", name="uq_schools_slug"),
        )

    # ── Admission Forms ──────────────────────────────────
    if not inspector.has_table("admission_forms"):
        op.create_table(
            "admission_forms",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("school_id", UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False, index=True),
            sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), index=True),
            sa.Column("price_id", UUID(as_uuid=True), sa.ForeignKey("prices.id"), index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("academic_year", sa.String(20), nullable=False),
            sa.Column("status", sa.Enum("draft", "active", "closed", "archived", name="admissionformstatus", create_type=False), default="draft"),
            sa.Column("max_submissions", sa.Integer),
            sa.Column("current_submissions", sa.Integer, default=0),
            sa.Column("opens_at", sa.DateTime(timezone=True)),
            sa.Column("closes_at", sa.DateTime(timezone=True)),
            sa.Column("required_documents", sa.JSON),
            sa.Column("form_fields", sa.JSON),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("metadata", sa.JSON),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    # ── Applications ─────────────────────────────────────
    if not inspector.has_table("applications"):
        op.create_table(
            "applications",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("admission_form_id", UUID(as_uuid=True), sa.ForeignKey("admission_forms.id"), nullable=False, index=True),
            sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("people.id"), nullable=False, index=True),
            sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id"), index=True),
            sa.Column("application_number", sa.String(30), nullable=False),
            sa.Column("ward_first_name", sa.String(80)),
            sa.Column("ward_last_name", sa.String(80)),
            sa.Column("ward_date_of_birth", sa.Date),
            sa.Column("ward_gender", sa.String(20)),
            sa.Column("ward_passport_url", sa.String(512)),
            sa.Column("form_responses", sa.JSON),
            sa.Column("document_urls", sa.JSON),
            sa.Column("status", sa.Enum("draft", "submitted", "under_review", "accepted", "rejected", "withdrawn", name="applicationstatus", create_type=False), default="draft"),
            sa.Column("submitted_at", sa.DateTime(timezone=True)),
            sa.Column("reviewed_at", sa.DateTime(timezone=True)),
            sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("people.id")),
            sa.Column("review_notes", sa.Text),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("metadata", sa.JSON),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("application_number", name="uq_applications_number"),
        )

    # ── Ratings ──────────────────────────────────────────
    if not inspector.has_table("ratings"):
        op.create_table(
            "ratings",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("school_id", UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False, index=True),
            sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("people.id"), nullable=False, index=True),
            sa.Column("score", sa.Integer, nullable=False),
            sa.Column("comment", sa.Text),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("school_id", "parent_id", name="uq_ratings_school_parent"),
        )


def downgrade() -> None:
    op.drop_table("ratings")
    op.drop_table("applications")
    op.drop_table("admission_forms")
    op.drop_table("schools")
    for enum_name in [
        "applicationstatus",
        "admissionformstatus",
        "schoolgender",
        "schoolcategory",
        "schooltype",
        "schoolstatus",
    ]:
        sa.Enum(name=enum_name).drop(op.get_bind())
