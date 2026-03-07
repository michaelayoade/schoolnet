"""Seed demo data for SchoolNet development and testing.

Creates sample schools, admission forms, parents, wards, and applications.
Run after seed_schoolnet.py (RBAC) and seed_admin.py (admin user).

Usage:
    python -m scripts.seed_demo_data
"""
# ruff: noqa: S311

from __future__ import annotations

import logging
import random
import secrets
from datetime import UTC, date, datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.auth import AuthProvider, UserCredential
from app.models.person import Person
from app.models.rbac import PersonRole, Role
from app.models.school import (
    AdmissionForm,
    AdmissionFormStatus,
    Application,
    ApplicationStatus,
    School,
    SchoolCategory,
    SchoolGender,
    SchoolStatus,
    SchoolType,
)
from app.models.ward import Ward
from app.services.auth_flow import hash_password

logger = logging.getLogger(__name__)

DEFAULT_PASSWORD = "Demo1234"  # noqa: S105

NIGERIAN_STATES = [
    "Lagos",
    "Abuja",
    "Rivers",
    "Oyo",
    "Kano",
    "Kaduna",
    "Ogun",
    "Enugu",
    "Delta",
    "Edo",
]

SCHOOL_DATA = [
    {
        "name": "Greenfield Academy",
        "school_type": SchoolType.primary_secondary,
        "category": SchoolCategory.private,
        "gender": SchoolGender.mixed,
        "description": "A leading private institution offering world-class education "
        "from primary through secondary school.",
        "city": "Lekki",
        "state": "Lagos",
        "address": "42 Admiralty Way, Lekki Phase 1",
        "fee_range_min": 50000000,
        "fee_range_max": 120000000,
        "is_featured": True,
    },
    {
        "name": "Royal Crown College",
        "school_type": SchoolType.secondary,
        "category": SchoolCategory.private,
        "gender": SchoolGender.mixed,
        "description": "Excellence in secondary education with a focus on STEM "
        "and leadership development.",
        "city": "Ikeja",
        "state": "Lagos",
        "address": "15 Allen Avenue, Ikeja",
        "fee_range_min": 30000000,
        "fee_range_max": 80000000,
        "is_featured": True,
    },
    {
        "name": "Sunrise Nursery & Primary School",
        "school_type": SchoolType.nursery_primary,
        "category": SchoolCategory.private,
        "gender": SchoolGender.mixed,
        "description": "Nurturing young minds in a warm and engaging learning "
        "environment from nursery through primary.",
        "city": "Abuja",
        "state": "Abuja",
        "address": "8 Wuse Zone 5",
        "fee_range_min": 20000000,
        "fee_range_max": 45000000,
        "is_featured": False,
    },
    {
        "name": "Kings College Lagos",
        "school_type": SchoolType.secondary,
        "category": SchoolCategory.federal,
        "gender": SchoolGender.boys_only,
        "description": "One of Nigeria's oldest and most prestigious federal "
        "government secondary schools for boys.",
        "city": "Lagos Island",
        "state": "Lagos",
        "address": "Catholic Mission Street, Lagos Island",
        "fee_range_min": 5000000,
        "fee_range_max": 10000000,
        "is_featured": True,
    },
    {
        "name": "St. Mary's Girls School",
        "school_type": SchoolType.primary_secondary,
        "category": SchoolCategory.missionary,
        "gender": SchoolGender.girls_only,
        "description": "A missionary school dedicated to empowering girls through "
        "quality education and moral development.",
        "city": "Enugu",
        "state": "Enugu",
        "address": "12 Bishop Shanahan Road",
        "fee_range_min": 15000000,
        "fee_range_max": 35000000,
        "is_featured": False,
    },
    {
        "name": "Bright Future International School",
        "school_type": SchoolType.primary_secondary,
        "category": SchoolCategory.private,
        "gender": SchoolGender.mixed,
        "description": "International curriculum school with British and Nigerian "
        "certifications available.",
        "city": "Port Harcourt",
        "state": "Rivers",
        "address": "45 Trans Amadi Industrial Layout",
        "fee_range_min": 80000000,
        "fee_range_max": 200000000,
        "is_featured": True,
    },
]

PARENT_DATA = [
    {"first_name": "Chioma", "last_name": "Okafor", "email": "chioma@demo.test"},
    {"first_name": "Emeka", "last_name": "Eze", "email": "emeka@demo.test"},
    {"first_name": "Fatima", "last_name": "Bello", "email": "fatima@demo.test"},
    {"first_name": "Oluwaseun", "last_name": "Adeyemi", "email": "seun@demo.test"},
    {"first_name": "Ngozi", "last_name": "Nwosu", "email": "ngozi@demo.test"},
    {"first_name": "Ibrahim", "last_name": "Musa", "email": "ibrahim@demo.test"},
    {"first_name": "Aisha", "last_name": "Yusuf", "email": "aisha@demo.test"},
    {"first_name": "Chukwudi", "last_name": "Obi", "email": "chukwudi@demo.test"},
]

SCHOOL_ADMIN_DATA = [
    {"first_name": "Adebayo", "last_name": "Johnson", "email": "adebayo@demo.test"},
    {"first_name": "Grace", "last_name": "Okwu", "email": "grace@demo.test"},
    {"first_name": "Mohammed", "last_name": "Aliyu", "email": "mohammed@demo.test"},
    {"first_name": "Blessing", "last_name": "Emenike", "email": "blessing@demo.test"},
    {"first_name": "David", "last_name": "Achebe", "email": "david.a@demo.test"},
    {"first_name": "Funke", "last_name": "Alade", "email": "funke@demo.test"},
]

WARD_FIRST_NAMES = [
    "Adaeze",
    "Chinedu",
    "Olumide",
    "Zainab",
    "Tunde",
    "Amara",
    "Obiora",
    "Halima",
    "Yemi",
    "Nneka",
    "Babatunde",
    "Ifunanya",
    "Jibril",
    "Chiamaka",
    "Seyi",
]


def _slug(name: str) -> str:
    import re

    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug.strip("-")


def _get_or_create_person(
    db: Session, *, first_name: str, last_name: str, email: str
) -> Person:
    person: Person | None = db.scalar(select(Person).where(Person.email == email))
    if person:
        return person
    person = Person(
        first_name=first_name,
        last_name=last_name,
        email=email,
        email_verified=True,
        is_active=True,
    )
    db.add(person)
    db.flush()
    return person


def _ensure_credential(db: Session, person: Person) -> None:
    existing = db.scalar(
        select(UserCredential).where(
            UserCredential.person_id == person.id,
            UserCredential.provider == AuthProvider.local,
        )
    )
    if existing:
        return
    cred = UserCredential(
        person_id=person.id,
        provider=AuthProvider.local,
        username=person.email,
        password_hash=hash_password(DEFAULT_PASSWORD),
        must_change_password=False,
    )
    db.add(cred)
    db.flush()


def _assign_role(db: Session, person: Person, role_name: str) -> None:
    role = db.scalar(select(Role).where(Role.name == role_name))
    if not role:
        logger.warning("Role %s not found — run seed_schoolnet.py first", role_name)
        return
    existing = db.scalar(
        select(PersonRole).where(
            PersonRole.person_id == person.id,
            PersonRole.role_id == role.id,
        )
    )
    if existing:
        return
    db.add(PersonRole(person_id=person.id, role_id=role.id))
    db.flush()


def _create_school(db: Session, data: dict, owner: Person) -> School:
    existing: School | None = db.scalar(
        select(School).where(School.slug == _slug(data["name"]))
    )
    if existing:
        return existing
    school = School(
        owner_id=owner.id,
        name=data["name"],
        slug=_slug(data["name"]),
        school_type=data["school_type"],
        category=data["category"],
        gender=data.get("gender", SchoolGender.mixed),
        description=data.get("description"),
        address=data.get("address"),
        city=data.get("city"),
        state=data.get("state"),
        country_code="NG",
        fee_range_min=data.get("fee_range_min"),
        fee_range_max=data.get("fee_range_max"),
        is_featured=data.get("is_featured", False),
        status=SchoolStatus.active,
        verified_at=datetime.now(UTC),
        is_active=True,
    )
    db.add(school)
    db.flush()
    return school


def _create_admission_form(
    db: Session, school: School, *, title: str, academic_year: str
) -> AdmissionForm:
    existing: AdmissionForm | None = db.scalar(
        select(AdmissionForm).where(
            AdmissionForm.school_id == school.id,
            AdmissionForm.title == title,
            AdmissionForm.academic_year == academic_year,
        )
    )
    if existing:
        return existing

    form = AdmissionForm(
        school_id=school.id,
        title=title,
        description=f"Application form for {title} at {school.name}",
        academic_year=academic_year,
        status=AdmissionFormStatus.active,
        max_submissions=100,
        current_submissions=0,
        opens_at=datetime.now(UTC) - timedelta(days=30),
        closes_at=datetime.now(UTC) + timedelta(days=60),
        required_documents=[
            "Birth Certificate",
            "Previous Report Card",
            "Passport Photo",
        ],
        form_fields=[
            {
                "name": "previous_school",
                "label": "Previous School",
                "type": "text",
                "required": False,
            },
            {
                "name": "blood_group",
                "label": "Blood Group",
                "type": "select",
                "required": False,
                "options": ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"],
            },
            {
                "name": "medical_conditions",
                "label": "Medical Conditions",
                "type": "textarea",
                "required": False,
            },
        ],
        is_active=True,
    )
    db.add(form)
    db.flush()
    return form


def _create_ward(db: Session, parent: Person, first_name: str, last_name: str) -> Ward:
    existing: Ward | None = db.scalar(
        select(Ward).where(
            Ward.parent_id == parent.id,
            Ward.first_name == first_name,
            Ward.last_name == last_name,
        )
    )
    if existing:
        return existing

    ward = Ward(
        parent_id=parent.id,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date(
            random.randint(2012, 2019),
            random.randint(1, 12),
            random.randint(1, 28),
        ),
        gender=random.choice(["male", "female"]),
        is_active=True,
    )
    db.add(ward)
    db.flush()
    return ward


def _create_application(
    db: Session,
    form: AdmissionForm,
    parent: Person,
    ward: Ward,
    status: ApplicationStatus,
) -> Application:
    existing: Application | None = db.scalar(
        select(Application).where(
            Application.admission_form_id == form.id,
            Application.parent_id == parent.id,
            Application.ward_first_name == ward.first_name,
            Application.ward_last_name == ward.last_name,
        )
    )
    if existing:
        return existing

    now = datetime.now(UTC)
    year = now.strftime("%Y")
    suffix = secrets.token_hex(3).upper()
    app_number = f"SCH-{year}-{suffix}"

    app = Application(
        admission_form_id=form.id,
        parent_id=parent.id,
        application_number=app_number,
        ward_first_name=ward.first_name,
        ward_last_name=ward.last_name,
        ward_date_of_birth=ward.date_of_birth,
        ward_gender=ward.gender,
        form_responses={
            "previous_school": random.choice(
                ["None", "ABC Primary", "XYZ Nursery", ""]
            ),
            "blood_group": random.choice(["A+", "B+", "O+", "AB-"]),
            "medical_conditions": "",
        },
        status=status,
        is_active=True,
    )

    if status != ApplicationStatus.draft:
        app.submitted_at = now - timedelta(days=random.randint(1, 20))

    if status in (ApplicationStatus.accepted, ApplicationStatus.rejected):
        app.reviewed_at = now - timedelta(days=random.randint(0, 5))
        if status == ApplicationStatus.rejected:
            app.review_notes = random.choice(
                [
                    "Incomplete documents",
                    "Age requirement not met",
                    "Capacity reached for this class",
                ]
            )

    db.add(app)
    db.flush()
    return app


def main() -> None:
    load_dotenv()
    db = SessionLocal()
    try:
        print("Creating school admin users...")
        school_admins = []
        for data in SCHOOL_ADMIN_DATA:
            person = _get_or_create_person(db, **data)
            _ensure_credential(db, person)
            _assign_role(db, person, "school_admin")
            school_admins.append(person)

        print("Creating parent users...")
        parents = []
        for data in PARENT_DATA:
            person = _get_or_create_person(db, **data)
            _ensure_credential(db, person)
            _assign_role(db, person, "parent")
            parents.append(person)

        print("Creating schools...")
        schools = []
        for i, school_data in enumerate(SCHOOL_DATA):
            admin = school_admins[i % len(school_admins)]
            school = _create_school(db, school_data, admin)
            schools.append(school)
            print(f"  {school.name} (owner: {admin.email})")

        print("Creating admission forms...")
        forms = []
        for school in schools:
            form = _create_admission_form(
                db, school, title=f"{school.name} Admission", academic_year="2025/2026"
            )
            forms.append(form)

        print("Creating wards and applications...")
        statuses = [
            ApplicationStatus.submitted,
            ApplicationStatus.submitted,
            ApplicationStatus.under_review,
            ApplicationStatus.accepted,
            ApplicationStatus.rejected,
            ApplicationStatus.draft,
        ]
        app_count = 0
        for parent in parents:
            # Each parent has 1-2 wards
            num_wards = random.randint(1, 2)
            for _ in range(num_wards):
                first_name = random.choice(WARD_FIRST_NAMES)
                ward = _create_ward(db, parent, first_name, parent.last_name)

                # Apply to 1-2 schools
                target_forms = random.sample(
                    forms, min(random.randint(1, 2), len(forms))
                )
                for form in target_forms:
                    status = random.choice(statuses)
                    _create_application(db, form, parent, ward, status)
                    app_count += 1

        db.commit()
        print("\nSeed complete:")
        print(f"  {len(school_admins)} school admins")
        print(f"  {len(parents)} parents")
        print(f"  {len(schools)} schools")
        print(f"  {len(forms)} admission forms")
        print(f"  {app_count} applications")
        print(f"\nAll demo users have password: {DEFAULT_PASSWORD}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
