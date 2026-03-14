"""Tests for document upload in application fill."""

import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from tests.conftest import _create_access_token


def _get_csrf(client):
    resp = client.get("/login")
    return resp.cookies.get("csrf_token", "")


def _setup_application(db_session, required_documents=None):
    """Create parent + school + form + application for upload testing."""
    from app.models.auth import Session as AuthSession
    from app.models.auth import SessionStatus
    from app.models.billing import Price, PriceType, Product
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

    parent = Person(
        first_name="Upload",
        last_name="Test",
        email=f"upload-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(parent)
    db_session.flush()

    role = db_session.query(Role).filter(Role.name == "parent").first()
    if not role:
        role = Role(name="parent", description="Parent role")
        db_session.add(role)
        db_session.flush()
    db_session.add(PersonRole(person_id=parent.id, role_id=role.id))

    auth_sess = AuthSession(
        person_id=parent.id,
        token_hash="upload-hash-" + uuid.uuid4().hex[:8],
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(auth_sess)
    db_session.flush()

    token = _create_access_token(str(parent.id), str(auth_sess.id), roles=["parent"])

    owner = Person(
        first_name="Owner",
        last_name="Upload",
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(owner)
    db_session.flush()

    school = School(
        owner_id=owner.id,
        name="Upload Test School",
        slug=f"upload-{uuid.uuid4().hex[:6]}",
        school_type=SchoolType.primary,
        category=SchoolCategory.private,
        gender=SchoolGender.mixed,
        status=SchoolStatus.active,
    )
    db_session.add(school)
    db_session.flush()

    product = Product(name="Upload Form Product", is_active=True)
    db_session.add(product)
    db_session.flush()

    price = Price(
        product_id=product.id,
        currency="NGN",
        unit_amount=500000,
        type=PriceType.one_time,
        is_active=True,
    )
    db_session.add(price)
    db_session.flush()

    form = AdmissionForm(
        school_id=school.id,
        product_id=product.id,
        price_id=price.id,
        title="Upload Test Form",
        academic_year="2025/2026",
        status=AdmissionFormStatus.active,
        required_documents=required_documents,
    )
    db_session.add(form)
    db_session.flush()

    application = Application(
        admission_form_id=form.id,
        parent_id=parent.id,
        application_number=f"UPL-{uuid.uuid4().hex[:6].upper()}",
        status=ApplicationStatus.draft,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    return application, token, parent


class TestDocumentUpload:
    def test_fill_page_shows_document_inputs(self, client, db_session):
        required_docs = ["Birth Certificate", "Passport Photo"]
        app, token, _ = _setup_application(db_session, required_documents=required_docs)
        resp = client.get(
            f"/parent/applications/fill/{app.id}",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert b"Birth Certificate" in resp.content
        assert b"Passport Photo" in resp.content
        assert b"Required Documents" in resp.content

    @patch("app.services.application.FileUploadService")
    def test_submit_with_document_upload(self, mock_upload_cls, client, db_session):
        required_docs = ["Birth Certificate"]
        app_obj, token, parent = _setup_application(
            db_session, required_documents=required_docs
        )

        mock_record = MagicMock()
        mock_record.url = "/uploads/test-file.pdf"
        mock_instance = MagicMock()
        mock_instance.upload.return_value = mock_record
        mock_upload_cls.return_value = mock_instance

        csrf = _get_csrf(client)
        file_content = b"%PDF-1.4 fake pdf content"
        resp = client.post(
            f"/parent/applications/fill/{app_obj.id}",
            data={
                "ward_first_name": "Child",
                "ward_last_name": "Doc",
                "ward_date_of_birth": "2015-03-20",
                "ward_gender": "male",
                "csrf_token": csrf,
            },
            files={
                "doc_Birth Certificate": (
                    "birth_cert.pdf",
                    io.BytesIO(file_content),
                    "application/pdf",
                )
            },
            headers={"X-CSRF-Token": csrf},
            cookies={"access_token": token, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "success" in resp.headers["location"]
        mock_instance.upload.assert_called_once()

    def test_submit_without_documents_when_none_required(self, client, db_session):
        app_obj, token, _ = _setup_application(db_session)
        csrf = _get_csrf(client)
        resp = client.post(
            f"/parent/applications/fill/{app_obj.id}",
            data={
                "ward_first_name": "Child",
                "ward_last_name": "NoDoc",
                "ward_date_of_birth": "2015-01-10",
                "ward_gender": "female",
                "csrf_token": csrf,
            },
            headers={"X-CSRF-Token": csrf},
            cookies={"access_token": token, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "success" in resp.headers["location"]
