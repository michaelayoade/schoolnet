"""Integration tests for school admin application web routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from jose import jwt

from app.models.auth import Session as AuthSession, SessionStatus
from app.models.school import Application, ApplicationStatus


def _create_access_token(person_id: str, session_id: str, roles: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": person_id,
        "session_id": session_id,
        "roles": roles,
        "scopes": [],
        "typ": "access",
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iat": int(now.timestamp()),
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


@pytest.fixture()
def school_admin_auth_cookie(db_session, school_owner):
    session = AuthSession(
        person_id=school_owner.id,
        token_hash="school-admin-token-hash",
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    token = _create_access_token(
        str(school_owner.id),
        str(session.id),
        roles=["school_admin"],
    )
    return {"access_token": token}


@pytest.fixture(autouse=True)
def _mock_external_services():
    with (
        patch("app.services.application.paystack_gateway.is_configured", return_value=False),
        patch("app.services.application.paystack_gateway.initialize_transaction"),
        patch("app.services.email.send_email", return_value=True),
    ):
        yield


@pytest.fixture()
def submitted_application(db_session, parent_person, admission_form_with_price):
    app = Application(
        admission_form_id=admission_form_with_price.id,
        parent_id=parent_person.id,
        application_number="APP-SCHOOL-001",
        ward_first_name="Ada",
        ward_last_name="Lovelace",
        ward_gender="female",
        status=ApplicationStatus.submitted,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


class TestWebSchoolApplications:
    def test_list_applications(self, client, school_admin_auth_cookie, submitted_application):
        response = client.get(
            "/school/applications",
            cookies=school_admin_auth_cookie,
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert b"Applications" in response.content
        assert submitted_application.application_number.encode() in response.content

    def test_view_application_detail(self, client, school_admin_auth_cookie, submitted_application):
        response = client.get(
            f"/school/applications/{submitted_application.id}",
            cookies=school_admin_auth_cookie,
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert submitted_application.application_number.encode() in response.content
        assert b"Review Application" in response.content

    def test_review_approve_flow(
        self,
        client,
        db_session,
        school_owner,
        school_admin_auth_cookie,
        submitted_application,
    ):
        detail_response = client.get(
            f"/school/applications/{submitted_application.id}",
            cookies=school_admin_auth_cookie,
            follow_redirects=False,
        )
        csrf_token = detail_response.cookies.get("csrf_token", "")

        response = client.post(
            f"/school/applications/{submitted_application.id}/review",
            data={
                "decision": "accepted",
                "review_notes": "Strong profile",
                "csrf_token": csrf_token,
            },
            headers={"X-CSRF-Token": csrf_token},
            cookies={**school_admin_auth_cookie, "csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith(
            f"/school/applications/{submitted_application.id}?success=Application+accepted"
        )

        db_session.refresh(submitted_application)
        assert submitted_application.status == ApplicationStatus.accepted
        assert submitted_application.reviewed_by == school_owner.id
        assert submitted_application.review_notes == "Strong profile"
