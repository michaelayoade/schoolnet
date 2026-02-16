from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings


def _allowed_types() -> set[str]:
    raw = getattr(
        settings,
        "branding_allowed_types",
        "image/jpeg,image/png,image/gif,image/webp,image/svg+xml,image/x-icon,image/vnd.microsoft.icon",
    )
    return {item.strip() for item in raw.split(",") if item.strip()}


def _max_size() -> int:
    return int(getattr(settings, "branding_max_size_bytes", 5 * 1024 * 1024))


def _upload_dir() -> Path:
    return Path(getattr(settings, "branding_upload_dir", "static/branding"))


def _url_prefix() -> str:
    return str(getattr(settings, "branding_url_prefix", "/static/branding"))


def _extension(content_type: str | None) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "image/x-icon": ".ico",
        "image/vnd.microsoft.icon": ".ico",
    }
    return mapping.get(content_type or "", ".png")


def _validate_upload(file: UploadFile) -> None:
    if file.content_type not in _allowed_types():
        allowed = ", ".join(sorted(_allowed_types()))
        raise HTTPException(
            status_code=400, detail=f"Invalid file type. Allowed: {allowed}"
        )


async def save_branding_asset(file: UploadFile, kind: str) -> str:
    _validate_upload(file)
    base = _upload_dir()
    base.mkdir(parents=True, exist_ok=True)

    filename = f"{kind}_{uuid.uuid4().hex[:10]}{_extension(file.content_type)}"
    file_path = base / filename
    content = await file.read()

    if len(content) > _max_size():
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {_max_size() // 1024 // 1024}MB",
        )

    with open(file_path, "wb") as f:
        f.write(content)

    return f"{_url_prefix()}/{filename}"


def delete_branding_asset(asset_url: str | None) -> None:
    if not asset_url:
        return
    prefix = _url_prefix().rstrip("/")
    if not asset_url.startswith(prefix + "/"):
        return
    relative = asset_url.replace(prefix + "/", "", 1)
    file_path = _upload_dir() / relative
    if file_path.exists():
        os.remove(file_path)
