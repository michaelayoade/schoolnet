from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.services.secrets import resolve_secret

logger = logging.getLogger(__name__)


class EncryptedSecretString(TypeDecorator[str]):
    """Encrypts values on write and decrypts on read."""

    impl = String(255)
    cache_ok = False

    @staticmethod
    def _fernet() -> Fernet:
        key = resolve_secret(os.getenv("TOTP_ENCRYPTION_KEY", ""))
        if not key:
            raise RuntimeError("TOTP_ENCRYPTION_KEY is not configured")
        return Fernet(key.encode("utf-8"))

    @staticmethod
    def _is_fernet_token(value: str) -> bool:
        """Check whether *value* is a valid Fernet token by attempting decryption."""
        try:
            EncryptedSecretString._fernet().decrypt(value.encode("utf-8"))
            return True
        except (InvalidToken, RuntimeError):
            return False

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        if value is None or value == "":
            return value
        # Already encrypted -- pass through.
        if self._is_fernet_token(value):
            return value
        return self._fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        if value is None or value == "":
            return value
        try:
            return self._fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Legacy plaintext value stored before encryption was enabled.
            logger.warning("Could not decrypt value; returning as-is (legacy plaintext?)")
            return value
        except RuntimeError:
            # Encryption key not configured -- return ciphertext so the caller
            # can decide how to handle it rather than crashing mid-query.
            logger.error("TOTP_ENCRYPTION_KEY not configured; cannot decrypt value")
            return value
