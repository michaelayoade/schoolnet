"""Test/runtime compatibility shims for optional dependencies.

Loaded automatically by Python when present on `sys.path`.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType, SimpleNamespace


def _module_missing(name: str) -> bool:
    return importlib.util.find_spec(name) is None


def _install_datetime_utc_compat() -> None:
    import datetime as _datetime

    if not hasattr(_datetime, "UTC"):
        _datetime.UTC = _datetime.timezone.utc


def _install_prometheus_stub() -> None:
    if not _module_missing("prometheus_client"):
        return

    prometheus = ModuleType("prometheus_client")
    prometheus.CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class _Metric:
        def __init__(self, *args, **kwargs) -> None:
            self._args = args
            self._kwargs = kwargs

        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs) -> None:
            return None

        def observe(self, *args, **kwargs) -> None:
            return None

    def _generate_latest(*args, **kwargs) -> bytes:
        return b""

    prometheus.Counter = _Metric
    prometheus.Histogram = _Metric
    prometheus.generate_latest = _generate_latest
    sys.modules["prometheus_client"] = prometheus


def _install_cachetools_stub() -> None:
    if not _module_missing("cachetools"):
        return

    cachetools = ModuleType("cachetools")

    class TTLCache(dict):
        def __init__(self, maxsize: int, ttl: int, *args, **kwargs) -> None:
            super().__init__()
            self.maxsize = maxsize
            self.ttl = ttl

    cachetools.TTLCache = TTLCache
    sys.modules["cachetools"] = cachetools


def _install_redis_stub() -> None:
    if not _module_missing("redis"):
        return

    redis = ModuleType("redis")

    class RedisError(Exception):
        pass

    class ConnectionError(RedisError):
        pass

    class _Pipeline:
        def __init__(self, client) -> None:
            self.client = client

        def incr(self, *args, **kwargs):
            return self

        def expire(self, *args, **kwargs):
            return self

        def execute(self):
            return [1, True]

    class Redis:
        @classmethod
        def from_url(cls, *args, **kwargs):
            return cls()

        def ping(self) -> bool:
            return True

        def incr(self, *args, **kwargs) -> int:
            return 1

        def expire(self, *args, **kwargs) -> bool:
            return True

        def pipeline(self, *args, **kwargs):
            return _Pipeline(self)

    redis.Redis = Redis
    redis.RedisError = RedisError
    redis.exceptions = SimpleNamespace(ConnectionError=ConnectionError)
    sys.modules["redis"] = redis


def _install_multipart_stub() -> None:
    if not _module_missing("multipart"):
        return

    multipart = ModuleType("multipart")
    multipart.__version__ = "0.0.0"

    multipart_submodule = ModuleType("multipart.multipart")

    def parse_options_header(value):
        if isinstance(value, bytes):
            value = value.decode("latin-1")
        return value, {}

    multipart_submodule.parse_options_header = parse_options_header

    sys.modules["multipart"] = multipart
    sys.modules["multipart.multipart"] = multipart_submodule
    multipart.multipart = multipart_submodule


def _install_email_validator_stub() -> None:
    if not _module_missing("email_validator"):
        return

    email_validator = ModuleType("email_validator")

    class EmailNotValidError(ValueError):
        pass

    class _ValidatedEmail:
        def __init__(self, email: str) -> None:
            self.normalized = email
            self.local_part = email.split("@", 1)[0]

    def validate_email(value: str, *args, **kwargs):
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise EmailNotValidError("An email address must contain a single @")
        return _ValidatedEmail(value)

    email_validator.EmailNotValidError = EmailNotValidError
    email_validator.validate_email = validate_email
    sys.modules["email_validator"] = email_validator

    # Pydantic checks distribution metadata for email-validator>=2.
    # In this constrained test environment, patch the import helper directly.
    try:
        import pydantic.networks as pydantic_networks

        pydantic_networks.email_validator = email_validator
        pydantic_networks.import_email_validator = lambda: None
    except Exception:
        pass


_install_datetime_utc_compat()
_install_prometheus_stub()
_install_cachetools_stub()
_install_redis_stub()
_install_multipart_stub()
_install_email_validator_stub()
