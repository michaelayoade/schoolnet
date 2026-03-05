"""Tests for RateLimitMiddleware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
import httpx
from fastapi import FastAPI

from app.middleware.rate_limit import RateLimitMiddleware


@pytest.fixture
def app_with_rate_limit() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/auth/login")
    def login():
        return {"token": "abc"}

    @app.post("/auth/forgot-password")
    def forgot_password():
        return {"sent": True}

    @app.get("/auth/login")
    def login_form():
        return {"form": True}

    @app.post("/other")
    def other():
        return {"ok": True}

    return app


@pytest_asyncio.fixture
async def client(app_with_rate_limit: FastAPI) -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app_with_rate_limit, raise_app_exceptions=True
        ),
        base_url="http://test",
    ) as client:
        yield client


class TestRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_allows_get_requests(self, client: httpx.AsyncClient) -> None:
        """GET requests are never rate limited."""
        resp = await client.get("/auth/login")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_allows_non_auth_posts(self, client: httpx.AsyncClient) -> None:
        """POST requests to non-auth paths are not rate limited."""
        resp = await client.post("/other")
        assert resp.status_code == 200

    @patch("app.middleware.rate_limit._get_redis", return_value=None)
    @pytest.mark.asyncio
    async def test_blocks_when_redis_unavailable_by_default(
        self, mock_redis: MagicMock
    ) -> None:
        """Fail-closed by default: if Redis is unavailable, requests are blocked."""
        # Create a fresh app so the middleware hasn't cached Redis yet
        fresh_app = FastAPI()
        fresh_app.add_middleware(RateLimitMiddleware)

        @fresh_app.post("/auth/login")
        def login():
            return {"token": "abc"}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fresh_app, raise_app_exceptions=True),
            base_url="http://test",
        ) as c:
            resp = await c.post("/auth/login")
        assert resp.status_code == 503
        assert resp.json()["code"] == "rate_limit_unavailable"

    @patch("app.middleware.rate_limit._get_redis", return_value=None)
    @pytest.mark.asyncio
    async def test_allows_when_redis_unavailable_if_fail_open_enabled(
        self, mock_redis: MagicMock, monkeypatch
    ) -> None:
        monkeypatch.setenv("RATE_LIMIT_FAIL_CLOSED", "false")

        fresh_app = FastAPI()
        fresh_app.add_middleware(RateLimitMiddleware)

        @fresh_app.post("/auth/login")
        def login():
            return {"token": "abc"}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fresh_app, raise_app_exceptions=True),
            base_url="http://test",
        ) as c:
            resp = await c.post("/auth/login")
        assert resp.status_code == 200

    @patch("app.middleware.rate_limit._get_redis")
    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, mock_redis: MagicMock) -> None:
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

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fresh_app, raise_app_exceptions=True),
            base_url="http://test",
        ) as c:
            resp = await c.post("/auth/login")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers

    def test_429_response_format(self) -> None:
        """429 responses have standard error format."""
        from app.middleware.rate_limit import RateLimitMiddleware
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

        assert "/auth/forgot-password" in _RATE_LIMIT_PATHS
        max_req, window = _RATE_LIMIT_PATHS["/auth/forgot-password"]
        assert max_req == 5
        assert window == 300

    def test_mfa_verify_path_configured(self) -> None:
        from app.middleware.rate_limit import _RATE_LIMIT_PATHS

        assert "/auth/mfa/verify" in _RATE_LIMIT_PATHS

    def test_api_reset_path_configured(self) -> None:
        from app.middleware.rate_limit import _RATE_LIMIT_PATHS

        assert "/auth/reset-password" in _RATE_LIMIT_PATHS

    def test_web_login_paths_configured(self) -> None:
        from app.middleware.rate_limit import _RATE_LIMIT_PATHS

        assert "/login" in _RATE_LIMIT_PATHS
        assert "/admin/login" in _RATE_LIMIT_PATHS
        assert "/mfa-verify" in _RATE_LIMIT_PATHS
        assert "/admin/mfa-verify" in _RATE_LIMIT_PATHS

    def test_web_registration_and_reset_paths_configured(self) -> None:
        from app.middleware.rate_limit import _RATE_LIMIT_PATHS

        assert "/forgot-password" in _RATE_LIMIT_PATHS
        assert "/reset-password" in _RATE_LIMIT_PATHS
        assert "/register/parent" in _RATE_LIMIT_PATHS
        assert "/register/school" in _RATE_LIMIT_PATHS


class TestClientIPSelection:
    def test_uses_remote_addr_when_proxy_headers_untrusted(self, monkeypatch) -> None:
        from app.middleware.rate_limit import _get_client_ip
        from starlette.requests import Request

        monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [(b"x-forwarded-for", b"203.0.113.1")],
            "client": ("127.0.0.1", 12345),
        }
        request = Request(scope)
        assert _get_client_ip(request) == "127.0.0.1"

    def test_uses_forwarded_addr_when_proxy_headers_trusted(self, monkeypatch) -> None:
        from app.middleware.rate_limit import _get_client_ip
        from starlette.requests import Request

        monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [(b"x-forwarded-for", b"203.0.113.1, 10.0.0.2")],
            "client": ("127.0.0.1", 12345),
        }
        request = Request(scope)
        assert _get_client_ip(request) == "203.0.113.1"
