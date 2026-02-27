from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── School ───────────────────────────────────────────────


class SchoolBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1, max_length=255)
    school_type: str
    category: str
    gender: str = "mixed"
    description: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    lga: str | None = None
    country_code: str = "NG"
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    fee_range_min: int | None = None
    fee_range_max: int | None = None
    year_established: int | None = None
    student_capacity: int | None = None


class SchoolCreate(SchoolBase):
    # Bank details for Paystack subaccount (optional at creation)
    bank_code: str | None = None
    account_number: str | None = None
    account_name: str | None = None


class SchoolUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    lga: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    fee_range_min: int | None = None
    fee_range_max: int | None = None
    logo_url: str | None = None
    cover_image_url: str | None = None
    year_established: int | None = None
    student_capacity: int | None = None
    bank_code: str | None = None
    account_number: str | None = None
    account_name: str | None = None


class SchoolRead(SchoolBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: UUID
    slug: str
    owner_id: UUID
    logo_url: str | None = None
    cover_image_url: str | None = None
    status: str
    verified_at: datetime | None = None
    paystack_subaccount_code: str | None = None
    bank_code: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
    account_name: str | None = None
    commission_rate: int | None = None
    settlement_bank_verified: bool = False
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class SchoolSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str
    school_type: str
    category: str
    city: str | None = None
    state: str | None = None
    logo_url: str | None = None
    fee_range_min: int | None = None
    fee_range_max: int | None = None
    average_rating: float | None = None


# ── Admission Form ───────────────────────────────────────


class AdmissionFormBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    academic_year: str = Field(min_length=4, max_length=20)
    max_submissions: int | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    required_documents: list[str] | None = None
    form_fields: list[dict] | None = None


class AdmissionFormCreate(AdmissionFormBase):
    school_id: UUID
    price_amount: int = Field(gt=0, description="Price in kobo")


class AdmissionFormUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    max_submissions: int | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    required_documents: list[str] | None = None
    form_fields: list[dict] | None = None
    price_amount: int | None = Field(default=None, gt=0)


class AdmissionFormRead(AdmissionFormBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: UUID
    school_id: UUID
    product_id: UUID | None = None
    price_id: UUID | None = None
    status: str
    current_submissions: int = 0
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    # Populated from Price
    price_amount: int | None = None
    school_name: str | None = None


# ── Application ──────────────────────────────────────────


class ApplicationBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ward_first_name: str | None = Field(default=None, max_length=80)
    ward_last_name: str | None = Field(default=None, max_length=80)
    ward_date_of_birth: date | None = None
    ward_gender: str | None = None
    form_responses: dict | None = None
    document_urls: list[str] | None = None


class ApplicationCreate(BaseModel):
    admission_form_id: UUID


class ApplicationSubmit(ApplicationBase):
    """Used when parent fills and submits the application."""
    ward_first_name: str = Field(min_length=1, max_length=80)
    ward_last_name: str = Field(min_length=1, max_length=80)
    ward_date_of_birth: date
    ward_gender: str


class ApplicationReview(BaseModel):
    decision: str = Field(pattern="^(accepted|rejected)$")
    review_notes: str | None = None


class ApplicationRead(ApplicationBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: UUID
    admission_form_id: UUID
    parent_id: UUID
    invoice_id: UUID | None = None
    application_number: str
    ward_passport_url: str | None = None
    status: str
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None
    review_notes: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    # Populated in service
    school_name: str | None = None
    form_title: str | None = None


class ApplicationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    application_number: str
    ward_first_name: str | None = None
    ward_last_name: str | None = None
    status: str
    submitted_at: datetime | None = None
    created_at: datetime


# ── Rating ───────────────────────────────────────────────


class RatingBase(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = None


class RatingCreate(RatingBase):
    school_id: UUID


class RatingRead(RatingBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    school_id: UUID
    parent_id: UUID
    created_at: datetime


# ── Dashboard Stats ──────────────────────────────────────


class SchoolDashboardStats(BaseModel):
    total_forms: int = 0
    active_forms: int = 0
    total_applications: int = 0
    pending_applications: int = 0
    accepted_applications: int = 0
    rejected_applications: int = 0
    total_revenue: int = 0
    average_rating: float | None = None


class PurchaseInitiate(BaseModel):
    admission_form_id: UUID
    callback_url: str | None = None


class PurchaseResponse(BaseModel):
    checkout_url: str
    reference: str
    application_id: UUID
