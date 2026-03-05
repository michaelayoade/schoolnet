import os

from sqlalchemy.orm import Session

from app.models.domain_settings import SettingDomain, SettingValueType
from app.services.domain_settings import DomainSettings
from app.services.secrets import is_openbao_ref


def _csv_list(raw: str | None, upper: bool = True) -> list[str] | None:
    if not raw:
        return None
    items = [item.strip() for item in raw.split(",") if item.strip()]
    if upper:
        return [item.upper() for item in items]
    return items


def seed_auth_settings(db: Session) -> None:
    svc = DomainSettings(db, SettingDomain.auth)
    svc.ensure_by_key(
        key="jwt_algorithm",
        value_type=SettingValueType.string,
        value_text=os.getenv("JWT_ALGORITHM", "HS256"),
    )
    svc.ensure_by_key(
        key="jwt_access_ttl_minutes",
        value_type=SettingValueType.integer,
        value_text=os.getenv("JWT_ACCESS_TTL_MINUTES", "15"),
    )
    svc.ensure_by_key(
        key="jwt_refresh_ttl_days",
        value_type=SettingValueType.integer,
        value_text=os.getenv("JWT_REFRESH_TTL_DAYS", "30"),
    )
    svc.ensure_by_key(
        key="refresh_cookie_name",
        value_type=SettingValueType.string,
        value_text=os.getenv("REFRESH_COOKIE_NAME", "refresh_token"),
    )
    svc.ensure_by_key(
        key="refresh_cookie_secure",
        value_type=SettingValueType.boolean,
        value_text=os.getenv("REFRESH_COOKIE_SECURE", "false"),
    )
    svc.ensure_by_key(
        key="refresh_cookie_samesite",
        value_type=SettingValueType.string,
        value_text=os.getenv("REFRESH_COOKIE_SAMESITE", "lax"),
    )
    svc.ensure_by_key(
        key="refresh_cookie_domain",
        value_type=SettingValueType.string,
        value_text=os.getenv("REFRESH_COOKIE_DOMAIN"),
    )
    svc.ensure_by_key(
        key="refresh_cookie_path",
        value_type=SettingValueType.string,
        value_text=os.getenv("REFRESH_COOKIE_PATH", "/auth"),
    )
    svc.ensure_by_key(
        key="totp_issuer",
        value_type=SettingValueType.string,
        value_text=os.getenv("TOTP_ISSUER", "schoolnet"),
    )
    svc.ensure_by_key(
        key="api_key_rate_window_seconds",
        value_type=SettingValueType.integer,
        value_text=os.getenv("API_KEY_RATE_WINDOW_SECONDS", "60"),
    )
    svc.ensure_by_key(
        key="api_key_rate_max",
        value_type=SettingValueType.integer,
        value_text=os.getenv("API_KEY_RATE_MAX", "5"),
    )
    svc.ensure_by_key(
        key="default_auth_provider",
        value_type=SettingValueType.string,
        value_text=os.getenv("AUTH_DEFAULT_AUTH_PROVIDER", "local"),
    )
    jwt_secret = os.getenv("JWT_SECRET")
    if jwt_secret and is_openbao_ref(jwt_secret):
        svc.ensure_by_key(
            key="jwt_secret",
            value_type=SettingValueType.string,
            value_text=jwt_secret,
            is_secret=True,
        )
    totp_key = os.getenv("TOTP_ENCRYPTION_KEY")
    if totp_key and is_openbao_ref(totp_key):
        svc.ensure_by_key(
            key="totp_encryption_key",
            value_type=SettingValueType.string,
            value_text=totp_key,
            is_secret=True,
        )


def seed_audit_settings(db: Session) -> None:
    svc = DomainSettings(db, SettingDomain.audit)
    svc.ensure_by_key(
        key="enabled",
        value_type=SettingValueType.boolean,
        value_text=os.getenv("AUDIT_ENABLED", "true"),
    )
    methods_env = os.getenv("AUDIT_METHODS")
    methods_value = _csv_list(methods_env, upper=True)
    svc.ensure_by_key(
        key="methods",
        value_type=SettingValueType.json,
        value_json=methods_value or ["POST", "PUT", "PATCH", "DELETE"],
    )
    skip_paths_env = os.getenv("AUDIT_SKIP_PATHS")
    skip_paths_value = _csv_list(skip_paths_env, upper=False)
    svc.ensure_by_key(
        key="skip_paths",
        value_type=SettingValueType.json,
        value_json=skip_paths_value or ["/static", "/web", "/health"],
    )
    svc.ensure_by_key(
        key="read_trigger_header",
        value_type=SettingValueType.string,
        value_text=os.getenv("AUDIT_READ_TRIGGER_HEADER", "x-audit-read"),
    )
    svc.ensure_by_key(
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
    svc = DomainSettings(db, SettingDomain.scheduler)
    svc.ensure_by_key(
        key="broker_url",
        value_type=SettingValueType.string,
        value_text=broker,
    )
    svc.ensure_by_key(
        key="result_backend",
        value_type=SettingValueType.string,
        value_text=backend,
    )
    svc.ensure_by_key(
        key="timezone",
        value_type=SettingValueType.string,
        value_text=os.getenv("CELERY_TIMEZONE", "UTC"),
    )
    svc.ensure_by_key(
        key="beat_max_loop_interval",
        value_type=SettingValueType.integer,
        value_text=os.getenv("CELERY_BEAT_MAX_LOOP_INTERVAL", "5"),
    )
    svc.ensure_by_key(
        key="beat_refresh_seconds",
        value_type=SettingValueType.integer,
        value_text=os.getenv("CELERY_BEAT_REFRESH_SECONDS", "30"),
    )


def seed_billing_settings(db: Session) -> None:
    svc = DomainSettings(db, SettingDomain.billing)
    svc.ensure_by_key(
        key="default_currency",
        value_type=SettingValueType.string,
        value_text=os.getenv("BILLING_DEFAULT_CURRENCY", "usd"),
    )
    svc.ensure_by_key(
        key="tax_rate_percent",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_TAX_RATE_PERCENT", "0"),
    )
    svc.ensure_by_key(
        key="invoice_prefix",
        value_type=SettingValueType.string,
        value_text=os.getenv("BILLING_INVOICE_PREFIX", "INV-"),
    )
    svc.ensure_by_key(
        key="trial_period_days",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_TRIAL_PERIOD_DAYS", "14"),
    )
    svc.ensure_by_key(
        key="dunning_max_retries",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_DUNNING_MAX_RETRIES", "3"),
    )
    svc.ensure_by_key(
        key="grace_period_days",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_GRACE_PERIOD_DAYS", "3"),
    )
    svc.ensure_by_key(
        key="webhook_tolerance_seconds",
        value_type=SettingValueType.integer,
        value_text=os.getenv("BILLING_WEBHOOK_TOLERANCE_SECONDS", "300"),
    )
