import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5434/starter_template",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    secret_key: str = os.getenv("SECRET_KEY", "")
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    db_pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    db_pool_recycle: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    # Avatar settings
    avatar_upload_dir: str = os.getenv("AVATAR_UPLOAD_DIR", "static/avatars")
    avatar_max_size_bytes: int = int(
        os.getenv("AVATAR_MAX_SIZE_BYTES", str(2 * 1024 * 1024))
    )  # 2MB
    avatar_allowed_types: str = os.getenv(
        "AVATAR_ALLOWED_TYPES", "image/jpeg,image/png,image/gif,image/webp"
    )
    avatar_url_prefix: str = os.getenv("AVATAR_URL_PREFIX", "/static/avatars")

    # Branding
    brand_name: str = os.getenv("BRAND_NAME", "Starter Template")
    brand_tagline: str = os.getenv("BRAND_TAGLINE", "FastAPI starter")
    brand_logo_url: str | None = os.getenv("BRAND_LOGO_URL") or None
    branding_upload_dir: str = os.getenv("BRANDING_UPLOAD_DIR", "static/branding")
    branding_max_size_bytes: int = int(
        os.getenv("BRANDING_MAX_SIZE_BYTES", str(5 * 1024 * 1024))
    )  # 5MB
    branding_allowed_types: str = os.getenv(
        "BRANDING_ALLOWED_TYPES",
        "image/jpeg,image/png,image/gif,image/webp,image/svg+xml,image/x-icon,image/vnd.microsoft.icon",
    )
    branding_url_prefix: str = os.getenv("BRANDING_URL_PREFIX", "/static/branding")

    # Storage
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")  # "local" or "s3"
    storage_local_dir: str = os.getenv("STORAGE_LOCAL_DIR", "static/uploads")
    storage_url_prefix: str = os.getenv("STORAGE_URL_PREFIX", "/static/uploads")
    s3_bucket: str = os.getenv("S3_BUCKET", "")
    s3_region: str = os.getenv("S3_REGION", "")
    s3_access_key: str = os.getenv("S3_ACCESS_KEY", "")
    s3_secret_key: str = os.getenv("S3_SECRET_KEY", "")
    s3_endpoint_url: str = os.getenv("S3_ENDPOINT_URL", "")

    # File uploads
    upload_max_size_bytes: int = int(
        os.getenv("UPLOAD_MAX_SIZE_BYTES", str(10 * 1024 * 1024))
    )  # 10MB
    upload_allowed_types: str = os.getenv(
        "UPLOAD_ALLOWED_TYPES",
        "image/jpeg,image/png,image/gif,image/webp,application/pdf,text/plain,text/csv",
    )

    # Paystack
    paystack_secret_key: str = os.getenv("PAYSTACK_SECRET_KEY", "")
    paystack_public_key: str = os.getenv("PAYSTACK_PUBLIC_KEY", "")

    # SchoolNet
    schoolnet_commission_rate: int = int(
        os.getenv("SCHOOLNET_COMMISSION_RATE", "1000")
    )  # basis points (10%)
    schoolnet_currency: str = os.getenv("SCHOOLNET_CURRENCY", "NGN")

    # CORS
    cors_origins: str = os.getenv("CORS_ORIGINS", "")  # Comma-separated origins


def validate_settings(s: Settings) -> list[str]:
    """Validate required settings at startup. Returns list of warnings."""
    warnings: list[str] = []
    jwt_secret = os.getenv("JWT_SECRET", "")
    totp_key = os.getenv("TOTP_ENCRYPTION_KEY", "")

    if not jwt_secret:
        warnings.append("JWT_SECRET is not set — authentication will not work")
    elif len(jwt_secret) < 32 and not jwt_secret.startswith("openbao://"):
        warnings.append(
            "JWT_SECRET is shorter than 32 characters — consider a stronger secret"
        )

    if not totp_key:
        warnings.append("TOTP_ENCRYPTION_KEY is not set — MFA will not work")

    if not s.secret_key:
        warnings.append("SECRET_KEY is not set — CSRF and session security weakened")

    if (
        "localhost" in s.database_url
        and os.getenv("ENVIRONMENT", "dev") == "production"
    ):
        warnings.append("DATABASE_URL points to localhost in production")

    return warnings


settings = Settings()
