"""Two-layer web appearance engine: R3 node/plane brand themes and R0..R3 viewer accessibility.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.core.manifests import load_node_manifest
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.auth.surface_access import SURFACE_RING_HEADER, SurfaceAccessPolicy
from zcg.web.auth.tls import format_set_cookie_header
from zcg.web.capabilities.brand_assets import (
    PLANE_IDENTITY_LABELS,
    BrandCommitCallback,
    apply_node_theme_mutation,
)
from zcg.web.http.channels import DeliveryChannel, build_swap_response_headers
from zcg.web.http.request import Request, UploadFile, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.templates import SafeHTML, render_icon, sanitize_url

UI_PREFS_COOKIE_NAME: Final[str] = "zcg_ui_prefs"
UI_PREFS_COOKIE_MAX_AGE_SEC: Final[int] = 31_536_000
DEFAULT_BRAND_LOGO_URL: Final[str] = "/static/img/logo.svg"
VALID_THEME_PLANES: Final[tuple[str, ...]] = ("control_plane", "workspace", "public_portal")
VALID_THEME_SCOPES: Final[tuple[str, ...]] = ("all", *VALID_THEME_PLANES)
VALID_THEME_PRESETS: Final[tuple[str, ...]] = (
    "blueprint-dark", "paper-light", "nordic-slate", "solar-warm"
)  # fmt: skip
VALID_THEME_ACCENTS: Final[tuple[str, ...]] = (
    "default", "sky", "emerald", "violet", "amber", "rose"
)  # fmt: skip
VALID_VIEWER_CONTRASTS: Final[tuple[str, ...]] = (
    "inherit", "dark", "light", "high-contrast", "colorblind-safe"
)  # fmt: skip
VALID_VIEWER_SCALES: Final[tuple[str, ...]] = ("100", "112", "125")
VALID_VIEWER_MOTIONS: Final[tuple[str, ...]] = ("standard", "reduced")
ENV_FRAME_LABELS: Final[dict[str, str]] = {
    "dev": "DEV · Sandbox", "tst": "TST · QA", "pre": "PRE · Staging", "pro": "LIVE"
}  # fmt: skip
_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "::1", "localhost", ""})
_CONTRAST_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("inherit", "Node Default"), ("dark", "Force Dark"), ("light", "Force Light"),
    ("high-contrast", "High Contrast (AAA)"), ("colorblind-safe", "Colorblind-Safe (Okabe-Ito)"),
)  # fmt: skip
_SCALE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("100", "100% Standard"), ("112", "112% Comfortable"), ("125", "125% Large")
)  # fmt: skip
_MOTION_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("standard", "Standard Motion"), ("reduced", "Reduced Motion")
)  # fmt: skip
_PRESET_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("blueprint-dark", "Blueprint Dark"), ("paper-light", "Paper Light"),
    ("nordic-slate", "Nordic Slate"), ("solar-warm", "Solar Warm"),
)  # fmt: skip


def sanitize_brand_logo_url(raw_url: str) -> str:
    """Validate a brand logo/avatar path or HTTPS URL, falling back to DEFAULT_BRAND_LOGO_URL."""
    clean = raw_url.strip()
    if not clean:
        return DEFAULT_BRAND_LOGO_URL
    safe = sanitize_url(clean)
    return DEFAULT_BRAND_LOGO_URL if safe == "#" else safe


def resolve_plane_web_theme(
    manifest: Mapping[str, Any] | None, *, plane: str = "workspace"
) -> dict[str, str]:
    """Resolve effective preset, accent, and logo_url for a node surface plane."""
    eff_plane = plane if plane in VALID_THEME_PLANES else "workspace"
    raw_wt = (manifest or {}).get("web_theme")
    wt = raw_wt if isinstance(raw_wt, Mapping) else {}
    raw_planes = wt.get("planes")
    p_ovr_raw = raw_planes.get(eff_plane) if isinstance(raw_planes, Mapping) else None
    p_ovr = p_ovr_raw if isinstance(p_ovr_raw, Mapping) else {}
    pr = str(p_ovr.get("preset") or wt.get("preset") or "blueprint-dark").strip().lower()
    ac = str(p_ovr.get("accent") or wt.get("accent") or "default").strip().lower()
    lg = str(p_ovr.get("logo_url") or wt.get("logo_url") or "").strip()
    return {
        "plane": eff_plane, "preset": pr if pr in VALID_THEME_PRESETS else "blueprint-dark",
        "accent": ac if ac in VALID_THEME_ACCENTS else "default",
        "logo_url": sanitize_brand_logo_url(lg),
    }  # fmt: skip


def parse_viewer_ui_prefs(cookies: Mapping[str, str] | None) -> dict[str, str]:
    """Decode per-browser viewer contrast, font scale, and motion preferences from cookies."""
    parts = str((cookies or {}).get(UI_PREFS_COOKIE_NAME) or "").strip().split(".")
    c = parts[0].lower() if len(parts) >= 1 and parts[0].lower() in VALID_VIEWER_CONTRASTS else ""
    s = parts[1] if len(parts) >= 2 and parts[1] in VALID_VIEWER_SCALES else ""
    m = parts[2].lower() if len(parts) >= 3 and parts[2].lower() in VALID_VIEWER_MOTIONS else ""
    return {"contrast": c or "inherit", "font_scale": s or "100", "motion": m or "standard"}


def encode_viewer_ui_prefs(
    *, contrast: str = "inherit", font_scale: str = "100", motion: str = "standard"
) -> str:
    """Validate and encode viewer UI accessibility preferences into a compact cookie token."""
    c, s, m = contrast.strip().lower(), font_scale.strip(), motion.strip().lower()
    if c not in VALID_VIEWER_CONTRASTS:
        raise ValueError(f"Invalid contrast {contrast!r}; valid={VALID_VIEWER_CONTRASTS}")
    if s not in VALID_VIEWER_SCALES:
        raise ValueError(f"Invalid font_scale {font_scale!r}; valid={VALID_VIEWER_SCALES}")
    if m not in VALID_VIEWER_MOTIONS:
        raise ValueError(f"Invalid motion {motion!r}; valid={VALID_VIEWER_MOTIONS}")
    return f"{c}.{s}.{m}"


def can_viewer_travel_environments(*, caller_ring: str) -> bool:
    """Return True only for authenticated internal intranet members (R2) and operators (R3)."""
    return caller_ring.strip().upper() in ("R2", "R3")


def _select_opts(choices: Sequence[tuple[str, str]], selected: str) -> str:
    return "".join(
        f"<option value='{html.escape(val, quote=True)}'"
        f"{' selected' if val == selected else ''}>{html.escape(lbl)}</option>"
        for val, lbl in choices
    )


def render_appearance_menu_html(
    *, plane: str = "workspace", active_env: str = "pro", caller_ring: str = "R0",
    theme: Mapping[str, str] | None = None, viewer_prefs: Mapping[str, str] | None = None,
    env_urls: Mapping[str, str] | None = None, allow_node_theme: bool = False,
) -> SafeHTML:  # fmt: skip
    """Render the unified Viewer Accessibility, Environment Travel, and R3 Node Theme menu."""
    eff_plane = plane if plane in VALID_THEME_PLANES else "workspace"
    raw_env, ring = active_env.strip().lower(), caller_ring.strip().upper() or "R0"
    clean_env = raw_env if raw_env in ENV_FRAME_LABELS else "pro"
    can_travel = can_viewer_travel_environments(caller_ring=ring)
    eff_theme = theme or {
        "preset": "blueprint-dark", "accent": "default", "logo_url": DEFAULT_BRAND_LOGO_URL
    }  # fmt: skip
    eff_prefs = viewer_prefs or {"contrast": "inherit", "font_scale": "100", "motion": "standard"}
    dot_html = (
        f"<span class='zcg-env-dot zcg-env-dot--{html.escape(clean_env)}'></span>"
        f"<span>{html.escape(clean_env.upper())}</span>"
        if can_travel and clean_env != "pro" else "<span>Appearance</span>"
    )  # fmt: skip
    c_opts = _select_opts(_CONTRAST_CHOICES, eff_prefs.get("contrast", "inherit"))
    s_opts = _select_opts(_SCALE_CHOICES, eff_prefs.get("font_scale", "100"))
    m_opts = _select_opts(_MOTION_CHOICES, eff_prefs.get("motion", "standard"))
    sec_viewer = (
        "<div class='zcg-burger__divider'>My View &amp; Accessibility (Browser)</div>"
        "<form class='zcg-appearance-form' method='post' action='/api/appearance/viewer-prefs' "
        "data-zcg-post='/api/appearance/viewer-prefs' data-zcg-target='#zcg-appearance-out'>"
        f"<label>Contrast<select name='contrast'>{c_opts}</select></label>"
        f"<label>Text Scale<select name='font_scale'>{s_opts}</select></label>"
        f"<label>Motion<select name='motion'>{m_opts}</select></label>"
        "<button type='submit' class='zcg-btn zcg-btn--sm'>Apply to My Browser</button></form>"
    )
    sec_env = ""
    if can_travel:
        urls = env_urls or {e: f"?env={e}" for e in ENV_FRAME_LABELS}
        pills = "".join(
            f"<a class='zcg-env-pill zcg-env-pill--{html.escape(ec)}"
            f"{' is-active' if ec == clean_env else ''}' "
            f"href='{html.escape(str(u), quote=True)}'>"
            f"{html.escape('LIVE' if ec == 'pro' else ec.upper())}</a>"
            for ec, u in urls.items() if ec in ENV_FRAME_LABELS
        )  # fmt: skip
        sec_env = (
            f"<div class='zcg-burger__divider'>Environment Travel ({html.escape(ring)})</div>"
            f"<div class='zcg-env-strip' role='group' aria-label='Environment travel'>{pills}</div>"
        )
    sec_node = ""
    if ring == "R3" and allow_node_theme:
        p_lbl = html.escape(PLANE_IDENTITY_LABELS[eff_plane])
        pr_opts = _select_opts(_PRESET_CHOICES, eff_theme.get("preset", "blueprint-dark"))
        ac_opts = _select_opts(
            tuple((a, a.capitalize()) for a in VALID_THEME_ACCENTS),
            eff_theme.get("accent", "default"),
        )
        logo_v = html.escape(eff_theme.get("logo_url", DEFAULT_BRAND_LOGO_URL), quote=True)
        sec_node = (
            f"<div class='zcg-burger__divider'>Node Brand — {p_lbl}</div>"
            "<form class='zcg-appearance-form' method='post' enctype='multipart/form-data' "
            "action='/api/appearance/node-theme' data-zcg-post='/api/appearance/node-theme' "
            "data-zcg-target='#zcg-appearance-out'>"
            f"<input type='hidden' name='scope' value='{eff_plane}'>"
            f"<label>Base Theme<select name='preset'>{pr_opts}</select></label>"
            f"<label>Accent<select name='accent'>{ac_opts}</select></label>"
            "<label>Upload Emblem / Photo (<= 512 KB)"
            "<input type='file' name='brand_file' accept='.svg,.png,.jpg,.jpeg,.webp'></label>"
            f"<label>Or Brand URL<input type='text' name='logo_url' value='{logo_v}'></label>"
            "<label><input type='checkbox' name='commit_changes' value='1'> "
            "Scoped Git commit on save</label>"
            "<label><input type='checkbox' name='reset_plane' value='1'> "
            "Reset this perspective to default</label>"
            "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
            "Save Perspective Brand</button></form>"
        )
    return SafeHTML(
        f"<details class='zcg-burger zcg-appearance-menu' data-zcg-appearance-plane='{eff_plane}'>"
        "<summary class='zcg-burger__btn' aria-label='Appearance and accessibility settings'>"
        f"{render_icon('sparkles')} {dot_html}</summary>"
        "<div class='zcg-burger__panel zcg-appearance-panel'>"
        f"{sec_viewer}{sec_env}{sec_node}"
        "<div id='zcg-appearance-out' aria-live='polite'></div></div></details>"
    )


def build_appearance_template_context(
    *, manifest: Mapping[str, Any] | None = None, cookies: Mapping[str, str] | None = None,
    plane: str = "workspace", active_env: str = "pro", caller_ring: str = "R0",
    env_urls: Mapping[str, str] | None = None, allow_node_theme: bool = False,
) -> dict[str, object]:  # fmt: skip
    """Build template context variables for base.html, cockpit, workspace, and public portal."""
    eff_plane = plane if plane in VALID_THEME_PLANES else "workspace"
    raw_env, ring = active_env.strip().lower(), caller_ring.strip().upper() or "R0"
    can_travel = can_viewer_travel_environments(caller_ring=ring)
    clean_env = raw_env if raw_env in ENV_FRAME_LABELS else "pro"
    framed_env = "pro" if (eff_plane == "public_portal" and not can_travel) else clean_env
    theme = resolve_plane_web_theme(manifest, plane=eff_plane)
    prefs = parse_viewer_ui_prefs(cookies)
    env_bdg = (
        SafeHTML(
            f"<span class='zcg-env-pill zcg-env-pill--{html.escape(framed_env)} is-active' "
            f"title='Active environment'>{html.escape(ENV_FRAME_LABELS[framed_env])}</span>"
        ) if framed_env != "pro" and can_travel else SafeHTML("")
    )  # fmt: skip
    menu = render_appearance_menu_html(
        plane=eff_plane, active_env=framed_env, caller_ring=ring, theme=theme,
        viewer_prefs=prefs, env_urls=env_urls, allow_node_theme=allow_node_theme,
    )  # fmt: skip
    return {
        "active_env_attr": framed_env, "theme_preset_attr": theme["preset"],
        "theme_accent_attr": theme["accent"], "viewer_contrast_attr": prefs["contrast"],
        "viewer_scale_attr": prefs["font_scale"], "viewer_motion_attr": prefs["motion"],
        "brand_logo_url": theme["logo_url"], "env_frame_badge_html": env_bdg,
        "appearance_menu_html": menu,
    }  # fmt: skip


def _extract_payload(req: Request) -> tuple[Mapping[str, Any], UploadFile | None]:
    ct = req.content_type.lower()
    if "multipart/form-data" in ct:
        mp = req.multipart()
        flat = {k: v[0] for k, v in mp.fields.items() if v}
        return flat, mp.get_file("brand_file")
    if "urlencoded" in ct:
        return req.form(), None
    if req.body.strip() and isinstance(parsed := req.json(), Mapping):
        return parsed, None
    return {}, None


def resolve_request_ring(req: Request, policy: SurfaceAccessPolicy | None = None) -> str:
    """Resolve effective R0..R3 caller ring from SurfaceAccessPolicy, header, or loopback host."""
    host = req.headers.get("host", "").partition(":")[0].strip().lower().strip("[]")
    if policy is not None:
        return policy.authenticate_request(
            headers=req.headers, cookies=req.cookies, client_host=host
        ).ring.value
    hdr_r = req.headers.get(SURFACE_RING_HEADER, "").strip().upper()
    def_r = "R3" if (host in _LOOPBACK_HOSTS or host.endswith(".localhost")) else "R0"
    return hdr_r if hdr_r in ("R0", "R1", "R2", "R3") else def_r


def _matching_cookie_domain(req: Request, cookie_domains: Sequence[str]) -> str:
    h = req.headers.get("host", "").partition(":")[0].strip().rstrip(".").lower()
    doms = (d.strip().lstrip(".").rstrip(".").lower() for d in cookie_domains)
    return next((d for d in doms if d and (h == d or h.endswith(f".{d}"))), "")


def _bad_input(msg: str, code: str) -> WebAppError:
    return WebAppError(
        msg, error_code=code, http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
        severity=ErrorSeverity.WARNING, action=ErrorAction.FIX_INPUT,
    )  # fmt: skip


def create_appearance_router(
    workspace_dir: Path | None = None, *, policy: SurfaceAccessPolicy | None = None,
    cookie_domains: Sequence[str] = (), prefix: str = "/api/appearance",
    commit_callback: BrandCommitCallback | None = None,
) -> APIRouter:  # fmt: skip
    """Create APIRouter for R0..R3 viewer accessibility cookies and R3 node brand themes."""
    ws = workspace_dir.resolve() if workspace_dir is not None else None
    router = APIRouter(prefix=prefix.rstrip("/") or "/api/appearance", tags=("appearance",))

    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="Inspect resolved appearance state")
    def inspect_appearance(req: Request) -> WebResponse:
        has_m = ws is not None and (ws / NODE_MANIFEST_REL_PATH).is_file()
        m_doc = load_node_manifest(ws) if has_m and ws is not None else {}
        theme = resolve_plane_web_theme(m_doc, plane=req.query("plane", "workspace").strip())
        prefs = parse_viewer_ui_prefs(req.cookies)
        t_h, c_h = html.escape(theme["preset"]), html.escape(prefs["contrast"])
        frag = (
            f"<div class='zcg-card'>Theme: <code>{t_h}</code> · Contrast: <code>{c_h}</code></div>"
        )
        return respond(req, html_fragment=frag, data={"web_theme": theme, "viewer_prefs": prefs})

    @router.post(
        "/viewer-prefs", channel=DeliveryChannel.SWAP_SYNC,
        summary="Persist browser-scoped viewer contrast, font scale, and motion preferences",
    )  # fmt: skip
    def save_viewer_prefs(req: Request) -> WebResponse:
        payload, _ = _extract_payload(req)
        try:
            encoded = encode_viewer_ui_prefs(
                contrast=str(payload.get("contrast") or "inherit"),
                font_scale=str(payload.get("font_scale") or "100"),
                motion=str(payload.get("motion") or "standard"),
            )
        except ValueError as exc:
            raise _bad_input(str(exc), "INVALID_VIEWER_PREFS") from exc
        prefs = parse_viewer_ui_prefs({UI_PREFS_COOKIE_NAME: encoded})
        ck_hdr = format_set_cookie_header(
            UI_PREFS_COOKIE_NAME, encoded, is_https=req.is_secure, same_site="Lax",
            http_only=True, path="/", max_age=UI_PREFS_COOKIE_MAX_AGE_SEC,
            domain=_matching_cookie_domain(req, cookie_domains),
        )  # fmt: skip
        hdrs = {**build_swap_response_headers(trigger="appearanceUpdated"), "set-cookie": ck_hdr}
        frag = (
            "<div class='zcg-alert' "
            f"data-apply-contrast='{html.escape(prefs['contrast'], quote=True)}' "
            f"data-apply-scale='{html.escape(prefs['font_scale'], quote=True)}' "
            f"data-apply-motion='{html.escape(prefs['motion'], quote=True)}'>"
            "Saved personal view &amp; accessibility preferences for this browser.</div>"
        )
        return respond(req, html_fragment=frag, data={"viewer_prefs": prefs}, headers=hdrs)

    @router.post(
        "/node-theme", channel=DeliveryChannel.SWAP_SYNC,
        summary="Update R3 operator node brand logo and plane theme in system/zcg-node.json",
    )  # fmt: skip
    def save_node_theme(req: Request) -> WebResponse:
        if resolve_request_ring(req, policy) != "R3":
            raise WebAppError(
                "Updating node brand & plane theme requires R3 operator authority",
                error_code="R3_OPERATOR_REQUIRED", http_status=int(HTTPStatus.FORBIDDEN),
                severity=ErrorSeverity.WARNING,
            )  # fmt: skip
        if ws is None or not (ws / NODE_MANIFEST_REL_PATH).is_file():
            raise WebAppError(
                "Node manifest system/zcg-node.json is required to persist web_theme",
                error_code="WORKSPACE_MANIFEST_MISSING", http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
            )  # fmt: skip
        payload, brand_file = _extract_payload(req)
        scope = str(payload.get("scope") or "all").strip().lower()
        preset = str(payload.get("preset") or "blueprint-dark").strip().lower()
        accent = str(payload.get("accent") or "default").strip().lower()
        raw_logo = str(payload.get("logo_url") or "").strip()
        if (
            scope not in VALID_THEME_SCOPES
            or preset not in VALID_THEME_PRESETS
            or accent not in VALID_THEME_ACCENTS
        ):
            raise _bad_input("Invalid scope, preset, or accent", "INVALID_NODE_THEME")
        try:
            mut = apply_node_theme_mutation(
                ws, scope=scope, preset=preset, accent=accent, raw_logo=raw_logo,
                default_logo_url=DEFAULT_BRAND_LOGO_URL, brand_file=brand_file,
                reset_plane=str(payload.get("reset_plane") or "") == "1",
                commit_changes=str(payload.get("commit_changes") or "") == "1",
                commit_callback=commit_callback,
            )  # fmt: skip
        except ValueError as exc:
            raise _bad_input(str(exc), str(exc).partition(":")[0] or "INVALID_BRAND") from exc
        hdrs = build_swap_response_headers(trigger="appearanceUpdated")
        frag = (
            "<div class='zcg-alert' "
            f"data-apply-scope='{html.escape(scope, quote=True)}' "
            f"data-apply-theme='{html.escape(mut['preset'], quote=True)}' "
            f"data-apply-accent='{html.escape(mut['accent'], quote=True)}' "
            f"data-apply-logo='{html.escape(mut['logo_url'], quote=True)}'>"
            f"Saved perspective brand (<code>{html.escape(scope)}</code> &rarr; "
            f"<code>{html.escape(mut['preset'])}</code>).</div>"
        )
        return respond(req, html_fragment=frag, data=mut, headers=hdrs)

    return router
