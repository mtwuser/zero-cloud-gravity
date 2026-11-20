"""Temporary Day-0 Pending-Setup Studio renderer and /api/modules/onboarding router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Any

from zcg.cockpit.routing import network_auth
from zcg.cockpit.views import dashboard_app, orientation_ui, shell_chrome, spatial_bridge
from zcg.cockpit.views.node_context import read_json_dict
from zcg.core.blueprints import resolve_workspace_setup_state
from zcg.governance.workspace import onboarding_studio
from zcg.providers.antigravity_runtime import inspect_local_antigravity_runtime
from zcg.web.auth.security import WebAppError
from zcg.web.auth.surface_access import SurfaceAccessPolicy
from zcg.web.capabilities import appearance
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.factory import WebAppState
from zcg.web.http.request import HTML_CONTENT_TYPE, Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.templates import SafeHTML, html_t, render_icon


def _require_r3_operator(req: Request, policy: SurfaceAccessPolicy | None) -> str:
    ring = appearance.resolve_request_ring(req, policy) if policy is not None else "R3"
    if ring != "R3":
        raise WebAppError(
            "Node onboarding studio requires R3_OPERATOR access.",
            error_code="OPERATOR_RING_REQUIRED",
            http_status=int(HTTPStatus.FORBIDDEN),
        )
    return ring


def should_render_pending_setup_studio(workspace_dir: Path, req: Request) -> bool:
    """Return True when GET / should present the temporary Pending-Setup Web Studio."""
    ws = workspace_dir.resolve()
    if not (ws / "system/zcg-node.json").is_file():
        return False
    if req.query("setup", "").strip().lower() == "studio":
        return True
    if req.query("view", "").strip() or req.query("tab", "").strip():
        return False
    m_doc = read_json_dict(ws / "system/zcg-node.json")
    return not bool(resolve_workspace_setup_state(ws, m_doc)["is_configured"])


def _render_step2_agents_html(
    ws_raw: str, open_cmd: str, inst_cmd: str, local_agy: Mapping[str, Any]
) -> SafeHTML:
    comps = local_agy.get("components") or {}
    ver_parts = [
        f"{lbl} v{comps[key]['version']}"
        for key, lbl in (("agents", "Agents"), ("cli", "CLI"), ("ide", "IDE"))
        if isinstance(comps.get(key), Mapping)
        and comps[key].get("installed")
        and comps[key].get("version")
    ]
    ver_suffix = f" ({' · '.join(ver_parts)})" if ver_parts else ""
    any_inst = bool(local_agy.get("any_installed"))
    badge_text = (
        f"✓ Local Antigravity Detected{ver_suffix}" if any_inst else "Local Antigravity Setup"
    )
    details_open = SafeHTML("") if any_inst else SafeHTML(" open")
    cpu_icon = render_icon("cpu")
    return html_t(
        t"<li><strong>Open this folder in Antigravity Agents</strong> "
        t"<span class='zcg-chip'>{badge_text}</span> "
        t"<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        t'data-zcg-copy="{ws_raw}">{cpu_icon} Copy Folder Path</button>'
        t"<div class='zcg-muted-note' style='margin:0.3rem 0;'>"
        t"Open the <strong>Antigravity Agents</strong> desktop app → "
        t"<strong>Projects</strong> → select <code>{ws_raw}</code> → "
        t"<strong>New Conversation</strong> (Antigravity IDE is optional).</div>"
        t"<details{details_open} style='margin:0.35rem 0 0.2rem;'>"
        t"<summary>Terminal CLI &amp; Installer Commands (Optional)</summary>"
        t"<div style='display:grid;gap:0.4rem;margin-top:0.4rem;'>"
        t"<div><button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        t'data-zcg-copy="{inst_cmd}">Copy Install CLI</button> '
        t"<code>{inst_cmd}</code> — <small>Downloads and installs (or updates) "
        t"the Antigravity Agents desktop app (<code>/opt/antigravity-agents</code>) and "
        t"<code>agy</code> terminal CLI (<code>~/.local/bin/agy</code>).</small></div>"
        t"<div><button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        t'data-zcg-copy="{open_cmd}">Copy Terminal CLI</button> '
        t"<code>{open_cmd}</code> — <small>Starts an interactive Antigravity agent "
        t"chat directly inside your Linux terminal for this folder (terminal alternative "
        t"to the desktop app).</small></div>"
        t"</div></details></li>"
    )


def render_onboarding_studio_card_html(
    studio_state: Mapping[str, Any],
    *,
    workspace_url: str = "",
    local_agy: Mapping[str, Any] | None = None,
) -> str:
    """Render the persistent Pending-Setup Kickoff Prompt Studio card (0 inline scripts)."""
    lid = str(studio_state["layer_id"])
    ws_raw = str(studio_state.get("workspace_path") or studio_state.get("workspace_dir") or "")
    open_cmd = str(studio_state["open_workspace_cmd"])
    inst_cmd = str(studio_state["install_agents_cmd"])
    agy_state = (
        local_agy
        if local_agy is not None
        else inspect_local_antigravity_runtime(Path(ws_raw or "."))
    )
    step2_html = _render_step2_agents_html(ws_raw, open_cmd, inst_cmd, agy_state)
    prompt_raw = str(studio_state["active_prompt"])
    web_url = workspace_url or "http://localhost/"
    has_draft = bool(studio_state["has_saved_draft"])
    stamp = str(studio_state["updated_at"])
    status_lbl = (
        f"✓ Saved draft loaded from .zcg/runtime/ ({stamp})"
        if has_draft
        else "Template ready — edits auto-save locally so you never lose progress"
    )
    props_json = json.dumps(
        {
            "storageKey": f"zcg_onboarding_draft:{lid}",
            "saveUrl": "/api/modules/onboarding/draft",
            "resetUrl": "/api/modules/onboarding/reset",
            "hasServerDraft": has_draft,
            "resetConfirm": (
                f"Discard your customized edits for '{lid}' "
                "and restore the default kickoff template?"
            ),
        },
        ensure_ascii=False,
    )
    sparkles = render_icon("sparkles")
    check = render_icon("check")
    return html_t(
        t"<section class='zcg-card' data-island='draft-studio' data-hydrate='eager' "
        t"data-props='{props_json}' style='max-width:68rem;margin:0 auto;'>"
        t"<div class='zcg-card__header'><div>"
        t"<span class='zcg-badge' style='margin-bottom:0.35rem;display:inline-flex;'>"
        t"{sparkles} Pending Initial Setup · Temporary Day-0 Studio</span>"
        t"<h2>Configure <code>{lid}</code> with Your Initial Kickoff Prompt</h2></div>"
        t"<span class='zcg-badge' data-draft-status='1'>{status_lbl}</span></div>"
        t"<div class='zcg-card' style='margin:0 0 0.85rem;padding:0.85rem 1rem;'>"
        t"<ol style='margin:0;padding-left:1.25rem;display:grid;gap:0.65rem;'>"
        t"<li><strong>Customize <code>[Customize: ...]</code> below</strong>: "
        t"Replace placeholder lines with your mission and owner email "
        t"(edits auto-save locally in <code>.zcg/runtime/onboarding_draft.json</code>).</li>"
        t"{step2_html}"
        t"<li><strong>Paste &amp; Run</strong>: Click "
        t"<strong>Copy Prompt for Antigravity Chat</strong> below, paste into your new "
        t"conversation, and reload <code>{web_url}</code> once Phase D finishes "
        t"(or click <strong>Explore Workspace (Skip Setup) →</strong> anytime; "
        t"<strong>Initial Setup</strong> in the Workspace header brings you right back)."
        t"</li></ol></div>"
        t"<label for='zcg-onboarding-prompt-input' style='display:block;font-weight:600;"
        t"margin-bottom:0.35rem;'>Initial Kickoff Prompt Template (Editable &amp; Persistent)"
        t"</label><textarea id='zcg-onboarding-prompt-input' data-draft-input='1' rows='14' "
        t"style='width:100%;font-family:var(--zcg-font-mono,monospace);font-size:0.88rem;"
        t"line-height:1.45;padding:0.75rem;margin-bottom:0.75rem;'>{prompt_raw}</textarea>"
        t"<div class='zcg-tabs' style='justify-content:space-between;flex-wrap:wrap;'>"
        t"<div class='zcg-tabs'>"
        t"<button type='button' class='zcg-btn' data-draft-copy='1'>"
        t"{check} Copy Prompt for Antigravity Chat</button>"
        t"<button type='button' class='zcg-btn zcg-btn--secondary' data-draft-save='1'>"
        t"Save Draft</button></div>"
        t"<div class='zcg-tabs'>"
        t'<a class="zcg-btn zcg-btn--secondary zcg-btn--sm" href="/?view=workspace">'
        t"Explore Workspace (Skip Setup) →</a>"
        t"<button type='button' class='zcg-btn zcg-btn--secondary' data-draft-reset='1'>"
        t"Reset to Default Template</button></div></div></section>"
    ).value


def serve_pending_setup_studio(
    ws: Path,
    req: Request,
    *,
    state: WebAppState,
    plugin_id: str,
    view_archetype: str,
    policy: SurfaceAccessPolicy | None = None,
) -> WebResponse:
    """Serve the full-page temporary Pending-Setup Studio inside the node's base.html frame."""
    m_doc = read_json_dict(ws / "system/zcg-node.json")
    node_doc = read_json_dict(ws / "surfaces/data/node_scope.json")
    layer_id = str(node_doc.get("layer_id") or m_doc.get("layer_id") or ws.name)
    rt_e = read_json_dict(ws / f".agents/runtime/{plugin_id}.json").get("environment")
    q_env = req.query("env", "").strip().lower()
    act_env = (
        q_env
        if q_env in ("dev", "tst", "pre", "pro")
        else str(rt_e or network_auth.resolve_default_node_environment(m_doc))
    )
    enrich_ctx = orientation_ui.build_node_dashboard_enrichment(
        ws, layer_id=layer_id, view_archetype=view_archetype, active_env=act_env
    )
    ring = appearance.resolve_request_ring(req, policy) if policy is not None else "R3"
    prefs = shell_chrome.resolve_effective_user_prefs(ws, m_doc, cookies=req.cookies)
    app_ctx = appearance.build_appearance_template_context(
        manifest=m_doc,
        cookies=req.cookies,
        plane="workspace",
        active_env=act_env,
        caller_ring=ring,
        allow_node_theme=bool(m_doc),
        env_urls={e: f"/?env={e}" for e in ("dev", "tst", "pre", "pro")},
    )
    u_menu = shell_chrome.render_user_account_menu_html(
        layer_id=layer_id,
        entity_kind=str(enrich_ctx["entity_kind"]),
        layer_role=str(enrich_ctx["layer_role"]),
        caller_ring=ring,
        root_node_id=str(enrich_ctx["root_node_id"]),
        root_href=str(enrich_ctx["root_href"]),
        root_online=bool(enrich_ctx.get("root_online", True)),
        public_portal_enabled=bool(enrich_ctx["public_portal_enabled"]),
        health_state="UNCONFIGURED",
        language_code=prefs["language"],
        has_active_session=bool(req.cookies.get("zcg_session")),
        constellation_html=str(enrich_ctx["constellation_menu_html"]),
    )
    wb = dashboard_app.build_modular_workbench_spec(view_archetype, view_archetype)
    panel_title = str(wb["panel_title"])
    studio_state = onboarding_studio.inspect_onboarding_studio_state(ws)
    ws_url = onboarding_studio.canonical_workspace_root_url(str(enrich_ctx["cockpit_href"]))
    studio_html = render_onboarding_studio_card_html(studio_state, workspace_url=ws_url)
    ctx: dict[str, object] = {
        **enrich_ctx,
        **app_ctx,
        "csrf_token": state.csrf_token,
        "title": f"{layer_id} — Pending Initial Setup ({panel_title})",
        "layer_id": layer_id,
        "viewer_lang_attr": prefs["language"],
        "viewer_contrast_attr": prefs["contrast"],
        "viewer_scale_attr": prefs["font_scale"],
        "viewer_motion_attr": prefs["motion"],
        "user_menu_html": u_menu,
        "content": SafeHTML(f"<div class='zcg-stage'>{studio_html}</div>"),
    }
    body = str(state.templates.render("base.html", ctx)).encode("utf-8")
    return WebResponse(int(HTTPStatus.OK), HTML_CONTENT_TYPE, body, DeliveryChannel.ISLAND_SYNC)


def serve_node_atlas_plane(
    ws: Path,
    req: Request,
    *,
    state: WebAppState,
    plugin_id: str,
    view_archetype: str,
    policy: SurfaceAccessPolicy | None = None,
) -> WebResponse:
    """Serve the dedicated 2D/3D Network Atlas plane inside the node's base.html frame."""
    m_doc = read_json_dict(ws / "system/zcg-node.json")
    node_doc = read_json_dict(ws / "surfaces/data/node_scope.json")
    layer_id = str(node_doc.get("layer_id") or m_doc.get("layer_id") or ws.name)
    rt_e = read_json_dict(ws / f".agents/runtime/{plugin_id}.json").get("environment")
    q_env = req.query("env", "").strip().lower()
    act_env = (
        q_env
        if q_env in ("dev", "tst", "pre", "pro")
        else str(rt_e or network_auth.resolve_default_node_environment(m_doc))
    )
    enrich_ctx = orientation_ui.build_node_dashboard_enrichment(
        ws,
        layer_id=layer_id,
        view_archetype=view_archetype,
        active_env=act_env,
        active_view_title="Network Atlas",
        show_scope_bar=False,
    )
    ring = appearance.resolve_request_ring(req, policy) if policy is not None else "R3"
    prefs = shell_chrome.resolve_effective_user_prefs(ws, m_doc, cookies=req.cookies)
    app_ctx = appearance.build_appearance_template_context(
        manifest=m_doc,
        cookies=req.cookies,
        plane="workspace",
        active_env=act_env,
        caller_ring=ring,
        allow_node_theme=bool(m_doc),
        env_urls={e: f"/atlas?env={e}" for e in ("dev", "tst", "pre", "pro")},
    )
    u_menu = shell_chrome.render_user_account_menu_html(
        layer_id=layer_id,
        entity_kind=str(enrich_ctx["entity_kind"]),
        layer_role=str(enrich_ctx["layer_role"]),
        caller_ring=ring,
        root_node_id=str(enrich_ctx["root_node_id"]),
        root_href=str(enrich_ctx["root_href"]),
        root_online=bool(enrich_ctx.get("root_online", True)),
        public_portal_enabled=bool(enrich_ctx["public_portal_enabled"]),
        health_state=str(enrich_ctx["node_health_state"]),
        language_code=prefs["language"],
        has_active_session=bool(req.cookies.get("zcg_session")),
        constellation_html=str(enrich_ctx["constellation_menu_html"]),
        active_plane="atlas",
    )
    atlas_html = spatial_bridge.render_live_node_atlas_fragment(ws)
    ctx: dict[str, object] = {
        **enrich_ctx,
        **app_ctx,
        "csrf_token": state.csrf_token,
        "title": f"{layer_id} — Network Atlas",
        "layer_id": layer_id,
        "brand_href": "/atlas",
        "viewer_lang_attr": prefs["language"],
        "viewer_contrast_attr": prefs["contrast"],
        "viewer_scale_attr": prefs["font_scale"],
        "viewer_motion_attr": prefs["motion"],
        "user_menu_html": u_menu,
        "content": SafeHTML(
            f"<div class='zcg-stage'>{enrich_ctx['orientation_bar_html']}"
            f"<section id='zcg-atlas-stage'>{atlas_html}</section></div>"
        ),
    }
    body = str(state.templates.render("base.html", ctx)).encode("utf-8")
    return WebResponse(int(HTTPStatus.OK), HTML_CONTENT_TYPE, body, DeliveryChannel.IMMERSIVE_SYNC)


def create_onboarding_router(
    workspace_dir: Path, *, policy: SurfaceAccessPolicy | None = None
) -> APIRouter:
    """Mount R3-guarded /api/modules/onboarding endpoints for persistent Day-0 setup drafts."""
    ws = workspace_dir.resolve()
    router = APIRouter(prefix="/api/modules/onboarding", tags=("onboarding",))

    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="Inspect Day-0 onboarding studio")
    def get_onboarding_studio(req: Request) -> WebResponse:
        _require_r3_operator(req, policy)
        studio_state = onboarding_studio.inspect_onboarding_studio_state(ws)
        frag = render_onboarding_studio_card_html(studio_state)
        return respond(req, html_fragment=frag, data=studio_state)

    @router.post(
        "/draft", channel=DeliveryChannel.ISLAND_SYNC, summary="Persist Day-0 kickoff draft"
    )
    def save_draft(req: Request) -> WebResponse:
        _require_r3_operator(req, policy)
        form = req.form() if "urlencoded" in req.content_type.lower() else {}
        payload = form or (req.json() if req.body.strip() else {})
        prompt_val = str(payload.get("prompt") or "") if isinstance(payload, dict) else ""
        try:
            saved = onboarding_studio.save_onboarding_draft(ws, prompt_text=prompt_val)
        except ValueError as exc:
            raise WebAppError(
                str(exc),
                error_code="INVALID_ONBOARDING_DRAFT",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
            ) from exc
        frag = f"<span class='zcg-badge'>✓ Saved ({saved['updated_at']})</span>"
        return respond(req, html_fragment=frag, data=saved)

    @router.post("/reset", channel=DeliveryChannel.ISLAND_SYNC, summary="Reset Day-0 kickoff draft")
    def reset_draft(req: Request) -> WebResponse:
        _require_r3_operator(req, policy)
        res = onboarding_studio.reset_onboarding_draft(ws)
        frag = "<span class='zcg-badge'>↺ Restored original template</span>"
        return respond(req, html_fragment=frag, data=res)

    return router
