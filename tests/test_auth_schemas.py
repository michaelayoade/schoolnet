"""Tests for auth schema serialization rules."""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.auth import SessionStatus
from app.schemas.auth import SessionRead


def test_session_read_does_not_expose_token_hash():
    now = datetime.now(timezone.utc)
    payload = {
        "id": uuid.uuid4(),
        "person_id": uuid.uuid4(),
        "status": SessionStatus.active,
        "token_hash": "sensitive-hash-value",
        "ip_address": "127.0.0.1",
        "user_agent": "pytest",
        "last_seen_at": now,
        "expires_at": now + timedelta(days=1),
        "revoked_at": None,
        "created_at": now,
    }

    session = SessionRead.model_validate(payload)
    data = session.model_dump()

    assert "token_hash" not in data
