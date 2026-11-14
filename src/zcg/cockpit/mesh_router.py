"""Cohesive 1:1 Sovereign Node 3-Scope & Linked Cloud Topology Router ('create_node_mesh_router').

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Final

from zcg.core.constants import NODE_MANIFEST_REL_PATH, VALID_NODE_LINK_RELATIONS
from zcg.core.manifests import load_node_manifest
from zcg.topology.posture import (
    PERSONAL_CONSTELLATION_PILLARS,
    resolve_governance_posture,
    resolve_surface_origin,
)
from zcg.web.channels import DeliveryChannel, build_swap_response_headers
from zcg.web.components import render_card, render_kpi_stat, render_table
from zcg.web.request import Request, WebResponse, respond
from zcg.web.router import APIRouter
from zcg.web.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.templates import SafeHTML

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_NODE_MESH_PREFIX: Final[str] = "/api/modules/node-mesh"


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _extract_link_payload(req: Request) -> dict[str, Any]:
    if "application/x-www-form-urlencoded" in req.content_type.lower():
        return dict(req.form())
    if not req.body:
        return {}
    parsed = req.json()
    if not isinstance(parsed, dict):
        raise WebAppError(
            "Node link payload must be a JSON object",
            error_code="INVALID_MESH_LINK_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    return parsed


def _build_constellation_pillars(
    ws: Path, lid: str, manifest: dict[str, Any]
) -> list[dict[str, str]]:
    persona = lid
    for suffix in ("-pc", "-tutor", "-work", "-wallet"):
        if persona.endswith(suffix) and len(persona) > len(suffix):
            persona = persona.removesuffix(suffix)
            break
    linked_ids = {
        str(x.get("node_id") or "") for x in manifest.get("linked_nodes", []) if isinstance(x, dict)
    }
    rows: list[dict[str, str]] = []
    for pillar in PERSONAL_CONSTELLATION_PILLARS:
        cid = f"{persona}-{pillar}"
        present = (
            lid == cid or cid in linked_ids or (ws.parent / cid / NODE_MANIFEST_REL_PATH).is_file()
        )
        rows.append(
            {
                "pillar": pillar,
                "node_id": cid,
                "status": "active" if present else "blueprint",
                "airlock": "R3 local-only (via work)" if pillar == "wallet" else "peer-ready",
            }
        )
    return rows


def _render_link_form_html(link_endpoint: str) -> str:
    esc_ep = html.escape(link_endpoint, quote=True)
    opts = "".join(
        f'<option value="{html.escape(rel, quote=True)}">{html.escape(rel)}</option>'
        for rel in VALID_NODE_LINK_RELATIONS
    )
    return (
        f'<form class="zcg-form" data-zcg-post="{esc_ep}" '
        'data-zcg-target="#zcg-capability-stage" style="margin-top:0.85rem;">'
        '<div class="zcg-grid">'
        '<label class="zcg-field"><span>Remote Git URL or Local Node Ref</span>'
        '<input type="text" name="from_source" placeholder="https://github.com/org/node.git">'
        "</label>"
        '<label class="zcg-field"><span>Target Node ID (optional with URL)</span>'
        '<input type="text" name="target_id" placeholder="org-partner">'
        "</label>"
        '<label class="zcg-field"><span>Relation</span>'
        f'<select name="relation">{opts}</select></label>'
        "</div>"
        '<div style="margin-top:0.65rem;">'
        '<button type="submit" class="zcg-btn">Connect Sovereign Node</button>'
        "</div></form>"
    )


def create_node_mesh_router(
    workspace_dir: Path, *, prefix: str = DEFAULT_NODE_MESH_PREFIX
) -> APIRouter:
    """Create a 1:1 Sovereign Node 1-Hop, Constellation Setup & Linked Cloud APIRouter."""
    from zcg.governance.links import link_node

    ws = workspace_dir.resolve()
    router = APIRouter(prefix=prefix, tags=("node-mesh",))
    clean_prefix = prefix.rstrip("/")

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

    @router.get(
        "/onboarding", summary="Inspect 4-pillar constellation posture and visual link form"
    )
    def inspect_mesh_onboarding(req: Request) -> WebResponse:
        has_m = (ws / NODE_MANIFEST_REL_PATH).is_file()
        m_doc = load_node_manifest(ws) if has_m else {"layer_id": ws.name}
        lid = str(m_doc.get("layer_id") or ws.name)
        posture = resolve_governance_posture(ws, m_doc)
        origin = resolve_surface_origin(m_doc)
        pillars = _build_constellation_pillars(ws, lid, m_doc)
        action_html = (
            _render_link_form_html(f"{clean_prefix}/link")
            if posture["allow_external_peer_links"]
            else (
                '<p class="zcg-muted" style="margin-top:0.75rem;">'
                "R3 Airlock Active: external peer links are disabled on wallet nodes; "
                "route opt-in settlement links via your work pillar.</p>"
            )
        )
        body_html = SafeHTML(
            render_kpi_stat(label="Posture", value=str(posture["governance_posture"])).value
            + render_kpi_stat(label="Ring", value=str(posture["default_surface_ring"])).value
            + render_kpi_stat(label="Origin", value=str(origin["origin_mode"])).value
            + render_table(
                columns=(
                    ("pillar", "Pillar"),
                    ("node_id", "Node"),
                    ("status", "State"),
                    ("airlock", "Boundary"),
                ),
                rows=pillars,
                empty_message="No constellation pillars configured.",
            ).value
            + action_html
        )
        frag = render_card(
            title=f"Visual Link & Constellation Setup ({lid})",
            badge=str(posture["governance_posture"]),
            body=body_html,
        ).value
        return respond(
            req,
            html_fragment=frag,
            data={
                "capability": "node_mesh_onboarding",
                "layer_id": lid,
                "posture": posture,
                "surface_origin": origin,
                "constellation_pillars": pillars,
            },
        )

    @router.post(
        "/link",
        channel=DeliveryChannel.SWAP_SYNC,
        summary="Register a CSRF-guarded declarative node link without raw JSON edits",
    )
    def create_mesh_link(req: Request) -> WebResponse:
        payload = _extract_link_payload(req)
        tgt = str(payload.get("target_id") or "").strip()
        frm = str(payload.get("from_source") or "").strip()
        if not tgt and not frm:
            raise WebAppError(
                "Provide target_id or from_source to register a node link",
                error_code="MISSING_LINK_TARGET",
                http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        try:
            res = link_node(
                ws,
                target_id=tgt,
                from_source=frm,
                from_branch=str(payload.get("from_branch") or "master"),
                relation=str(payload.get("relation") or "lateral-peer"),
                target_ref=str(payload.get("target_ref") or ""),
                description=str(payload.get("description") or ""),
            )
        except ValueError as exc:
            msg = str(exc)
            is_wallet_block = "WALLET_EXTERNAL_LINK_BLOCKED" in msg
            raise WebAppError(
                msg,
                error_code=(
                    "WALLET_EXTERNAL_LINK_BLOCKED" if is_wallet_block else "INVALID_NODE_LINK"
                ),
                http_status=(
                    int(HTTPStatus.FORBIDDEN) if is_wallet_block else int(HTTPStatus.BAD_REQUEST)
                ),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.NONE if is_wallet_block else ErrorAction.FIX_INPUT,
            ) from exc
        entry = res["linked_node"]
        safe_entry = {
            "node_id": entry["node_id"],
            "relation": entry["relation"],
            "layer_role": entry["layer_role"],
            "precedence": entry["precedence"],
            "cockpit_url": entry["cockpit_url"],
            "shared_packs": entry["shared_packs"],
        }
        body_html = SafeHTML(
            render_kpi_stat(label="Linked Node", value=str(safe_entry["node_id"])).value
            + render_kpi_stat(label="Relation", value=str(safe_entry["relation"])).value
            + render_kpi_stat(label="Total Links", value=str(res["total_linked_nodes"])).value
        )
        frag = render_card(
            title="Sovereign Node Link Registered",
            badge=str(safe_entry["layer_role"]),
            body=body_html,
        ).value
        return respond(
            req,
            html_fragment=frag,
            data={
                "capability": "node_mesh_link",
                "linked_node": safe_entry,
                "total_linked_nodes": res["total_linked_nodes"],
            },
            status=int(HTTPStatus.CREATED),
            headers=build_swap_response_headers(trigger="nodeMeshLinked"),
        )

    return router
