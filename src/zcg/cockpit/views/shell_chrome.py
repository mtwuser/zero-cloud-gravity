"""Unified sovereign shell chrome, human role labels, user preferences, and settings router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable, Mapping, Sequence
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.routing import network_auth, provenance
from zcg.cockpit.views import mesh_liveness
from zcg.core.constants import (  # fmt: skip
    DEFAULT_PLUGIN_BASE_PORT,
    VALID_ENVIRONMENTS,
    VALID_KNOWLEDGE_PREFIXES,
)
from zcg.core.manifests import load_node_manifest
from zcg.topology.exposure import is_public_portal_enabled
from zcg.web.auth.security import SESSION_COOKIE, ErrorAction, ErrorSeverity, WebAppError
from zcg.web.auth.surface_access import SURFACE_RING_HEADER, SurfaceAccessPolicy
from zcg.web.auth.tls import format_set_cookie_header
from zcg.web.capabilities import appearance
from zcg.web.http.channels import DeliveryChannel, build_swap_response_headers
from zcg.web.http.request import HTML_CONTENT_TYPE, Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.templates import SafeHTML, TemplateCatalog, render_icon

type SettingsHtmlRenderer = Callable[[str, str, dict[str, str]], bytes]

USER_PREFS_REL_PATH: Final[str] = ".zcg/runtime/user_prefs.json"
VALID_UI_LANGUAGES: Final[tuple[tuple[str, str], ...]] = (
    ("es", "Español"), ("en", "English"), ("fr", "Français"),
    ("de", "Deutsch"), ("it", "Italiano"), ("pt", "Português"),
)  # fmt: skip
VALID_UI_LANGUAGE_CODES: Final[frozenset[str]] = frozenset(c for c, _ in VALID_UI_LANGUAGES)
_PERSONAL_PILLAR_LABELS: Final[tuple[tuple[str, str], ...]] = (
    ("tutor", "Study & Tutor"), ("work", "Career & Ventures"),
    ("wallet", "Patrimony & Wallet"), ("game", "Game & Lab"),
)  # fmt: skip
_ORG_ROLE_LABELS: Final[dict[str, str]] = {
    "workstation": "Workstation Hub", "corporate": "Corporate Root 0",
    "domain-policy": "Domain Policy", "department": "Department", "squad": "Squad",
    "project": "Project", "service-node": "Service Node",
    "environment-cluster": "Environment Cluster",
}  # fmt: skip
_CONTRAST_LABELS: Final[tuple[tuple[str, str], ...]] = (
    ("inherit", "Follow Node Brand"), ("dark", "Force Dark"), ("light", "Force Light"),
    ("high-contrast", "High Contrast (AAA)"), ("colorblind-safe", "Colorblind-Safe (Okabe-Ito)"),
)  # fmt: skip
_SCALE_LABELS: Final[tuple[tuple[str, str], ...]] = (("100", "100% Standard"), ("112", "112% Comfortable"), ("125", "125% Large"))  # fmt: skip  # noqa: E501
_MOTION_LABELS: Final[tuple[tuple[str, str], ...]] = (("standard", "Standard Motion"), ("reduced", "Reduced Motion"))  # fmt: skip  # noqa: E501
_PLANE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("workspace", "Workspace (/)"), ("public_portal", "Public Web (/portal)"),
    ("control_plane", "Node Admin (/admin)"), ("all", "All Node Surfaces"),
)  # fmt: skip


def resolve_human_role_label(
    node_id: str, layer_role: str, *, entity_kind: str = "enterprise"
) -> str:
    """Translate raw topological layer_role into an entity-appropriate human-legible label."""
    cid, crole = node_id.strip().lower(), layer_role.strip().lower()
    if crole == "knowledge" or cid.startswith(VALID_KNOWLEDGE_PREFIXES):
        return "Knowledge Corpus"
    if entity_kind.strip().lower() == "individual":
        if crole == "workstation" or cid == "profile" or cid.endswith("-profile"):
            return "Personal Hub"
        if crole == "domain-policy" or cid == "security" or cid.endswith("-security"):
            return "Personal Security"
        for suffix, label in _PERSONAL_PILLAR_LABELS:
            if cid == suffix or cid.endswith(f"-{suffix}"):
                return label
        return "Personal Pillar"
    return _ORG_ROLE_LABELS.get(crole) or crole.replace("-", " ").title()


def resolve_avatar_initials(subject: str) -> str:
    """Derive 1-2 uppercase avatar initials from an email, node ID, or operator handle."""
    parts = subject.strip().partition("@")[0].replace(".", "-").replace("_", "-").split("-")
    clean = [t for seg in parts if (t := "".join(ch for ch in seg if ch.isalnum()))]
    return (clean[0][0] + clean[1][0]).upper() if len(clean) >= 2 else (
        clean[0][0].upper() if clean else "OP"
    )  # fmt: skip


def _read_runtime_user_prefs(root_ws: Path) -> dict[str, str]:
    fp = root_ws / USER_PREFS_REL_PATH
    try:
        raw = json.loads(fp.read_text("utf-8")) if fp.is_file() else None
    except json.JSONDecodeError:
        raw = None
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _pick_valid(raw_val: str, allowed: Sequence[str] | frozenset[str], fallback: str) -> str:
    v, lo = raw_val.strip(), raw_val.strip().lower()
    return v if v in allowed else (lo if lo in allowed else fallback)


def _select_html(choices: Sequence[tuple[str, str]], selected: str) -> str:
    return "".join(f"<option value='{html.escape(v, quote=True)}'{' selected' if v == selected else ''}>{html.escape(lbl)}</option>" for v, lbl in choices)  # fmt: skip  # noqa: E501


def resolve_effective_user_prefs(
    workspace_dir: Path, manifest: Mapping[str, Any] | None = None,
    *, cookies: Mapping[str, str] | None = None,
) -> dict[str, str]:  # fmt: skip
    """Resolve user-scoped language, contrast, font_scale, and motion across nodes."""
    m = manifest or {}
    disk = _read_runtime_user_prefs(network_auth.resolve_governing_root_workspace(workspace_dir, m))
    def_lg = _pick_valid(str(m.get("interaction_language") or ""), VALID_UI_LANGUAGE_CODES, "en")
    b_lg = _pick_valid(disk.get("language", ""), VALID_UI_LANGUAGE_CODES, def_lg)
    b_con = _pick_valid(disk.get("contrast", ""), appearance.VALID_VIEWER_CONTRASTS, "inherit")
    b_scl = _pick_valid(disk.get("font_scale", ""), appearance.VALID_VIEWER_SCALES, "100")
    b_mot = _pick_valid(disk.get("motion", ""), appearance.VALID_VIEWER_MOTIONS, "standard")
    parts = str((cookies or {}).get(appearance.UI_PREFS_COOKIE_NAME) or "").strip().split(".")
    c = _pick_valid(parts[0], appearance.VALID_VIEWER_CONTRASTS, b_con)
    s = _pick_valid(parts[1] if len(parts) >= 2 else "", appearance.VALID_VIEWER_SCALES, b_scl)
    mo = _pick_valid(parts[2] if len(parts) >= 3 else "", appearance.VALID_VIEWER_MOTIONS, b_mot)
    lg = _pick_valid(parts[3] if len(parts) >= 4 else "", VALID_UI_LANGUAGE_CODES, b_lg)
    return {"contrast": c, "font_scale": s, "motion": mo, "language": lg}


def persist_user_prefs(
    workspace_dir: Path, manifest: Mapping[str, Any] | None = None, *,
    language: str = "en", contrast: str = "inherit", font_scale: str = "100",
    motion: str = "standard", persist_local: bool = False, is_https: bool = False,
    request_host: str = "", cookie_domains: Sequence[str] = (),
) -> dict[str, Any]:  # fmt: skip
    """Validate and persist cross-node user preferences to runtime JSON + network cookie."""
    lg, c = language.strip().lower(), contrast.strip().lower()
    s, mo = font_scale.strip(), motion.strip().lower()
    for val, allowed, name in ((lg, VALID_UI_LANGUAGE_CODES, "language"),
                               (c, appearance.VALID_VIEWER_CONTRASTS, "contrast"),
                               (s, appearance.VALID_VIEWER_SCALES, "font_scale"),
                               (mo, appearance.VALID_VIEWER_MOTIONS, "motion")):  # fmt: skip
        if val not in allowed:
            raise ValueError(f"Invalid {name} {val!r}")
    prefs = {"contrast": c, "font_scale": s, "motion": mo, "language": lg}
    if persist_local:
        r_ws = network_auth.resolve_governing_root_workspace(workspace_dir, manifest or {})
        out_f = r_ws / USER_PREFS_REL_PATH
        out_f.parent.mkdir(parents=True, exist_ok=True)
        out_f.write_text(json.dumps(prefs, indent=2) + "\n", encoding="utf-8")
    host_only = request_host.partition(":")[0].strip().lower().strip("[]")
    matched_dom = next((d for raw in cookie_domains if (d := raw.strip().lower().lstrip("."))
                        and (host_only == d or host_only.endswith(f".{d}"))), "")  # fmt: skip
    token = f"{c}.{s}.{mo}.{lg}"
    hdr = format_set_cookie_header(
        appearance.UI_PREFS_COOKIE_NAME, token, is_https=is_https, http_only=False,
        same_site="Lax", max_age=appearance.UI_PREFS_COOKIE_MAX_AGE_SEC, domain=matched_dom,
    )  # fmt: skip
    return {"prefs": prefs, "cookie_token": token, "set_cookie_header": hdr}


def render_user_account_menu_html(
    *, layer_id: str, entity_kind: str = "enterprise", layer_role: str = "department",
    caller_ring: str = "R3", subject_id: str = "", root_node_id: str = "", root_href: str = "",
    root_online: bool = True, public_portal_enabled: bool = True,
    health_state: str = "OPTIMAL", language_code: str = "en",
    login_enabled: bool = True, has_active_session: bool = False,
    constellation_html: str = "", health_notes: Sequence[str] = (), active_plane: str = "workspace",
) -> SafeHTML:  # fmt: skip
    """Render the universal top-right Sign-In CTA (R0) or Circular User Avatar menu (R1..R3)."""
    ring = caller_ring.strip().upper() or "R0"
    if ring == "R0":
        if not login_enabled:
            return SafeHTML("")
        s_cta = "<a class='zcg-btn zcg-btn--sm zcg-google-signin' href='/auth/session?format=html' data-zcg-auth-cta='google-oidc'>"  # noqa: E501
        return SafeHTML(f"<div class='zcg-user-cta'>{s_cta}{render_icon('user')} Sign in with Google</a></div>")  # fmt: skip  # noqa: E501
    sub_clean, h_st = subject_id.strip(), health_state.strip().upper() or "OPTIMAL"
    ident = sub_clean or layer_id
    initials = html.escape(resolve_avatar_initials(ident))
    h_role = html.escape(resolve_human_role_label(layer_id, layer_role, entity_kind=entity_kind))
    dot_cls = f"zcg-status-dot zcg-status-dot--{html.escape(h_st.lower())}"
    lid_h, ring_h, lg_h = html.escape(layer_id), html.escape(ring), html.escape(language_code.strip().upper() or "EN")  # fmt: skip  # noqa: E501
    root_lbl, r_href = html.escape(root_node_id or layer_id), html.escape(root_href, quote=True)
    if r_href:
        p_pill = (
            f"<a class='zcg-crumb-pill' href='{r_href}' aria-label='Go up to Root 0 ({root_lbl})' "
            f"title='Go up to Root 0 ({root_lbl})'>↑ {root_lbl}</a>" if root_online
            else f"<span class='zcg-crumb-pill zcg-crumb-offline' role='link' aria-disabled='true' "
            f"title='Root 0 ({root_lbl}) is offline'>⚪ ↑ {root_lbl} · Offline</span>"
        )  # fmt: skip
        crumb_h = f"<nav class='zcg-user-menu__crumb' aria-label='Node lineage'>{p_pill}<span aria-hidden='true'>&rsaquo;</span><strong>{lid_h}</strong></nav>"  # noqa: E501
    else:
        crumb_h = f"<div class='zcg-user-menu__crumb'><span class='zcg-crumb-badge'>★ Root 0</span><strong>{lid_h}</strong></div>"  # noqa: E501
    sub_pfx = f"{html.escape(sub_clean)} · " if (sub_clean and sub_clean != layer_id) else ""
    h_cls, h_txt = f"zcg-health-pill--{html.escape(h_st.lower())}", html.escape(h_st)
    h_tip = f" title='{html.escape(' · '.join(health_notes), quote=True)}'" if health_notes else ""
    h_bdg = f" <span class='zcg-badge {h_cls}'{h_tip}>{h_txt}</span>" if h_st != "OPTIMAL" else ""
    ap, act_a = active_plane.strip().lower(), " class='is-active' aria-current='page'"
    ws_a, ad_a, pb_a = (act_a if ap == k else "" for k in ("workspace", "admin", "portal"))
    st_c, st_cur = (" is-active", " aria-current='page'") if ap == "settings" else ("", "")
    at_c, at_cur = (" is-active", " aria-current='page'") if ap == "atlas" else ("", "")
    adm_r = f'<a{ad_a} href="/admin">{render_icon("shield")} Node Admin (/admin){h_bdg}</a>' if ring == "R3" else ""  # fmt: skip  # noqa: E501
    pub_r = f"<a{pb_a} href='/portal?format=html'>{render_icon('globe')} Public Web (/portal)</a>" if public_portal_enabled else ""  # fmt: skip  # noqa: E501
    out_r = f"<form method='post' action='/auth/logout' data-zcg-post='/auth/logout'><button type='submit' class='zcg-menu-btn'>{render_icon('lock')} Sign Out</button></form>" if has_active_session else ""  # fmt: skip  # noqa: E501
    atlas_btn = f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm zcg-atlas-icon-btn{at_c}' href='/atlas'{at_cur} aria-label='Network Atlas (/atlas)' title='Open 2D/3D Network Atlas (/atlas)'>{render_icon('layers')}</a>"  # noqa: E501
    set_btn = f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm zcg-settings-btn{st_c}' href='/settings'{st_cur} aria-label='User Settings (/settings)' title='User Settings (/settings)'>{render_icon('settings')}</a>"  # noqa: E501
    return SafeHTML(
        f"{set_btn}<details class='zcg-burger zcg-user-menu'><summary class='zcg-user-avatar-btn' "
        f"aria-label='Account ({ring_h})' data-zcg-auth-cta='active-session' "
        f"title='{html.escape(ident)} ({h_role})'><span class='zcg-user-avatar'>{initials}</span>"
        f"<span class='{dot_cls}' data-health-state='{h_txt}'></span>"
        f"<span class='zcg-sr-only'>Account ({ring_h})</span></summary>"
        f"<div class='zcg-burger__panel zcg-user-menu__panel'><div class='zcg-user-menu__head'>"
        f"<div>{crumb_h}<small>{sub_pfx}{h_role} · {ring_h} · {lg_h}</small></div>{atlas_btn}"
        f"</div><a{ws_a} href='/'>{render_icon('compass')} Workspace (/)</a>{adm_r}{pub_r}"
        f"{constellation_html}{out_r}</div></details>"
    )


def render_node_brand_settings_card_html(
    *, theme: Mapping[str, str], plane: str = "workspace"
) -> SafeHTML:
    """Render the R3 Node Brand customization form strictly inside /settings."""
    eff_plane = plane if plane in appearance.VALID_THEME_PLANES else "workspace"
    sc_opts = _select_html(_PLANE_CHOICES, eff_plane)
    presets = tuple((p, p.replace("-", " ").title()) for p in appearance.VALID_THEME_PRESETS)
    pr_v = str(theme.get("preset") or "")
    pr_opts = _select_html(presets, pr_v if pr_v in appearance.VALID_THEME_PRESETS else "blueprint-dark")  # noqa: E501  # fmt: skip
    ac_opts = _select_html(tuple((a, a.capitalize()) for a in appearance.VALID_THEME_ACCENTS), theme.get("accent", "default"))  # noqa: E501  # fmt: skip
    logo_v = html.escape(theme.get("logo_url", appearance.DEFAULT_BRAND_LOGO_URL), quote=True)
    return SafeHTML(
        "<form class='zcg-appearance-form' method='post' enctype='multipart/form-data' "
        "action='/api/appearance/node-theme' data-zcg-post='/api/appearance/node-theme' "
        f"data-zcg-target='#zcg-brand-settings-out'><label>Target Surface<select name='scope'>"
        f"{sc_opts}</select></label><label>Base Palette<select name='preset'>{pr_opts}"
        f"</select></label><label>Accent Color<select name='accent'>{ac_opts}</select></label>"
        "<label>Upload Node Emblem / Logo (&lt;= 512 KB)<input type='file' name='brand_file' "
        f"accept='.svg,.png,.jpg,.jpeg,.webp'></label><label>Or Brand Logo URL<input type='text' "
        f"name='logo_url' value='{logo_v}'></label><label><input type='checkbox' "
        "name='commit_changes' value='1'> Scoped Git commit</label><label><input type='checkbox' "
        "name='reset_plane' value='1'> Reset to default</label><button type='submit' "
        "class='zcg-btn zcg-btn--sm'>Save Node Brand</button>"
        "<div id='zcg-brand-settings-out' aria-live='polite'></div></form>"
    )


def require_operator_settings_ring(caller_ring: str) -> None:
    """Raise HTTP 403 NODE_ADMIN_OPERATOR_REQUIRED unless caller_ring is R3."""
    if caller_ring.strip().upper() != "R3":
        raise WebAppError(
            "Operator ring R3 is required to inspect or modify Node Admin.",
            error_code="NODE_ADMIN_OPERATOR_REQUIRED", http_status=int(HTTPStatus.FORBIDDEN),
            severity=ErrorSeverity.WARNING, action=ErrorAction.NONE,
        )  # fmt: skip


def require_authenticated_settings_ring(caller_ring: str) -> None:
    """Raise HTTP 403 USER_SETTINGS_AUTH_REQUIRED when caller_ring is anonymous R0."""
    if caller_ring.strip().upper() in ("", "R0"):
        raise WebAppError(
            "Authenticated ring (R1..R3) is required to access User Settings.",
            error_code="USER_SETTINGS_AUTH_REQUIRED", http_status=int(HTTPStatus.FORBIDDEN),
            severity=ErrorSeverity.WARNING, action=ErrorAction.NONE,
        )  # fmt: skip


def create_shell_chrome_router(
    workspace_dir: Path, *, csrf_token: str, active_env: str = "pro",
    policy: SurfaceAccessPolicy | None = None, cookie_domains: Sequence[str] = (),
    settings_renderer: SettingsHtmlRenderer,
) -> APIRouter:  # fmt: skip
    """Create the (/admin, /settings) APIRouter separating Node Admin vs User Settings."""
    ws = workspace_dir.resolve()
    router, catalog = APIRouter(tags=("shell-chrome",)), TemplateCatalog(())

    def _ring_and_subject(req: Request) -> tuple[str, str]:
        if policy is not None:
            h = req.headers.get("host", "").partition(":")[0].strip().lower().strip("[]")
            p = policy.authenticate_request(headers=req.headers, cookies=req.cookies, client_host=h)
            return p.ring.value, p.subject_id
        return req.headers.get(SURFACE_RING_HEADER, "R3").strip().upper() or "R3", ""

    @router.get("/admin", channel=DeliveryChannel.ISLAND_SYNC, summary="R3 Node Admin")
    def get_node_admin(req: Request) -> WebResponse:
        require_operator_settings_ring((rs := _ring_and_subject(req))[0])
        q_e = req.query("env", "").strip().lower()
        raw_b = settings_renderer(q_e if q_e in VALID_ENVIRONMENTS else active_env, rs[0], dict(req.cookies))  # noqa: E501  # fmt: skip
        csrf_m = f'<meta name="zcg-csrf-token" content="{html.escape(csrf_token)}">'.encode()
        body = raw_b.replace(b'<meta name="zcg-csrf-token" content="">', csrf_m, 1)
        return WebResponse(int(HTTPStatus.OK), HTML_CONTENT_TYPE, body, DeliveryChannel.ISLAND_SYNC)

    @router.get("/settings", channel=DeliveryChannel.ISLAND_SYNC, summary="User Settings")
    def get_user_settings(req: Request) -> WebResponse:
        m, (ring, subj) = load_node_manifest(ws), _ring_and_subject(req)
        require_authenticated_settings_ring(ring)
        lid, prefs = str(m.get("layer_id") or ws.name), resolve_effective_user_prefs(ws, m, cookies=req.cookies)  # noqa: E501  # fmt: skip
        app_ctx = appearance.build_appearance_template_context(
            manifest=m, cookies=req.cookies, plane="workspace", active_env=active_env, caller_ring=ring,  # noqa: E501
        )  # fmt: skip
        lg_o, c_o = _select_html(VALID_UI_LANGUAGES, prefs["language"]), _select_html(_CONTRAST_LABELS, prefs["contrast"])  # noqa: E501  # fmt: skip
        s_o, m_o = _select_html(_SCALE_LABELS, prefs["font_scale"]), _select_html(_MOTION_LABELS, prefs["motion"])  # noqa: E501  # fmt: skip
        r_ws = network_auth.resolve_governing_root_workspace(ws, m)
        r_m = load_node_manifest(r_ws) if r_ws != ws else m
        r_id, r_p = str(r_m.get("layer_id") or r_ws.name), DEFAULT_PLUGIN_BASE_PORT + int(r_m.get("precedence", 90))  # noqa: E501  # fmt: skip
        from zcg.cockpit.views import node_context

        r_href = f"http://{r_id}.localhost:{r_p}/" if r_ws != ws else ""
        r_on = mesh_liveness.probe_local_node_online(r_href)[0] if r_href else True
        nh = (node_context.read_json_dict(ws / "surfaces/data/node_scope.json").get("representation_context") or {}).get("node_health") or {}  # noqa: E501  # fmt: skip
        n_sc, f_sc = node_context.read_json_dict(ws / "surfaces/data/network_scope.json"), node_context.read_json_dict(ws / "surfaces/data/federation_scope.json")  # noqa: E501  # fmt: skip
        nav_it = mesh_liveness.annotate_cross_node_liveness(node_context.build_cross_node_links(lid, n_sc, f_sc, manifest=m))  # noqa: E501  # fmt: skip
        menu = render_user_account_menu_html(
            layer_id=lid, entity_kind=str(m.get("entity_kind") or "enterprise"),
            layer_role=str(m.get("layer_role") or "department"), caller_ring=ring, subject_id=subj,
            root_node_id=r_id, root_href=r_href, root_online=r_on,
            public_portal_enabled=is_public_portal_enabled(m, active_env=active_env),
            health_state=str(nh.get("overall_state") or "OPTIMAL"), health_notes=tuple(str(x) for x in (nh.get("attention_items") or ())),  # noqa: E501
            language_code=prefs["language"], has_active_session=bool(req.cookies.get(SESSION_COOKIE)),  # noqa: E501
            constellation_html=mesh_liveness.render_menu_constellation_html(nav_it), active_plane="settings",  # noqa: E501
        )  # fmt: skip
        frag = (
            "<section class='zcg-card'><h1>User Settings (Cross-Node)</h1><p>Personal language "
            "and reading settings follow you across connected nodes with zero Git changes.</p>"
            "<form class='zcg-appearance-form' method='post' action='/settings' data-zcg-post="
            f"'/settings' data-zcg-target='#zcg-user-prefs-out'><label>Interface Language<select "
            f"name='language'>{lg_o}</select></label><label>Reading Theme &amp; Contrast<select "
            f"name='contrast'>{c_o}</select></label><label>Text Scale<select name='font_scale'>"
            f"{s_o}</select></label><label>Motion<select name='motion'>{m_o}</select></label>"
            "<button type='submit' class='zcg-btn'>Save User Settings</button></form>"
            "<div id='zcg-user-prefs-out' aria-live='polite'></div></section>"
        )
        fmt, acc = req.query("format", "").lower(), req.headers.get("accept", "").lower()
        wants_html = fmt == "html" or (fmt != "json" and "text/html" in acc)
        ftr = provenance.render_provenance_footer_html(ws, m, f_sc.get("intranet_topology") or {}, active_env=active_env)  # noqa: E501  # fmt: skip
        full = (
            str(catalog.render("base.html", {
                **app_ctx, "csrf_token": csrf_token, "title": f"User Settings — {lid}",
                "layer_id": lid, "brand_href": "/settings", "provenance_footer_html": ftr,
                "viewer_lang_attr": prefs["language"], "viewer_contrast_attr": prefs["contrast"],
                "viewer_scale_attr": prefs["font_scale"], "viewer_motion_attr": prefs["motion"],
                "user_menu_html": menu, "content": SafeHTML(frag),
            })) if wants_html else None
        )  # fmt: skip
        data = {"scope": "user_settings", "caller_ring": ring, "subject": subj, "prefs": prefs}
        return respond(req, html_fragment=frag, data=data, full_html=full)

    @router.post("/settings", channel=DeliveryChannel.SWAP_SYNC, summary="Save User Settings")
    def post_user_settings(req: Request) -> WebResponse:
        m, (ring, _) = load_node_manifest(ws), _ring_and_subject(req)
        require_authenticated_settings_ring(ring)
        cur = resolve_effective_user_prefs(ws, m, cookies=req.cookies)
        if "urlencoded" in req.content_type.lower():
            raw: Mapping[str, Any] = req.form()
        elif not req.body.strip():
            raw = {}
        elif isinstance(parsed := req.json(), dict):
            raw = parsed
        else:
            raise WebAppError(
                "User Settings payload must be a JSON object.", error_code="INVALID_USER_PREFS",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
            )  # fmt: skip
        try:
            saved = persist_user_prefs(
                ws, m, language=str(raw.get("language") or cur["language"]),
                contrast=str(raw.get("contrast") or cur["contrast"]),
                font_scale=str(raw.get("font_scale") or cur["font_scale"]),
                motion=str(raw.get("motion") or cur["motion"]), persist_local=(ring == "R3"),
                is_https=(req.headers.get("x-forwarded-proto", "").lower() == "https"),
                request_host=req.headers.get("host", ""), cookie_domains=cookie_domains,
            )  # fmt: skip
        except ValueError as exc:
            raise WebAppError(
                str(exc), error_code="INVALID_USER_PREFS",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY), action=ErrorAction.FIX_INPUT,
            ) from exc  # fmt: skip
        sw_h = build_swap_response_headers(refresh=True)
        hdrs = {"Set-Cookie": saved["set_cookie_header"], **sw_h}
        frag = "<div class='zcg-alert'>Saved personal user settings across your network.</div>"
        return respond(req, html_fragment=frag, data=saved, headers=hdrs)

    return router
