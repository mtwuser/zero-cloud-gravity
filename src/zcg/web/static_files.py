"""Cascading /static/ asset catalog and zero-build ES2024 client runtimes.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Sequence
from http import HTTPStatus
from pathlib import Path
from typing import Final

from zcg.core.manifests import ensure_contained_path
from zcg.web.channels import DeliveryChannel
from zcg.web.request import Request, WebResponse
from zcg.web.security import ErrorSeverity, WebAppError

ETAG_HEX_LEN: Final[int] = 16

ZCG_BRAND_LOGO_SVG: Final[str] = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
    '<rect x="3" y="3" width="58" height="58" rx="14" fill="#0f172a" '
    'stroke="#38bdf8" stroke-width="2.5"/>'
    '<polygon points="32,10 51,21 51,43 32,54 13,43 13,21" '
    'fill="#1e293b" stroke="#38bdf8" stroke-width="2"/>'
    '<ellipse cx="32" cy="32" rx="16" ry="7" transform="rotate(-28 32 32)" '
    'stroke="#38bdf8" stroke-width="2" stroke-opacity="0.85"/>'
    '<circle cx="32" cy="32" r="5.5" fill="#22c55e" stroke="#f8fafc" stroke-width="1.6"/>'
    "</svg>\n"
)

BUILTIN_STATIC_ASSETS: Final[dict[str, tuple[str, str]]] = {
    "img/logo.svg": ("image/svg+xml; charset=utf-8", ZCG_BRAND_LOGO_SVG),
    "css/design-system.css": (
        "text/css; charset=utf-8",
        ":root {\n"
        "  --zcg-bg: #0f172a;\n"
        "  --zcg-surface: #1e293b;\n"
        "  --zcg-surface-alt: #334155;\n"
        "  --zcg-border: #475569;\n"
        "  --zcg-text: #f8fafc;\n"
        "  --zcg-muted: #94a3b8;\n"
        "  --zcg-accent: #38bdf8;\n"
        "  --zcg-ok: #22c55e;\n"
        "  --zcg-warn: #f59e0b;\n"
        "  --zcg-crit: #ef4444;\n"
        "  --zcg-radius: 0.65rem;\n"
        "  --zcg-font: system-ui, -apple-system, sans-serif;\n"
        "}\n"
        "*, *::before, *::after { box-sizing: border-box; }\n"
        "body { margin: 0; font-family: var(--zcg-font); background: var(--zcg-bg);"
        " color: var(--zcg-text); line-height: 1.5; }\n"
        ":focus-visible { outline: 2px solid var(--zcg-accent); outline-offset: 2px; }\n"
        ".zcg-sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden;"
        " clip: rect(0, 0, 0, 0); }\n",
    ),
    "css/layout.css": (
        "text/css; charset=utf-8",
        '[data-zcg-surface="cockpit"] { min-height: 100vh; display: grid;'
        " grid-template-rows: auto auto 1fr auto; }\n"
        ".zcg-skip-link { position: absolute; left: -9999px; background: var(--zcg-accent);"
        " color: #000; padding: 0.5rem 1rem; }\n"
        ".zcg-skip-link:focus { left: 1rem; top: 1rem; z-index: 50; }\n"
        ".zcg-z1-header, .zcg-z2-nav, .zcg-z4-footer { padding: 0.85rem 1.5rem;"
        " background: var(--zcg-surface); border-bottom: 1px solid var(--zcg-border); }\n"
        ".zcg-z3-main { padding: 1.5rem; max-width: 84rem; width: 100%; margin: 0 auto; }\n"
        ".zcg-grid { display: grid; gap: 1rem;"
        " grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); }\n",
    ),
    "css/components.css": (
        "text/css; charset=utf-8",
        ".zcg-icon { display: inline-block; vertical-align: -0.18em; flex-shrink: 0; }\n"
        ".zcg-brand { display: flex; align-items: center; gap: 0.75rem; }\n"
        ".zcg-brand-logo { width: 2.25rem; height: 2.25rem; flex-shrink: 0; display: block; }\n"
        ".zcg-card { background: var(--zcg-surface); border: 1px solid var(--zcg-border);"
        " border-radius: var(--zcg-radius); padding: 1rem 1.2rem; margin-bottom: 1rem; }\n"
        ".zcg-card__header { display: flex; justify-content: space-between;"
        " align-items: center; gap: 0.5rem; }\n"
        ".zcg-badge { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.78rem;"
        " padding: 0.18rem 0.6rem; border-radius: 999px; background: var(--zcg-surface-alt);"
        " border: 1px solid rgba(148, 163, 184, 0.2); text-decoration: none;"
        " color: var(--zcg-text); }\n"
        ".zcg-btn { display: inline-flex; align-items: center; gap: 0.4rem;"
        " background: var(--zcg-accent); color: #0f172a; font-weight: 600; font-size: 0.85rem;"
        " border: 1px solid transparent; border-radius: 0.45rem; padding: 0.46rem 0.92rem;"
        " cursor: pointer; text-decoration: none; transition: filter 0.15s ease; }\n"
        ".zcg-btn:hover { filter: brightness(1.08); }\n"
        ".zcg-btn--secondary { display: inline-flex; align-items: center; gap: 0.38rem;"
        " background: var(--zcg-surface-alt); color: var(--zcg-text); font-weight: 500;"
        " font-size: 0.83rem; border: 1px solid var(--zcg-border); border-radius: 0.45rem;"
        " padding: 0.42rem 0.82rem; cursor: pointer; text-decoration: none;"
        " transition: border-color 0.15s ease, color 0.15s ease; }\n"
        ".zcg-btn--secondary:hover { border-color: var(--zcg-accent); color: var(--zcg-accent); }\n"
        ".zcg-btn--sm { font-size: 0.78rem; padding: 0.28rem 0.65rem; }\n"
        ".zcg-chip-list { display: flex; flex-wrap: wrap; gap: 0.42rem; margin: 0.45rem 0; }\n"
        ".zcg-chip { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.79rem;"
        " padding: 0.22rem 0.65rem; border-radius: 999px; background: var(--zcg-bg);"
        " border: 1px solid var(--zcg-border); color: var(--zcg-text); }\n"
        ".zcg-chip--active { border-color: var(--zcg-ok); background: rgba(34, 197, 94, 0.12); }\n"
        ".zcg-chip--created { border-color: var(--zcg-accent); }\n"
        ".zcg-chip--blueprint { border-style: dashed; color: var(--zcg-muted); }\n"
        ".zcg-knowledge-list { display: flex; flex-direction: column; gap: 0.45rem;"
        " margin: 0.5rem 0 0.7rem; }\n"
        ".zcg-knowledge-row { display: flex; flex-wrap: wrap; justify-content: space-between;"
        " align-items: center; gap: 0.6rem; padding: 0.45rem 0.75rem;"
        " background: var(--zcg-bg); border: 1px solid var(--zcg-border);"
        " border-radius: 0.45rem; font-size: 0.84rem; }\n"
        ".zcg-table { width: 100%; border-collapse: collapse; }\n"
        ".zcg-table th, .zcg-table td { text-align: left; padding: 0.55rem 0.75rem;"
        " border-bottom: 1px solid var(--zcg-border); }\n"
        ".zcg-tabs { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }\n"
        ".zcg-tab { display: inline-flex; align-items: center; gap: 0.35rem;"
        " background: transparent; color: var(--zcg-text); font-size: 0.84rem;"
        " border: 1px solid var(--zcg-border); border-radius: 0.45rem;"
        " padding: 0.4rem 0.85rem; cursor: pointer; text-decoration: none; }\n"
        ".zcg-tab.is-active { border-color: var(--zcg-accent); color: var(--zcg-accent);"
        " background: rgba(56, 189, 248, 0.1); font-weight: 600; }\n"
        ".zcg-field { display: flex; flex-direction: column; gap: 0.3rem;"
        " margin-bottom: 0.75rem; }\n"
        ".zcg-field input, .zcg-field textarea, .zcg-field select {"
        " background: var(--zcg-bg); color: var(--zcg-text);"
        " border: 1px solid var(--zcg-border); border-radius: 0.4rem; padding: 0.45rem; }\n"
        ".zcg-alert { padding: 0.75rem 1rem; border-radius: 0.45rem;"
        " border-left: 4px solid var(--zcg-accent); background: var(--zcg-surface-alt); }\n"
        ".zcg-alert--warning { border-left-color: var(--zcg-warn); }\n"
        ".zcg-alert--error, .zcg-alert--critical { border-left-color: var(--zcg-crit); }\n"
        ".zcg-kpi { background: var(--zcg-surface); border: 1px solid var(--zcg-border);"
        " border-radius: var(--zcg-radius); padding: 0.75rem 1rem;"
        " display: flex; flex-direction: column; }\n"
        ".zcg-plugin-header, .zcg-plugin-footer { display: flex; justify-content: space-between;"
        " align-items: center; flex-wrap: wrap; gap: 0.75rem; }\n"
        ".zcg-plugin-header h1 { margin: 0.3rem 0 0.2rem; font-size: 1.35rem; }\n"
        ".zcg-plugin-subtitle { margin: 0; color: var(--zcg-muted); font-size: 0.86rem; }\n"
        ".zcg-plugin-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }\n"
        ".zcg-plugin-island { margin-top: 1.25rem; }\n"
        ".zcg-nav-shell { display: flex; flex-direction: column; gap: 0.65rem; }\n"
        ".zcg-compass { display: flex; flex-wrap: wrap; justify-content: space-between;"
        " align-items: center; gap: 0.6rem; padding: 0.55rem 0.9rem;"
        " border: 1px solid var(--zcg-border); border-radius: 0.5rem;"
        " background: var(--zcg-surface-alt); font-size: 0.84rem; }\n"
        ".zcg-node-nav { display: flex; flex-wrap: wrap; align-items: center; gap: 0.45rem;"
        " font-size: 0.82rem; }\n"
        ".zcg-provenance-footer { display: flex; flex-wrap: wrap; align-items: center;"
        " gap: 0.5rem; margin-top: 0.55rem; padding-top: 0.55rem;"
        " border-top: 1px solid var(--zcg-border); font-size: 0.78rem; color: var(--zcg-muted); }\n"
        ".zcg-provenance-footer a { display: inline-flex; align-items: center; gap: 0.28rem;"
        " color: var(--zcg-accent); text-decoration: none; }\n",
    ),
    "js/island-bus.js": (
        "application/javascript; charset=utf-8",
        "(() => {\n"
        "  const subs = new Map();\n"
        "  const last = new Map();\n"
        "  window.IslandBus = {\n"
        "    emit(topic, payload) {\n"
        "      last.set(topic, payload);\n"
        "      for (const fn of subs.get(topic) || []) fn(payload);\n"
        "    },\n"
        "    on(topic, fn, { replay = true } = {}) {\n"
        "      if (!subs.has(topic)) subs.set(topic, new Set());\n"
        "      subs.get(topic).add(fn);\n"
        "      if (replay && last.has(topic)) fn(last.get(topic));\n"
        "      return () => subs.get(topic)?.delete(fn);\n"
        "    },\n"
        "    getLast(topic) { return last.get(topic); },\n"
        "  };\n"
        "})();\n",
    ),
    "js/zcg-swap.js": (
        "application/javascript; charset=utf-8",
        "(() => {\n"
        "  const csrf = () =>\n"
        "    document.querySelector('meta[name=\"zcg-csrf-token\"]')?.content || '';\n"
        "  async function swapFetch(\n"
        "    url, { method = 'GET', body = null, targetSel = null } = {}\n"
        "  ) {\n"
        "    const headers = { 'hx-request': 'true' };\n"
        "    if (targetSel) headers['hx-target'] = targetSel;\n"
        "    if (method !== 'GET' && csrf()) headers['x-zcg-csrf-token'] = csrf();\n"
        "    const res = await fetch(url, { method, headers, body });\n"
        "    const html = await res.text();\n"
        "    const effSel = res.headers.get('hx-retarget') || targetSel;\n"
        "    const mode = res.headers.get('hx-reswap') || 'innerHTML';\n"
        "    const el = effSel ? document.querySelector(effSel) : null;\n"
        "    if (el) {\n"
        "      if (mode === 'outerHTML') el.outerHTML = html;\n"
        "      else el.innerHTML = html;\n"
        "      bindPolling(document);\n"
        "    }\n"
        "    const trig = res.headers.get('hx-trigger');\n"
        "    if (trig) window.IslandBus?.emit(trig, { status: res.status });\n"
        "    return res;\n"
        "  }\n"
        "  document.addEventListener('click', (ev) => {\n"
        "    const openBtn = ev.target.closest('[data-zcg-modal-open]');\n"
        "    if (openBtn) {\n"
        "      document.getElementById(openBtn.dataset.zcgModalOpen)?.showModal();\n"
        "      return;\n"
        "    }\n"
        "    const closeBtn = ev.target.closest('[data-zcg-modal-close]');\n"
        "    if (closeBtn) {\n"
        "      document.getElementById(closeBtn.dataset.zcgModalClose)?.close();\n"
        "      return;\n"
        "    }\n"
        "    const sel = 'button[data-zcg-get],a[data-zcg-get],[data-zcg-delete]';\n"
        "    const el = ev.target.closest(sel);\n"
        "    if (!el) return;\n"
        "    ev.preventDefault();\n"
        "    if (el.getAttribute('role') === 'tab') {\n"
        "      el.parentElement?.querySelectorAll('[role=\"tab\"]').forEach((t) => {\n"
        "        t.classList.toggle('is-active', t === el);\n"
        "        t.setAttribute('aria-selected', String(t === el));\n"
        "      });\n"
        "      const ind = document.querySelector('[data-zcg-view-indicator]');\n"
        "      if (ind) ind.textContent = `View: ${(el.textContent || '').trim()}`;\n"
        "    }\n"
        "    const method = el.dataset.zcgDelete ? 'DELETE' : 'GET';\n"
        "    const url = el.dataset.zcgDelete || el.dataset.zcgGet;\n"
        "    swapFetch(url, { method, targetSel: el.dataset.zcgTarget });\n"
        "  });\n"
        "  document.addEventListener('submit', (ev) => {\n"
        "    const form = ev.target.closest('form[data-zcg-get],form[data-zcg-post]');\n"
        "    if (!form) return;\n"
        "    ev.preventDefault();\n"
        "    const fd = new FormData(form);\n"
        "    if (form.dataset.zcgGet) {\n"
        "      const qs = new URLSearchParams(fd).toString();\n"
        "      const base = form.dataset.zcgGet;\n"
        "      const url = qs ? `${base}${base.includes('?') ? '&' : '?'}${qs}` : base;\n"
        "      swapFetch(url, { method: 'GET', targetSel: form.dataset.zcgTarget });\n"
        "    } else {\n"
        "      const isMulti = (form.enctype || '').includes('multipart/form-data');\n"
        "      const body = isMulti ? fd : new URLSearchParams(fd);\n"
        "      const opts = { method: 'POST', body, targetSel: form.dataset.zcgTarget };\n"
        "      swapFetch(form.dataset.zcgPost, opts);\n"
        "    }\n"
        "  });\n"
        "  function bindPolling(root) {\n"
        "    root.querySelectorAll('[data-zcg-poll]').forEach((node) => {\n"
        "      if (node.dataset.zcgPollActive) return;\n"
        "      node.dataset.zcgPollActive = '1';\n"
        "      const iv = Math.max(250, Number(node.dataset.zcgInterval || 1000));\n"
        "      const timer = setInterval(async () => {\n"
        "        if (!document.body.contains(node)) { clearInterval(timer); return; }\n"
        "        const pHdr = { headers: { 'hx-request': 'true' } };\n"
        "        const res = await fetch(node.dataset.zcgPoll, pHdr);\n"
        "        node.outerHTML = await res.text();\n"
        "        if (res.status === 286) clearInterval(timer);\n"
        "      }, iv);\n"
        "    });\n"
        "  }\n"
        "  function bindSSE(root) {\n"
        "    root.querySelectorAll('[data-zcg-sse]').forEach((node) => {\n"
        "      const es = new EventSource(node.dataset.zcgSse);\n"
        "      es.onmessage = (e) => window.IslandBus?.emit('sse.message', e.data);\n"
        "    });\n"
        "  }\n"
        "  window.ZCGSwap = { swapFetch, bindPolling, bindSSE };\n"
        "  document.addEventListener('DOMContentLoaded', () => {\n"
        "    bindPolling(document);\n"
        "    bindSSE(document);\n"
        "  });\n"
        "})();\n",
    ),
    "js/hydrator.js": (
        "application/javascript; charset=utf-8",
        "(() => {\n"
        "  window.ZCGIslands = window.ZCGIslands || {};\n"
        "  async function mount(el) {\n"
        "    if (el.dataset.hydrated) return;\n"
        "    el.dataset.hydrated = '1';\n"
        "    const props = JSON.parse(el.dataset.props || '{}');\n"
        "    if (el.dataset.module) {\n"
        "      const mod = await import(el.dataset.module);\n"
        "      mod.mount?.(el, props, window.IslandBus);\n"
        "    } else {\n"
        "      window.ZCGIslands[el.dataset.island]?.(el, props, window.IslandBus);\n"
        "    }\n"
        "  }\n"
        "  function hydrateAll(root = document) {\n"
        "    root.querySelectorAll('[data-island]').forEach((el) => {\n"
        "      const mode = el.dataset.hydrate || 'visible';\n"
        "      if (mode === 'eager') queueMicrotask(() => mount(el));\n"
        "      else if (mode === 'idle') {\n"
        "        const idle = window.requestIdleCallback || ((cb) => setTimeout(cb, 50));\n"
        "        idle(() => mount(el));\n"
        "      } else if ('IntersectionObserver' in window) {\n"
        "        const io = new IntersectionObserver((entries) => {\n"
        "          if (entries.some((e) => e.isIntersecting)) { io.disconnect(); mount(el); }\n"
        "        });\n"
        "        io.observe(el);\n"
        "      } else mount(el);\n"
        "    });\n"
        "  }\n"
        "  window.ZCGHydrator = { hydrateAll, mount };\n"
        "  document.addEventListener('DOMContentLoaded', () => hydrateAll(document));\n"
        "})();\n",
    ),
}


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
