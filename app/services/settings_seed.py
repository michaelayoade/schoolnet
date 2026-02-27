import os

from sqlalchemy.orm import Session

from app.models.domain_settings import SettingValueType
from app.services.domain_settings import (
    audit_settings,
    auth_settings,
    billing_settings,
    scheduler_settings,
)
from app.services.secrets import is_openbao_ref


def _csv_list(raw: str | None, upper: bool = True) -> list[str] | None:
    if not raw:
        return None
    items = [item.strip() for item in raw.split(",") if item.strip()]
    if upper:
        return [item.upper() for item in items]
    return items


def _auth_jwt_setting_defs() -> list[tuple[str, SettingValueType, str | None]]:
    return [
        ("jwt_algorithm", SettingValueType.string, os.getenv("JWT_ALGORITHM", "HS256")),
        (
            "jwt_access_ttl_minutes",
            SettingValueType.integer,
            os.getenv("JWT_ACCESS_TTL_MINUTES", "15"),
        ),
        (
            "jwt_refresh_ttl_days",
            SettingValueType.integer,
            os.getenv("JWT_REFRESH_TTL_DAYS", "30"),
        ),
    ]


def _auth_cookie_setting_defs() -> list[tuple[str, SettingValueType, str | None]]:
    return [
        (
            "refresh_cookie_name",
            SettingValueType.string,
            os.getenv("REFRESH_COOKIE_NAME", "refresh_token"),
        ),
        (
            "refresh_cookie_secure",
            SettingValueType.boolean,
            os.getenv("REFRESH_COOKIE_SECURE", "false"),
        ),
        (
            "refresh_cookie_samesite",
            SettingValueType.string,
            os.getenv("REFRESH_COOKIE_SAMESITE", "lax"),
        ),
        (
            "refresh_cookie_domain",
            SettingValueType.string,
            os.getenv("REFRESH_COOKIE_DOMAIN"),
        ),
        (
            "refresh_cookie_path",
            SettingValueType.string,
            os.getenv("REFRESH_COOKIE_PATH", "/auth"),
        ),
    ]


def _auth_misc_setting_defs() -> list[tuple[str, SettingValueType, str | None]]:
    return [
        ("totp_issuer", SettingValueType.string, os.getenv("TOTP_ISSUER", "starter_template")),
        (
            "api_key_rate_window_seconds",
            SettingValueType.integer,
            os.getenv("API_KEY_RATE_WINDOW_SECONDS", "60"),
        ),
        ("api_key_rate_max", SettingValueType.integer, os.getenv("API_KEY_RATE_MAX", "5")),
        (
            "default_auth_provider",
            SettingValueType.string,
            os.getenv("AUTH_DEFAULT_AUTH_PROVIDER", "local"),
        ),
    ]


def seed_auth_settings(db: Session) -> None:
    setting_defs = (
        _auth_jwt_setting_defs()
        + _auth_cookie_setting_defs()
        + _auth_misc_setting_defs()
    )
    for key, value_type, value_text in setting_defs:
        auth_settings.ensure_by_key(
            db,
            key=key,
            value_type=value_type,
            value_text=value_text,
        )
    jwt_secret = os.getenv("JWT_SECRET")
    if jwt_secret and is_openbao_ref(jwt_secret):
        auth_settings.ensure_by_key(
            db,
            key="jwt_secret",
            value_type=SettingValueType.string,
            value_text=jwt_secret,
            is_secret=True,
        )
    totp_key = os.getenv("TOTP_ENCRYPTION_KEY")
    if totp_key and is_openbao_ref(totp_key):
        auth_settings.ensure_by_key(
            db,
            key="totp_encryption_key",
            value_type=SettingValueType.string,
            value_text=totp_key,
            is_secret=True,
        )


def seed_audit_settings(db: Session) -> None:
    audit_settings.ensure_by_key(
        db,
        key="enabled",
        value_type=SettingValueType.boolean,
        value_text=os.getenv("AUDIT_ENABLED", "true"),
    )
    methods_env = os.getenv("AUDIT_METHODS")
    methods_value = _csv_list(methods_env, upper=True)
    audit_settings.ensure_by_key(
        db,
        key="methods",
        value_type=SettingValueType.json,
        value_json=methods_value or ["POST", "PUT", "PATCH", "DELETE"],
    )
    skip_paths_env = os.getenv("AUDIT_SKIP_PATHS")
    skip_paths_value = _csv_list(skip_paths_env, upper=False)
    audit_settings.ensure_by_key(
        db,
        key="skip_paths",
        value_type=SettingValueType.json,
        value_json=skip_paths_value or ["/static", "/web", "/health"],
    )
    audit_settings.ensure_by_key(
        db,
        key="read_trigger_header",
        value_type=SettingValueType.string,
        value_text=os.getenv("AUDIT_READ_TRIGGER_HEADER", "x-audit-read"),
    )
    audit_settings.ensure_by_key(
        db,
        key="read_trigger_query",
        value_type=SettingValueType.string,
        value_text=os.getenv("AUDIT_READ_TRIGGER_QUERY", "audit"),
    )


def seed_scheduler_settings(db: Session) -> None:
    broker = (
        os.getenv("CELERY_BROKER_URL")
        or os.getenv("REDIS_URL")
        or "redis://localhost:6379/0"
    )
    backend = (
        os.getenv("CELERY_RESULT_BACKEND")
        or os.getenv("REDIS_URL")
        or "redis://localhost:6379/1"
    )
    scheduler_settings.ensure_by_key(
        db,
        key="broker_url",
        value_type=SettingValueType.string,
        value_text=broker,
    )
    scheduler_settings.ensure_by_key(
        db,
        key="result_backend",
        value_type=SettingValueType.string,
        value_text=backend,
    )
    scheduler_settings.ensure_by_key(
        db,
        key="timezone",
        value_type=SettingValueType.string,
        value_text=os.getenv("CELERY_TIMEZONE", "UTC"),
    )
    scheduler_settings.ensure_by_key(
        db,
        key="beat_max_loop_interval",
        value_type=SettingValueType.integer,
        value_text=os.getenv("CELERY_BEAT_MAX_LOOP_INTERVAL", "5"),
    )
    scheduler_settings.ensure_by_key(
        db,
        key="beat_refresh_seconds",
        value_type=SettingValueType.integer,
        value_text=os.getenv("CELERY_BEAT_REFRESH_SECONDS", "30"),
    )


def seed_billing_settings(db: Session) -> None:
    billing_settings.ensure_by_key(
        db,
        key="default_currency",
        value_type=SettingValueType.string,
        value_text=os.getenv("BILLING_DEFAULT_CURRENCY", "usd"),
    )
    billing_settings.ensure_by_key(
        db,
        key="tax_rate_percent",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_TAX_RATE_PERCENT", "0"),
    )
    billing_settings.ensure_by_key(
        db,
        key="invoice_prefix",
        value_type=SettingValueType.string,
        value_text=os.getenv("BILLING_INVOICE_PREFIX", "INV-"),
    )
    billing_settings.ensure_by_key(
        db,
        key="trial_period_days",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_TRIAL_PERIOD_DAYS", "14"),
    )
    billing_settings.ensure_by_key(
        db,
        key="dunning_max_retries",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_DUNNING_MAX_RETRIES", "3"),
    )
    billing_settings.ensure_by_key(
        db,
        key="grace_period_days",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_GRACE_PERIOD_DAYS", "3"),
    )
    billing_settings.ensure_by_key(
        db,
        key="webhook_tolerance_seconds",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_WEBHOOK_TOLERANCE_SECONDS", "300"),
    )
