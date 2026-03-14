"""Tests for SecurityHeadersMiddleware."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.middleware.security_headers import SecurityHeadersMiddleware


@pytest.fixture
def app_with_headers() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    def test_endpoint():
        return {"ok": True}

    return app


@pytest_asyncio.fixture
async def client(app_with_headers: FastAPI) -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_headers, raise_app_exceptions=True),
        base_url="http://test",
    ) as client:
        yield client


class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_x_content_type_options(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/test")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/test")
        assert resp.headers["X-Frame-Options"] == "DENY"

    @pytest.mark.asyncio
    async def test_x_xss_protection(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/test")
        assert resp.headers["X-XSS-Protection"] == "1; mode=block"

    @pytest.mark.asyncio
    async def test_referrer_policy(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/test")
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_permissions_policy(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/test")
        assert "camera=()" in resp.headers["Permissions-Policy"]
        assert "microphone=()" in resp.headers["Permissions-Policy"]

    @pytest.mark.asyncio
    async def test_content_security_policy(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/test")
        csp = resp.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "form-action 'self'" in csp
        assert "script-src 'self' 'nonce-" in csp
        assert "script-src 'self' 'unsafe-inline'" not in csp
        assert "'unsafe-eval'" not in csp

    @pytest.mark.asyncio
    async def test_no_hsts_without_https(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/test")
        assert "Strict-Transport-Security" not in resp.headers

    @pytest.mark.asyncio
    async def test_hsts_with_https_proxy(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/test", headers={"X-Forwarded-Proto": "https"})
        assert "Strict-Transport-Security" in resp.headers
        assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_headers(self) -> None:
        """If a route sets a custom CSP, the middleware should not overwrite it."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/custom-csp")
        def custom_csp():
            from starlette.responses import JSONResponse

            resp = JSONResponse({"ok": True})
            resp.headers["Content-Security-Policy"] = "default-src 'none'"
            return resp

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=True),
            base_url="http://test",
        ) as client:
            resp = await client.get("/custom-csp")
        assert resp.headers["Content-Security-Policy"] == "default-src 'none'"
