"""Sovereign Exposure Posture, parallel context branch discovery, and cross-node links.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.routing.provenance import normalize_repo_web_url
from zcg.cockpit.views.shell_chrome import resolve_human_role_label
from zcg.core import constants
from zcg.core.manifests import canonicalize_local_node_url

GOVERNED_HOST_DIRS: Final[tuple[str, ...]] = ("bash", "git", "system", "antigravity")
ARCHETYPE_TRACK_BLUEPRINTS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "workstation-control-tower": (
        ("machine/laptop-linux", "Parallel hardware / OS workstation profile"),
        ("machine/studio-desktop", "Secondary desktop Stow & host package target"),
        ("hat/research", "Focused deep-work / offline research persona"),
    ),
    "academic-tutor-cockpit": (
        ("specialty/maths", "Formal mathematics & proof derivations (M1..M4)"),
        ("specialty/physics", "Classical & modern physics lab track"),
        ("specialty/biology", "Biological systems & experimental methodology"),
        ("specialty/engineering", "Applied systems & software engineering"),
        ("specialty/maths-physics", "Coupled mathematical physics synthesis"),
    ),
    "personal-work-cockpit": (
        ("opportunity/role-application", "Minimal-disclosure candidate dossier track"),
        ("venture/new-product-mvp", "Incubated startup / product spin-off candidate"),
        ("engagement/advisory-client", "Scoped B2B consulting or partner engagement"),
    ),
    "secops-mcp-guardian": (
        ("context/constellation-audit", "Cross-node posture, drift & ring verification"),
        ("context/device-hardening", "Workstation, endpoint & tool-sandbox hardening"),
        ("context/patrimony-vault", "Assets, credentials hygiene & recovery drills"),
        ("context/travel-jurisdiction", "Country travel + gov-*/geo-* risk advisories"),
    ),
}
DEFAULT_TRACK_BLUEPRINTS: Final[tuple[tuple[str, str], ...]] = (
    ("feature/capability-slice", "Scoped feature or policy iteration branch"),
    ("directive/cross-layer-sync", "1-hop governance delegation branch"),
)


def read_json_dict(path: Path) -> dict[str, Any]:
    """Read a JSON file into a dictionary, returning an empty dict if missing or non-object."""
    raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return raw if isinstance(raw, dict) else {}


def _canonicalize_passport_topology(
    topo: Mapping[str, Any], *, lid: str, lrole: str, env: str, port: int
) -> dict[str, Any]:
    dg = topo.get("domain_governance")
    ldz = str(dg.get("local_dev_zone") or "") if isinstance(dg, Mapping) else ""
    raw_loc = str(topo.get("local_subdomain_url") or topo.get("localhost_url") or "")
    base_loc = canonicalize_local_node_url(
        raw_loc, node_id=lid, layer_role=lrole,
        local_dev_zone=ldz, active_env=env, fallback_port=port,
    )  # fmt: skip
    raw_envs = topo.get("local_subdomain_urls") or topo.get("local_environment_urls")
    out: dict[str, Any] = {**topo, "localhost_url": f"{base_loc}/?env={env}"}
    if isinstance(raw_envs, Mapping):
        out["local_environment_urls"] = {
            str(
                k
            ): f"{canonicalize_local_node_url(str(v), node_id=lid, layer_role=lrole, local_dev_zone=ldz, active_env=str(k), fallback_port=port)}/?env={k}"  # noqa: E501
            for k, v in raw_envs.items()
        }
    return out


def build_cockpit_passport_data(
    lid: str, manifest: Mapping[str, Any], state_payload: Mapping[str, Any],
    eff_scopes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:  # fmt: skip
    """Build sanitized External Sovereign Node Passport data in public+pro or operator payload."""
    pid, env = str(state_payload["plugin_id"]), str(state_payload["environment"])
    lrole = str(manifest.get("layer_role") or "department")
    raw_topo = state_payload["intranet_topology"]
    port = int(
        raw_topo.get("port") or manifest.get("cockpit_port")
        or (constants.DEFAULT_PLUGIN_BASE_PORT + int(manifest.get("precedence", 50)))
    )  # fmt: skip
    topo = _canonicalize_passport_topology(raw_topo, lid=lid, lrole=lrole, env=env, port=port)
    c_state = {**state_payload, "intranet_topology": topo}
    is_pub_pro = topo.get("visibility") == "public" and env == "pro"
    raw_led = dict(eff_scopes["node"]["own_node_ledger"])
    pub_led = {**raw_led, "active_node_tasks": []} if is_pub_pro else raw_led
    own_flt = [
        p for p in eff_scopes["federation"]["fleet_plugin_inventory"]
        if p.get("workspace_id") == lid
    ]  # fmt: skip
    raw_fed_t = eff_scopes["federation"].get("intranet_topology")
    fed_base = (
        {**eff_scopes["federation"], "intranet_topology": _canonicalize_passport_topology(
            raw_fed_t, lid=lid, lrole=lrole, env=env, port=port,
        )} if isinstance(raw_fed_t, Mapping) else dict(eff_scopes["federation"])
    )  # fmt: skip
    fed_copy = {**fed_base, "fleet_plugin_inventory": own_flt} if is_pub_pro else fed_base
    raw_nl = dict(eff_scopes["network"].get("network_representation_links") or {})
    pub_nl = {
        "parent_home_node": None, "downward_child_nodes": [], "lateral_peers": [],
        "linked_nodes": raw_nl.get("linked_nodes") or [],
    }  # fmt: skip
    net_copy = (
        {**eff_scopes["network"], "network_representation_links": pub_nl}
        if is_pub_pro else eff_scopes["network"]
    )  # fmt: skip
    base_u = topo["localhost_url"].partition("?")[0].rstrip("/")
    cmds = (
        ["Public Portal -> GET /dashboard", "Liveness Probe -> GET /healthz",
         f"zcg link . --target {lid} --url {base_u} --relation knowledge-exchange"]
        if is_pub_pro else [
            "/sopen", "make status", f"make install-plugin PLUGIN={pid}",
            f"make activate-plugin PLUGIN={pid} ENV={env}",
            f"make switch-env PLUGIN={pid} ENV={env}", f"make deactivate-plugin PLUGIN={pid}",
            f"make uninstall-plugin PLUGIN={pid}", "/sclose",
        ]
    )  # fmt: skip
    ek = str(manifest.get("entity_kind") or "enterprise")
    return {
        "layer_id": lid, "layer_role": lrole, "entity_kind": ek,
        "human_role": resolve_human_role_label(lid, lrole, entity_kind=ek),
        "governing_root_id": str(manifest.get("governing_root_id") or ""),
        "cockpit_posture": "public-passport" if is_pub_pro else "internal-operator",
        "plugin_state": c_state, "intranet_topology": topo,
        "data_scopes": {"node": {**eff_scopes["node"], "own_node_ledger": pub_led},
                        "network": net_copy, "federation": fed_copy},
        "work_orchestration": {
            "own_node_ledger": pub_led,
            "inter_layer_exchange": eff_scopes["network"]["inter_layer_exchange"],
        },
        "mounted_layers": eff_scopes["federation"]["mounted_layers"],
        "remote_session_commands": cmds,
    }  # fmt: skip


def inspect_context_branches(ws: Path, *, view_archetype: str) -> dict[str, Any]:
    """List local Git branches alongside recommended parallel context track blueprints."""
    active_branch, local_branches, git_bin = "master", [], shutil.which("git")
    if (ws / ".git").exists() and git_bin is not None:
        cmd = [
            git_bin, "-C", str(ws), "for-each-ref", "--format=%(refname:short)|%(HEAD)",
            "refs/heads",
        ]  # fmt: skip
        res = subprocess.run(  # noqa: S603
            cmd, check=False, capture_output=True, text=True,
            timeout=constants.GIT_CMD_TIMEOUT_SECONDS,
        )  # fmt: skip
        for line in res.stdout.splitlines():
            bname, _, head_mark = line.partition("|")
            if clean_b := bname.strip():
                local_branches.append(clean_b)
                if head_mark.strip() == "*":
                    active_branch = clean_b
    local_branches = local_branches or [active_branch]
    bp_list = ARCHETYPE_TRACK_BLUEPRINTS.get(view_archetype, DEFAULT_TRACK_BLUEPRINTS)
    bp_desc = dict(bp_list)
    tracks = [
        {"branch": b, "purpose": bp_desc.get(b, "Local workspace branch"),
         "status": "active" if b == active_branch else "created"} for b in local_branches
    ]  # fmt: skip
    return {
        "active_branch": active_branch, "local_branches": local_branches, "tracks": tracks,
        "blueprints": [{"branch": p, "purpose": d} for p, d in bp_list if p not in local_branches],
    }  # fmt: skip


def collect_workstation_host_summary(ws: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Collect non-sensitive host hardware/OS metadata and governed Stow root directories."""
    present_dirs = [d for d in GOVERNED_HOST_DIRS if (ws / d).is_dir()]
    return {
        "os_kernel": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine() or "unknown", "cpu_cores": os.cpu_count() or 1,
        "python_version": platform.python_version(),
        "global_profile": str(manifest.get("global_profile") or "universal-base"),
        "interaction_language": str(manifest.get("interaction_language") or "en"),
        "governed_host_roots": present_dirs or ["system"],
    }  # fmt: skip


def _resolve_corpus_public_url(
    lid: str, raw_repo: str = "", reg: Mapping[str, Any] | None = None
) -> str:
    reg_e = reg.get(lid) if isinstance(reg, Mapping) else None
    r_u = str(reg_e.get("public_url") or "") if isinstance(reg_e, Mapping) else ""
    d_u = str((constants.DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY.get(lid) or {}).get("public_url") or "")
    cand = raw_repo.strip() or r_u.strip() or d_u.strip()
    return normalize_repo_web_url(cand) or (
        cand.rstrip("/") if cand.startswith(("https://", "http://")) else ""
    )


def _resolve_corpus_entry(
    lid: str, stage: str, *, raw_cockpit: str = "", raw_repo: str = "",
    raw_local: str = "", lrole: str = "knowledge", ldz: str = "",
    reg: Mapping[str, Any] | None = None,
) -> dict[str, str]:  # fmt: skip
    if raw_cockpit.strip():
        c_u = canonicalize_local_node_url(
            raw_cockpit, node_id=lid, layer_role=lrole, local_dev_zone=ldz
        )
        return {"layer_id": lid, "stage": stage, "kind": "live-node", "endpoint": f"{c_u}/"}
    if web_u := _resolve_corpus_public_url(lid, raw_repo, reg):
        return {"layer_id": lid, "stage": stage, "kind": "corpus", "endpoint": web_u}
    return {
        "layer_id": lid, "stage": stage, "kind": "local-mount",
        "endpoint": raw_local.strip() or f"layers/{lid}",
    }  # fmt: skip


def collect_knowledge_connections(
    ws: Path, manifest: Mapping[str, Any], fed_scope: Mapping[str, Any]
) -> dict[str, Any]:
    """Collect mounted epistemic layers, local docs guides, and registered knowledge corpora."""
    raw_topo = fed_scope.get("intranet_topology")
    topo_m = raw_topo if isinstance(raw_topo, Mapping) else {}
    own_root = str(manifest.get("governing_root_id") or manifest.get("layer_id") or ws.name)
    ldz = str(
        (topo_m.get("domain_governance") or {}).get("local_dev_zone")
        or own_root.removeprefix("corp-").removesuffix("-root")
    )
    raw_reg = manifest.get("public_knowledge_registry")
    reg = raw_reg if isinstance(raw_reg, Mapping) else None
    raw_mounts = fed_scope.get("mounted_layers") or manifest.get("mounted_layers") or []
    mounts = [
        _resolve_corpus_entry(
            str(m.get("layer_id") or m.get("name") or "corpus"),
            str(m.get("stewardship_stage") or "mounted"),
            raw_repo=str(m.get("public_url") or m.get("repository") or ""),
            raw_local=str(m.get("active_endpoint") or ""), ldz=ldz, reg=reg,
        )
        for m in raw_mounts if isinstance(m, Mapping)
    ]  # fmt: skip
    available_registry = [
        _resolve_corpus_entry(
            str(kid), str(kmeta.get("stewardship_stage") or "registry"),
            raw_repo=str(kmeta.get("public_url") or ""), ldz=ldz, reg=reg,
        )
        for kid, kmeta in (reg.items() if reg is not None else ())
        if isinstance(kmeta, Mapping) and not any(x["layer_id"] == kid for x in mounts)
    ]  # fmt: skip
    for lnk in manifest.get("linked_nodes") or []:
        if isinstance(lnk, Mapping) and (
            lnk.get("layer_role") == "knowledge"
            or lnk.get("relation") in ("knowledge-feed", "knowledge-exchange")
        ):
            lid = str(lnk.get("node_id") or "")
            if lid and not any(x["layer_id"] == lid for x in mounts):
                mounts.append(_resolve_corpus_entry(
                    lid, f"linked:{lnk.get('relation', 'corpus')}",
                    raw_cockpit=str(lnk.get("cockpit_url") or ""),
                    raw_repo=str(lnk.get("target_ref") or ""),
                    lrole=str(lnk.get("layer_role") or "knowledge"), ldz=ldz, reg=reg,
                ))  # fmt: skip
    connected_ids = {x["layer_id"] for x in mounts}
    available_registry = [x for x in available_registry if x["layer_id"] not in connected_ids]
    docs_dir = ws / "docs"
    guides = (
        [str(p.relative_to(ws)) for p in sorted(docs_dir.rglob("*.md"))]
        if docs_dir.is_dir() else []
    )  # fmt: skip
    return {"mounts": mounts, "available_registry": available_registry, "study_guides": guides}


def _classify_horizon_group(direction: str, node_id: str, role: str) -> tuple[int, str]:
    if direction == "★ Pinned":
        return 0, "Pinned"
    if direction in ("↑ Governor", "↓ Sub-Node", "↔ Peer"):
        return 1, "1-Hop Hierarchy"
    if node_id.startswith(constants.PUBLIC_GOV_PREFIXES):
        return 3, "Public Admin"
    if (
        direction == "📚 Corpus" or role == "knowledge"
        or node_id.startswith(constants.VALID_KNOWLEDGE_PREFIXES)
        or direction.startswith("Link:knowledge")
    ):  # fmt: skip
        return 4, "Knowledge"
    return (2, "Peers & B2B") if direction.startswith("Link:") else (5, "Fleet")


def build_cross_node_links(
    layer_id: str, net_scope: Mapping[str, Any], fed_scope: Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:  # fmt: skip
    """Build directional cross-node navigation items ordered by Daily Conscious Horizon weight."""
    rel = net_scope.get("network_representation_links")
    raw_topo = fed_scope.get("intranet_topology")
    links_map = rel if isinstance(rel, Mapping) else {}
    topo_m = raw_topo if isinstance(raw_topo, Mapping) else {}
    own_root = str(net_scope.get("governing_root_id") or layer_id)
    ldz = str(
        (topo_m.get("domain_governance") or {}).get("local_dev_zone")
        or own_root.removeprefix("corp-").removesuffix("-root")
    )
    raw_own = str(topo_m.get("local_subdomain_dashboard_url") or topo_m.get("localhost_url") or "")
    own_base = canonicalize_local_node_url(
        raw_own.removesuffix("/dashboard"), node_id=layer_id, local_dev_zone=ldz
    )
    flt_list = [
        flt for flt in (fed_scope.get("fleet_plugin_inventory") or [])
        if isinstance(flt, Mapping) and flt.get("workspace_path") != "."
    ]  # fmt: skip
    flt_urls = {
        str(f.get("workspace_id", "")): str(f.get("localhost_url", "")).removesuffix("/dashboard")
        for f in flt_list
    }
    m_doc = manifest if isinstance(manifest, Mapping) else {}
    raw_reg = m_doc.get("public_knowledge_registry")
    reg_m = raw_reg if isinstance(raw_reg, Mapping) else None
    m_prec = int(m_doc.get("precedence", 50))
    ek = str(m_doc.get("entity_kind") or (
        "individual" if m_prec >= constants.INDIVIDUAL_MIN_PRECEDENCE else "enterprise"
    ))  # fmt: skip
    ranked: list[tuple[int, int, dict[str, str]]] = []
    seen: set[str] = {layer_id}

    def _add(d: str, nid: str, role: str, base_u: str, fb_pub: str = "") -> None:
        raw_c = (flt_urls.get(nid) or base_u).strip()
        is_ext = raw_c.startswith("https://") and ".localhost" not in raw_c
        eff_b = (
            raw_c.rstrip("/") if is_ext else canonicalize_local_node_url(
                raw_c.removesuffix("/dashboard").rstrip("/"),
                node_id=nid, layer_role=role, local_dev_zone=ldz,
            )
        )  # fmt: skip
        if not eff_b and fb_pub:
            eff_b, is_ext = fb_pub, True
        if not nid or nid in seen or not eff_b or eff_b == own_base:
            return
        seen.add(nid)
        pub_pfx = (*constants.VALID_KNOWLEDGE_PREFIXES, "pub-")
        stag = (
            "Public/Corpus" if (role == "knowledge" or nid.startswith(pub_pfx))
            else ("Private Local" if role in ("workstation", "project") else "Private/Intranet")
        )  # fmt: skip
        rank, hgrp = _classify_horizon_group(d, nid, role)
        h_role = resolve_human_role_label(nid, role, entity_kind=ek)
        ranked.append((rank, len(ranked), {
            "direction": d, "node_id": nid, "role": role, "role_label": h_role,
            "scope_tag": stag, "horizon_group": hgrp, "url": eff_b if is_ext else f"{eff_b}/",
        }))  # fmt: skip

    for pin in (p for p in (m_doc.get("pinned_places") or []) if isinstance(p, Mapping)):
        _add("★ Pinned", str(pin.get("node_id") or pin.get("label") or ""),
             str(pin.get("layer_role") or "pinned"),
             str(pin.get("url") or pin.get("cockpit_url") or ""))  # fmt: skip
    if isinstance(parent := links_map.get("parent_home_node"), Mapping):
        _add("↑ Governor", str(parent.get("node_id", "")), str(parent.get("layer_role", "root")),
             str(parent.get("cockpit_url", "")))  # fmt: skip
    for d_lbl, key, fb_r in (("↓ Sub-Node", "downward_child_nodes", "child"),
                             ("↔ Peer", "lateral_peers", "peer")):  # fmt: skip
        for e in (x for x in (links_map.get(key) or []) if isinstance(x, Mapping)):
            _add(d_lbl, str(e.get("node_id", "")), str(e.get("layer_role", fb_r)),
                 str(e.get("cockpit_url", "")))  # fmt: skip
    raw_lnks = (*(links_map.get("linked_nodes") or []), *(m_doc.get("linked_nodes") or []))
    for lnk in (e for e in raw_lnks if isinstance(e, Mapping)):
        nid, l_rel = str(lnk.get("node_id", "")), str(lnk.get("relation", "link"))
        l_role = str(lnk.get("layer_role", "linked"))
        is_kn = l_role == "knowledge" or l_rel in ("knowledge-feed", "knowledge-exchange")
        raw_p = str(lnk.get("public_url") or lnk.get("target_ref") or "")
        fb_p = _resolve_corpus_public_url(nid, raw_p, reg_m) if is_kn else ""
        _add(f"Link:{l_rel}", nid, l_role, str(lnk.get("cockpit_url", "")), fb_p)
    raw_mnts = (*(links_map.get("knowledge_nodes") or []), *(fed_scope.get("mounted_layers") or []), *(m_doc.get("mounted_layers") or []))  # noqa: E501  # fmt: skip
    for mnt in (e for e in raw_mnts if isinstance(e, Mapping)):
        mid = str(mnt.get("node_id") or mnt.get("layer_id") or mnt.get("name") or "")
        fb_m = _resolve_corpus_public_url(
            mid, str(mnt.get("public_url") or mnt.get("repository") or ""), reg_m
        )
        _add("📚 Corpus", mid, "knowledge", str(mnt.get("cockpit_url") or ""), fb_m)
    for flt in flt_list:
        _add("Fleet", str(flt.get("workspace_id", "")), str(flt.get("environment", "dev")),
             str(flt.get("localhost_url", "")))  # fmt: skip
    return [item for _r, _i, item in sorted(ranked, key=lambda t: (t[0], t[1]))]
