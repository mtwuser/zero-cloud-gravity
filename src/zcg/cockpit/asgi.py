"""Sovereign node Native ASGI adapter composed over zcg.web.factory.create_web_app.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import json
import mimetypes
from http import HTTPStatus
from pathlib import Path
from typing import Any

from zcg.cockpit.dashboard_app import (
    ARCHETYPE_DEFAULT_PLUGIN,
    MODULE_ACTION_CATALOG,
    MODULE_SWAP_URLS,
    build_dashboard_routers,
    build_modular_workbench_spec,
    resolve_enabled_modules,
)
from zcg.cockpit.orientation_ui import (
    build_node_dashboard_enrichment,
    create_node_context_router,
    create_surface_attestation_router,
)
from zcg.cockpit.plugin_sdk import load_plugin_routers, resolve_plugin_pack_dir
from zcg.core.constants import REPO_DIR
from zcg.core.manifests import ensure_contained_path
from zcg.web.channels import DeliveryChannel, build_swap_response_headers
from zcg.web.components import render_tabs
from zcg.web.factory import WebAppState, create_web_app
from zcg.web.request import HTML_CONTENT_TYPE, ASGIApp, Request, WebResponse, respond
from zcg.web.router import APIRouter
from zcg.web.security import DEFAULT_MAX_PAYLOAD_BYTES, DocsAccessMode, ErrorSeverity, WebAppError
from zcg.web.server import run_server_cli
from zcg.web.telemetry import TelemetryGrade
from zcg.web.templates import SafeHTML


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _resolve_node_modules_and_id(ws: Path) -> tuple[str, str, tuple[str, ...]]:
    node_doc = _read_json_if_exists(ws / "surfaces/data/node_scope.json")
    manifest_doc = _read_json_if_exists(ws / "system/zcg-node.json")
    layer_id = str(node_doc.get("layer_id") or manifest_doc.get("layer_id") or ws.name)
    rep = node_doc.get("representation_context") or {}
    v_arch = str(rep.get("view_archetype") or "departmental-ops-cockpit")
    raw_mods = rep.get("enabled_modules") or manifest_doc.get("enabled_modules")
    mod_list = [str(m) for m in raw_mods] if isinstance(raw_mods, list) else None
    return layer_id, v_arch, resolve_enabled_modules(v_arch, mod_list)


def resolve_cockpit_web_dirs(
    workspace_dir: Path, *, engine_dir: Path = REPO_DIR
) -> tuple[str, tuple[Path, ...], tuple[Path, ...]]:
    """Resolve active plugin ID and cascading (template_dirs, static_dirs) for a node."""
    ws = workspace_dir.resolve()
    node_doc = _read_json_if_exists(ws / "surfaces/data/node_scope.json")
    rep = node_doc.get("representation_context") or {}
    v_arch = str(rep.get("view_archetype") or "departmental-ops-cockpit")
    dw = rep.get("dual_world_contract") or {}
    rt_dir = ws / ".agents/runtime"
    rt_docs = (
        [_read_json_if_exists(f) for f in sorted(rt_dir.glob("*.json"))] if rt_dir.is_dir() else []
    )
    act_doc = next(
        (d for d in rt_docs if d.get("status") == "active"), rt_docs[0] if rt_docs else {}
    )
    rt_id = str(act_doc.get("plugin_id") or "")
    raw_base = str(dw.get("common_base_plugin") or rt_id)
    valid_plugins = set(ARCHETYPE_DEFAULT_PLUGIN.values())
    base_id = (
        raw_base
        if raw_base in valid_plugins
        else ARCHETYPE_DEFAULT_PLUGIN.get(v_arch, "node-work-cockpit")
    )
    active_pdir = resolve_plugin_pack_dir(ws, rt_id, engine_dir=engine_dir) if rt_id else None
    base_pdir = resolve_plugin_pack_dir(ws, base_id, engine_dir=engine_dir)
    plugin_id = rt_id if active_pdir is not None else base_id
    cand_tpls = [ws / "surfaces/web/templates"]
    cand_stats = [ws / "surfaces/web/static"]
    for pdir in (active_pdir, base_pdir):
        if pdir is not None:
            cand_tpls.append(pdir / "web/templates")
            cand_stats.append(pdir / "web/static")
    tpl_dirs = tuple(dict.fromkeys(d.resolve() for d in cand_tpls if d.is_dir()))
    stat_dirs = tuple(dict.fromkeys(d.resolve() for d in cand_stats if d.is_dir()))
    return plugin_id, tpl_dirs, stat_dirs


def _build_plugin_dashboard_router(
    ws: Path,
    *,
    plugin_id: str,
    view_archetype: str,
    enabled_modules: tuple[str, ...],
    state: WebAppState,
) -> APIRouter:
    router = APIRouter(tags=("dashboard",))

    def _dashboard_context() -> dict[str, object]:
        node_doc = _read_json_if_exists(ws / "surfaces/data/node_scope.json")
        manifest_doc = _read_json_if_exists(ws / "system/zcg-node.json")
        layer_id = str(node_doc.get("layer_id") or manifest_doc.get("layer_id") or ws.name)
        rep = node_doc.get("representation_context") or {}
        dw = rep.get("dual_world_contract") or {}
        overlay = str(dw.get("use_case_overlay") or view_archetype)
        wb_spec = build_modular_workbench_spec(
            view_archetype, overlay, enabled_modules=enabled_modules
        )
        panel_title = str(wb_spec["panel_title"])
        tabs = [
            ("overview", "Overview", "/dashboard/overview"),
            *[(m, MODULE_ACTION_CATALOG[m][0], MODULE_SWAP_URLS[m]) for m in enabled_modules],
        ]
        nav_html = render_tabs(
            tabs=tabs, active_tab="overview", target_selector="#zcg-capability-stage"
        )
        rt_doc = _read_json_if_exists(ws / f".agents/runtime/{plugin_id}.json")
        act_env = str(rt_doc.get("environment") or "dev")
        enrich_ctx = build_node_dashboard_enrichment(
            ws, layer_id=layer_id, view_archetype=view_archetype, active_env=act_env
        )
        base_ctx: dict[str, object] = {
            "csrf_token": state.csrf_token,
            "title": f"{layer_id} — {panel_title}",
            "layer_id": layer_id,
            "plugin_id": plugin_id,
            "view_archetype": view_archetype,
            "use_case_overlay": overlay,
            "active_env": act_env,
            "panel_title": panel_title,
            "enabled_modules_csv": ", ".join(enabled_modules),
            "nav_tabs": nav_html,
            **enrich_ctx,
        }
        try:
            ov_html = state.templates.render("partials/overview.html", base_ctx)
        except KeyError:
            ov_html = SafeHTML(f'<div class="zcg-card"><p>{html.escape(panel_title)}</p></div>')
        return {**base_ctx, "overview_fragment": ov_html}

    @router.get(
        "/dashboard", channel=DeliveryChannel.ISLAND_SYNC, summary="Editable plugin dashboard"
    )
    def serve_plugin_dashboard(req: Request) -> WebResponse:
        ctx = _dashboard_context()
        tpl_name = "index.html"
        try:
            state.templates.resolve_template_source(tpl_name)
        except KeyError:
            tpl_name = "base.html"
        return state.templates.respond_template(
            req, template_name=tpl_name, block_name="content", context=ctx
        )

    @router.get(
        "/dashboard/overview",
        channel=DeliveryChannel.SWAP_SYNC,
        summary="Editable dashboard overview fragment",
    )
    def serve_dashboard_overview(_req: Request) -> WebResponse:
        ov_frag = _dashboard_context()["overview_fragment"]
        return WebResponse(
            int(HTTPStatus.OK),
            HTML_CONTENT_TYPE,
            str(ov_frag).encode("utf-8"),
            DeliveryChannel.SWAP_SYNC,
        )

    return router


def _build_cockpit_shell_router(ws: Path) -> APIRouter:
    router = APIRouter(tags=("cockpit",))

    def _serve_index(req: Request) -> WebResponse:
        node_doc = _read_json_if_exists(ws / "surfaces/data/node_scope.json")
        net_doc = _read_json_if_exists(ws / "surfaces/data/network_scope.json")
        layer_id = str(node_doc.get("layer_id") or ws.name)
        if req.is_partial_swap and not req.is_boosted:
            links_n = len(
                (net_doc.get("network_representation_links") or {}).get("linked_nodes") or []
            )
            tgt = req.swap_target
            auto_h = build_swap_response_headers(reselect=tgt, reswap="outerHTML") if tgt else {}
            frag_s = (
                f'<section id="zcg-z2-fragment" data-layer="{html.escape(layer_id)}" '
                f'data-linked-count="{links_n}">{html.escape(layer_id)}</section>'
            )
            return WebResponse(
                int(HTTPStatus.OK),
                HTML_CONTENT_TYPE,
                frag_s.encode("utf-8"),
                DeliveryChannel.SWAP_SYNC,
                auto_h,
            )
        idx_p = ws / "surfaces/web/index.html"
        fb = f"<!doctype html><title>{html.escape(layer_id)}</title>".encode()
        html_b = idx_p.read_bytes() if idx_p.is_file() else fb
        return WebResponse(
            int(HTTPStatus.OK), HTML_CONTENT_TYPE, html_b, DeliveryChannel.ISLAND_SYNC
        )

    router.add_route("GET", "/", _serve_index, summary="Serve sovereign node cockpit HTML or swap")
    router.add_route("GET", "/index.html", _serve_index, summary="Serve index.html alias")

    @router.post("/fragments/ack", channel=DeliveryChannel.SWAP_SYNC, summary="Acknowledge swap")
    def acknowledge_fragment(req: Request) -> WebResponse:
        node_doc = _read_json_if_exists(ws / "surfaces/data/node_scope.json")
        layer_id = str(node_doc.get("layer_id") or ws.name)
        raw_txt = req.body.decode("utf-8", errors="replace").strip()
        parsed = json.loads(raw_txt) if raw_txt.startswith("{") else {"raw": raw_txt}
        sw_hdrs = build_swap_response_headers(trigger="cockpitAck")
        ack_frag = f'<div class="zcg-ack" data-layer="{html.escape(layer_id)}">OK</div>'
        return respond(
            req,
            html_fragment=ack_frag,
            data={"acknowledged": True, "payload": parsed},
            channel=DeliveryChannel.SWAP_SYNC,
            headers=sw_hdrs,
        )

    return router


def _build_surfaces_fallback_handler(ws: Path) -> Any:
    data_root = ws / "surfaces/data"
    web_root = ws / "surfaces/web"

    def _serve_surface_file(req: Request) -> WebResponse:
        if req.method != "GET":
            raise WebAppError(
                f"Resource not found: {req.path}",
                error_code="NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND),
                severity=ErrorSeverity.WARNING,
            )
        rel = req.path.lstrip("/")
        try:
            if req.path.startswith("/data/"):
                cand = ensure_contained_path(data_root / req.path.removeprefix("/data/"), data_root)
                target_file = (
                    cand if cand.is_file() else ensure_contained_path(web_root / rel, web_root)
                )
            else:
                target_file = ensure_contained_path(web_root / rel, web_root)
        except ValueError as exc:
            raise WebAppError(
                str(exc),
                error_code="PATH_CONTAINMENT_VIOLATION",
                http_status=int(HTTPStatus.FORBIDDEN),
            ) from exc
        if not target_file.is_file():
            raise WebAppError(
                f"Resource not found: {req.path}",
                error_code="NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND),
                severity=ErrorSeverity.WARNING,
            )
        mime = mimetypes.guess_type(target_file.name)[0] or "application/octet-stream"
        return WebResponse(
            int(HTTPStatus.OK), mime, target_file.read_bytes(), DeliveryChannel.STATIC_SYNC
        )

    return _serve_surface_file


def create_node_cockpit_asgi_app(
    workspace_dir: Path,
    *,
    csrf_token: str | None = None,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    docs_access_mode: DocsAccessMode = DocsAccessMode.PUBLIC,
    docs_bearer_token: str = "",
    sse_heartbeat_sec: float = 15.0,
    telemetry_grade: TelemetryGrade = TelemetryGrade.G1_OBSERVE,
    engine_dir: Path = REPO_DIR,
) -> ASGIApp:
    """Create a sovereign node Native ASGI callable delegating to create_web_app."""
    ws = workspace_dir.resolve()
    init_layer_id, init_archetype, enabled_mods = _resolve_node_modules_and_id(ws)
    plugin_id, tpl_dirs, stat_dirs = resolve_cockpit_web_dirs(ws, engine_dir=engine_dir)
    plugin_dir = resolve_plugin_pack_dir(ws, plugin_id, engine_dir=engine_dir)

    def _sse_snapshot(_st: WebAppState) -> dict[str, object]:
        node_doc = _read_json_if_exists(ws / "surfaces/data/node_scope.json")
        lid = str(node_doc.get("layer_id") or ws.name)
        rt = (node_doc.get("representation_context") or {}).get(
            "runtime_telemetry", {"regime": "OPTIMAL", "health_score": 1.0}
        )
        return {"layer_id": lid, "runtime_telemetry": rt, "enabled_modules": list(enabled_mods)}

    def _healthz_extra(_st: WebAppState) -> dict[str, object]:
        node_doc = _read_json_if_exists(ws / "surfaces/data/node_scope.json")
        lid = str(node_doc.get("layer_id") or ws.name)
        return {
            "layer_id": lid,
            "enabled_modules": list(enabled_mods),
            **_read_json_if_exists(ws / "surfaces/web/healthz"),
        }

    def _poll_done(_req: Request, st: WebAppState) -> bool:
        ledger = _read_json_if_exists(ws / "surfaces/data/node_scope.json").get("own_node_ledger")
        in_prog = int(ledger.get("in_progress_count", 0)) if isinstance(ledger, dict) else 0
        return in_prog == 0 and st.job_queue.active_count == 0

    return create_web_app(
        title=f"ZeroCloudGravity Cockpit ({init_layer_id})",
        routers=(
            _build_cockpit_shell_router(ws),
            create_surface_attestation_router(
                ws, plugin_id=plugin_id, web_dirs=(*tpl_dirs, *stat_dirs, ws / "surfaces/web")
            ),
        ),
        router_factory=lambda st: (
            _build_plugin_dashboard_router(
                ws,
                plugin_id=plugin_id,
                view_archetype=init_archetype,
                enabled_modules=enabled_mods,
                state=st,
            ),
            create_node_context_router(ws, view_archetype=init_archetype),
            *build_dashboard_routers(
                ws,
                enabled_modules=enabled_mods,
                layer_label=init_layer_id,
                state=st,
                view_archetype=init_archetype,
            ),
            *(load_plugin_routers(ws, plugin_dir, state=st) if plugin_dir is not None else ()),
        ),
        template_dirs=tpl_dirs,
        static_dirs=stat_dirs,
        csrf_token=csrf_token,
        max_payload_bytes=max_payload_bytes,
        docs_access_mode=docs_access_mode,
        docs_bearer_token=docs_bearer_token,
        sse_heartbeat_sec=sse_heartbeat_sec,
        sse_event_name="cockpit.snapshot",
        telemetry_grade=telemetry_grade,
        sse_snapshot_provider=_sse_snapshot,
        healthz_extra_provider=_healthz_extra,
        poll_done_predicate=_poll_done,
        fallback_handler=_build_surfaces_fallback_handler(ws),
    )


def run_cockpit_daemon_cli(
    argv: list[str] | None = None, *, max_runtime_sec: float | None = None
) -> int:
    """Run the loopback ASGI daemon CLI configured with create_node_cockpit_asgi_app."""
    return run_server_cli(
        argv,
        app_builder=lambda ws, mode: create_node_cockpit_asgi_app(ws, docs_access_mode=mode),
        max_runtime_sec=max_runtime_sec,
    )
