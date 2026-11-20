"""Four-archetype public R0 web portals over base.html and ring-projected CV A4 print/exports.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

from zcg.core.manifests import load_node_manifest
from zcg.plugins.portal_channels import (
    build_portal_channels_context,
    create_portal_channels_router,
)
from zcg.plugins.portal_cv import (
    CVProfileSpec,
    portal_template_catalog,
    project_cv_by_disclosure_tier,
    render_cv_markdown,
    render_cv_print_a4_html,
    resolve_personal_hub_context,
    resolve_workspace_cv_profile,
)
from zcg.plugins.portal_inbox import build_public_exposure_context, check_workspace_portal_exposure
from zcg.plugins.wallet_ledger import export_r0_public_stewardship_snapshot
from zcg.plugins.wallet_treasury import WalletRuntimeStore
from zcg.web.auth.surface_access import (
    DISCLOSURE_TIER_HEADER,
    RING_DEFAULT_DISCLOSURE_TIER,
    SURFACE_RING_HEADER,
    VALID_DISCLOSURE_TIERS,
    SurfaceAccessPolicy,
    SurfaceRing,
)
from zcg.web.capabilities.appearance import build_appearance_template_context
from zcg.web.capabilities.spatial_atlas import render_spatial_atlas_html
from zcg.web.capabilities.spatial_layout import (
    SpatialEdgeSpec,
    SpatialNodeSpec,
    build_reference_spatial_presets,
    compute_exploded_scene_layout,
)
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import HTML_CONTENT_TYPE, JSON_CONTENT_TYPE, Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.templates import SafeHTML, render_icon

_PORTAL_TITLES: Final[dict[str, str]] = {
    "oss-flagship-portal": "ZeroCloudGravity — Verifiable Zero-Cloud Sovereign Architecture",
    "personal-constellation-hub": "Personal Sovereign Hub & Delegated Pillar Subdomains",
    "personal-portfolio-cv": "Sovereign Portfolio & Ring-Projected Curriculum Vitae",
    "corporate-brand-portal": "Enterprise Fiduciary Portal & Departmental Intranet Gateway",
}
VALID_PORTAL_KINDS: Final[tuple[str, ...]] = tuple(_PORTAL_TITLES)
MARKDOWN_CONTENT_TYPE: Final[str] = "text/markdown; charset=utf-8"

type SpatialPresetMap = Mapping[str, tuple[Sequence[SpatialNodeSpec], Sequence[SpatialEdgeSpec]]]


def _portal_nav_links(
    portal_kind: str, clean_pref: str, *, has_contact: bool = True, has_facets: bool = False
) -> list[dict[str, str]]:
    contact_tail = [{"label": "Contact", "href": "#contact"}] if has_contact else []
    if portal_kind == "oss-flagship-portal":
        return [
            {"label": "Platform", "href": "#overview"},
            {"label": "3D Mesh", "href": "#atlas"},
            {"label": "Directory", "href": "#directory"},
            {"label": "Stewardship", "href": f"{clean_pref}/stewardship"},
            *contact_tail,
        ]
    if portal_kind == "personal-constellation-hub":
        facet_nav = (
            [{"label": "Subdomains & Pillars", "href": "#constellation"}] if has_facets else []
        )
        return [*facet_nav, *contact_tail]
    if portal_kind == "personal-portfolio-cv":
        return [{"label": "Download CV", "href": f"{clean_pref}/cv/print"}, *contact_tail]
    return [
        {"label": "Organization", "href": "#overview"},
        {"label": "Intranet", "href": "#gateway"},
        *contact_tail,
    ]


def _build_portal_atlas_embed(presets: SpatialPresetMap | None, csrf_token: str) -> str:
    eff = dict(presets) if presets is not None else build_reference_spatial_presets()
    key = next(iter(eff))
    scene = compute_exploded_scene_layout(*eff[key], explosion=0.25, seed=42)
    scene["preset"] = key
    return render_spatial_atlas_html(
        scene,
        preset_names=tuple(eff),
        active_preset=key,
        api_prefix="/api/modules/spatial-atlas",
        csrf_token=csrf_token,
    )


def render_public_portal_html(
    *,
    portal_kind: str,
    node_id: str,
    canonical_domain: str,
    secondary_domain: str = "",
    caller_ring: str = "R0",
    effective_tier: str = "core_summary",
    cv_projected: Mapping[str, Any] | None = None,
    prefix: str = "/portal",
    full_page: bool = False,
    csrf_token: str = "",
    spatial_atlas_html: str = "",
    manifest: Mapping[str, Any] | None = None,
    workspace_dir: Path | None = None,
    active_env: str = "pro",
    cookies: Mapping[str, str] | None = None,
    allow_node_theme: bool = False,
    login_enabled: bool = True,
) -> SafeHTML:
    """Render base.html-backed public R0 portal HTML for OSS, Hub, Personal CV, or Enterprise."""
    if portal_kind not in VALID_PORTAL_KINDS:
        raise ValueError(f"Unsupported portal_kind {portal_kind!r}; valid={VALID_PORTAL_KINDS}")
    clean_pref = prefix.rstrip("/")
    is_oss = portal_kind == "oss-flagship-portal"
    is_hub = portal_kind == "personal-constellation-hub"
    is_cv = portal_kind == "personal-portfolio-cv"
    atlas_blk = (
        (spatial_atlas_html or _build_portal_atlas_embed(None, csrf_token)) if is_oss else ""
    )
    proj: Mapping[str, Any] = {}
    if is_cv:
        d_cv = resolve_workspace_cv_profile(
            workspace_dir, manifest, node_id=node_id, public_domain=canonical_domain
        )
        proj = cv_projected or project_cv_by_disclosure_tier(d_cv, effective_tier=effective_tier)
    ch_ctx = build_portal_channels_context(
        manifest, portal_kind=portal_kind, canonical_domain=canonical_domain
    )
    exp_ctx = build_public_exposure_context(manifest)
    hub_ctx = (
        resolve_personal_hub_context(
            workspace_dir,
            manifest,
            node_id=node_id,
            canonical_domain=canonical_domain,
            base_facets=exp_ctx["public_facets"],
        )
        if is_hub
        else {"hub_title": "", "hub_summary": "", "public_facets": exp_ctx["public_facets"]}
    )
    eff_facets = hub_ctx["public_facets"]
    has_any_ch = bool(
        ch_ctx["social_links"]
        or ch_ctx["contact_phone"]
        or ch_ctx["contact_email"]
        or ch_ctx["peer_handshake_enabled"]
    )
    has_contact = exp_ctx["exposure_mode"] != "disabled" and has_any_ch
    catalog = portal_template_catalog()
    frag = catalog.render(
        "public_portal.html",
        {
            "portal_kind": portal_kind,
            "node_id": node_id,
            "canonical_domain": canonical_domain,
            "secondary_domain": secondary_domain or canonical_domain,
            "caller_ring": caller_ring,
            "effective_tier": effective_tier,
            "clean_prefix": clean_pref,
            "is_oss": is_oss,
            "is_hub": is_hub,
            "is_cv": is_cv,
            "is_corp": portal_kind == "corporate-brand-portal",
            "has_contact": has_contact,
            "hub_title": hub_ctx["hub_title"],
            "hub_summary": hub_ctx["hub_summary"],
            "spatial_atlas_safe": SafeHTML(atlas_blk),
            **ch_ctx,
            **exp_ctx,
            "public_facets": eff_facets,
            "cv_full_name": str(proj.get("full_name", "")),
            "cv_headline": str(proj.get("headline", "")),
            "cv_public_contact": str(proj.get("public_contact", "")),
            "cv_withheld_count": int(proj.get("withheld_count", 0)),
            "cv_entries": list(proj.get("disclosed_entries", ())),
        },
    )
    if not full_page:
        return frag
    disp_dom = canonical_domain.strip() or node_id
    cdom_h, ring_h = html.escape(disp_dom), html.escape(caller_ring)
    ftr = SafeHTML(
        "<div class='zcg-provenance-footer' data-zcg-provenance='portal-footer'>"
        f"<div class='zcg-provenance-footer__left'><span>© 2026 <strong>{cdom_h}</strong> · "
        f"Ring <code>{ring_h}</code></span></div>"
        "<div class='zcg-provenance-footer__right'>"
        f"<a href='/.well-known/zcg-attestation.json'>{render_icon('shield')}"
        "Verified Surface Attestation</a></div></div>"
    )
    p_base = clean_pref or "/portal"
    app_ctx = build_appearance_template_context(
        manifest=manifest,
        cookies=cookies,
        plane="public_portal",
        active_env=active_env,
        caller_ring=caller_ring,
        allow_node_theme=allow_node_theme,
        env_urls={e: f"{p_base}?format=html&env={e}" for e in ("dev", "tst", "pre", "pro")},
    )
    nav_links = _portal_nav_links(
        portal_kind, clean_pref, has_contact=has_contact, has_facets=bool(eff_facets)
    )
    return catalog.render(
        "portal_shell.html",
        {
            "csrf_token": csrf_token,
            "title": _PORTAL_TITLES[portal_kind],
            "brand_name": node_id,
            "canonical_domain": canonical_domain,
            "display_domain": disp_dom,
            "clean_prefix": clean_pref or "/",
            "caller_ring": caller_ring,
            "is_signed_in": caller_ring != "R0",
            "is_operator_ring": caller_ring in ("R2", "R3"),
            "login_enabled": login_enabled,
            "nav_links": nav_links,
            "portal_content": frag,
            "portal_footer": ftr,
            **app_ctx,
        },
    )


def create_public_portal_router(
    *,
    portal_kind: str = "oss-flagship-portal",
    node_id: str = "zerocloudgravity",
    canonical_domain: str = "zerocloudgravity.org",
    secondary_domain: str = "zerocloudgravity.dev",
    cv_profile: CVProfileSpec | None = None,
    workspace_dir: Path | None = None,
    policy: SurfaceAccessPolicy | None = None,
    prefix: str = "/portal",
    csrf_token: str = "",
    active_env: str = "pro",
    spatial_presets: SpatialPresetMap | None = None,
    login_enabled: bool = True,
) -> APIRouter:
    """Create composable public R0 portal, stewardship, and CV download APIRouter."""
    if portal_kind not in VALID_PORTAL_KINDS:
        raise ValueError(f"Unsupported portal_kind {portal_kind!r}; valid={VALID_PORTAL_KINDS}")
    clean_pref = prefix.rstrip("/") or "/portal"
    is_oss = portal_kind == "oss-flagship-portal"
    atlas_s = _build_portal_atlas_embed(spatial_presets, csrf_token) if is_oss else ""
    router = APIRouter(prefix=clean_pref, tags=("public-portal",))

    def _caller_ring_and_tier(req: Request) -> tuple[str, str]:
        if policy is not None:
            host = req.headers.get("host", "").partition(":")[0].strip().lower().strip("[]")
            p = policy.authenticate_request(
                headers=req.headers, cookies=req.cookies, client_host=host
            )
            r_code, tier = p.ring.value, p.max_disclosure_tier
        else:
            raw_r = req.headers.get(SURFACE_RING_HEADER, "R0").strip().upper()
            r_enum = {r.value: r for r in SurfaceRing}.get(raw_r, SurfaceRing.R0_PUBLIC)
            raw_t = req.headers.get(DISCLOSURE_TIER_HEADER, "").strip()
            r_code, def_t = r_enum.value, RING_DEFAULT_DISCLOSURE_TIER[r_enum]
            tier = raw_t if raw_t in VALID_DISCLOSURE_TIERS else def_t
        q_tier = req.query("tier", "").strip()
        return r_code, (q_tier if r_code == "R3" and q_tier in VALID_DISCLOSURE_TIERS else tier)

    def _live_cv(live_man: Mapping[str, Any]) -> CVProfileSpec:
        return cv_profile or resolve_workspace_cv_profile(
            workspace_dir, live_man, node_id=node_id, public_domain=canonical_domain
        )

    def _render_portal_pair(
        req: Request, r_code: str, tier: str, live_man: Mapping[str, Any], full: bool
    ) -> SafeHTML:
        q_env = req.query("env", "").strip().lower() or active_env
        proj = project_cv_by_disclosure_tier(_live_cv(live_man), effective_tier=tier)
        return render_public_portal_html(
            portal_kind=portal_kind,
            node_id=node_id,
            canonical_domain=canonical_domain,
            secondary_domain=secondary_domain,
            caller_ring=r_code,
            effective_tier=tier,
            cv_projected=proj,
            prefix=clean_pref,
            full_page=full,
            csrf_token=csrf_token,
            spatial_atlas_html=atlas_s,
            manifest=live_man,
            workspace_dir=workspace_dir,
            active_env=q_env,
            cookies=req.cookies,
            allow_node_theme=workspace_dir is not None,
            login_enabled=login_enabled,
        )

    def _guard_exp(req: Request) -> None:
        check_workspace_portal_exposure(workspace_dir, caller_ring=_caller_ring_and_tier(req)[0])

    @router.get("", channel=DeliveryChannel.ISLAND_SYNC, summary="Serve public R0 entity portal")
    def get_portal(req: Request) -> WebResponse:
        r_code, tier = _caller_ring_and_tier(req)
        check_workspace_portal_exposure(workspace_dir, caller_ring=r_code)
        live_man = load_node_manifest(workspace_dir) if workspace_dir is not None else {}
        frag = _render_portal_pair(req, r_code, tier, live_man, False)
        fmt = req.query("format", "").lower()
        accept_h = "text/html" in req.headers.get("accept", "").lower()
        wants_html = fmt == "html" or (fmt != "json" and accept_h)
        full_doc = (
            str(_render_portal_pair(req, r_code, tier, live_man, True)) if wants_html else None
        )
        data = {
            "portal_kind": portal_kind,
            "node_id": node_id,
            "canonical_domain": canonical_domain,
            "secondary_domain": secondary_domain,
            "caller_ring": r_code,
            "effective_tier": tier,
        }
        return respond(req, html_fragment=str(frag), data=data, full_html=full_doc)

    @router.get("/stewardship", channel=DeliveryChannel.SWAP_SYNC, summary="Public R0 stewardship")
    def get_stewardship(req: Request) -> WebResponse:
        store = WalletRuntimeStore(workspace_dir) if workspace_dir is not None else None
        addrs = store.list_watch_addresses(ring_mode="R0") if store is not None else ()
        rcpts = store.list_receipts(ring_mode="R0") if store is not None else ()
        snap = export_r0_public_stewardship_snapshot(
            node_id=node_id, public_watch_accounts=addrs, receipts=rcpts
        )
        n_res, n_rcp = len(snap["public_reserve_accounts"]), len(snap["verified_public_receipts"])
        frag = (
            f"<section class='zcg-card' data-zcg-stewardship='R0'><h3>{render_icon('vault')} "
            "Public R0 Stewardship &amp; Verifiable Patronage</h3><p>Reserve Accounts: "
            f"<code>{n_res}</code> · Verified Receipts: <code>{n_rcp}</code></p></section>"
        )
        return respond(req, html_fragment=frag, data=snap)

    def _dl(ct: str, body: bytes, ext: str = "", tier: str = "") -> WebResponse:
        fn = f'attachment; filename="{node_id}-cv-{tier}.{ext}"'
        h = {"content-disposition": fn} if ext else {}
        return WebResponse(int(HTTPStatus.OK), ct, body, DeliveryChannel.STATIC_SYNC, h)

    def _cv_proj(req: Request) -> tuple[str, dict[str, Any]]:
        _, tier = _caller_ring_and_tier(req)
        live_man = load_node_manifest(workspace_dir) if workspace_dir is not None else {}
        return tier, project_cv_by_disclosure_tier(_live_cv(live_man), effective_tier=tier)

    @router.get("/cv", channel=DeliveryChannel.SWAP_SYNC, summary="Inspect ring-projected CV")
    def get_projected_cv(req: Request) -> WebResponse:
        _, proj = _cv_proj(req)
        frag = f"<div class='zcg-card'><strong>{html.escape(proj['full_name'])}</strong></div>"
        return respond(req, html_fragment=frag, data=proj)

    @router.get("/cv/print", channel=DeliveryChannel.STATIC_SYNC, summary="Print A4 PDF-ready CV")
    def print_cv_a4(req: Request) -> WebResponse:
        doc = render_cv_print_a4_html(_cv_proj(req)[1], prefix=clean_pref)
        return _dl(HTML_CONTENT_TYPE, str(doc).encode("utf-8"))

    @router.get("/cv/download.md", channel=DeliveryChannel.STATIC_SYNC, summary="Download CV .md")
    def download_cv_markdown(req: Request) -> WebResponse:
        tier, proj = _cv_proj(req)
        return _dl(MARKDOWN_CONTENT_TYPE, render_cv_markdown(proj).encode("utf-8"), "md", tier)

    @router.get("/cv/download.json", channel=DeliveryChannel.STATIC_SYNC, summary="Download CV")
    def download_cv_json(req: Request) -> WebResponse:
        tier, proj = _cv_proj(req)
        body = (json.dumps(proj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        return _dl(JSON_CONTENT_TYPE, body, "json", tier)

    ch_r = create_portal_channels_router(workspace_dir=workspace_dir, exposure_guard=_guard_exp)
    router.include_router(ch_r)
    return router
