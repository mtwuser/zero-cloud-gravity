"""Unit tests for zcg.web.static_files.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zcg.web.request import Request
from zcg.web.security import WebAppError
from zcg.web.static_files import FallbackStaticCatalog


class TestStaticFiles:
    """Verify FallbackStaticCatalog cascading overrides, built-ins, ETag 304, and 403/404 guards."""

    def test_serve_resolves_local_override_before_builtin_assets_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify search_dirs priority cascade and fallback to BUILTIN_STATIC_ASSETS."""
        # Arrange
        first_dir = tmp_path / "override_static"
        second_dir = tmp_path / "plugin_static"
        first_dir.mkdir()
        (second_dir / "css").mkdir(parents=True)
        (second_dir / "css/theme.css").write_text("body { color: cyan; }\n", "utf-8")
        catalog = FallbackStaticCatalog((first_dir, second_dir))
        req = Request({"type": "http", "method": "GET", "path": "/static/css/theme.css"})

        # Act
        resp_local = catalog.serve(req, "css/theme.css")
        resp_builtin = catalog.serve(req, "js/zcg-swap.js")

        # Assert
        assert len(catalog.search_dirs) == 2
        assert resp_local.status == 200 and b"cyan" in resp_local.body
        assert resp_builtin.status == 200 and b"ZCGSwap" in resp_builtin.body

    def test_serve_returns_304_not_modified_when_if_none_match_matches_etag_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify SHA-256 ETag conditional GET returns HTTP 304 with empty body on match."""
        # Arrange
        catalog = FallbackStaticCatalog((tmp_path,))
        req_initial = Request(
            {"type": "http", "method": "GET", "path": "/static/css/design-system.css"}
        )
        initial_resp = catalog.serve(req_initial, "css/design-system.css")
        etag = initial_resp.headers["etag"]
        req_cached = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/static/css/design-system.css",
                "headers": [(b"if-none-match", etag.encode("latin1"))],
            }
        )

        # Act
        cached_resp = catalog.serve(req_cached, "css/design-system.css")

        # Assert
        assert cached_resp.status == 304
        assert cached_resp.body == b""
        assert cached_resp.headers["etag"] == etag

    def test_serve_rejects_path_traversal_with_403_containment_violation_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify bipolar path-containment guard blocks '../' and leading '/' asset paths."""
        # Arrange
        catalog = FallbackStaticCatalog((tmp_path,))
        req = Request({"type": "http", "method": "GET", "path": "/static/secret"})

        # Act
        with pytest.raises(WebAppError) as exc_rel:
            catalog.serve(req, "../secret.txt")
        with pytest.raises(WebAppError) as exc_empty:
            catalog.serve(req, "   ")

        # Assert
        assert exc_rel.value.http_status == 403
        assert exc_empty.value.http_status == 403

    def test_serve_raises_404_when_asset_absent_from_all_layers_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify missing static asset raises HTTP 404 STATIC_ASSET_NOT_FOUND."""
        # Arrange
        catalog = FallbackStaticCatalog((tmp_path,))
        req = Request({"type": "http", "method": "GET", "path": "/static/css/missing.css"})

        # Act
        with pytest.raises(WebAppError) as exc_404:
            catalog.serve(req, "css/missing.css")

        # Assert
        assert exc_404.value.http_status == 404
