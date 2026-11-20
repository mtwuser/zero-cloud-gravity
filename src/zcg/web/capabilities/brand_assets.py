"""Perspective-scoped brand asset validation, isolated storage, and orphan cleanup.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.core.manifests import ensure_contained_path, load_node_manifest
from zcg.web.ui.templates import sanitize_url

if TYPE_CHECKING:
    from zcg.web.http.request import UploadFile


class BrandCommitCallback(Protocol):
    """Protocol for optional path-scoped Git commit callback injected by cockpit shell."""

    def __call__(
        self, workspace_dir: Path, /, *, rel_paths: Sequence[str], commit_message: str
    ) -> dict[str, Any]:
        """Commit strictly scoped workspace paths with a Conventional Commit message."""


MAX_BRAND_ASSET_BYTES: Final[int] = 524_288
BRAND_ASSETS_REL_DIR: Final[str] = "surfaces/web/static/brand"
ALLOWED_BRAND_EXTENSIONS: Final[tuple[str, ...]] = (".svg", ".png", ".jpg", ".jpeg", ".webp")
VALID_BRAND_ASSET_SCOPES: Final[tuple[str, ...]] = (
    "control_plane",
    "workspace",
    "public_portal",
    "all",
)
PLANE_IDENTITY_LABELS: Final[dict[str, str]] = {
    "control_plane": "Control Plane (/) · Private R3",
    "workspace": "Workspace (/dashboard)",
    "public_portal": "Public Web (/portal · R0)",
}

PNG_MAGIC: Final[bytes] = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC: Final[bytes] = b"\xff\xd8\xff"
RIFF_MAGIC: Final[bytes] = b"RIFF"
WEBP_MAGIC: Final[bytes] = b"WEBP"
WEBP_HEADER_MIN_LEN: Final[int] = 12


class _SvgSafetyScanner(HTMLParser):
    """HTML/SVG tag scanner rejecting executable scripts, foreignObject, and event handlers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_svg_root: bool = False
        self.has_unsafe: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        low_tag = tag.lower()
        if low_tag == "svg":
            self.has_svg_root = True
        if low_tag in ("script", "foreignobject", "iframe", "object", "embed"):
            self.has_unsafe = True
            return
        for attr_name, raw_val in attrs:
            low_attr = attr_name.lower()
            val = (raw_val or "").strip().lower()
            if low_attr.startswith("on") or val.startswith(("javascript:", "data:text/html")):
                self.has_unsafe = True
                return


def validate_brand_asset_bytes(filename: str, data: bytes) -> str:
    """Validate uploaded brand image size, extension, magic bytes, and SVG script safety."""
    if not data:
        raise ValueError("BRAND_ASSET_EMPTY: Uploaded brand asset file is empty")
    if len(data) > MAX_BRAND_ASSET_BYTES:
        raise ValueError(
            f"BRAND_ASSET_TOO_LARGE: Asset exceeds {MAX_BRAND_ASSET_BYTES} bytes ({len(data)})"
        )
    ext = Path(filename.strip()).suffix.lower()
    if ext not in ALLOWED_BRAND_EXTENSIONS:
        raise ValueError(
            f"UNSUPPORTED_BRAND_ASSET_FORMAT: {ext!r} not in {ALLOWED_BRAND_EXTENSIONS}"
        )
    if ext == ".png":
        if not data.startswith(PNG_MAGIC):
            raise ValueError("INVALID_BRAND_ASSET_BYTES: Invalid PNG signature")
        return ".png"
    if ext in (".jpg", ".jpeg"):
        if not data.startswith(JPEG_MAGIC):
            raise ValueError("INVALID_BRAND_ASSET_BYTES: Invalid JPEG signature")
        return ".jpg"
    if ext == ".webp":
        if (
            len(data) < WEBP_HEADER_MIN_LEN
            or not data.startswith(RIFF_MAGIC)
            or data[8:12] != WEBP_MAGIC
        ):
            raise ValueError("INVALID_BRAND_ASSET_BYTES: Invalid WebP RIFF signature")
        return ".webp"
    try:
        svg_txt = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("INVALID_BRAND_ASSET_BYTES: SVG must be valid UTF-8") from exc
    scanner = _SvgSafetyScanner()
    scanner.feed(svg_txt)
    if not scanner.has_svg_root or scanner.has_unsafe:
        raise ValueError("UNSAFE_SVG_BRAND_ASSET: SVG must contain <svg> and 0 active scripts")
    return ".svg"


def _scope_slug(plane: str) -> str:
    clean = plane.strip().lower()
    if clean not in VALID_BRAND_ASSET_SCOPES:
        raise ValueError(f"INVALID_BRAND_SCOPE: {plane!r} not in {VALID_BRAND_ASSET_SCOPES}")
    return "shared" if clean == "all" else clean


def prune_plane_brand_asset(workspace_dir: Path, *, plane: str) -> list[str]:
    """Delete plane-scoped brand assets under surfaces/web/static/brand/ and prune empty dir."""
    ws = workspace_dir.resolve()
    slug = _scope_slug(plane)
    brand_dir = ensure_contained_path(ws / BRAND_ASSETS_REL_DIR, ws)
    if not brand_dir.is_dir():
        return []
    pattern = "*-logo.*" if plane.strip().lower() == "all" else f"{slug}-logo.*"
    removed: list[str] = []
    for existing in sorted(brand_dir.glob(pattern)):
        if existing.is_file():
            removed.append(str(existing.relative_to(ws)))
            existing.unlink()
    if not any(brand_dir.iterdir()):
        brand_dir.rmdir()
    return removed


def store_plane_brand_asset(workspace_dir: Path, *, plane: str, upload: UploadFile) -> str:
    """Validate and write a perspective-scoped brand asset, returning its /static/brand/ URL."""
    ws = workspace_dir.resolve()
    slug = _scope_slug(plane)
    norm_ext = validate_brand_asset_bytes(upload.filename, upload.data)
    prune_plane_brand_asset(ws, plane=slug if slug != "shared" else "all")
    rel_file = f"{BRAND_ASSETS_REL_DIR}/{slug}-logo{norm_ext}"
    dest = ensure_contained_path(ws / rel_file, ws)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(upload.data)
    return f"/static/brand/{slug}-logo{norm_ext}"


def apply_node_theme_mutation(
    workspace_dir: Path,
    *,
    scope: str,
    preset: str,
    accent: str,
    raw_logo: str,
    default_logo_url: str,
    brand_file: UploadFile | None = None,
    reset_plane: bool = False,
    commit_changes: bool = False,
    commit_callback: BrandCommitCallback | None = None,
) -> dict[str, Any]:
    """Persist perspective-scoped theme/brand upload or reset, with optional scoped Git commit."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    raw_wt = manifest.get("web_theme")
    cur_wt: dict[str, Any] = dict(raw_wt) if isinstance(raw_wt, Mapping) else {}
    planes_map = dict(cur_wt["planes"]) if isinstance(cur_wt.get("planes"), Mapping) else {}

    if reset_plane:
        prune_plane_brand_asset(ws, plane=scope)
        if scope == "all":
            cur_wt = {}
        else:
            planes_map.pop(scope, None)
            cur_wt["planes"] = planes_map
        eff_preset = str(cur_wt.get("preset") or "blueprint-dark")
        eff_accent = str(cur_wt.get("accent") or "default")
        eff_logo = str(cur_wt.get("logo_url") or default_logo_url)
    else:
        if brand_file is not None and brand_file.size > 0:
            eff_logo = store_plane_brand_asset(ws, plane=scope, upload=brand_file)
        elif raw_logo:
            safe_u = sanitize_url(raw_logo)
            if safe_u == "#":
                raise ValueError(f"INVALID_BRAND_LOGO_URL: Disallowed logo_url {raw_logo!r}")
            eff_logo = safe_u
        else:
            eff_logo = default_logo_url
        eff_preset, eff_accent = preset, accent
        entry = {"preset": eff_preset, "accent": eff_accent, "logo_url": eff_logo}
        if scope == "all":
            cur_wt = {**cur_wt, **entry, "planes": {}}
        else:
            planes_map[scope] = entry
            cur_wt["planes"] = planes_map

    if cur_wt:
        manifest["web_theme"] = cur_wt
    else:
        manifest.pop("web_theme", None)
    (ws / NODE_MANIFEST_REL_PATH).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    commit_res: dict[str, Any] | None = None
    if commit_changes and commit_callback is not None:
        scoped_paths: list[str] = [NODE_MANIFEST_REL_PATH]
        if (ws / BRAND_ASSETS_REL_DIR).exists():
            scoped_paths.append(BRAND_ASSETS_REL_DIR)
        commit_res = commit_callback(
            ws,
            rel_paths=tuple(scoped_paths),
            commit_message=f"chore(web): update {scope} brand theme",
        )
    return {
        "scope": scope,
        "preset": eff_preset,
        "accent": eff_accent,
        "logo_url": eff_logo,
        "web_theme": cur_wt,
        "commit": commit_res,
    }
