"""Composable Zone.Z4 2D/3D Exploded-View Spatial Atlas Blueprint Renderer & APIRouter.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any, Final, NoReturn

from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.capabilities.spatial_layout import (
    SpatialEdgeSpec,
    SpatialNodeSpec,
    build_reference_spatial_presets,
    clamp_explosion_factor,
)
from zcg.web.capabilities.spatial_lenses import (
    DEFAULT_SPATIAL_LENS,
    SPATIAL_LENS_DESCRIPTIONS,
    VALID_SPATIAL_LENSES,
    project_scene_with_lens,
)
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import JSON_CONTENT_TYPE, Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.templates import SafeHTML, TemplateCatalog, escape_html

DEFAULT_SPATIAL_ATLAS_PREFIX: Final[str] = "/api/spatial-atlas"
VALID_SPATIAL_RENDER_MODES: Final[tuple[str, ...]] = (
    "blueprint-3d",
    "blueprint-2d",
    "accessible-table",
)
VALID_PROXIMITY_ACTIONS: Final[tuple[str, ...]] = ("+A", "-A", "\u00b1A")
_ACTION_INTENTS: Final[dict[str, str]] = {
    "+A": "link-propose",
    "-A": "distance-decouple",
    "\u00b1A": "reconcile-diff-consult",
}


def _render_mode_btn(target_mode: str, label: str, active_mode: str) -> str:
    cls = "zcg-tab is-active" if target_mode == active_mode else "zcg-tab"
    pressed = "true" if target_mode == active_mode else "false"
    return (
        f'<button type="button" class="{cls}" data-atlas-mode="{escape_html(target_mode)}" '
        f'aria-pressed="{pressed}">{escape_html(label)}</button>'
    )


def render_spatial_atlas_html(
    scene: Mapping[str, Any],
    *,
    preset_names: Sequence[str] = (),
    active_preset: str = "constellation-4-pillar",
    active_lens: str = DEFAULT_SPATIAL_LENS,
    mode: str = "blueprint-3d",
    full_page: bool = False,
    api_prefix: str = DEFAULT_SPATIAL_ATLAS_PREFIX,
    csrf_token: str = "",
) -> str:
    """Render Non-Photorealistic Blueprint Zone.Z4 2D/3D Island + WCAG 2.2 AA parity table."""
    if mode not in VALID_SPATIAL_RENDER_MODES:
        raise ValueError(f"Unsupported spatial render mode: {mode!r}")
    if active_lens not in VALID_SPATIAL_LENSES:
        raise ValueError(f"Unsupported spatial lens: {active_lens!r}")
    props_json = escape_html(
        json.dumps(
            {
                "apiPrefix": api_prefix,
                "initialMode": mode,
                "initialLens": active_lens,
                "scene": dict(scene),
            }
        )
    )
    opts = "".join(
        f'<option value="{escape_html(p)}"{" selected" if p == active_preset else ""}>'
        f"{escape_html(p)}</option>"
        for p in (preset_names or (active_preset,))
    )
    lens_opts = "".join(
        f'<option value="{escape_html(ln)}"{" selected" if ln == active_lens else ""}>'
        f"{escape_html(ln)}</option>"
        for ln in VALID_SPATIAL_LENSES
    )
    nodes = tuple(scene.get("nodes", ()))
    node_opts = "".join(
        f'<option value="{escape_html(str(nd["node_id"]))}">'
        f"{escape_html(str(nd['node_id']))} ({escape_html(str(nd['surface_ring']))})</option>"
        for nd in nodes
    )
    rows = "".join(
        f"<tr><td><code>{escape_html(str(nd['node_id']))}</code></td>"
        f"<td>{escape_html(str(nd['label']))}</td>"
        f"<td>{escape_html(str(nd.get('lens_group') or nd['zone_band']))}</td>"
        f"<td>{escape_html(str(nd['surface_ring']))}</td>"
        f"<td>({nd['x']:.1f}, {nd['y']:.1f}, {nd['z']:.1f})</td>"
        f"<td>{nd['jaccard_affinity']:.2f}</td></tr>"
        for nd in nodes
    )
    exp_val = f"{float(scene.get('explosion', 0.0)):.2f}"
    posture_lbl = escape_html(str(scene.get("federation_posture", "sovereign")))
    lens_desc = escape_html(
        str(scene.get("lens_summary") or SPATIAL_LENS_DESCRIPTIONS[active_lens])
    )
    mode_btns = (
        _render_mode_btn("blueprint-3d", "3D Orbit", mode)
        + _render_mode_btn("blueprint-2d", "2D Blueprint", mode)
        + _render_mode_btn("accessible-table", "Table Parity", mode)
    )
    hidden_stage = " hidden" if mode == "accessible-table" else ""
    hdr_h = "<h3>2D/3D Network Atlas</h3>" if full_page else ""
    frag = (
        f'<section class="zcg-card zcg-spatial-atlas" data-zcg-surface="cockpit" '
        f'data-island="spatial-atlas" data-hydrate="eager" data-props="{props_json}" '
        f'data-render-mode="{escape_html(mode)}" data-api-prefix="{escape_html(api_prefix)}">'
        f'<header class="zcg-spatial-toolbar">{hdr_h}'
        f'<div class="zcg-tabs" role="group" aria-label="Spatial projection mode">'
        f"{mode_btns}</div>"
        f'<label>Preset <select id="zcg-atlas-preset" data-atlas-preset>{opts}</select></label>'
        f'<label>Lens <select id="zcg-atlas-lens" data-atlas-lens>{lens_opts}</select></label>'
        f'<label>Explosion [0..1] <input id="zcg-atlas-explosion" data-atlas-explosion '
        f'type="range" min="0" max="1" step="0.05" value="{exp_val}">'
        f"<output data-atlas-explosion-val>{exp_val}</output></label>"
        f'<div class="zcg-tabs">'
        f'<button type="button" class="zcg-btn--secondary zcg-btn--sm" data-atlas-zoom="in" '
        f'aria-label="Zoom in">+</button>'
        f'<button type="button" class="zcg-btn--secondary zcg-btn--sm" data-atlas-zoom="out" '
        f'aria-label="Zoom out">&minus;</button>'
        f'<button type="button" class="zcg-btn--secondary zcg-btn--sm" data-atlas-reset>'
        f"Reset</button>"
        f'<button type="button" class="zcg-btn--secondary zcg-btn--sm" data-atlas-spin>'
        f"Auto-Orbit: ON</button></div>"
        f'<span class="zcg-chip" data-atlas-posture>Posture: {posture_lbl}</span></header>'
        f'<p class="zcg-compass" data-atlas-lens-desc>{lens_desc} '
        f"&middot; Solid = Connected Core &middot; Dashed = Discoverable Horizon "
        f"&middot; Green = Shared Pack Overlap</p>"
        f'<div class="zcg-spatial-stage" data-atlas-stage{hidden_stage}>'
        f'<canvas id="zcg-spatial-canvas" data-atlas-canvas width="920" height="460" '
        f'tabindex="0" aria-label="Interactive 2D/3D Network Atlas Canvas"></canvas>'
        f"</div>"
        f'<div class="zcg-spatial-actions" data-atlas-actions>'
        f'<label>Source <select data-atlas-src aria-label="Source node">{node_opts}</select>'
        f"</label>"
        f'<label>Target <select data-atlas-dst aria-label="Target node">{node_opts}</select>'
        f"</label>"
        f'<button type="button" class="zcg-btn--secondary zcg-btn--sm" data-atlas-act="+A">'
        f"+A Link</button>"
        f'<button type="button" class="zcg-btn--secondary zcg-btn--sm" data-atlas-act="-A">'
        f"-A Distance</button>"
        f'<button type="button" class="zcg-btn--secondary zcg-btn--sm" data-atlas-act="\u00b1A">'
        f"&plusmn;A Reconcile</button>"
        f'<span class="zcg-badge" data-atlas-receipt aria-live="polite">'
        f"Drag canvas or use arrow keys to orbit 3D · wheel/+/- to zoom</span></div>"
        f'<table class="zcg-table" aria-label="Spatial Atlas Topological Parity Table">'
        f"<thead><tr><th>Node ID</th><th>Label</th><th>Lens Group</th><th>Ring</th>"
        f"<th>Pose (x,y,z)</th><th>Affinity</th></tr></thead><tbody data-atlas-tbody>{rows}</tbody>"
        f"</table></section>"
    )
    if not full_page:
        return frag
    nav_html = SafeHTML(
        '<div class="zcg-tabs">'
        '<a class="zcg-tab" href="/">Workspace (/)</a>'
        '<a class="zcg-tab" href="/admin">Node Admin (/admin)</a>'
        '<a class="zcg-tab" href="/portal?format=html">Public Web (/portal)</a>'
        '<a class="zcg-tab is-active" href="?format=html">Network Atlas</a>'
        '<a class="zcg-tab" href="/auth/session?format=html">Identity &amp; Ring</a>'
        "</div>"
    )
    return (
        TemplateCatalog()
        .render(
            "portal_shell.html",
            {
                "csrf_token": csrf_token,
                "title": "ZeroCloudGravity — 2D/3D Network Atlas",
                "portal_nav": nav_html,
                "portal_content": SafeHTML(frag),
                "portal_footer": SafeHTML(
                    "<span>Interactive 2D/3D Network Atlas · WCAG 2.2 AA Parity</span>"
                ),
            },
        )
        .value
    )


def _parse_explosion(raw: str, fallback: float) -> float:
    try:
        return clamp_explosion_factor(float(raw))
    except ValueError:
        return fallback


def _parse_int(raw: str, fallback: int) -> int:
    try:
        return int(raw)
    except ValueError:
        return fallback


def _raise_action_error(msg: str, code: str, status: HTTPStatus) -> NoReturn:
    raise WebAppError(
        msg,
        error_code=code,
        http_status=int(status),
        severity=ErrorSeverity.WARNING,
        action=ErrorAction.FIX_INPUT,
    )


def create_spatial_atlas_router(
    *,
    presets: Mapping[str, tuple[Sequence[SpatialNodeSpec], Sequence[SpatialEdgeSpec]]]
    | None = None,
    prefix: str = DEFAULT_SPATIAL_ATLAS_PREFIX,
    csrf_token: str = "",
) -> APIRouter:
    """Create a domain-neutral Zone.Z4 2D/3D Exploded-View Spatial Atlas APIRouter."""
    eff_presets = dict(presets) if presets is not None else build_reference_spatial_presets()
    default_key = next(iter(eff_presets))
    router = APIRouter(prefix=prefix, tags=("spatial-atlas",))

    def _build_scene(req: Request) -> tuple[str, str, str, dict[str, Any]]:
        raw_preset = req.query("preset", default_key)
        preset_key = raw_preset if raw_preset in eff_presets else default_key
        raw_lens = req.query("lens", DEFAULT_SPATIAL_LENS)
        lens_key = raw_lens if raw_lens in VALID_SPATIAL_LENSES else DEFAULT_SPATIAL_LENS
        explosion = _parse_explosion(req.query("explosion", "0.25"), 0.25)
        seed = _parse_int(req.query("seed", "42"), 42)
        raw_mode = req.query("mode", "blueprint-3d")
        mode = raw_mode if raw_mode in VALID_SPATIAL_RENDER_MODES else "blueprint-3d"
        nodes, edges = eff_presets[preset_key]
        scene = project_scene_with_lens(nodes, edges, lens=lens_key, explosion=explosion, seed=seed)
        scene["preset"] = preset_key
        scene["render_mode"] = mode
        return preset_key, lens_key, mode, scene

    @router.get("", channel=DeliveryChannel.IMMERSIVE_SYNC, summary="Render Zone.Z4 Spatial Atlas")
    def get_atlas_view(req: Request) -> WebResponse:
        preset_key, lens_key, mode, scene = _build_scene(req)
        names = tuple(eff_presets)
        frag = render_spatial_atlas_html(
            scene,
            preset_names=names,
            active_preset=preset_key,
            active_lens=lens_key,
            mode=mode,
            api_prefix=prefix,
        )
        fmt = req.query("format", "").lower()
        wants_html = fmt == "html" or (
            fmt != "json" and "text/html" in req.headers.get("accept", "").lower()
        )
        full_doc = (
            render_spatial_atlas_html(
                scene,
                preset_names=names,
                active_preset=preset_key,
                active_lens=lens_key,
                mode=mode,
                full_page=True,
                api_prefix=prefix,
                csrf_token=csrf_token,
            )
            if wants_html
            else None
        )
        return respond(
            req,
            html_fragment=frag,
            data=scene,
            full_html=full_doc,
            channel=DeliveryChannel.IMMERSIVE_SYNC,
        )

    @router.get("/scene", channel=DeliveryChannel.IMMERSIVE_SYNC, summary="Topological JSON scene")
    def get_atlas_scene(req: Request) -> WebResponse:
        _, _, _, scene = _build_scene(req)
        return WebResponse(
            int(HTTPStatus.OK),
            JSON_CONTENT_TYPE,
            json.dumps(scene).encode("utf-8"),
            DeliveryChannel.IMMERSIVE_SYNC,
        )

    @router.post("/action", channel=DeliveryChannel.ISLAND_SYNC, summary="Execute +A/-A/±A action")
    def post_proximity_action(req: Request) -> WebResponse:
        if "application/json" in req.content_type.lower():
            parsed = req.json()
            if not isinstance(parsed, dict):
                _raise_action_error(
                    "Spatial action payload must be a JSON object",
                    "INVALID_SPATIAL_ACTION_PAYLOAD",
                    HTTPStatus.BAD_REQUEST,
                )
        else:
            parsed = req.form()
        action = str(parsed.get("action", "")).strip()
        if action not in _ACTION_INTENTS:
            _raise_action_error(
                f"Unsupported proximity action {action!r}",
                "INVALID_PROXIMITY_ACTION",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        source_id = str(parsed.get("source_id", "")).strip()
        target_id = str(parsed.get("target_id", "")).strip()
        if not source_id or not target_id or source_id == target_id:
            _raise_action_error(
                "Distinct non-empty source_id and target_id are required",
                "INVALID_PROXIMITY_ENDPOINTS",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        intent = _ACTION_INTENTS[action]
        receipt = {
            "action": action,
            "intent": intent,
            "source_id": source_id,
            "target_id": target_id,
        }
        frag = (
            f'<div class="zcg-chip" data-spatial-intent="{escape_html(intent)}">'
            f"{escape_html(action)} {escape_html(intent)}: "
            f"{escape_html(source_id)} &rarr; {escape_html(target_id)}</div>"
        )
        return respond(req, html_fragment=frag, data=receipt, channel=DeliveryChannel.ISLAND_SYNC)

    return router
