"""Unit tests for zcg.web.capabilities.brand_assets.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.web.capabilities.brand_assets import (
    MAX_BRAND_ASSET_BYTES,
    PLANE_IDENTITY_LABELS,
    apply_node_theme_mutation,
    prune_plane_brand_asset,
    store_plane_brand_asset,
    validate_brand_asset_bytes,
)
from zcg.web.http.request import UploadFile


class TestBrandAssets:
    """Verify perspective-scoped brand asset validation, isolated storage, and orphan pruning."""

    def test_validate_store_and_prune_brand_assets_across_formats_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify PNG, JPEG, WebP, and safe SVG uploads plus orphan cleanup on replace/reset."""
        # Arrange
        ws = tmp_path / "node-brand"
        ws.mkdir()
        png_up = UploadFile("brand_file", "avatar.PNG", "image/png", b"\x89PNG\r\n\x1a\n\x00")
        jpg_up = UploadFile("brand_file", "photo.jpeg", "image/jpeg", b"\xff\xd8\xff\xe0JFIF")
        webp_up = UploadFile("brand_file", "mark.webp", "image/webp", b"RIFF\x10\x00\x00\x00WEBP")
        svg_up = UploadFile(
            "brand_file",
            "logo.svg",
            "image/svg+xml",
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10"/></svg>',
        )

        # Act
        no_dir_prune = prune_plane_brand_asset(ws, plane="control_plane")
        cp_png_url = store_plane_brand_asset(ws, plane="control_plane", upload=png_up)
        cp_jpg_url = store_plane_brand_asset(ws, plane="control_plane", upload=jpg_up)
        ws_webp_url = store_plane_brand_asset(ws, plane="workspace", upload=webp_up)
        pub_svg_url = store_plane_brand_asset(ws, plane="public_portal", upload=svg_up)
        cp_removed = prune_plane_brand_asset(ws, plane="control_plane")
        all_url = store_plane_brand_asset(ws, plane="all", upload=svg_up)
        (ws / "surfaces/web/static/brand/workspace-logo.dir").mkdir(parents=True)
        ws_removed = prune_plane_brand_asset(ws, plane="workspace")
        (ws / "surfaces/web/static/brand/workspace-logo.dir").rmdir()
        all_removed = prune_plane_brand_asset(ws, plane="all")

        # Assert
        assert set(PLANE_IDENTITY_LABELS) == {"control_plane", "workspace", "public_portal"}
        assert no_dir_prune == []
        assert cp_png_url == "/static/brand/control_plane-logo.png"
        assert cp_jpg_url == "/static/brand/control_plane-logo.jpg"
        assert ws_webp_url == "/static/brand/workspace-logo.webp"
        assert pub_svg_url == "/static/brand/public_portal-logo.svg"
        assert all_url == "/static/brand/shared-logo.svg"
        assert cp_removed == ["surfaces/web/static/brand/control_plane-logo.jpg"]
        assert ws_removed == []
        assert "surfaces/web/static/brand/shared-logo.svg" in all_removed
        assert not (ws / "surfaces/web/static/brand").exists()

    def test_validate_brand_asset_bipolar_size_format_magic_and_svg_xss_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify rejection of empty, oversized, bad-magic, bad-scope, and XSS-bearing SVG files."""
        # Arrange
        max_exact_png = b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_BRAND_ASSET_BYTES - 8)
        over_png = max_exact_png + b"X"
        ws = tmp_path / "mut-ws"
        (ws / "system").mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text('{"layer_id": "mut-ws"}\n', encoding="utf-8")
        commits: list[tuple[tuple[str, ...], str]] = []

        def _fake_commit(
            _w: Path, *, rel_paths: Sequence[str], commit_message: str
        ) -> dict[str, Any]:
            commits.append((tuple(rel_paths), commit_message))
            return {"committed": True, "message": commit_message}

        # Act
        exact_ext = validate_brand_asset_bytes("exact.png", max_exact_png)
        up_res = apply_node_theme_mutation(
            ws,
            scope="control_plane",
            preset="nordic-slate",
            accent="sky",
            raw_logo="",
            default_logo_url="/static/img/logo.svg",
            brand_file=UploadFile("brand_file", "av.png", "image/png", b"\x89PNG\r\n\x1a\n1"),
            commit_changes=True,
            commit_callback=_fake_commit,
        )
        reset_plane_res = apply_node_theme_mutation(
            ws,
            scope="control_plane",
            preset="blueprint-dark",
            accent="default",
            raw_logo="",
            default_logo_url="/static/img/logo.svg",
            reset_plane=True,
        )
        plain_res = apply_node_theme_mutation(
            ws,
            scope="workspace",
            preset="high-contrast",
            accent="amber",
            raw_logo="",
            default_logo_url="/static/img/logo.svg",
        )
        all_url_res = apply_node_theme_mutation(
            ws,
            scope="all",
            preset="paper-light",
            accent="emerald",
            raw_logo="https://cdn.iso.example/logo.svg",
            default_logo_url="/static/img/logo.svg",
        )
        reset_all_res = apply_node_theme_mutation(
            ws,
            scope="all",
            preset="blueprint-dark",
            accent="default",
            raw_logo="",
            default_logo_url="/static/img/logo.svg",
            reset_plane=True,
            commit_changes=True,
            commit_callback=_fake_commit,
        )

        # Assert
        assert exact_ext == ".png"
        assert up_res["logo_url"] == "/static/brand/control_plane-logo.png"
        assert up_res["commit"] is not None
        assert reset_plane_res["logo_url"] == "/static/img/logo.svg"
        assert plain_res["logo_url"] == "/static/img/logo.svg"
        assert all_url_res["logo_url"] == "https://cdn.iso.example/logo.svg"
        assert reset_all_res["web_theme"] == {}
        assert len(commits) == 2
        with pytest.raises(ValueError, match="INVALID_BRAND_LOGO_URL"):
            apply_node_theme_mutation(
                ws,
                scope="workspace",
                preset="blueprint-dark",
                accent="default",
                raw_logo="javascript:alert(1)",
                default_logo_url="/static/img/logo.svg",
            )
        with pytest.raises(ValueError, match="BRAND_ASSET_EMPTY"):
            validate_brand_asset_bytes("empty.png", b"")
        with pytest.raises(ValueError, match="BRAND_ASSET_TOO_LARGE"):
            validate_brand_asset_bytes("huge.png", over_png)
        with pytest.raises(ValueError, match="UNSUPPORTED_BRAND_ASSET_FORMAT"):
            validate_brand_asset_bytes("archive.exe", b"MZ")
        with pytest.raises(ValueError, match="Invalid PNG"):
            validate_brand_asset_bytes("fake.png", b"not-a-png")
        with pytest.raises(ValueError, match="Invalid JPEG"):
            validate_brand_asset_bytes("fake.jpg", b"not-a-jpg")
        with pytest.raises(ValueError, match="Invalid WebP"):
            validate_brand_asset_bytes("fake.webp", b"RIFFshort")
        with pytest.raises(ValueError, match="valid UTF-8"):
            validate_brand_asset_bytes("bad.svg", b"\xff\xfe\xfd")
        with pytest.raises(ValueError, match="UNSAFE_SVG_BRAND_ASSET"):
            validate_brand_asset_bytes("noscript.svg", b"<svg><script>alert(1)</script></svg>")
        with pytest.raises(ValueError, match="UNSAFE_SVG_BRAND_ASSET"):
            validate_brand_asset_bytes("onload.svg", b'<svg onload="alert(1)"></svg>')
        with pytest.raises(ValueError, match="UNSAFE_SVG_BRAND_ASSET"):
            validate_brand_asset_bytes("not_svg.svg", b"<div>plain html</div>")
        with pytest.raises(ValueError, match="INVALID_BRAND_SCOPE"):
            prune_plane_brand_asset(tmp_path, plane="unknown_plane")
