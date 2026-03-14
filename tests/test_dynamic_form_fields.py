"""Tests for dynamic form fields in application fill."""

import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import _create_access_token


def _get_csrf(client):
    resp = client.get("/login")
    return resp.cookies.get("csrf_token", "")


def _setup_application(db_session, form_fields=None, required_documents=None):
    """Create parent person + role + session + school + form + application."""
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
        first_name="Parent",
        last_name="DynTest",
        email=f"dyntest-{uuid.uuid4().hex[:8]}@example.com",
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
        token_hash="dyntest-hash-" + uuid.uuid4().hex[:8],
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
        last_name="Dyn",
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(owner)
    db_session.flush()

    school = School(
        owner_id=owner.id,
        name="DynTest School",
        slug=f"dyntest-{uuid.uuid4().hex[:6]}",
        school_type=SchoolType.primary,
        category=SchoolCategory.private,
        gender=SchoolGender.mixed,
        status=SchoolStatus.active,
    )
    db_session.add(school)
    db_session.flush()

    product = Product(name="Test Form Product", is_active=True)
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
        title="Dynamic Test Form",
        academic_year="2025/2026",
        status=AdmissionFormStatus.active,
        form_fields=form_fields,
        required_documents=required_documents,
    )
    db_session.add(form)
    db_session.flush()

    application = Application(
        admission_form_id=form.id,
        parent_id=parent.id,
        application_number=f"DYN-{uuid.uuid4().hex[:6].upper()}",
        status=ApplicationStatus.draft,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    return application, token, parent


class TestDynamicFormFields:
    def test_fill_page_shows_dynamic_fields(self, client, db_session):
        form_fields = [
            {
                "name": "religion",
                "label": "Religion",
                "type": "select",
                "options": ["Christian", "Muslim", "Other"],
                "required": True,
            },
            {
                "name": "hobbies",
                "label": "Hobbies",
                "type": "textarea",
                "required": False,
            },
        ]
        app, token, _ = _setup_application(db_session, form_fields=form_fields)
        resp = client.get(
            f"/parent/applications/fill/{app.id}",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert b"Religion" in resp.content
        assert b"Hobbies" in resp.content
        assert b"Additional Information" in resp.content

    def test_submit_with_dynamic_fields(self, client, db_session):
        form_fields = [
            {
                "name": "religion",
                "label": "Religion",
                "type": "text",
                "required": False,
            },
        ]
        app, token, _ = _setup_application(db_session, form_fields=form_fields)
        csrf = _get_csrf(client)
        resp = client.post(
            f"/parent/applications/fill/{app.id}",
            data={
                "ward_first_name": "Child",
                "ward_last_name": "Name",
                "ward_date_of_birth": "2015-06-15",
                "ward_gender": "female",
                "field_religion": "Christianity",
                "csrf_token": csrf,
            },
            headers={"X-CSRF-Token": csrf},
            cookies={"access_token": token, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "success" in resp.headers["location"]

        # Verify form_responses saved
        db_session.refresh(app)
        assert app.form_responses is not None
        assert app.form_responses.get("religion") == "Christianity"

    def test_submit_without_dynamic_fields(self, client, db_session):
        """Form with no form_fields should still work."""
        app, token, _ = _setup_application(db_session)
        csrf = _get_csrf(client)
        resp = client.post(
            f"/parent/applications/fill/{app.id}",
            data={
                "ward_first_name": "Child",
                "ward_last_name": "Name",
                "ward_date_of_birth": "2015-06-15",
                "ward_gender": "male",
                "csrf_token": csrf,
            },
            headers={"X-CSRF-Token": csrf},
            cookies={"access_token": token, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "success" in resp.headers["location"]
