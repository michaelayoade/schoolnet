"""Tests for branding asset upload hardening."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.services import branding_assets


def _local_name(name: str) -> str:
    if "}" in name:
        return name.split("}", 1)[1]
    if ":" in name:
        return name.split(":", 1)[1]
    return name


@pytest.mark.asyncio
async def test_save_branding_asset_sniffs_png_content(tmp_path: Path) -> None:
    # PNG signature + minimal data
    png = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 32)
    file = MagicMock(spec=UploadFile)
    file.content_type = "image/png"
    file.read = AsyncMock(side_effect=[png, b""])

    with (
        patch.object(branding_assets, "_upload_dir", return_value=tmp_path),
        patch.object(branding_assets, "_url_prefix", return_value="/static/branding"),
        patch.object(branding_assets, "_max_size", return_value=1024 * 1024),
        patch.object(branding_assets, "_allowed_types", return_value={"image/png"}),
    ):
        url = await branding_assets.save_branding_asset(file, "logo")
    assert url.startswith("/static/branding/logo_")


@pytest.mark.asyncio
async def test_rejects_mismatch_declared_and_sniffed_type(tmp_path: Path) -> None:
    # PNG bytes declared as JPEG should fail.
    png = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 32)
    file = MagicMock(spec=UploadFile)
    file.content_type = "image/jpeg"
    file.read = AsyncMock(side_effect=[png, b""])

    with (
        patch.object(branding_assets, "_upload_dir", return_value=tmp_path),
        patch.object(branding_assets, "_max_size", return_value=1024 * 1024),
        patch.object(branding_assets, "_allowed_types", return_value={"image/jpeg"}),
        pytest.raises(HTTPException) as exc,
    ):
        await branding_assets.save_branding_asset(file, "logo")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tag",
    [
        "use",
        "animate",
        "animateTransform",
        "animateMotion",
        "set",
        "foreignObject",
        "script",
        "iframe",
    ],
)
async def test_rejects_blocked_svg_elements(tmp_path: Path, tag: str) -> None:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg"><{tag}>x</{tag}></svg>'.encode("utf-8")
    )
    file = MagicMock(spec=UploadFile)
    file.content_type = "image/svg+xml"
    file.read = AsyncMock(side_effect=[svg, b""])

    with (
        patch.object(branding_assets, "_upload_dir", return_value=tmp_path),
        patch.object(branding_assets, "_max_size", return_value=1024 * 1024),
        patch.object(branding_assets, "_allowed_types", return_value={"image/svg+xml"}),
        pytest.raises(HTTPException) as exc,
    ):
        await branding_assets.save_branding_asset(file, "logo")
    assert "unsafe svg" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_strips_href_and_xlink_href_from_svg(tmp_path: Path) -> None:
    svg = b"""
    <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
      <a href="javascript:alert(1)">link</a>
      <image href="#local" xlink:href="javascript:alert(2)" />
    </svg>
    """
    file = MagicMock(spec=UploadFile)
    file.content_type = "image/svg+xml"
    file.read = AsyncMock(side_effect=[svg, b""])

    with (
        patch.object(branding_assets, "_upload_dir", return_value=tmp_path),
        patch.object(branding_assets, "_url_prefix", return_value="/static/branding"),
        patch.object(branding_assets, "_max_size", return_value=1024 * 1024),
        patch.object(branding_assets, "_allowed_types", return_value={"image/svg+xml"}),
    ):
        url = await branding_assets.save_branding_asset(file, "logo")

    saved = (tmp_path / url.rsplit("/", 1)[1]).read_bytes()
    root = ET.fromstring(saved)
    for element in root.iter():
        local_names = {_local_name(name).lower() for name in element.attrib}
        assert "href" not in local_names


@pytest.mark.asyncio
async def test_strips_css_url_from_svg_style_attributes(tmp_path: Path) -> None:
    svg = b"""
    <svg xmlns="http://www.w3.org/2000/svg">
      <rect style="fill:url(javascript:alert(1));stroke:red" />
    </svg>
    """
    file = MagicMock(spec=UploadFile)
    file.content_type = "image/svg+xml"
    file.read = AsyncMock(side_effect=[svg, b""])

    with (
        patch.object(branding_assets, "_upload_dir", return_value=tmp_path),
        patch.object(branding_assets, "_url_prefix", return_value="/static/branding"),
        patch.object(branding_assets, "_max_size", return_value=1024 * 1024),
        patch.object(branding_assets, "_allowed_types", return_value={"image/svg+xml"}),
    ):
        url = await branding_assets.save_branding_asset(file, "logo")

    saved = (tmp_path / url.rsplit("/", 1)[1]).read_bytes()
    root = ET.fromstring(saved)
    style_value = next(
        (element.attrib.get("style") for element in root.iter() if "style" in element.attrib),
        "",
    )
    assert "url(" not in style_value.lower()
    assert "stroke:red" in style_value.replace(" ", "").lower()


def test_delete_branding_asset_blocks_path_traversal(tmp_path: Path) -> None:
    keep = tmp_path / "keep.txt"
    keep.write_text("do-not-delete", encoding="utf-8")

    with (
        patch.object(branding_assets, "_upload_dir", return_value=tmp_path),
        patch.object(branding_assets, "_url_prefix", return_value="/static/branding"),
    ):
        branding_assets.delete_branding_asset("/static/branding/../../keep.txt")

    assert keep.exists()
