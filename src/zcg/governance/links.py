"""Declarative node connection registry (link/unlink) and branch spin-out engine.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zcg.core.constants import (
    DEFAULT_PLUGIN_BASE_PORT,
    GIT_CMD_TIMEOUT_SECONDS,
    KEBAB_ID_RE,
    NODE_MANIFEST_REL_PATH,
    ROLE_DEFAULT_PRECEDENCE,
    SAFE_GIT_REF_RE,
    VALID_KNOWLEDGE_PREFIXES,
    VALID_NODE_LINK_RELATIONS,
)
from zcg.core.manifests import (
    canonicalize_local_node_url,
    ensure_contained_path,
    load_node_manifest,
)
from zcg.governance.bootstrap import bootstrap_node_workspace

_SPINOUT_SKIP_EXACT: frozenset[str] = frozenset(
    {
        NODE_MANIFEST_REL_PATH,
        "Makefile",
        "WORKROAD.md",
        "WORKTASK.md",
        "WORKVALI.md",
        "BACKLOG.md",
    }
)
_SPINOUT_SKIP_PREFIXES: tuple[str, ...] = (".agents/", "surfaces/", "templates/")


def _is_remote_ref(ref: str) -> bool:
    return "://" in ref or ref.startswith("git@")


def resolve_linked_node_dir(workspace_dir: Path, target_id: str) -> Path | None:
    """Resolve a locally reachable linked_nodes target directory containing zcg-node.json."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    for entry in (x for x in manifest.get("linked_nodes", []) if isinstance(x, dict)):
        if str(entry.get("node_id") or "").strip() != target_id:
            continue
        raw_ref = str(entry.get("target_ref") or "").strip()
        if raw_ref and not _is_remote_ref(raw_ref):
            cand = Path(raw_ref).expanduser()
            resolved = cand.resolve() if cand.is_absolute() else (ws / cand).resolve()
            if (resolved / NODE_MANIFEST_REL_PATH).is_file():
                return resolved
        sib = (ws.parent / target_id).resolve()
        if (sib / NODE_MANIFEST_REL_PATH).is_file():
            return sib
    return None


def link_node(
    workspace_dir: Path,
    *,
    target_id: str,
    relation: str = "lateral-peer",
    target_ref: str = "",
    cockpit_url: str = "",
    shared_packs: list[str] | None = None,
    description: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upsert a zero-copy declarative node connection in system/zcg-node.json -> linked_nodes."""
    clean_id = target_id.strip()
    if not KEBAB_ID_RE.match(clean_id):
        raise ValueError(f"Invalid target_id {target_id!r}: must match kebab-case")
    clean_rel = relation.strip() or "lateral-peer"
    if clean_rel not in VALID_NODE_LINK_RELATIONS:
        raise ValueError(
            f"Invalid relation {relation!r}: must be one of {VALID_NODE_LINK_RELATIONS}"
        )
    ws = workspace_dir.resolve()
    manifest_path = ws / NODE_MANIFEST_REL_PATH
    if not manifest_path.is_file():
        raise ValueError(f"Missing node manifest: {manifest_path}")
    manifest = load_node_manifest(ws)
    own_id = str(manifest.get("layer_id") or ws.name).strip()
    if clean_id == own_id:
        raise ValueError(f"Cannot link node {own_id!r} to itself")

    clean_packs = [p.strip() for p in (shared_packs or []) if p.strip()]
    for pack in clean_packs:
        if not KEBAB_ID_RE.match(pack):
            raise ValueError(f"Invalid shared_pack {pack!r}: must match kebab-case")

    raw_ref = target_ref.strip()
    local_cand: Path | None = None
    if raw_ref and not _is_remote_ref(raw_ref):
        cand_p = Path(raw_ref).expanduser()
        local_cand = cand_p.resolve() if cand_p.is_absolute() else (ws / cand_p).resolve()
    elif not raw_ref and (ws.parent / clean_id / NODE_MANIFEST_REL_PATH).is_file():
        local_cand = (ws.parent / clean_id).resolve()

    if local_cand is not None and (local_cand / NODE_MANIFEST_REL_PATH).is_file():
        tm = load_node_manifest(local_cand)
        t_role = str(tm.get("layer_role") or "project")
        t_prec = int(tm.get("precedence", ROLE_DEFAULT_PRECEDENCE.get(t_role, 80)))
        t_port = int(tm.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + t_prec))
        t_root = (
            str(tm.get("governing_root_id") or clean_id).removeprefix("corp-").removesuffix("-root")
        )
        t_dg = tm.get("domain_governance")
        t_zone = str(t_dg.get("local_dev_zone") if isinstance(t_dg, dict) else "") or t_root
        eff_ref = raw_ref or str(local_cand)
    else:
        t_role = "knowledge" if clean_id.startswith(VALID_KNOWLEDGE_PREFIXES) else "project"
        t_prec = ROLE_DEFAULT_PRECEDENCE.get(t_role, 80)
        t_port = DEFAULT_PLUGIN_BASE_PORT + t_prec
        t_zone = clean_id
        eff_ref = raw_ref

    def_url = (
        ""
        if clean_rel == "knowledge-feed"
        else canonicalize_local_node_url(
            "",
            node_id=clean_id,
            layer_role=t_role,
            active_env="pro" if t_role == "knowledge" else "dev",
            local_dev_zone=t_zone,
            fallback_port=t_port,
        )
    )
    eff_url = cockpit_url.strip() or def_url
    entry: dict[str, Any] = {
        "node_id": clean_id,
        "relation": clean_rel,
        "layer_role": t_role,
        "precedence": t_prec,
        "target_ref": eff_ref,
        "cockpit_url": eff_url,
        "shared_packs": clean_packs,
    }
    if description.strip():
        entry["description"] = description.strip()

    existing = [
        x
        for x in manifest.get("linked_nodes", [])
        if isinstance(x, dict) and str(x.get("node_id") or "").strip() != clean_id
    ]
    existing.append(entry)
    existing.sort(key=lambda it: (str(it.get("relation", "")), str(it.get("node_id", ""))))
    manifest["linked_nodes"] = existing
    if not dry_run:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return {"linked_node": entry, "total_linked_nodes": len(existing), "dry_run": dry_run}


def unlink_node(workspace_dir: Path, *, target_id: str, dry_run: bool = False) -> dict[str, Any]:
    """Remove a declarative node connection from system/zcg-node.json -> linked_nodes."""
    clean_id = target_id.strip()
    if not KEBAB_ID_RE.match(clean_id):
        raise ValueError(f"Invalid target_id {target_id!r}: must match kebab-case")
    ws = workspace_dir.resolve()
    manifest_path = ws / NODE_MANIFEST_REL_PATH
    if not manifest_path.is_file():
        raise ValueError(f"Missing node manifest: {manifest_path}")
    manifest = load_node_manifest(ws)
    before = [x for x in manifest.get("linked_nodes", []) if isinstance(x, dict)]
    kept = [x for x in before if str(x.get("node_id") or "").strip() != clean_id]
    removed = len(kept) < len(before)
    if removed and not dry_run:
        manifest["linked_nodes"] = kept
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return {
        "unlinked_node_id": clean_id,
        "removed": removed,
        "total_linked_nodes": len(kept),
        "dry_run": dry_run,
    }


def spinout_branch_to_project(
    repo_dir: Path,
    source_workspace_dir: Path,
    target_dir: Path,
    *,
    project_id: str,
    from_branch: str,
    layer_role: str = "project",
    precedence: int = 80,
    description: str | None = None,
    templates: list[str] | None = None,
    shared_packs: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Graduate an incubated context branch into a standalone governed ZCG repository."""
    if not KEBAB_ID_RE.match(project_id):
        raise ValueError(f"Invalid project_id {project_id!r}: must match kebab-case")
    clean_branch = from_branch.strip()
    if not SAFE_GIT_REF_RE.match(clean_branch) or clean_branch in ("master", "main"):
        raise ValueError(
            f"spinout-project requires a non-default context branch, got {from_branch!r}"
        )
    src_ws, dst_ws = source_workspace_dir.resolve(), target_dir.resolve()
    if src_ws == dst_ws:
        raise ValueError("target_dir must be distinct from source_workspace_dir")
    if not (src_ws / NODE_MANIFEST_REL_PATH).is_file():
        raise ValueError(f"Missing source node manifest: {src_ws / NODE_MANIFEST_REL_PATH}")

    src_m = load_node_manifest(src_ws)
    src_id = str(src_m.get("layer_id") or src_ws.name)
    gov_root = str(src_m.get("governing_root_id") or src_id)
    ent_kind = str(src_m.get("entity_kind") or "individual")
    lang = str(src_m.get("interaction_language") or "en")

    extracted_files: list[str] = []
    if (src_ws / ".git").exists():
        git_bin = shutil.which("git") or "/usr/bin/git"
        chk = subprocess.run(  # noqa: S603
            [git_bin, "-C", str(src_ws), "rev-parse", "--verify", f"refs/heads/{clean_branch}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_CMD_TIMEOUT_SECONDS,
        )
        if chk.returncode != 0:
            raise ValueError(f"Branch {clean_branch!r} not found in {src_ws}")
        ls_res = subprocess.run(  # noqa: S603
            [git_bin, "-C", str(src_ws), "ls-tree", "-r", "--name-only", clean_branch],
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_CMD_TIMEOUT_SECONDS,
        )
        for rel in sorted(ln.strip() for ln in ls_res.stdout.splitlines() if ln.strip()):
            if rel in _SPINOUT_SKIP_EXACT or rel.startswith(_SPINOUT_SKIP_PREFIXES):
                continue
            extracted_files.append(rel)
            if not dry_run:
                dst_file = ensure_contained_path(Path(rel), dst_ws)
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                blob = subprocess.run(  # noqa: S603
                    [git_bin, "-C", str(src_ws), "show", f"{clean_branch}:{rel}"],
                    check=True,
                    capture_output=True,
                    timeout=GIT_CMD_TIMEOUT_SECONDS,
                )
                dst_file.write_bytes(blob.stdout)

    eff_tpls = templates or ["business-base", "software-engineering", "node-work-cockpit"]
    eff_desc = description or f"Standalone node spun out from {src_id}:{clean_branch}"
    boot_res = bootstrap_node_workspace(
        repo_dir,
        dst_ws,
        layer_id=project_id,
        layer_role=layer_role,
        precedence=precedence,
        description=eff_desc,
        parent_dir=src_ws,
        templates=eff_tpls,
        entity_kind=ent_kind,
        governing_root_id=gov_root,
        interaction_language=lang,
        dry_run=dry_run,
    )
    fwd_link = link_node(
        src_ws,
        target_id=project_id,
        relation="spinout-project",
        target_ref=str(dst_ws),
        shared_packs=shared_packs,
        description=f"Graduated from {clean_branch}",
        dry_run=dry_run,
    )
    rev_link = (
        {
            "linked_node": {
                "node_id": src_id,
                "relation": "spinout-project",
                "target_ref": str(src_ws),
                "shared_packs": shared_packs or [],
            },
            "dry_run": True,
        }
        if dry_run
        else link_node(
            dst_ws,
            target_id=src_id,
            relation="spinout-project",
            target_ref=str(src_ws),
            shared_packs=shared_packs,
            description=f"Origin hub ({clean_branch})",
            dry_run=False,
        )
    )
    return {
        "project_id": project_id,
        "from_branch": clean_branch,
        "source_layer_id": src_id,
        "target_dir": str(dst_ws),
        "extracted_files": extracted_files,
        "bootstrap": boot_res,
        "bidirectional_links": {"from_source": fwd_link, "from_project": rev_link},
        "dry_run": dry_run,
    }
