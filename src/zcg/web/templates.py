"""Cascading multi-directory TemplateCatalog and SafeHTML auto-escaping.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Final

from zcg.core.manifests import ensure_contained_path
from zcg.web.channels import DeliveryChannel
from zcg.web.request import HTML_CONTENT_TYPE, Request, WebResponse

MAX_TEMPLATE_INHERITANCE_DEPTH: Final[int] = 4
_EXTENDS_RE: Final[re.Pattern[str]] = re.compile(r'^\s*\{%\s*extends\s+"([^"]+)"\s*%\}\s*')
_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"\{%\s*block\s+([a-zA-Z0-9_]+)\s*%\}([\s\S]*?)\{%\s*endblock\s*%\}"
)
_VAR_RE: Final[re.Pattern[str]] = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

ZCG_ICONS: Final[dict[str, str]] = {
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "book": (
        '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
        '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'
    ),
    "branch": (
        '<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/>'
        '<circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>'
    ),
    "briefcase": (
        '<rect x="2" y="7" width="20" height="14" rx="2"/>'
        '<path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>'
    ),
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "compass": (
        '<circle cx="12" cy="12" r="10"/>'
        '<polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>'
    ),
    "cpu": (
        '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
        '<line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/>'
        '<line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/>'
    ),
    "database": (
        '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'
    ),
    "external": (
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
        '<polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>'
    ),
    "github": (
        '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61'
        "c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1"
        "S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77"
        'a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>'
    ),
    "globe": (
        '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
        '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10'
        ' 15.3 15.3 0 0 1 4-10z"/>'
    ),
    "layers": (
        '<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>'
    ),
    "lock": (
        '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
    ),
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "sparkles": '<path d="M12 3l1.9 5.8L20 10.7l-6.1 1.9L12 18.4l-1.9-5.8L4 10.7l6.1-1.9L12 3z"/>',
    "vault": (
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
    ),
}

BUILTIN_TEMPLATES: Final[dict[str, str]] = {
    "base.html": (
        '<!doctype html>\n<html lang="en" data-zcg-surface="cockpit">\n<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '  <meta name="zcg-csrf-token" content="{{ csrf_token }}">\n'
        "  <title>{{ title }}</title>\n"
        '  <link rel="stylesheet" href="/static/css/design-system.css">\n'
        '  <link rel="stylesheet" href="/static/css/layout.css">\n'
        '  <link rel="stylesheet" href="/static/css/components.css">\n'
        "  {% block extra_head %}{% endblock %}\n"
        "</head>\n<body>\n"
        '  <a class="zcg-skip-link" href="#main-content">Skip to main content</a>\n'
        '  <header class="zcg-z1-header">'
        "{% block header %}<h1>{{ title }}</h1>{% endblock %}</header>\n"
        '  <nav class="zcg-z2-nav" aria-label="Primary navigation">'
        "{% block nav %}{% endblock %}</nav>\n"
        '  <main id="main-content" class="zcg-z3-main">'
        "{% block content %}{% endblock %}{% block island %}{% endblock %}</main>\n"
        '  <footer class="zcg-z4-footer">{% block footer %}{% endblock %}</footer>\n'
        '  <script src="/static/js/island-bus.js" defer></script>\n'
        '  <script src="/static/js/zcg-swap.js" defer></script>\n'
        '  <script src="/static/js/hydrator.js" defer></script>\n'
        "</body>\n</html>\n"
    ),
    "plugin_shell.html": (
        '{% extends "base.html" %}\n'
        "{% block extra_head %}\n"
        '  <link rel="stylesheet" href="/static/css/plugin.css">\n'
        '  <script src="/static/js/islands/plugin-island.js" defer></script>\n'
        "{% endblock %}\n"
        "{% block header %}\n"
        '  <div class="zcg-plugin-header">\n'
        "    <div>\n"
        "      {{ shell_kicker_html }}\n"
        "      <h1>{{ layer_id }} — {{ panel_title }}</h1>\n"
        '      <p class="zcg-plugin-subtitle">Plugin: <code>{{ plugin_id }}</code> · '
        "Overlay: <code>{{ use_case_overlay }}</code> · "
        "Modules: <code>{{ enabled_modules_csv }}</code></p>\n"
        "    </div>\n"
        '    <div class="zcg-plugin-actions">{{ header_actions_html }}</div>\n'
        "  </div>\n"
        "{% endblock %}\n"
        "{% block nav %}\n"
        '  <div class="zcg-nav-shell">\n'
        "    {{ orientation_bar_html }}\n"
        "    {{ cross_node_nav_html }}\n"
        "    {{ nav_tabs }}\n"
        "  </div>\n"
        "{% endblock %}\n"
        "{% block content %}\n"
        '  <section id="zcg-capability-stage" aria-live="polite">'
        "{{ overview_fragment }}</section>\n"
        "{% endblock %}\n"
        "{% block island %}{% endblock %}\n"
        "{% block footer %}\n"
        '  <div class="zcg-plugin-footer">\n'
        "    <span>{{ icon_layers }} Dual-World Base: <strong>{{ plugin_id }}</strong></span>\n"
        "    <span>Local Override Root: <code>surfaces/web/templates/</code> &amp; "
        "<code>surfaces/web/static/</code></span>\n"
        "  </div>\n"
        "  {{ provenance_footer_html }}\n"
        "{% endblock %}\n"
    ),
}


@dataclass(frozen=True, slots=True)
class SafeHTML:
    """Trusted pre-escaped HTML fragment exempt from secondary escaping."""

    value: str

    def __str__(self) -> str:
        """Return raw HTML string."""
        return self.value


def escape_html(value: object) -> str:
    """Return SafeHTML verbatim or escape untrusted values via html.escape."""
    if isinstance(value, SafeHTML):
        return value.value
    return html.escape(str(value), quote=True)


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


def _interpolate_vars(source: str, context: Mapping[str, object]) -> str:
    merged_ctx = {**ICON_TEMPLATE_GLOBALS, **context}
    return _VAR_RE.sub(lambda m: escape_html(merged_ctx.get(m.group(1), "")), source)


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

    def _resolve_inheritance_chain(self, name: str) -> str:
        cur = self.resolve_template_source(name)
        seen: set[str] = {name.strip().replace("\\", "/")}
        merged_blocks: dict[str, str] = {}
        for _ in range(MAX_TEMPLATE_INHERITANCE_DEPTH):
            ext_match = _EXTENDS_RE.match(cur)
            if ext_match is None:
                break
            cur_blocks = {m.group(1): m.group(2) for m in _BLOCK_RE.finditer(cur)}
            merged_blocks = {**cur_blocks, **merged_blocks}
            parent_name = ext_match.group(1).strip().replace("\\", "/")
            if parent_name in seen:
                raise ValueError(f"Circular template inheritance detected: {parent_name!r}")
            seen.add(parent_name)
            cur = self.resolve_template_source(parent_name)
        else:
            raise ValueError(
                f"Template inheritance exceeded MAX_TEMPLATE_INHERITANCE_DEPTH="
                f"{MAX_TEMPLATE_INHERITANCE_DEPTH}"
            )
        if not merged_blocks:
            return cur
        return _BLOCK_RE.sub(
            lambda m: (
                f"{{% block {m.group(1)} %}}"
                f"{merged_blocks.get(m.group(1), m.group(2))}{{% endblock %}}"
            ),
            cur,
        )

    def render(
        self,
        name: str,
        context: Mapping[str, object] | None = None,
        *,
        block_name: str | None = None,
    ) -> SafeHTML:
        """Render a full template (resolving extends/blocks) or an isolated named block."""
        ctx = context or {}
        resolved_src = self._resolve_inheritance_chain(name)
        if block_name is not None:
            blocks = {m.group(1): m.group(2) for m in _BLOCK_RE.finditer(resolved_src)}
            if block_name not in blocks:
                raise KeyError(f"Block {block_name!r} not found in template {name!r}")
            return SafeHTML(_interpolate_vars(blocks[block_name], ctx))
        unwrapped = _BLOCK_RE.sub(lambda m: m.group(2), resolved_src)
        return SafeHTML(_interpolate_vars(unwrapped, ctx))

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
            if partial_name is not None:
                frag = self.render(partial_name, context)
            elif block_name is not None:
                frag = self.render(template_name, context, block_name=block_name)
            else:
                frag = self.render(template_name, context)
            return WebResponse(
                status, HTML_CONTENT_TYPE, frag.value.encode(), DeliveryChannel.SWAP_SYNC, hdrs
            )
        full = self.render(template_name, context)
        return WebResponse(
            status, HTML_CONTENT_TYPE, full.value.encode(), DeliveryChannel.ISLAND_SYNC, hdrs
        )
