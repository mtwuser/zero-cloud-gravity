"""Triadic Node x Layer x Network identity, twin attestation, and hierarchical RBAC.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from zcg.core.constants import (
    CAPSULE_DIGEST_HEX_LEN,
    DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY,
    INDIVIDUAL_MIN_PRECEDENCE,
    LAYER_ORIGIN_ROLES,
    MCP_OPERATING_MODES,
    NODE_MANIFEST_REL_PATH,
    OSS_WORKSTATION_IDS,
    PUBLIC_GOV_MAX_PRECEDENCE,
    PUBLIC_GOV_MAX_ROOT_PRECEDENCE,
    PUBLIC_GOV_PREFIXES,
    ROLE_DEFAULT_PRECEDENCE,
    ROLE_ENVIRONMENT_PERMISSIONS,
    TOPOLOGICAL_ROLE_CLASSES,
    VALID_ENTITY_KINDS,
    VALID_VISIBILITY_MODES,
)  # fmt: skip
from zcg.core.epistemics import classify_knowledge_domain
from zcg.core.manifests import is_oss_root_manifest, load_node_manifest


def resolve_default_parent_dir(workspace_dir: Path, parent_dir: Path | None = None) -> Path | None:
    """Resolve an explicit, Makefile-configured, mounted, or sibling governing parent_dir."""
    if parent_dir is not None:
        return parent_dir.resolve()
    ws = workspace_dir.resolve()
    mk = ws / "Makefile"
    if mk.is_file() and (
        m := re.search(r"^PARENT_DIR\s*\?=\s*(.+)$", mk.read_text(encoding="utf-8"), re.MULTILINE)
    ):
        cand = Path(m.group(1).strip())
        if cand.is_dir() and cand.resolve() != ws and (cand / NODE_MANIFEST_REL_PATH).is_file():
            return cand.resolve()
    if ws.parent.name == "layers" and (ws.parent.parent / NODE_MANIFEST_REL_PATH).is_file():
        return ws.parent.parent.resolve()
    wm = load_node_manifest(ws)
    lid = str(wm.get("layer_id") or ws.name).strip()
    gov_id = str(wm.get("governing_root_id") or "").strip()
    bases = (
        (ws.parent, ws.parent.parent) if (gov_id and gov_id != lid and "/" not in gov_id) else ()
    )
    cands = [*(b / gov_id for b in bases), *(d for b in bases for d in sorted(b.glob("*")))]
    return next(
        (
            d.resolve()
            for d in cands
            if d.resolve() != ws
            and (d / NODE_MANIFEST_REL_PATH).is_file()
            and str(load_node_manifest(d).get("layer_id") or d.name) == gov_id
        ),
        None,
    )


def resolve_mounted_child_dir(workspace_dir: Path, child_name: str) -> Path | None:
    """Resolve a 1-hop child node inside ws/layers/<child> or governed sibling repos."""
    ws = workspace_dir.resolve()
    layers_dir = ws / "layers"
    if ((cand := layers_dir / child_name) / NODE_MANIFEST_REL_PATH).is_file():
        return cand.resolve()
    for mf in sorted(layers_dir.glob(f"*/{NODE_MANIFEST_REL_PATH}")):
        with contextlib.suppress(json.JSONDecodeError, OSError):
            data = json.loads(mf.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("layer_id") == child_name:
                return mf.parent.parent.resolve()
    pid = str(load_node_manifest(ws).get("layer_id") or "")
    grp_dirs = (
        g
        for g in sorted(ws.parent.glob("*"))
        if g.is_dir() and (g.name.endswith("-org") or "knowledge" in g.name or g.name == "Projects")
    )
    sibs = [ws.parent / child_name, *(g / child_name for g in grp_dirs)] if pid else []
    return next(
        (
            s.resolve()
            for s in sibs
            if (s / NODE_MANIFEST_REL_PATH).is_file()
            and load_node_manifest(s).get("governing_root_id") == pid
        ),
        None,
    )


def resolve_node_entity_identity(
    target_dir: Path,
    manifest: dict[str, Any] | None = None,
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Resolve entity_kind, visibility, twin identity, and governing_root_id (Root 0) for a node."""
    ws = target_dir.resolve()
    m = manifest if manifest is not None else load_node_manifest(ws)
    lid, lrole = str(m.get("layer_id") or ws.name), str(m.get("layer_role") or "project")
    prec = int(m.get("precedence", ROLE_DEFAULT_PRECEDENCE.get(lrole, 80)))
    k_dom = classify_knowledge_domain(lid, lrole)
    raw_ek = str(m.get("entity_kind") or "").strip().lower()
    is_ind_ws = (
        (lrole == "workstation" and lid not in OSS_WORKSTATION_IDS)
        or prec >= INDIVIDUAL_MIN_PRECEDENCE
        or k_dom["default_entity_kind"] == "individual"
    )
    is_gov = 1 <= prec <= PUBLIC_GOV_MAX_PRECEDENCE or lid.lower().startswith(PUBLIC_GOV_PREFIXES)
    ek = (
        raw_ek if raw_ek in VALID_ENTITY_KINDS else (
            "individual" if is_ind_ws else (
                "open-source" if is_oss_root_manifest(m)
                else ("public-government" if is_gov else "enterprise")
            )
        )
    )  # fmt: skip
    raw_exp = str(m.get("governing_root_id") or "").strip()
    exp_root = "" if raw_exp in OSS_WORKSTATION_IDS else raw_exp
    up_raw = m.get("upstream_layer")
    raw_up_lid = str(up_raw.get("layer_id") or "").strip() if isinstance(up_raw, dict) else ""
    up_lid = "" if raw_up_lid in OSS_WORKSTATION_IDS else raw_up_lid

    eff_p, p_root, p_ek = resolve_default_parent_dir(ws, parent_dir), "", ""
    if eff_p is not None and (eff_p / NODE_MANIFEST_REL_PATH).is_file():
        pm = load_node_manifest(eff_p)
        p_id = resolve_node_entity_identity(eff_p, pm)
        if p_id["entity_kind"] != "open-source":
            p_root = str(p_id["governing_root_id"] or pm.get("layer_id", eff_p.name))
            p_ek = str(p_id["entity_kind"])

    org_pfx = re.split(r"-(?:dept|squad)-", lid)[0] if ("-dept-" in lid or "-squad-" in lid) else ""
    up_org_pfx = (
        re.split(r"-(?:dept|squad)-", up_lid)[0]
        if ("-dept-" in up_lid or "-squad-" in up_lid)
        else ""
    )
    conflict_pfx = bool(org_pfx and p_root and not p_root.startswith(org_pfx))
    is_root_ek = (
        lrole == "corporate"
        or ek == "open-source"
        or (ek == "public-government" and prec <= PUBLIC_GOV_MAX_ROOT_PRECEDENCE)
    )
    ind_rt = exp_root or (
        lid if lrole in ("workstation", "corporate", "knowledge") else (p_root or up_lid or None)
    )
    ent_fb = (
        f"{up_org_pfx}-root"
        if up_org_pfx
        else (up_lid if up_lid else (f"{org_pfx}-root" if org_pfx else lid))
    )
    p_match = p_root if (p_root and p_ek == ek and not conflict_pfx) else ent_fb
    gov_root: str | None = (
        ind_rt
        if ek == "individual"
        else (exp_root if exp_root else (lid if is_root_ek else p_match))
    )

    is_know = bool(k_dom["is_knowledge_node"])
    k_lbl = str(k_dom["knowledge_domain"] or "custom-knowledge")
    t_cls = TOPOLOGICAL_ROLE_CLASSES.get(lrole, "consumer-workspace")
    is_origin = lrole in LAYER_ORIGIN_ROLES
    purpose = str(m.get("description") or "").strip() or f"{lrole}:{t_cls}"
    is_rt = not is_know and (
        lrole == "corporate"
        or ek == "open-source"
        or prec <= PUBLIC_GOV_MAX_ROOT_PRECEDENCE
        or (ek == "individual" and lrole == "workstation")
    )
    is_dev = ek == "open-source" and ws.name.startswith("dev-")
    is_oss_pub = ek == "open-source" and not is_dev
    sub_unap = is_know and (
        m.get("root_0_public_approved") is False
        or (
            bool(up_lid)
            and up_lid not in ("root", *OSS_WORKSTATION_IDS, gov_root)
            and not bool(m.get("root_0_public_approved"))
        )
    )
    raw_vis = str(m.get("visibility") or "").strip().lower()
    vis = (
        raw_vis
        if raw_vis in VALID_VISIBILITY_MODES
        else ("public" if ((is_know and not sub_unap) or is_oss_pub) else "private")
    )
    t_sc = (
        "dev" if is_dev else ("root-0" if is_rt else ("knowledge" if is_know else (
            "department" if lrole in ("department", "domain-policy")
            else ("unit" if lrole in ("squad", "bridge", "service-node") else "project")
        )))
    )  # fmt: skip
    v_sc = (
        f"public:knowledge:{k_lbl}"
        if (is_know and vis == "public")
        else ("public-oss" if (is_oss_pub and vis == "public") else f"private:{ek}:{t_sc}")
    )
    can_oss = (is_know and not sub_unap) or is_rt or up_lid in ("root", *OSS_WORKSTATION_IDS)
    exp_b = (
        "public-surface"
        if (vis == "public" and can_oss)
        else ("root-0-gateway" if can_oss else "internal-1hop")
    )
    is_ro_app = lrole == "workstation" and (ws / ".workstation-state.json").is_file()
    is_ind_st = lrole == "workstation" and (
        m.get("entity_kind") == "individual" or prec >= INDIVIDUAL_MIN_PRECEDENCE
    )
    corp_or_role = "corporate-root" if lrole == "corporate" else lrole
    w_st = (
        "individual-root" if is_ind_st else ("oss-dev" if lrole == "workstation" else corp_or_role)
    )
    op_state = "oss-readonly-appliance" if is_ro_app else w_st
    mcp_m = MCP_OPERATING_MODES.get(op_state, "project-consumer-only")

    raw_pni: dict[str, Any] = rp if isinstance(rp := m.get("public_node_identity"), dict) else {}
    c_dom = str(
        raw_pni.get("canonical_domain")
        or m.get("base_domain")
        or (
            f"{lid}.knowledge.local" if is_know
            else (f"{lid}.personal.local" if ek == "individual" else f"{lid}.intranet.local")
        )
    )  # fmt: skip
    pub_u = str(
        raw_pni.get("public_url")
        or m.get("public_url")
        or m.get("repository")
        or DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY.get(lid, {}).get("public_url")
        or ""
    )
    br_mode = (
        "private-to-public-twin"
        if (is_know and vis == "public" and gov_root and gov_root != lid)
        else ("canonical-public-knowledge" if is_know else "private-layer-node")
    )
    att_dig = hashlib.sha256(f"{gov_root}:{lid}:{c_dom}:{pub_u}".encode()).hexdigest()[
        :CAPSULE_DIGEST_HEX_LEN
    ]
    pni = {
        "node_id": lid, "display_name": str(raw_pni.get("display_name") or purpose),
        "canonical_domain": c_dom, "public_url": pub_u, "governing_root_id": gov_root,
        "root_0_public_approved": not sub_unap and vis == "public", "bridge_mode": br_mode,
        "attestation_digest": att_dig,
        "recognizable_in_network": bool(vis == "public" and not sub_unap and pub_u),
    }  # fmt: skip
    return {
        "layer_id": lid, "node_id": lid, "layer_role": lrole, "topological_class": t_cls,
        "is_layer_origin_node": is_origin, "is_knowledge_node": is_know, "visibility": vis,
        "knowledge_domain": k_dom["knowledge_domain"], "node_purpose": purpose, "precedence": prec,
        "entity_kind": ek, "governing_root_id": gov_root, "public_node_identity": pni,
        "visibility_scope": v_sc, "exposure_boundary": exp_b, "can_expose_to_oss": can_oss,
        "operating_state": op_state, "mcp_operating_mode": mcp_m,
    }  # fmt: skip


def classify_inter_layer_relationship(
    source_identity: dict[str, Any], target_identity: dict[str, Any]
) -> dict[str, Any]:
    """Classify mutual relationship between nodes (internal, knowledge, or external)."""
    src_ek, tgt_ek = str(source_identity["entity_kind"]), str(target_identity["entity_kind"])
    src_root = source_identity.get("governing_root_id")
    tgt_root = target_identity.get("governing_root_id")
    eff_s = src_root or (source_identity.get("layer_id") if src_ek == "individual" else None)
    eff_t = tgt_root or (target_identity.get("layer_id") if tgt_ek == "individual" else None)
    same_root = bool(
        eff_s
        and eff_s == eff_t
        and src_ek == tgt_ek
        and (src_ek != "individual" or src_root or tgt_root)
    )
    is_tgt_know = bool(target_identity.get("is_knowledge_node"))
    rel_scope = "knowledge" if is_tgt_know else ("internal" if same_root else "external")
    oss_ok = bool(source_identity.get("can_expose_to_oss"))
    inter_root_ok = bool(oss_ok and target_identity.get("can_expose_to_oss"))
    mcp_mode = (
        "knowledge-rcap1-and-citation" if is_tgt_know else (
            "internal-1hop-hierarchical" if same_root else (
                "external-root0-to-oss-sanitized" if (tgt_ek == "open-source" and oss_ok) else (
                    "external-peer-root0-pr-and-readonly-mcp" if inter_root_ok
                    else "blocked-must-route-via-governing-root0"
                )
            )
        )
    )  # fmt: skip
    k_lbl = target_identity.get("knowledge_domain") or tgt_ek
    ext_cat = (
        f"public-knowledge:{k_lbl}"
        if is_tgt_know
        else ("internal" if same_root else f"external:{tgt_ek}")
    )
    return {
        "relationship_scope": rel_scope, "mcp_communication_mode": mcp_mode,
        "external_category": ext_cat, "same_governing_root": same_root,
        "source_governing_root_id": src_root, "target_governing_root_id": tgt_root,
        "target_entity_kind": tgt_ek,
        "source_visibility": source_identity.get("visibility", "private"),
        "target_visibility": target_identity.get("visibility", "private"),
        "source_visibility_scope": source_identity.get("visibility_scope"),
        "target_visibility_scope": target_identity.get("visibility_scope"),
        "oss_gateway_authorized": oss_ok, "inter_root_collaboration_authorized": inter_root_ok,
    }  # fmt: skip


def match_manifest_actor_role(manifest: dict[str, Any], actor_email: str) -> tuple[str, bool]:
    """Resolve actor_email role (owner, maintainer, validator, member, consumer) in manifest."""
    raw_auth = manifest.get("layer_authority")
    auth = raw_auth if isinstance(raw_auth, dict) else {}
    raw_roster = auth.get("roster")
    roster = raw_roster if isinstance(raw_roster, dict) else {}

    def _pool(top_key: str, roster_key: str) -> list[str]:
        top = [str(e).strip() for e in auth.get(top_key, []) if str(e).strip()]
        r_list = [
            str(m.get("email", "")).strip()
            for m in roster.get(roster_key, [])
            if isinstance(m, dict) and str(m.get("email", "")).strip()
        ]
        return list(dict.fromkeys([*top, *r_list]))

    owners = _pool("authorized_emails", "owners")
    maintainers = _pool("maintainer_emails", "maintainers")
    validators, members = _pool("validator_emails", "validators"), _pool("member_emails", "members")
    has_roster = bool(owners or maintainers or validators or members)
    clean_em = actor_email.strip().lower()
    if not clean_em:
        return "consumer", has_roster
    for role_name, pool in (
        ("owner", owners), ("maintainer", maintainers),
        ("validator", validators), ("member", members),
    ):  # fmt: skip
        if any(fnmatchcase(clean_em, pat.lower()) for pat in pool):
            return role_name, has_roster
    return "consumer", has_roster


def resolve_hierarchical_actor_profile(
    target_dir: Path, *, actor_email: str, parent_dir: Path | None = None
) -> dict[str, Any]:
    """Compute effective actor role, read-only upstream inheritance, and 1-hop parent authority."""
    ws = target_dir.resolve()
    ws_m = load_node_manifest(ws)
    eff_p = resolve_default_parent_dir(ws, parent_dir)
    local_id = resolve_node_entity_identity(ws, ws_m, eff_p)
    lid = str(local_id["layer_id"])
    lrole, lprec = str(local_id["layer_role"]), int(local_id["precedence"])
    raw_role, has_roster = match_manifest_actor_role(ws_m, actor_email)
    local_role = (
        "owner" if (not has_roster and local_id["entity_kind"] == "individual") else raw_role
    )
    up_role, up_id, up_prec, hier_ok, up_rel = "consumer", None, None, False, "none"
    if eff_p is not None and (eff_p / NODE_MANIFEST_REL_PATH).is_file():
        up_m = load_node_manifest(eff_p)
        up_id_meta = resolve_node_entity_identity(eff_p, up_m)
        up_id, up_prec = str(up_id_meta["layer_id"]), int(up_id_meta["precedence"])
        rel = classify_inter_layer_relationship(local_id, up_id_meta)
        up_rel = str(rel["external_category"])
        if not is_oss_root_manifest(up_m):
            up_role, _ = match_manifest_actor_role(up_m, actor_email)
            hier_ok = (
                up_role in ("owner", "maintainer")
                and up_prec < lprec
                and rel["relationship_scope"] == "internal"
            )
    rank = {"owner": 4, "maintainer": 3, "validator": 2, "member": 1, "consumer": 0}
    eff_role = up_role if (hier_ok and rank[up_role] > rank[local_role]) else local_role
    return {
        "layer_id": lid, "layer_role": lrole, "precedence": lprec, "entity_identity": local_id,
        "actor_email": actor_email, "local_role": local_role, "has_configured_roster": has_roster,
        "upstream_layer_id": up_id, "upstream_precedence": up_prec, "upstream_role": up_role,
        "upstream_relationship": up_rel,
        "upstream_read_only": up_role not in ("owner", "maintainer"),
        "hierarchical_authority_granted": hier_ok, "effective_role": eff_role,
        "allowed_environments": list(ROLE_ENVIRONMENT_PERMISSIONS[eff_role]),
    }  # fmt: skip
