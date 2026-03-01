"""Tests for RegistrationService — parent and school admin registration."""

import pytest

from app.models.auth import UserCredential
from app.models.rbac import Role
from app.services.registration import RegistrationService, _validate_password_strength
from tests.conftest import _unique_email


@pytest.fixture()
def parent_role(db_session):
    """Ensure a parent role exists."""
    from sqlalchemy import select

    stmt = select(Role).where(Role.name == "parent")
    existing = db_session.scalar(stmt)
    if existing:
        return existing
    role = Role(name="parent", description="Parent role")
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


@pytest.fixture()
def school_admin_role(db_session):
    """Ensure a school_admin role exists."""
    from sqlalchemy import select

    stmt = select(Role).where(Role.name == "school_admin")
    existing = db_session.scalar(stmt)
    if existing:
        return existing
    role = Role(name="school_admin", description="School admin role")
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


class TestRegisterParent:
    def test_register_parent(self, db_session, parent_role):
        svc = RegistrationService(db_session)
        email = _unique_email()
        person = svc.register_parent(
            first_name="Jane",
            last_name="Doe",
            email=email,
            password="securepassword123",
            phone="+2348012345678",
        )
        db_session.commit()

        assert person.id is not None
        assert person.first_name == "Jane"
        assert person.email == email

    def test_register_parent_creates_credential(self, db_session, parent_role):
        svc = RegistrationService(db_session)
        person = svc.register_parent(
            first_name="Jane",
            last_name="Doe",
            email=_unique_email(),
            password="securepassword123",
        )
        db_session.commit()

        from sqlalchemy import select

        stmt = select(UserCredential).where(UserCredential.person_id == person.id)
        cred = db_session.scalar(stmt)
        assert cred is not None
        assert cred.password_hash is not None

    def test_register_parent_assigns_role(self, db_session, parent_role):
        svc = RegistrationService(db_session)
        person = svc.register_parent(
            first_name="Jane",
            last_name="Doe",
            email=_unique_email(),
            password="securepassword123",
        )
        db_session.commit()

        roles = svc.get_person_role_names(person.id)
        assert "parent" in roles

    def test_register_parent_duplicate_email(self, db_session, parent_role):
        svc = RegistrationService(db_session)
        email = _unique_email()
        svc.register_parent(
            first_name="Jane",
            last_name="Doe",
            email=email,
            password="password123",
        )
        db_session.commit()

        with pytest.raises(ValueError, match="already exists"):
            svc.register_parent(
                first_name="John",
                last_name="Doe",
                email=email,
                password="password456",
            )

    def test_register_parent_short_password_raises(self, db_session, parent_role):
        svc = RegistrationService(db_session)
        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            svc.register_parent(
                first_name="Jane",
                last_name="Doe",
                email=_unique_email(),
                password="short",
            )


class TestRegisterSchoolAdmin:
    def test_register_school_admin(self, db_session, school_admin_role):
        svc = RegistrationService(db_session)
        person, school = svc.register_school_admin(
            first_name="Admin",
            last_name="User",
            email=_unique_email(),
            password="securepassword123",
            school_name="Excel Academy",
            school_type="primary",
            category="private",
            state="Lagos",
            city="Ikeja",
        )
        db_session.commit()

        assert person.id is not None
        assert school is not None
        assert school.name == "Excel Academy"  # type: ignore[attr-defined]
        assert school.owner_id == person.id  # type: ignore[attr-defined]

    def test_register_school_admin_assigns_role(self, db_session, school_admin_role):
        svc = RegistrationService(db_session)
        person, _ = svc.register_school_admin(
            first_name="Admin",
            last_name="User",
            email=_unique_email(),
            password="securepassword123",
            school_name="Future Stars Academy",
            school_type="secondary",
            category="public",
        )
        db_session.commit()

        roles = svc.get_person_role_names(person.id)
        assert "school_admin" in roles

    def test_register_school_admin_duplicate_email(self, db_session, school_admin_role):
        svc = RegistrationService(db_session)
        email = _unique_email()
        svc.register_school_admin(
            first_name="Admin",
            last_name="One",
            email=email,
            password="password123",
            school_name="School One",
            school_type="primary",
            category="private",
        )
        db_session.commit()

        with pytest.raises(ValueError, match="already exists"):
            svc.register_school_admin(
                first_name="Admin",
                last_name="Two",
                email=email,
                password="password456",
                school_name="School Two",
                school_type="primary",
                category="private",
            )

    def test_register_school_admin_short_password_raises(
        self, db_session, school_admin_role
    ):
        svc = RegistrationService(db_session)
        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            svc.register_school_admin(
                first_name="Admin",
                last_name="User",
                email=_unique_email(),
                password="short",
                school_name="Excel Academy",
                school_type="primary",
                category="private",
            )


class TestGetPersonRoleNames:
    def test_get_roles(self, db_session, parent_role):
        svc = RegistrationService(db_session)
        person = svc.register_parent(
            first_name="Test",
            last_name="User",
            email=_unique_email(),
            password="password123",
        )
        db_session.commit()

        roles = svc.get_person_role_names(person.id)
        assert isinstance(roles, set)
        assert "parent" in roles

    def test_get_roles_empty(self, db_session, person):
        svc = RegistrationService(db_session)
        roles = svc.get_person_role_names(person.id)
        assert isinstance(roles, set)


class TestEmailExists:
    def test_email_exists_true(self, db_session, person):
        svc = RegistrationService(db_session)
        assert svc.email_exists(person.email) is True

    def test_email_exists_false(self, db_session):
        svc = RegistrationService(db_session)
        assert svc.email_exists("nonexistent@example.com") is False


class TestPasswordValidation:
    def test_validate_password_strength_accepts_eight_chars(self):
        _validate_password_strength("password")

    def test_validate_password_strength_rejects_short_password(self):
        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            _validate_password_strength("short")
