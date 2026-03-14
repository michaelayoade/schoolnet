"""Tests for school verification document workflow."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from tests.conftest import _create_access_token


def _get_csrf(client):
    resp = client.get("/login")
    return resp.cookies.get("csrf_token", "")


def _setup_school_admin(db_session):
    """Create school admin + school + auth session."""
    from app.models.auth import Session as AuthSession
    from app.models.auth import SessionStatus
    from app.models.person import Person
    from app.models.rbac import PersonRole, Role
    from app.models.school import (
        School,
        SchoolCategory,
        SchoolGender,
        SchoolStatus,
        SchoolType,
    )

    person = Person(
        first_name="School",
        last_name="Admin",
        email=f"veradmin-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(person)
    db_session.flush()

    role = db_session.query(Role).filter(Role.name == "school_admin").first()
    if not role:
        role = Role(name="school_admin", description="School admin role")
        db_session.add(role)
        db_session.flush()
    db_session.add(PersonRole(person_id=person.id, role_id=role.id))

    school = School(
        owner_id=person.id,
        name="Verification School",
        slug=f"verification-{uuid.uuid4().hex[:6]}",
        school_type=SchoolType.primary,
        category=SchoolCategory.private,
        gender=SchoolGender.mixed,
        status=SchoolStatus.pending,
    )
    db_session.add(school)
    db_session.flush()

    auth_sess = AuthSession(
        person_id=person.id,
        token_hash="veradmin-hash-" + uuid.uuid4().hex[:8],
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(auth_sess)
    db_session.commit()
    db_session.refresh(person)
    db_session.refresh(school)
    db_session.refresh(auth_sess)

    token = _create_access_token(
        str(person.id), str(auth_sess.id), roles=["school_admin"]
    )
    return person, school, token


class TestSchoolVerification:
    def test_verification_page_renders(self, client, db_session):
        _, school, token = _setup_school_admin(db_session)
        resp = client.get(
            "/school/verification",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert b"Verification" in resp.content

    def test_verification_page_shows_pending(self, client, db_session):
        _, school, token = _setup_school_admin(db_session)
        resp = client.get(
            "/school/verification",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert b"Pending Verification" in resp.content

    def test_verification_page_shows_verified(self, client, db_session):
        person, school, token = _setup_school_admin(db_session)
        school.verified_at = datetime.now(timezone.utc)
        db_session.commit()
        resp = client.get(
            "/school/verification",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert b"Verified" in resp.content

    @patch("app.services.school.FileUploadService")
    def test_upload_verification_document(self, mock_cls, client, db_session):
        _, school, token = _setup_school_admin(db_session)

        mock_record = MagicMock()
        mock_record.id = uuid.uuid4()
        mock_record.url = "/uploads/test-doc.pdf"
        mock_instance = MagicMock()
        mock_instance.upload.return_value = mock_record
        mock_cls.return_value = mock_instance

        csrf = _get_csrf(client)
        import io

        resp = client.post(
            "/school/verification/upload",
            files={
                "document": (
                    "cac_cert.pdf",
                    io.BytesIO(b"%PDF-fake"),
                    "application/pdf",
                )
            },
            data={"csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            cookies={"access_token": token, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "success" in resp.headers["location"]
        mock_instance.upload.assert_called_once()

    def test_verification_unauthenticated(self, client):
        resp = client.get("/school/verification", follow_redirects=False)
        assert resp.status_code == 302
