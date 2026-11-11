"""Cohesive 1:1 Sovereign Node 3-Scope & Linked Cloud Topology Router ('create_node_mesh_router').

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from zcg.web.components import render_card, render_kpi_stat, render_table
from zcg.web.request import Request, WebResponse, respond
from zcg.web.router import APIRouter
from zcg.web.templates import SafeHTML

DEFAULT_NODE_MESH_PREFIX: Final[str] = "/api/modules/node-mesh"


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def create_node_mesh_router(
    workspace_dir: Path, *, prefix: str = DEFAULT_NODE_MESH_PREFIX
) -> APIRouter:
    """Create a 1:1 Sovereign Node 1-Hop & Linked Cloud Topology APIRouter."""
    ws = workspace_dir.resolve()
    router = APIRouter(prefix=prefix, tags=("node-mesh",))

    @router.get("", summary="Inspect 1-hop node relationships and linked cloud directory")
    def inspect_mesh(req: Request) -> WebResponse:
        node_doc = _read_json_dict(ws / "surfaces/data/node_scope.json")
        net_doc = _read_json_dict(ws / "surfaces/data/network_scope.json")
        fed_doc = _read_json_dict(ws / "surfaces/data/federation_scope.json")
        lid = str(node_doc.get("layer_id") or ws.name)
        links = net_doc.get("network_representation_links")
        links_map = links if isinstance(links, dict) else {}
        linked = list(links_map.get("linked_nodes") or [])
        children = list(links_map.get("downward_child_nodes") or [])
        peers = list(links_map.get("lateral_peers") or [])
        mounts = list(fed_doc.get("mounted_layers") or [])
        rows = [
            {"relation": f"link:{n.get('relation', '')}", "node_id": n.get("node_id", "")}
            for n in linked
            if isinstance(n, dict)
        ] + [
            {"relation": "child", "node_id": c.get("node_id", "")}
            for c in children
            if isinstance(c, dict)
        ]
        body_html = SafeHTML(
            render_kpi_stat(label="Children", value=str(len(children))).value
            + render_kpi_stat(label="Peers", value=str(len(peers))).value
            + render_kpi_stat(label="Links", value=str(len(linked))).value
            + render_table(
                columns=(("relation", "Relation"), ("node_id", "Node")),
                rows=rows,
                empty_message="Standalone sovereign node.",
            ).value
        )
        frag = render_card(title=f"Node Mesh ({lid})", badge=str(len(mounts)), body=body_html).value
        return respond(
            req,
            html_fragment=frag,
            data={
                "capability": "node_mesh",
                "layer_id": lid,
                "parent_home_node": links_map.get("parent_home_node"),
                "children_count": len(children),
                "peers_count": len(peers),
                "linked_nodes": linked,
                "mounted_layers_count": len(mounts),
            },
        )

    return router
