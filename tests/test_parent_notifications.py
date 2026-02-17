"""Tests for parent notification bell and list."""

import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import _create_access_token


def _get_csrf(client):
    resp = client.get("/login")
    return resp.cookies.get("csrf_token", "")


def _setup_parent(db_session):
    """Create parent person + role + session."""
    from app.models.person import Person
    from app.models.auth import Session as AuthSession, SessionStatus
    from app.models.rbac import Role, PersonRole

    person = Person(
        first_name="Notif", last_name="Parent",
        email=f"notif-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(person)
    db_session.flush()

    role = db_session.query(Role).filter(Role.name == "parent").first()
    if not role:
        role = Role(name="parent", description="Parent role")
        db_session.add(role)
        db_session.flush()
    db_session.add(PersonRole(person_id=person.id, role_id=role.id))

    auth_sess = AuthSession(
        person_id=person.id,
        token_hash="notif-hash-" + uuid.uuid4().hex[:8],
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(auth_sess)
    db_session.commit()
    db_session.refresh(person)
    db_session.refresh(auth_sess)

    token = _create_access_token(
        str(person.id), str(auth_sess.id), roles=["parent"]
    )
    return person, token


def _create_notification(db_session, recipient_id, title="Test Notification", is_read=False):
    from app.models.notification import Notification, NotificationType

    notif = Notification(
        recipient_id=recipient_id,
        title=title,
        message="This is a test notification",
        type=NotificationType.info,
        is_read=is_read,
    )
    db_session.add(notif)
    db_session.commit()
    db_session.refresh(notif)
    return notif


class TestParentNotifications:
    def test_notifications_list_empty(self, client, db_session):
        person, token = _setup_parent(db_session)
        resp = client.get(
            "/parent/notifications",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert b"No notifications yet" in resp.content

    def test_notifications_list_with_items(self, client, db_session):
        person, token = _setup_parent(db_session)
        _create_notification(db_session, person.id, "Application Accepted")
        resp = client.get(
            "/parent/notifications",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert b"Application Accepted" in resp.content

    def test_bell_fragment_no_unread(self, client, db_session):
        person, token = _setup_parent(db_session)
        resp = client.get(
            "/parent/notifications/bell",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        # No badge if zero unread
        assert b"bg-red-500" not in resp.content

    def test_bell_fragment_with_unread(self, client, db_session):
        person, token = _setup_parent(db_session)
        _create_notification(db_session, person.id, "New message", is_read=False)
        resp = client.get(
            "/parent/notifications/bell",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert b"bg-red-500" in resp.content
        assert b"1" in resp.content

    def test_mark_notification_read(self, client, db_session):
        person, token = _setup_parent(db_session)
        notif = _create_notification(db_session, person.id)
        csrf = _get_csrf(client)
        resp = client.post(
            f"/parent/notifications/{notif.id}/read",
            data={"csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            cookies={"access_token": token, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Verify marked as read
        db_session.refresh(notif)
        assert notif.is_read is True

    def test_notifications_unauthenticated(self, client):
        resp = client.get("/parent/notifications", follow_redirects=False)
        assert resp.status_code == 302
