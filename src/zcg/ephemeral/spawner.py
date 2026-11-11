"""Scoped Department Bot fork spawning and cross-project rule bridging.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from zcg.capsules.constants import (
    DEFAULT_EPHEMERAL_TTL_SECONDS,
    EPOCH_DECIMAL_PLACES,
    FORK_ID_HASH_HEX_LEN,
    MAX_ACTIVE_EPHEMERAL_FORKS,
    MAX_EPHEMERAL_TTL_SECONDS,
    MIN_EPHEMERAL_TTL_SECONDS,
    VALID_ARCHITECTURAL_PLANES,
    VALID_EPHEMERAL_ACCESS_MODES,
    VALID_EPHEMERAL_SCOPES,
    VALID_RESOLUTIONS,
)
from zcg.core.constants import (
    CAPSULE_HMAC_HEX_LEN,
    KEBAB_ID_RE,
    NODE_MANIFEST_CONTRACT_REV,
    NODE_MANIFEST_REL_PATH,
    ROLE_DEFAULT_PRECEDENCE,
    VALID_AGENT_TIERS,
    VALID_DYNAMIC_RESOLUTION_POLICIES,
    VALID_ROSTER_ROLES,
    VALID_RUNTIME_PERSISTENCE_MODES,
)
from zcg.core.manifests import resolve_template_dir
from zcg.ephemeral.lifecycle import (
    copy_zero_copy,
    default_ephemeral_root,
    reap_expired_ephemeral_forks,
)


def _prepare_project_bridge(project_dir: Path) -> tuple[list[str], str, dict[str, Any]]:
    proj = project_dir.resolve()
    if not proj.is_dir():
        raise FileNotFoundError(f"mount_project_rules_from directory does not exist: {proj}")
    rules_dir, bridged_files = proj / ".agents/rules", list[str]()
    sections = [f"# Ephemeral Project Bridge ({proj.name})\n"]
    for rf in sorted(rules_dir.glob("*.md")) if rules_dir.is_dir() else ():
        if not rf.resolve().is_relative_to(proj):
            raise ValueError(
                f"Outbound symlink escape denied in mount_project_rules_from: {rf.name}"
            )
        sections.append(f"## Rule: {rf.name}\n\n{rf.read_text(encoding='utf-8').strip()}\n")
        bridged_files.append(f".agents/rules/{rf.name}")
    w, lid = ["*"], f"bridge-{proj.name.lower().replace('_', '-')}"
    binding: dict[str, Any] = {
        "binding_id": "ephemeral-project-bridge-rules",
        "mode": "authoritative",
        "description": f"Bridged workspace rules from {proj.name}",
        "default_resolution": "L2",
        "target_globs": w,
        "architectural_planes": w,
        "scopes": w,
        "traits": w,
        "invariants": [f"Enforce bridged workspace contracts from {proj.name}"],
        "rule_files": ["antigravity/.gemini/config/AGENTS.md"],
        "canonical_templates": [],
    }
    bridge_manifest: dict[str, Any] = {
        "schema_version": NODE_MANIFEST_CONTRACT_REV,
        "layer_id": lid,
        "layer_role": "squad",
        "precedence": ROLE_DEFAULT_PRECEDENCE["bridge"],
        "default_stack_templates": [],
        "description": f"Ephemeral cross-project rule bridge from {proj.name}",
        "baseline_guardrails": [f"Cross-project bridge active from {proj.name}"],
        "surface_bindings": [binding],
        "environments": {},
        "federated_mcps": [],
    }
    return bridged_files, "\n".join(sections), bridge_manifest


def _validate_spawn_args(
    repo_dir: Path,
    base_manifest: dict[str, Any],
    role_clean: str,
    model_tier: str,
    access_mode: str,
    eff_scope: str,
    clean_actor: str,
    res_pol: str,
    resolution: str,
    ttl_seconds: int,
    planes: list[str],
    mount_templates: list[str] | None,
    mount_layers: list[str] | None,
) -> None:
    if not KEBAB_ID_RE.match(role_clean):
        raise ValueError(f"Invalid bot_role {role_clean!r}: must be kebab-case")
    if model_tier not in VALID_AGENT_TIERS:
        raise ValueError(f"Invalid model_tier {model_tier!r}: must be one of {VALID_AGENT_TIERS}")
    if access_mode not in VALID_EPHEMERAL_ACCESS_MODES:
        raise ValueError(f"Invalid access_mode {access_mode!r}")
    if eff_scope not in VALID_EPHEMERAL_SCOPES:
        raise ValueError(f"Invalid ephemeral_scope {eff_scope!r}")
    if clean_actor not in VALID_ROSTER_ROLES:
        raise ValueError(f"Invalid actor_role {clean_actor!r}")
    if res_pol not in VALID_DYNAMIC_RESOLUTION_POLICIES:
        raise ValueError(f"Invalid resolution_policy {res_pol!r}")
    if eff_scope == "inter-layer" and access_mode != "strictly-read-only":
        raise ValueError("Inter-layer ephemeral forks must use access_mode='strictly-read-only'")
    if clean_actor == "validator" and access_mode == "read-write-scoped":
        raise ValueError("Validator actor_role cannot use access_mode='read-write-scoped'")
    is_ro = (
        base_manifest.get("layer_role") == "workstation"
        and (repo_dir / ".workstation-state.json").is_file()
    )
    if is_ro and access_mode != "strictly-read-only":
        raise ValueError("Read-only workstation only permits access_mode='strictly-read-only'")
    if resolution not in VALID_RESOLUTIONS:
        raise ValueError(f"Invalid resolution {resolution!r}")
    if not (MIN_EPHEMERAL_TTL_SECONDS <= ttl_seconds <= MAX_EPHEMERAL_TTL_SECONDS):
        raise ValueError(f"Invalid ttl_seconds {ttl_seconds}")
    for p in planes:
        if p != "*" and p not in VALID_ARCHITECTURAL_PLANES:
            raise ValueError(f"Invalid architectural_plane {p!r}")
    for kind, items in (("mount_template", mount_templates), ("mount_layer", mount_layers)):
        for item in items or []:
            if not KEBAB_ID_RE.match(item):
                raise ValueError(f"Invalid {kind} {item!r}: must be kebab-case")


def spawn_ephemeral_fork(
    repo_dir: Path,
    base_manifest: dict[str, Any],
    *,
    bot_role: str,
    target_globs: list[str] | None = None,
    architectural_planes: list[str] | None = None,
    mount_templates: list[str] | None = None,
    mount_layers: list[str] | None = None,
    mount_project_rules_from: Path | None = None,
    model_tier: str = "flash",
    access_mode: str = "strictly-read-only",
    ephemeral_scope: str | None = None,
    actor_role: str = "member",
    resolution: str = "L2",
    resolution_policy: str = "ttl-expired",
    ttl_seconds: int = DEFAULT_EPHEMERAL_TTL_SECONDS,
    ephemeral_root: Path | None = None,
    now_epoch: float | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Materialize a zero-copy, TTL-bounded ephemeral fork for a Department Bot."""
    role_clean, res_pol = bot_role.strip(), resolution_policy.strip().lower() or "ttl-expired"
    planes, globs = list(architectural_planes or ["*"]), list(target_globs or ["*"])
    eff_scope = (ephemeral_scope or "intra-layer").strip().lower()
    clean_actor = actor_role.strip().lower() or "member"
    _validate_spawn_args(
        repo_dir,
        base_manifest,
        role_clean,
        model_tier,
        access_mode,
        eff_scope,
        clean_actor,
        res_pol,
        resolution,
        ttl_seconds,
        planes,
        mount_templates,
        mount_layers,
    )
    reaped = reap_expired_ephemeral_forks(repo_dir, ephemeral_root, now_epoch=now_epoch)
    root = default_ephemeral_root(repo_dir, ephemeral_root)
    active_dirs = [d for d in root.iterdir() if d.is_dir()] if root.is_dir() else []
    if len(active_dirs) >= MAX_ACTIVE_EPHEMERAL_FORKS:
        raise ValueError(
            f"EPHEMERAL_FORK_LIMIT_REACHED: active forks ({len(active_dirs)}) reached cap."
        )
    created_at = round(now_epoch if now_epoch is not None else time.time(), EPOCH_DECIMAL_PLACES)
    expires_at = round(created_at + ttl_seconds, EPOCH_DECIMAL_PLACES)
    seed = f"{role_clean}:{created_at}:{target_globs}:{mount_templates}:{mount_project_rules_from}"
    f_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:FORK_ID_HASH_HEX_LEN]
    fork_id = f"eph-{role_clean}-{f_hash}"
    session_secret = hashlib.sha256(f"rcap1-ephemeral:{fork_id}:{created_at}".encode()).hexdigest()[
        :CAPSULE_HMAC_HEX_LEN
    ]
    eff_tpls = (
        list(mount_templates)
        if mount_templates is not None
        else list(base_manifest.get("default_stack_templates", []))
    )
    tpl_dirs = [d for t in eff_tpls if (d := resolve_template_dir(repo_dir, t))]
    tpl_rules = [
        str(rf.relative_to(repo_dir)).replace("\\", "/")
        for td in tpl_dirs
        for rf in sorted((td / "rules").glob("*.md"))
    ]
    tpl_assets = [
        str(af.relative_to(repo_dir)).replace("\\", "/")
        for td in tpl_dirs
        for af in sorted((td / "assets").glob("*.md"))
    ]
    p_layers_dir = repo_dir / "layers"
    sel_layers = [
        c.name
        for c in (sorted(p_layers_dir.iterdir()) if p_layers_dir.is_dir() else ())
        if c.is_dir()
        and not c.name.startswith(".")
        and (mount_layers is None or c.name in mount_layers)
    ]
    parent_id = str(base_manifest.get("layer_id", "zero-cloud-gravity-workstation"))
    b_files, b_md, b_man = (
        _prepare_project_bridge(mount_project_rules_from)
        if mount_project_rules_from
        else ([], "", {})
    )
    b_extra: dict[str, Any] = {}
    if mount_project_rules_from is not None:
        sel_layers.append("ephemeral-project-bridge")
        b_extra = {
            "bridge_layer_id": str(b_man.get("layer_id", "")),
            "bridge_agents_md": b_md,
            "bridge_manifest": b_man,
            "bridged_project_files": b_files,
        }
    eph_meta: dict[str, Any] = {
        "fork_id": fork_id,
        "bot_role": role_clean,
        "parent_layer_id": parent_id,
        "persistence_mode": VALID_RUNTIME_PERSISTENCE_MODES[1],
        "resolution_policy": res_pol,
        "model_tier": model_tier,
        "access_mode": access_mode,
        "ephemeral_scope": eff_scope,
        "actor_role": clean_actor,
        "resolution": resolution,
        "target_globs": globs,
        "architectural_planes": planes,
        "mount_layers_filter": mount_layers,
        "created_at_epoch": created_at,
        "expires_at_epoch": expires_at,
        "ttl_seconds": ttl_seconds,
        "session_resonance_key": session_secret,
        "handback_contract": "4-channel-digest+rcap1",
        **b_extra,
    }
    binding: dict[str, Any] = {
        "binding_id": f"{role_clean}-ephemeral-authority",
        "mode": "authoritative",
        "description": f"Authoritative scoped binding for {role_clean}",
        "target_globs": globs,
        "architectural_planes": planes,
        "scopes": ["*"],
        "traits": ["*"],
        "default_resolution": resolution,
        "rule_files": ["antigravity/.gemini/config/AGENTS.md", *tpl_rules],
        "invariants": [
            f"Operate strictly within {access_mode} mode ({eff_scope}) and {globs} boundary",
            "Return output using the 4-Channel Executive Digest contract (AGENTS.md §12)",
        ],
        "canonical_templates": tpl_assets or tpl_rules,
    }
    ephemeral_manifest: dict[str, Any] = {
        "schema_version": str(base_manifest.get("schema_version", NODE_MANIFEST_CONTRACT_REV)),
        "layer_id": fork_id,
        "layer_role": "ephemeral-bot",
        "precedence": ROLE_DEFAULT_PRECEDENCE["ephemeral-bot"],
        "upstream_layer": {
            "layer_id": parent_id,
            "repository": "local-ephemeral-overlay",
            "branch": "ephemeral",
        },
        "description": f"Ephemeral Department Bot ({role_clean}) scoped to {globs}",
        "mounted_layers_dir": "layers",
        "mounted_layers": sel_layers,
        "default_stack_templates": eff_tpls,
        "surface_bindings": [binding],
        "baseline_guardrails": [
            f"Bot Role: {role_clean} (tier={model_tier}, access={access_mode}, scope={eff_scope})",
            "AGENTS.md §12 (Return compact 4-Channel Executive Digest + rcap1 capsule)",
            *list(base_manifest.get("baseline_guardrails", [])),
        ],
        "environments": dict(base_manifest.get("environments", {})),
        "federated_mcps": [],
        "ephemeral_metadata": eph_meta,
    }
    fork_dir = root / fork_id
    if not dry_run:
        for subdir in ("system", "layers", "logs"):
            (fork_dir / subdir).mkdir(parents=True, exist_ok=True)
        for item in (
            "antigravity",
            "docs",
            "templates",
            "corporate",
            "surfaces",
            "README.md",
            "VERSION",
        ):
            if (repo_dir / item).exists() and not (fork_dir / item).exists():
                copy_zero_copy(repo_dir / item, fork_dir / item)
        for lname in sel_layers:
            if lname != "ephemeral-project-bridge":
                copy_zero_copy(p_layers_dir / lname, fork_dir / "layers" / lname)
        if b_man:
            b_layer = fork_dir / "layers/ephemeral-project-bridge"
            for b_sub in ("antigravity/.gemini/config", "system"):
                (b_layer / b_sub).mkdir(parents=True, exist_ok=True)
            (b_layer / "antigravity/.gemini/config/AGENTS.md").write_text(b_md, encoding="utf-8")
            (b_layer / NODE_MANIFEST_REL_PATH).write_text(
                json.dumps(b_man, indent=2) + "\n", encoding="utf-8"
            )
        (fork_dir / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(ephemeral_manifest, indent=2) + "\n", encoding="utf-8"
        )
    return {
        **eph_meta,
        "dry_run": dry_run,
        "fork_dir": str(fork_dir),
        "bridged_project_files": b_files,
        "reaped_expired": reaped,
        "manifest": ephemeral_manifest,
    }
