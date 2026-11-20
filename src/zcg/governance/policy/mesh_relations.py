"""Triadic mesh governance policy, lateral channel authorization, and exchange grants.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import NODE_MANIFEST_REL_PATH, VALID_KNOWLEDGE_PREFIXES
from zcg.core.domain import is_kebab_id
from zcg.core.manifests import load_node_manifest
from zcg.topology.identity import (
    classify_inter_layer_relationship,
    resolve_default_parent_dir,
    resolve_mounted_child_dir,
    resolve_node_entity_identity,
)
from zcg.topology.network import discover_network_topology
from zcg.topology.posture import resolve_governance_posture

MESH_RELATIONS_CONTRACT_REV: Final[str] = "zcg-mesh-relations-v1"
VALID_MESH_TOPOLOGY_MODES: Final[tuple[str, ...]] = (
    "full-mesh", "hierarchical-only", "curated-matrix",
)  # fmt: skip
VALID_RELATION_ROLES: Final[tuple[str, ...]] = (
    "governor", "governed-child", "governed-peer", "external-partner", "airlocked",
)  # fmt: skip
VALID_RELATION_VERBS: Final[tuple[str, ...]] = (
    "consult_context", "propose_work", "delegate_work", "validate_gate",
)  # fmt: skip
VALID_WORKSPACE_SCOPES: Final[tuple[str, ...]] = ("all", "node", "network", "corpora")

_DEFAULT_LATERAL_VERBS: Final[tuple[str, ...]] = ("consult_context", "propose_work")
_SCOPE_ALIASES: Final[dict[str, str]] = {
    "": "all", "all": "all", "node": "node", "own": "node", "network": "network",
    "parent": "network", "cross-node": "network", "corpora": "corpora", "corpus": "corpora",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class LateralChannelRule:
    """Authorized lateral channel rule between two governed peer nodes."""

    source_node: str
    target_node: str
    allowed_verbs: tuple[str, ...]
    reciprocal: bool = True


@dataclass(frozen=True, slots=True)
class MeshGovernancePolicy:
    """Effective mesh topology mode and curated lateral channels for a node."""

    governed_by: str
    topology_mode: str
    lateral_channels: tuple[LateralChannelRule, ...]
    inherited_from_parent: bool


@dataclass(frozen=True, slots=True)
class NodeRelationGrant:
    """Resolved runtime exchange grant from source_node to target_node."""

    source_node: str
    target_node: str
    target_role: str
    relation_role: str
    allowed_verbs: tuple[str, ...]
    reciprocal: bool
    governed_by: str


def normalize_workspace_scope(raw_scope: str) -> str:
    """Normalize workspace scope aliases into ('all' | 'node' | 'network' | 'corpora')."""
    return _SCOPE_ALIASES.get(raw_scope.strip().lower(), "all")


def is_airlocked_wallet_node(node_id: str, manifest: Mapping[str, Any] | None = None) -> bool:
    """Return True when a node represents an airlocked personal wallet cockpit."""
    return node_id.strip().lower().endswith("-wallet") or (
        manifest is not None
        and str(manifest.get("view_archetype") or "") == "sovereign-wallet-cockpit"
    )


def _extract_mesh_block(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    cap_pol = manifest.get("capability_policy")
    mesh_gov = cap_pol.get("mesh_governance") if isinstance(cap_pol, Mapping) else None
    return mesh_gov if isinstance(mesh_gov, Mapping) else {}


def _pick_mode(raw_mode: object, target_dir: Path, manifest: dict[str, Any]) -> str:
    clean = str(raw_mode or "").strip().lower()
    if clean in VALID_MESH_TOPOLOGY_MODES:
        return clean
    ek = resolve_node_entity_identity(target_dir, manifest)["entity_kind"]
    return "full-mesh" if ek == "individual" else "curated-matrix"


def _extract_endpoints(entry: Mapping[str, Any]) -> tuple[str, str]:
    src = str(entry.get("source") or entry.get("source_node") or "").strip()
    return src, str(entry.get("target") or entry.get("target_node") or "").strip()


def _parse_lateral_channels(raw_channels: object) -> tuple[LateralChannelRule, ...]:
    if not isinstance(raw_channels, list):
        return ()
    parsed: list[LateralChannelRule] = []
    for entry in raw_channels:
        if not isinstance(entry, Mapping):
            continue
        src, tgt = _extract_endpoints(entry)
        if (
            not is_kebab_id(src) or not is_kebab_id(tgt) or src == tgt
            or is_airlocked_wallet_node(src) or is_airlocked_wallet_node(tgt)
        ):  # fmt: skip
            continue
        raw_v = entry.get("verbs") if "verbs" in entry else entry.get("allowed_verbs")
        verbs = tuple(dict.fromkeys(
            v for item in (raw_v if isinstance(raw_v, (list, tuple)) else ())
            if (v := str(item).strip()) in VALID_RELATION_VERBS
        ))  # fmt: skip
        recip = bool(entry.get("reciprocal", True))
        parsed.append(LateralChannelRule(src, tgt, verbs or _DEFAULT_LATERAL_VERBS, recip))
    return tuple(parsed)


def resolve_mesh_governance_policy(
    workspace_dir: Path, *, parent_dir: Path | None = None
) -> MeshGovernancePolicy:
    """Resolve effective mesh governance policy, inheriting from internal governing parent."""
    ws = workspace_dir.resolve()
    own_m = load_node_manifest(ws) if (ws / NODE_MANIFEST_REL_PATH).is_file() else {}
    eff_p = resolve_default_parent_dir(ws, parent_dir)
    inherited, gov_m, gov_dir, gov_by = False, own_m, ws, str(own_m.get("layer_id") or ws.name)
    if eff_p is not None and (eff_p / NODE_MANIFEST_REL_PATH).is_file():
        rel = classify_inter_layer_relationship(
            resolve_node_entity_identity(ws, own_m, eff_p), resolve_node_entity_identity(eff_p)
        )
        if rel["relationship_scope"] == "internal":
            gov_m, gov_dir, inherited = load_node_manifest(eff_p), eff_p, True
            gov_by = str(gov_m.get("layer_id") or eff_p.name)
    mesh_gov = _extract_mesh_block(gov_m)
    eff_mode = _pick_mode(mesh_gov.get("topology_mode"), gov_dir, gov_m)
    chs = _parse_lateral_channels(mesh_gov.get("lateral_channels"))
    return MeshGovernancePolicy(gov_by, eff_mode, chs, inherited)


def _validate_channel_rule(raw: Mapping[str, Any]) -> LateralChannelRule:
    src, tgt = _extract_endpoints(raw)
    if not is_kebab_id(src) or not is_kebab_id(tgt):
        raise ValueError(f"INVALID_CHANNEL_NODE: {src!r} and {tgt!r} must match kebab-case")
    if src == tgt:
        raise ValueError(f"SELF_CHANNEL_FORBIDDEN: cannot link {src!r} to itself")
    if is_airlocked_wallet_node(src) or is_airlocked_wallet_node(tgt):
        raise ValueError(f"WALLET_LATERAL_CHANNEL_BLOCKED: airlocked node ({src!r}, {tgt!r})")
    raw_v = raw.get("verbs") if "verbs" in raw else raw.get("allowed_verbs")
    clean_v: list[str] = []
    if isinstance(raw_v, (list, tuple)):
        for item in raw_v:
            if (verb := str(item).strip()) not in VALID_RELATION_VERBS:
                raise ValueError(f"INVALID_RELATION_VERB: {verb!r} not in {VALID_RELATION_VERBS}")
            clean_v.append(verb)
    verbs = tuple(dict.fromkeys(clean_v)) or _DEFAULT_LATERAL_VERBS
    return LateralChannelRule(src, tgt, verbs, bool(raw.get("reciprocal", True)))


def _matches_pair(rule: LateralChannelRule, src: str, tgt: str) -> bool:
    return (rule.source_node == src and rule.target_node == tgt) or (
        rule.reciprocal and rule.source_node == tgt and rule.target_node == src
    )


def _serialize_rule(rule: LateralChannelRule) -> dict[str, Any]:
    return {
        "source_node": rule.source_node, "target_node": rule.target_node,
        "allowed_verbs": list(rule.allowed_verbs), "reciprocal": rule.reciprocal,
    }  # fmt: skip


def configure_mesh_governance_policy(
    workspace_dir: Path,
    *,
    topology_mode: str = "",
    add_channel: Mapping[str, Any] | None = None,
    remove_channel: tuple[str, str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Configure capability_policy.mesh_governance inside system/zcg-node.json."""
    ws = workspace_dir.resolve()
    manifest_path = ws / NODE_MANIFEST_REL_PATH
    if not manifest_path.is_file():
        raise ValueError(f"MISSING_NODE_MANIFEST: {manifest_path}")
    manifest = load_node_manifest(ws)
    existing_mg = _extract_mesh_block(manifest)
    clean_mode = topology_mode.strip().lower()
    if clean_mode and clean_mode not in VALID_MESH_TOPOLOGY_MODES:
        raise ValueError(f"INVALID_MESH_TOPOLOGY_MODE: {topology_mode!r}")
    eff_mode = clean_mode or _pick_mode(existing_mg.get("topology_mode"), ws, manifest)
    channels = list(_parse_lateral_channels(existing_mg.get("lateral_channels")))
    if add_channel is not None:
        rule = _validate_channel_rule(add_channel)
        channels = [r for r in channels if not _matches_pair(r, rule.source_node, rule.target_node)]
        channels.append(rule)
    if remove_channel is not None:
        rm_src, rm_tgt = remove_channel[0].strip(), remove_channel[1].strip()
        channels = [r for r in channels if not _matches_pair(r, rm_src, rm_tgt)]
    serialized = [_serialize_rule(r) for r in channels]
    raw_cap = manifest.get("capability_policy")
    cap_pol: dict[str, Any] = dict(raw_cap) if isinstance(raw_cap, Mapping) else {}
    cap_pol["mesh_governance"] = {"topology_mode": eff_mode, "lateral_channels": serialized}
    manifest["capability_policy"] = cap_pol
    if not dry_run:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return {
        "contract_rev": MESH_RELATIONS_CONTRACT_REV,
        "node_id": str(manifest.get("layer_id") or ws.name),
        "topology_mode": eff_mode, "lateral_channels": serialized,
        "channel_count": len(serialized), "dry_run": dry_run,
    }  # fmt: skip


def resolve_node_relation_grants(
    workspace_dir: Path, *, parent_dir: Path | None = None
) -> tuple[NodeRelationGrant, ...]:
    """Compute authorized relation grants across parent, children, lateral peers, and links."""
    ws = workspace_dir.resolve()
    if not (ws / NODE_MANIFEST_REL_PATH).is_file():
        return ()
    if not resolve_governance_posture(ws, parent_dir=parent_dir)["allow_external_peer_links"]:
        return ()
    pol = resolve_mesh_governance_policy(ws, parent_dir=parent_dir)
    conn = discover_network_topology(ws, parent_dir=parent_dir)["node_connection_summary"]
    own_id, gv = str(conn["node_id"]), pol.governed_by
    grants: list[NodeRelationGrant] = []
    seen: set[str] = {own_id}

    def _add(tgt: str, role: str, rel: str, verbs: tuple[str, ...], recip: bool, gov: str) -> None:
        seen.add(tgt)
        grants.append(NodeRelationGrant(own_id, tgt, role, rel, verbs, recip, gov))

    up = conn.get("upward_governor")
    if isinstance(up, Mapping) and up.get("relationship_scope") == "internal":
        up_r = str(up.get("layer_role") or "corporate")
        _add(str(up["node_id"]), up_r, "governed-child", _DEFAULT_LATERAL_VERBS, True, gv)
    for dn in conn.get("downward_governed_nodes", []):
        cid, crole = str(dn["node_id"]), str(dn.get("layer_role") or "project")
        is_w = is_airlocked_wallet_node(cid)
        rel_r, verbs = ("airlocked", ()) if is_w else ("governor", VALID_RELATION_VERBS)
        _add(cid, crole, rel_r, verbs, not is_w, gv)
    for peer in conn.get("lateral_peers", []):
        pid, prole = str(peer["node_id"]), str(peer.get("layer_role") or "project")
        if is_airlocked_wallet_node(pid):
            _add(pid, prole, "airlocked", (), False, gv)
        elif pol.topology_mode == "full-mesh":
            _add(pid, prole, "governed-peer", _DEFAULT_LATERAL_VERBS, True, gv)
        elif pol.topology_mode == "curated-matrix":
            rule = next((r for r in pol.lateral_channels if _matches_pair(r, own_id, pid)), None)
            if rule is not None:
                _add(pid, prole, "governed-peer", rule.allowed_verbs, rule.reciprocal, gv)
    for lnk in conn.get("linked_nodes", []):
        lid = str(lnk["node_id"])
        lrole, lrel = str(lnk.get("layer_role") or "project"), str(lnk.get("relation") or "")
        is_know = (
            lrole == "knowledge" or lrel.startswith("knowledge")
            or lid.startswith(VALID_KNOWLEDGE_PREFIXES)
        )  # fmt: skip
        if not (is_know or lid in seen or is_airlocked_wallet_node(lid)):
            _add(lid, lrole, "external-partner", _DEFAULT_LATERAL_VERBS, True, "bilateral-link")
    return tuple(grants)


def evaluate_node_exchange_grant(
    workspace_dir: Path, *, target_node: str, required_verb: str, parent_dir: Path | None = None
) -> NodeRelationGrant:
    """Verify target_node is authorized for required_verb or raise MESH_RELATION_FORBIDDEN."""
    clean_t, clean_v = target_node.strip(), required_verb.strip()
    for grant in resolve_node_relation_grants(workspace_dir, parent_dir=parent_dir):
        if grant.target_node == clean_t and clean_v in grant.allowed_verbs:
            return grant
    msg = f"MESH_RELATION_FORBIDDEN: {target_node!r} is not authorized for {required_verb!r}"
    raise ValueError(msg)


def _resolve_linked_node_dir(ws: Path, target_id: str) -> Path | None:
    if not (ws / NODE_MANIFEST_REL_PATH).is_file():
        return None
    manifest = load_node_manifest(ws)
    for entry in (x for x in manifest.get("linked_nodes", []) if isinstance(x, Mapping)):
        if str(entry.get("node_id") or "").strip() != target_id:
            continue
        raw_ref = str(entry.get("target_ref") or "").strip()
        if raw_ref and "://" not in raw_ref and not raw_ref.startswith("git@"):
            cand = Path(raw_ref).expanduser()
            resolved = cand.resolve() if cand.is_absolute() else (ws / cand).resolve()
            if (resolved / NODE_MANIFEST_REL_PATH).is_file():
                return resolved
        if ((sib := (ws.parent / target_id).resolve()) / NODE_MANIFEST_REL_PATH).is_file():
            return sib
    return None


def resolve_exchange_target_dir(
    workspace_dir: Path, target_node: str, *, parent_dir: Path | None = None
) -> Path | None:
    """Resolve local workspace directory for an upward, downward, sibling, or linked target."""
    if not (clean_t := target_node.strip()):
        return None
    ws = workspace_dir.resolve()
    eff_p = resolve_default_parent_dir(ws, parent_dir)
    if eff_p is not None and (eff_p / NODE_MANIFEST_REL_PATH).is_file():
        pm = load_node_manifest(eff_p)
        if str(pm.get("layer_id") or eff_p.name).strip() == clean_t or eff_p.name == clean_t:
            return eff_p.resolve()
    if (child_dir := resolve_mounted_child_dir(ws, clean_t)) is not None:
        return child_dir
    sib = resolve_mounted_child_dir(eff_p, clean_t) if eff_p is not None else None
    if sib is not None and sib.resolve() != ws:
        return sib
    return _resolve_linked_node_dir(ws, clean_t)
