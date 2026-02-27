from __future__ import annotations

import os
import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings

_UNSAFE_SVG_ERROR = "Unsafe SVG content is not allowed"
_BLOCKED_SVG_ELEMENTS = {
    "use",
    "animate",
    "animatetransform",
    "animatemotion",
    "set",
    "foreignobject",
    "script",
    "iframe",
}
_EVENT_ATTRIBUTE_RE = re.compile(r"^on[a-z]+$", flags=re.IGNORECASE)
_JAVASCRIPT_RE = re.compile(r"javascript\s*:", flags=re.IGNORECASE)


def _xml_local_name(name: str) -> str:
    if "}" in name:
        return name.split("}", 1)[1]
    if ":" in name:
        return name.split(":", 1)[1]
    return name


def _sanitize_style_value(value: str) -> str:
    # Remove CSS url(...) tokens, handling nested parentheses in payloads.
    sanitized: list[str] = []
    index = 0
    while index < len(value):
        if value[index : index + 3].lower() == "url":
            scan = index + 3
            while scan < len(value) and value[scan].isspace():
                scan += 1
            if scan < len(value) and value[scan] == "(":
                depth = 1
                scan += 1
                quote: str | None = None
                while scan < len(value) and depth > 0:
                    char = value[scan]
                    if quote:
                        if char == quote:
                            quote = None
                        elif char == "\\" and scan + 1 < len(value):
                            scan += 1
                    else:
                        if char in {'"', "'"}:
                            quote = char
                        elif char == "(":
                            depth += 1
                        elif char == ")":
                            depth -= 1
                    scan += 1
                index = scan
                continue
        sanitized.append(value[index])
        index += 1
    return "".join(sanitized).strip()


def _allowed_types() -> set[str]:
    raw = getattr(
        settings,
        "branding_allowed_types",
        "image/jpeg,image/png,image/gif,image/webp,image/svg+xml,image/x-icon,image/vnd.microsoft.icon",
    )
    return {item.strip() for item in raw.split(",") if item.strip()}


def _normalize_mime(value: str | None) -> str:
    if value in {"image/x-icon", "image/vnd.microsoft.icon"}:
        return "image/x-icon"
    return value or ""


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


def _validate_declared_type(file: UploadFile) -> None:
    allowed = {_normalize_mime(item) for item in _allowed_types()}
    if _normalize_mime(file.content_type) not in allowed:
        allowed = ", ".join(sorted(_allowed_types()))
        raise HTTPException(
            status_code=400, detail=f"Invalid file type. Allowed: {allowed}"
        )


def _sniff_content_type(content: bytes) -> str | None:
    if content.startswith(b"\xFF\xD8\xFF"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"

    # SVG files are text/XML and do not have fixed magic bytes.
    head = content[:1024].decode("utf-8", errors="ignore").strip().lower()
    if head.startswith("<?xml"):
        if "<svg" in head:
            return "image/svg+xml"
    elif head.startswith("<svg") or "<svg" in head:
        return "image/svg+xml"
    return None


def _sanitize_svg(content: bytes) -> bytes:
    text = content.decode("utf-8", errors="ignore")
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise HTTPException(status_code=400, detail=_UNSAFE_SVG_ERROR)

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise HTTPException(status_code=400, detail=_UNSAFE_SVG_ERROR) from exc

    if _xml_local_name(root.tag).lower() != "svg":
        raise HTTPException(status_code=400, detail=_UNSAFE_SVG_ERROR)

    for element in root.iter():
        tag_name = _xml_local_name(element.tag).lower()
        if tag_name in _BLOCKED_SVG_ELEMENTS:
            raise HTTPException(status_code=400, detail=_UNSAFE_SVG_ERROR)

        for attr_name in list(element.attrib):
            local_name = _xml_local_name(attr_name).lower()

            if local_name == "href":
                del element.attrib[attr_name]
                continue

            if _EVENT_ATTRIBUTE_RE.match(local_name):
                raise HTTPException(status_code=400, detail=_UNSAFE_SVG_ERROR)

            value = element.attrib.get(attr_name, "")
            if local_name == "style":
                sanitized_style = _sanitize_style_value(value)
                if sanitized_style:
                    element.attrib[attr_name] = sanitized_style
                    value = sanitized_style
                else:
                    del element.attrib[attr_name]
                    continue

            if _JAVASCRIPT_RE.search(value):
                raise HTTPException(status_code=400, detail=_UNSAFE_SVG_ERROR)

    return ET.tostring(root, encoding="utf-8")


async def _read_limited(file: UploadFile, max_size: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    chunk_size = 64 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        size += len(chunk)
        if size > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {max_size // 1024 // 1024}MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_asset_path(asset_url: str) -> Path | None:
    prefix = _url_prefix().rstrip("/")
    if not asset_url.startswith(prefix + "/"):
        return None
    relative = asset_url.replace(prefix + "/", "", 1)
    if not relative:
        return None
    base = _upload_dir().resolve()
    target = (base / relative).resolve()
    if not str(target).startswith(str(base) + os.sep):
        return None
    return target


async def save_branding_asset(file: UploadFile, kind: str) -> str:
    _validate_declared_type(file)
    base = _upload_dir()
    base.mkdir(parents=True, exist_ok=True)

    content = await _read_limited(file, _max_size())
    sniffed_type = _sniff_content_type(content)
    if not sniffed_type:
        raise HTTPException(status_code=400, detail="Could not verify uploaded file type")
    declared_type = file.content_type or ""
    declared_normalized = _normalize_mime(declared_type)
    sniffed_normalized = _normalize_mime(sniffed_type)
    if declared_normalized and declared_normalized != sniffed_normalized:
        raise HTTPException(status_code=400, detail="Uploaded file content does not match file type")
    allowed_normalized = {_normalize_mime(item) for item in _allowed_types()}
    if sniffed_normalized not in allowed_normalized:
        raise HTTPException(status_code=400, detail="Detected file type is not allowed")
    if sniffed_type == "image/svg+xml":
        content = _sanitize_svg(content)
    if file.content_type in {"image/x-icon", "image/vnd.microsoft.icon"} and sniffed_type == "image/x-icon":
        resolved_type = file.content_type
    else:
        resolved_type = sniffed_type

    filename = f"{kind}_{uuid.uuid4().hex[:10]}{_extension(resolved_type)}"
    file_path = base / filename

    with open(file_path, "wb") as f:
        f.write(content)

    return f"{_url_prefix()}/{filename}"


def delete_branding_asset(asset_url: str | None) -> None:
    if not asset_url:
        return
    file_path = _safe_asset_path(asset_url)
    if file_path and file_path.exists():
        os.remove(file_path)
