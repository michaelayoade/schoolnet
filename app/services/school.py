"""School service — all school-related business logic."""

import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.config import settings
from app.models.billing import Invoice, InvoiceStatus
from app.models.school import (
    AdmissionForm,
    AdmissionFormStatus,
    Application,
    ApplicationStatus,
    Rating,
    School,
    SchoolStatus,
)
from app.schemas.school import SchoolCreate, SchoolDashboardStats, SchoolUpdate
from app.services.common import escape_like
from app.services.file_upload import FileUploadService
from app.services.payment_gateway import paystack_gateway

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug = base
    counter = 1
    while db.scalar(select(School.id).where(School.slug == slug)):
        slug = f"{base}-{counter}"
        counter += 1
    return slug


class SchoolService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: SchoolCreate, owner_id: UUID) -> School:
        slug = _unique_slug(self.db, payload.name)
        school = School(
            owner_id=owner_id,
            name=payload.name,
            slug=slug,
            school_type=payload.school_type,
            category=payload.category,
            gender=payload.gender,
            description=payload.description,
            address=payload.address,
            city=payload.city,
            state=payload.state,
            lga=payload.lga,
            country_code=payload.country_code,
            phone=payload.phone,
            email=payload.email,
            website=payload.website,
            fee_range_min=payload.fee_range_min,
            fee_range_max=payload.fee_range_max,
            year_established=payload.year_established,
            student_capacity=payload.student_capacity,
            commission_rate=settings.schoolnet_commission_rate,
            status=SchoolStatus.pending,
        )

        # Store bank details if provided
        if payload.bank_code and payload.account_number:
            school.bank_code = payload.bank_code
            school.account_number = payload.account_number
            school.account_name = payload.account_name

            # Create Paystack subaccount if gateway is configured
            if paystack_gateway.is_configured():
                try:
                    commission_pct = settings.schoolnet_commission_rate / 100
                    result = paystack_gateway.create_subaccount(
                        business_name=payload.name,
                        bank_code=payload.bank_code,
                        account_number=payload.account_number,
                        percentage_charge=commission_pct,
                    )
                    school.paystack_subaccount_code = result["subaccount_code"]
                    school.bank_name = result.get("settlement_bank")
                    school.settlement_bank_verified = True
                except (ValueError, RuntimeError) as e:
                    logger.warning("Paystack subaccount creation failed: %s", e)

        self.db.add(school)
        self.db.flush()
        logger.info("Created school: %s (slug=%s)", school.id, school.slug)
        return school

    def get_by_id(self, school_id: UUID) -> School | None:
        school: School | None = self.db.get(School, school_id)
        return school

    def get_by_slug(self, slug: str) -> School | None:
        stmt = select(School).where(School.slug == slug, School.is_active.is_(True))
        school: School | None = self.db.scalar(stmt)
        return school

    def get_schools_for_owner(self, owner_id: UUID) -> list[School]:
        stmt = (
            select(School)
            .where(School.owner_id == owner_id, School.is_active.is_(True))
            .order_by(School.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_school_for_owner(self, owner_id: UUID) -> School | None:
        """Get the first school owned by this person."""
        stmt = (
            select(School)
            .where(School.owner_id == owner_id, School.is_active.is_(True))
            .order_by(School.created_at.asc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def upload_verification_document(
        self,
        school: School,
        document: UploadFile,
        uploaded_by: UUID,
    ) -> dict[str, str | None]:
        """Upload a verification document and append it to school metadata."""
        filename = document.filename or "document"
        content = document.file.read()
        record = FileUploadService(self.db).upload(
            content=content,
            filename=filename,
            content_type=document.content_type or "application/octet-stream",
            uploaded_by=uploaded_by,
            category="verification",
            entity_type="school",
            entity_id=str(school.id),
        )
        meta = dict(school.metadata_ or {})
        docs = list(meta.get("verification_documents", []))
        docs.append(
            {
                "file_id": str(record.id),
                "filename": document.filename,
                "url": record.url,
            }
        )
        meta["verification_documents"] = docs
        school.metadata_ = meta
        self.db.flush()
        return {
            "file_id": str(record.id),
            "filename": document.filename,
            "url": record.url,
        }

    def list_admission_forms(self, school_id: UUID) -> list[AdmissionForm]:
        """List all active admission forms for a school."""
        stmt = (
            select(AdmissionForm)
            .where(AdmissionForm.school_id == school_id, AdmissionForm.is_active.is_(True))
            .order_by(AdmissionForm.title)
        )
        return list(self.db.scalars(stmt).all())

    def search(
        self,
        *,
        query: str | None = None,
        state: str | None = None,
        city: str | None = None,
        school_type: str | None = None,
        category: str | None = None,
        gender: str | None = None,
        fee_min: int | None = None,
        fee_max: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[School], int]:
        stmt = select(School).where(
            School.status == SchoolStatus.active,
            School.is_active.is_(True),
        )
        if query:
            stmt = stmt.where(School.name.ilike(f"%{escape_like(query)}%"))
        if state:
            stmt = stmt.where(School.state.ilike(f"%{escape_like(state)}%"))
        if city:
            stmt = stmt.where(School.city.ilike(f"%{escape_like(city)}%"))
        if school_type:
            stmt = stmt.where(School.school_type == school_type)
        if category:
            stmt = stmt.where(School.category == category)
        if gender:
            stmt = stmt.where(School.gender == gender)
        if fee_min is not None:
            stmt = stmt.where(School.fee_range_min >= fee_min)
        if fee_max is not None:
            stmt = stmt.where(School.fee_range_max <= fee_max)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = stmt.order_by(School.is_featured.desc(), School.name).limit(limit).offset(offset)
        schools = list(self.db.scalars(stmt).all())
        return schools, total

    def get_featured(self, limit: int = 6) -> list[School]:
        """Get featured schools, falling back to recently verified active schools."""
        stmt = select(School).where(
            School.status == SchoolStatus.active,
            School.is_active.is_(True),
            School.is_featured.is_(True),
        ).order_by(School.name).limit(limit)
        featured = list(self.db.scalars(stmt).all())
        if len(featured) < limit:
            # Fill with non-featured active schools
            existing_ids = [s.id for s in featured]
            fill_stmt = select(School).where(
                School.status == SchoolStatus.active,
                School.is_active.is_(True),
            )
            if existing_ids:
                fill_stmt = fill_stmt.where(School.id.notin_(existing_ids))
            fill_stmt = fill_stmt.order_by(
                School.verified_at.desc().nulls_last()
            ).limit(limit - len(featured))
            featured.extend(list(self.db.scalars(fill_stmt).all()))
        return featured

    def update(self, school: School, payload: SchoolUpdate) -> School:
        update_data = payload.model_dump(exclude_unset=True)

        # Handle bank details update
        bank_changed = False
        for field in ("bank_code", "account_number", "account_name"):
            if field in update_data and update_data[field] is not None:
                bank_changed = True

        for key, value in update_data.items():
            setattr(school, key, value)

        if bank_changed and school.bank_code and school.account_number:
            if paystack_gateway.is_configured():
                try:
                    if school.paystack_subaccount_code:
                        paystack_gateway.update_subaccount(
                            school.paystack_subaccount_code,
                            bank_code=school.bank_code,
                            account_number=school.account_number,
                        )
                    else:
                        commission_pct = (
                            school.commission_rate or settings.schoolnet_commission_rate
                        ) / 100
                        result = paystack_gateway.create_subaccount(
                            business_name=school.name,
                            bank_code=school.bank_code,
                            account_number=school.account_number,
                            percentage_charge=commission_pct,
                        )
                        school.paystack_subaccount_code = result["subaccount_code"]
                        school.bank_name = result.get("settlement_bank")
                    school.settlement_bank_verified = True
                except (ValueError, RuntimeError) as e:
                    logger.warning("Paystack subaccount update failed: %s", e)

        self.db.flush()
        logger.info("Updated school: %s", school.id)
        return school

    def approve(self, school: School, approved_by: UUID) -> School:
        school.status = SchoolStatus.active
        school.verified_at = datetime.now(timezone.utc)
        school.verified_by = approved_by
        self.db.flush()
        logger.info("Approved school: %s by %s", school.id, approved_by)

        try:
            from app.services.notification import NotificationService

            NotificationService(self.db).notify_school_approved(
                school.owner_id,
                school.name,
            )
        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning("Failed to send approval notification: %s", e)

        return school

    def suspend(self, school: School) -> School:
        school.status = SchoolStatus.suspended
        self.db.flush()
        logger.info("Suspended school: %s", school.id)

        try:
            from app.services.notification import NotificationService

            NotificationService(self.db).notify_school_suspended(
                school.owner_id,
                school.name,
            )
        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning("Failed to send suspension notification: %s", e)

        return school

    def get_average_rating(self, school_id: UUID) -> float | None:
        stmt = select(func.avg(Rating.score)).where(
            Rating.school_id == school_id,
            Rating.is_active.is_(True),
        )
        result = self.db.scalar(stmt)
        return round(float(result), 1) if result else None

    def get_ratings(self, school_id: UUID, limit: int = 20) -> list[Rating]:
        stmt = (
            select(Rating)
            .where(Rating.school_id == school_id, Rating.is_active.is_(True))
            .order_by(Rating.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_dashboard_stats(self, school_id: UUID) -> SchoolDashboardStats:
        # Forms
        total_forms = (
            self.db.scalar(
                select(func.count())
                .select_from(AdmissionForm)
                .where(
                    AdmissionForm.school_id == school_id,
                    AdmissionForm.is_active.is_(True),
                )
            )
            or 0
        )
        active_forms = (
            self.db.scalar(
                select(func.count())
                .select_from(AdmissionForm)
                .where(
                    AdmissionForm.school_id == school_id,
                    AdmissionForm.status == AdmissionFormStatus.active,
                    AdmissionForm.is_active.is_(True),
                )
            )
            or 0
        )

        # Applications (via admission forms for this school)
        form_ids_stmt = select(AdmissionForm.id).where(
            AdmissionForm.school_id == school_id
        )
        total_apps = (
            self.db.scalar(
                select(func.count())
                .select_from(Application)
                .where(
                    Application.admission_form_id.in_(form_ids_stmt),
                    Application.is_active.is_(True),
                )
            )
            or 0
        )
        pending_apps = (
            self.db.scalar(
                select(func.count())
                .select_from(Application)
                .where(
                    Application.admission_form_id.in_(form_ids_stmt),
                    Application.status.in_(
                        [
                            ApplicationStatus.submitted,
                            ApplicationStatus.under_review,
                        ]
                    ),
                    Application.is_active.is_(True),
                )
            )
            or 0
        )
        accepted_apps = (
            self.db.scalar(
                select(func.count())
                .select_from(Application)
                .where(
                    Application.admission_form_id.in_(form_ids_stmt),
                    Application.status == ApplicationStatus.accepted,
                    Application.is_active.is_(True),
                )
            )
            or 0
        )
        rejected_apps = (
            self.db.scalar(
                select(func.count())
                .select_from(Application)
                .where(
                    Application.admission_form_id.in_(form_ids_stmt),
                    Application.status == ApplicationStatus.rejected,
                    Application.is_active.is_(True),
                )
            )
            or 0
        )

        # Revenue — sum of paid invoices linked to this school's applications
        invoice_ids_stmt = (
            select(Application.invoice_id)
            .where(
                Application.admission_form_id.in_(form_ids_stmt),
                Application.invoice_id.isnot(None),
            )
        )
        total_revenue: int = (
            self.db.scalar(
                select(func.coalesce(func.sum(Invoice.amount_paid), 0)).where(
                    Invoice.id.in_(invoice_ids_stmt),
                    Invoice.status == InvoiceStatus.paid,
                )
            )
            or 0
        )

        avg_rating = self.get_average_rating(school_id)

        return SchoolDashboardStats(
            total_forms=total_forms,
            active_forms=active_forms,
            total_applications=total_apps,
            pending_applications=pending_apps,
            accepted_applications=accepted_apps,
            rejected_applications=rejected_apps,
            total_revenue=total_revenue,
            average_rating=avg_rating,
        )

    def list_payments(
        self,
        school_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """List paid invoices for a school's applications."""
        import math

        form_ids_stmt = select(AdmissionForm.id).where(
            AdmissionForm.school_id == school_id
        )
        invoice_ids_stmt = select(Application.invoice_id).where(
            Application.admission_form_id.in_(form_ids_stmt),
            Application.invoice_id.isnot(None),
        )
        stmt = select(Invoice).where(
            Invoice.id.in_(invoice_ids_stmt),
            Invoice.status == InvoiceStatus.paid,
        )

        total: int = (
            self.db.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
            or 0
        )

        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        stmt = stmt.order_by(Invoice.paid_at.desc()).limit(page_size).offset(offset)
        items = list(self.db.scalars(stmt).all())

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": math.ceil(total / page_size) if page_size else 0,
        }
