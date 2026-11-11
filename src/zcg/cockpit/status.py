"""Single-call consolidated status & cockpit telemetry digest for /sopen and node ops.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zcg.cockpit.lifecycle import summarize_runtime_orchestration
from zcg.core.blueprints import resolve_template_lineage_chain, resolve_workspace_setup_state
from zcg.core.constants import (
    BASE_SKILL_TAXONOMY,
    COMMAND_CONSCIOUSNESS_TIERS,
    LAYER_ROLE_MAKEFILE_TARGETS,
    MAKEFILE_DOMAIN_TAXONOMY,
    NODE_MANIFEST_REL_PATH,
    REPO_DIR,
    ROLE_DEFAULT_PRECEDENCE,
    STATUS_EXCERPT_MAX_LINES,
)
from zcg.core.epistemics import (
    resolve_effective_human_stack,
    resolve_effective_interaction_language,
)
from zcg.core.manifests import iter_layer_template_dirs, load_node_manifest
from zcg.governance.horizon import diff_project_against_layers, inspect_layer_horizon
from zcg.governance.ledger import inspect_git_governance_state, summarize_work_orchestration_ledger
from zcg.topology.identity import resolve_node_entity_identity
from zcg.topology.network import discover_network_topology

PRIORITY_TRACKER_CANDIDATES: tuple[str, ...] = (
    "WORKTASK.md",
    "WORKROAD.md",
    "ROADMAP.md",
    "BACKLOG.md",
    "README.md",
)


def inspect_workspace_status(
    repo_dir: Path, target_dir: Path, *, parent_dir: Path | None = None
) -> dict[str, Any]:
    """Return a single-call consolidated status digest for /sopen and day-to-day node ops."""
    ws, m_path = target_dir.resolve(), target_dir.resolve() / NODE_MANIFEST_REL_PATH
    is_layer = m_path.is_file()
    m = load_node_manifest(ws) if is_layer else {}
    role, lid = str(m.get("layer_role", "project")), str(m.get("layer_id", ws.name))
    prec = int(m.get("precedence", ROLE_DEFAULT_PRECEDENCE["project"]))
    tpls = [str(x) for x in m.get("default_stack_templates", [])]
    rules = [p.name for p in sorted((ws / ".agents/rules").glob("*.md"))]
    s_roots = (ws, *((parent_dir,) if parent_dir else ()), repo_dir, REPO_DIR)
    rmap = {
        rf.name: tn
        for r in s_roots
        for tn, td in iter_layer_template_dirs(r)
        for rf in (td / "rules").glob("*.md")
    }
    seeds = [*tpls, *(rmap[rn] for rn in rules if rn in rmap)]
    lin = {n for n, _ in resolve_template_lineage_chain(seeds, s_roots)} | set(seeds)
    has_acad, has_tech = "academic-base" in lin, "software-engineering" in lin
    has_sci = "science-base" in lin or has_tech
    has_biz = (
        "business-base" in lin
        or role in ("corporate", "domain-policy")
        or (ws / "corporate").is_dir()
    )
    mode = "hybrid" if (has_tech and has_biz) else ("business" if has_biz else "technical")
    s_file = ws / ".agents/SESSION.md"
    s_txt = s_file.read_text(encoding="utf-8") if s_file.is_file() else ""
    uuid_m = re.search(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", s_txt)
    active_trk = next((t for t in PRIORITY_TRACKER_CANDIDATES if (ws / t).is_file()), None)
    trk_txt = (ws / active_trk).read_text(encoding="utf-8") if active_trk else ""
    git_bin, is_git = shutil.which("git") or "/usr/bin/git", (ws / ".git").exists()

    def _git_lines(*args: str) -> list[str]:
        if not is_git:
            return []
        proc = subprocess.run(  # noqa: S603
            [git_bin, *args], cwd=ws, check=False, capture_output=True, text=True
        )
        return proc.stdout.splitlines()

    g_stat = _git_lines("status", "--short", "--branch")
    g_log = _git_lines("log", "--oneline", "-5")
    mk_t = list(LAYER_ROLE_MAKEFILE_TARGETS.get(role, LAYER_ROLE_MAKEFILE_TARGETS["project"]))
    ent_id = resolve_node_entity_identity(ws, m, parent_dir=parent_dir)
    net_topo = discover_network_topology(ws, m, parent_dir=parent_dir)
    work_orch = summarize_work_orchestration_ledger(ws, parent_dir=parent_dir)
    hs = resolve_effective_human_stack(ws, m)
    cmd_tiers = {k: [t for t in v if t in mk_t] for k, v in COMMAND_CONSCIOUSNESS_TIERS.items()}
    base_sk = (
        *BASE_SKILL_TAXONOMY["universal-base"],
        *BASE_SKILL_TAXONOMY["academic-base"],
        *BASE_SKILL_TAXONOMY["business-base"],
        *BASE_SKILL_TAXONOMY["science-base"],
    )
    ws_sk = [
        p.parent.name
        for p in sorted((ws / ".agents/skills").glob("*/SKILL.md"))
        if p.parent.name not in base_sk
    ]
    cmd_tax = {
        "skill_rings": {
            "universal-base": list(BASE_SKILL_TAXONOMY["universal-base"]),
            "academic-base": list(BASE_SKILL_TAXONOMY["academic-base"]) if has_acad else [],
            "business-base": list(BASE_SKILL_TAXONOMY["business-base"]) if has_biz else [],
            "science-base": list(BASE_SKILL_TAXONOMY["science-base"]) if has_sci else [],
            "workspace_layer_skills": ws_sk,
        },
        "makefile_domains": {
            k: [t for t in v if t in mk_t] for k, v in MAKEFILE_DOMAIN_TAXONOMY.items()
        },
    }
    l_pol = resolve_effective_interaction_language(ws, m, parent_dir=parent_dir)
    rt_orch = summarize_runtime_orchestration(ws, m)
    fp = (rt_orch["static_runtime"]["plugins"] or [{}])[0]
    itp = fp.get("intranet_topology") or {}
    cockpit = (
        {
            "plugin_id": fp.get("plugin_id"),
            "status": fp.get("status"),
            "daemon_active": fp.get("daemon_active", False),
            "daemon_pid": fp.get("daemon_pid"),
            "localhost_url": itp.get("localhost_url"),
            "environment_urls": itp.get("local_environment_urls", {}),
            "active_subdomain_url": itp.get("active_subdomain_url"),
        }
        if fp
        else None
    )
    a_root = ws if is_layer else (parent_dir or repo_dir)
    return {
        "workspace_dir": str(ws),
        "layer_id": lid,
        "layer_role": role,
        "active_cockpit": cockpit,
        "entity_identity": ent_id,
        "network_topology": net_topo["network_topology"],
        "node_connection_summary": net_topo["node_connection_summary"],
        "sync_topology": net_topo["sync_topology"],
        "work_orchestration": work_orch,
        "runtime_orchestration": rt_orch,
        "visibility_scope": ent_id["visibility_scope"],
        "exposure_boundary": ent_id["exposure_boundary"],
        "can_expose_to_oss": ent_id["can_expose_to_oss"],
        "global_profile": str(m.get("global_profile", "universal-base")),
        "language_policy": l_pol,
        "human_stack": hs["facets"],
        "human_stack_scope": hs["scope"],
        "operating_state": str(ent_id["operating_state"]),
        "mcp_operating_mode": str(ent_id["mcp_operating_mode"]),
        "precedence": prec,
        "workspace_mode": mode,
        "is_oss_dev_workspace": str(ent_id["operating_state"]) == "oss-dev",
        "command_tiers": cmd_tiers,
        "command_taxonomy": cmd_tax,
        "active_templates": tpls,
        "active_rules": rules,
        "available_makefile_targets": mk_t,
        "git_governance": inspect_git_governance_state(ws),
        "has_project_start_skill": (ws / ".agents/skills/start/SKILL.md").is_file(),
        "setup_state": resolve_workspace_setup_state(ws, m),
        "session_state": {
            "exists": s_file.is_file(),
            "last_conversation_id": uuid_m.group(0) if uuid_m else None,
            "excerpt": "\n".join(s_txt.splitlines()[:STATUS_EXCERPT_MAX_LINES]),
        },
        "priority_state": {
            "active_tracker": active_trk,
            "excerpt": "\n".join(trk_txt.splitlines()[:STATUS_EXCERPT_MAX_LINES]),
        },
        "git_state": {"is_git_repo": is_git, "status_short": g_stat, "recent_commits": g_log},
        "horizon": inspect_layer_horizon(repo_dir, ws, parent_dir=parent_dir) if is_layer else None,
        "agent_diff": diff_project_against_layers(a_root, ws),
    }
