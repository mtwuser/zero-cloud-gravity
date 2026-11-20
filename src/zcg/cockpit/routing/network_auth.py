"""Root 0 network membership inheritance, shared SSO session material, and environment defaults.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.routing.provenance import MAX_GOVERNANCE_HOPS
from zcg.core.constants import (
    INDIVIDUAL_MIN_PRECEDENCE,
    NODE_MANIFEST_REL_PATH,
    OSS_WORKSTATION_IDS,
    REPO_DIR,
    VALID_ENVIRONMENTS,
)
from zcg.core.manifests import load_node_manifest
from zcg.topology.identity import resolve_default_parent_dir

_VERSION_FILE: Final[Path] = REPO_DIR / "VERSION"
NETWORK_SESSION_KEY_REL_PATH: Final[str] = ".zcg/runtime/network_session.key"
PRIVATE_KEY_FILE_MODE: Final[int] = stat.S_IRUSR | stat.S_IWUSR
ENV_SEMANTIC_META: Final[dict[str, tuple[str, str, str]]] = {
    "dev": ("#38bdf8", "DEV", "Sandbox / Development"),
    "tst": ("#22c55e", "TST", "Validation / QA"),
    "pre": ("#f59e0b", "PRE", "Pre-Production Staging"),
    "pro": ("", "LIVE", "Definitive / Production"),
}


def resolve_engine_version(version_file: Path = _VERSION_FILE) -> str:
    """Read the canonical SemVer string from VERSION, falling back to '1.2.0'."""
    if version_file.is_file():
        raw = version_file.read_text(encoding="utf-8").strip()
        if raw:
            return raw
    return "1.2.0"


ENGINE_VERSION: Final[str] = resolve_engine_version()


def is_private_personal_node(manifest: Mapping[str, Any]) -> bool:
    """Return True when a node is a 127.0.0.1-only private individual sovereign pillar."""
    prec = int(manifest.get("precedence", 50))
    is_ind = manifest.get("entity_kind") == "individual" or prec >= INDIVIDUAL_MIN_PRECEDENCE
    lrole = str(manifest.get("layer_role") or "department")
    vis = str(manifest.get("visibility") or ("public" if lrole == "knowledge" else "private"))
    return is_ind and vis != "public"


def resolve_default_node_environment(manifest: Mapping[str, Any]) -> str:
    """Resolve default operating environment ('pro' daily live on personal nodes, else 'dev')."""
    exp_env = str(manifest.get("default_active_env") or "").strip().lower()
    if exp_env in VALID_ENVIRONMENTS:
        return exp_env
    return "pro" if is_private_personal_node(manifest) else "dev"


def _walk_same_root_ancestors(
    workspace_dir: Path, manifest: Mapping[str, Any]
) -> list[tuple[Path, Mapping[str, Any]]]:
    ws = workspace_dir.resolve()
    own_id = str(manifest.get("layer_id") or ws.name)
    own_root = str(manifest.get("governing_root_id") or own_id)
    ancestors: list[tuple[Path, Mapping[str, Any]]] = []
    cur = ws
    visited: set[Path] = {cur}
    for _ in range(MAX_GOVERNANCE_HOPS):
        parent_ws = resolve_default_parent_dir(cur)
        if (
            parent_ws is None
            or parent_ws in visited
            or not (parent_ws / NODE_MANIFEST_REL_PATH).is_file()
        ):
            break
        visited.add(parent_ws)
        pm = load_node_manifest(parent_ws)
        p_lid = str(pm.get("layer_id") or parent_ws.name)
        p_root = str(pm.get("governing_root_id") or p_lid)
        if p_lid not in OSS_WORKSTATION_IDS and p_root == own_root:
            ancestors.append((parent_ws, pm))
        cur = parent_ws
    ancestors.reverse()
    return ancestors


def resolve_governing_root_workspace(workspace_dir: Path, manifest: Mapping[str, Any]) -> Path:
    """Walk up to MAX_GOVERNANCE_HOPS within governing_root_id to locate the Root 0 workspace."""
    ancestors = _walk_same_root_ancestors(workspace_dir, manifest)
    return ancestors[0][0] if ancestors else workspace_dir.resolve()


def _str_list(raw_val: object) -> list[str]:
    return [str(x).strip() for x in raw_val if str(x).strip()] if isinstance(raw_val, list) else []


def _dedup_list(*seqs: list[str]) -> list[str]:
    return list(dict.fromkeys(x for seq in seqs for x in seq if x))


def _collect_same_root_chain(
    workspace_dir: Path, manifest: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    ancestors = _walk_same_root_ancestors(workspace_dir, manifest)
    return [*(pm for _, pm in ancestors), manifest]


def resolve_inherited_network_access(
    workspace_dir: Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Inherit Root 0 layer_authority and surface_access across same-root subordinate nodes."""
    chain = _collect_same_root_chain(workspace_dir, manifest)
    local_sa_raw = manifest.get("surface_access")
    if isinstance(local_sa_raw, Mapping) and local_sa_raw.get("enabled", True) is False:
        return {"has_surface_access": False, "authorized_emails": [], "surface_access": {}}

    auth_lists: list[list[str]] = []
    sa_chain: list[Mapping[str, Any]] = []
    for node_m in chain:
        la = node_m.get("layer_authority")
        if isinstance(la, Mapping):
            auth_lists.append(_str_list(la.get("authorized_emails")))
        sa = node_m.get("surface_access")
        if isinstance(sa, Mapping) and sa.get("enabled", True) is not False:
            sa_chain.append(sa)

    if not sa_chain:
        return {
            "has_surface_access": False,
            "authorized_emails": _dedup_list(*auth_lists),
            "surface_access": {},
        }

    merged_sa: dict[str, Any] = {}
    ops: list[list[str]] = []
    mems: list[list[str]] = []
    exts: list[list[str]] = []
    doms: list[list[str]] = []
    grps: list[list[str]] = []
    rules: list[Any] = []
    peers: dict[str, str] = {}
    for sa_item in sa_chain:
        merged_sa = {**merged_sa, **sa_item}
        ops.append(_str_list(sa_item.get("operator_emails")))
        mems.append(_str_list(sa_item.get("member_emails")))
        exts.append(_str_list(sa_item.get("scoped_external_emails")))
        doms.append(_str_list(sa_item.get("allowed_workspace_domains")))
        grps.append(_str_list(sa_item.get("allowed_workspace_groups")))
        raw_r = sa_item.get("route_rules")
        if isinstance(raw_r, list):
            rules.extend(raw_r)
        raw_p = sa_item.get("allowed_linked_peers")
        if isinstance(raw_p, Mapping):
            peers = {
                **peers,
                **{
                    str(k).strip(): str(v).strip()
                    for k, v in raw_p.items()
                    if str(k).strip() and str(v).strip()
                },
            }

    merged_sa["operator_emails"] = _dedup_list(*ops)
    merged_sa["member_emails"] = _dedup_list(*mems)
    merged_sa["scoped_external_emails"] = _dedup_list(*exts)
    merged_sa["allowed_workspace_domains"] = _dedup_list(*doms)
    merged_sa["allowed_workspace_groups"] = _dedup_list(*grps)
    merged_sa["route_rules"] = rules
    merged_sa["allowed_linked_peers"] = peers
    inh_auth = bool(merged_sa.get("inherit_layer_authority", True))
    return {
        "has_surface_access": True,
        "authorized_emails": _dedup_list(*auth_lists) if inh_auth else [],
        "surface_access": merged_sa,
    }


def resolve_network_session_material(
    workspace_dir: Path,
    manifest: Mapping[str, Any],
    *,
    intranet_zone: str = "",
    local_dev_zone: str = "",
    env_vars: Mapping[str, str] | None = None,
    fallback_key: str = "",
) -> tuple[str, tuple[str, ...]]:
    """Resolve shared Root 0 HMAC session key and network cookie_domains for SSO navigation."""
    eff_env = os.environ if env_vars is None else env_vars
    inh = resolve_inherited_network_access(workspace_dir, manifest)
    sa = inh["surface_access"]
    key_env = str(sa.get("session_key_env") or "ZCG_SURFACE_SESSION_KEY").strip()
    exp_key = eff_env.get(key_env, "").strip() or str(sa.get("session_key") or "").strip()

    sess_key = exp_key
    if not sess_key:
        root_ws = resolve_governing_root_workspace(workspace_dir, manifest)
        if (root_ws / NODE_MANIFEST_REL_PATH).is_file():
            key_file = root_ws / NETWORK_SESSION_KEY_REL_PATH
            if key_file.is_file():
                sess_key = key_file.read_text(encoding="utf-8").strip()
            if not sess_key:
                sess_key = fallback_key.strip() or secrets.token_urlsafe(32)
                key_file.parent.mkdir(parents=True, exist_ok=True)
                key_file.write_text(f"{sess_key}\n", encoding="utf-8")
                key_file.chmod(PRIVATE_KEY_FILE_MODE)
        else:
            sess_key = fallback_key.strip() or secrets.token_urlsafe(24)

    domains = tuple(
        dict.fromkeys(
            d
            for d in (
                intranet_zone.strip().lower().lstrip("."),
                local_dev_zone.strip().lower().lstrip("."),
            )
            if d
        )
    )
    return sess_key, domains
