from __future__ import annotations

from typing import Any

from starlette.datastructures import UploadFile


def as_str(value: Any) -> str | None:
    """Best-effort conversion for Starlette/FastAPI form values.

    `request.form()` values can be `str` or `UploadFile` (or `None`).
    For non-string scalars we fall back to `str(value)`.
    """
    if value is None:
        return None
    if isinstance(value, UploadFile):
        return None
    if isinstance(value, str):
        return value
    return str(value)


def as_int(value: Any) -> int | None:
    raw = as_str(value)
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None
