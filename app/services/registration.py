"""Registration service — parent and school admin onboarding."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import AuthProvider, UserCredential
from app.models.person import Person
from app.models.rbac import PersonRole, Role
from app.schemas.school import SchoolCreate
from app.services.auth_flow import hash_password
from app.services.school import SchoolService

logger = logging.getLogger(__name__)


class RegistrationService:
    """Handles user registration and role assignment."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def email_exists(self, email: str) -> bool:
        stmt = select(Person.id).where(Person.email == email)
        return self.db.scalar(stmt) is not None

    def _create_person(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone: str | None,
    ) -> Person:
        person = Person(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            email_verified=False,
        )
        self.db.add(person)
        self.db.flush()
        return person

    def _create_credential(self, person_id: UUID, password: str) -> UserCredential:
        cred = UserCredential(
            person_id=person_id,
            provider=AuthProvider.local,
            password_hash=hash_password(password),
        )
        self.db.add(cred)
        self.db.flush()
        return cred

    def _assign_role(self, person_id: UUID, role_name: str) -> None:
        stmt = select(Role).where(Role.name == role_name, Role.is_active.is_(True))
        role = self.db.scalar(stmt)
        if role:
            self.db.add(PersonRole(person_id=person_id, role_id=role.id))
            self.db.flush()

    def register_parent(
        self,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        phone: str | None = None,
    ) -> Person:
        if self.email_exists(email):
            raise ValueError("An account with this email already exists")

        person = self._create_person(first_name, last_name, email, phone)
        self._create_credential(person.id, password)
        self._assign_role(person.id, "parent")

        logger.info("Registered parent: %s", person.id)
        return person

    def register_school_admin(
        self,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        school_name: str,
        school_type: str,
        category: str,
        phone: str | None = None,
        state: str | None = None,
        city: str | None = None,
        address: str | None = None,
    ) -> tuple[Person, object]:
        if self.email_exists(email):
            raise ValueError("An account with this email already exists")

        person = self._create_person(first_name, last_name, email, phone)
        self._create_credential(person.id, password)
        self._assign_role(person.id, "school_admin")

        payload = SchoolCreate(
            name=school_name,
            school_type=school_type,
            category=category,
            state=state,
            city=city,
            address=address,
        )
        school_svc = SchoolService(self.db)
        school = school_svc.create(payload, owner_id=person.id)

        logger.info(
            "Registered school admin: %s with school: %s", person.id, school_name
        )
        return person, school

    def get_person_role_names(self, person_id: UUID) -> set[str]:
        stmt = (
            select(Role.name)
            .join(PersonRole, PersonRole.role_id == Role.id)
            .where(PersonRole.person_id == person_id)
        )
        return set(self.db.scalars(stmt).all())
