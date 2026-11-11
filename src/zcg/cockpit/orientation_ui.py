"""SafeHTML node orientation compass, cross-node switcher, spotlights, and context router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import itertools
import json
from http import HTTPStatus
from pathlib import Path
from typing import Final

from zcg.cockpit.node_context import (
    build_cross_node_links,
    classify_exposure_posture,
    collect_knowledge_connections,
    collect_workstation_host_summary,
    inspect_context_branches,
    read_json_dict,
)
from zcg.cockpit.provenance import (
    WELL_KNOWN_ATTESTATION_PATH,
    build_public_surface_seal,
    render_provenance_footer_html,
    resolve_domain_governance,
)
from zcg.core.constants import DEFAULT_PLUGIN_BASE_PORT, KEBAB_ID_RE, SAFE_GIT_REF_RE
from zcg.web.channels import DeliveryChannel
from zcg.web.request import JSON_CONTENT_TYPE, Request, WebResponse, respond
from zcg.web.router import APIRouter
from zcg.web.security import WebAppError
from zcg.web.templates import SafeHTML, render_icon

MAX_PREVIEW_GUIDES: Final[int] = 5
_ARCHETYPE_KICKERS: Final[dict[str, tuple[str, str]]] = {
    "workstation-control-tower": ("cpu", "Workstation Root 0"),
    "academic-tutor-cockpit": ("book", "Socratic Study Lab"),
    "personal-work-cockpit": ("briefcase", "Personal Career & Ventures"),
    "corporate-root-hub": ("layers", "Corporate Root 0 Hub"),
    "secops-mcp-guardian": ("shield", "Fiduciary SecOps Guardian"),
    "knowledge-stewardship-portal": ("globe", "Knowledge Stewardship Corpus"),
}


def build_node_dashboard_enrichment(
    ws: Path, *, layer_id: str, view_archetype: str, active_env: str
) -> dict[str, object]:
    """Compose SafeHTML orientation, cross-node navigation, and archetype spotlight blocks."""
    manifest = read_json_dict(ws / "system/zcg-node.json")
    net_sc = read_json_dict(ws / "surfaces/data/network_scope.json")
    fed_sc = read_json_dict(ws / "surfaces/data/federation_scope.json")
    lrole = str(manifest.get("layer_role") or "department")
    port = int(
        (fed_sc.get("intranet_topology") or {}).get("port")
        or manifest.get("cockpit_port")
        or (DEFAULT_PLUGIN_BASE_PORT + int(manifest.get("precedence", 50)))
    )
    exp = classify_exposure_posture(manifest, active_env=active_env)
    topo = {
        "port": port,
        **resolve_domain_governance(
            manifest, layer_id=layer_id, active_env=active_env, port=port, workspace_dir=ws
        ),
        **(fed_sc.get("intranet_topology") or {}),
    }
    sub_host = str(topo["local_subdomain_host"])
    sub_dash = str(topo["local_subdomain_dashboard_url"])
    sub_urls = topo.get("local_subdomain_urls")
    cockpit_href = str(
        (sub_urls.get(active_env) if isinstance(sub_urls, dict) else "")
        or f"http://{sub_host}:{port}/?env={active_env}"
    )
    k_icon, k_label = _ARCHETYPE_KICKERS.get(view_archetype, ("briefcase", "Operational Hub"))
    kicker_s = (
        f"<span class='zcg-badge'>{render_icon(k_icon)} {html.escape(k_label)} · "
        f":{port} · {html.escape(active_env)}</span>"
    )
    docs_btn = (
        f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='/docs'>"
        f"{render_icon('book')} OpenAPI</a>"
        if active_env != "pro"
        else ""
    )
    hdr_actions_s = (
        f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        f"href='{html.escape(cockpit_href, quote=True)}'>{render_icon('shield')} Node Cockpit</a>"
        f"{docs_btn}"
        f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='/healthz'>"
        f"{render_icon('activity')} Health</a>"
    )
    b_info = inspect_context_branches(ws, view_archetype=view_archetype)
    nav_items = build_cross_node_links(layer_id, net_sc, fed_sc)
    post_icon = render_icon("globe" if exp["posture"].startswith("public") else "lock")

    orient_s = (
        "<div class='zcg-compass' role='region' aria-label='Node orientation and privacy posture'>"
        f"<div>{render_icon('compass')} <strong>Node:</strong> <code>{html.escape(layer_id)}</code>"
        f" ({html.escape(lrole)} · :{port}) · "
        f"<a class='zcg-badge' href='{html.escape(sub_dash, quote=True)}' "
        "title='Zero-root RFC 6761 local subdomain'>"
        f"{render_icon('globe')} <code>{html.escape(sub_host)}:{port}</code></a> · "
        f"<span class='zcg-badge'>{post_icon} {html.escape(exp['badge'])}</span></div>"
        "<div><span class='zcg-badge' data-zcg-view-indicator='1'>View: Overview (Node Summary)"
        f"</span> <small style='color:var(--zcg-muted)'>{html.escape(exp['summary'])}</small>"
        "</div></div>"
    )
    pills = "".join(
        f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='{html.escape(it['url'])}' "
        f"title='Target role: {html.escape(it['role'])} ({html.escape(it['scope_tag'])})'>"
        f"{render_icon('layers')} {html.escape(it['direction'])}: "
        f"<strong>{html.escape(it['node_id'])}</strong> "
        f"<small>[{html.escape(it['scope_tag'])}]</small></a>"
        for it in nav_items
    )
    nav_s = (
        "<div class='zcg-node-nav' role='navigation' aria-label='Connected sovereign nodes'>"
        f"<strong>Switch Node:</strong> {pills}</div>"
        if nav_items
        else "<div class='zcg-node-nav'><small style='color:var(--zcg-muted)'>"
        "Standalone sovereign node (0 connected 1-hop or linked peers).</small></div>"
    )
    b_chips = "".join(
        f"<span class='zcg-chip zcg-chip--{html.escape(str(t['status']))}' "
        f"title='{html.escape(str(t['purpose']))}'>"
        f"{'● ' if t['status'] == 'active' else ('✓ ' if t['status'] == 'created' else '○ ')}"
        f"<code>{html.escape(str(t['branch']))}</code></span>"
        for t in b_info.get("tracks", [])
    )
    b_pills = f"<div class='zcg-chip-list'>{b_chips}</div>"
    act_b = html.escape(str(b_info["active_branch"]))
    if view_archetype == "workstation-control-tower":
        h = collect_workstation_host_summary(ws, manifest)
        roots_s = ", ".join(f"<code>{html.escape(r)}/</code>" for r in h["governed_host_roots"])
        spot_s = (
            "<section class='zcg-card'><div class='zcg-card__header'>"
            f"<h2>{render_icon('cpu')} Host Machine, Quick Shortcuts &amp; Parallel Profiles</h2>"
            f"<span class='zcg-badge'>{render_icon('branch')} Active Branch: {act_b}</span></div>"
            f"<p><strong>Host:</strong> <code>{html.escape(str(h['os_kernel']))}</code> · "
            f"Arch: <code>{html.escape(str(h['architecture']))}</code> · "
            f"CPU: <strong>{h['cpu_cores']} cores</strong> · "
            f"Python: <code>{html.escape(str(h['python_version']))}</code> · "
            f"Profile: <code>{html.escape(str(h['global_profile']))}</code> "
            f"(lang=<code>{html.escape(str(h['interaction_language']))}</code>) · "
            f"Governed Stow Roots: {roots_s}</p>"
            "<div class='zcg-tabs' style='margin-bottom:0.65rem;'>"
            f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
            f"href='{html.escape(cockpit_href, quote=True)}'>"
            f"{render_icon('shield')} Sovereign Cockpit (/)</a>"
            f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='/docs'>"
            f"{render_icon('book')} OpenAPI Explorer (/docs)</a>"
            f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='/healthz'>"
            f"{render_icon('activity')} ASGI Probe (/healthz)</a>"
            "<button type='button' class='zcg-btn zcg-btn--sm' "
            "data-zcg-get='/api/modules/telemetry' data-zcg-target='#zcg-capability-stage'>"
            f"{render_icon('activity')} Live Runtime Telemetry</button></div>"
            "<div><strong>Parallel Machine &amp; Persona Branches:</strong>"
            f"{b_pills}</div><small>Privacy Firewall: Personal configs stay on local loopback; use "
            "an optional <code>pub-&lt;persona&gt;</code> twin for public presence.</small>"
            "</section>"
        )
    elif view_archetype == "academic-tutor-cockpit":
        kc = collect_knowledge_connections(ws, manifest, fed_sc)
        top_g = itertools.islice(kc["study_guides"], MAX_PREVIEW_GUIDES)
        guides_s = ", ".join(f"<code>{html.escape(g)}</code>" for g in top_g)
        rows = []
        for m in kc["mounts"]:
            lid_h, stg_h, ep_h = (
                html.escape(m["layer_id"]),
                html.escape(m["stage"]),
                html.escape(m["endpoint"], quote=True),
            )
            if m.get("kind") == "live-node":
                rows.append(
                    f"<div class='zcg-knowledge-row'><span>{render_icon('layers')} "
                    f"<code>{lid_h}</code> <span class='zcg-badge'>{stg_h} · Live Hub</span></span>"
                    f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='{ep_h}'>"
                    f"{render_icon('compass')} Open Live Hub</a></div>"
                )
            elif m.get("kind") == "corpus":
                rows.append(
                    f"<div class='zcg-knowledge-row'><span>{render_icon('book')} "
                    f"<code>{lid_h}</code> <span class='zcg-badge'>{stg_h} · rcap1</span></span>"
                    f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='{ep_h}' "
                    "target='_blank' rel='noopener noreferrer'>"
                    f"{render_icon('github')} GitHub Corpus {render_icon('external')}</a></div>"
                )
            else:
                rows.append(
                    f"<div class='zcg-knowledge-row'><span>{render_icon('database')} "
                    f"<code>{lid_h}</code> <span class='zcg-badge'>{stg_h}</span></span>"
                    f"<code>{ep_h} · make consult</code></div>"
                )
        mnt_s = "".join(rows) or (
            "<div class='zcg-knowledge-row'><small>Mount corpora via "
            "<code>zcg register-subtree</code> (<code>sci-*</code>, <code>gov-*</code>, "
            "<code>geo-*</code>).</small></div>"
        )
        spot_s = (
            "<section class='zcg-card'><div class='zcg-card__header'>"
            f"<h2>{render_icon('book')} Parallel Specialty Branches &amp; Epistemic Knowledge "
            "Sources</h2>"
            f"<span class='zcg-badge'>{render_icon('branch')} Active Track: {act_b} · "
            f"{len(kc['study_guides'])} Local Guides</span></div>"
            "<div><strong>Parallel Curriculum Tracks (<code>specialty/*</code>):</strong>"
            f"{b_pills}</div><div style='margin-top:0.75rem;'>"
            "<strong>Connected Knowledge Corpora (E3..E1):</strong>"
            f"<div class='zcg-knowledge-list'>{mnt_s}</div></div>"
            f"<small style='display:block;margin-top:0.5rem;'>Local Study Guides: "
            f"{guides_s or '<code>docs/</code>'}</small></section>"
        )
    elif view_archetype == "personal-work-cockpit":
        inp_css = (
            "background:var(--zcg-bg);color:var(--zcg-text);"
            "border:1px solid var(--zcg-border);border-radius:0.4rem;padding:0.4rem;"
        )
        spot_s = (
            "<section class='zcg-card'><div class='zcg-card__header'>"
            f"<h2>{render_icon('briefcase')} Parallel Career / Venture Branches &amp; Project "
            "Spin-Off Studio</h2>"
            f"<span class='zcg-badge'>{render_icon('branch')} Active Context: {act_b}</span></div>"
            "<div><strong>Parallel Context Tracks (<code>opportunity/*</code> · "
            f"<code>venture/*</code> · <code>engagement/*</code>):</strong>{b_pills}</div>"
            "<form class='zcg-tabs' style='margin-top:0.75rem;' "
            "data-zcg-get='/api/modules/node-context/spinout-preview' "
            "data-zcg-target='#zcg-spinout-out'>"
            "<input type='text' name='branch' value='venture/new-product-mvp' "
            f"aria-label='Source branch' style='{inp_css}'>"
            "<input type='text' name='project_id' value='new-product-mvp' "
            f"aria-label='New project ID' style='{inp_css}'>"
            f"<button type='submit' class='zcg-btn'>{render_icon('sparkles')} "
            "Generate Independent Spin-Off Plan</button>"
            "<button type='button' class='zcg-btn zcg-btn--secondary' "
            "data-zcg-get='/api/modules/role-projection?stage=candidate_application' "
            f"data-zcg-target='#zcg-capability-stage'>{render_icon('shield')} "
            "Preview Candidate Role Projection</button>"
            "</form><div id='zcg-spinout-out' style='margin-top:0.65rem;'></div></section>"
        )
    else:
        spot_s = (
            "<section class='zcg-card'><div class='zcg-card__header'>"
            f"<h2>{render_icon('branch')} Node Context &amp; Parallel Governance Branches "
            f"({html.escape(lrole)})</h2>"
            f"<span class='zcg-badge'>{render_icon('branch')} Active Branch: {act_b}</span></div>"
            f"<div><strong>Branches &amp; Promotion Tracks:</strong>{b_pills}</div></section>"
        )
    return {
        "exposure_posture": exp["posture"],
        "exposure_badge": exp["badge"],
        "local_subdomain_host": sub_host,
        "local_subdomain_dashboard_url": sub_dash,
        "shell_kicker_html": SafeHTML(kicker_s),
        "header_actions_html": SafeHTML(hdr_actions_s),
        "orientation_bar_html": SafeHTML(orient_s),
        "cross_node_nav_html": SafeHTML(nav_s),
        "archetype_spotlight_html": SafeHTML(spot_s),
        "provenance_footer_html": render_provenance_footer_html(
            ws, manifest, topo, active_env=active_env
        ),
    }


def create_node_context_router(workspace_dir: Path, *, view_archetype: str) -> APIRouter:
    """Mount /api/modules/node-context & /spinout-preview for branch and spin-off inspection."""
    ws = workspace_dir.resolve()
    router = APIRouter(prefix="/api/modules/node-context", tags=("node-context",))

    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="Inspect branches and posture")
    def get_node_context(req: Request) -> WebResponse:
        exp = classify_exposure_posture(read_json_dict(ws / "system/zcg-node.json"))
        b_info = inspect_context_branches(ws, view_archetype=view_archetype)
        frag = (
            f"<div class='zcg-card'><strong>{html.escape(exp['badge'])}</strong> · "
            f"Active branch: <code>{html.escape(str(b_info['active_branch']))}</code></div>"
        )
        return respond(req, html_fragment=frag, data={"exposure": exp, "branches": b_info})

    @router.get(
        "/spinout-preview",
        channel=DeliveryChannel.SWAP_SYNC,
        summary="Preview zcg spinout-project graduation recipe",
    )
    def preview_spinout(req: Request) -> WebResponse:
        branch = req.query("branch", "venture/new-product-mvp").strip()
        proj_id = req.query("project_id", "new-product-mvp").strip()
        if not KEBAB_ID_RE.match(proj_id):
            raise WebAppError(
                f"Invalid project_id {proj_id!r}: must match lowercase kebab-case",
                error_code="INVALID_PROJECT_ID",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
            )
        if not SAFE_GIT_REF_RE.match(branch) or branch in ("master", "main"):
            raise WebAppError(
                f"Invalid context branch {branch!r}: must be a non-default branch",
                error_code="INVALID_SPINOUT_BRANCH",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
            )
        b_info = inspect_context_branches(ws, view_archetype=view_archetype)
        exists = branch in b_info["local_branches"]
        prep = (
            f"# Branch '{branch}' already exists locally — ready to graduate:\n"
            if exists
            else f"git checkout -b {branch} && git checkout {b_info['active_branch']}\n"
        )
        cmd = (
            f"{prep}zcg spinout-project ../{proj_id} "
            f"--source-dir . --id {proj_id} --from-branch {branch}"
        )
        frag = (
            "<div class='zcg-alert'><strong>Spin-Off Graduation Blueprint "
            f"({'Ready' if exists else 'Create + Extract'}):</strong>"
            f"<pre style='margin:0.4rem 0 0;overflow-x:auto;'><code>{html.escape(cmd)}</code></pre>"
            '<small>Extracts clean branch files into an independent <code>layer_role: "project"'
            "</code> repository (:8780) and links both nodes via <code>spinout-project</code>."
            "</small></div>"
        )
        return respond(
            req,
            html_fragment=frag,
            data={"project_id": proj_id, "branch": branch, "branch_exists": exists, "command": cmd},
        )

    return router


def create_surface_attestation_router(
    workspace_dir: Path, *, plugin_id: str = "", web_dirs: tuple[Path, ...] = ()
) -> APIRouter:
    """Mount GET /.well-known/zcg-attestation.json for selective Web <-> Repo verification."""
    ws = workspace_dir.resolve()
    router = APIRouter(tags=("attestation",))

    @router.get(
        WELL_KNOWN_ATTESTATION_PATH,
        channel=DeliveryChannel.STATIC_SYNC,
        summary="Serve selective Web-Repo surface attestation",
    )
    def serve_surface_attestation(_req: Request) -> WebResponse:
        m_doc = read_json_dict(ws / "system/zcg-node.json")
        fed_doc = read_json_dict(ws / "surfaces/data/federation_scope.json")
        rt_doc = read_json_dict(ws / f".agents/runtime/{plugin_id}.json")
        lid = str(m_doc.get("layer_id") or ws.name)
        act_env = str(rt_doc.get("environment") or "dev")
        port = int(
            (fed_doc.get("intranet_topology") or {}).get("port")
            or m_doc.get("cockpit_port")
            or (DEFAULT_PLUGIN_BASE_PORT + int(m_doc.get("precedence", 50)))
        )
        topo = {
            **resolve_domain_governance(
                m_doc, layer_id=lid, active_env=act_env, port=port, workspace_dir=ws
            ),
            **(fed_doc.get("intranet_topology") or {}),
        }
        seal = build_public_surface_seal(ws, m_doc, topo, active_env=act_env, web_dirs=web_dirs)
        body = (json.dumps(seal, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        return WebResponse(int(HTTPStatus.OK), JSON_CONTENT_TYPE, body, DeliveryChannel.STATIC_SYNC)

    return router
