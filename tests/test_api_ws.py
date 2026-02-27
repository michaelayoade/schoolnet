"""Tests for WebSocket auth token extraction."""
import uuid
from unittest.mock import MagicMock

from app.api import ws
from app.api.ws import _token_from_subprotocol


def test_token_from_subprotocol_uses_first_offered_value() -> None:
    websocket = MagicMock()
    websocket.scope = {"subprotocols": ["jwt.access.token", "fallback"]}
    websocket.query_params = {"token": "legacy-query-token"}

    assert _token_from_subprotocol(websocket) == "jwt.access.token"


def test_token_from_subprotocol_does_not_fallback_to_query_param() -> None:
    websocket = MagicMock()
    websocket.scope = {"subprotocols": []}
    websocket.query_params = {"token": "legacy-query-token"}

    assert _token_from_subprotocol(websocket) == ""


class _FakeDB:
    def __init__(self, scalar_result):
        self._scalar_result = scalar_result
        self.scalar_called = 0
        self.closed = False

    def scalar(self, _stmt):
        self.scalar_called += 1
        return self._scalar_result

    def close(self):
        self.closed = True


def test_authenticate_ws_requires_active_session(monkeypatch) -> None:
    person_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    fake_db = _FakeDB(scalar_result=object())

    monkeypatch.setattr(ws, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        ws,
        "decode_access_token",
        lambda _db, _token: {"sub": person_id, "session_id": session_id},
    )

    assert ws._authenticate_ws("jwt-token") == person_id
    assert fake_db.scalar_called == 1
    assert fake_db.closed is True


def test_authenticate_ws_rejects_revoked_or_missing_session(monkeypatch) -> None:
    person_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    fake_db = _FakeDB(scalar_result=None)

    monkeypatch.setattr(ws, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        ws,
        "decode_access_token",
        lambda _db, _token: {"sub": person_id, "session_id": session_id},
    )

    assert ws._authenticate_ws("jwt-token") is None
    assert fake_db.scalar_called == 1
    assert fake_db.closed is True


def test_authenticate_ws_rejects_missing_session_claim(monkeypatch) -> None:
    person_id = str(uuid.uuid4())
    fake_db = _FakeDB(scalar_result=object())

    monkeypatch.setattr(ws, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        ws,
        "decode_access_token",
        lambda _db, _token: {"sub": person_id},
    )

    assert ws._authenticate_ws("jwt-token") is None
    assert fake_db.scalar_called == 0
    assert fake_db.closed is True
