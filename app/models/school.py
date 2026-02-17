import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# ── Enums ────────────────────────────────────────────────


class SchoolStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    suspended = "suspended"
    verification_expired = "verification_expired"


class SchoolType(str, enum.Enum):
    primary = "primary"
    secondary = "secondary"
    primary_secondary = "primary_secondary"
    nursery = "nursery"
    nursery_primary = "nursery_primary"


class SchoolCategory(str, enum.Enum):
    public = "public"
    private = "private"
    federal = "federal"
    missionary = "missionary"


class SchoolGender(str, enum.Enum):
    mixed = "mixed"
    boys_only = "boys_only"
    girls_only = "girls_only"


class AdmissionFormStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    closed = "closed"
    archived = "archived"


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    accepted = "accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"


# ── School ───────────────────────────────────────────────


class School(Base):
    __tablename__ = "schools"
    __table_args__ = (UniqueConstraint("slug", name="uq_schools_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)

    school_type: Mapped[SchoolType] = mapped_column(Enum(SchoolType), nullable=False)
    category: Mapped[SchoolCategory] = mapped_column(
        Enum(SchoolCategory), nullable=False
    )
    gender: Mapped[SchoolGender] = mapped_column(
        Enum(SchoolGender), default=SchoolGender.mixed
    )
    description: Mapped[str | None] = mapped_column(Text)

    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    lga: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str] = mapped_column(String(2), default="NG")

    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(512))

    fee_range_min: Mapped[int | None] = mapped_column(Integer)
    fee_range_max: Mapped[int | None] = mapped_column(Integer)

    logo_url: Mapped[str | None] = mapped_column(String(512))
    cover_image_url: Mapped[str | None] = mapped_column(String(512))

    status: Mapped[SchoolStatus] = mapped_column(
        Enum(SchoolStatus), default=SchoolStatus.pending
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id")
    )

    year_established: Mapped[int | None] = mapped_column(Integer)
    student_capacity: Mapped[int | None] = mapped_column(Integer)

    # Partnership fields for Paystack Split
    paystack_subaccount_code: Mapped[str | None] = mapped_column(String(255))
    bank_code: Mapped[str | None] = mapped_column(String(20))
    bank_name: Mapped[str | None] = mapped_column(String(255))
    account_number: Mapped[str | None] = mapped_column(String(20))
    account_name: Mapped[str | None] = mapped_column(String(255))
    commission_rate: Mapped[int | None] = mapped_column(Integer)
    settlement_bank_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    owner = relationship("Person", foreign_keys=[owner_id])
    admission_forms = relationship("AdmissionForm", back_populates="school")
    ratings = relationship("Rating", back_populates="school")


# ── Admission Form ───────────────────────────────────────


class AdmissionForm(Base):
    __tablename__ = "admission_forms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), index=True
    )
    price_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prices.id"), index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False)

    status: Mapped[AdmissionFormStatus] = mapped_column(
        Enum(AdmissionFormStatus), default=AdmissionFormStatus.draft
    )
    max_submissions: Mapped[int | None] = mapped_column(Integer)
    current_submissions: Mapped[int] = mapped_column(Integer, default=0)

    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    required_documents: Mapped[dict | None] = mapped_column(JSON)
    form_fields: Mapped[dict | None] = mapped_column(JSON)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    school = relationship("School", back_populates="admission_forms")
    product = relationship("Product")
    price = relationship("Price")
    applications = relationship("Application", back_populates="admission_form")


# ── Application ──────────────────────────────────────────


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("application_number", name="uq_applications_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    admission_form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admission_forms.id"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), index=True
    )

    application_number: Mapped[str] = mapped_column(String(30), nullable=False)

    ward_first_name: Mapped[str | None] = mapped_column(String(80))
    ward_last_name: Mapped[str | None] = mapped_column(String(80))
    ward_date_of_birth: Mapped[date | None] = mapped_column(Date)
    ward_gender: Mapped[str | None] = mapped_column(String(20))
    ward_passport_url: Mapped[str | None] = mapped_column(String(512))

    form_responses: Mapped[dict | None] = mapped_column(JSON)
    document_urls: Mapped[dict | None] = mapped_column(JSON)

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.draft
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id")
    )
    review_notes: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    admission_form = relationship("AdmissionForm", back_populates="applications")
    parent = relationship("Person", foreign_keys=[parent_id])
    invoice = relationship("Invoice")
    reviewer = relationship("Person", foreign_keys=[reviewed_by])


# ── Rating ───────────────────────────────────────────────


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("school_id", "parent_id", name="uq_ratings_school_parent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    school = relationship("School", back_populates="ratings")
    parent = relationship("Person")
