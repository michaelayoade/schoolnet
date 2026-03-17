"""Add admissions management: shortlists, calendar, and enrich school/ward/form models.

Revision ID: 012_admissions_management
Revises: 011_wards_table
Create Date: 2026-03-17
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "014_admissions_mgmt"
down_revision = "013_ad_budget"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


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

    # ── Extend schools table ────────────────────────────
    school_cols = {
        "religious_affiliation": sa.Column(
            "religious_affiliation", sa.String(100), nullable=True
        ),
        "curriculum_type": sa.Column("curriculum_type", sa.String(100), nullable=True),
        "special_needs_support": sa.Column(
            "special_needs_support",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        "special_needs_details": sa.Column(
            "special_needs_details", sa.Text(), nullable=True
        ),
        "admissions_contact_name": sa.Column(
            "admissions_contact_name", sa.String(255), nullable=True
        ),
        "admissions_contact_phone": sa.Column(
            "admissions_contact_phone", sa.String(40), nullable=True
        ),
        "admissions_contact_email": sa.Column(
            "admissions_contact_email", sa.String(255), nullable=True
        ),
    }
    for col_name, col_def in school_cols.items():
        if not _has_column(inspector, "schools", col_name):
            op.add_column("schools", col_def)

    # ── Extend wards table ──────────────────────────────
    ward_cols = {
        "religion": sa.Column("religion", sa.String(100), nullable=True),
        "has_special_needs": sa.Column(
            "has_special_needs",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        "special_needs_details": sa.Column(
            "special_needs_details", sa.Text(), nullable=True
        ),
        "current_school": sa.Column("current_school", sa.String(255), nullable=True),
    }
    for col_name, col_def in ward_cols.items():
        if not _has_column(inspector, "wards", col_name):
            op.add_column("wards", col_def)

    # ── Extend admission_forms table ────────────────────
    form_cols = {
        "has_entrance_exam": sa.Column(
            "has_entrance_exam",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        "exam_date": sa.Column("exam_date", sa.DateTime(timezone=True), nullable=True),
        "exam_time": sa.Column("exam_time", sa.String(50), nullable=True),
        "exam_venue": sa.Column("exam_venue", sa.String(255), nullable=True),
        "exam_requirements": sa.Column("exam_requirements", sa.JSON(), nullable=True),
        "interview_date": sa.Column(
            "interview_date", sa.DateTime(timezone=True), nullable=True
        ),
        "interview_time": sa.Column("interview_time", sa.String(50), nullable=True),
        "interview_venue": sa.Column("interview_venue", sa.String(255), nullable=True),
    }
    for col_name, col_def in form_cols.items():
        if not _has_column(inspector, "admission_forms", col_name):
            op.add_column("admission_forms", col_def)

    # ── Extend applications table ───────────────────────
    if not _has_column(inspector, "applications", "ward_id"):
        op.add_column(
            "applications",
            sa.Column("ward_id", UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_applications_ward_id",
            "applications",
            "wards",
            ["ward_id"],
            ["id"],
        )
        op.create_index("ix_applications_ward_id", "applications", ["ward_id"])

    # ── Create school_shortlists table ──────────────────
    if not inspector.has_table("school_shortlists"):
        op.create_table(
            "school_shortlists",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "parent_id",
                UUID(as_uuid=True),
                sa.ForeignKey("people.id"),
                nullable=False,
            ),
            sa.Column(
                "ward_id",
                UUID(as_uuid=True),
                sa.ForeignKey("wards.id"),
                nullable=False,
            ),
            sa.Column(
                "school_id",
                UUID(as_uuid=True),
                sa.ForeignKey("schools.id"),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="researching",
            ),
            sa.Column("rank", sa.Integer(), nullable=True),
            sa.Column("religious_fit", sa.Integer(), nullable=True),
            sa.Column("curriculum_fit", sa.Integer(), nullable=True),
            sa.Column("proximity_score", sa.Integer(), nullable=True),
            sa.Column("special_needs_fit", sa.Integer(), nullable=True),
            sa.Column("overall_fit", sa.Integer(), nullable=True),
            sa.Column("notes", sa.JSON(), nullable=True),
            sa.Column(
                "application_id",
                UUID(as_uuid=True),
                sa.ForeignKey("applications.id"),
                nullable=True,
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "parent_id",
                "ward_id",
                "school_id",
                name="uq_shortlists_parent_ward_school",
            ),
        )
        op.create_index("ix_shortlists_parent_id", "school_shortlists", ["parent_id"])
        op.create_index("ix_shortlists_ward_id", "school_shortlists", ["ward_id"])
        op.create_index("ix_shortlists_school_id", "school_shortlists", ["school_id"])

    # ── Create admissions_calendar_events table ─────────
    if not inspector.has_table("admissions_calendar_events"):
        op.create_table(
            "admissions_calendar_events",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "parent_id",
                UUID(as_uuid=True),
                sa.ForeignKey("people.id"),
                nullable=False,
            ),
            sa.Column(
                "ward_id",
                UUID(as_uuid=True),
                sa.ForeignKey("wards.id"),
                nullable=True,
            ),
            sa.Column(
                "school_id",
                UUID(as_uuid=True),
                sa.ForeignKey("schools.id"),
                nullable=True,
            ),
            sa.Column(
                "shortlist_id",
                UUID(as_uuid=True),
                sa.ForeignKey("school_shortlists.id"),
                nullable=True,
            ),
            sa.Column(
                "application_id",
                UUID(as_uuid=True),
                sa.ForeignKey("applications.id"),
                nullable=True,
            ),
            sa.Column(
                "event_type",
                sa.String(30),
                nullable=False,
                server_default="custom",
            ),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("event_date", sa.Date(), nullable=False),
            sa.Column("event_time", sa.String(50), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("venue", sa.String(255), nullable=True),
            sa.Column(
                "is_reminder_set",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "reminder_days_before",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("3"),
            ),
            sa.Column(
                "buffer_days_before",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
            sa.Column(
                "buffer_days_after",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "has_conflict",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("conflict_notes", sa.Text(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_cal_events_parent_id",
            "admissions_calendar_events",
            ["parent_id"],
        )
        op.create_index(
            "ix_cal_events_parent_date",
            "admissions_calendar_events",
            ["parent_id", "event_date"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Drop calendar events table
    if inspector.has_table("admissions_calendar_events"):
        op.drop_table("admissions_calendar_events")

    # Drop shortlists table
    if inspector.has_table("school_shortlists"):
        op.drop_table("school_shortlists")

    # Drop ward_id from applications
    if _has_column(inspector, "applications", "ward_id"):
        if _has_index(inspector, "applications", "ix_applications_ward_id"):
            op.drop_index("ix_applications_ward_id", table_name="applications")
        op.drop_constraint(
            "fk_applications_ward_id", "applications", type_="foreignkey"
        )
        op.drop_column("applications", "ward_id")

    # Drop admission_forms columns
    for col in (
        "interview_venue",
        "interview_time",
        "interview_date",
        "exam_requirements",
        "exam_venue",
        "exam_time",
        "exam_date",
        "has_entrance_exam",
    ):
        if _has_column(inspector, "admission_forms", col):
            op.drop_column("admission_forms", col)

    # Drop wards columns
    for col in (
        "current_school",
        "special_needs_details",
        "has_special_needs",
        "religion",
    ):
        if _has_column(inspector, "wards", col):
            op.drop_column("wards", col)

    # Drop schools columns
    for col in (
        "admissions_contact_email",
        "admissions_contact_phone",
        "admissions_contact_name",
        "special_needs_details",
        "special_needs_support",
        "curriculum_type",
        "religious_affiliation",
    ):
        if _has_column(inspector, "schools", col):
            op.drop_column("schools", col)
