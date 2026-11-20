"""3-Scope Node Data Topology and self-contained HTML5 Zero-Cloud Node Cockpit renderer.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from zcg.cockpit.ops.posture_guard import evaluate_local_security_posture
from zcg.cockpit.ops.status import evaluate_node_health
from zcg.cockpit.routing import provenance
from zcg.cockpit.routing.surface_routing import resolve_deployment_target_summary
from zcg.cockpit.views import dashboard_app, mesh_liveness, node_context, shell_chrome
from zcg.cockpit.views.node_context import build_cockpit_passport_data
from zcg.core import constants
from zcg.core.blueprints import resolve_template_lineage_chain
from zcg.core.epistemics import resolve_knowledge_mount_endpoints
from zcg.core.manifests import canonicalize_local_node_url, load_node_manifest
from zcg.governance.runtime.skill_auditor import audit_skills_sovereign_profile
from zcg.governance.work.consensus import evaluate_environment_promotion
from zcg.governance.work.ledger import summarize_work_orchestration_ledger
from zcg.topology.exposure import is_public_portal_enabled, resolve_active_env_stages
from zcg.topology.identity import resolve_node_entity_identity
from zcg.topology.network import discover_network_topology
from zcg.web.capabilities import appearance
from zcg.web.ui.templates import SafeHTML, TemplateCatalog

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
    port = int(manifest.get("cockpit_port") or (constants.DEFAULT_PLUGIN_BASE_PORT + prec))
    is_ind = manifest.get("entity_kind") == "individual" or prec >= constants.INDIVIDUAL_MIN_PRECEDENCE  # noqa: E501  # fmt: skip
    env_order = ["dev", "pro"] if is_ind else list(constants.VALID_ENVIRONMENTS)
    root_slug = str(manifest.get("governing_root_id") or layer_id).removeprefix("corp-").removesuffix("-root") or layer_id  # noqa: E501  # fmt: skip
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
    node_host = base_dom if (l_role in ("corporate", "workstation") or base_dom.startswith(f"{layer_id}.")) else f"{layer_id}.{base_dom}"  # noqa: E501  # fmt: skip
    env_subs = {e: f"https://{node_host}" if e == "pro" else f"https://{e}.{node_host}" for e in env_order}  # noqa: E501  # fmt: skip
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
    dom_gov = provenance.resolve_domain_governance(
        manifest, layer_id=layer_id, active_env=active_env,
        port=port, env_order=env_order, workspace_dir=workspace_dir,
    )  # fmt: skip
    return {
        "base_domain": base_dom, "node_host": node_host, "port": port,
        "promotion_pipeline": "direct" if is_ind else "staged", "visibility": vis,
        "environment_promotion_order": env_order, "environment_subdomains": env_subs,
        "local_environment_urls": loc_urls, "environment_reachability": env_reach,
        "remote_production_url": str(manifest.get("public_url") or "") or (None if is_ind_priv else env_subs.get("pro")),  # noqa: E501
        "active_subdomain_url": env_subs.get(active_env, f"https://{active_env}.{node_host}"),
        "localhost_url": f"http://127.0.0.1:{port}/?env={active_env}", **dom_gov,
    }  # fmt: skip


def _node_rep_link(
    n: dict[str, Any], flt_urls: dict[str, str], ldz: str = "", entity_kind: str = "enterprise"
) -> dict[str, Any]:
    nid, prec, role = str(n["node_id"]), int(n.get("precedence", 50)), str(n["layer_role"])
    port = int(n.get("cockpit_port") or (constants.DEFAULT_PLUGIN_BASE_PORT + prec))
    c_url = canonicalize_local_node_url(
        flt_urls.get(nid, ""), node_id=nid, layer_role=role, local_dev_zone=ldz, fallback_port=port
    )
    return {
        "node_id": nid, "layer_role": role, "precedence": prec, "cockpit_url": c_url,
        "human_role": shell_chrome.resolve_human_role_label(nid, role, entity_kind=entity_kind),
    }  # fmt: skip


def resolve_manifest_view_archetype(
    workspace_dir: Path, manifest: dict[str, Any]
) -> tuple[str, list[str]]:
    """Resolve the canonical view_archetype and expanded template lineage for a node manifest."""
    ws = workspace_dir.resolve()
    lrole = str(manifest.get("layer_role") or "department")
    raw_tpls = [str(t) for t in manifest.get("default_stack_templates", [])]
    tpl_names = [n for n, _ in resolve_template_lineage_chain(raw_tpls, (ws, constants.REPO_DIR))]
    ek = str(resolve_node_entity_identity(ws, manifest)["entity_kind"]) if manifest else ""
    is_ind_sub = ek == "individual" and lrole not in ("workstation", "knowledge")
    is_secops = lrole == "domain-policy" or "secops-mcp-guardian" in tpl_names
    is_wallet = "sovereign-wallet-cockpit" in tpl_names
    has_spatial = "spatial-simulation" in tpl_names
    has_acad = "academic-base" in tpl_names or "tutor-study-cockpit" in tpl_names
    is_ind_work = is_ind_sub and not has_acad and not is_secops and not has_spatial and (
        "node-work-cockpit" in tpl_names or "business-base" in tpl_names
    )  # fmt: skip
    is_tutor = (
        is_ind_sub and not is_ind_work and not is_wallet and not is_secops and not has_spatial
    )
    v_arch = (
        "workstation-control-tower" if lrole == "workstation"
        else "sovereign-wallet-cockpit" if is_wallet
        else "secops-mcp-guardian" if is_secops
        else "personal-work-cockpit" if is_ind_work
        else "academic-tutor-cockpit" if is_tutor
        else "corporate-root-hub" if lrole == "corporate"
        else "knowledge-stewardship-portal" if lrole == "knowledge"
        else "departmental-ops-cockpit"
    )  # fmt: skip
    return v_arch, tpl_names


def materialize_node_data_scopes(
    workspace_dir: Path, manifest: dict[str, Any], state_payload: dict[str, Any],
    *, persist_files: bool = True,
) -> dict[str, dict[str, Any]]:  # fmt: skip
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
    v_arch, tpl_names = resolve_manifest_view_archetype(ws, manifest)
    is_tutor = v_arch == "academic-tutor-cockpit"
    is_ind_work = v_arch == "personal-work-cockpit"
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
    fb_ldz = own_root.removeprefix("corp-").removesuffix("-root")
    ldz = str((topo.get("domain_governance") or {}).get("local_dev_zone") or fb_ldz)
    scan_dirs = list(dict.fromkeys(
        d.resolve() for d in raw_scan if (d / ".agents/runtime").is_dir() and (
            lrole == "workstation" or d.resolve() == ws or d.resolve().is_relative_to(ws)
            or str(load_node_manifest(d).get("governing_root_id") or d.name) == own_root
        )
    ))  # fmt: skip
    fleet_plugins = [
        {"workspace_id": (
            wid := lid if d == ws else str(load_node_manifest(d).get("layer_id") or d.name)
        ),
         "workspace_path": "." if d == ws else d.name,
         "plugin_id": str(rd.get("plugin_id", rf.stem)),
         "status": str(rd.get("status", "unknown")),
         "environment": (renv := str(rd.get("environment", "dev"))),
         "daemon_active": bool(rd.get("daemon_active")),
         "localhost_url": canonicalize_local_node_url(
             str(
                 rt_t.get("local_subdomain_dashboard_url") or rt_t.get("localhost_url", "")
             ).removesuffix("/dashboard"),
             node_id=wid, active_env=renv, local_dev_zone=ldz)}
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
         "public_url": str(n.get("public_url") or ""),
         "shared_packs": list(n["shared_packs"])}
        for n in conn.get("linked_nodes", [])
    ]  # fmt: skip
    up_g, ek_n = conn["upward_governor"], str(
        resolve_node_entity_identity(ws, manifest)["entity_kind"] if manifest else "enterprise"
    )  # fmt: skip
    p_link = _node_rep_link(up_g, flt_urls, ldz, ek_n) if isinstance(up_g, dict) else None

    def _rep_l(seq: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_node_rep_link(n, flt_urls, ldz, ek_n) for n in seq]

    net_links = {
        "parent_home_node": p_link, "downward_child_nodes": _rep_l(conn["downward_governed_nodes"]),
        "lateral_peers": _rep_l(conn["lateral_peers"]),
        "knowledge_nodes": _rep_l(conn.get("knowledge_nodes", [])), "linked_nodes": linked_list,
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
    en_mods = dashboard_app.resolve_enabled_modules(
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
        "security_posture": (sec_pos := evaluate_local_security_posture(ws)),
        "skill_trust": (sk_tr := {
            "score": (sk_aud := audit_skills_sovereign_profile(ws))["trust_score"],
            "grade": "VERIFIED" if sk_aud["passed"] else "REVIEW", "passed": sk_aud["passed"],
            "finding_count": sk_aud["finding_count"],
            "scanned_skill_count": sk_aud["scanned_skill_count"],
        }),
        "node_health": evaluate_node_health(ws, security_posture=sec_pos, skill_trust=sk_tr),
        "dual_world_contract": {
            "common_base_plugin": str(state_payload.get("plugin_id") or v_arch),
            "use_case_overlay": overlay, "enterprise_scale": ent_scale,
        },
        "modular_workbench": dashboard_app.build_modular_workbench_spec(
            v_arch, overlay, ent_scale, en_mods
        ),
        "workstation_config": (
            {"global_profile": str(manifest.get("global_profile") or "universal-base"),
             "interaction_language": str(manifest.get("interaction_language") or "en"),
             "precedence": int(manifest.get("precedence", 90))} if lrole == "workstation" else None
        ),
    "academic_study_state": {
            "curriculum_tracks": ["master", "specialty/maths", "specialty/physics",
                                  "specialty/biology", "specialty/engineering",
                                  "specialty/maths-physics"],
            "study_guides": know_docs, "mounted_knowledge_ids": [m["layer_id"] for m in mounts],
        } if is_tutor else None,
        "personal_work_state": {
            "context_tracks": ["master", "opportunity/*", "venture/*", "engagement/*"],
            "linked_nodes_count": len(linked_list),
        } if is_ind_work else None,
    }  # fmt: skip
    env_gates = {
        e: {k: evaluate_environment_promotion(ws, target_env=e, dry_run=True)[k]
            for k in ("allowed", "failed_gates")}
        for e in topo["environment_promotion_order"]
    }  # fmt: skip
    deploy_target = resolve_deployment_target_summary(manifest, active_env=act_env)
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
                       "deployment_target": deploy_target},
    }  # fmt: skip
    if persist_files:
        data_dir = ws / "surfaces/data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (ws / "surfaces/web").mkdir(parents=True, exist_ok=True)
        for s_name in constants.VALID_NODE_DATA_SCOPES:
            (data_dir / f"{s_name}_scope.json").write_text(
                json.dumps(scopes[s_name], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        provenance.materialize_node_provenance_surfaces(ws, manifest, topo, active_env=act_env)
    return scopes


def render_node_cockpit_html(
    workspace_dir: Path, manifest: dict[str, Any], state_payload: dict[str, Any],
    *, scopes: dict[str, dict[str, Any]] | None = None,
    cookies: Mapping[str, str] | None = None, caller_ring: str = "R3",
) -> str:  # fmt: skip
    """Render the HTML5 Sovereign Node Cockpit via base.html + cockpit_passport.html."""
    eff_scopes = scopes or materialize_node_data_scopes(workspace_dir, manifest, state_payload)
    lid = str(manifest.get("layer_id") or workspace_dir.name)
    lrole = str(manifest.get("layer_role") or "department")
    ek = str(manifest.get("entity_kind") or "enterprise")
    act_env = str(state_payload.get("environment") or "dev")
    cockpit_data = build_cockpit_passport_data(lid, manifest, state_payload, eff_scopes)
    can_sw = appearance.can_viewer_travel_environments(caller_ring=caller_ring)
    cockpit_data["can_switch_env"] = can_sw
    topo, sub_url = state_payload["intranet_topology"], str(state_payload["intranet_topology"]["active_subdomain_url"])  # noqa: E501  # fmt: skip
    ftr = provenance.render_provenance_footer_html(workspace_dir, manifest, topo, active_env=act_env)  # noqa: E501  # fmt: skip
    app_ctx = appearance.build_appearance_template_context(
        manifest=manifest, cookies=cookies, plane="control_plane", active_env=act_env,
        caller_ring=caller_ring, env_urls=topo.get("local_subdomain_urls") or None,
        allow_node_theme=True,
    )  # fmt: skip
    prefs = shell_chrome.resolve_effective_user_prefs(workspace_dir, manifest, cookies=cookies)
    nh = (eff_scopes["node"].get("representation_context") or {}).get("node_health") or {}
    live_nl = mesh_liveness.annotate_passport_links_liveness(cockpit_data["data_scopes"]["network"]["network_representation_links"])  # noqa: E501  # fmt: skip
    cockpit_data["data_scopes"]["network"]["network_representation_links"] = live_nl
    p_node = live_nl.get("parent_home_node")
    p_url = str(p_node.get("cockpit_url") or "") if isinstance(p_node, dict) else ""
    r_on = bool(p_node.get("online", True)) if isinstance(p_node, dict) else True
    nav_it = mesh_liveness.annotate_cross_node_liveness(node_context.build_cross_node_links(lid, eff_scopes["network"], eff_scopes["federation"], manifest=manifest))  # noqa: E501  # fmt: skip
    u_menu = shell_chrome.render_user_account_menu_html(
        layer_id=lid, entity_kind=ek, layer_role=lrole, caller_ring=caller_ring,
        root_node_id=str(p_node["node_id"]) if isinstance(p_node, dict) else lid,
        root_href=f"{p_url}/" if p_url else "", root_online=r_on,
        public_portal_enabled=is_public_portal_enabled(manifest, active_env=act_env),
        health_state=str(nh.get("overall_state") or "OPTIMAL"), language_code=prefs["language"],
        health_notes=tuple(str(x) for x in (nh.get("attention_items") or ())),
        has_active_session=bool((cookies or {}).get("zcg_session")), active_plane="admin",
        constellation_html=mesh_liveness.render_menu_constellation_html(nav_it),
    )  # fmt: skip
    env_sw = SafeHTML(mesh_liveness.render_navbar_env_switcher_html(active_env=act_env, stages=resolve_active_env_stages(manifest), href_prefix="/admin", can_switch=can_sw))  # noqa: E501  # fmt: skip
    v_arch = str(manifest.get("view_archetype") or "")
    b_info = node_context.inspect_context_branches(workspace_dir, view_archetype=v_arch)
    br_dd = SafeHTML(mesh_liveness.render_navbar_branch_dropdown_html(b_info))
    th_d = {"preset": str(app_ctx["theme_preset_attr"]), "accent": str(app_ctx["theme_accent_attr"]), "logo_url": str(app_ctx["brand_logo_url"])}  # noqa: E501  # fmt: skip
    brand_card = shell_chrome.render_node_brand_settings_card_html(theme=th_d, plane="workspace")
    safe_json = SafeHTML(json.dumps(cockpit_data, ensure_ascii=False).replace("</", "<\\/"))
    rendered = TemplateCatalog().render("cockpit_passport.html", {
        **app_ctx, "csrf_token": "", "title": f"{lid} — Node Admin ({sub_url})",
        "layer_id": lid, "active_subdomain_url": sub_url, "cockpit_json": safe_json,
        "provenance_footer_html": ftr, "viewer_lang_attr": prefs["language"],
        "viewer_contrast_attr": prefs["contrast"], "viewer_scale_attr": prefs["font_scale"],
        "viewer_motion_attr": prefs["motion"], "env_switcher_html": env_sw,
        "branch_badge_html": br_dd, "user_menu_html": u_menu, "node_brand_settings_html": brand_card,  # noqa: E501
    })  # fmt: skip
    return rendered.value


def render_live_cockpit_html(
    workspace_dir: Path, *, plugin_id: str, active_env: str = "dev",
    cookies: Mapping[str, str] | None = None, caller_ring: str = "R3",
) -> bytes:  # fmt: skip
    """Render live Sovereign Node Cockpit HTML in memory without mutating disk surfaces."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    lid = str(manifest.get("layer_id") or ws.name)
    topo = resolve_node_intranet_topology(
        manifest, layer_id=lid, active_env=active_env, workspace_dir=ws
    )
    state_payload: dict[str, Any] = {
        "plugin_id": plugin_id, "status": "active", "environment": active_env,
        "daemon_active": True, "intranet_topology": topo,
    }  # fmt: skip
    scopes = materialize_node_data_scopes(ws, manifest, state_payload, persist_files=False)
    return render_node_cockpit_html(
        ws, manifest, state_payload, scopes=scopes, cookies=cookies, caller_ring=caller_ring
    ).encode("utf-8")
