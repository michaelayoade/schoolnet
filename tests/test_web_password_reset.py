"""Tests for password reset web pages."""

import uuid

from app.services.auth_flow import _issue_password_reset_token


def _get_csrf(client):
    resp = client.get("/login")
    return resp.cookies.get("csrf_token", "")


def _post(client, url, data):
    """POST form with CSRF."""
    csrf = _get_csrf(client)
    data["csrf_token"] = csrf
    return client.post(
        url,
        data=data,
        headers={"X-CSRF-Token": csrf},
        cookies={"csrf_token": csrf},
        follow_redirects=False,
    )


def _make_user(db_session):
    """Create person + credential for password reset testing."""
    from app.models.person import Person
    from app.models.auth import UserCredential
    from app.services.auth_flow import hash_password

    person = Person(
        first_name="Reset",
        last_name="Test",
        email=f"reset-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(person)
    db_session.flush()

    cred = UserCredential(
        person_id=person.id,
        username=person.email,
        password_hash=hash_password("oldpass123"),
        is_active=True,
    )
    db_session.add(cred)
    db_session.commit()
    db_session.refresh(person)
    return person, cred


class TestForgotPassword:
    def test_forgot_password_page_renders(self, client):
        resp = client.get("/forgot-password")
        assert resp.status_code == 200
        assert b"Forgot Password" in resp.content

    def test_forgot_password_existing_email(self, client, db_session):
        person, _ = _make_user(db_session)
        resp = _post(client, "/forgot-password", {"email": person.email})
        assert resp.status_code == 200
        assert b"reset link has been sent" in resp.content

    def test_forgot_password_nonexistent_email(self, client, db_session):
        resp = _post(client, "/forgot-password", {"email": "nobody@example.com"})
        assert resp.status_code == 200
        assert b"reset link has been sent" in resp.content


class TestResetPassword:
    def test_reset_password_page_renders(self, client):
        resp = client.get("/reset-password?token=abc123")
        assert resp.status_code == 200
        assert b"Reset Password" in resp.content

    def test_reset_password_valid_token(self, client, db_session):
        person, _ = _make_user(db_session)
        token = _issue_password_reset_token(None, str(person.id), person.email)
        resp = _post(
            client,
            "/reset-password",
            {
                "token": token,
                "new_password": "NewPass123",
                "confirm_password": "NewPass123",
            },
        )
        assert resp.status_code == 303
        assert "/login" in resp.headers["location"]

    def test_reset_password_invalid_token(self, client, db_session):
        resp = _post(
            client,
            "/reset-password",
            {
                "token": "invalid-token",
                "new_password": "NewPass123",
                "confirm_password": "NewPass123",
            },
        )
        assert resp.status_code == 200
        assert b"Invalid or expired" in resp.content

    def test_reset_password_mismatch(self, client, db_session):
        person, _ = _make_user(db_session)
        token = _issue_password_reset_token(None, str(person.id), person.email)
        resp = _post(
            client,
            "/reset-password",
            {
                "token": token,
                "new_password": "NewPass123",
                "confirm_password": "different456",
            },
        )
        assert resp.status_code == 200
        assert b"do not match" in resp.content
