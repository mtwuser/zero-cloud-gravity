"""Upward composite network discovery, 1-hop connections, and public-seed isolation.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from zcg.core.constants import (
    DEFAULT_PLUGIN_BASE_PORT,
    DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY,
    NODE_MANIFEST_REL_PATH,
    ROLE_DEFAULT_PRECEDENCE,
    VALID_NODE_LINK_RELATIONS,
)
from zcg.core.epistemics import classify_knowledge_domain
from zcg.core.manifests import load_node_manifest
from zcg.topology.identity import (
    classify_inter_layer_relationship,
    resolve_default_parent_dir,
    resolve_node_entity_identity,
)


def discover_network_topology(
    target_dir: Path,
    manifest: dict[str, Any] | None = None,
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Discover composite network topology, 1-hop connections, and 4-stage sync_topology."""
    ws = target_dir.resolve()
    m = manifest if manifest is not None else load_node_manifest(ws)
    eff_p = resolve_default_parent_dir(ws, parent_dir)
    self_id = resolve_node_entity_identity(ws, m, eff_p)
    lid, lrole = str(self_id["layer_id"]), str(self_id["layer_role"])
    gov_root = str(self_id["governing_root_id"] or lid)
    up_gov: dict[str, Any] | None = None
    if eff_p is not None and (eff_p / NODE_MANIFEST_REL_PATH).is_file():
        pm = load_node_manifest(eff_p)
        p_id = resolve_node_entity_identity(eff_p, pm)
        rel = classify_inter_layer_relationship(self_id, p_id)
        up_gov = {
            "node_id": p_id["layer_id"], "layer_role": p_id["layer_role"],
            "precedence": p_id["precedence"],
            "cockpit_port": int(
                pm.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + int(p_id["precedence"]))
            ),
            "is_layer_origin_node": p_id["is_layer_origin_node"],
            "relationship_scope": rel["relationship_scope"],
            "hierarchy_relation": "1-hop-upward-governor",
        }  # fmt: skip
    root_ws = (
        eff_p
        if (up_gov and up_gov["relationship_scope"] == "internal" and eff_p is not None)
        else ws
    )
    base_dirs = [
        ws, root_ws, *sorted((ws / "layers").glob("*")), *sorted((root_ws / "layers").glob("*")),
        *sorted((root_ws.parent / f"{root_ws.name}-org").glob("*")),
        *(
            d for g in sorted(root_ws.parent.glob("*"))
            if g.is_dir() and ("knowledge" in g.name or g.name == "Projects")
            for d in sorted(g.glob("*"))
        ),
        *sorted(ws.parent.glob("*")),
    ]  # fmt: skip
    cand_dirs = list(
        dict.fromkeys(
            d.resolve()
            for d in [
                *base_dirs,
                *(c for d in base_dirs if d.is_dir() for c in sorted((d / "layers").glob("*"))),
            ]
            if (d / NODE_MANIFEST_REL_PATH).is_file()
        )
    )
    nodes: dict[str, dict[str, Any]] = {}
    raw_reg: dict[str, Any] = (
        rr if isinstance(rr := m.get("public_knowledge_registry"), dict) else {}
    )
    pub_reg: dict[str, dict[str, Any]] = {**DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY, **raw_reg}
    for cd in cand_dirs:
        cm = load_node_manifest(cd)
        cid_m = resolve_node_entity_identity(cd, cm)
        nid = str(cid_m["layer_id"])
        same_org_twin = cid_m["governing_root_id"] == gov_root or nid in raw_reg
        if (
            cid_m["is_knowledge_node"]
            and cid_m["public_node_identity"]["recognizable_in_network"]
            and (not nid.startswith("org-") or same_org_twin)
        ):
            pub_reg[nid] = {**pub_reg.get(nid, {}), **cid_m["public_node_identity"]}
        if nid == gov_root or cid_m["governing_root_id"] == gov_root:
            up_r = cm.get("upstream_layer")
            up_l = str(up_r.get("layer_id") or "").strip() if isinstance(up_r, dict) else ""
            p_l = (
                str(load_node_manifest(cd.parent.parent).get("layer_id") or cd.parent.parent.name)
                if (
                    not up_l
                    and cd.parent.name == "layers"
                    and (cd.parent.parent / NODE_MANIFEST_REL_PATH).is_file()
                )
                else ""
            )
            eff_up = up_l or p_l or ("" if nid == gov_root else gov_root)
            c_prec = int(cid_m["precedence"])
            nodes[nid] = {
                "node_id": nid, "layer_role": str(cid_m["layer_role"]),
                "precedence": c_prec,
                "cockpit_port": int(cm.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + c_prec)),
                "is_layer_origin_node": bool(cid_m["is_layer_origin_node"]),
                "is_knowledge_node": bool(cid_m["is_knowledge_node"]),
                "knowledge_domain": cid_m["knowledge_domain"],
                "node_purpose": str(cid_m["node_purpose"]), "upstream_id": eff_up,
            }  # fmt: skip
    s_up = (
        str(up_gov["node_id"])
        if (up_gov and up_gov["relationship_scope"] == "internal")
        else ("" if lid == gov_root else gov_root)
    )
    s_prec = int(self_id["precedence"])
    nodes.setdefault(
        lid,
        {
            "node_id": lid, "layer_role": lrole, "precedence": s_prec,
            "cockpit_port": int(m.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + s_prec)),
            "is_layer_origin_node": bool(self_id["is_layer_origin_node"]),
            "is_knowledge_node": bool(self_id["is_knowledge_node"]),
            "knowledge_domain": self_id["knowledge_domain"],
            "node_purpose": str(self_id["node_purpose"]), "upstream_id": s_up,
        },
    )  # fmt: skip
    self_up_id = str(nodes[lid]["upstream_id"])
    downward = [
        {k: v for k, v in n.items() if k != "upstream_id"}
        | {"hierarchy_relation": "1-hop-downward-governed"}
        for nid, n in sorted(nodes.items())
        if nid != lid and n["upstream_id"] == lid and not n["is_knowledge_node"]
    ]
    peers = [
        {k: v for k, v in n.items() if k not in ("upstream_id", "node_purpose")}
        | {"hierarchy_relation": "1-hop-lateral-peer"}
        for nid, n in sorted(nodes.items())
        if nid != lid
        and bool(self_up_id)
        and n["upstream_id"] == self_up_id
        and not n["is_knowledge_node"]
    ]
    know_map: dict[str, dict[str, Any]] = {
        nid: {k: v for k, v in n.items() if k != "upstream_id"}
        | {"hierarchy_relation": "1-hop-knowledge-node"}
        for nid, n in sorted(nodes.items())
        if nid != lid
        and n["upstream_id"] in {lid, *([self_up_id] if self_up_id else [])}
        and n["is_knowledge_node"]
    }
    for ml in (x for x in m.get("mounted_layers", []) if isinstance(x, dict)):
        m_id = str(ml.get("layer_id") or ml.get("name") or "").strip()
        m_role = str(ml.get("layer_role") or "knowledge").strip()
        if m_id and (kd := classify_knowledge_domain(m_id, m_role))["is_knowledge_node"]:
            know_map.setdefault(
                m_id,
                {
                    "node_id": m_id, "layer_role": m_role,
                    "precedence": int(ml.get("precedence", ROLE_DEFAULT_PRECEDENCE["knowledge"])),
                    "is_layer_origin_node": True, "is_knowledge_node": True,
                    "knowledge_domain": kd["knowledge_domain"],
                    "node_purpose": f"knowledge:{kd['knowledge_domain']}",
                    "hierarchy_relation": "1-hop-knowledge-node",
                },
            )  # fmt: skip
    know_nodes = list(know_map.values())
    linked_nodes: list[dict[str, Any]] = []
    for ln in (x for x in m.get("linked_nodes", []) if isinstance(x, dict)):
        ln_id = str(ln.get("node_id") or "").strip()
        if ln_id and ln_id != lid:
            raw_rel = str(ln.get("relation") or "lateral-peer").strip()
            ln_rel = raw_rel if raw_rel in VALID_NODE_LINK_RELATIONS else "lateral-peer"
            ln_role = str(ln.get("layer_role") or "project").strip()
            ln_prec = int(ln.get("precedence", ROLE_DEFAULT_PRECEDENCE.get(ln_role, 80)))
            def_ln_url = (
                ""
                if ln_rel == "knowledge-feed"
                else f"http://127.0.0.1:{DEFAULT_PLUGIN_BASE_PORT + ln_prec}"
            )
            ln_url = str(ln.get("cockpit_url") or def_ln_url).strip()
            ln_packs = [str(p).strip() for p in (ln.get("shared_packs") or []) if str(p).strip()]
            linked_nodes.append(
                {
                    "node_id": ln_id, "relation": ln_rel, "layer_role": ln_role,
                    "precedence": ln_prec, "cockpit_url": ln_url,
                    "target_ref": str(ln.get("target_ref") or ""),
                    "shared_packs": ln_packs, "hierarchy_relation": f"linked:{ln_rel}",
                }
            )  # fmt: skip
    depts = sorted(
        (n for n in nodes.values() if n["layer_role"] in ("department", "domain-policy")),
        key=lambda x: (x["precedence"], x["node_id"]),
    )
    dept_subnets = []
    for dn in depts:
        d_ids = {dn["node_id"]} | {
            nid for nid, it in nodes.items()
            if it["upstream_id"] == dn["node_id"] and not it["is_knowledge_node"]
        }  # fmt: skip
        d_ids |= {
            nid for nid, it in nodes.items()
            if it["upstream_id"] in d_ids and not it["is_knowledge_node"]
        }  # fmt: skip
        dept_subnets.append(
            {
                "department_id": dn["node_id"],
                "layer_role": dn["layer_role"],
                "precedence": dn["precedence"],
                "layers_count": sum(1 for i in d_ids if nodes[i]["is_layer_origin_node"]),
                "nodes_count": len(d_ids),
            }
        )
    is_root_sc = (
        self_id["visibility_scope"].endswith((":root-0", ":dev"))
        or self_id["visibility_scope"] == "public-oss"
    )
    own_ids = (
        set(nodes)
        if is_root_sc
        else ({lid} | {nid for nid, it in nodes.items() if it["upstream_id"] == lid})
    )
    own_ids |= {nid for nid, it in nodes.items() if it["upstream_id"] in own_ids}
    net_sc = (
        "knowledge-network" if self_id["is_knowledge_node"] else (
            "root-0-composite-network" if is_root_sc else (
                "departmental-network" if lrole in ("department", "domain-policy")
                else ("unit-subnetwork" if lrole == "squad" else "leaf-execution-node")
            )
        )
    )  # fmt: skip
    priv_in_b = (
        "personal-private" if self_id["entity_kind"] == "individual" else "corporate-private"
    )
    in_b = (
        "public-curated-corpus"
        if (self_id["is_knowledge_node"] and self_id["visibility"] == "public")
        else ("open-source-curated" if self_id["visibility_scope"] == "public-oss" else priv_in_b)
    )
    sync_sc = "workstation" if lrole == "workstation" else "workspace"
    is_auto_root = lrole == "corporate" or not up_gov or up_gov["layer_role"] == "workstation"
    dag_lvl = (
        0
        if self_id["entity_kind"] == "open-source"
        else (1 if sync_sc == "workstation" else (2 if is_auto_root else 3))
    )
    dag_stg = (
        "engine-source", "workstation-hub",
        "autonomous-root-workspace", "subordinate-origin-workspace",
    )[dag_lvl]  # fmt: skip
    in_from = (
        str(up_gov["node_id"])
        if up_gov
        else ("zero-cloud-gravity" if sync_sc == "workstation" else "workstation-hub")
    )
    in_cmd = (
        "zcg workstation sync"
        if sync_sc == "workstation"
        else (
            f"make sync PARENT_DIR={eff_p}"
            if (eff_p is not None and (not up_gov or up_gov["layer_role"] != "workstation"))
            else "make sync"
        )
    )
    out_dn = (
        "zcg workstation sync"
        if sync_sc == "workstation"
        else (
            "make delegate"
            if lrole in ("corporate", "department", "division", "domain-policy", "squad")
            else None
        )
    )
    has_sub = bool(
        m.get("mounted_layers") or list((ws / "layers").glob(f"*/{NODE_MANIFEST_REL_PATH}"))
    )
    sub_cmd = "zcg subtree pull-all" if has_sub else None
    know_cmd = (
        f"make delegate CHILD={know_nodes[0]['node_id']} "
        "SURFACE=docs/reference SOURCE=<curated-doc>"
        if (know_nodes and lrole == "corporate")
        else None
    )
    sync_topo = {
        "sync_scope": sync_sc, "dag_level": dag_lvl, "dag_stage": dag_stg,
        "inherits_from": in_from, "inbound_sync_command": in_cmd,
        "outbound_upward_command": "make promote", "outbound_downward_command": out_dn,
        "outbound_knowledge_command": know_cmd,
        "downward_dependents_count": len(downward) + len(know_nodes),
        "has_mounted_subtrees": has_sub, "subtree_aggregation_command": sub_cmd,
        "recommended_sync_order": [
            "1. Workstation Control Tower ($HOME): zcg workstation sync",
            "2. Autonomous Root / Primary Node: make sync",
            "3. Subordinate Origin Nodes (dept-* / org-*): make sync PARENT_DIR=<root-0-dir>",
            "4. Composite Parent Subtree Aggregation (layers/*): zcg subtree pull-all",
        ],
    }  # fmt: skip
    return {
        "network_topology": {
            "network_scope": net_sc, "visibility": self_id["visibility"],
            "governing_root_id": gov_root,
            "is_layer_origin_node": bool(self_id["is_layer_origin_node"]),
            "is_knowledge_node": bool(self_id["is_knowledge_node"]),
            "own_network_layers_count": sum(
                1 for i in own_ids
                if nodes[i]["is_layer_origin_node"] and not nodes[i]["is_knowledge_node"]
            ),
            "own_network_nodes_count": len(own_ids),
            "root_composite_layers_count": sum(
                1 for n in nodes.values()
                if n["is_layer_origin_node"] and not n["is_knowledge_node"]
            ),
            "root_composite_nodes_count": len(nodes),
            "mounted_knowledge_nodes_count": len(know_nodes),
            "departmental_subnetworks": dept_subnets, "public_knowledge_registry": pub_reg,
            "inward_boundary": in_b, "outward_boundary": self_id["exposure_boundary"],
        },
        "node_connection_summary": {
            "node_id": lid, "node_purpose": self_id["node_purpose"],
            "is_layer_origin_node": bool(self_id["is_layer_origin_node"]),
            "is_knowledge_node": bool(self_id["is_knowledge_node"]),
            "upward_governor": up_gov, "downward_governed_nodes": downward,
            "lateral_peers": peers, "knowledge_nodes": know_nodes,
            "linked_nodes": linked_nodes,
        },
        "sync_topology": sync_topo,
    }  # fmt: skip
