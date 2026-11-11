"""3-Scope Node Data Topology and self-contained HTML5 Zero-Cloud Node Cockpit renderer.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zcg.cockpit.dashboard_app import (
    MODULAR_WORKBENCH_JS,
    build_modular_workbench_spec,
    resolve_enabled_modules,
)
from zcg.cockpit.node_context import build_cockpit_passport_data
from zcg.cockpit.provenance import (
    materialize_node_provenance_surfaces,
    render_provenance_footer_html,
    resolve_domain_governance,
)
from zcg.core.blueprints import resolve_template_lineage_chain
from zcg.core.constants import (
    DEFAULT_PLUGIN_BASE_PORT,
    INDIVIDUAL_MIN_PRECEDENCE,
    REPO_DIR,
    VALID_ENVIRONMENTS,
    VALID_NODE_DATA_SCOPES,
)
from zcg.core.epistemics import resolve_knowledge_mount_endpoints
from zcg.core.manifests import canonicalize_local_node_url, load_node_manifest
from zcg.governance.consensus import evaluate_environment_promotion
from zcg.governance.ledger import summarize_work_orchestration_ledger
from zcg.topology.identity import resolve_node_entity_identity
from zcg.topology.network import discover_network_topology

VALID_DELIVERY_ZONES: tuple[str, ...] = ("Z1", "Z2", "Z3", "Z4")
TIER_LATENCY_BUDGET_MS: dict[str, int] = {
    "T1": 200, "T2": 1000, "T3": 5000, "T4": 30000, "T5": 300000,
}  # fmt: skip
HTTP_POLL_STOP_STATUS: int = 286


def resolve_node_intranet_topology(
    manifest: dict[str, Any], *, layer_id: str, active_env: str = "dev",
    workspace_dir: Path | None = None,
) -> dict[str, Any]:  # fmt: skip
    """Compute orthogonal Subdomain x Environment routing and deterministic port for a node."""
    prec = int(manifest.get("precedence", 50))
    port = int(manifest.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + prec))
    is_ind = manifest.get("entity_kind") == "individual" or prec >= INDIVIDUAL_MIN_PRECEDENCE
    p_pipe = "direct" if is_ind else "staged"
    env_order = ["dev", "pro"] if is_ind else list(VALID_ENVIRONMENTS)
    root_id = str(manifest.get("governing_root_id") or layer_id)
    root_slug = root_id.removeprefix("corp-").removesuffix("-root") or layer_id
    l_role = str(manifest.get("layer_role") or "department")
    vis = str(manifest.get("visibility") or ("public" if l_role == "knowledge" else "private"))
    is_ind_priv = is_ind and vis != "public"
    def_dom = (
        f"{layer_id}.personal.local" if is_ind_priv else (
            f"{layer_id}.knowledge.local" if l_role == "knowledge" and vis == "public"
            else f"{root_slug}.intranet.local"
        )
    )  # fmt: skip
    base_dom = str(manifest.get("base_domain") or def_dom)
    is_root_host = l_role in ("corporate", "workstation") or base_dom.startswith(f"{layer_id}.")
    node_host = base_dom if is_root_host else f"{layer_id}.{base_dom}"
    env_subs = {
        e: f"https://{node_host}" if e == "pro" else f"https://{e}.{node_host}" for e in env_order
    }
    loc_urls = {e: f"http://127.0.0.1:{port}/?env={e}" for e in env_order}
    pro_reach = (
        "local-workstation-only" if is_ind_priv
        else ("public-remote-live" if vis == "public" else "private-intranet-target")
    )  # fmt: skip
    env_reach = {
        e: "local-loopback-only" if e == "dev"
        else (pro_reach if e == "pro" else "local-preview-unprovisioned-intranet")
        for e in env_order
    }  # fmt: skip
    fb_pro = None if is_ind_priv else env_subs.get("pro")
    dom_gov = resolve_domain_governance(
        manifest, layer_id=layer_id, active_env=active_env,
        port=port, env_order=env_order, workspace_dir=workspace_dir,
    )  # fmt: skip
    return {
        "base_domain": base_dom, "node_host": node_host, "port": port,
        "promotion_pipeline": p_pipe, "visibility": vis,
        "environment_promotion_order": env_order, "environment_subdomains": env_subs,
        "local_environment_urls": loc_urls, "environment_reachability": env_reach,
        "remote_production_url": str(manifest.get("public_url") or "") or fb_pro,
        "active_subdomain_url": env_subs.get(active_env, f"https://{active_env}.{node_host}"),
        "localhost_url": f"http://127.0.0.1:{port}/?env={active_env}", **dom_gov,
    }  # fmt: skip


def _node_rep_link(n: dict[str, Any], flt_urls: dict[str, str], ldz: str = "") -> dict[str, Any]:
    nid, prec, role = str(n["node_id"]), int(n.get("precedence", 50)), str(n["layer_role"])
    port = int(n.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + prec))
    c_url = canonicalize_local_node_url(
        flt_urls.get(nid, ""), node_id=nid, layer_role=role, local_dev_zone=ldz, fallback_port=port
    )
    return {"node_id": nid, "layer_role": role, "precedence": prec, "cockpit_url": c_url}


def materialize_node_data_scopes(
    workspace_dir: Path, manifest: dict[str, Any], state_payload: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Materialize the 3-Scope Node Data Topology (node, network, federation) in surfaces/data/."""
    ws, work_led = workspace_dir.resolve(), summarize_work_orchestration_ledger(workspace_dir)
    lid, lrole = str(manifest.get("layer_id") or ws.name), str(
        manifest.get("layer_role") or "department"
    )  # fmt: skip
    mounts = [
        resolve_knowledge_mount_endpoints(m, ws)
        for m in manifest.get("mounted_layers", []) if isinstance(m, dict)
    ]  # fmt: skip
    docs_dir = ws / "docs"
    know_docs = (
        [str(f.relative_to(ws)) for f in sorted(docs_dir.rglob("*.md"))]
        if docs_dir.is_dir() else []
    )  # fmt: skip
    raw_tpls = [str(t) for t in manifest.get("default_stack_templates", [])]
    tpl_names = [n for n, _ in resolve_template_lineage_chain(raw_tpls, (ws, REPO_DIR))]
    is_ind_sub = manifest.get("entity_kind") == "individual" and lrole not in (
        "workstation", "knowledge",
    )  # fmt: skip
    has_acad = "academic-base" in tpl_names or "tutor-study-cockpit" in tpl_names
    is_ind_work = is_ind_sub and not has_acad and (
        "node-work-cockpit" in tpl_names or "business-base" in tpl_names
    )  # fmt: skip
    is_tutor = is_ind_sub and not is_ind_work
    is_secops = lrole == "domain-policy" or "secops-mcp-guardian" in tpl_names
    v_arch = (
        "workstation-control-tower" if lrole == "workstation"
        else ("personal-work-cockpit" if is_ind_work else (
            "academic-tutor-cockpit" if is_tutor else ("secops-mcp-guardian" if is_secops else (
                "corporate-root-hub" if lrole == "corporate" else (
                    "knowledge-stewardship-portal" if lrole == "knowledge"
                    else "departmental-ops-cockpit"
                )
            ))
        ))
    )  # fmt: skip
    topo = state_payload["intranet_topology"]
    is_public_know = topo["visibility"] == "public" and lrole == "knowledge"
    raw_scan = (
        [ws, *sorted((ws / "layers").glob("*"))] if is_public_know
        else [
            ws, *sorted((ws / "layers").glob("*")),
            *sorted((ws / "Projects").glob("*")), *sorted(ws.parent.glob("*")),
            *sorted((ws.parent / f"{ws.name}-org").glob("*")),
        ]
    )  # fmt: skip
    own_root = str(manifest.get("governing_root_id") or lid)
    ldz = str(
        (topo.get("domain_governance") or {}).get("local_dev_zone")
        or own_root.removeprefix("corp-").removesuffix("-root")
    )  # fmt: skip
    scan_dirs = list(
        dict.fromkeys(
            d.resolve() for d in raw_scan if (d / ".agents/runtime").is_dir() and (
                lrole == "workstation" or d.resolve() == ws or d.resolve().is_relative_to(ws)
                or str(load_node_manifest(d).get("governing_root_id") or d.name) == own_root
            )
        )
    )  # fmt: skip
    fleet_plugins = [
        {"workspace_id": lid if d == ws else str(load_node_manifest(d).get("layer_id") or d.name),
         "workspace_path": "." if d == ws else d.name,
         "plugin_id": str(rd.get("plugin_id", rf.stem)),
         "status": str(rd.get("status", "unknown")),
         "environment": str(rd.get("environment", "dev")),
         "daemon_active": bool(rd.get("daemon_active")),
         "localhost_url": str(rt_t.get("local_subdomain_dashboard_url")
                              or rt_t.get("localhost_url", "")).removesuffix("/dashboard")}
        for d in scan_dirs for rf in sorted((d / ".agents/runtime").glob("*.json"))
        if isinstance(rd := json.loads(rf.read_text("utf-8")), dict) and "plugin_id" in rd
        for rt_t in [rd.get("intranet_topology") or {}]
    ]  # fmt: skip
    flt_urls = {
        str(p["workspace_id"]): str(p["localhost_url"]).partition("?")[0].rstrip("/")
        for p in fleet_plugins
    }  # fmt: skip
    conn = discover_network_topology(ws, manifest)["node_connection_summary"]
    linked_list = [
        {"node_id": str(n["node_id"]), "relation": str(n["relation"]),
         "layer_role": str(n["layer_role"]), "precedence": int(n["precedence"]),
         "cockpit_url": canonicalize_local_node_url(
             str(n["cockpit_url"]), node_id=str(n["node_id"]),
             layer_role=str(n["layer_role"]), local_dev_zone=ldz),
         "shared_packs": list(n["shared_packs"])}
        for n in conn.get("linked_nodes", [])
    ]  # fmt: skip
    up_g = conn["upward_governor"]
    net_links = {
        "parent_home_node": _node_rep_link(up_g, flt_urls, ldz) if isinstance(up_g, dict) else None,
        "downward_child_nodes": [_node_rep_link(n, flt_urls, ldz)
                                 for n in conn["downward_governed_nodes"]],
        "lateral_peers": [_node_rep_link(n, flt_urls, ldz) for n in conn["lateral_peers"]],
        "linked_nodes": linked_list,
    }  # fmt: skip
    overlay = (
        str(manifest.get("use_case_overlay") or "personal-career-and-ventures") if is_ind_work
        else ("school-student-m1-m2" if is_tutor and manifest.get("academic_stage") == "school"
              else ("university-specialty-m2-m3" if is_tutor else v_arch))
    )  # fmt: skip
    ent_scale = (
        "medium-scaleup" if net_links["downward_child_nodes"] else "small-startup"
    ) if lrole == "corporate" else None  # fmt: skip
    act_env, ent_id = str(state_payload["environment"]), resolve_node_entity_identity(ws, manifest)
    tier, raw_mods = ("T1" if act_env == "dev" else "T2"), manifest.get("enabled_modules")
    en_mods = resolve_enabled_modules(
        v_arch, [str(m) for m in raw_mods] if isinstance(raw_mods, list) else None
    )  # fmt: skip
    rep_ctx = {
        "view_archetype": v_arch, "active_templates": tpl_names, "enabled_modules": list(en_mods),
        "public_node_identity": ent_id["public_node_identity"],
        "delivery_channel": {
            "protocol": "python314-native-asgi", "zones": list(VALID_DELIVERY_ZONES), "tier": tier,
            "latency_budget_ms": TIER_LATENCY_BUDGET_MS[tier],
            "http_poll_stop_status": HTTP_POLL_STOP_STATUS,
        },
        "runtime_telemetry": {
            "regime": "OPTIMAL", "health_score": 1.0, "telemetry_sink": ".agents/telemetry",
            "ledger_bridge": "WORKTASK.md",
        },
        "dual_world_contract": {
            "common_base_plugin": str(state_payload.get("plugin_id") or v_arch),
            "use_case_overlay": overlay, "enterprise_scale": ent_scale,
        },
        "modular_workbench": build_modular_workbench_spec(v_arch, overlay, ent_scale, en_mods),
        "workstation_config": (
            {"global_profile": str(manifest.get("global_profile") or "universal-base"),
             "interaction_language": str(manifest.get("interaction_language") or "en"),
             "precedence": int(manifest.get("precedence", 90))} if lrole == "workstation" else None
        ),
        "academic_study_state": (
            {"curriculum_tracks": ["master", "specialty/maths", "specialty/physics",
                                   "specialty/biology", "specialty/engineering",
                                   "specialty/maths-physics"],
             "study_guides": know_docs,
             "mounted_knowledge_ids": [m["layer_id"] for m in mounts]} if is_tutor else None
        ),
        "personal_work_state": (
            {"context_tracks": ["master", "opportunity/*", "venture/*", "engagement/*"],
             "linked_nodes_count": len(linked_list)} if is_ind_work else None
        ),
    }  # fmt: skip
    env_gates = {
        e: {k: evaluate_environment_promotion(ws, target_env=e, dry_run=True)[k]
            for k in ("allowed", "failed_gates")}
        for e in topo["environment_promotion_order"]
    }  # fmt: skip
    iac_stage = (
        "local-cockpit" if act_env == "dev"
        else ("production-cloud-run-gke" if act_env == "pro" else "staging-cloud-deploy")
    )  # fmt: skip
    cloud_iac = {
        "provider": "google-cloud-iac", "environment": act_env, "stage": iac_stage,
        "iac_manifest": "surfaces/infra/cloud_deployment.json",
    }  # fmt: skip
    scopes: dict[str, dict[str, Any]] = {
        "node": {"scope": "node", "layer_id": lid, "target_environments": ["dev"],
                 "representation_context": rep_ctx, "own_node_ledger": work_led["own_node_ledger"],
                 "knowledge_docs": know_docs},
        "network": {"scope": "network", "layer_id": lid,
                    "governing_root_id": str(manifest.get("governing_root_id") or lid),
                    "target_environments": ["tst", "pre"],
                    "network_representation_links": net_links,
                    "inter_layer_exchange": work_led["inter_layer_exchange"],
                    "environment_gates": env_gates},
        "federation": {"scope": "federation", "layer_id": lid, "visibility": topo["visibility"],
                       "target_environments": ["pro"], "intranet_topology": topo,
                       "mounted_layers": mounts, "fleet_plugin_inventory": fleet_plugins,
                       "cloud_iac_target": cloud_iac},
    }  # fmt: skip
    data_dir, web_dir = ws / "surfaces/data", ws / "surfaces/web"
    data_dir.mkdir(parents=True, exist_ok=True)
    web_dir.mkdir(parents=True, exist_ok=True)
    for s_name in VALID_NODE_DATA_SCOPES:
        s_txt = json.dumps(scopes[s_name], indent=2, ensure_ascii=False) + "\n"
        (data_dir / f"{s_name}_scope.json").write_text(s_txt, encoding="utf-8")
    (web_dir / "cockpit-shell.js").write_text(COCKPIT_SHELL_JS, encoding="utf-8")
    materialize_node_provenance_surfaces(ws, manifest, topo, active_env=act_env)
    return scopes


COCKPIT_SHELL_JS: str = (
    "(()=>{window.IslandBus={_h:{},on(e,f){(this._h[e]=this._h[e]||[]).push(f)},emit(e,d){"
    "(this._h[e]||[]).forEach(f=>f(d))}};const $=id=>document.getElementById(id),el="
    "$('cockpit-data');if(!el)return;const D=JSON.parse(el.textContent),T=D.intranet_topology,R="
    "D.data_scopes.node.representation_context,MW=R.modular_workbench||{},W=D.data_scopes.node."
    "own_node_ledger,G=D.data_scopes.network.environment_gates,NL=D.data_scopes.network."
    "network_representation_links||{},F=D.data_scopes.federation.fleet_plugin_inventory||[],"
    f"C=D.data_scopes.federation.cloud_iac_target;{MODULAR_WORKBENCH_JS}function render(env){{"
    "const pub=T.visibility==='public'&&env==='pro',sc=env==='dev'?'node_scope.json':(env==="
    "'pro'?'federation_scope.json':'network_scope.json'),DC=R.delivery_channel,DW="
    "R.dual_world_contract,modeLbl=pub?'Public Sovereign Node Passport (External Peer View)':"
    "'Internal Sovereign Operator Cockpit (Private / Intranet View)',cta=pub?"
    "'Open Public Website (/dashboard)':'Open Node Dashboard (/dashboard)';$('title').textContent="
    "`${D.layer_id} — ${modeLbl}`;$('sub').textContent=`Archetype: ${R.view_archetype} "
    "(${DW.use_case_overlay}) | Tier: ${DC.tier} | Health: ${R.runtime_telemetry.regime} | Scope: "
    "surfaces/data/${sc}`;renderModularWorkbench(MW,DW);$('s_hdr').textContent=pub?`Public "
    "Governance Attestation (${sc})`:`Node Work & Sprint Ledger — ${R.view_archetype}`;$('z4_hdr')"
    ".textContent=pub?'External Peer Verification & Link Commands (Z4)':'Env Switcher & "
    "Antigravity Operator Companion (Z4)';$('envs').innerHTML=`<a class='pill active' "
    "href='/dashboard'>${cta}</a>`+T.environment_promotion_order.map(e=>`<button type='button' "
    "class='pill ${e===env?\"active\":\"\"}' data-env-switch='${e}'>${e.toUpperCase()}: "
    "${(T.local_subdomain_urls||T.local_environment_urls||{})[e]||T.localhost_url}</button>`)."
    "join('');const p=NL.parent_home_node,mkL=(tag,n)=>`<code>[${tag}] ${n.node_id} "
    "(${n.layer_role||'linked'}) -> ${n.cockpit_url?`<a href='${n.cockpit_url}/dashboard'>"
    "${n.cockpit_url}/dashboard</a>`:'rcap1 corpus (make consult)'}</code>`;$('rel').innerHTML="
    "(p?mkL('Parent',p):'<code>[Root 0 Sovereign]</code>')+(NL.downward_child_nodes||[]).map(n=>"
    "mkL('Child',n)).join('')+(NL.lateral_peers||[]).map(n=>mkL('Peer',n)).join('')+"
    "(NL.linked_nodes||[]).map(n=>mkL('Link:'+n.relation,n)).join('');$('work').innerHTML=pub?"
    "`<p>Public Twin Status: <b>CERTIFIED (pro)</b> · Internal sprint items sanitized on public "
    "passport; visit <a style='color:var(--zcg-accent)' href='/dashboard'>/dashboard</a>.</p>`:`<p>"
    "Open: <b>${W.total_open_items}</b> · In Progress: <b>${W.total_in_progress_items}</b> · "
    "Completed: <b>${W.total_completed_items}</b></p>`+(W.active_node_tasks||[]).map(t=>`<code>"
    "${t}</code>`).join('');$('net').innerHTML=(D.data_scopes.node.knowledge_docs||[]).map(d=>"
    "`<code>[Doc] ${d}</code>`).join('')+(D.mounted_layers||[]).map(m=>`<code>[Knowledge] "
    "${m.layer_id} (${m.stewardship_stage}) -> ${m.active_endpoint}</code>`).join('')||"
    "'<code>Sovereign Node</code>';$('iac').innerHTML=F.map(p=>`<code>[Plugin] ${p.workspace_id}: "
    "${p.plugin_id} (${p.status} · ${p.environment})</code>`).join('')+`<code>Google Cloud IaC: "
    "${C.provider} (${C.stage}) -> </code><code>${C.iac_manifest}</code>`+Object.entries(G).map("
    '([k,v])=>`<code>Gate [${k.toUpperCase()}]: ${v.allowed?"READY":"BLOCKED"}</code>`).join(\'\');'
    "$('cmds').innerHTML=D.remote_session_commands.map(c=>`<code>${c}</code>`).join('');"
    "window.IslandBus.emit('env:change',{env,scope:sc});}document.addEventListener('click',ev=>{"
    "const b=ev.target.closest('[data-env-switch]');if(b)render(b.dataset.envSwitch);});"
    "render(new URLSearchParams(location.search).get('env')||D.plugin_state.environment);})();\n"
)


def render_node_cockpit_html(
    workspace_dir: Path, manifest: dict[str, Any], state_payload: dict[str, Any],
    *, scopes: dict[str, dict[str, Any]] | None = None,
) -> str:  # fmt: skip
    """Render the HTML5 Sovereign Node Cockpit (Internal Operator vs. Public Node Passport)."""
    eff_scopes = scopes or materialize_node_data_scopes(workspace_dir, manifest, state_payload)
    lid = str(manifest.get("layer_id") or workspace_dir.name)
    cockpit_data = build_cockpit_passport_data(lid, manifest, state_payload, eff_scopes)
    topo = state_payload["intranet_topology"]
    sub_url = topo["active_subdomain_url"]
    ftr = render_provenance_footer_html(
        workspace_dir, manifest, topo, active_env=str(state_payload.get("environment") or "dev")
    )  # fmt: skip
    json_str = json.dumps(cockpit_data, ensure_ascii=False)
    return (
        f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/><title>{lid} — Zero-Cloud"
        f" Node Cockpit ({sub_url})</title><style>:root{{--zcg-bg:#0b1020;--zcg-surface:#151d36;"
        "--zcg-accent:#38bdf8;--zcg-text:#f8fafc;--zcg-muted:#94a3b8;--zcg-border:#334155}"
        "body{font-family:system-ui,sans-serif;background:var(--zcg-bg);color:var(--zcg-text);"
        "padding:20px}.bar{display:flex;justify-content:space-between;align-items:center;gap:12px;"
        "flex-wrap:wrap;background:var(--zcg-surface);padding:16px;border-radius:12px;"
        "border:1px solid var(--zcg-border);margin-bottom:16px}.grid{display:grid;"
        "grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}.card{background:"
        "var(--zcg-surface);padding:16px;border-radius:12px;border:1px solid var(--zcg-border)}"
        ".vcard{grid-column:1/-1;border-color:var(--zcg-accent)}.pill{display:inline-block;"
        "padding:5px 11px;border-radius:99px;font-size:12px;background:#1e293b;color:"
        "var(--zcg-accent);margin:2px;cursor:pointer;border:0;text-decoration:none}.pill.active{"
        "background:var(--zcg-accent);color:var(--zcg-bg);font-weight:700}code a,"
        ".zcg-provenance-footer a{color:var(--zcg-accent)}.zcg-provenance-footer{margin-top:10px;"
        "padding-top:8px;border-top:1px solid var(--zcg-border);font-size:12px;color:#94a3b8}"
        "code{background:#090d16;padding:6px 10px;border-radius:6px;font-size:12px;color:#e2e8f0;"
        "display:block;overflow-x:auto;margin:4px 0}.zcg-provenance-footer code{display:inline;"
        "padding:2px 6px}</style></head><body data-zcg-surface='cockpit'><header class='bar' "
        "data-zone='Z1'><div><h2 id='title' style='margin:0'></h2><small id='sub' style='color:"
        "var(--zcg-muted)'></small></div><div id='envs'></div></header><main class='grid' "
        "data-zone='Z3'><section class='card vcard' id='v_panel'><h3 id='v_hdr' style='margin-top:"
        "0'></h3><div id='v_btns'></div><div id='v_out'></div></section><section class='card' "
        "data-zone='Z2'><h3>1-Hop Node Relationship Summary (Z2)</h3><div id='rel'></div></section>"
        "<section class='card'><h3 id='s_hdr'>Node Work & Sprint Ledger</h3><div id='work'></div>"
        "</section><section class='card'><h3>Epistemic Knowledge & Spec Atlas</h3><div id='net'>"
        "</div></section><section class='card'><h3>Fleet Plugins, Env-Gate & Google Cloud IaC</h3>"
        "<div id='iac'></div></section></main><footer class='bar' data-zone='Z4' style='margin-top"
        f":16px;display:block'><h3 id='z4_hdr'>Env Switcher & Antigravity Companion (Z4)</h3><div "
        f"id='cmds'></div>{ftr}</footer><script id='cockpit-data' type='application/json'>"
        f"{json_str}</script><script src='/cockpit-shell.js' defer></script></body></html>\n"
    )
