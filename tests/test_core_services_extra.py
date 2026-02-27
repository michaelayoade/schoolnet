import uuid
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import Response

from app.models.audit import AuditActorType, AuditEvent
from app.schemas.rbac import PermissionCreate, PersonRoleCreate, RoleCreate
from app.services import audit as audit_service
from app.services import rbac as rbac_service
from app.services import scheduler as scheduler_service


def test_rbac_role_permission_link(db_session, person):
    role = rbac_service.roles.create(db_session, RoleCreate(name=f"test_role_{uuid.uuid4().hex[:8]}"))
    permission_key = f"people:read:{uuid.uuid4().hex[:8]}"
    permission = rbac_service.permissions.create(
        db_session, PermissionCreate(key=permission_key, description="People Read")
    )
    link = rbac_service.person_roles.create(
        db_session, PersonRoleCreate(person_id=person.id, role_id=role.id)
    )
    assert link.person_id == person.id
    assert permission.key == permission_key


def test_audit_log_request(db_session):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    response = Response(status_code=200)
    audit_service.audit_events.log_request(db_session, request, response)
    events = audit_service.audit_events.list(
        db_session,
        actor_id=None,
        actor_type=None,
        action="POST",
        entity_type="/test",
        request_id=None,
        is_success=True,
        status_code=200,
        is_active=None,
        order_by="occurred_at",
        order_dir="desc",
        limit=5,
        offset=0,
    )
    assert len(events) == 1


def test_scheduler_refresh_response():
    result = scheduler_service.refresh_schedule()
    assert "detail" in result


def test_audit_log_request_ignores_actor_headers_for_untrusted_ip(db_session):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test/untrusted",
        "headers": [
            (b"x-actor-id", b"spoofed-user"),
            (b"x-actor-type", b"service"),
        ],
        "client": ("203.0.113.10", 12345),
        "query_string": b"",
    }
    request = Request(scope)
    response = Response(status_code=200)
    audit_service.audit_events.log_request(db_session, request, response)

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "/test/untrusted")
        .order_by(AuditEvent.occurred_at.desc())
        .first()
    )
    assert event is not None
    assert event.actor_id is None
    assert event.actor_type == AuditActorType.system


def test_audit_log_request_uses_state_actor_over_headers(db_session):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test/state-priority",
        "headers": [
            (b"x-actor-id", b"spoofed-user"),
            (b"x-actor-type", b"service"),
        ],
        "client": ("198.51.100.24", 12345),
        "query_string": b"",
    }
    request = Request(scope)
    request.state.actor_id = "authenticated-user-id"
    request.state.actor_type = "user"
    response = Response(status_code=200)
    audit_service.audit_events.log_request(db_session, request, response)

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "/test/state-priority")
        .order_by(AuditEvent.occurred_at.desc())
        .first()
    )
    assert event is not None
    assert event.actor_id == "authenticated-user-id"
    assert event.actor_type == AuditActorType.user


def test_audit_log_request_uses_actor_headers_for_trusted_internal_ip(
    db_session, monkeypatch
):
    monkeypatch.setattr(audit_service.settings, "internal_service_ips", "127.0.0.1")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test/internal",
        "headers": [
            (b"x-actor-id", b"internal-service"),
            (b"x-actor-type", b"service"),
        ],
        "client": ("127.0.0.1", 12345),
        "query_string": b"",
    }
    request = Request(scope)
    response = Response(status_code=200)
    audit_service.audit_events.log_request(db_session, request, response)

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "/test/internal")
        .order_by(AuditEvent.occurred_at.desc())
        .first()
    )
    assert event is not None
    assert event.actor_id == "internal-service"
    assert event.actor_type == AuditActorType.service
