"""Tests for web token refresh and login redirect."""

import uuid
from datetime import datetime, timedelta, timezone


def _get_csrf(client):
    """Get a CSRF token by loading the login page."""
    resp = client.get("/login")
    return resp.cookies.get("csrf_token", "")


def _login_post(client, db_session, email, password):
    """POST /login with CSRF handling."""
    csrf = _get_csrf(client)
    return client.post(
        "/login",
        data={
            "email": email,
            "password": password,
            "csrf_token": csrf,
        },
        headers={"X-CSRF-Token": csrf},
        cookies={"csrf_token": csrf},
        follow_redirects=False,
    )


def _make_person_with_role(db_session, role_name):
    """Create person + credential + role. Returns (person, credential)."""
    from app.models.person import Person
    from app.models.auth import UserCredential
    from app.models.rbac import Role, PersonRole
    from app.services.auth_flow import hash_password

    person = Person(
        first_name="Test", last_name="User",
        email=f"{role_name}-{uuid.uuid4().hex[:8]}@example.com",
        email_verified=True,
    )
    db_session.add(person)
    db_session.flush()

    cred = UserCredential(
        person_id=person.id,
        username=person.email,
        password_hash=hash_password("testpass123"),
        is_active=True,
    )
    db_session.add(cred)

    role = db_session.query(Role).filter(Role.name == role_name).first()
    if not role:
        role = Role(name=role_name, description=f"{role_name} role")
        db_session.add(role)
        db_session.flush()

    db_session.add(PersonRole(person_id=person.id, role_id=role.id))
    db_session.commit()
    db_session.refresh(person)

    return person, cred


def _make_refresh_session(db_session, person):
    """Create an auth session with known refresh token. Returns raw refresh token."""
    from app.models.auth import Session as AuthSession, SessionStatus
    from app.services.auth_flow import _hash_token

    refresh_raw = "test-refresh-token-" + uuid.uuid4().hex
    auth_sess = AuthSession(
        person_id=person.id,
        token_hash=_hash_token(refresh_raw),
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(auth_sess)
    db_session.commit()
    db_session.refresh(auth_sess)
    return refresh_raw


class TestWebRefresh:
    def test_web_refresh_with_valid_cookie(self, client, db_session):
        person, _ = _make_person_with_role(db_session, "parent")
        refresh_raw = _make_refresh_session(db_session, person)
        csrf = _get_csrf(client)
        resp = client.post(
            "/auth/web-refresh",
            cookies={"refresh_token": refresh_raw, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "access_token" in resp.cookies
        assert "logged_in" in resp.cookies

    def test_web_refresh_missing_cookie(self, client):
        csrf = _get_csrf(client)
        resp = client.post(
            "/auth/web-refresh",
            headers={"X-CSRF-Token": csrf},
            cookies={"csrf_token": csrf},
        )
        assert resp.status_code == 401

    def test_web_refresh_invalid_cookie(self, client):
        csrf = _get_csrf(client)
        resp = client.post(
            "/auth/web-refresh",
            cookies={"refresh_token": "totally-bogus-token", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 401


class TestLoginRedirect:
    def test_login_parent_redirects_to_parent(self, client, db_session):
        _, cred = _make_person_with_role(db_session, "parent")
        resp = _login_post(client, db_session, cred.username, "testpass123")
        assert resp.status_code == 303
        assert resp.headers["location"] == "/parent"
        assert "logged_in" in resp.cookies

    def test_login_school_admin_redirects_to_school(self, client, db_session):
        _, cred = _make_person_with_role(db_session, "school_admin")
        resp = _login_post(client, db_session, cred.username, "testpass123")
        assert resp.status_code == 303
        assert resp.headers["location"] == "/school"

    def test_login_platform_admin_redirects_to_admin(self, client, db_session):
        _, cred = _make_person_with_role(db_session, "platform_admin")
        resp = _login_post(client, db_session, cred.username, "testpass123")
        assert resp.status_code == 303
        assert resp.headers["location"] == "/admin/schools"

    def test_logout_deletes_logged_in_cookie(self, client):
        csrf = _get_csrf(client)
        resp = client.post(
            "/logout",
            data={"csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            cookies={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        set_cookies = resp.headers.get_list("set-cookie")
        cookie_names = [c.split("=")[0].strip() for c in set_cookies]
        assert "logged_in" in cookie_names
