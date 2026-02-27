"""Integration tests for parent application web routes."""

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
def parent_auth_cookie(db_session, parent_person):
    session = AuthSession(
        person_id=parent_person.id,
        token_hash="parent-token-hash",
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    token = _create_access_token(str(parent_person.id), str(session.id), roles=["parent"])
    return {"access_token": token}


@pytest.fixture()
def other_parent_auth_cookie(db_session, person):
    session = AuthSession(
        person_id=person.id,
        token_hash="other-parent-token-hash",
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    token = _create_access_token(str(person.id), str(session.id), roles=["parent"])
    return {"access_token": token}


@pytest.fixture(autouse=True)
def _mock_external_services():
    with (
        patch("app.services.application.paystack_gateway.is_configured", return_value=False),
        patch("app.services.application.paystack_gateway.initialize_transaction") as mock_init,
        patch("app.services.email.send_email", return_value=True),
    ):
        yield mock_init


@pytest.fixture()
def parent_application(db_session, parent_person, admission_form_with_price):
    app = Application(
        admission_form_id=admission_form_with_price.id,
        parent_id=parent_person.id,
        application_number="APP-PARENT-001",
        status=ApplicationStatus.draft,
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


@pytest.fixture()
def other_parent_application(db_session, person, admission_form_with_price):
    app = Application(
        admission_form_id=admission_form_with_price.id,
        parent_id=person.id,
        application_number="APP-PARENT-002",
        status=ApplicationStatus.draft,
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


class TestWebParentApplications:
    def test_list_applications(self, client, parent_auth_cookie, parent_application):
        response = client.get(
            "/parent/applications",
            cookies=parent_auth_cookie,
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert b"My Applications" in response.content
        assert parent_application.application_number.encode() in response.content

    def test_purchase_form_page(
        self,
        client,
        parent_auth_cookie,
        school,
        admission_form_with_price,
    ):
        response = client.get(
            f"/parent/applications/purchase/{admission_form_with_price.id}",
            cookies=parent_auth_cookie,
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert b"Confirm Purchase" in response.content
        assert school.name.encode() in response.content
        assert admission_form_with_price.title.encode() in response.content

    def test_purchase_form_submit(
        self,
        client,
        parent_auth_cookie,
        admission_form_with_price,
    ):
        page_response = client.get(
            f"/parent/applications/purchase/{admission_form_with_price.id}",
            cookies=parent_auth_cookie,
            follow_redirects=False,
        )
        csrf_token = page_response.cookies.get("csrf_token", "")

        response = client.post(
            f"/parent/applications/purchase/{admission_form_with_price.id}",
            data={"csrf_token": csrf_token},
            headers={"X-CSRF-Token": csrf_token},
            cookies={**parent_auth_cookie, "csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/parent/applications/fill/" in response.headers["location"]

    def test_view_application_detail(self, client, parent_auth_cookie, parent_application):
        response = client.get(
            f"/parent/applications/{parent_application.id}",
            cookies=parent_auth_cookie,
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert parent_application.application_number.encode() in response.content

    def test_idor_parent_cannot_access_other_parents_application(
        self,
        client,
        parent_auth_cookie,
        other_parent_application,
    ):
        response = client.get(
            f"/parent/applications/{other_parent_application.id}",
            cookies=parent_auth_cookie,
            follow_redirects=False,
        )

        assert response.status_code in (302, 303, 404)
        if response.status_code in (302, 303):
            assert response.headers["location"].startswith("/parent/applications")
