"""Single-call consolidated status & cockpit telemetry digest for /sopen and node ops.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.ops.posture_guard import evaluate_local_security_posture
from zcg.cockpit.routing.network_auth import resolve_default_node_environment
from zcg.core.blueprints import resolve_template_lineage_chain, resolve_workspace_setup_state
from zcg.core.constants import (
    BASE_SKILL_TAXONOMY,
    COMMAND_CONSCIOUSNESS_TIERS,
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
from zcg.core.surface_composer import compose_node_makefile_targets
from zcg.governance.runtime.skill_auditor import audit_skills_sovereign_profile
from zcg.governance.work.horizon import diff_project_against_layers, inspect_layer_horizon
from zcg.governance.work.ledger import (
    inspect_git_governance_state,
    summarize_work_orchestration_ledger,
)
from zcg.governance.workspace.antigravity_sync import summarize_runtime_orchestration
from zcg.topology.identity import resolve_node_entity_identity
from zcg.topology.network import discover_network_topology
from zcg.topology.posture import resolve_governance_posture, resolve_surface_origin

PRIORITY_TRACKER_CANDIDATES: tuple[str, ...] = (
    "WORKTASK.md",
    "WORKROAD.md",
    "ROADMAP.md",
    "BACKLOG.md",
    "README.md",
)
UUID_CANONICAL_LEN: Final[int] = 36
UUID_STRIP_CHARS: Final[str] = "`'\"()[]{}<>.,;:/"
NODE_HEALTH_CONTRACT_REV: Final[str] = "zcg-node-health-v1"
VALID_NODE_HEALTH_STATES: Final[tuple[str, ...]] = (
    "OPTIMAL",
    "ATTENTION",
    "CRITICAL",
    "UNCONFIGURED",
)


def _extract_first_uuid(text: str) -> str | None:
    for raw_tok in text.split():
        cand = raw_tok.strip(UUID_STRIP_CHARS)
        if len(cand) == UUID_CANONICAL_LEN:
            with contextlib.suppress(ValueError):
                return str(uuid.UUID(cand)).lower()
    return None


def _parse_git_branch_status(
    git_status_lines: Sequence[str], *, has_origin_remote: bool = False
) -> dict[str, Any]:
    if not git_status_lines:
        return {"has_remote": has_origin_remote, "ahead": 0, "behind": 0, "dirty": 0}
    head = git_status_lines[0]
    is_hdr = head.startswith("## ")
    dirty = len(git_status_lines) - (1 if is_hdr else 0)
    has_rem = has_origin_remote or (is_hdr and "..." in head)
    ahead, behind = 0, 0
    if is_hdr and "[" in head and head.endswith("]"):
        for part in head.rpartition("[")[2][:-1].split(","):
            tok = part.strip()
            if tok.startswith("ahead ") and tok.removeprefix("ahead ").isdigit():
                ahead = int(tok.removeprefix("ahead "))
            elif tok.startswith("behind ") and tok.removeprefix("behind ").isdigit():
                behind = int(tok.removeprefix("behind "))
    return {"has_remote": has_rem, "ahead": ahead, "behind": behind, "dirty": dirty}


def evaluate_node_health(
    workspace_dir: Path,
    *,
    parent_dir: Path | None = None,
    setup_state_str: str | None = None,
    is_git_repo: bool | None = None,
    git_status_lines: Sequence[str] | None = None,
    has_origin_remote: bool = False,
    security_posture: Mapping[str, Any] | None = None,
    skill_trust: Mapping[str, Any] | None = None,
    git_governance: Mapping[str, Any] | None = None,
    horizon: Mapping[str, Any] | None = None,
    agent_diff: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute a 4-state epistemic node health digest (OPTIMAL|ATTENTION|CRITICAL|UNCONFIGURED)."""
    ws = workspace_dir.resolve()
    is_layer = (ws / NODE_MANIFEST_REL_PATH).is_file()
    m = load_node_manifest(ws) if is_layer else {}
    eff_setup = setup_state_str or str(resolve_workspace_setup_state(ws, m)["state"])
    eff_git = (ws / ".git").exists() if is_git_repo is None else is_git_repo
    git_bin = shutil.which("git") or "/usr/bin/git"
    if git_status_lines is None and eff_git:
        proc = subprocess.run(  # noqa: S603
            [git_bin, "status", "--short", "--branch"],
            cwd=ws, check=False, capture_output=True, text=True,
        )  # fmt: skip
        eff_gstat: Sequence[str] = proc.stdout.splitlines()
    else:
        eff_gstat = git_status_lines or ()

    sec = (
        dict(security_posture)
        if security_posture is not None
        else evaluate_local_security_posture(ws, parent_dir=parent_dir)
    )
    raw_checks = sec.get("checks")
    sec_checks: Mapping[str, Any] = raw_checks if isinstance(raw_checks, Mapping) else {}
    sec_score = int(sec.get("score", 100))
    if not sec_checks.get("overlay_integrity", True) or not sec_checks.get(
        "skill_supply_chain_trust", True
    ):
        sec_st, sec_note = "CRITICAL", f"Active overlay or skill security violation ({sec_score})"
    elif eff_setup != "configured":
        sec_st, sec_note = "UNCONFIGURED", f"Workspace setup_state is {eff_setup!r}"
    elif sec_score < 70:
        sec_st, sec_note = "CRITICAL", f"Security posture {sec_score}/100 requires remediation"
    elif sec_score < 100:
        sec_st, sec_note = "ATTENTION", f"Security posture {sec_score}/100 (guarded)"
    else:
        sec_st, sec_note = "OPTIMAL", "Security posture 100/100 (HARDENED)"

    sk = dict(skill_trust) if skill_trust is not None else audit_skills_sovereign_profile(ws)
    sk_score = int(sk.get("score", sk.get("trust_score", 100)))
    sk_passed = bool(sk.get("passed", True))
    sk_tiers = sk.get("tiers")
    t1_sec = (
        int(sk_tiers.get("tier1_security_finding_count", 0))
        if isinstance(sk_tiers, Mapping)
        else (0 if sk_passed or sk_score >= 70 else 1)
    )
    sk_cnt = int(sk.get("scanned_skill_count", 0))
    if t1_sec > 0 or sk_score < 70:
        sk_st, sk_note = "CRITICAL", f"Skill security violation ({sk_score}/100)"
    elif sk_cnt == 0:
        sk_st, sk_note = "UNCONFIGURED", "0 active SKILL.md playbooks materialized"
    elif not sk_passed or sk_score < 100:
        sk_st, sk_note = "ATTENTION", f"Skill taxonomy/overlap review ({sk_score}/100)"
    else:
        sk_st, sk_note = "OPTIMAL", f"All {sk_cnt} active skills verified (100/100)"

    gs = _parse_git_branch_status(eff_gstat, has_origin_remote=has_origin_remote)
    if not eff_git:
        sy_st, sy_note = "UNCONFIGURED", "Not a Git repository"
    elif gs["dirty"] > 0 or gs["ahead"] > 0 or gs["behind"] > 0:
        sy_st = "ATTENTION"
        sy_note = f"dirty={gs['dirty']}, ahead={gs['ahead']}, behind={gs['behind']}"
    elif not gs["has_remote"]:
        sy_st, sy_note = "UNCONFIGURED", "Git remote origin not configured (push sync undefined)"
    else:
        sy_st, sy_note = "OPTIMAL", "Working tree clean and synchronized with remote"

    if not is_layer:
        op_st, op_note = "UNCONFIGURED", "Standalone project without system/zcg-node.json"
    else:
        gg = (
            dict(git_governance) if git_governance is not None else inspect_git_governance_state(ws)
        )
        hz = dict(horizon) if horizon is not None else {}
        ad = dict(agent_diff) if agent_diff is not None else {"in_sync": True}
        has_drift = bool(
            gg.get("makefile_outdated")
            or gg.get("manifest_contracts_outdated")
            or hz.get("downward_sync_needed")
            or hz.get("child_sync_needed")
            or not ad.get("in_sync", True)
        )
        op_st = "ATTENTION" if has_drift else "OPTIMAL"
        op_note = "Template/Makefile sync needed" if has_drift else "Manifest & horizon in sync"

    dims = {
        "security_posture": {"state": sec_st, "score": sec_score, "note": sec_note},
        "skill_trust": {"state": sk_st, "score": sk_score, "note": sk_note},
        "sync_safety": {"state": sy_st, **gs, "note": sy_note},
        "operational_drift": {"state": op_st, "note": op_note},
    }
    states = [str(d["state"]) for d in dims.values()]
    unconf = [k for k, d in dims.items() if d["state"] == "UNCONFIGURED"]
    attn = [f"{k}: {d['note']}" for k, d in dims.items() if d["state"] in ("CRITICAL", "ATTENTION")]
    if "CRITICAL" in states:
        overall = "CRITICAL"
    elif eff_setup != "configured" or len(unconf) == len(dims):
        overall = "UNCONFIGURED"
    elif "ATTENTION" in states:
        overall = "ATTENTION"
    else:
        overall = "OPTIMAL"
    return {
        "contract_rev": NODE_HEALTH_CONTRACT_REV,
        "overall_state": overall,
        "valid_states": list(VALID_NODE_HEALTH_STATES),
        "dimensions": dims,
        "unconfigured_dimensions": unconf,
        "attention_items": attn,
    }


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
    conv_uuid = _extract_first_uuid(s_txt)
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
    g_rem = bool(_git_lines("config", "--get", "remote.origin.url"))
    posture_info = resolve_governance_posture(ws, m, parent_dir=parent_dir)
    mk_t = compose_node_makefile_targets(
        role,
        active_templates=seeds,
        allow_external_links=bool(posture_info["allow_external_peer_links"]),
        search_roots=s_roots,
    )
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
            "localhost_url": itp.get("local_subdomain_url") or itp.get("localhost_url"),
            "environment_urls": itp.get("local_subdomain_urls")
            or itp.get("local_environment_urls", {}),
            "active_subdomain_url": itp.get("active_subdomain_url"),
        }
        if fp
        else None
    )
    a_root = ws if is_layer else (parent_dir or repo_dir)
    gg_doc = inspect_git_governance_state(ws)
    setup_doc = resolve_workspace_setup_state(ws, m)
    hz_doc = inspect_layer_horizon(repo_dir, ws, parent_dir=parent_dir) if is_layer else None
    ad_doc = diff_project_against_layers(a_root, ws)
    nh_doc = evaluate_node_health(
        ws,
        parent_dir=parent_dir,
        setup_state_str=str(setup_doc["state"]),
        is_git_repo=is_git,
        git_status_lines=g_stat,
        has_origin_remote=g_rem,
        git_governance=gg_doc,
        horizon=hz_doc,
        agent_diff=ad_doc,
    )
    return {
        "workspace_dir": str(ws),
        "layer_id": lid,
        "layer_role": role,
        "active_cockpit": cockpit,
        "node_health": nh_doc,
        "entity_identity": ent_id,
        "posture": posture_info,
        "surface_origin": resolve_surface_origin(
            m, active_env=str(fp.get("environment") or resolve_default_node_environment(m))
        ),
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
        "git_governance": gg_doc,
        "has_project_start_skill": (ws / ".agents/skills/start/SKILL.md").is_file(),
        "setup_state": setup_doc,
        "session_state": {
            "exists": s_file.is_file(),
            "last_conversation_id": conv_uuid,
            "excerpt": "\n".join(s_txt.splitlines()[:STATUS_EXCERPT_MAX_LINES]),
        },
        "priority_state": {
            "active_tracker": active_trk,
            "excerpt": "\n".join(trk_txt.splitlines()[:STATUS_EXCERPT_MAX_LINES]),
        },
        "git_state": {"is_git_repo": is_git, "status_short": g_stat, "recent_commits": g_log},
        "horizon": hz_doc,
        "agent_diff": ad_doc,
    }
