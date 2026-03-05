"""Tests for rating submission UI."""

import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import _create_access_token


def _get_csrf(client):
    resp = client.get("/login")
    return resp.cookies.get("csrf_token", "")


def _setup_rating_scenario(db_session):
    """Create parent + school + application so parent can rate."""
    from app.models.person import Person
    from app.models.auth import Session as AuthSession, SessionStatus
    from app.models.rbac import Role, PersonRole
    from app.models.school import (
        School,
        SchoolType,
        SchoolCategory,
        SchoolGender,
        SchoolStatus,
        AdmissionForm,
        AdmissionFormStatus,
        Application,
        ApplicationStatus,
    )
    from app.models.billing import Product, Price, PriceType

    parent = Person(
        first_name="Rater",
        last_name="Parent",
        email=f"rater-{uuid.uuid4().hex[:8]}@example.com",
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
        token_hash="rater-hash-" + uuid.uuid4().hex[:8],
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
        last_name="Rate",
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(owner)
    db_session.flush()

    slug = f"rate-school-{uuid.uuid4().hex[:6]}"
    school = School(
        owner_id=owner.id,
        name="Rate Test School",
        slug=slug,
        school_type=SchoolType.primary,
        category=SchoolCategory.private,
        gender=SchoolGender.mixed,
        status=SchoolStatus.active,
    )
    db_session.add(school)
    db_session.flush()

    # Create an application so parent can_rate
    product = Product(name="Rate Form Product", is_active=True)
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
        title="Rate Test Form",
        academic_year="2025/2026",
        status=AdmissionFormStatus.active,
    )
    db_session.add(form)
    db_session.flush()

    application = Application(
        admission_form_id=form.id,
        parent_id=parent.id,
        application_number=f"RATE-{uuid.uuid4().hex[:6].upper()}",
        status=ApplicationStatus.submitted,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(school)

    return school, parent, token


class TestRatingSubmission:
    def test_school_profile_shows_rating_form(self, client, db_session):
        school, parent, token = _setup_rating_scenario(db_session)
        resp = client.get(
            f"/schools/{school.slug}",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert b"Leave a Review" in resp.content

    def test_submit_rating(self, client, db_session):
        school, parent, token = _setup_rating_scenario(db_session)
        csrf = _get_csrf(client)
        resp = client.post(
            f"/schools/{school.slug}/rate",
            data={"score": "4", "comment": "Great school!", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            cookies={"access_token": token, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "success" in resp.headers["location"]

    def test_submit_rating_unauthenticated(self, client, db_session):
        school, _, _ = _setup_rating_scenario(db_session)
        csrf = _get_csrf(client)
        resp = client.post(
            f"/schools/{school.slug}/rate",
            data={"score": "5", "comment": "", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            cookies={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/login" in resp.headers["location"]

    def test_submit_duplicate_rating(self, client, db_session):
        school, parent, token = _setup_rating_scenario(db_session)
        # First rating
        csrf1 = _get_csrf(client)
        resp1 = client.post(
            f"/schools/{school.slug}/rate",
            data={"score": "4", "comment": "First", "csrf_token": csrf1},
            headers={"X-CSRF-Token": csrf1},
            cookies={"access_token": token, "csrf_token": csrf1},
            follow_redirects=False,
        )
        assert resp1.status_code == 303

        # Second rating should fail — use same csrf approach
        resp = client.post(
            f"/schools/{school.slug}/rate",
            data={"score": "5", "comment": "Second", "csrf_token": csrf1},
            headers={"X-CSRF-Token": csrf1},
            cookies={"access_token": token, "csrf_token": csrf1},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "error" in resp.headers["location"]
