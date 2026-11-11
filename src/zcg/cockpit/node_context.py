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

from zcg.cockpit.provenance import normalize_repo_web_url
from zcg.core.constants import (
    DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY,
    GIT_CMD_TIMEOUT_SECONDS,
    INDIVIDUAL_MIN_PRECEDENCE,
    VALID_KNOWLEDGE_PREFIXES,
)
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
}
DEFAULT_TRACK_BLUEPRINTS: Final[tuple[tuple[str, str], ...]] = (
    ("feature/capability-slice", "Scoped feature or policy iteration branch"),
    ("directive/cross-layer-sync", "1-hop governance delegation branch"),
)


def read_json_dict(path: Path) -> dict[str, Any]:
    """Read a JSON file into a dictionary, returning an empty dict if missing or non-object."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _posture(posture: str, badge: str, audience: str, summary: str) -> dict[str, str]:
    return {"posture": posture, "badge": badge, "audience": audience, "summary": summary}


def classify_exposure_posture(
    manifest: Mapping[str, Any], *, active_env: str = "dev"
) -> dict[str, str]:
    """Classify a node's privacy boundary and cockpit audience from manifest + environment."""
    prec = int(manifest.get("precedence", 50))
    lrole = str(manifest.get("layer_role") or "department")
    is_ind = manifest.get("entity_kind") == "individual" or prec >= INDIVIDUAL_MIN_PRECEDENCE
    vis = str(manifest.get("visibility") or ("public" if lrole == "knowledge" else "private"))
    clean_env = active_env.strip().lower() or "dev"
    if vis == "public" and clean_env == "pro":
        return _posture(
            "public-live",
            "Public Sovereign Surface (pro · External Live)",
            "External Visitors & Peer Nodes",
            "Public web/knowledge surface; runtime SQLite WAL stays outside Git.",
        )
    if vis == "public":
        return _posture(
            "public-preview",
            f"Public Twin Preview ({clean_env} · Local Staging)",
            "Pre-Release Curators",
            "Public-target repository inspected locally prior to 'pro' promotion.",
        )
    if is_ind:
        return _posture(
            "private-personal",
            "Private Local Node (Loopback Only)",
            "Sovereign Individual Only",
            "Personal configs, study tracks, and branches never leave this machine.",
        )
    return _posture(
        "private-intranet",
        "Private Enterprise Intranet (RBAC Scoped)",
        "Authorized Internal Members",
        "Internal holding, fiduciary policy, or departmental operations surface.",
    )


def build_cockpit_passport_data(
    lid: str, manifest: Mapping[str, Any], state_payload: Mapping[str, Any],
    eff_scopes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:  # fmt: skip
    """Build sanitized External Sovereign Node Passport data in public+pro or operator payload."""
    pid, env = str(state_payload["plugin_id"]), str(state_payload["environment"])
    topo = state_payload["intranet_topology"]
    is_pub_pro = topo.get("visibility") == "public" and env == "pro"
    raw_led = dict(eff_scopes["node"]["own_node_ledger"])
    pub_led = {**raw_led, "active_node_tasks": []} if is_pub_pro else raw_led
    own_flt = [
        p for p in eff_scopes["federation"]["fleet_plugin_inventory"]
        if p.get("workspace_id") == lid
    ]  # fmt: skip
    fed_copy = (
        {**eff_scopes["federation"], "fleet_plugin_inventory": own_flt}
        if is_pub_pro else eff_scopes["federation"]
    )  # fmt: skip
    raw_nl = dict(eff_scopes["network"].get("network_representation_links") or {})
    pub_nl = {
        "parent_home_node": None, "downward_child_nodes": [], "lateral_peers": [],
        "linked_nodes": raw_nl.get("linked_nodes") or [],
    }  # fmt: skip
    net_copy = (
        {**eff_scopes["network"], "network_representation_links": pub_nl}
        if is_pub_pro else eff_scopes["network"]
    )  # fmt: skip
    sub_urls = topo.get("local_subdomain_urls")
    raw_base = str(
        (sub_urls.get(env) if isinstance(sub_urls, Mapping) else "") or topo["localhost_url"]
    )
    base_u = canonicalize_local_node_url(
        raw_base, node_id=lid,
        layer_role=str(manifest.get("layer_role") or "department"), active_env=env,
    )  # fmt: skip
    cmds = (
        [
            "Public Portal -> GET /dashboard", "Liveness Probe -> GET /healthz",
            f"zcg link . --target {lid} --url {base_u} --relation knowledge-exchange",
        ]
        if is_pub_pro else [
            "/sopen", "make status", f"make install-plugin PLUGIN={pid}",
            f"make activate-plugin PLUGIN={pid} ENV={env}",
            f"make switch-env PLUGIN={pid} ENV={env}", f"make deactivate-plugin PLUGIN={pid}",
            f"make uninstall-plugin PLUGIN={pid}", "/sclose",
        ]
    )  # fmt: skip
    return {
        "layer_id": lid, "layer_role": str(manifest.get("layer_role") or "department"),
        "entity_kind": str(manifest.get("entity_kind") or "enterprise"),
        "governing_root_id": str(manifest.get("governing_root_id") or ""),
        "cockpit_posture": "public-passport" if is_pub_pro else "internal-operator",
        "plugin_state": state_payload, "intranet_topology": topo,
        "data_scopes": {
            "node": {**eff_scopes["node"], "own_node_ledger": pub_led},
            "network": net_copy, "federation": fed_copy,
        },
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
            cmd, check=False, capture_output=True, text=True, timeout=GIT_CMD_TIMEOUT_SECONDS
        )
        for line in res.stdout.splitlines():
            bname, _, head_mark = line.partition("|")
            if clean_b := bname.strip():
                local_branches.append(clean_b)
                if head_mark.strip() == "*":
                    active_branch = clean_b
    local_branches = local_branches or [active_branch]
    blueprints = ARCHETYPE_TRACK_BLUEPRINTS.get(view_archetype, DEFAULT_TRACK_BLUEPRINTS)
    bp_names = {pat for pat, _ in blueprints}
    extra_local = [
        {"branch": b, "purpose": "Local workspace branch",
         "status": "active" if b == active_branch else "created"}
        for b in local_branches if b not in bp_names
    ]  # fmt: skip
    tracks = [
        {"branch": pat, "purpose": desc,
         "status": "active" if pat == active_branch else (
             "created" if pat in local_branches else "blueprint"
         )}
        for pat, desc in blueprints
    ]  # fmt: skip
    return {
        "active_branch": active_branch, "local_branches": local_branches,
        "tracks": [*extra_local, *tracks],
    }  # fmt: skip


def collect_workstation_host_summary(ws: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Collect non-sensitive host hardware/OS metadata and governed Stow root directories."""
    present_dirs = [d for d in GOVERNED_HOST_DIRS if (ws / d).is_dir()]
    return {
        "os_kernel": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine() or "unknown",
        "python_version": platform.python_version(),
        "cpu_cores": os.cpu_count() or 1,
        "global_profile": str(manifest.get("global_profile") or "universal-base"),
        "interaction_language": str(manifest.get("interaction_language") or "en"),
        "governed_host_roots": present_dirs or ["system"],
    }


def _resolve_corpus_entry(
    lid: str,
    stage: str,
    *,
    raw_cockpit: str = "",
    raw_repo: str = "",
    raw_local: str = "",
    lrole: str = "knowledge",
    ldz: str = "",
    reg: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    if raw_cockpit.strip():
        c_u = canonicalize_local_node_url(
            raw_cockpit, node_id=lid, layer_role=lrole, local_dev_zone=ldz
        )
        return {
            "layer_id": lid, "stage": stage, "kind": "live-node", "endpoint": f"{c_u}/dashboard",
        }  # fmt: skip
    reg_e = reg.get(lid) if isinstance(reg, Mapping) else None
    reg_u = str(reg_e.get("public_url") or "") if isinstance(reg_e, Mapping) else ""
    def_u = str((DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY.get(lid) or {}).get("public_url") or "")
    cand = raw_repo.strip() or reg_u.strip() or def_u.strip()
    web_u = normalize_repo_web_url(cand) or (
        cand.rstrip("/") if cand.startswith(("https://", "http://")) else ""
    )
    if web_u:
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
            raw_local=str(m.get("active_endpoint") or ""),
            ldz=ldz, reg=reg,
        )
        for m in raw_mounts if isinstance(m, Mapping)
    ]  # fmt: skip
    if reg is not None:
        for kid, kmeta in reg.items():
            if isinstance(kmeta, Mapping) and not any(x["layer_id"] == kid for x in mounts):
                mounts.append(
                    _resolve_corpus_entry(
                        str(kid), str(kmeta.get("stewardship_stage") or "registry"),
                        raw_repo=str(kmeta.get("public_url") or ""), ldz=ldz, reg=reg,
                    )
                )  # fmt: skip
    for lnk in manifest.get("linked_nodes") or []:
        if isinstance(lnk, Mapping) and (
            lnk.get("layer_role") == "knowledge"
            or lnk.get("relation") in ("knowledge-feed", "knowledge-exchange")
        ):
            lid = str(lnk.get("node_id") or "")
            if lid and not any(x["layer_id"] == lid for x in mounts):
                mounts.append(
                    _resolve_corpus_entry(
                        lid, f"linked:{lnk.get('relation', 'corpus')}",
                        raw_cockpit=str(lnk.get("cockpit_url") or ""),
                        raw_repo=str(lnk.get("target_ref") or ""),
                        lrole=str(lnk.get("layer_role") or "knowledge"), ldz=ldz, reg=reg,
                    )
                )  # fmt: skip
    docs_dir = ws / "docs"
    guides = (
        [str(p.relative_to(ws)) for p in sorted(docs_dir.rglob("*.md"))]
        if docs_dir.is_dir() else []
    )  # fmt: skip
    return {"mounts": mounts, "study_guides": guides}


def build_cross_node_links(
    layer_id: str, net_scope: Mapping[str, Any], fed_scope: Mapping[str, Any]
) -> list[dict[str, str]]:
    """Build directional cross-node navigation items with explicit role and exposure labels."""
    rel = net_scope.get("network_representation_links")
    links_map = rel if isinstance(rel, Mapping) else {}
    raw_topo = fed_scope.get("intranet_topology")
    topo_m = raw_topo if isinstance(raw_topo, Mapping) else {}
    ldz = str(
        (topo_m.get("domain_governance") or {}).get("local_dev_zone")
        or str(net_scope.get("governing_root_id") or layer_id)
        .removeprefix("corp-")
        .removesuffix("-root")
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
    items: list[dict[str, str]] = []
    seen: set[str] = {layer_id}

    def _add(direction: str, node_id: str, role: str, base_url: str) -> None:
        raw_cand = flt_urls.get(node_id) or base_url
        eff_base = canonicalize_local_node_url(
            raw_cand, node_id=node_id, layer_role=role, local_dev_zone=ldz
        )
        if not node_id or node_id in seen or not eff_base or eff_base == own_base:
            return
        seen.add(node_id)
        is_pub = role == "knowledge" or node_id.startswith((*VALID_KNOWLEDGE_PREFIXES, "pub-"))
        stag = (
            "Public/Corpus" if is_pub
            else ("Private Local" if role in ("workstation", "project") else "Private/Intranet")
        )  # fmt: skip
        items.append(
            {"direction": direction, "node_id": node_id, "role": role,
             "scope_tag": stag, "url": f"{eff_base}/dashboard"}
        )  # fmt: skip

    parent = links_map.get("parent_home_node")
    if isinstance(parent, Mapping):
        _add(
            "↑ Governor", str(parent.get("node_id", "")),
            str(parent.get("layer_role", "root")), str(parent.get("cockpit_url", "")),
        )  # fmt: skip
    for direction, key, fb_role in (
        ("↓ Sub-Node", "downward_child_nodes", "child"),
        ("↔ Peer", "lateral_peers", "peer"),
    ):
        for entry in links_map.get(key) or []:
            if isinstance(entry, Mapping):
                _add(
                    direction, str(entry.get("node_id", "")),
                    str(entry.get("layer_role", fb_role)), str(entry.get("cockpit_url", "")),
                )  # fmt: skip
    for lnk in links_map.get("linked_nodes") or []:
        if isinstance(lnk, Mapping):
            _add(
                f"Link:{lnk.get('relation', 'link')}", str(lnk.get("node_id", "")),
                str(lnk.get("layer_role", "linked")), str(lnk.get("cockpit_url", "")),
            )  # fmt: skip
    for flt in flt_list:
        _add(
            "Fleet", str(flt.get("workspace_id", "")),
            str(flt.get("environment", "dev")), str(flt.get("localhost_url", "")),
        )  # fmt: skip
    return items
