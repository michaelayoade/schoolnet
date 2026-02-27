"""Admission form service — form lifecycle management."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.billing import Price, PriceType, Product
from app.models.school import AdmissionForm, AdmissionFormStatus, School
from app.schemas.school import AdmissionFormCreate, AdmissionFormUpdate

logger = logging.getLogger(__name__)


class AdmissionFormService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def assert_school_owner(self, school_id: UUID, person_id: UUID) -> None:
        school = self.db.get(School, school_id)
        if not school:
            raise ValueError("School not found")
        if school.owner_id != person_id:
            raise PermissionError("Not your school")

    def create(self, payload: AdmissionFormCreate) -> AdmissionForm:
        school = self.db.get(School, payload.school_id)
        if not school:
            raise ValueError("School not found")

        # Create billing Product
        product = Product(
            name=f"{school.name} - {payload.title}",
            description=payload.description or f"Admission form for {payload.academic_year}",
            is_active=True,
            metadata_={"school_id": str(school.id), "type": "admission_form"},
        )
        self.db.add(product)
        self.db.flush()

        # Create billing Price
        price = Price(
            product_id=product.id,
            currency=settings.schoolnet_currency,
            unit_amount=payload.price_amount,
            type=PriceType.one_time,
            is_active=True,
        )
        self.db.add(price)
        self.db.flush()

        form = AdmissionForm(
            school_id=payload.school_id,
            product_id=product.id,
            price_id=price.id,
            title=payload.title,
            description=payload.description,
            academic_year=payload.academic_year,
            status=AdmissionFormStatus.draft,
            max_submissions=payload.max_submissions,
            opens_at=payload.opens_at,
            closes_at=payload.closes_at,
            required_documents=payload.required_documents,
            form_fields=payload.form_fields,
        )
        self.db.add(form)
        self.db.flush()
        logger.info("Created admission form: %s for school %s", form.id, school.id)
        return form

    def get_by_id(self, form_id: UUID) -> AdmissionForm | None:
        form: AdmissionForm | None = self.db.get(AdmissionForm, form_id)
        return form

    def list_for_school(self, school_id: UUID) -> list[AdmissionForm]:
        stmt = (
            select(AdmissionForm)
            .where(
                AdmissionForm.school_id == school_id,
                AdmissionForm.is_active.is_(True),
            )
            .order_by(AdmissionForm.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_active_for_school(self, school_id: UUID) -> list[AdmissionForm]:
        stmt = (
            select(AdmissionForm)
            .where(
                AdmissionForm.school_id == school_id,
                AdmissionForm.status == AdmissionFormStatus.active,
                AdmissionForm.is_active.is_(True),
            )
            .order_by(AdmissionForm.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_active(self, limit: int = 20, offset: int = 0) -> list[AdmissionForm]:
        stmt = (
            select(AdmissionForm)
            .where(
                AdmissionForm.status == AdmissionFormStatus.active,
                AdmissionForm.is_active.is_(True),
            )
            .order_by(AdmissionForm.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).all())

    def check_availability(self, form: AdmissionForm) -> bool:
        if form.status != AdmissionFormStatus.active:
            return False
        return not (form.max_submissions and form.current_submissions >= form.max_submissions)

    def update(self, form: AdmissionForm, payload: AdmissionFormUpdate) -> AdmissionForm:
        data = payload.model_dump(exclude_unset=True)

        # Update price if changed
        price_amount = data.pop("price_amount", None)
        if price_amount and form.price_id:
            price = self.db.get(Price, form.price_id)
            if price:
                price.unit_amount = price_amount
                price.is_active = True

        for key, value in data.items():
            if value is not None:
                setattr(form, key, value)

        self.db.flush()
        logger.info("Updated admission form: %s", form.id)
        return form

    def activate(self, form: AdmissionForm) -> AdmissionForm:
        form.status = AdmissionFormStatus.active
        self.db.flush()
        logger.info("Activated admission form: %s", form.id)
        return form

    def close(self, form: AdmissionForm) -> AdmissionForm:
        form.status = AdmissionFormStatus.closed
        self.db.flush()
        logger.info("Closed admission form: %s", form.id)
        return form

    def get_price_amount(self, form: AdmissionForm) -> int | None:
        if form.price_id:
            price: Price | None = self.db.get(Price, form.price_id)
            if price:
                amount: int | None = price.unit_amount
                return amount
        return None
