"""Cohesive 1:1 Sovereign Node 3-Scope, 1-Hop Mesh, Corpus Registry & Link/Unlink Router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Final

from zcg.cockpit.ops import mesh_studio
from zcg.cockpit.ops.metrics_studio import render_cli_transparency_hint
from zcg.cockpit.routing import network_auth
from zcg.cockpit.views.shell_chrome import resolve_human_role_label
from zcg.core.constants import (
    DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY,
    INDIVIDUAL_MIN_PRECEDENCE,
    NODE_MANIFEST_REL_PATH,
)
from zcg.core.manifests import load_node_manifest
from zcg.governance.policy.mesh_relations import configure_mesh_governance_policy
from zcg.topology.posture import resolve_governance_posture, resolve_surface_origin
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.http.channels import DeliveryChannel, build_swap_response_headers
from zcg.web.http.request import Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.components import render_card, render_kpi_stat, render_table
from zcg.web.ui.templates import SafeHTML, sanitize_url

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_NODE_MESH_PREFIX: Final[str] = "/api/modules/node-mesh"


def _read_json_dict(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return raw if isinstance(raw, dict) else {}


def _extract_link_payload(req: Request) -> dict[str, Any]:
    if "application/x-www-form-urlencoded" in req.content_type.lower():
        return dict(req.form())
    if not req.body:
        return {}
    parsed = req.json()
    if not isinstance(parsed, dict):
        raise WebAppError(
            "Node link payload must be a JSON object", error_code="INVALID_MESH_LINK_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST), severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )  # fmt: skip
    return parsed


def _resolve_available_corpora(
    ws: Path, manifest: Mapping[str, Any], connected_ids: set[str]
) -> list[dict[str, str]]:
    r_ws = network_auth.resolve_governing_root_workspace(ws, manifest)
    r_man = load_node_manifest(r_ws) if r_ws != ws else manifest
    raw_r = manifest.get("public_knowledge_registry") or r_man.get("public_knowledge_registry")
    fb = DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY if (ws / NODE_MANIFEST_REL_PATH).is_file() else {}
    reg: Mapping[str, Any] = raw_r if isinstance(raw_r, Mapping) else fb
    return [
        {"corpus_id": str(k), "domain": str(v.get("knowledge_domain") or "epistemic"), "public_url": str(v.get("public_url") or "")}  # noqa: E501
        for k, v in sorted(reg.items()) if isinstance(v, Mapping) and str(k) not in connected_ids
    ]  # fmt: skip


def _render_mesh_studio_html(
    ws: Path, *, lid: str, manifest: dict[str, Any], parent_node: dict[str, Any] | None,
    children: list[dict[str, Any]], peers: list[dict[str, Any]], linked: list[dict[str, Any]],
    mounts: list[dict[str, Any]], clean_prefix: str, banner_html: str = "",
) -> str:  # fmt: skip
    prec = int(manifest.get("precedence", 50))
    ek = str(manifest.get("entity_kind") or ("individual" if prec >= INDIVIDUAL_MIN_PRECEDENCE else "enterprise"))  # noqa: E501  # fmt: skip
    posture = resolve_governance_posture(ws, manifest)
    link_ep, unlink_ep = f"{clean_prefix}/link", f"{clean_prefix}/unlink"
    hier_ids, hier_rows, probe_cache = set[str](), list[str](), dict[int, bool]()

    def _add_hier(
        sym: str, nid: str, kind: str, raw_role: str, entry: Mapping[str, Any] | None = None
    ) -> None:
        if nid and nid not in hier_ids:
            hier_ids.add(nid)
            rl = resolve_human_role_label(nid, raw_role, entity_kind=ek)
            row = mesh_studio.render_hierarchy_node_row_html(
                ws, sym=sym, nid=nid, kind=kind, role_label=rl,
                clean_prefix=clean_prefix, entry=entry, cache=probe_cache,
            )  # fmt: skip
            hier_rows.append(row)

    if isinstance(parent_node, dict) and parent_node.get("node_id"):
        p_nid = str(parent_node["node_id"])
        _add_hier("↑", p_nid, "Root 0 / Parent", str(parent_node.get("layer_role") or "root"), parent_node)  # fmt: skip  # noqa: E501
        strip_s = f"<div class='zcg-chip-list' style='margin:0.45rem 0;'><span class='zcg-badge'>↑ {html.escape(p_nid)}</span> &rarr; <span class='zcg-chip zcg-chip--active'>● {html.escape(lid)}</span></div>"  # fmt: skip  # noqa: E501
    else:
        ch_chips = " ".join(f"<span class='zcg-badge'>↳ {html.escape(str(c.get('node_id') or ''))}</span>" for c in children if c.get("node_id"))  # fmt: skip  # noqa: E501
        strip_s = f"<div class='zcg-chip-list' style='margin:0.45rem 0;'><span class='zcg-chip zcg-chip--active'>★ {html.escape(lid)} (Root 0)</span>{f' &rarr; {ch_chips}' if ch_chips else ''}</div>"  # fmt: skip  # noqa: E501
    for ch in children:
        _add_hier("↳", str(ch.get("node_id") or ""), "child", str(ch.get("layer_role") or "child"), ch)  # fmt: skip  # noqa: E501
    for sib in peers:
        _add_hier("↔", str(sib.get("node_id") or ""), "sibling", str(sib.get("layer_role") or "sibling"), sib)  # fmt: skip  # noqa: E501
    hier_html = f"{strip_s}<ul class='zcg-knowledge-list'>{''.join(hier_rows)}</ul>" if hier_rows else "<p class='zcg-muted-note'>Standalone sovereign node.</p>"  # fmt: skip  # noqa: E501

    exp_links = [n for n in linked if isinstance(n, dict) and not mesh_studio.is_corpus_link(n)]
    corp_links = [n for n in linked if isinstance(n, dict) and mesh_studio.is_corpus_link(n)]
    dup_note = "<div class='zcg-muted-note'>Already connected via 1-Hop; cleaning up removes only the duplicate entry in <code>linked_nodes</code> without disconnecting this node.</div>"  # noqa: E501
    exp_rows = "".join(
        "<li class='zcg-knowledge-row'><div>"
        f"<strong>{html.escape(nid := str(n.get('node_id', '')))}</strong> "
        f"<span class='zcg-badge'>link:{html.escape(str(n.get('relation', '')))}</span>"
        + (f" <span class='zcg-badge zcg-health-pill--attention'>Duplicate manual entry (already in 1-Hop)</span>{dup_note}" if nid in hier_ids else "")  # noqa: E501
        + "</div>"
        + mesh_studio.render_unlink_btn(unlink_ep, nid, "Clean Up Duplicate" if nid in hier_ids else "Disconnect")  # noqa: E501
        + "</li>"
        for n in exp_links
    )  # fmt: skip
    exp_list = (
        f"<ul class='zcg-knowledge-list'>{exp_rows}</ul>"
        if exp_rows else "<p class='zcg-muted-note'>0 explicit cross-network links configured.</p>"
    )  # fmt: skip
    conn_form = (
        mesh_studio.render_link_form_html(link_ep, target_sel="#zcg-mesh-panel")
        if posture["allow_external_peer_links"]
        else "<p class='zcg-muted-note' style='margin-top:0.65rem;'>R3 Airlock Active: external peer links are disabled on wallet nodes; read-only knowledge corpora feeds remain available below.</p>"  # noqa: E501
    )

    conn_corp, conn_ids = list[str](), set[str]()
    mnt_ids = [
        mid for m in mounts if isinstance(m, dict)
        and (mid := str(m.get("layer_id") or m.get("name") or "").strip())
    ]  # fmt: skip
    for mid in mnt_ids:
        conn_ids.add(mid)
        conn_corp.append(f"<li class='zcg-knowledge-row'><span>📚 <strong>{html.escape(mid)}</strong> <span class='zcg-badge'>mounted subtree</span></span></li>")  # fmt: skip  # noqa: E501
    for cl in corp_links:
        if (cid := str(cl.get("node_id") or "").strip()) and cid not in conn_ids:
            conn_ids.add(cid)
            rel_s, btn_s = html.escape(str(cl.get("relation") or "knowledge-feed")), mesh_studio.render_unlink_btn(unlink_ep, cid, "Disconnect")  # fmt: skip  # noqa: E501
            conn_corp.append(f"<li class='zcg-knowledge-row'><span>📚 <strong>{html.escape(cid)}</strong> <span class='zcg-badge'>link:{rel_s}</span></span>{btn_s}</li>")  # fmt: skip  # noqa: E501
    conn_html = (
        f"<ul class='zcg-knowledge-list'>{''.join(conn_corp)}</ul>"
        if conn_corp else "<p class='zcg-muted-note'>0 corpora connected to this node (only connected corpora appear in Workspace).</p>"  # noqa: E501
    )  # fmt: skip
    avail = _resolve_available_corpora(ws, manifest, conn_ids)
    ep_q = html.escape(link_ep, quote=True)
    avail_rows = "".join(
        f"<li class='zcg-knowledge-row'><span><code>{html.escape(it['corpus_id'])}</code> "
        f"<small>({html.escape(it['domain'])})</small></span>"
        f'<form method="post" action="{ep_q}" data-zcg-post="{ep_q}" data-zcg-target="#zcg-mesh-panel" style="display:inline;">'  # noqa: E501
        f'<input type="hidden" name="target_id" value="{html.escape(it["corpus_id"], quote=True)}">'
        '<input type="hidden" name="relation" value="knowledge-feed">'
        f'<input type="hidden" name="target_ref" value="{html.escape(it["public_url"], quote=True)}">'  # noqa: E501
        '<button type="submit" class="zcg-btn zcg-btn--secondary zcg-btn--sm">Connect</button></form></li>'  # noqa: E501
        for it in avail
    )
    avail_hdr = "<h4 style='margin-top:0.85rem;'>Available Knowledge Registry</h4>"
    avail_html = f"{avail_hdr}<ul class='zcg-knowledge-list'>{avail_rows}</ul>" if avail_rows else ""  # fmt: skip  # noqa: E501
    kpis = "".join((
        render_kpi_stat(label="Children", value=str(len(children))).value,
        render_kpi_stat(label="Peers", value=str(len(peers))).value,
        render_kpi_stat(label="Links", value=str(len(exp_links))).value,
        render_kpi_stat(label="Connected Corpora", value=str(len(conn_ids))).value,
    ))  # fmt: skip
    gov_card = mesh_studio.render_mesh_governance_card_html(
        ws, clean_prefix=clean_prefix, children=children
    )
    cli_h = render_cli_transparency_hint(("system/zcg-node.json", "layers/*"), ("zcg link . --target <id> --relation lateral-peer", "zcg unlink . --target <id>", "make consult"))  # noqa: E501  # fmt: skip
    return (
        f"<div id='zcg-mesh-panel'>{banner_html}"
        f"<article class='zcg-card'><h3>1-Hop Hierarchy ({html.escape(lid)})</h3>"
        "<p class='zcg-muted-note'>Structural parent and child pillars resolved automatically via "
        f"<code>governing_root_id</code>.</p><div>{kpis}</div>{hier_html}</article>"
        f"{gov_card}"
        "<article class='zcg-card' style='margin-top:0.85rem;'>"
        "<h3>External &amp; Cross-Network Links (Manual <code>zcg link</code>)</h3>"
        "<p class='zcg-muted-note'>Use manual links for external partners, B2B engagements, or "
        f"independent projects outside your Root 0 hierarchy.</p>{exp_list}{conn_form}</article>"
        "<article class='zcg-card' style='margin-top:0.85rem;'><h3>Knowledge &amp; Epistemic Corpora</h3>"  # noqa: E501
        f"<h4>Connected to This Node ({len(conn_ids)})</h4>{conn_html}{avail_html}</article>"
        f"{cli_h}</div>"
    )


def create_node_mesh_router(
    workspace_dir: Path, *, prefix: str = DEFAULT_NODE_MESH_PREFIX
) -> APIRouter:
    """Create a 1:1 Sovereign Node 1-Hop, Corpus Registry & Link/Unlink APIRouter."""
    from zcg.cockpit.ops import lifecycle
    from zcg.governance.workspace.links import link_node, unlink_node

    ws = workspace_dir.resolve()
    router, clean_prefix = APIRouter(prefix=prefix, tags=("node-mesh",)), prefix.rstrip("/")

    def _snapshot(banner_html: str = "") -> tuple[str, dict[str, Any]]:
        has_m = (ws / NODE_MANIFEST_REL_PATH).is_file()
        m_doc = load_node_manifest(ws) if has_m else {}
        node_doc = _read_json_dict(ws / "surfaces/data/node_scope.json")
        net_doc = _read_json_dict(ws / "surfaces/data/network_scope.json")
        fed_doc = _read_json_dict(ws / "surfaces/data/federation_scope.json")
        lid = str(m_doc.get("layer_id") or node_doc.get("layer_id") or ws.name)
        raw_l = net_doc.get("network_representation_links")
        l_map = dict(raw_l) if isinstance(raw_l, dict) else {}
        if has_m:
            l_map["linked_nodes"] = [
                x for x in m_doc.get("linked_nodes", []) if isinstance(x, dict)
            ]
        raw_p = l_map.get("parent_home_node")
        parent_n = raw_p if isinstance(raw_p, dict) else None
        children = [c for c in (l_map.get("downward_child_nodes") or []) if isinstance(c, dict)]
        peers = [p for p in (l_map.get("lateral_peers") or []) if isinstance(p, dict)]
        linked = [n for n in (l_map.get("linked_nodes") or []) if isinstance(n, dict)]
        mounts = list(fed_doc.get("mounted_layers") or m_doc.get("mounted_layers") or [])
        frag = _render_mesh_studio_html(
            ws, lid=lid, manifest=m_doc, parent_node=parent_n, children=children,
            peers=peers, linked=linked, mounts=mounts, clean_prefix=clean_prefix,
            banner_html=banner_html,
        )  # fmt: skip
        return frag, {
            "capability": "node_mesh", "layer_id": lid, "parent_home_node": parent_n,
            "children_count": len(children), "peers_count": len(peers),
            "linked_nodes": linked, "mounted_layers_count": len(mounts),
        }  # fmt: skip

    def _refresh_scopes() -> None:
        if (ws / "surfaces/data/node_scope.json").is_file():
            lifecycle.manage_plugin_service(ws, action="provision", target_env="")

    @router.get("", summary="Inspect 1-hop node relationships, explicit links, and corpora")
    def inspect_mesh(req: Request) -> WebResponse:
        frag, data = _snapshot()
        return respond(req, html_fragment=frag, data=data)

    @router.get("/onboarding", summary="Inspect constellation posture and visual link form")
    def inspect_mesh_onboarding(req: Request) -> WebResponse:
        has_m = (ws / NODE_MANIFEST_REL_PATH).is_file()
        m_doc = load_node_manifest(ws) if has_m else {"layer_id": ws.name}
        lid = str(m_doc.get("layer_id") or ws.name)
        posture, origin = resolve_governance_posture(ws, m_doc), resolve_surface_origin(m_doc)
        pillars = mesh_studio.build_constellation_pillars(ws, lid, m_doc)
        act_h = (
            mesh_studio.render_link_form_html(
                f"{clean_prefix}/link", target_sel="#zcg-capability-stage"
            )
            if posture["allow_external_peer_links"]
            else '<p class="zcg-muted" style="margin-top:0.75rem;">R3 Airlock Active: external peer links are disabled on wallet nodes; route opt-in settlement links via your work pillar.</p>'  # noqa: E501
        )
        cols = (("pillar", "Pillar"), ("node_id", "Node"), ("status", "State"), ("airlock", "Boundary"))  # noqa: E501  # fmt: skip
        body_html = SafeHTML(
            render_kpi_stat(label="Posture", value=str(posture["governance_posture"])).value
            + render_kpi_stat(label="Ring", value=str(posture["default_surface_ring"])).value
            + render_kpi_stat(label="Origin", value=str(origin["origin_mode"])).value
            + render_table(
                columns=cols, rows=pillars, empty_message="No constellation pillars."
            ).value
            + act_h
        )
        frag = render_card(
            title=f"Visual Link & Constellation Setup ({lid})",
            badge=str(posture["governance_posture"]),
            body=body_html,
        ).value
        return respond(req, html_fragment=frag, data={
            "capability": "node_mesh_onboarding", "layer_id": lid, "posture": posture,
            "surface_origin": origin, "constellation_pillars": pillars,
        })  # fmt: skip

    @router.post("/link", channel=DeliveryChannel.SWAP_SYNC, summary="Connect node or corpus")
    def create_mesh_link(req: Request) -> WebResponse:
        payload = _extract_link_payload(req)
        tgt, frm = (
            str(payload.get("target_id") or "").strip(),
            str(payload.get("from_source") or "").strip(),
        )
        if not tgt and not frm:
            raise WebAppError(
                "Provide target_id or from_source to register a node link",
                error_code="MISSING_LINK_TARGET", http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING, action=ErrorAction.FIX_INPUT,
            )  # fmt: skip
        try:
            res = link_node(
                ws, target_id=tgt, from_source=frm,
                from_branch=str(payload.get("from_branch") or "master"),
                relation=str(payload.get("relation") or "lateral-peer"),
                target_ref=str(payload.get("target_ref") or ""),
                description=str(payload.get("description") or ""),
            )  # fmt: skip
        except ValueError as exc:
            msg, is_w = str(exc), "WALLET_EXTERNAL_LINK_BLOCKED" in str(exc)
            raise WebAppError(
                msg, error_code="WALLET_EXTERNAL_LINK_BLOCKED" if is_w else "INVALID_NODE_LINK",
                http_status=int(HTTPStatus.FORBIDDEN if is_w else HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING, action=ErrorAction.NONE if is_w else ErrorAction.FIX_INPUT,  # noqa: E501
            ) from exc  # fmt: skip
        _refresh_scopes()
        ent = res["linked_node"]
        safe = {k: ent[k] for k in ("node_id", "relation", "layer_role", "precedence", "cockpit_url", "shared_packs")}  # noqa: E501  # fmt: skip
        alert = f"<div class='zcg-alert'>Connected <code>{html.escape(str(safe['node_id']))}</code> ({html.escape(str(safe['relation']))}).</div>"  # noqa: E501
        frag, _ = _snapshot(alert)
        return respond(
            req, html_fragment=frag,
            data={"capability": "node_mesh_link", "linked_node": safe, "total_linked_nodes": res["total_linked_nodes"]},  # noqa: E501
            status=int(HTTPStatus.CREATED), headers=build_swap_response_headers(trigger="nodeMeshLinked"),  # noqa: E501
        )  # fmt: skip

    @router.post("/unlink", channel=DeliveryChannel.SWAP_SYNC, summary="Disconnect linked node")
    def remove_mesh_link(req: Request) -> WebResponse:
        payload = _extract_link_payload(req)
        try:
            res = unlink_node(ws, target_id=str(payload.get("target_id") or "").strip())
        except ValueError as exc:
            raise WebAppError(
                str(exc), error_code="INVALID_NODE_UNLINK",
                http_status=int(HTTPStatus.BAD_REQUEST), severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            ) from exc  # fmt: skip
        _refresh_scopes()
        alert = f"<div class='zcg-alert'>Disconnected <code>{html.escape(res['unlinked_node_id'])}</code>.</div>"  # noqa: E501
        frag, _ = _snapshot(alert)
        return respond(
            req, html_fragment=frag, data={"capability": "node_mesh_unlink", **res},
            headers=build_swap_response_headers(trigger="nodeMeshUnlinked"),
        )  # fmt: skip

    @router.post(
        "/policy", channel=DeliveryChannel.SWAP_SYNC,
        summary="Configure Root 0 mesh communication policy",
    )  # fmt: skip
    def update_mesh_policy(req: Request) -> WebResponse:
        pl = _extract_link_payload(req)
        add_ch, rem_ch = mesh_studio.parse_mesh_policy_mutation(pl, content_type=req.content_type)
        try:
            res = configure_mesh_governance_policy(
                ws, topology_mode=str(pl.get("topology_mode") or "").strip(),
                add_channel=add_ch, remove_channel=rem_ch,
            )  # fmt: skip
        except ValueError as exc:
            msg, is_w = str(exc), "WALLET_LATERAL_CHANNEL_BLOCKED" in str(exc)
            raise WebAppError(
                msg, error_code="WALLET_LATERAL_CHANNEL_BLOCKED" if is_w else "INVALID_MESH_POLICY",
                http_status=int(HTTPStatus.FORBIDDEN if is_w else HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING, action=ErrorAction.NONE if is_w else ErrorAction.FIX_INPUT,  # noqa: E501
            ) from exc  # fmt: skip
        _refresh_scopes()
        alert = f"<div class='zcg-alert'>Updated mesh policy (<code>{html.escape(str(res['topology_mode']))}</code>).</div>"  # noqa: E501
        frag, _ = _snapshot(alert)
        return respond(
            req, html_fragment=frag, data={"capability": "node_mesh_policy", **res},
            headers=build_swap_response_headers(trigger="nodeMeshPolicyUpdated"),
        )  # fmt: skip

    @router.post("/activate", channel=DeliveryChannel.SWAP_SYNC, summary="Start local 1-hop node workspace")  # noqa: E501  # fmt: skip
    def activate_mesh_node(req: Request) -> WebResponse:
        tgt = str(_extract_link_payload(req).get("target_id") or "").strip()
        try:
            act_res = mesh_studio.activate_local_mesh_node(ws, tgt)
        except ValueError as exc:
            is_nf = "NOT_FOUND" in str(exc)
            raise WebAppError(
                str(exc), error_code="TARGET_WORKSPACE_NOT_FOUND" if is_nf else "NODE_ACTIVATION_FAILED",  # noqa: E501
                http_status=int(HTTPStatus.NOT_FOUND if is_nf else HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING, action=ErrorAction.FIX_INPUT,
            ) from exc  # fmt: skip
        nid_h, url_h = html.escape(str(act_res["activated_node_id"])), html.escape(sanitize_url(act_res["cockpit_url"]), quote=True)  # noqa: E501  # fmt: skip
        alert = f"<div class='zcg-alert'>Activated <code>{nid_h}</code>. <a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='{url_h}'>Open Workspace →</a></div>"  # noqa: E501
        frag, _ = _snapshot(alert)
        return respond(
            req, html_fragment=frag, data={"capability": "node_mesh_activate", **act_res},
            headers=build_swap_response_headers(trigger="nodeMeshActivated"),
        )  # fmt: skip

    return router
