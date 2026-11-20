"""Vendor-neutral node capability ring (R0..R3) compilation, OIDC/portal wiring, and CDN routing.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.routing import network_auth
from zcg.cockpit.routing.provenance import resolve_domain_governance
from zcg.cockpit.views.spatial_bridge import build_live_node_spatial_presets
from zcg.core.constants import DEFAULT_PLUGIN_BASE_PORT
from zcg.core.manifests import load_node_manifest
from zcg.governance.policy.egress import resolve_effective_egress_policy
from zcg.platform.projection import (
    ExchangeStage,
    PayloadFieldSegment,
    ProjectedRoleCapsule,
    RolePayloadProjector,
)
from zcg.plugins.portal_cv import resolve_entity_portal_kind
from zcg.plugins.public_portals import create_public_portal_router
from zcg.providers.oidc_presets import resolve_oidc_provider_endpoints
from zcg.topology.exposure import classify_exposure_posture, compile_local_trust_circle_grants
from zcg.topology.identity import resolve_node_entity_identity
from zcg.web.auth.oidc_session import OidcSessionConfig, create_oidc_session_router
from zcg.web.auth.surface_access import (
    DEFAULT_RATE_LIMIT_REQUESTS,
    DEFAULT_RATE_LIMIT_WINDOW_SEC,
    VALID_DISCLOSURE_TIERS,
    ExternalSubjectKind,
    RingRouteRule,
    SlidingWindowRateLimiter,
    SurfaceAccessPolicy,
    SurfaceRing,
)
from zcg.web.http.router import APIRouter

_POSTURE_DEFAULT_RINGS: Final[dict[str, SurfaceRing]] = {
    "public-live": SurfaceRing.R0_PUBLIC,
    "public-preview": SurfaceRing.R2_NETWORK_MEMBER,
    "private-intranet": SurfaceRing.R2_NETWORK_MEMBER,
    "private-personal": SurfaceRing.R3_OPERATOR,
}
_TIER_STAGE_MAP: Final[dict[str, tuple[ExchangeStage, float]]] = {
    "core_summary": (ExchangeStage.PUBLIC_OVERVIEW, 1.0),
    "verified_competency": (ExchangeStage.B2B_PROPOSAL, 1.0),
    "day1_onboarding": (ExchangeStage.DAY1_ONBOARDING, 1.0),
    "deep_context": (ExchangeStage.DAY1_ONBOARDING, 0.0),
}
_RING_ALIASES: Final[dict[str, SurfaceRing]] = {
    "r0": SurfaceRing.R0_PUBLIC,
    "public": SurfaceRing.R0_PUBLIC,
    "r1": SurfaceRing.R1_SCOPED_EXTERNAL,
    "scoped-external": SurfaceRing.R1_SCOPED_EXTERNAL,
    "r2": SurfaceRing.R2_NETWORK_MEMBER,
    "network-member": SurfaceRing.R2_NETWORK_MEMBER,
    "r3": SurfaceRing.R3_OPERATOR,
    "operator": SurfaceRing.R3_OPERATOR,
}


def _parse_ring(raw_val: object, fallback: SurfaceRing) -> SurfaceRing:
    return _RING_ALIASES.get(str(raw_val or "").strip().lower(), fallback)


def _str_tuple(raw_val: object) -> tuple[str, ...]:
    return (
        tuple(str(x).strip() for x in raw_val if str(x).strip())
        if isinstance(raw_val, list)
        else ()
    )


def _csv_env(env: Mapping[str, str], key: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in env.get(key, "").split(",") if x.strip())


def _dedup(*seqs: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(x for seq in seqs for x in seq if x))


def _merge_iam_lists(
    manifest: Mapping[str, Any],
    raw_sa: Mapping[str, Any],
    eff_env: Mapping[str, str],
    *,
    inherited_auth: Sequence[str] = (),
) -> dict[str, tuple[str, ...]]:
    auth_doc = manifest.get("layer_authority")
    loc_e = _str_tuple(auth_doc.get("authorized_emails")) if isinstance(auth_doc, Mapping) else ()
    base_e = tuple(inherited_auth) if inherited_auth else loc_e
    inh = base_e if bool(raw_sa.get("inherit_layer_authority", True)) else ()
    circles = compile_local_trust_circle_grants(manifest)
    return {
        "operators": _dedup(
            inh, _str_tuple(raw_sa.get("operator_emails")), _csv_env(eff_env, "ZCG_OPERATOR_EMAILS")
        ),
        "members": _dedup(
            _str_tuple(raw_sa.get("member_emails")),
            circles["r2_member_emails"],
            _csv_env(eff_env, "ZCG_MEMBER_EMAILS"),
        ),
        "externals": _dedup(
            _str_tuple(raw_sa.get("scoped_external_emails")),
            circles["r1_scoped_external_emails"],
            _csv_env(eff_env, "ZCG_SCOPED_EXTERNAL_EMAILS"),
        ),
        "domains": _dedup(
            _str_tuple(raw_sa.get("allowed_workspace_domains")),
            _csv_env(eff_env, "ZCG_WORKSPACE_DOMAINS"),
        ),
        "groups": _dedup(
            _str_tuple(raw_sa.get("allowed_workspace_groups")),
            _csv_env(eff_env, "ZCG_WORKSPACE_GROUPS"),
        ),
    }


def resolve_deployment_target_summary(
    manifest: Mapping[str, Any], *, active_env: str = "dev"
) -> dict[str, Any]:
    """Resolve vendor-neutral deployment target summary ('local-sovereign' by default)."""
    act_env = active_env.strip().lower() or "dev"
    raw_tpls = manifest.get("default_stack_templates")
    def_tpls = (
        {str(x).strip() for x in raw_tpls if str(x).strip()}
        if isinstance(raw_tpls, list)
        else set()
    )
    is_workstation_catalog = str(manifest.get("layer_role") or "") == "workstation"
    explicit_provider = str(manifest.get("deployment_provider") or "").strip().lower()

    if (
        explicit_provider == "google-cloud-iac"
        or "cloud_deployment" in manifest
        or (not is_workstation_catalog and "google-cloud-iac" in def_tpls)
    ):
        stage = (
            "local-cockpit"
            if act_env == "dev"
            else ("production-cloud-run-gke" if act_env == "pro" else "staging-cloud-deploy")
        )
        return {
            "provider": "google-cloud-iac",
            "environment": act_env,
            "stage": stage,
            "iac_manifest": f"surfaces/infra/cloud_deployment_{act_env}.json",
        }
    if (
        explicit_provider == "self-hosted-container"
        or "container_deployment" in manifest
        or (not is_workstation_catalog and "self-hosted-container" in def_tpls)
    ):
        stage = (
            "local-cockpit"
            if act_env == "dev"
            else ("production-container-edge" if act_env == "pro" else "staging-container-edge")
        )
        return {
            "provider": "self-hosted-container",
            "environment": act_env,
            "stage": stage,
            "iac_manifest": f"surfaces/infra/container_deployment_{act_env}.json",
        }
    return {
        "provider": "local-sovereign",
        "environment": act_env,
        "stage": "local-loopback-w3c",
        "iac_manifest": "none",
    }


def compile_node_surface_access_policy(
    workspace_dir: Path,
    manifest: Mapping[str, Any] | None = None,
    *,
    active_env: str = "dev",
    env_vars: Mapping[str, str] | None = None,
    default_session_key: str = "",
) -> SurfaceAccessPolicy | None:
    """Compile Root 0 + node surface_access and IAM env vars into SurfaceAccessPolicy."""
    ws = workspace_dir.resolve()
    m = dict(manifest) if manifest is not None else load_node_manifest(ws)
    inh_net = network_auth.resolve_inherited_network_access(ws, m)
    if not inh_net["has_surface_access"]:
        return None
    raw_sa: Mapping[str, Any] = inh_net["surface_access"]
    eff_env = os.environ if env_vars is None else env_vars
    posture = classify_exposure_posture(m, active_env=active_env)["posture"]
    p_ring = _POSTURE_DEFAULT_RINGS.get(posture, SurfaceRing.R2_NETWORK_MEMBER)
    def_ring = _parse_ring(raw_sa.get("default_ring"), p_ring)
    ext_by_val = {k.value: k for k in ExternalSubjectKind}
    rules: list[RingRouteRule] = []
    for item in raw_sa.get("route_rules") or ():
        if not isinstance(item, Mapping):
            continue
        pat = str(item.get("path_pattern") or item.get("path") or "").strip()
        if not pat:
            continue
        raw_ext = _str_tuple(item.get("allowed_external_subjects"))
        ext_tup = tuple(ext_by_val[e] for e in raw_ext if e in ext_by_val) or (
            ExternalSubjectKind.GUEST,
            ExternalSubjectKind.LINKED_PEER,
        )
        rules.append(
            RingRouteRule(
                pat,
                _parse_ring(item.get("ring"), def_ring),
                methods=_str_tuple(item.get("methods")) or ("*",),
                allowed_external_subjects=ext_tup,
                disclosure_tier=str(item.get("disclosure_tier") or "").strip(),
                required_groups=_str_tuple(item.get("required_groups")),
            )
        )
    if bool(raw_sa.get("protect_mutating_ops", posture == "public-live")):
        rules.append(RingRouteRule("/api/modules/work-ledger*", SurfaceRing.R3_OPERATOR))
    stg_gate = (
        posture == "public-preview"
        and active_env.strip().lower() in ("tst", "pre")
        and bool(raw_sa.get("protect_staging_portal", True))
    )
    portal_ring = SurfaceRing.R1_SCOPED_EXTERNAL if stg_gate else SurfaceRing.R0_PUBLIC
    if posture.startswith("public"):
        rules.append(
            RingRouteRule(
                "/api/modules/spatial-atlas*", portal_ring, methods=("GET", "HEAD", "OPTIONS")
            )
        )
    rules.extend((
        RingRouteRule("/portal*", portal_ring, methods=("GET", "HEAD", "OPTIONS")),
        RingRouteRule("/portal/contact", portal_ring, methods=("POST",)),
        RingRouteRule("/portal/handshake", portal_ring, methods=("POST",)),
        RingRouteRule("/auth/*", SurfaceRing.R0_PUBLIC),
        RingRouteRule("/settings", SurfaceRing.R1_SCOPED_EXTERNAL),
        RingRouteRule("/admin*", SurfaceRing.R3_OPERATOR),
        RingRouteRule("/api/appearance", SurfaceRing.R0_PUBLIC, methods=("GET", "HEAD")),
        RingRouteRule("/api/appearance/viewer-prefs", SurfaceRing.R0_PUBLIC, methods=("POST",)),
        RingRouteRule("/api/appearance/node-theme", SurfaceRing.R3_OPERATOR, methods=("POST",)),
        RingRouteRule("/api/modules/portal-inbox*", SurfaceRing.R3_OPERATOR),
    ))  # fmt: skip
    iam = _merge_iam_lists(m, raw_sa, eff_env, inherited_auth=inh_net["authorized_emails"])
    raw_peers = raw_sa.get("allowed_linked_peers")
    p_items = raw_peers.items() if isinstance(raw_peers, Mapping) else ()
    peers = {
        str(k).strip(): str(v).strip() for k, v in p_items if str(k).strip() and str(v).strip()
    }
    sess_key, _ = network_auth.resolve_network_session_material(
        ws, m, env_vars=eff_env, fallback_key=default_session_key
    )
    oidc_ep = resolve_oidc_provider_endpoints(raw_sa, eff_env)
    rl_req = int(raw_sa.get("r0_rate_limit_requests") or DEFAULT_RATE_LIMIT_REQUESTS)
    rl_win = float(raw_sa.get("r0_rate_limit_window_sec") or DEFAULT_RATE_LIMIT_WINDOW_SEC)
    def_bypass = active_env == "dev" or posture == "private-personal"
    return SurfaceAccessPolicy(
        default_ring=def_ring, rules=rules, session_key=sess_key, allowed_linked_peers=peers,
        peer_allowed_routes=_str_tuple(raw_sa.get("peer_allowed_routes")) or ("*",),
        oidc_expected_audience=oidc_ep.expected_audience, oidc_assertion_key=oidc_ep.assertion_key,
        oidc_allowed_issuers=oidc_ep.allowed_issuers, proxy_jwt_headers=oidc_ep.proxy_jwt_headers,
        infer_domain_from_email=oidc_ep.infer_domain_from_email,
        domain_infer_issuers=oidc_ep.domain_infer_issuers,
        allowed_workspace_domains=iam["domains"], allowed_workspace_groups=iam["groups"],
        operator_emails=iam["operators"], member_emails=iam["members"],
        scoped_external_emails=iam["externals"],
        loopback_operator_bypass=bool(raw_sa.get("loopback_operator_bypass", def_bypass)),
        r0_rate_limiter=SlidingWindowRateLimiter(max_requests=rl_req, window_sec=rl_win),
    )  # fmt: skip


def build_node_oidc_and_portal_routers(
    workspace_dir: Path,
    *,
    csrf_token: str,
    active_env: str = "dev",
    policy: SurfaceAccessPolicy | None = None,
    env_vars: Mapping[str, str] | None = None,
) -> tuple[APIRouter, APIRouter]:
    """Instantiate node-parameterized (/auth/*, /portal*) routers across 3 entity kinds."""
    ws = workspace_dir.resolve()
    m = load_node_manifest(ws)
    eff_env = os.environ if env_vars is None else env_vars
    lid = str(m.get("layer_id") or ws.name)
    ek = str(resolve_node_entity_identity(ws, m)["entity_kind"]) if m else "open-source"
    p_kind = resolve_entity_portal_kind(m, ek)
    port = int(m.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + int(m.get("precedence", 50))))
    dg = resolve_domain_governance(
        m, layer_id=lid, active_env=active_env, port=port, workspace_dir=ws
    )["domain_governance"]
    ldz = str(dg["local_dev_zone"])
    def_cd = "zerocloudgravity.org" if ek == "open-source" else ldz
    def_sd = "zerocloudgravity.dev" if ek == "open-source" else f"intra.{def_cd}"
    c_dom = str(dg["canonical_domain"] or def_cd).strip()
    s_dom = str(dg["intranet_zone"] or dg["developer_domain"] or def_sd).strip()
    inh_net = network_auth.resolve_inherited_network_access(ws, m)
    sa_map: Mapping[str, Any] = inh_net["surface_access"]
    iam = _merge_iam_lists(m, sa_map, eff_env, inherited_auth=inh_net["authorized_emails"])
    sess_k, c_doms = network_auth.resolve_network_session_material(
        ws, m, intranet_zone=str(dg["intranet_zone"] or ""), local_dev_zone=ldz,
        env_vars=eff_env, fallback_key=csrf_token,
    )  # fmt: skip
    qa_sw = (
        active_env == "dev"
        or network_auth.is_private_personal_node(m)
        or eff_env.get("ZCG_LOCAL_QA_SWITCH", "").strip() == "1"
    )
    portal_pol = policy or SurfaceAccessPolicy(
        default_ring=SurfaceRing.R0_PUBLIC, session_key=sess_k
    )
    oidc_ep = resolve_oidc_provider_endpoints(sa_map, eff_env)
    oidc_cfg = OidcSessionConfig(
        session_signing_key=sess_k, provider_id=oidc_ep.provider_id,
        provider_label=oidc_ep.provider_label,
        authorization_endpoint=oidc_ep.authorization_endpoint,
        allowed_issuers=oidc_ep.allowed_issuers, client_id=oidc_ep.client_id,
        domain_hint=iam["domains"][0] if len(iam["domains"]) == 1 else "",
        domain_hint_param=oidc_ep.domain_hint_param,
        infer_domain_from_email=oidc_ep.infer_domain_from_email,
        domain_infer_issuers=oidc_ep.domain_infer_issuers,
        expected_audience=oidc_ep.expected_audience, jwt_assertion_key=oidc_ep.assertion_key,
        allowed_workspace_domains=iam["domains"], allowed_workspace_groups=iam["groups"],
        operator_emails=iam["operators"], member_emails=iam["members"],
        scoped_external_emails=iam["externals"], cookie_domains=c_doms,
        allow_dev_persona_switch=qa_sw,
    )  # fmt: skip
    return (
        create_oidc_session_router(oidc_cfg, policy=portal_pol, csrf_token=csrf_token),
        create_public_portal_router(
            portal_kind=p_kind, node_id=lid, canonical_domain=c_dom, secondary_domain=s_dom,
            workspace_dir=ws, policy=portal_pol, csrf_token=csrf_token, active_env=active_env,
            spatial_presets=build_live_node_spatial_presets(ws),
            login_enabled=oidc_cfg.login_enabled,
        ),
    )  # fmt: skip


def resolve_node_cdn_origins(
    workspace_dir: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
    active_env: str = "dev",
) -> tuple[str, ...]:
    """Resolve governed HTTPS/loopback CDN origins for a sovereign node."""
    ws = workspace_dir.resolve()
    m = dict(manifest) if manifest is not None else load_node_manifest(ws)
    lid = str(m.get("layer_id") or ws.name)
    port = int(m.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + int(m.get("precedence", 50))))
    dg = resolve_domain_governance(
        m, layer_id=lid, active_env=active_env, port=port, workspace_dir=ws
    )["domain_governance"]
    c_dom = str(dg["canonical_domain"] or "").strip()
    return resolve_effective_egress_policy(ws, manifest=m, canonical_domain=c_dom).cdn_origins


def project_ring_scoped_capsule(
    *,
    resource_id: str,
    target_node_id: str,
    effective_disclosure_tier: str,
    segments: Sequence[PayloadFieldSegment],
    shared_packs: Sequence[str] = (),
) -> ProjectedRoleCapsule:
    """Filter sovereign payload segments to the caller's R0..R3 DisclosureTier ceiling."""
    clean_tier = effective_disclosure_tier.strip()
    if clean_tier not in VALID_DISCLOSURE_TIERS:
        raise ValueError(f"Invalid effective_disclosure_tier {effective_disclosure_tier!r}")
    stage, drop_rate = _TIER_STAGE_MAP[clean_tier]
    return RolePayloadProjector().project(
        resource_id=resource_id,
        target_node_id=target_node_id,
        stage=stage,
        segments=segments,
        drop_off_rate=drop_rate,
        shared_packs=shared_packs,
    )
