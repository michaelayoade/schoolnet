from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.domain_settings import SettingValueType
from app.services import settings_seed


@pytest.fixture
def db_session_mock() -> MagicMock:
    return MagicMock(name="db_session")


@pytest.fixture
def clear_seed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = (
        "JWT_ALGORITHM",
        "JWT_ACCESS_TTL_MINUTES",
        "JWT_REFRESH_TTL_DAYS",
        "REFRESH_COOKIE_NAME",
        "REFRESH_COOKIE_SECURE",
        "REFRESH_COOKIE_SAMESITE",
        "REFRESH_COOKIE_DOMAIN",
        "REFRESH_COOKIE_PATH",
        "TOTP_ISSUER",
        "API_KEY_RATE_WINDOW_SECONDS",
        "API_KEY_RATE_MAX",
        "AUTH_DEFAULT_AUTH_PROVIDER",
        "JWT_SECRET",
        "TOTP_ENCRYPTION_KEY",
        "AUDIT_ENABLED",
        "AUDIT_METHODS",
        "AUDIT_SKIP_PATHS",
        "AUDIT_READ_TRIGGER_HEADER",
        "AUDIT_READ_TRIGGER_QUERY",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "REDIS_URL",
        "CELERY_TIMEZONE",
        "CELERY_BEAT_MAX_LOOP_INTERVAL",
        "CELERY_BEAT_REFRESH_SECONDS",
        "BILLING_DEFAULT_CURRENCY",
        "BILLING_TAX_RATE_PERCENT",
        "BILLING_INVOICE_PREFIX",
        "BILLING_TRIAL_PERIOD_DAYS",
        "BILLING_DUNNING_MAX_RETRIES",
        "BILLING_GRACE_PERIOD_DAYS",
        "BILLING_WEBHOOK_TOLERANCE_SECONDS",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def _calls_by_key(ensure_mock: MagicMock) -> dict[str, dict]:
    return {seed_call.kwargs["key"]: seed_call.kwargs for seed_call in ensure_mock.call_args_list}


def test_seed_auth_settings_defaults(db_session_mock: MagicMock, clear_seed_env: None) -> None:
    with patch.object(settings_seed.auth_settings, "ensure_by_key") as ensure_mock:
        settings_seed.seed_auth_settings(db_session_mock)

    seeded = _calls_by_key(ensure_mock)
    assert len(seeded) == 12
    assert all(seed_call.args[0] is db_session_mock for seed_call in ensure_mock.call_args_list)
    assert seeded["jwt_algorithm"]["value_type"] == SettingValueType.string
    assert seeded["jwt_algorithm"]["value_text"] == "HS256"
    assert seeded["jwt_access_ttl_minutes"]["value_text"] == "15"
    assert seeded["jwt_refresh_ttl_days"]["value_text"] == "30"
    assert seeded["refresh_cookie_name"]["value_text"] == "refresh_token"
    assert seeded["refresh_cookie_secure"]["value_type"] == SettingValueType.boolean
    assert seeded["refresh_cookie_samesite"]["value_text"] == "lax"
    assert seeded["refresh_cookie_domain"]["value_text"] is None
    assert seeded["refresh_cookie_path"]["value_text"] == "/auth"
    assert seeded["totp_issuer"]["value_text"] == "starter_template"
    assert seeded["api_key_rate_window_seconds"]["value_type"] == SettingValueType.integer
    assert seeded["api_key_rate_max"]["value_text"] == "5"
    assert seeded["default_auth_provider"]["value_text"] == "local"
    assert "jwt_secret" not in seeded
    assert "totp_encryption_key" not in seeded


def test_seed_auth_settings_adds_openbao_secret_refs(
    db_session_mock: MagicMock, clear_seed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_SECRET", "openbao://secret/data/app#jwt")
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", "vault://secret/data/app#totp")

    with patch.object(settings_seed.auth_settings, "ensure_by_key") as ensure_mock:
        settings_seed.seed_auth_settings(db_session_mock)

    seeded = _calls_by_key(ensure_mock)
    assert seeded["jwt_secret"]["is_secret"] is True
    assert seeded["jwt_secret"]["value_text"] == "openbao://secret/data/app#jwt"
    assert seeded["totp_encryption_key"]["is_secret"] is True
    assert seeded["totp_encryption_key"]["value_text"] == "vault://secret/data/app#totp"


def test_seed_auth_settings_skips_plain_secret_values(
    db_session_mock: MagicMock, clear_seed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_SECRET", "plain-secret-value")
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", "another-plain-secret")

    with patch.object(settings_seed.auth_settings, "ensure_by_key") as ensure_mock:
        settings_seed.seed_auth_settings(db_session_mock)

    seeded = _calls_by_key(ensure_mock)
    assert "jwt_secret" not in seeded
    assert "totp_encryption_key" not in seeded


def test_seed_audit_settings_defaults(db_session_mock: MagicMock, clear_seed_env: None) -> None:
    with patch.object(settings_seed.audit_settings, "ensure_by_key") as ensure_mock:
        settings_seed.seed_audit_settings(db_session_mock)

    seeded = _calls_by_key(ensure_mock)
    assert seeded["enabled"]["value_text"] == "true"
    assert seeded["methods"]["value_json"] == ["POST", "PUT", "PATCH", "DELETE"]
    assert seeded["skip_paths"]["value_json"] == ["/static", "/web", "/health"]
    assert seeded["read_trigger_header"]["value_text"] == "x-audit-read"
    assert seeded["read_trigger_query"]["value_text"] == "audit"


def test_seed_audit_settings_parses_csv_values(
    db_session_mock: MagicMock, clear_seed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_METHODS", "post, get, patch")
    monkeypatch.setenv("AUDIT_SKIP_PATHS", "/v1, /healthz, /metrics")

    with patch.object(settings_seed.audit_settings, "ensure_by_key") as ensure_mock:
        settings_seed.seed_audit_settings(db_session_mock)

    seeded = _calls_by_key(ensure_mock)
    assert seeded["methods"]["value_json"] == ["POST", "GET", "PATCH"]
    assert seeded["skip_paths"]["value_json"] == ["/v1", "/healthz", "/metrics"]


def test_seed_scheduler_settings_uses_celery_values(
    db_session_mock: MagicMock, clear_seed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://broker.example:6379/2")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://backend.example:6379/3")
    monkeypatch.setenv("REDIS_URL", "redis://fallback.example:6379/9")
    monkeypatch.setenv("CELERY_TIMEZONE", "Africa/Lagos")
    monkeypatch.setenv("CELERY_BEAT_MAX_LOOP_INTERVAL", "11")
    monkeypatch.setenv("CELERY_BEAT_REFRESH_SECONDS", "45")

    with patch.object(settings_seed.scheduler_settings, "ensure_by_key") as ensure_mock:
        settings_seed.seed_scheduler_settings(db_session_mock)

    seeded = _calls_by_key(ensure_mock)
    assert seeded["broker_url"]["value_text"] == "redis://broker.example:6379/2"
    assert seeded["result_backend"]["value_text"] == "redis://backend.example:6379/3"
    assert seeded["timezone"]["value_text"] == "Africa/Lagos"
    assert seeded["beat_max_loop_interval"]["value_text"] == "11"
    assert seeded["beat_refresh_seconds"]["value_text"] == "45"


def test_seed_scheduler_settings_uses_redis_and_defaults(
    db_session_mock: MagicMock, clear_seed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://shared.example:6379/6")

    with patch.object(settings_seed.scheduler_settings, "ensure_by_key") as ensure_mock:
        settings_seed.seed_scheduler_settings(db_session_mock)

    seeded = _calls_by_key(ensure_mock)
    assert seeded["broker_url"]["value_text"] == "redis://shared.example:6379/6"
    assert seeded["result_backend"]["value_text"] == "redis://shared.example:6379/6"
    assert seeded["timezone"]["value_text"] == "UTC"
    assert seeded["beat_max_loop_interval"]["value_text"] == "5"
    assert seeded["beat_refresh_seconds"]["value_text"] == "30"


def test_seed_billing_settings_defaults(db_session_mock: MagicMock, clear_seed_env: None) -> None:
    with patch.object(settings_seed.billing_settings, "ensure_by_key") as ensure_mock:
        settings_seed.seed_billing_settings(db_session_mock)

    seeded = _calls_by_key(ensure_mock)
    assert seeded["default_currency"]["value_text"] == "usd"
    assert seeded["tax_rate_percent"]["value_text"] == "0"
    assert seeded["invoice_prefix"]["value_text"] == "INV-"
    assert seeded["trial_period_days"]["value_text"] == "14"
    assert seeded["dunning_max_retries"]["value_text"] == "3"
    assert seeded["grace_period_days"]["value_text"] == "3"
    assert seeded["webhook_tolerance_seconds"]["value_text"] == "300"


def test_seed_billing_settings_env_overrides(
    db_session_mock: MagicMock, clear_seed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BILLING_DEFAULT_CURRENCY", "ngn")
    monkeypatch.setenv("BILLING_TAX_RATE_PERCENT", "8")
    monkeypatch.setenv("BILLING_INVOICE_PREFIX", "SCH-")
    monkeypatch.setenv("BILLING_TRIAL_PERIOD_DAYS", "21")
    monkeypatch.setenv("BILLING_DUNNING_MAX_RETRIES", "5")
    monkeypatch.setenv("BILLING_GRACE_PERIOD_DAYS", "10")
    monkeypatch.setenv("BILLING_WEBHOOK_TOLERANCE_SECONDS", "180")

    with patch.object(settings_seed.billing_settings, "ensure_by_key") as ensure_mock:
        settings_seed.seed_billing_settings(db_session_mock)

    seeded = _calls_by_key(ensure_mock)
    assert seeded["default_currency"]["value_text"] == "ngn"
    assert seeded["tax_rate_percent"]["value_text"] == "8"
    assert seeded["invoice_prefix"]["value_text"] == "SCH-"
    assert seeded["trial_period_days"]["value_text"] == "21"
    assert seeded["dunning_max_retries"]["value_text"] == "5"
    assert seeded["grace_period_days"]["value_text"] == "10"
    assert seeded["webhook_tolerance_seconds"]["value_text"] == "180"
