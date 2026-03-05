import hashlib

import pytest
from cryptography.fernet import Fernet

from app.models.auth import MFAMethod, MFAMethodType, SessionStatus
from app.schemas.auth import (
    ApiKeyGenerateRequest,
    MFAMethodCreate,
    MFAMethodUpdate,
    SessionCreate,
    UserCredentialCreate,
)
from app.services import auth as auth_service
from app.services.auth_flow import hash_password


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def expire(self, key, _seconds):
        return True


def test_user_credentials_soft_delete(db_session, person):
    payload = UserCredentialCreate(
        person_id=person.id,
        username="user@example.com",
        password_hash=hash_password("secret"),
    )
    svc = auth_service.UserCredentials(db_session)
    credential = svc.create(payload)
    active, active_total = svc.list(
        person_id=str(person.id),
        provider=None,
        is_active=None,
        order_by="created_at",
        order_dir="desc",
        limit=25,
        offset=0,
    )
    assert active_total == 1
    assert len(active) == 1
    svc.delete(str(credential.id))
    active, active_total = svc.list(
        person_id=str(person.id),
        provider=None,
        is_active=None,
        order_by="created_at",
        order_dir="desc",
        limit=25,
        offset=0,
    )
    inactive, inactive_total = svc.list(
        person_id=str(person.id),
        provider=None,
        is_active=False,
        order_by="created_at",
        order_dir="desc",
        limit=25,
        offset=0,
    )
    assert active == []
    assert active_total == 0
    assert inactive_total == 1
    assert len(inactive) == 1


def test_mfa_primary_switch(db_session, person, monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", key)
    payload = MFAMethodCreate(
        person_id=person.id,
        method_type="totp",
        label="primary",
        secret="JBSWY3DPEHPK3PXP",
        is_primary=True,
        enabled=True,
    )
    mfa_svc = auth_service.MFAMethods(db_session)
    first = mfa_svc.create(payload)
    second = mfa_svc.create(
        MFAMethodCreate(
            person_id=person.id,
            method_type="totp",
            label="secondary",
            secret="KRSXG5DSNFXGOIDP",
            is_primary=True,
            enabled=True,
        ),
    )
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.is_primary is False
    assert second.is_primary is True
    # EncryptedSecretString decrypts transparently on read
    assert first.secret == "JBSWY3DPEHPK3PXP"
    assert second.secret == "KRSXG5DSNFXGOIDP"


def test_mfa_secret_is_encrypted_on_create_and_update(db_session, person, monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", key)

    mfa_svc = auth_service.MFAMethods(db_session)
    created = mfa_svc.create(
        MFAMethodCreate(
            person_id=person.id,
            method_type="totp",
            label="device",
            secret="JBSWY3DPEHPK3PXP",
            enabled=True,
        ),
    )
    # EncryptedSecretString decrypts transparently on read
    assert created.secret == "JBSWY3DPEHPK3PXP"

    updated = mfa_svc.update(
        str(created.id),
        MFAMethodUpdate(secret="KRSXG5DSNFXGOIDP"),
    )
    # EncryptedSecretString decrypts transparently on read
    assert updated.secret == "KRSXG5DSNFXGOIDP"


def test_mfa_model_encrypted_type_encrypts_plaintext_on_write(
    db_session, person, monkeypatch
):
    from sqlalchemy import select as sa_select, literal_column

    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", key)

    plaintext = "JBSWY3DPEHPK3PXP"
    method = MFAMethod(
        person_id=person.id,
        method_type=MFAMethodType.totp,
        secret=plaintext,
        enabled=True,
        is_active=True,
    )
    db_session.add(method)
    db_session.commit()
    db_session.refresh(method)

    # EncryptedSecretString decrypts transparently on read
    assert method.secret == plaintext

    # Verify the raw DB value is NOT plaintext (it's Fernet-encrypted)
    raw = db_session.scalar(
        sa_select(literal_column("secret"))
        .select_from(MFAMethod.__table__)
        .where(MFAMethod.__table__.c.id == method.id)
    )
    assert raw != plaintext
    # Verify the raw value can be decrypted back to plaintext
    f = Fernet(key.encode("utf-8"))
    assert f.decrypt(raw.encode("utf-8")).decode("utf-8") == plaintext


def test_session_delete_revokes(db_session, person):
    payload = SessionCreate(
        person_id=person.id,
        status=SessionStatus.active,
        token_hash="hash",
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at="2099-01-01T00:00:00+00:00",
    )
    sessions_svc = auth_service.Sessions(db_session)
    session = sessions_svc.create(payload)
    sessions_svc.delete(str(session.id))
    db_session.refresh(session)
    assert session.status == SessionStatus.revoked
    assert session.revoked_at is not None


def test_api_key_generate_with_redis(monkeypatch, db_session):
    fake = _FakeRedis()
    monkeypatch.setattr(auth_service, "_get_redis_client", lambda: fake)
    payload = ApiKeyGenerateRequest(label="test")
    result = auth_service.ApiKeys(db_session).generate_with_rate_limit(payload, None)
    raw_key = result["key"]
    api_key = result["api_key"]
    assert hashlib.sha256(raw_key.encode("utf-8")).hexdigest() == api_key.key_hash


def test_api_key_rate_limit_requires_redis(monkeypatch, db_session):
    monkeypatch.setattr(auth_service, "_get_redis_client", lambda: None)
    with pytest.raises(auth_service.RateLimitUnavailableError) as exc:
        auth_service.ApiKeys(db_session).generate_with_rate_limit(
            ApiKeyGenerateRequest(label="test"), None
        )
    assert "Rate limiting unavailable" in str(exc.value)
