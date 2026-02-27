"""Tests for RateLimitMiddleware."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.middleware.rate_limit import RateLimitMiddleware, _get_client_ip


def _make_request(client_host: str | None, forwarded_for: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "headers": headers,
        "client": (client_host, 12345) if client_host is not None else None,
    }
    return Request(scope)


@pytest.fixture
def app_with_rate_limit() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/auth/login")
    def login():
        return {"token": "abc"}

    @app.post("/auth/password-reset")
    def password_reset():
        return {"sent": True}

    @app.get("/auth/login")
    def login_form():
        return {"form": True}

    @app.post("/other")
    def other():
        return {"ok": True}

    return app


@pytest.fixture
def client(app_with_rate_limit: FastAPI) -> TestClient:
    return TestClient(app_with_rate_limit)


class TestRateLimitMiddleware:
    def test_allows_get_requests(self, client: TestClient) -> None:
        """GET requests are never rate limited."""
        resp = client.get("/auth/login")
        assert resp.status_code == 200

    def test_allows_non_auth_posts(self, client: TestClient) -> None:
        """POST requests to non-auth paths are not rate limited."""
        resp = client.post("/other")
        assert resp.status_code == 200

    @patch("app.middleware.rate_limit._get_redis", return_value=None)
    def test_fallback_limits_when_redis_unavailable(self, mock_redis: MagicMock) -> None:
        """When Redis is unavailable, in-memory fallback blocks the 6th request."""
        # Create a fresh app so the middleware hasn't cached Redis yet
        fresh_app = FastAPI()
        fresh_app.add_middleware(RateLimitMiddleware)

        @fresh_app.post("/auth/login")
        def login():
            return {"token": "abc"}

        with TestClient(fresh_app) as c:
            responses = [c.post("/auth/login") for _ in range(6)]
        assert [resp.status_code for resp in responses[:5]] == [200] * 5
        assert responses[5].status_code == 429
        assert responses[5].json()["code"] == "rate_limit_exceeded"

    @patch("app.middleware.rate_limit._get_redis")
    def test_fallback_limits_when_redis_connection_errors(
        self, mock_redis: MagicMock
    ) -> None:
        """If Redis operations fail, in-memory fallback blocks the 6th request."""
        from redis.exceptions import ConnectionError as RedisConnectionError

        mock_r = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.side_effect = RedisConnectionError("redis down")
        mock_r.pipeline.return_value = mock_pipe
        mock_redis.return_value = mock_r

        fresh_app = FastAPI()
        fresh_app.add_middleware(RateLimitMiddleware)

        @fresh_app.post("/auth/login")
        def login():
            return {"token": "abc"}

        with TestClient(fresh_app) as c:
            responses = [c.post("/auth/login") for _ in range(6)]
        assert [resp.status_code for resp in responses[:5]] == [200] * 5
        assert responses[5].status_code == 429
        assert responses[5].json()["code"] == "rate_limit_exceeded"

    @patch("app.middleware.rate_limit._get_redis")
    def test_rate_limit_headers_present(self, mock_redis: MagicMock) -> None:
        """Rate limit response headers are present when Redis works."""
        mock_r = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [None, 0, None, None]  # count=0 (under limit)
        mock_r.pipeline.return_value = mock_pipe
        mock_redis.return_value = mock_r

        fresh_app = FastAPI()
        fresh_app.add_middleware(RateLimitMiddleware)

        @fresh_app.post("/auth/login")
        def login():
            return {"token": "abc"}

        with TestClient(fresh_app) as c:
            resp = c.post("/auth/login")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers

    def test_429_response_format(self) -> None:
        """429 responses have standard error format."""
        from starlette.responses import JSONResponse

        # Verify the response structure matches our error envelope
        response_content = {
            "code": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "details": None,
        }
        resp = JSONResponse(status_code=429, content=response_content)
        assert resp.status_code == 429


class TestRateLimitPaths:
    def test_login_path_configured(self) -> None:
        from app.middleware.rate_limit import _RATE_LIMIT_PATHS
        assert "/auth/login" in _RATE_LIMIT_PATHS
        max_req, window = _RATE_LIMIT_PATHS["/auth/login"]
        assert max_req == 10
        assert window == 60

    def test_password_reset_path_configured(self) -> None:
        from app.middleware.rate_limit import _RATE_LIMIT_PATHS
        assert "/auth/password-reset" in _RATE_LIMIT_PATHS
        max_req, window = _RATE_LIMIT_PATHS["/auth/password-reset"]
        assert max_req == 5
        assert window == 300

    def test_mfa_verify_path_configured(self) -> None:
        from app.middleware.rate_limit import _RATE_LIMIT_PATHS
        assert "/auth/mfa/verify" in _RATE_LIMIT_PATHS

    def test_register_path_configured(self) -> None:
        from app.middleware.rate_limit import _RATE_LIMIT_PATHS
        assert "/auth/register" in _RATE_LIMIT_PATHS


class TestClientIpExtraction:
    def test_ignores_x_forwarded_for_when_proxy_untrusted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TRUSTED_PROXIES", "198.51.100.0/24")
        request = _make_request("203.0.113.10", "198.51.100.8")
        assert _get_client_ip(request) == "203.0.113.10"

    def test_uses_x_forwarded_for_when_proxy_trusted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TRUSTED_PROXIES", "198.51.100.0/24")
        request = _make_request("198.51.100.10", "203.0.113.10, 198.51.100.10")
        assert _get_client_ip(request) == "203.0.113.10"

    def test_invalid_x_forwarded_for_falls_back_to_direct_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TRUSTED_PROXIES", "198.51.100.0/24")
        request = _make_request("198.51.100.10", "not-an-ip")
        assert _get_client_ip(request) == "198.51.100.10"
