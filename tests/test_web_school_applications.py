"""Tests for school application web routes."""

import uuid

import pytest

from app.models.person import Person
from app.models.school import (
    Application,
    ApplicationStatus,
    School,
    SchoolCategory,
    SchoolGender,
    SchoolStatus,
    SchoolType,
)


@pytest.fixture()
def other_school_owner(db_session):
    owner = Person(
        first_name="Other",
        last_name="Owner",
        email=f"other-owner-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner


@pytest.fixture()
def other_school(db_session, other_school_owner):
    school = School(
        owner_id=other_school_owner.id,
        name="Other Academy",
        slug=f"other-academy-{uuid.uuid4().hex[:6]}",
        school_type=SchoolType.primary,
        category=SchoolCategory.private,
        gender=SchoolGender.mixed,
        state="Lagos",
        city="Ikeja",
        status=SchoolStatus.active,
    )
    db_session.add(school)
    db_session.commit()
    db_session.refresh(school)
    return school


@pytest.fixture()
def submitted_application(db_session, admission_form_with_price, parent_person):
    application = Application(
        admission_form_id=admission_form_with_price.id,
        parent_id=parent_person.id,
        application_number=f"SCH-TEST-{uuid.uuid4().hex[:8].upper()}",
        status=ApplicationStatus.submitted,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


@pytest.fixture()
def override_school_admin_auth(client, other_school_owner, other_school):
    from app.main import app
    from app.web.schoolnet_deps import require_school_admin_auth

    def _override():
        return {"person_id": str(other_school_owner.id), "roles": ["school_admin"]}

    app.dependency_overrides[require_school_admin_auth] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_school_admin_auth, None)


class TestSchoolApplicationOwnership:
    def test_detail_blocks_cross_school_access(
        self, client, submitted_application, override_school_admin_auth
    ):
        response = client.get(
            f"/school/applications/{submitted_application.id}",
            follow_redirects=False,
        )
        assert response.status_code == 403

    def test_review_blocks_cross_school_action(
        self, client, db_session, submitted_application, override_school_admin_auth
    ):
        csrf_token = "a" * 24
        response = client.post(
            f"/school/applications/{submitted_application.id}/review",
            data={"decision": "accepted", "review_notes": "Looks good"},
            headers={"X-CSRF-Token": csrf_token},
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 403

        db_session.refresh(submitted_application)
        assert submitted_application.status == ApplicationStatus.submitted
        assert submitted_application.reviewed_by is None
