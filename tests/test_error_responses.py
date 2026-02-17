"""Tests for structured error responses with request_id."""
from __future__ import annotations

import pytest
import pytest_asyncio
import httpx
from fastapi import FastAPI, HTTPException

from app.errors import register_error_handlers
from app.observability import ObservabilityMiddleware


@pytest.fixture
def app_with_errors() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)
    register_error_handlers(app)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    @app.get("/http-error")
    def http_error():
        raise HTTPException(status_code=403, detail="Forbidden")

    @app.get("/http-error-dict")
    def http_error_dict():
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_input", "message": "Bad field", "details": {"field": "name"}},
        )

    @app.get("/crash")
    def crash():
        raise RuntimeError("boom")

    return app


@pytest_asyncio.fixture
async def client(app_with_errors: FastAPI) -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_errors, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


class TestErrorResponses:
    @pytest.mark.asyncio
    async def test_http_error_includes_request_id(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/http-error")
        assert resp.status_code == 403
        body = resp.json()
        assert "request_id" in body
        assert body["code"] == "http_403"
        assert body["message"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_http_error_dict_detail(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/http-error-dict")
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "invalid_input"
        assert body["message"] == "Bad field"
        assert body["details"] == {"field": "name"}
        assert "request_id" in body

    @pytest.mark.asyncio
    async def test_unhandled_exception_includes_request_id(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/crash")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "internal_error"
        assert body["message"] == "Internal server error"
        assert "request_id" in body
        # Should NOT leak exception details
        assert body["details"] is None

    @pytest.mark.asyncio
    async def test_request_id_propagated_from_header(self, client: httpx.AsyncClient) -> None:
        custom_id = "test-request-id-12345"
        resp = await client.get("/http-error", headers={"X-Request-Id": custom_id})
        body = resp.json()
        assert body["request_id"] == custom_id

    @pytest.mark.asyncio
    async def test_success_response_has_request_id_header(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/ok")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
