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

from zcg.cockpit.ops import mesh_studio
from zcg.cockpit.ops.status import evaluate_node_health
from zcg.cockpit.routing import provenance
from zcg.cockpit.views import mesh_liveness, node_context, work_board
from zcg.cockpit.views.shell_chrome import resolve_human_role_label
from zcg.core.blueprints import resolve_workspace_setup_state
from zcg.core.constants import DEFAULT_PLUGIN_BASE_PORT, INDIVIDUAL_MIN_PRECEDENCE
from zcg.core.domain import is_kebab_id, is_safe_git_ref
from zcg.core.markdown_scan import scan_markdown_checkboxes
from zcg.governance.workspace.surface_mutations import switch_workspace_context_branch
from zcg.topology.exposure import (
    classify_exposure_posture,
    is_public_portal_enabled,
    resolve_active_env_stages,
)  # fmt: skip
from zcg.web.auth.security import WebAppError
from zcg.web.http.channels import DeliveryChannel, build_swap_response_headers
from zcg.web.http.request import JSON_CONTENT_TYPE, Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.templates import SafeHTML, render_icon

MAX_PREVIEW_GUIDES: Final[int] = 5
MAX_FOCUS_TASKS: Final[int] = 3
_ARCHETYPE_KICKERS: Final[dict[str, tuple[str, str]]] = {
    "workstation-control-tower": ("cpu", "Personal & Workstation Hub"),
    "academic-tutor-cockpit": ("book", "Study & Curriculum Lab"),
    "personal-work-cockpit": ("briefcase", "Career & Ventures"),
    "corporate-root-hub": ("layers", "Corporate Root 0 Hub"),
    "secops-mcp-guardian": ("shield", "Security & Governance"),
    "knowledge-stewardship-portal": ("globe", "Epistemic Knowledge Corpus"),
    "sovereign-wallet-cockpit": ("vault", "Treasury & Portfolio"),
}


def _render_work_pulse_card(ws: Path, net_sc: dict[str, object]) -> str:
    wt, bk = ws / "WORKTASK.md", ws / "BACKLOG.md"
    w_items = scan_markdown_checkboxes(wt.read_text("utf-8")) if wt.is_file() else []
    b_items = scan_markdown_checkboxes(bk.read_text("utf-8")) if bk.is_file() else []
    todo_n = sum(1 for x in w_items if x.state == " ")
    prog_n = sum(1 for x in w_items if x.state == "/")
    done_n = sum(1 for x in w_items if x.state.lower() == "x")
    hop_n = sum(len(ch["inbound"]) for ch in work_board.collect_counterpart_work_channels(ws, net_sc))  # noqa: E501  # fmt: skip
    focus = [x for x in w_items if x.state in ("/", " ")]
    rows = "".join(
        "<div class='zcg-knowledge-row'><span>"
        f"<span class='zcg-chip'>{'In Progress' if it.state == '/' else 'To Do'}</span> "
        f"{html.escape(''.join(itertools.islice(it.body, 110)))}</span></div>"
        for it in itertools.islice(focus, MAX_FOCUS_TASKS)
    )
    list_s = rows or "<p class='zcg-muted-note'>0 active tasks queued in WORKTASK.md.</p>"
    return (
        f"<section class='zcg-card' style='margin-bottom:0.85rem;'><div class='zcg-card__header'>"
        f"<h2>{render_icon('check')} Work &amp; Collaboration Pulse</h2><div class='zcg-tabs'>"
        f"<span class='zcg-badge'>To Do: {todo_n}</span><span class='zcg-badge'>In Progress: "
        f"{prog_n}</span><span class='zcg-badge'>Done: {done_n}</span><span class='zcg-badge'>"
        f"Backlog: {len(b_items)}</span><span class='zcg-badge'>1-Hop Pending: {hop_n}</span>"
        f"</div></div><div class='zcg-knowledge-list'>{list_s}</div>"
        "<div class='zcg-tabs' style='margin-top:0.65rem;'>"
        "<button type='button' class='zcg-btn zcg-btn--sm' data-zcg-get='/api/modules/work-ledger' "
        f"data-zcg-target='#zcg-capability-stage'>{render_icon('check')} Open Work Board</button>"
        "<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        "data-zcg-get='/api/modules/docs-reader' data-zcg-target='#zcg-capability-stage'>"
        f"{render_icon('book')} Docs &amp; Knowledge</button>"
        "<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='/atlas'>"
        f"{render_icon('compass')} Network Atlas</a></div></section>"
    )


def build_node_dashboard_enrichment(
    ws: Path, *, layer_id: str, view_archetype: str, active_env: str,
    active_view_title: str = "Dashboard", ws_scope: str = "all", show_scope_bar: bool = True,
) -> dict[str, object]:  # fmt: skip
    """Compose SafeHTML orientation, 1-hop family tree, and archetype spotlight blocks."""
    manifest = node_context.read_json_dict(ws / "system/zcg-node.json")
    node_sc = node_context.read_json_dict(ws / "surfaces/data/node_scope.json")
    net_sc = node_context.read_json_dict(ws / "surfaces/data/network_scope.json")
    fed_sc = node_context.read_json_dict(ws / "surfaces/data/federation_scope.json")
    rep_sc = node_sc.get("representation_context") or {}
    nh = rep_sc.get("node_health") or evaluate_node_health(ws)
    h_st = str(nh.get("overall_state") or "OPTIMAL").upper()
    lrole = str(manifest.get("layer_role") or "department")
    m_prec = int(manifest.get("precedence", 50))
    def_ek = "individual" if m_prec >= INDIVIDUAL_MIN_PRECEDENCE else "enterprise"
    ek = str(manifest.get("entity_kind") or def_ek)
    h_role = resolve_human_role_label(layer_id, lrole, entity_kind=ek)
    port = int(
        (fed_sc.get("intranet_topology") or {}).get("port") or manifest.get("cockpit_port")
        or (DEFAULT_PLUGIN_BASE_PORT + m_prec)
    )  # fmt: skip
    exp = classify_exposure_posture(manifest, active_env=active_env)
    pub_enabled = is_public_portal_enabled(manifest, active_env=active_env)
    live_dg = provenance.resolve_domain_governance(
        manifest, layer_id=layer_id, active_env=active_env, port=port, workspace_dir=ws
    )
    topo = {"port": port, **(fed_sc.get("intranet_topology") or {}), **live_dg}
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
        f"<code>{html.escape(sub_host)}:{port}</code> · {html.escape(active_env)}</span>"
    )
    b_info = node_context.inspect_context_branches(ws, view_archetype=view_archetype)
    act_b = html.escape(str(b_info["active_branch"]))
    raw_nav = node_context.build_cross_node_links(layer_id, net_sc, fed_sc, manifest=manifest)
    nav_items = mesh_liveness.annotate_cross_node_liveness(raw_nav)
    post_icon = render_icon("globe" if exp["posture"].startswith("public") else "lock")
    parent_item = next((it for it in nav_items if it["direction"] == "↑ Governor"), None)
    p_online = bool(parent_item and parent_item.get("online") == "true")
    if parent_item is not None:
        p_nid = html.escape(parent_item["node_id"])
        p_el = (
            f"<a href='{html.escape(parent_item['url'], quote=True)}'>↑ {p_nid}</a>"
            if p_online
            else f"<span class='zcg-crumb-offline' aria-disabled='true'>⚪ ↑ {p_nid} (Offline)</span>"  # noqa: E501
        )
        crumb_s = (
            f"<div class='zcg-lineage-crumb' data-lineage='subordinate'>{p_el}"
            f"<span aria-hidden='true'>&rsaquo;</span><strong>● {html.escape(layer_id)}</strong>"
            f"<span class='zcg-crumb-role'>({html.escape(h_role)})</span></div>"
        )
    else:
        crumb_s = (
            "<div class='zcg-lineage-crumb' data-lineage='root-0'>"
            f"<span class='zcg-badge'>★ Root 0</span><strong>{html.escape(layer_id)}</strong>"
            f"<span class='zcg-crumb-role'>({html.escape(h_role)})</span></div>"
        )
    env_sw_s = mesh_liveness.render_navbar_env_switcher_html(
        active_env=active_env, stages=resolve_active_env_stages(manifest),
        env_urls=sub_urls if isinstance(sub_urls, dict) else None, href_prefix="/",
    )  # fmt: skip
    branch_bdg_s = mesh_liveness.render_navbar_branch_dropdown_html(b_info)
    scope_bar = mesh_studio.render_workspace_scope_bar_html(ws_scope) if show_scope_bar else ""
    has_m = (ws / "system/zcg-node.json").is_file()
    is_cfg = (not has_m) or bool(resolve_workspace_setup_state(ws, manifest)["is_configured"])
    setup_a = (
        "" if is_cfg else (
            f"<a class='zcg-btn zcg-btn--sm' href='/?setup=studio'>"
            f"{render_icon('sparkles')} Initial Setup</a>"
        )
    )  # fmt: skip
    orient_s = (
        "<header class='zcg-stage-head' data-surface-purpose='plugin-workbench' "
        "role='region' aria-label='Workspace objective and privacy posture'>"
        "<div class='zcg-stage-head__main'>"
        f"<h1 class='zcg-stage-head__title' data-zcg-view-indicator='1'>"
        f"{html.escape(active_view_title)}</h1>"
        f"<p class='zcg-stage-head__sub'>{html.escape(k_label)} · {html.escape(exp['summary'])}</p>"
        f"</div><div class='zcg-stage-head__actions'>{setup_a}{scope_bar}"
        f"<span class='zcg-badge'>{post_icon} {html.escape(exp['badge'])}</span></div></header>"
    )
    nav_s = mesh_liveness.render_liveness_network_tree_html(layer_id, nav_items)
    b_pills = mesh_liveness.render_branch_switcher_html(b_info)
    act_bdg = f"<span class='zcg-badge'>{render_icon('branch')} Active: {act_b}</span>"
    if view_archetype == "workstation-control-tower":
        h = node_context.collect_workstation_host_summary(ws, manifest)
        roots_s = ", ".join(f"<code>{html.escape(r)}/</code>" for r in h["governed_host_roots"])
        spot_s = (
            f"<section class='zcg-card'><div class='zcg-card__header'>"
            f"<h2>{render_icon('cpu')} Host Machine &amp; Parallel Workstation Profiles</h2>"
            f"{act_bdg}</div><p><strong>Host:</strong> <code>{html.escape(str(h['os_kernel']))}"
            f"</code> · Arch: <code>{html.escape(str(h['architecture']))}</code> · CPU: <strong>"
            f"{h['cpu_cores']} cores</strong> · Python: <code>"
            f"{html.escape(str(h['python_version']))}</code> · Profile: <code>"
            f"{html.escape(str(h['global_profile']))}</code> (lang=<code>"
            f"{html.escape(str(h['interaction_language']))}</code>) · Stow: {roots_s}</p>"
            f"<div><strong>Parallel Machine &amp; Persona Branches:</strong>{b_pills}</div>"
            "<small>Privacy Firewall: Personal configs stay on local loopback.</small></section>"
        )
    elif view_archetype == "academic-tutor-cockpit":
        kc = node_context.collect_knowledge_connections(ws, manifest, fed_sc)
        top_g = itertools.islice(kc["study_guides"], MAX_PREVIEW_GUIDES)
        guides_s = ", ".join(f"<code>{html.escape(g)}</code>" for g in top_g)
        rows, bcls = [], "zcg-btn zcg-btn--secondary zcg-btn--sm"
        for m in kc["mounts"]:
            lid_h, stg_h = html.escape(m["layer_id"]), html.escape(m["stage"])
            ep_h, kind = html.escape(m["endpoint"], quote=True), m.get("kind")
            ic = "layers" if kind == "live-node" else ("book" if kind == "corpus" else "database")
            tag = " · Live Hub" if kind == "live-node" else (" · rcap1" if kind == "corpus" else "")
            if kind == "live-node":
                rhs = f"<a class='{bcls}' href='{ep_h}'>{render_icon('compass')} Open Live Hub</a>"
            elif kind == "corpus":
                rhs = (
                    f"<a class='{bcls}' href='{ep_h}' target='_blank' rel='noopener noreferrer'>"
                    f"{render_icon('github')} GitHub Corpus {render_icon('external')}</a>"
                )
            else:
                rhs = f"<code>{ep_h} · make consult</code>"
            rows.append(
                f"<div class='zcg-knowledge-row'><span>{render_icon(ic)} <code>{lid_h}</code> "
                f"<span class='zcg-badge'>{stg_h}{tag}</span></span>{rhs}</div>"
            )
        mnt_s = "".join(rows) or (
            "<div class='zcg-knowledge-row'><small>Mount corpora via <code>zcg register-subtree"
            "</code> (<code>sci-*</code>, <code>gov-*</code>, <code>geo-*</code>).</small></div>"
        )
        spot_s = (
            f"<section class='zcg-card'><div class='zcg-card__header'><h2>{render_icon('book')} "
            "Parallel Specialty Branches &amp; Epistemic Knowledge Sources</h2>"
            f"<span class='zcg-badge'>{render_icon('branch')} {act_b} · {len(kc['study_guides'])} "
            "Guides</span></div><div><strong>Curriculum Tracks (<code>specialty/*</code>):</strong>"
            f"{b_pills}</div><div style='margin-top:0.75rem;'><strong>Connected Corpora:</strong>"
            f"<div class='zcg-knowledge-list'>{mnt_s}</div></div><small>Study Guides: "
            f"{guides_s or '<code>docs/</code>'}</small></section>"
        )
    elif view_archetype == "personal-work-cockpit":
        spot_s = (
            f"<section class='zcg-card'><div class='zcg-card__header'><h2>"
            f"{render_icon('briefcase')} Parallel Career / Venture Branches &amp; Spin-Off Studio"
            f"</h2>{act_bdg}</div><div><strong>Parallel Context Tracks:</strong>{b_pills}</div>"
            "<form class='zcg-tabs' style='margin-top:0.75rem;' "
            "data-zcg-get='/api/modules/node-context/spinout-preview' "
            "data-zcg-target='#zcg-spinout-out'>"
            "<input type='text' name='branch' value='venture/new-product-mvp' aria-label='Branch'>"
            "<input type='text' name='project_id' value='new-product-mvp' aria-label='Project ID'>"
            f"<button type='submit' class='zcg-btn'>{render_icon('sparkles')} "
            "Spin-Off Plan</button><button type='button' class='zcg-btn zcg-btn--secondary' "
            "data-zcg-get='/api/modules/role-projection?stage=candidate_application' "
            f"data-zcg-target='#zcg-capability-stage'>{render_icon('shield')} "
            "Candidate Projection</button></form><div id='zcg-spinout-out'></div></section>"
        )
    else:
        spot_s = (
            f"<section class='zcg-card'><div class='zcg-card__header'><h2>{render_icon('branch')} "
            f"Node Context &amp; Parallel Governance Branches ({html.escape(h_role)})</h2>"
            f"{act_bdg}</div><div><strong>Branches:</strong>{b_pills}</div></section>"
        )
    return {
        "exposure_posture": exp["posture"], "exposure_badge": exp["badge"],
        "entity_kind": ek, "layer_role": lrole, "human_role": h_role,
        "node_health_state": h_st,
        "root_node_id": parent_item["node_id"] if parent_item else layer_id,
        "root_href": parent_item["url"] if parent_item else "",
        "root_online": p_online if parent_item else True, "public_portal_enabled": pub_enabled,
        "local_subdomain_host": sub_host, "local_subdomain_dashboard_url": sub_dash,
        "cockpit_href": cockpit_href, "lineage_crumb_html": SafeHTML(crumb_s),
        "shell_kicker_html": SafeHTML(kicker_s), "env_switcher_html": SafeHTML(env_sw_s),
        "branch_badge_html": SafeHTML(branch_bdg_s), "header_actions_html": SafeHTML(branch_bdg_s),
        "orientation_bar_html": SafeHTML(orient_s), "cross_node_nav_html": SafeHTML(nav_s),
        "constellation_menu_html": SafeHTML(mesh_liveness.render_menu_constellation_html(nav_items)),  # noqa: E501
        "archetype_spotlight_html": SafeHTML(f"{_render_work_pulse_card(ws, net_sc)}{spot_s}"),
        "provenance_footer_html": provenance.render_provenance_footer_html(
            ws, manifest, topo, active_env=active_env
        ),
    }  # fmt: skip


def create_node_context_router(workspace_dir: Path, *, view_archetype: str) -> APIRouter:
    """Mount /api/modules/node-context, /spinout-preview, and /switch-branch."""
    ws = workspace_dir.resolve()
    router = APIRouter(prefix="/api/modules/node-context", tags=("node-context",))

    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="Inspect branches and posture")
    def get_node_context(req: Request) -> WebResponse:
        exp = classify_exposure_posture(node_context.read_json_dict(ws / "system/zcg-node.json"))
        b_info = node_context.inspect_context_branches(ws, view_archetype=view_archetype)
        frag = (
            f"<div class='zcg-card'><strong>{html.escape(exp['badge'])}</strong> · "
            f"Active branch: <code>{html.escape(str(b_info['active_branch']))}</code></div>"
        )
        return respond(req, html_fragment=frag, data={"exposure": exp, "branches": b_info})

    @router.get(
        "/spinout-preview", channel=DeliveryChannel.SWAP_SYNC,
        summary="Preview zcg spinout-project graduation recipe",
    )  # fmt: skip
    def preview_spinout(req: Request) -> WebResponse:
        branch = req.query("branch", "venture/new-product-mvp").strip()
        proj_id = req.query("project_id", "new-product-mvp").strip()
        st_422 = int(HTTPStatus.UNPROCESSABLE_ENTITY)
        if not is_kebab_id(proj_id):
            raise WebAppError(
                f"Invalid project_id {proj_id!r}: must match lowercase kebab-case",
                error_code="INVALID_PROJECT_ID", http_status=st_422,
            )  # fmt: skip
        if not is_safe_git_ref(branch) or branch in ("master", "main"):
            raise WebAppError(
                f"Invalid context branch {branch!r}: must be a non-default branch",
                error_code="INVALID_SPINOUT_BRANCH", http_status=st_422,
            )  # fmt: skip
        b_info = node_context.inspect_context_branches(ws, view_archetype=view_archetype)
        exists = branch in b_info["local_branches"]
        prep = (
            f"# Branch '{branch}' already exists locally — ready to graduate:\n" if exists
            else f"git checkout -b {branch} && git checkout {b_info['active_branch']}\n"
        )  # fmt: skip
        cmd = (
            f"{prep}zcg spinout-project ../{proj_id} "
            f"--source-dir . --id {proj_id} --from-branch {branch}"
        )
        mode_lbl = "Ready" if exists else "Create + Extract"
        frag = (
            f"<div class='zcg-alert'><strong>Spin-Off Graduation Blueprint ({mode_lbl}):</strong>"
            f"<pre style='margin:0.4rem 0 0;overflow-x:auto;'><code>{html.escape(cmd)}</code></pre>"
            '<small>Extracts clean branch files into an independent <code>layer_role: "project"'
            "</code> repository (:8780) and links both nodes via <code>spinout-project</code>."
            "</small></div>"
        )
        return respond(
            req, html_fragment=frag,
            data={"project_id": proj_id, "branch": branch, "branch_exists": exists, "command": cmd},
        )  # fmt: skip

    @router.post(
        "/switch-branch", channel=DeliveryChannel.SWAP_SYNC,
        summary="Safely switch or create a Git context branch and re-project skills",
    )  # fmt: skip
    def switch_branch(req: Request) -> WebResponse:
        form = req.form() if "urlencoded" in req.content_type.lower() else {}
        payload = form or (req.json() if req.body.strip() else {})
        d = payload if isinstance(payload, dict) else {}
        branch = str(d.get("branch") or "").strip()
        allow_create = str(d.get("allow_create", "1")).strip().lower() not in ("0", "false", "no")
        try:
            res = switch_workspace_context_branch(ws, branch=branch, allow_create=allow_create)
        except ValueError as exc:
            msg, code = str(exc), str(exc).partition(":")[0] or "BRANCH_SWITCH_BLOCKED"
            st = (
                HTTPStatus.CONFLICT if code == "WORKTREE_DIRTY" else HTTPStatus.UNPROCESSABLE_ENTITY
            )
            raise WebAppError(msg, error_code=code, http_status=int(st)) from exc
        br_h = html.escape(res["branch"])
        act_lbl = "Created & switched to" if res["created"] else "Switched to"
        frag = f"<div class='zcg-alert'>{act_lbl} <code>{br_h}</code> (skills synced).</div>"
        return respond(
            req, html_fragment=frag, data=res, headers=build_swap_response_headers(refresh=True)
        )

    return router


def create_surface_attestation_router(
    workspace_dir: Path, *, plugin_id: str = "", web_dirs: tuple[Path, ...] = ()
) -> APIRouter:
    """Mount GET /.well-known/zcg-attestation.json for selective Web <-> Repo verification."""
    ws = workspace_dir.resolve()
    router = APIRouter(tags=("attestation",))

    @router.get(
        provenance.WELL_KNOWN_ATTESTATION_PATH, channel=DeliveryChannel.STATIC_SYNC,
        summary="Serve selective Web-Repo surface attestation",
    )  # fmt: skip
    def serve_surface_attestation(_req: Request) -> WebResponse:
        m_doc = node_context.read_json_dict(ws / "system/zcg-node.json")
        fed_doc = node_context.read_json_dict(ws / "surfaces/data/federation_scope.json")
        rt_doc = node_context.read_json_dict(ws / f".agents/runtime/{plugin_id}.json")
        lid = str(m_doc.get("layer_id") or ws.name)
        act_env = str(rt_doc.get("environment") or "dev")
        port = int(
            (fed_doc.get("intranet_topology") or {}).get("port") or m_doc.get("cockpit_port")
            or (DEFAULT_PLUGIN_BASE_PORT + int(m_doc.get("precedence", 50)))
        )  # fmt: skip
        gov_d = provenance.resolve_domain_governance(
            m_doc, layer_id=lid, active_env=act_env, port=port, workspace_dir=ws
        )
        topo = {**gov_d, **(fed_doc.get("intranet_topology") or {})}
        seal = provenance.build_public_surface_seal(
            ws, m_doc, topo, active_env=act_env, web_dirs=web_dirs
        )
        body = (json.dumps(seal, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        return WebResponse(int(HTTPStatus.OK), JSON_CONTENT_TYPE, body, DeliveryChannel.STATIC_SYNC)

    return router
