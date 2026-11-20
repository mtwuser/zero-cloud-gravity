"""Cascading multi-directory TemplateCatalog and built-in HTML/SVG asset loaders.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from http import HTTPStatus
from importlib.resources import files
from pathlib import Path
from typing import Final

from zcg.core.manifests import ensure_contained_path
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import HTML_CONTENT_TYPE, Request, WebResponse
from zcg.web.ui.template_ast import (
    MAX_TEMPLATE_INCLUDE_DEPTH,
    CompiledTemplate,
    SafeHTML,
    TemplateASTNode,
    compile_template_source,
    escape_html,
    evaluate_template_nodes,
    html_t,
    sanitize_url,
)

__all__ = [
    "BUILTIN_TEMPLATES",
    "ICON_TEMPLATE_GLOBALS",
    "MAX_TEMPLATE_INCLUDE_DEPTH",
    "MAX_TEMPLATE_INHERITANCE_DEPTH",
    "ZCG_ICONS",
    "SafeHTML",
    "TemplateCatalog",
    "escape_html",
    "html_t",
    "load_builtin_icons",
    "load_builtin_templates",
    "render_icon",
    "sanitize_url",
]

MAX_TEMPLATE_INHERITANCE_DEPTH: Final[int] = 4
_BUILTIN_TEMPLATE_NAMES: Final[tuple[str, ...]] = (
    "base.html",
    "plugin_shell.html",
    "portal_shell.html",
    "cockpit_passport.html",
)


@lru_cache(maxsize=1)
def load_builtin_icons() -> dict[str, str]:
    """Load built-in stroke SVG icon paths from zcg.web/assets/img/icons.json."""
    raw = files("zcg.web").joinpath("assets", "img", "icons.json").read_text(encoding="utf-8")
    return {str(k): str(v) for k, v in json.loads(raw).items()}


@lru_cache(maxsize=1)
def load_builtin_templates() -> dict[str, str]:
    """Load built-in HTML5 base and shell templates from zcg.web/assets/templates."""
    tpl_root = files("zcg.web").joinpath("assets", "templates")
    return {
        name: tpl_root.joinpath(name).read_text(encoding="utf-8")
        for name in _BUILTIN_TEMPLATE_NAMES
    }


ZCG_ICONS: Final[dict[str, str]] = load_builtin_icons()
BUILTIN_TEMPLATES: Final[dict[str, str]] = load_builtin_templates()


def render_icon(name: str, *, label: str = "") -> SafeHTML:
    """Render a zero-dependency 15x15 inline stroke SVG icon from ZCG_ICONS."""
    if name not in ZCG_ICONS:
        raise KeyError(f"Unknown icon: {name!r}")
    aria = f'role="img" aria-label="{escape_html(label)}"' if label else 'aria-hidden="true"'
    return SafeHTML(
        '<svg class="zcg-icon" viewBox="0 0 24 24" width="15" height="15" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round" {aria}>{ZCG_ICONS[name]}</svg>'
    )


ICON_TEMPLATE_GLOBALS: Final[dict[str, SafeHTML]] = {f"icon_{k}": render_icon(k) for k in ZCG_ICONS}


class TemplateCatalog:
    """Cascading multi-directory HTML template loader with multi-level inheritance blocks."""

    def __init__(self, search_dirs: Sequence[Path] = ()) -> None:
        self._search_dirs = tuple(d.resolve() for d in search_dirs)

    @property
    def search_dirs(self) -> tuple[Path, ...]:
        """Return resolved template search directories in priority order."""
        return self._search_dirs

    def resolve_template_source(self, name: str) -> str:
        """Resolve template source across search_dirs then BUILTIN_TEMPLATES."""
        clean = name.strip().replace("\\", "/")
        if not clean or clean.startswith("/") or ".." in Path(clean).parts:
            raise ValueError(f"PATH_CONTAINMENT_VIOLATION: invalid template name {name!r}")
        for directory in self._search_dirs:
            candidate = ensure_contained_path(directory / clean, directory)
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        if clean in BUILTIN_TEMPLATES:
            return BUILTIN_TEMPLATES[clean]
        raise KeyError(f"Template not found: {clean}")

    def _resolve_compiled_chain(
        self, name: str
    ) -> tuple[CompiledTemplate, dict[str, tuple[TemplateASTNode, ...]]]:
        cur = compile_template_source(self.resolve_template_source(name))
        seen: set[str] = {name.strip().replace("\\", "/")}
        chain: list[CompiledTemplate] = [cur]
        for _ in range(MAX_TEMPLATE_INHERITANCE_DEPTH):
            if cur.extends_name is None:
                break
            p_name = cur.extends_name.strip().replace("\\", "/")
            if p_name in seen:
                raise ValueError(f"Circular template inheritance detected: {p_name!r}")
            seen.add(p_name)
            cur = compile_template_source(self.resolve_template_source(p_name))
            chain.append(cur)
        else:
            raise ValueError(
                f"Template inheritance exceeded MAX_TEMPLATE_INHERITANCE_DEPTH="
                f"{MAX_TEMPLATE_INHERITANCE_DEPTH}"
            )
        merged: dict[str, tuple[TemplateASTNode, ...]] = {}
        for tpl in reversed(chain):
            merged = {**merged, **tpl.blocks}
        return chain[-1], merged

    def render(
        self,
        name: str,
        context: Mapping[str, object] | None = None,
        *,
        block_name: str | None = None,
    ) -> SafeHTML:
        """Render a full template (resolving extends/blocks) or an isolated named block."""
        ctx = {**ICON_TEMPLATE_GLOBALS, **(context or {})}
        root_tpl, merged_blocks = self._resolve_compiled_chain(name)
        if block_name is not None:
            if block_name not in merged_blocks:
                raise KeyError(f"Block {block_name!r} not found in template {name!r}")
            out = evaluate_template_nodes(
                merged_blocks[block_name], merged_blocks, ctx, self.resolve_template_source
            )
            return SafeHTML(out)
        out = evaluate_template_nodes(
            root_tpl.nodes, merged_blocks, ctx, self.resolve_template_source
        )
        return SafeHTML(out)

    def respond_template(
        self,
        request: Request,
        *,
        template_name: str,
        partial_name: str | None = None,
        block_name: str | None = None,
        context: Mapping[str, object] | None = None,
        status: int = int(HTTPStatus.OK),
        headers: Mapping[str, str] | None = None,
    ) -> WebResponse:
        """Render partial fragment on Z2 swap requests or full layout on page navigation."""
        hdrs = dict(headers or {})
        if request.is_partial_swap and not request.is_boosted:
            frag = (
                self.render(partial_name, context)
                if partial_name is not None
                else self.render(template_name, context, block_name=block_name)
                if block_name is not None
                else self.render(template_name, context)
            )
            return WebResponse(
                status, HTML_CONTENT_TYPE, frag.value.encode(), DeliveryChannel.SWAP_SYNC, hdrs
            )
        full = self.render(template_name, context)
        return WebResponse(
            status, HTML_CONTENT_TYPE, full.value.encode(), DeliveryChannel.ISLAND_SYNC, hdrs
        )
