"""Headless node exposure posture, default ring, and selective Web-Repo veracity classification.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from zcg.core.constants import INDIVIDUAL_MIN_PRECEDENCE, VALID_ENVIRONMENTS
from zcg.core.domain import is_kebab_id

VALID_SURFACE_VERACITY_MODES: Final[tuple[str, ...]] = (
    "full-open-source",
    "curated-public-surface",
    "attestation-only",
)
VALID_TRUST_CIRCLE_OUTWARD_RINGS: Final[tuple[str, ...]] = ("R2", "R1", "R0")
WALLET_AIRLOCK_PRECEDENCE: Final[int] = 88
POSTURE_DEFAULT_RINGS: Final[dict[str, str]] = {
    "public-live": "R0",
    "public-preview": "R2",
    "private-intranet": "R2",
    "private-personal": "R3",
}


def _posture(posture: str, badge: str, audience: str, summary: str) -> dict[str, str]:
    return {"posture": posture, "badge": badge, "audience": audience, "summary": summary}


def classify_exposure_posture(
    manifest: Mapping[str, Any], *, active_env: str = "dev"
) -> dict[str, str]:
    """Classify a node's privacy boundary and cockpit audience from manifest + environment."""
    prec, lrole = (
        int(manifest.get("precedence", 50)),
        str(manifest.get("layer_role") or "department"),
    )
    is_ind = manifest.get("entity_kind") == "individual" or prec >= INDIVIDUAL_MIN_PRECEDENCE
    vis = str(manifest.get("visibility") or ("public" if lrole == "knowledge" else "private"))
    clean_env = active_env.strip().lower() or "dev"
    if vis == "public" and clean_env == "pro":
        return _posture(
            "public-live",
            "Public Sovereign Surface (pro · External Live)",
            "External Visitors & Peer Nodes",
            "Public web/knowledge surface; runtime SQLite WAL stays outside Git.",
        )
    if vis == "public":
        return _posture(
            "public-preview",
            f"Public Twin Preview ({clean_env} · Local Staging)",
            "Pre-Release Curators",
            "Public-target repository inspected locally prior to 'pro' promotion.",
        )
    if is_ind:
        return _posture(
            "private-personal",
            "Private Local Node (Loopback Only)",
            "Sovereign Individual Only",
            "Personal configs, study tracks, and branches never leave this machine.",
        )
    return _posture(
        "private-intranet",
        "Private Enterprise Intranet (RBAC Scoped)",
        "Authorized Internal Members",
        "Internal holding, fiduciary policy, or departmental operations surface.",
    )


def resolve_surface_veracity_mode(manifest: Mapping[str, Any]) -> str:
    """Resolve selective Web-Repo veracity mode without forcing proprietary code exposure."""
    raw_mode = str(manifest.get("surface_veracity_mode") or "").strip().lower()
    if raw_mode in VALID_SURFACE_VERACITY_MODES:
        return raw_mode
    ek = str(manifest.get("entity_kind") or "").strip().lower()
    lid = str(manifest.get("layer_id") or "").strip().lower()
    lrole = str(manifest.get("layer_role") or "").strip().lower()
    vis = str(manifest.get("visibility") or ("public" if lrole == "knowledge" else "private"))
    if ek == "open-source" or (vis == "public" and lid.startswith(("gov-", "geo-", "sci-"))):
        return "full-open-source"
    if vis == "public":
        return "curated-public-surface"
    return "attestation-only"


def resolve_posture_default_ring(posture: str) -> str:
    """Map an exposure posture label to its default capability ring ('R0' | 'R2' | 'R3')."""
    return POSTURE_DEFAULT_RINGS.get(posture, "R2")


def is_public_portal_enabled(
    manifest: Mapping[str, Any] | None, *, active_env: str = "pro"
) -> bool:
    """Return True when /portal is enabled for menu navigation across /, /admin, and /settings."""
    m = manifest if isinstance(manifest, Mapping) else {}
    raw_pe = m.get("public_exposure")
    raw_mode = str(raw_pe.get("mode") or "").strip().lower() if isinstance(raw_pe, Mapping) else ""
    if raw_mode == "disabled":
        return False
    if raw_mode in ("online", "inbox-only", "members-only"):
        return True
    return classify_exposure_posture(m, active_env=active_env)["posture"] != "private-personal"


def resolve_active_env_stages(manifest: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Return real multi-environment promotion stages, or () for purely local-sovereign nodes."""
    m = manifest if isinstance(manifest, Mapping) else {}
    prec = int(m.get("precedence", 50))
    is_ind = str(m.get("entity_kind") or "").strip().lower() == "individual" or (
        prec >= INDIVIDUAL_MIN_PRECEDENCE
    )
    raw_gg, raw_dg = m.get("git_governance"), m.get("domain_governance")
    git_gov: Mapping[str, Any] = raw_gg if isinstance(raw_gg, Mapping) else {}
    dom_gov: Mapping[str, Any] = raw_dg if isinstance(raw_dg, Mapping) else {}
    promo = (
        str(
            m.get("promotion_pipeline")
            or git_gov.get("promotion_pipeline")
            or ("direct" if is_ind else "staged")
        )
        .strip()
        .lower()
    )
    vis = str(m.get("visibility") or "").strip().lower()
    has_remote_deploy = bool(
        is_public_portal_enabled(m)
        or vis == "public"
        or dom_gov.get("canonical_domain")
        or dom_gov.get("intranet_zone")
        or m.get("deployment_provider")
        or "cloud_deployment" in m
        or "container_deployment" in m
    )
    if (is_ind or promo == "direct") and not has_remote_deploy:
        return ()
    raw_order = m.get("environment_promotion_order") or git_gov.get("environment_promotion_order")
    if isinstance(raw_order, list):
        stages = tuple(
            dict.fromkeys(
                s for x in raw_order if (s := str(x).strip().lower()) in VALID_ENVIRONMENTS
            )
        )
        if stages:
            return stages
    return ("dev", "pro") if promo == "direct" else VALID_ENVIRONMENTS


def resolve_co_sovereign_union_contract(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate symmetric co-sovereign peer unions without Lex Superior over personal Root 0."""
    peers_raw: list[str] = []
    raw_co = manifest.get("co_sovereign_peers")
    if isinstance(raw_co, list):
        peers_raw.extend(str(x).strip() for x in raw_co if str(x).strip())
    raw_links = manifest.get("linked_nodes")
    if isinstance(raw_links, list):
        for entry in raw_links:
            if isinstance(entry, Mapping) and str(entry.get("relation") or "") == (
                "co-sovereign-union"
            ):
                nid = str(entry.get("node_id") or entry.get("target_id") or "").strip()
                if nid:
                    peers_raw.append(nid)

    peers = tuple(dict.fromkeys(peers_raw))
    if peers:
        lid = str(manifest.get("layer_id") or "").strip().lower()
        prec = int(manifest.get("precedence", 50))
        if prec == WALLET_AIRLOCK_PRECEDENCE or lid.endswith("-wallet"):
            raise ValueError(
                "WALLET_CO_SOVEREIGN_UNION_FORBIDDEN: R3 wallet airlock cannot join shared unions"
            )
        for pid in peers:
            if not is_kebab_id(pid):
                raise ValueError(f"INVALID_CO_SOVEREIGN_PEER_ID: {pid!r} must match kebab-case")

    return {
        "enabled": bool(peers),
        "peers": peers,
        "lex_superior_over_personal_pc": False,
        "consensus_mode": "symmetric-peer-consent",
    }


def compile_local_trust_circle_grants(manifest: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """Project local R3 trust circles into anonymous outward R2/R1 email grants (0% label leak)."""
    raw_circles = manifest.get("local_trust_circles")
    entries: list[Any]
    if isinstance(raw_circles, Mapping):
        entries = list(raw_circles.values())
    elif isinstance(raw_circles, list):
        entries = raw_circles
    else:
        entries = []

    r2_emails: list[str] = []
    r1_emails: list[str] = []
    for item in entries:
        if not isinstance(item, Mapping):
            continue
        ring = str(item.get("outward_ring") or "R1").strip().upper()
        if ring not in VALID_TRUST_CIRCLE_OUTWARD_RINGS:
            raise ValueError(
                f"TRUST_CIRCLE_R3_EXPORT_FORBIDDEN: outward_ring {ring!r} cannot export R3 access"
            )
        raw_emails = item.get("emails")
        if not isinstance(raw_emails, list):
            continue
        cleaned = [str(e).strip() for e in raw_emails if str(e).strip()]
        if ring == "R2":
            r2_emails.extend(cleaned)
        elif ring == "R1":
            r1_emails.extend(cleaned)

    return {
        "r2_member_emails": tuple(dict.fromkeys(r2_emails)),
        "r1_scoped_external_emails": tuple(dict.fromkeys(r1_emails)),
    }
