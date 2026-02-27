"""Tests for WebSocket auth token extraction."""

from unittest.mock import MagicMock

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
