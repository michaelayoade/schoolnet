"""Tests for web access cookie TTL alignment."""

from app.web.auth import _access_cookie_max_age_seconds as _admin_access_cookie_max_age
from app.web.public import (
    _access_cookie_max_age_seconds as _public_access_cookie_max_age,
)


def test_access_cookie_max_age_defaults_to_15_minutes(monkeypatch):
    monkeypatch.delenv("JWT_ACCESS_TTL_MINUTES", raising=False)
    assert _admin_access_cookie_max_age() == 900
    assert _public_access_cookie_max_age() == 900


def test_access_cookie_max_age_uses_env_value(monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TTL_MINUTES", "20")
    assert _admin_access_cookie_max_age() == 1200
    assert _public_access_cookie_max_age() == 1200


def test_access_cookie_max_age_handles_invalid_env(monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TTL_MINUTES", "invalid")
    assert _admin_access_cookie_max_age() == 900
    assert _public_access_cookie_max_age() == 900
