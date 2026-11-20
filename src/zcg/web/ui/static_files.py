"""Cascading /static/ asset catalog backed by native package assets (importlib.resources).

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Sequence
from functools import lru_cache
from http import HTTPStatus
from importlib.resources import files
from pathlib import Path
from typing import Final

from zcg.core.manifests import ensure_contained_path
from zcg.web.auth.security import ErrorSeverity, WebAppError
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import Request, WebResponse
from zcg.web.ui.templates import BUILTIN_TEMPLATES, ZCG_ICONS

ETAG_HEX_LEN: Final[int] = 16
ENGINE_ASSET_DIGEST_HEX_LEN: Final[int] = 12

_BUILTIN_ASSET_MANIFEST: Final[tuple[tuple[str, str], ...]] = (
    ("img/logo.svg", "image/svg+xml; charset=utf-8"),
    ("css/design-system.css", "text/css; charset=utf-8"),
    ("css/layout.css", "text/css; charset=utf-8"),
    ("css/components.css", "text/css; charset=utf-8"),
    ("js/island-bus.js", "application/javascript; charset=utf-8"),
    ("js/zcg-swap.js", "application/javascript; charset=utf-8"),
    ("js/spatial-atlas.js", "application/javascript; charset=utf-8"),
    ("js/cockpit-shell.js", "application/javascript; charset=utf-8"),
    ("js/hydrator.js", "application/javascript; charset=utf-8"),
)


@lru_cache(maxsize=1)
def load_builtin_static_assets() -> dict[str, tuple[str, str]]:
    """Load built-in SVG, CSS, and ES2024 JS assets from zcg.web/assets via importlib.resources."""
    assets_root = files("zcg.web").joinpath("assets")
    return {
        rel: (ctype, assets_root.joinpath(*rel.split("/")).read_text(encoding="utf-8"))
        for rel, ctype in _BUILTIN_ASSET_MANIFEST
    }


BUILTIN_STATIC_ASSETS: Final[dict[str, tuple[str, str]]] = load_builtin_static_assets()


@lru_cache(maxsize=1)
def compute_engine_asset_digest() -> str:
    """Compute a 12-char SHA-256 Golden Core asset digest across templates, icons, and static UI."""
    hasher = hashlib.sha256()
    for name, src in sorted(BUILTIN_TEMPLATES.items()):
        hasher.update(f"tpl:{name}:{src}\n".encode())
    for icon_id, path_d in sorted(ZCG_ICONS.items()):
        hasher.update(f"icon:{icon_id}:{path_d}\n".encode())
    for rel, (ctype, text) in sorted(BUILTIN_STATIC_ASSETS.items()):
        hasher.update(f"static:{rel}:{ctype}:{text}\n".encode())
    return hasher.hexdigest()[:ENGINE_ASSET_DIGEST_HEX_LEN]


CURRENT_ENGINE_ASSET_DIGEST: Final[str] = compute_engine_asset_digest()


def _compute_etag(data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()[:ETAG_HEX_LEN]
    return f'"{digest}"'


class FallbackStaticCatalog:
    """Cascading static asset dispatcher (override_dirs -> plugin_dirs -> built-in assets)."""

    def __init__(self, search_dirs: Sequence[Path] = ()) -> None:
        self._search_dirs = tuple(d.resolve() for d in search_dirs)

    @property
    def search_dirs(self) -> tuple[Path, ...]:
        """Return resolved static search directories in priority order."""
        return self._search_dirs

    def resolve_asset(self, rel_path: str) -> tuple[str, bytes, str]:
        """Resolve (content_type, bytes, etag) or raise 403/404 WebAppError."""
        clean = rel_path.strip().lstrip("/").replace("\\", "/")
        if not clean or ".." in Path(clean).parts:
            raise WebAppError(
                f"PATH_CONTAINMENT_VIOLATION: invalid static path {rel_path!r}",
                error_code="PATH_CONTAINMENT_VIOLATION",
                http_status=int(HTTPStatus.FORBIDDEN),
            )
        for directory in self._search_dirs:
            candidate = ensure_contained_path(directory / clean, directory)
            if candidate.is_file():
                raw = candidate.read_bytes()
                mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                return mime, raw, _compute_etag(raw)
        if clean in BUILTIN_STATIC_ASSETS:
            ctype, text = BUILTIN_STATIC_ASSETS[clean]
            raw = text.encode("utf-8")
            return ctype, raw, _compute_etag(raw)
        raise WebAppError(
            f"Static asset not found: {clean}",
            error_code="STATIC_ASSET_NOT_FOUND",
            http_status=int(HTTPStatus.NOT_FOUND),
            severity=ErrorSeverity.WARNING,
        )

    def serve(self, request: Request, rel_path: str) -> WebResponse:
        """Serve static asset with SHA-256 ETag and 304 Not Modified conditional support."""
        ctype, raw, etag = self.resolve_asset(rel_path)
        hdrs = {"etag": etag, "cache-control": "public, max-age=60"}
        if request.headers.get("if-none-match") == etag:
            return WebResponse(
                int(HTTPStatus.NOT_MODIFIED), ctype, b"", DeliveryChannel.STATIC_SYNC, hdrs
            )
        return WebResponse(int(HTTPStatus.OK), ctype, raw, DeliveryChannel.STATIC_SYNC, hdrs)
