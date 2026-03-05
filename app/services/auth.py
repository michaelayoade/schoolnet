import hashlib
import logging
import os
import secrets
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar, cast

import redis
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import (
    ApiKey,
    AuthProvider,
    MFAMethod,
    MFAMethodType,
    SessionStatus,
    UserCredential,
)
from app.models.auth import (
    Session as AuthSession,
)
from app.models.domain_settings import DomainSetting, SettingDomain
from app.models.person import Person
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyGenerateRequest,
    ApiKeyUpdate,
    MFAMethodCreate,
    MFAMethodUpdate,
    SessionCreate,
    SessionUpdate,
    UserCredentialCreate,
    UserCredentialUpdate,
)
from app.services import settings_spec
from app.services.auth_flow import _encrypt_secret
from app.services.common import coerce_uuid
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class PersonNotFoundError(ValueError):
    pass


class UserCredentialNotFoundError(ValueError):
    pass


class MFAMethodNotFoundError(ValueError):
    pass


class SessionNotFoundError(ValueError):
    pass


class ApiKeyNotFoundError(ValueError):
    pass


class PrimaryMFAMethodConflictError(ValueError):
    pass


class RateLimitUnavailableError(ValueError):
    pass


class RateLimitExceededError(ValueError):
    pass


EnumT = TypeVar("EnumT", bound=Enum)


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


_API_KEY_WINDOW_SECONDS = 60
_API_KEY_MAX_PER_WINDOW = 5
_REDIS_CLIENT: redis.Redis | None = None


def _parse_enum(value: str | None, enum_cls: type[EnumT], label: str) -> EnumT | None:
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {label}") from exc


def _apply_ordering(stmt, order_by: str, order_dir: str, allowed_columns: dict[str, Any]):
    column = allowed_columns.get(order_by)
    if column is None:
        raise ValueError(
            f"Invalid order_by. Allowed: {', '.join(sorted(allowed_columns))}"
        )
    if order_dir == "desc":
        return stmt.order_by(column.desc())
    return stmt.order_by(column.asc())


def _auth_setting(db: Session, key: str) -> str | None:
    stmt = (
        select(DomainSetting)
        .where(DomainSetting.domain == SettingDomain.auth)
        .where(DomainSetting.key == key)
        .where(DomainSetting.is_active.is_(True))
        .limit(1)
    )
    setting = db.scalar(stmt)
    if not setting:
        return None
    if setting.value_text is not None:
        return setting.value_text
    if setting.value_json is not None:
        return str(setting.value_json)
    return None


def _auth_int_setting(db: Session, key: str, default: int) -> int:
    value = _auth_setting(db, key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_redis_client() -> redis.Redis | None:
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        _REDIS_CLIENT = client
        return client
    except redis.RedisError:
        return None


def _ensure_person(db: Session, person_id: str):
    person = db.get(Person, coerce_uuid(person_id))
    if not person:
        raise PersonNotFoundError("Person not found")


class UserCredentials(ListResponseMixin):
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: UserCredentialCreate):
        _ensure_person(self.db, str(payload.person_id))
        data = payload.model_dump()
        fields_set = payload.model_fields_set
        if "provider" not in fields_set:
            default_provider = settings_spec.resolve_value(
                self.db, SettingDomain.auth, "default_auth_provider"
            )
            if default_provider:
                data["provider"] = _parse_enum(
                    cast(str, default_provider), AuthProvider, "provider"
                )
        credential = UserCredential(**data)
        self.db.add(credential)
        self.db.flush()
        self.db.refresh(credential)
        return credential

    def get(self, credential_id: str):
        credential = self.db.get(UserCredential, coerce_uuid(credential_id))
        if not credential:
            raise UserCredentialNotFoundError("User credential not found")
        return credential

    def list(
        self,
        person_id: str | None,
        provider: str | None,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(UserCredential)
        if person_id:
            stmt = stmt.where(UserCredential.person_id == coerce_uuid(person_id))
        if provider:
            stmt = stmt.where(
                UserCredential.provider
                == _parse_enum(provider, AuthProvider, "provider")
            )
        if is_active is None:
            stmt = stmt.where(UserCredential.is_active.is_(True))
        else:
            stmt = stmt.where(UserCredential.is_active == is_active)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = _apply_ordering(
            stmt,
            order_by,
            order_dir,
            {
                "created_at": UserCredential.created_at,
                "username": UserCredential.username,
                "last_login_at": UserCredential.last_login_at,
            },
        )
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def update(self, credential_id: str, payload: UserCredentialUpdate):
        credential = self.db.get(UserCredential, coerce_uuid(credential_id))
        if not credential:
            raise UserCredentialNotFoundError("User credential not found")
        data = payload.model_dump(exclude_unset=True)
        if "person_id" in data:
            _ensure_person(self.db, str(data["person_id"]))
        for key, value in data.items():
            setattr(credential, key, value)
        self.db.flush()
        self.db.refresh(credential)
        return credential

    def delete(self, credential_id: str):
        credential = self.db.get(UserCredential, coerce_uuid(credential_id))
        if not credential:
            raise UserCredentialNotFoundError("User credential not found")
        credential.is_active = False
        self.db.flush()


class MFAMethods(ListResponseMixin):
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: MFAMethodCreate):
        _ensure_person(self.db, str(payload.person_id))
        if payload.is_primary:
            self.db.execute(
                update(MFAMethod)
                .where(MFAMethod.person_id == payload.person_id)
                .where(MFAMethod.is_primary.is_(True))
                .values(is_primary=False)
            )
        data = payload.model_dump()
        if data.get("secret"):
            data["secret"] = _encrypt_secret(self.db, cast(str, data["secret"]))
        method = MFAMethod(**data)
        self.db.add(method)
        try:
            self.db.flush()
        except IntegrityError as exc:
            raise PrimaryMFAMethodConflictError(
                "Primary MFA method already exists for this user"
            ) from exc
        self.db.refresh(method)
        return method

    def get(self, method_id: str):
        method = self.db.get(MFAMethod, coerce_uuid(method_id))
        if not method:
            raise MFAMethodNotFoundError("MFA method not found")
        return method

    def list(
        self,
        person_id: str | None,
        method_type: str | None,
        is_primary: bool | None,
        enabled: bool | None,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(MFAMethod)
        if person_id:
            stmt = stmt.where(MFAMethod.person_id == coerce_uuid(person_id))
        if method_type:
            stmt = stmt.where(
                MFAMethod.method_type
                == _parse_enum(method_type, MFAMethodType, "method_type")
            )
        if is_primary is not None:
            stmt = stmt.where(MFAMethod.is_primary == is_primary)
        if enabled is not None:
            stmt = stmt.where(MFAMethod.enabled == enabled)
        if is_active is None:
            stmt = stmt.where(MFAMethod.is_active.is_(True))
        else:
            stmt = stmt.where(MFAMethod.is_active == is_active)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = _apply_ordering(
            stmt,
            order_by,
            order_dir,
            {
                "created_at": MFAMethod.created_at,
                "method_type": MFAMethod.method_type,
                "is_primary": MFAMethod.is_primary,
            },
        )
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def update(self, method_id: str, payload: MFAMethodUpdate):
        method = self.db.get(MFAMethod, coerce_uuid(method_id))
        if not method:
            raise MFAMethodNotFoundError("MFA method not found")
        data = payload.model_dump(exclude_unset=True)
        if "person_id" in data:
            _ensure_person(self.db, str(data["person_id"]))
        if data.get("secret"):
            data["secret"] = _encrypt_secret(self.db, cast(str, data["secret"]))
        if data.get("is_primary"):
            person_id = data.get("person_id", method.person_id)
            self.db.execute(
                update(MFAMethod)
                .where(MFAMethod.person_id == person_id)
                .where(MFAMethod.id != method.id)
                .where(MFAMethod.is_primary.is_(True))
                .values(is_primary=False)
            )
        for key, value in data.items():
            setattr(method, key, value)
        try:
            self.db.flush()
        except IntegrityError as exc:
            raise PrimaryMFAMethodConflictError(
                "Primary MFA method already exists for this user"
            ) from exc
        self.db.refresh(method)
        return method

    def delete(self, method_id: str):
        method = self.db.get(MFAMethod, coerce_uuid(method_id))
        if not method:
            raise MFAMethodNotFoundError("MFA method not found")
        method.is_active = False
        method.enabled = False
        method.is_primary = False
        self.db.flush()


class Sessions(ListResponseMixin):
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: SessionCreate):
        _ensure_person(self.db, str(payload.person_id))
        data = payload.model_dump()
        session = AuthSession(**data)
        self.db.add(session)
        self.db.flush()
        self.db.refresh(session)
        return session

    def get(self, session_id: str):
        session = self.db.get(AuthSession, coerce_uuid(session_id))
        if not session:
            raise SessionNotFoundError("Session not found")
        return session

    def list(
        self,
        person_id: str | None,
        status: str | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(AuthSession)
        if person_id:
            stmt = stmt.where(AuthSession.person_id == coerce_uuid(person_id))
        if status:
            stmt = stmt.where(
                AuthSession.status == _parse_enum(status, SessionStatus, "status")
            )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = _apply_ordering(
            stmt,
            order_by,
            order_dir,
            {
                "created_at": AuthSession.created_at,
                "last_seen_at": AuthSession.last_seen_at,
                "status": AuthSession.status,
            },
        )
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def update(self, session_id: str, payload: SessionUpdate):
        session = self.db.get(AuthSession, coerce_uuid(session_id))
        if not session:
            raise SessionNotFoundError("Session not found")
        data = payload.model_dump(exclude_unset=True)
        if "person_id" in data:
            _ensure_person(self.db, str(data["person_id"]))
        for key, value in data.items():
            setattr(session, key, value)
        self.db.flush()
        self.db.refresh(session)
        return session

    def delete(self, session_id: str):
        session = self.db.get(AuthSession, coerce_uuid(session_id))
        if not session:
            raise SessionNotFoundError("Session not found")
        session.status = SessionStatus.revoked
        session.revoked_at = datetime.now(UTC)
        self.db.flush()


class ApiKeys(ListResponseMixin):
    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_with_rate_limit(
        self, payload: ApiKeyGenerateRequest, request: Any | None
    ):
        client_ip = "unknown"
        if request is not None and request.client:
            client_ip = request.client.host
        window_seconds = _auth_int_setting(
            self.db, "api_key_rate_window_seconds", _API_KEY_WINDOW_SECONDS
        )
        max_per_window = _auth_int_setting(
            self.db, "api_key_rate_max", _API_KEY_MAX_PER_WINDOW
        )
        redis_client = _get_redis_client()
        if not redis_client:
            raise RateLimitUnavailableError("Rate limiting unavailable (Redis required)")
        window = max(window_seconds, 1)
        key = f"api_key_rl:{client_ip}:{int(time.time() // window)}"
        try:
            count = cast(int, redis_client.incr(key))
            if count == 1:
                redis_client.expire(key, window)
            if count > max(max_per_window, 1):
                raise RateLimitExceededError("Rate limit exceeded")
        except redis.RedisError as exc:
            raise RateLimitUnavailableError(
                "Rate limiting unavailable (Redis error)"
            ) from exc
        api_key, raw_key = self.generate(payload)
        return {"key": raw_key, "api_key": api_key}

    def generate(self, payload: ApiKeyGenerateRequest):
        raw_key = secrets.token_urlsafe(32)
        data = payload.model_dump()
        data["key_hash"] = hash_api_key(raw_key)
        data.setdefault("is_active", True)
        if data.get("person_id"):
            _ensure_person(self.db, str(data["person_id"]))
        api_key = ApiKey(**data)
        self.db.add(api_key)
        self.db.flush()
        self.db.refresh(api_key)
        return api_key, raw_key

    def create(self, payload: ApiKeyCreate):
        if payload.person_id:
            _ensure_person(self.db, str(payload.person_id))
        data = payload.model_dump()
        data["key_hash"] = hash_api_key(data["key_hash"])
        api_key = ApiKey(**data)
        self.db.add(api_key)
        self.db.flush()
        self.db.refresh(api_key)
        return api_key

    def get(self, key_id: str):
        api_key = self.db.get(ApiKey, coerce_uuid(key_id))
        if not api_key:
            raise ApiKeyNotFoundError("API key not found")
        return api_key

    def list(
        self,
        person_id: str | None,
        is_active: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(ApiKey)
        if person_id:
            stmt = stmt.where(ApiKey.person_id == coerce_uuid(person_id))
        if is_active is None:
            stmt = stmt.where(ApiKey.is_active.is_(True))
        else:
            stmt = stmt.where(ApiKey.is_active == is_active)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = _apply_ordering(
            stmt,
            order_by,
            order_dir,
            {"created_at": ApiKey.created_at, "label": ApiKey.label},
        )
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def update(self, key_id: str, payload: ApiKeyUpdate):
        api_key = self.db.get(ApiKey, coerce_uuid(key_id))
        if not api_key:
            raise ApiKeyNotFoundError("API key not found")
        data = payload.model_dump(exclude_unset=True)
        if "person_id" in data and data["person_id"] is not None:
            _ensure_person(self.db, str(data["person_id"]))
        if "key_hash" in data and data["key_hash"]:
            data["key_hash"] = hash_api_key(data["key_hash"])
        for key, value in data.items():
            setattr(api_key, key, value)
        self.db.flush()
        self.db.refresh(api_key)
        return api_key

    def delete(self, key_id: str):
        api_key = self.db.get(ApiKey, coerce_uuid(key_id))
        if not api_key:
            raise ApiKeyNotFoundError("API key not found")
        api_key.is_active = False
        api_key.revoked_at = datetime.now(UTC)
        self.db.flush()

    def revoke(self, key_id: str):
        self.delete(key_id)
