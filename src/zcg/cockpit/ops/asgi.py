"""Sovereign node Native ASGI adapter composed over zcg.web.http.factory.create_web_app.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import json
import mimetypes
import secrets
from http import HTTPStatus
from pathlib import Path
from typing import Any

from zcg.cockpit.ops import posture_guard
from zcg.cockpit.ops.plugin_sdk import load_plugin_routers, resolve_plugin_pack_dir
from zcg.cockpit.routing import (
    capability_router,
    ledger_router,
    network_auth,
    onboarding_router,
    provenance,
    runtime_router,
    surface_routing,
)
from zcg.cockpit.views import dashboard_app, orientation_ui, shell_chrome, work_views
from zcg.cockpit.views.node_context import read_json_dict
from zcg.cockpit.views.surfaces import render_live_cockpit_html, resolve_manifest_view_archetype
from zcg.core.constants import DEFAULT_PLUGIN_BASE_PORT, REPO_DIR
from zcg.core.manifests import ensure_contained_path
from zcg.governance.policy.module_registry import resolve_effective_workspace_modules
from zcg.governance.workspace.surface_mutations import commit_scoped_workspace_paths
from zcg.plugins.portal_inbox import inspect_portal_mailbox
from zcg.web.auth import security
from zcg.web.auth.surface_access import SurfaceAccessPolicy
from zcg.web.capabilities import appearance
from zcg.web.http.channels import DeliveryChannel, build_swap_response_headers
from zcg.web.http.factory import WebAppState, create_web_app
from zcg.web.http.request import HTML_CONTENT_TYPE, ASGIApp, Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.http.server import run_server_cli
from zcg.web.ops.probes import notify_systemd_ready
from zcg.web.ops.telemetry import TelemetryGrade
from zcg.web.ui.static_files import CURRENT_ENGINE_ASSET_DIGEST
from zcg.web.ui.templates import SafeHTML


def _default_archetype(ws: Path, manifest_doc: dict[str, Any]) -> str:
    return resolve_manifest_view_archetype(ws, manifest_doc)[0] if manifest_doc else "departmental-ops-cockpit"  # fmt: skip  # noqa: E501


def _resolve_node_modules_and_id(ws: Path) -> tuple[str, str, tuple[str, ...]]:
    nd, md = read_json_dict(ws / "surfaces/data/node_scope.json"), read_json_dict(ws / "system/zcg-node.json")  # noqa: E501  # fmt: skip
    layer_id, rep = str(nd.get("layer_id") or md.get("layer_id") or ws.name), nd.get("representation_context") or {}  # noqa: E501  # fmt: skip
    v_arch, def_mods = str(rep.get("view_archetype") or _default_archetype(ws, md)), dashboard_app.resolve_enabled_modules(str(rep.get("view_archetype") or _default_archetype(ws, md)))  # noqa: E501  # fmt: skip
    if md:
        return layer_id, v_arch, resolve_effective_workspace_modules(ws, view_archetype=v_arch, default_modules=def_mods)  # noqa: E501  # fmt: skip
    rep_mods = rep.get("enabled_modules")
    if not isinstance(rep_mods, list):
        return layer_id, v_arch, def_mods
    extra = [str(m) for m in rep_mods if str(m) in dashboard_app.VALID_DASHBOARD_MODULES]
    return layer_id, v_arch, tuple(dict.fromkeys((*def_mods, *extra)))


def resolve_cockpit_web_dirs(
    workspace_dir: Path, *, engine_dir: Path = REPO_DIR
) -> tuple[str, tuple[Path, ...], tuple[Path, ...]]:
    """Resolve active plugin ID and cascading (template_dirs, static_dirs) for a node."""
    ws, nd, md = workspace_dir.resolve(), read_json_dict(workspace_dir / "surfaces/data/node_scope.json"), read_json_dict(workspace_dir / "system/zcg-node.json")  # noqa: E501  # fmt: skip
    rep, rt_dir = nd.get("representation_context") or {}, ws / ".agents/runtime"
    v_arch, dw = str(rep.get("view_archetype") or _default_archetype(ws, md)), rep.get("dual_world_contract") or {}  # noqa: E501  # fmt: skip
    rt_docs = [read_json_dict(f) for f in sorted(rt_dir.glob("*.json"))] if rt_dir.is_dir() else []
    act_doc = next(
        (d for d in rt_docs if d.get("status") == "active"), rt_docs[0] if rt_docs else {}
    )
    rt_id = str(act_doc.get("plugin_id") or "")
    raw_base = str(dw.get("common_base_plugin") or rt_id)
    valid_plugins = set(dashboard_app.ARCHETYPE_DEFAULT_PLUGIN.values())
    base_id = (
        raw_base if raw_base in valid_plugins
        else dashboard_app.ARCHETYPE_DEFAULT_PLUGIN.get(v_arch, "node-work-cockpit")
    )  # fmt: skip
    active_pdir = resolve_plugin_pack_dir(ws, rt_id, engine_dir=engine_dir) if rt_id else None
    base_pdir = resolve_plugin_pack_dir(ws, base_id, engine_dir=engine_dir)
    plugin_id = rt_id if active_pdir is not None else base_id
    pdirs = [p for p in (active_pdir, base_pdir) if p is not None]
    cand_tpls = [ws / "surfaces/web/templates", *(p / "web/templates" for p in pdirs)]
    cand_stats = [ws / "surfaces/web/static", *(p / "web/static" for p in pdirs)]
    tpl_dirs = tuple(dict.fromkeys(d.resolve() for d in cand_tpls if d.is_dir()))
    stat_dirs = tuple(dict.fromkeys(d.resolve() for d in cand_stats if d.is_dir()))
    return plugin_id, tpl_dirs, stat_dirs


def _pick_env(req: Request, fallback: str) -> str:
    q = req.query("env", "").strip().lower()
    return q if q in ("dev", "tst", "pre", "pro") else fallback


def _build_plugin_dashboard_router(
    ws: Path, *, plugin_id: str, view_archetype: str, enabled_modules: tuple[str, ...],
    state: WebAppState, default_layer_id: str = "", policy: SurfaceAccessPolicy | None = None,
) -> APIRouter:  # fmt: skip
    router = APIRouter(tags=("dashboard",))

    def _dashboard_context(req: Request) -> dict[str, object]:
        node_doc = read_json_dict(ws / "surfaces/data/node_scope.json")
        m_doc = read_json_dict(ws / "system/zcg-node.json")
        layer_id = str(node_doc.get("layer_id") or m_doc.get("layer_id") or ws.name)
        dw = (node_doc.get("representation_context") or {}).get("dual_world_contract") or {}
        overlay = str(dw.get("use_case_overlay") or view_archetype)
        live_mods = _resolve_node_modules_and_id(ws)[2] if m_doc else enabled_modules
        wb = dashboard_app.build_modular_workbench_spec(view_archetype, overlay, None, live_mods)
        panel_title = str(wb["panel_title"])
        rt_e = read_json_dict(ws / f".agents/runtime/{plugin_id}.json").get("environment")
        act_env = _pick_env(req, str(rt_e or network_auth.resolve_default_node_environment(m_doc)))
        raw_v = req.query("view", "").strip() or req.query("tab", "").strip()
        ws_sc = req.query("ws_scope", "all").strip()
        v_title = work_views.resolve_workspace_view_title(wb["modules"], raw_v)
        enrich_ctx = orientation_ui.build_node_dashboard_enrichment(
            ws, layer_id=layer_id, view_archetype=view_archetype, active_env=act_env,
            active_view_title=v_title, ws_scope=ws_sc,
        )  # fmt: skip
        show_box = bool(enrich_ctx["public_portal_enabled"]) or bool(inspect_portal_mailbox(ws)["total_count"])  # noqa: E501  # fmt: skip
        nav_html, cap_html, eff_v = work_views.build_workspace_sidebar_tabs(
            wb["modules"], dashboard_app.MODULE_SWAP_URLS, show_mailbox=show_box, raw_view=raw_v
        )
        ring = appearance.resolve_request_ring(req, policy) if policy is not None else "R3"
        prefs = shell_chrome.resolve_effective_user_prefs(ws, m_doc, cookies=req.cookies)
        app_ctx = appearance.build_appearance_template_context(
            manifest=m_doc, cookies=req.cookies, plane="workspace", active_env=act_env,
            caller_ring=ring, allow_node_theme=bool(m_doc),
            env_urls={e: f"/?env={e}" for e in ("dev", "tst", "pre", "pro")},
        )  # fmt: skip
        u_menu = shell_chrome.render_user_account_menu_html(
            layer_id=layer_id, entity_kind=str(enrich_ctx["entity_kind"]),
            layer_role=str(enrich_ctx["layer_role"]), caller_ring=ring,
            root_node_id=str(enrich_ctx["root_node_id"]), root_href=str(enrich_ctx["root_href"]),
            root_online=bool(enrich_ctx.get("root_online", True)),
            public_portal_enabled=bool(enrich_ctx["public_portal_enabled"]),
            health_state=str(enrich_ctx["node_health_state"]), language_code=prefs["language"],
            has_active_session=bool(req.cookies.get("zcg_session")),
            constellation_html=str(enrich_ctx["constellation_menu_html"]),
        )  # fmt: skip
        w_sec = eff_v if eff_v in work_views.VALID_WORK_SECTIONS else "dashboard"
        w_frag, _ = ledger_router.render_work_section_fragment(
            ws, section=w_sec, metrics_scope=req.query("metrics_scope", ""),
            ws_scope=ws_sc, job_queue=state.job_queue,
        )  # fmt: skip
        base_ctx: dict[str, object] = {
            **enrich_ctx, **app_ctx, "csrf_token": state.csrf_token,
            "title": f"{layer_id} — {panel_title}", "layer_id": layer_id, "plugin_id": plugin_id,
            "view_archetype": view_archetype, "use_case_overlay": overlay, "active_env": act_env,
            "panel_title": panel_title, "enabled_modules_csv": ", ".join(live_mods),
            "nav_tabs": nav_html, "capability_tabs": cap_html,
            "work_dashboard_html": SafeHTML(w_frag), "viewer_lang_attr": prefs["language"],
            "viewer_contrast_attr": prefs["contrast"], "viewer_scale_attr": prefs["font_scale"],
            "viewer_motion_attr": prefs["motion"], "user_menu_html": u_menu,
        }  # fmt: skip
        if eff_v in ("backlog", "roadmaps", "validations", "metrics"):
            return {**base_ctx, "overview_fragment": SafeHTML(w_frag)}
        try:
            ov_html = state.templates.render("partials/overview.html", base_ctx)
        except KeyError:
            ov_html = SafeHTML(f'<div class="zcg-card"><p>{html.escape(panel_title)}</p></div>')
        return {**base_ctx, "overview_fragment": ov_html}

    def serve_plugin_dashboard(req: Request) -> WebResponse:
        ctx, tpl, tpl_s = _dashboard_context(req), "index.html", state.templates
        try:
            tpl_s.resolve_template_source(tpl)
        except KeyError:
            tpl = "base.html"
        return tpl_s.respond_template(req, template_name=tpl, block_name="content", context=ctx)

    @router.get("/dashboard/overview", channel=DeliveryChannel.SWAP_SYNC, summary="Overview swap")
    def serve_dashboard_overview(req: Request) -> WebResponse:
        body = str(_dashboard_context(req)["overview_fragment"]).encode("utf-8")
        return WebResponse(int(HTTPStatus.OK), HTML_CONTENT_TYPE, body, DeliveryChannel.SWAP_SYNC)

    def _html_ok(
        body_b: bytes, chan: DeliveryChannel = DeliveryChannel.ISLAND_SYNC, hdrs: dict[str, str] | None = None,  # noqa: E501
    ) -> WebResponse:  # fmt: skip
        return WebResponse(int(HTTPStatus.OK), HTML_CONTENT_TYPE, body_b, chan, hdrs or {})

    def _node_lid() -> str:
        return str(read_json_dict(ws / "surfaces/data/node_scope.json").get("layer_id") or default_layer_id or ws.name)  # noqa: E501  # fmt: skip

    def _serve_atlas(req: Request) -> WebResponse:
        return onboarding_router.serve_node_atlas_plane(ws, req, state=state, plugin_id=plugin_id, view_archetype=view_archetype, policy=policy)  # fmt: skip  # noqa: E501

    def _serve_index(req: Request) -> WebResponse:
        lid = _node_lid()
        if req.is_partial_swap and not req.is_boosted:
            lnks = (read_json_dict(ws / "surfaces/data/network_scope.json").get("network_representation_links") or {}).get("linked_nodes") or []  # noqa: E501  # fmt: skip
            tgt, lid_h = req.swap_target, html.escape(lid)
            auto_h = build_swap_response_headers(reselect=tgt, reswap="outerHTML") if tgt else {}
            return _html_ok(f'<section id="zcg-z2-fragment" data-layer="{lid_h}" data-linked-count="{len(lnks)}">{lid_h}</section>'.encode(), DeliveryChannel.SWAP_SYNC, auto_h)  # noqa: E501  # fmt: skip
        if (req.query("view", "").strip() or req.query("tab", "").strip()).lower() == "atlas":
            return _serve_atlas(req)
        idx_p = ws / "surfaces/web/index.html"
        disk_b = idx_p.read_bytes() if idx_p.is_file() else b""
        is_gen = b'data-island="cockpit-passport"' in disk_b or b"const D =" in disk_b
        if disk_b and not is_gen:
            tok_h = html.escape(state.csrf_token)
            csrf_m = f'<meta name="zcg-csrf-token" content="{tok_h}">'.encode()
            return _html_ok(disk_b.replace(b'<meta name="zcg-csrf-token" content="">', csrf_m, 1))
        if (ws / "system/zcg-node.json").is_file():
            if onboarding_router.should_render_pending_setup_studio(ws, req):
                return onboarding_router.serve_pending_setup_studio(ws, req, state=state, plugin_id=plugin_id, view_archetype=view_archetype, policy=policy)  # fmt: skip  # noqa: E501
            return serve_plugin_dashboard(req)
        return _html_ok(f"<!doctype html><title>{html.escape(lid)}</title>".encode())

    router.add_route("GET", "/dashboard", serve_plugin_dashboard, summary="Plugin dashboard")
    router.add_route("GET", "/atlas", _serve_atlas, channel=DeliveryChannel.IMMERSIVE_SYNC, summary="Serve dedicated 2D/3D Network Atlas plane")  # fmt: skip  # noqa: E501
    router.add_route("GET", "/", _serve_index, summary="Serve node workspace home or swap")
    router.add_route("GET", "/index.html", _serve_index, summary="Serve index.html alias")

    @router.post("/fragments/ack", channel=DeliveryChannel.SWAP_SYNC, summary="Acknowledge swap")
    def acknowledge_fragment(req: Request) -> WebResponse:
        lid = _node_lid()
        raw_txt = req.body.decode("utf-8", errors="replace").strip()
        parsed = json.loads(raw_txt) if raw_txt.startswith("{") else {"raw": raw_txt}
        ack_frag = f'<div class="zcg-ack" data-layer="{html.escape(lid)}">OK</div>'
        return respond(req, html_fragment=ack_frag, data={"acknowledged": True, "payload": parsed}, channel=DeliveryChannel.SWAP_SYNC, headers=build_swap_response_headers(trigger="cockpitAck"))  # fmt: skip  # noqa: E501

    return router


_BLOCKED_WEB_DIRS: tuple[str, ...] = ("routers", "modules", "templates", "__pycache__")
_BLOCKED_WEB_EXTS: tuple[str, ...] = (".py", ".pyc", ".sqlite3")


def _build_surfaces_fallback_handler(ws: Path) -> Any:
    data_root, web_root = ws / "surfaces/data", ws / "surfaces/web"

    def _not_found(path: str) -> security.WebAppError:
        return security.WebAppError(
            f"Resource not found: {path}", error_code="NOT_FOUND",
            http_status=int(HTTPStatus.NOT_FOUND), severity=security.ErrorSeverity.WARNING,
        )  # fmt: skip

    def _serve_surface_file(req: Request) -> WebResponse:
        if req.method != "GET":
            raise _not_found(req.path)
        try:
            d_p = data_root / req.path.removeprefix("/data/")
            cand = ensure_contained_path(d_p, data_root) if req.path.startswith("/data/") else None
            t_f = cand if (cand and cand.is_file()) else ensure_contained_path(web_root / req.path.lstrip("/"), web_root)  # noqa: E501  # fmt: skip
        except ValueError as exc:
            raise security.WebAppError(str(exc), error_code="PATH_CONTAINMENT_VIOLATION", http_status=int(HTTPStatus.FORBIDDEN)) from exc  # noqa: E501  # fmt: skip
        w_parts = t_f.relative_to(web_root).parts if t_f.is_relative_to(web_root) else ()
        if (w_parts and (w_parts[0] in _BLOCKED_WEB_DIRS or t_f.suffix.lower() in _BLOCKED_WEB_EXTS)) or not t_f.is_file():  # noqa: E501  # fmt: skip
            raise _not_found(req.path)
        mime = mimetypes.guess_type(t_f.name)[0] or "application/octet-stream"
        return WebResponse(int(HTTPStatus.OK), mime, t_f.read_bytes(), DeliveryChannel.STATIC_SYNC)

    return _serve_surface_file


def create_node_cockpit_asgi_app(
    workspace_dir: Path, *, csrf_token: str | None = None,
    max_payload_bytes: int = security.DEFAULT_MAX_PAYLOAD_BYTES,
    docs_access_mode: security.DocsAccessMode = security.DocsAccessMode.PUBLIC,
    docs_bearer_token: str = "", surface_access_policy: SurfaceAccessPolicy | None = None,
    sse_heartbeat_sec: float = 15.0,
    telemetry_grade: TelemetryGrade = TelemetryGrade.G1_OBSERVE, engine_dir: Path = REPO_DIR,
) -> ASGIApp:  # fmt: skip
    """Create a sovereign node Native ASGI callable delegating to create_web_app."""
    ws = workspace_dir.resolve()
    init_layer_id, init_archetype, enabled_mods = _resolve_node_modules_and_id(ws)
    pid, raw_tpl_dirs, stat_dirs = resolve_cockpit_web_dirs(ws, engine_dir=engine_dir)
    tpl_dirs, tpl_q = posture_guard.filter_safe_overlay_template_dirs(ws, raw_tpl_dirs)
    overlay_state: dict[str, Any] = dict(tpl_q)
    plugin_dir = resolve_plugin_pack_dir(ws, pid, engine_dir=engine_dir)
    m_doc = read_json_dict(ws / "system/zcg-node.json")
    def_env = network_auth.resolve_default_node_environment(m_doc)
    rt_env = read_json_dict(ws / f".agents/runtime/{pid}.json").get("environment")
    act_env, eff_csrf = str(rt_env or def_env), (csrf_token or secrets.token_urlsafe(24))
    eff_policy = surface_access_policy or surface_routing.compile_node_surface_access_policy(
        ws, active_env=act_env, default_session_key=eff_csrf
    )
    fb_port = DEFAULT_PLUGIN_BASE_PORT + int(m_doc.get("precedence", 50))
    port = int(m_doc.get("cockpit_port") or fb_port)
    dg = provenance.resolve_domain_governance(
        m_doc, layer_id=init_layer_id, active_env=act_env, port=port, workspace_dir=ws
    )["domain_governance"]
    _, c_doms = network_auth.resolve_network_session_material(
        ws, m_doc, intranet_zone=str(dg["intranet_zone"] or ""),
        local_dev_zone=str(dg["local_dev_zone"]), fallback_key=eff_csrf,
    )  # fmt: skip
    cdn_origins = surface_routing.resolve_node_cdn_origins(ws, active_env=act_env)

    def _render_settings(e: str, r: str, ck: dict[str, str]) -> bytes:
        return render_live_cockpit_html(ws, plugin_id=pid, active_env=e, cookies=ck, caller_ring=r)

    def _build_routers(st: WebAppState) -> tuple[APIRouter, ...]:
        ov_routers, rtr_q = posture_guard.load_overlay_routers_with_quarantine(ws, state=st)
        if rtr_q["quarantined"]:
            overlay_state["status"], overlay_state["quarantined"] = rtr_q["status"], True
            overlay_state["reason"] = rtr_q["reason"]
        return (
            _build_plugin_dashboard_router(
                ws, plugin_id=pid, view_archetype=init_archetype, enabled_modules=enabled_mods,
                state=st, default_layer_id=init_layer_id, policy=eff_policy,
            ),
            shell_chrome.create_shell_chrome_router(
                ws, csrf_token=st.csrf_token, active_env=act_env, policy=eff_policy,
                cookie_domains=c_doms, settings_renderer=_render_settings,
            ),
            orientation_ui.create_node_context_router(ws, view_archetype=init_archetype),
            appearance.create_appearance_router(
                ws, policy=eff_policy, commit_callback=commit_scoped_workspace_paths
            ),
            capability_router.create_capability_router(
                ws, view_archetype=init_archetype, policy=eff_policy,
                default_modules=dashboard_app.resolve_enabled_modules(init_archetype),
                crud_title=dashboard_app.resolve_archetype_crud_schema(init_archetype).title,
            ),
            onboarding_router.create_onboarding_router(ws, policy=eff_policy),
            runtime_router.create_runtime_router(ws, engine_dir=engine_dir, policy=eff_policy),
            *surface_routing.build_node_oidc_and_portal_routers(
                ws, csrf_token=st.csrf_token, active_env=act_env, policy=eff_policy
            ),
            *dashboard_app.build_dashboard_routers(
                ws, enabled_modules=dashboard_app.VALID_DASHBOARD_MODULES, state=st,
                layer_label=init_layer_id, view_archetype=init_archetype, policy=eff_policy,
            ),
            *(load_plugin_routers(ws, plugin_dir, state=st) if plugin_dir is not None else ()),
            *ov_routers,
        )  # fmt: skip

    def _sse_snapshot(_st: WebAppState) -> dict[str, object]:
        nd, cur_m = read_json_dict(ws / "surfaces/data/node_scope.json"), _resolve_node_modules_and_id(ws)[2]  # noqa: E501  # fmt: skip
        rt = (nd.get("representation_context") or {}).get("runtime_telemetry", {"regime": "OPTIMAL", "health_score": 1.0})  # noqa: E501  # fmt: skip
        return {"layer_id": str(nd.get("layer_id") or init_layer_id), "runtime_telemetry": rt, "enabled_modules": list(cur_m)}  # noqa: E501  # fmt: skip

    def _healthz_extra(_st: WebAppState) -> dict[str, object]:
        nd, cur_m = read_json_dict(ws / "surfaces/data/node_scope.json"), _resolve_node_modules_and_id(ws)[2]  # noqa: E501  # fmt: skip
        return {
            "layer_id": str(nd.get("layer_id") or init_layer_id), "enabled_modules": list(cur_m),
            "overlay_boot_status": overlay_state["status"],
            "security_posture_score": posture_guard.evaluate_local_security_posture(ws)["score"],
            **read_json_dict(ws / "surfaces/web/healthz"),
            "engine_asset_digest": CURRENT_ENGINE_ASSET_DIGEST,
        }  # fmt: skip

    def _poll_done(_req: Request, st: WebAppState) -> bool:
        led = read_json_dict(ws / "surfaces/data/node_scope.json").get("own_node_ledger")
        return (int(led.get("in_progress_count", 0)) if isinstance(led, dict) else 0) == 0 and st.job_queue.active_count == 0  # noqa: E501  # fmt: skip

    att_r = orientation_ui.create_surface_attestation_router(ws, plugin_id=pid, web_dirs=(*tpl_dirs, *stat_dirs, ws / "surfaces/web"))  # noqa: E501  # fmt: skip
    app = create_web_app(
        title=f"ZeroCloudGravity Cockpit ({init_layer_id})", version=network_auth.ENGINE_VERSION,
        routers=(att_r,), router_factory=_build_routers, template_dirs=tpl_dirs,
        static_dirs=stat_dirs, csrf_token=eff_csrf, max_payload_bytes=max_payload_bytes,
        docs_access_mode=docs_access_mode, docs_bearer_token=docs_bearer_token,
        surface_access_policy=eff_policy, allowed_cdn_origins=cdn_origins,
        critical_r3_safe_mode=True, sse_heartbeat_sec=sse_heartbeat_sec,
        sse_event_name="cockpit.snapshot", telemetry_grade=telemetry_grade,
        sse_snapshot_provider=_sse_snapshot, healthz_extra_provider=_healthz_extra,
        poll_done_predicate=_poll_done, fallback_handler=_build_surfaces_fallback_handler(ws),
    )  # fmt: skip
    notify_systemd_ready()
    return app


def run_cockpit_daemon_cli(
    argv: list[str] | None = None, *, max_runtime_sec: float | None = None
) -> int:
    """Run the loopback ASGI daemon CLI configured with create_node_cockpit_asgi_app."""
    return run_server_cli(
        argv, app_builder=lambda w, m: create_node_cockpit_asgi_app(w, docs_access_mode=m),
        max_runtime_sec=max_runtime_sec,
    )  # fmt: skip


if __name__ == "__main__":
    raise SystemExit(run_cockpit_daemon_cli())
