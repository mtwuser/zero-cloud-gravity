"""Live node topology projector for the Zone.Z4 2D/3D Spatial Atlas ('live-node-topology').

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from zcg.core.ast_graph import build_codebase_ast_graph
from zcg.core.constants import DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY
from zcg.topology.network import discover_network_topology
from zcg.web.capabilities.spatial_atlas import render_spatial_atlas_html
from zcg.web.capabilities.spatial_layout import (
    SpatialEdgeSpec,
    SpatialNodeSpec,
    build_reference_spatial_presets,
)
from zcg.web.capabilities.spatial_lenses import DEFAULT_SPATIAL_LENS, project_scene_with_lens

LIVE_TOPOLOGY_PRESET_KEY: Final[str] = "live-node-topology"
CODEBASE_AST_PRESET_KEY: Final[str] = "codebase-ast-topology"
MAX_HORIZON_PREVIEW_NODES: Final[int] = 2


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _infer_ring(role: str, *, visibility: str = "private", entity_kind: str = "individual") -> str:
    if visibility == "public" or role == "knowledge" or role.startswith(("pub-", "org-")):
        return "R0"
    if entity_kind == "enterprise" or role in ("corporate", "department", "domain-policy"):
        return "R2"
    return "R3"


def _extract_tags(raw_tags: object, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(raw_tags, (list, tuple)):
        cleaned = tuple(str(x).strip() for x in raw_tags if str(x).strip())
        if cleaned:
            return cleaned
    return fallback


def build_live_node_spatial_presets(
    workspace_dir: Path,
) -> dict[str, tuple[tuple[SpatialNodeSpec, ...], tuple[SpatialEdgeSpec, ...]]]:
    """Synthesize 'live-node-topology' from real node scopes ahead of reference spatial presets."""
    ws = workspace_dir.resolve()
    manifest = _read_json_dict(ws / "system/zcg-node.json")
    node_sc = _read_json_dict(ws / "surfaces/data/node_scope.json")
    net_sc = _read_json_dict(ws / "surfaces/data/network_scope.json")
    fed_sc = _read_json_dict(ws / "surfaces/data/federation_scope.json")

    rep_ctx = node_sc.get("representation_context")
    rep = rep_ctx if isinstance(rep_ctx, dict) else {}
    self_id = str(node_sc.get("layer_id") or manifest.get("layer_id") or ws.name)
    self_role = str(manifest.get("layer_role") or "department")
    self_prec = int(manifest.get("precedence", 50))
    vis = str(fed_sc.get("visibility") or manifest.get("visibility") or "private")
    ekind = str(manifest.get("entity_kind") or "individual")
    posture = "managed" if ekind == "enterprise" else "sovereign"
    self_tags = _extract_tags(
        rep.get("active_templates") or manifest.get("active_templates"),
        ("universal-base", "software-engineering"),
    )
    self_ring = _infer_ring(self_role, visibility=vis, entity_kind=ekind)

    nodes: dict[str, SpatialNodeSpec] = {
        self_id: SpatialNodeSpec(
            node_id=self_id,
            label=f"{self_id} ({self_role})",
            layer_role=self_role,
            precedence=self_prec,
            surface_ring=self_ring,
            membrane_radius=56.0,
            capability_tags=self_tags,
            is_connected=True,
            posture=posture,
        )
    }
    edges: list[SpatialEdgeSpec] = []
    seen_edges: set[tuple[str, str]] = set()

    def _add_edge(src: str, dst: str, rel: str, weight: float, shared: tuple[str, ...]) -> None:
        if src == dst or (src, dst) in seen_edges or (dst, src) in seen_edges:
            return
        seen_edges.add((src, dst))
        edges.append(SpatialEdgeSpec(src, dst, rel, weight, shared))

    raw_links = net_sc.get("network_representation_links")
    if isinstance(raw_links, dict):
        parent_entry = raw_links.get("parent_home_node")
        child_entries = raw_links.get("downward_child_nodes") or []
        peer_entries = raw_links.get("lateral_peers") or []
        linked_entries = raw_links.get("linked_nodes") or []
    elif manifest:
        conn = discover_network_topology(ws, manifest)["node_connection_summary"]
        parent_entry = conn.get("upward_governor")
        child_entries = conn.get("downward_governed_nodes") or []
        peer_entries = conn.get("lateral_peers") or []
        linked_entries = conn.get("linked_nodes") or []
    else:
        parent_entry, child_entries, peer_entries, linked_entries = None, [], [], []

    if isinstance(parent_entry, dict) and parent_entry.get("node_id"):
        pid = str(parent_entry["node_id"])
        prole = str(parent_entry.get("layer_role") or "workstation")
        nodes.setdefault(
            pid,
            SpatialNodeSpec(
                node_id=pid,
                label=f"{pid} (Governor)",
                layer_role=prole,
                precedence=int(parent_entry.get("precedence", max(0, self_prec - 10))),
                surface_ring=_infer_ring(prole, entity_kind=ekind),
                membrane_radius=52.0,
                capability_tags=(self_tags[0],),
                is_connected=True,
                posture=posture,
            ),
        )
        nodes[self_id] = SpatialNodeSpec(
            node_id=self_id,
            label=nodes[self_id].label,
            layer_role=self_role,
            precedence=self_prec,
            surface_ring=self_ring,
            membrane_radius=56.0,
            capability_tags=self_tags,
            parent_id=pid,
            is_connected=True,
            posture=posture,
        )
        _add_edge(pid, self_id, "1-hop-hierarchy", 0.94, (self_tags[0],))

    for ch in child_entries:
        if not isinstance(ch, dict) or not ch.get("node_id"):
            continue
        cid = str(ch["node_id"])
        crole = str(ch.get("layer_role") or "department")
        nodes.setdefault(
            cid,
            SpatialNodeSpec(
                node_id=cid,
                label=f"{cid} ({crole})",
                layer_role=crole,
                precedence=int(ch.get("precedence", min(100, self_prec + 10))),
                surface_ring=_infer_ring(crole, entity_kind=ekind),
                membrane_radius=48.0,
                capability_tags=(self_tags[0],),
                parent_id=self_id,
                is_connected=True,
                posture=posture,
            ),
        )
        _add_edge(self_id, cid, "1-hop-hierarchy", 0.90, (self_tags[0],))

    for pr in peer_entries:
        if not isinstance(pr, dict) or not pr.get("node_id"):
            continue
        pr_id = str(pr["node_id"])
        pr_role = str(pr.get("layer_role") or "department")
        nodes.setdefault(
            pr_id,
            SpatialNodeSpec(
                node_id=pr_id,
                label=f"{pr_id} (Peer)",
                layer_role=pr_role,
                precedence=int(pr.get("precedence", self_prec)),
                surface_ring=_infer_ring(pr_role, entity_kind=ekind),
                membrane_radius=46.0,
                capability_tags=(self_tags[0],),
                is_connected=True,
                posture=posture,
            ),
        )
        _add_edge(self_id, pr_id, "1-hop-hierarchy", 0.84, (self_tags[0],))

    for flt in fed_sc.get("fleet_plugin_inventory") or ():
        if not isinstance(flt, dict) or not flt.get("workspace_id"):
            continue
        fid = str(flt["workspace_id"])
        if fid == self_id or fid in nodes:
            continue
        plug = str(flt.get("plugin_id") or "node-work-cockpit")
        f_ring = "R0" if fid.startswith(("sci-", "gov-", "geo-", "org-", "pub-")) else self_ring
        nodes[fid] = SpatialNodeSpec(
            node_id=fid,
            label=f"{fid} ({plug})",
            layer_role="knowledge" if f_ring == "R0" else "department",
            precedence=30,
            surface_ring=f_ring,
            membrane_radius=46.0,
            capability_tags=(self_tags[0], plug),
            parent_id=self_id,
            is_connected=True,
            posture=posture,
        )
        _add_edge(self_id, fid, "1-hop-hierarchy", 0.82, (self_tags[0],))

    for lnk in linked_entries:
        if not isinstance(lnk, dict) or not lnk.get("node_id"):
            continue
        lid = str(lnk["node_id"])
        lrole = str(lnk.get("layer_role") or "department")
        rel_raw = str(lnk.get("relation") or "linked-peer")
        is_co_sov = rel_raw == "co-sovereign-union"
        rel = (
            "knowledge-feed"
            if rel_raw == "knowledge-feed" or lrole == "knowledge"
            else "linked-peer"
        )
        shared = _extract_tags(lnk.get("shared_packs"), (self_tags[0],))
        lring = (
            "R2"
            if is_co_sov
            else ("R0" if rel == "knowledge-feed" or lid.startswith(("pub-", "org-")) else "R1")
        )
        nodes.setdefault(
            lid,
            SpatialNodeSpec(
                node_id=lid,
                label=f"{lid} ({rel_raw})",
                layer_role=lrole,
                precedence=int(lnk.get("precedence", 20)),
                surface_ring=lring,
                membrane_radius=48.0 if is_co_sov else 46.0,
                capability_tags=shared,
                parent_id=None if is_co_sov else self_id,
                is_connected=True,
                posture="sovereign" if is_co_sov else posture,
            ),
        )
        _add_edge(self_id, lid, rel, 0.88 if is_co_sov else 0.78, shared)

    raw_mounts = fed_sc.get("mounted_layers") or manifest.get("mounted_layers") or ()
    for mnt in raw_mounts:
        mid = str(mnt.get("layer_id") if isinstance(mnt, dict) else mnt).strip()
        if not mid or mid == self_id:
            continue
        nodes.setdefault(
            mid,
            SpatialNodeSpec(
                node_id=mid,
                label=f"{mid} (Mounted Corpus)",
                layer_role="knowledge",
                precedence=20,
                surface_ring="R0",
                membrane_radius=44.0,
                capability_tags=("science-base", self_tags[0]),
                parent_id=self_id,
                is_connected=True,
                posture="sovereign",
            ),
        )
        _add_edge(self_id, mid, "knowledge-feed", 0.74, (self_tags[0],))

    horizon_added = 0
    for pub_id, pub_meta in DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY.items():
        if pub_id in nodes:
            continue
        dom = pub_meta.get("knowledge_domain", "epistemic")
        nodes[pub_id] = SpatialNodeSpec(
            node_id=pub_id,
            label=f"{pub_id} ({dom})",
            layer_role="knowledge",
            precedence=20,
            surface_ring="R0",
            membrane_radius=40.0,
            capability_tags=("science-base",),
            is_connected=False,
            posture="sovereign",
        )
        horizon_added += 1
        if horizon_added >= MAX_HORIZON_PREVIEW_NODES:
            break

    ast_nodes, ast_edges = build_codebase_ast_spatial_preset(ws)
    return {
        LIVE_TOPOLOGY_PRESET_KEY: (tuple(nodes.values()), tuple(edges)),
        **({CODEBASE_AST_PRESET_KEY: (ast_nodes, ast_edges)} if ast_nodes else {}),
        **build_reference_spatial_presets(),
    }


def build_codebase_ast_spatial_preset(
    workspace_dir: Path,
) -> tuple[tuple[SpatialNodeSpec, ...], tuple[SpatialEdgeSpec, ...]]:
    """Project local Python package AST dependencies into a Zone.Z4 spatial preset."""
    ws = workspace_dir.resolve()
    graph = build_codebase_ast_graph(ws)
    packages = graph["packages"]
    if not packages:
        return (), ()

    root_id = ws.name
    nodes: dict[str, SpatialNodeSpec] = {
        root_id: SpatialNodeSpec(
            node_id=root_id,
            label=f"{root_id} (Codebase Root)",
            layer_role="workstation",
            precedence=10,
            surface_ring="R2",
            membrane_radius=54.0,
            capability_tags=("software-engineering",),
            is_connected=True,
            posture="sovereign",
        )
    }
    edges: list[SpatialEdgeSpec] = []
    seen: set[tuple[str, str]] = set()
    for pkg in packages:
        pid = str(pkg["package_id"])
        mcnt = int(pkg["module_count"])
        short_tag = pid.rpartition(".")[2] or pid
        nodes[pid] = SpatialNodeSpec(
            node_id=pid,
            label=f"{pid} ({mcnt} mod)",
            layer_role="service-node",
            precedence=30,
            surface_ring="R2",
            membrane_radius=46.0,
            capability_tags=("software-engineering", short_tag),
            parent_id=root_id,
            is_connected=True,
            posture="sovereign",
        )
        edges.append(
            SpatialEdgeSpec(root_id, pid, "1-hop-hierarchy", 0.90, ("software-engineering",))
        )
    for pkg in packages:
        pid = str(pkg["package_id"])
        for dep in pkg["depends_on"]:
            if pid != dep and (pid, dep) not in seen and (dep, pid) not in seen:
                seen.add((pid, dep))
                edges.append(
                    SpatialEdgeSpec(pid, dep, "linked-peer", 0.78, ("software-engineering",))
                )
    return tuple(nodes.values()), tuple(edges)


def render_live_node_atlas_fragment(
    workspace_dir: Path, *, api_prefix: str = "/api/modules/spatial-atlas"
) -> str:
    """Render the live node 2D/3D Spatial Atlas HTML island fragment for dedicated /atlas."""
    presets = build_live_node_spatial_presets(workspace_dir)
    key = next(iter(presets))
    nodes, edges = presets[key]
    scene = project_scene_with_lens(
        nodes, edges, lens=DEFAULT_SPATIAL_LENS, explosion=0.25, seed=42
    )
    scene["preset"] = key
    scene["render_mode"] = "blueprint-3d"
    return render_spatial_atlas_html(
        scene,
        preset_names=tuple(presets),
        active_preset=key,
        api_prefix=api_prefix,
        full_page=False,
    )
