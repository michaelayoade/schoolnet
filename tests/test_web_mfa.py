"""Tests for web MFA (TOTP) verification routes."""
import re
import uuid

import pyotp
import pytest

from app.models.auth import AuthProvider, UserCredential
from app.services.auth_flow import AuthFlow, hash_password


def _unique_username() -> str:
    return f"mfa-user-{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture()
def mfa_user(db_session, person):
    """Create a user with MFA enabled and return (person, credential, totp_secret)."""
    username = _unique_username()
    credential = UserCredential(
        person_id=person.id,
        provider=AuthProvider.local,
        username=username,
        password_hash=hash_password("testpass123"),
        is_active=True,
    )
    db_session.add(credential)
    db_session.commit()

    # Set up MFA
    setup = AuthFlow.mfa_setup(db_session, str(person.id), label="test-device")
    code = pyotp.TOTP(setup["secret"]).now()
    AuthFlow.mfa_confirm(db_session, str(setup["method_id"]), code)

    return person, credential, setup["secret"]


class TestPublicMfaVerify:
    """Tests for the public /mfa-verify route."""

    def test_login_with_mfa_shows_mfa_page(self, client, db_session, mfa_user):
        """Login with MFA-enabled user should render MFA verify page."""
        person, credential, _secret = mfa_user
        person.email_verified = True
        db_session.commit()

        resp = client.get("/login")
        csrf_token = resp.cookies.get("csrf_token", "")

        response = client.post(
            "/login",
            data={
                "email": credential.username,
                "password": "testpass123",
                "csrf_token": csrf_token,
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Two-Factor Authentication" in response.content
        assert b"mfa_token" in response.content
        assert b"MFA is not supported" not in response.content

    def test_mfa_verify_success(self, client, db_session, mfa_user):
        """Successful MFA verification should set cookies and redirect."""
        person, credential, secret = mfa_user
        person.email_verified = True
        db_session.commit()

        # First login to get the MFA token
        resp = client.get("/login")
        csrf_token = resp.cookies.get("csrf_token", "")

        login_resp = client.post(
            "/login",
            data={
                "email": credential.username,
                "password": "testpass123",
                "csrf_token": csrf_token,
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert login_resp.status_code == 200

        # Extract mfa_token from the hidden input
        content = login_resp.text
        match = re.search(r'name="mfa_token"\s+value="([^"]+)"', content)
        assert match, "mfa_token not found in response"
        mfa_token = match.group(1)

        # Generate valid TOTP code
        totp = pyotp.TOTP(secret)
        code = totp.now()

        # Submit MFA verification
        verify_resp = client.post(
            "/mfa-verify",
            data={
                "mfa_token": mfa_token,
                "code": code,
                "csrf_token": csrf_token,
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert verify_resp.status_code == 303
        assert "access_token" in verify_resp.cookies
        assert "logged_in" in verify_resp.cookies

    def test_mfa_verify_invalid_code(self, client, db_session, mfa_user):
        """Invalid MFA code should re-render MFA page with error."""
        person, credential, _secret = mfa_user
        person.email_verified = True
        db_session.commit()

        resp = client.get("/login")
        csrf_token = resp.cookies.get("csrf_token", "")

        login_resp = client.post(
            "/login",
            data={
                "email": credential.username,
                "password": "testpass123",
                "csrf_token": csrf_token,
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        match = re.search(r'name="mfa_token"\s+value="([^"]+)"', login_resp.text)
        assert match
        mfa_token = match.group(1)

        verify_resp = client.post(
            "/mfa-verify",
            data={
                "mfa_token": mfa_token,
                "code": "000000",
                "csrf_token": csrf_token,
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert verify_resp.status_code == 200
        assert b"Invalid or expired code" in verify_resp.content
        assert b"mfa_token" in verify_resp.content

    def test_mfa_verify_expired_token(self, client, db_session):
        """Expired MFA token should show error on MFA page."""
        resp = client.get("/login")
        csrf_token = resp.cookies.get("csrf_token", "")

        verify_resp = client.post(
            "/mfa-verify",
            data={
                "mfa_token": "invalid-token",
                "code": "123456",
                "csrf_token": csrf_token,
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert verify_resp.status_code == 200
        assert b"Invalid or expired code" in verify_resp.content


class TestAdminMfaVerify:
    """Tests for the admin /admin/mfa-verify route."""

    def test_admin_login_with_mfa_shows_mfa_page(self, client, db_session, mfa_user):
        """Admin login with MFA-enabled user should render MFA verify page."""
        _person, credential, _secret = mfa_user

        resp = client.get("/admin/login")
        csrf_token = resp.cookies.get("csrf_token", "")

        response = client.post(
            "/admin/login",
            data={
                "username": credential.username,
                "password": "testpass123",
                "csrf_token": csrf_token,
                "next": "/admin",
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Two-Factor Authentication" in response.content
        assert b"/admin/mfa-verify" in response.content
        assert b"MFA is not yet supported" not in response.content

    def test_admin_mfa_verify_success(self, client, db_session, mfa_user):
        """Successful admin MFA verification should set cookies and redirect."""
        _person, credential, secret = mfa_user

        resp = client.get("/admin/login")
        csrf_token = resp.cookies.get("csrf_token", "")

        login_resp = client.post(
            "/admin/login",
            data={
                "username": credential.username,
                "password": "testpass123",
                "csrf_token": csrf_token,
                "next": "/admin",
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        match = re.search(r'name="mfa_token"\s+value="([^"]+)"', login_resp.text)
        assert match, "mfa_token not found in response"
        mfa_token = match.group(1)

        totp = pyotp.TOTP(secret)
        code = totp.now()

        verify_resp = client.post(
            "/admin/mfa-verify",
            data={
                "mfa_token": mfa_token,
                "code": code,
                "next_url": "/admin",
                "csrf_token": csrf_token,
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert verify_resp.status_code == 302
        assert "access_token" in verify_resp.cookies

    def test_admin_mfa_verify_invalid_code(self, client, db_session, mfa_user):
        """Invalid admin MFA code should re-render MFA page with error."""
        _person, credential, _secret = mfa_user

        resp = client.get("/admin/login")
        csrf_token = resp.cookies.get("csrf_token", "")

        login_resp = client.post(
            "/admin/login",
            data={
                "username": credential.username,
                "password": "testpass123",
                "csrf_token": csrf_token,
                "next": "/admin",
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        match = re.search(r'name="mfa_token"\s+value="([^"]+)"', login_resp.text)
        assert match
        mfa_token = match.group(1)

        verify_resp = client.post(
            "/admin/mfa-verify",
            data={
                "mfa_token": mfa_token,
                "code": "000000",
                "next_url": "/admin",
                "csrf_token": csrf_token,
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert verify_resp.status_code == 200
        assert b"Invalid or expired code" in verify_resp.content
        assert b"/admin/mfa-verify" in verify_resp.content
