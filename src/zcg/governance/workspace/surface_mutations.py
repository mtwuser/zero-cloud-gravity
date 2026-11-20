"""Safe transactional context-branch switching, Two-World skill authoring, and scoped Git commits.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import (
    BASE_SKILL_TAXONOMY,
    GIT_CMD_TIMEOUT_SECONDS,
    NODE_MANIFEST_REL_PATH,
    REPO_DIR,
    SKILLS_MANIFEST_REL_PATH,
    VALID_TRACKER_FILES,
)
from zcg.core.domain import is_kebab_id, is_safe_git_ref
from zcg.core.manifests import (
    ensure_contained_path,
    iter_layer_template_dirs,
    load_node_manifest,
    parse_skill_frontmatter,
)
from zcg.governance.runtime.skill_auditor import audit_skills_sovereign_profile
from zcg.governance.workspace.bootstrap import sync_node_workspace

MAX_SKILL_LINES: Final[int] = 464
VALID_COMMIT_PREFIXES: Final[tuple[str, ...]] = (
    "feat(", "fix(", "docs(", "chore(", "refactor(", "test(",
    "feat:", "fix:", "docs:", "chore:", "refactor:", "test:",
)  # fmt: skip
_IGNORED_RUNTIME_PREFIXES: Final[tuple[str, ...]] = (".agents/", ".zcg/", ".agents", ".zcg")


def _require_git_repo(ws: Path) -> str:
    git_bin = shutil.which("git")
    if not (ws / ".git").exists() or git_bin is None:
        raise ValueError("GIT_REPO_REQUIRED: workspace is not an initialized Git repository")
    return git_bin


def _run_git(git_bin: str, ws: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [git_bin, "-C", str(ws), *args],
        capture_output=True,
        text=True,
        timeout=GIT_CMD_TIMEOUT_SECONDS,
        check=False,
    )


def is_workspace_path_dirty(workspace_dir: Path, rel_path: str) -> bool:
    """Return True when a contained workspace file has uncommitted Git changes or is untracked."""
    ws = workspace_dir.resolve()
    norm_p = rel_path.strip().replace("\\", "/").lstrip("/")
    if not norm_p:
        return False
    ensure_contained_path(ws / norm_p, ws)
    if not (ws / ".git").exists() or (git_bin := shutil.which("git")) is None:
        return False
    proc = _run_git(git_bin, ws, "status", "--porcelain", "--", norm_p)
    return bool(proc.returncode == 0 and proc.stdout.strip())


def switch_workspace_context_branch(
    workspace_dir: Path,
    *,
    branch: str,
    allow_create: bool = True,
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Safely switch or create a Git context branch after clean-worktree preflight + skill sync."""
    ws = workspace_dir.resolve()
    clean_b = branch.strip()
    if not clean_b or not is_safe_git_ref(clean_b) or ".." in clean_b:
        raise ValueError(f"INVALID_CONTEXT_BRANCH: unsafe branch reference {branch!r}")
    git_bin = _require_git_repo(ws)
    st_proc = _run_git(git_bin, ws, "status", "--porcelain")
    dirty = [
        path_part
        for ln in st_proc.stdout.splitlines()
        if len(ln) > 3 and not (path_part := ln[3:].strip()).startswith(_IGNORED_RUNTIME_PREFIXES)
    ]
    if dirty:
        raise ValueError(f"WORKTREE_DIRTY: commit or clean {dirty[0]!r} before switching branches")
    refs_proc = _run_git(git_bin, ws, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    local_branches = {b.strip() for b in refs_proc.stdout.splitlines() if b.strip()}
    created = clean_b not in local_branches
    if created and not allow_create:
        raise ValueError(f"BRANCH_NOT_FOUND: branch {clean_b!r} does not exist locally")
    sw_args = ("switch", "-c", clean_b) if created else ("switch", clean_b)
    sw_proc = _run_git(git_bin, ws, *sw_args)
    if sw_proc.returncode != 0:
        raise ValueError(f"GIT_SWITCH_FAILED: {sw_proc.stderr.strip() or clean_b}")
    synced = False
    if (ws / NODE_MANIFEST_REL_PATH).is_file():
        sync_node_workspace(REPO_DIR, ws, parent_dir=parent_dir)
        synced = True
    return {"branch": clean_b, "created": created, "synced": synced}


def _read_skills_manifest_meta(ws: Path) -> tuple[dict[str, str], set[str]]:
    sk_file = ws / SKILLS_MANIFEST_REL_PATH
    if not sk_file.is_file():
        return {}, set()
    raw = json.loads(sk_file.read_text(encoding="utf-8"))
    entries = raw.get("skills") if isinstance(raw, dict) else None
    enabled_raw = raw.get("enabled_skills") if isinstance(raw, dict) else None
    prov = (
        {
            str(e["name"]): str(e.get("source") or "upstream")
            for e in entries
            if isinstance(e, dict) and e.get("name")
        }
        if isinstance(entries, list)
        else {}
    )
    enabled = (
        {
            s
            for raw_s in enabled_raw
            if (s := str(raw_s).strip())
            and (REPO_DIR / ".agents/skills" / s / "SKILL.md").is_file()
        }
        if isinstance(enabled_raw, list)
        else set()
    )
    return prov, enabled


def _resolve_engine_skill_sources() -> dict[str, str]:
    sources: dict[str, str] = {
        sk: "core:universal-baseline" for grp in BASE_SKILL_TAXONOMY.values() for sk in grp
    }
    for tname, tdir in iter_layer_template_dirs(REPO_DIR):
        for sf in sorted((tdir / "skills").glob("*/SKILL.md")):
            sources.setdefault(sf.parent.name, f"stack:{tname}")
    return sources


def inspect_workspace_skills_studio(
    workspace_dir: Path, *, skill_slug: str = "", parent_dir: Path | None = None
) -> dict[str, Any]:
    """Inspect active node-owned, parent-layer, and engine skills with 0..100 trust score."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    layer_id = str(manifest.get("layer_id") or ws.name)
    gov_root = str(manifest.get("governing_root_id") or "upstream")
    prov_map, enabled_eng = _read_skills_manifest_meta(ws)
    eng_map = _resolve_engine_skill_sources()
    owned_root = ws / "templates" / layer_id / "skills"
    proj_root = ws / ".agents/skills"
    slugs = sorted(
        {
            *(p.parent.name for p in owned_root.glob("*/SKILL.md")),
            *(p.parent.name for p in proj_root.glob("*/SKILL.md")),
            *enabled_eng,
        }
    )
    items: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    want_slug = skill_slug.strip()
    for slug in slugs:
        owned_f = owned_root / slug / "SKILL.md"
        proj_f = proj_root / slug / "SKILL.md"
        eff_f, fm_base = (
            (owned_f, ws)
            if owned_f.is_file()
            else (
                (proj_f, ws)
                if proj_f.is_file()
                else (REPO_DIR / ".agents/skills" / slug / "SKILL.md", REPO_DIR)
            )
        )
        raw = eff_f.read_text(encoding="utf-8")
        fm = parse_skill_frontmatter(eff_f, repo_dir=fm_base)
        sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        is_owned = owned_f.is_file()
        if is_owned:
            origin_tier, src = "node", f"layer:{layer_id}"
        elif slug in eng_map:
            origin_tier, src = "engine", prov_map.get(slug) or eng_map[slug]
        else:
            origin_tier, src = "parent", prov_map.get(slug) or f"parent:{gov_root}"
        rel_p = f"templates/{layer_id}/skills/{slug}/SKILL.md"
        entry = {
            "slug": slug,
            "ownership": "node-owned" if is_owned else "inherited",
            "origin_tier": origin_tier,
            "editable": is_owned,
            "source": src,
            "canonical_rel_path": rel_p,
            "sha256": sha,
            "line_count": len(raw.splitlines()),
            "description": str(fm.get("description") or ""),
        }
        items.append(entry)
        if want_slug and slug == want_slug:
            selected = {**entry, "content": raw}
    audit = audit_skills_sovereign_profile(ws, parent_dir=parent_dir)
    return {
        "layer_id": layer_id,
        "trust_score": audit["trust_score"],
        "passed": audit["passed"],
        "finding_count": audit["finding_count"],
        "skills": items,
        "selected_skill": selected,
    }


def delete_node_skill(workspace_dir: Path, *, skill_slug: str) -> dict[str, Any]:
    """Delete a node-owned skill from templates/<layer_id>/skills/ and .agents/skills/."""
    ws = workspace_dir.resolve()
    clean_slug = skill_slug.strip()
    if not is_kebab_id(clean_slug):
        raise ValueError(f"INVALID_SKILL_SLUG: {skill_slug!r} must be lowercase kebab-case")
    layer_id = str(load_node_manifest(ws).get("layer_id") or ws.name)
    if not is_kebab_id(layer_id):
        raise ValueError(f"INVALID_LAYER_ID: {layer_id!r}")
    tpl_root = ws / "templates"
    owned_dir = ensure_contained_path(tpl_root / layer_id / "skills" / clean_slug, tpl_root)
    if not (owned_dir / "SKILL.md").is_file():
        raise ValueError(f"SKILL_NOT_NODE_OWNED: skill {clean_slug!r} is not owned by {layer_id}")
    shutil.rmtree(owned_dir)
    proj_dir = ensure_contained_path(ws / ".agents/skills" / clean_slug, ws)
    if proj_dir.is_dir() and clean_slug not in _resolve_engine_skill_sources():
        shutil.rmtree(proj_dir)
    return {
        "deleted": True,
        "slug": clean_slug,
        "canonical_rel_path": f"templates/{layer_id}/skills/{clean_slug}/SKILL.md",
    }


def save_node_skill_verified(
    workspace_dir: Path,
    *,
    skill_slug: str,
    content: str,
    expected_sha256: str = "",
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate SKILL.md via 3-tier zcg-skill-auditor, enforce SHA-256 lock, and project 0-drift."""
    ws = workspace_dir.resolve()
    clean_slug = skill_slug.strip()
    if not is_kebab_id(clean_slug):
        raise ValueError(f"INVALID_SKILL_SLUG: {skill_slug!r} must be lowercase kebab-case")
    layer_id = str(load_node_manifest(ws).get("layer_id") or ws.name)
    if not is_kebab_id(layer_id):
        raise ValueError(f"INVALID_LAYER_ID: {layer_id!r}")
    norm_txt = content.replace("\r\n", "\n").rstrip() + "\n"
    if len(norm_txt.splitlines()) > MAX_SKILL_LINES:
        raise ValueError(f"SKILL_AUDIT_REJECTED: exceeds {MAX_SKILL_LINES}-line modularity cap")
    tpl_root = ws / "templates"
    tpl_root.mkdir(parents=True, exist_ok=True)
    target = ensure_contained_path(
        tpl_root / layer_id / "skills" / clean_slug / "SKILL.md", tpl_root
    )
    exp_sha = expected_sha256.strip()
    if target.is_file() and exp_sha:
        cur_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        if cur_sha != exp_sha:
            raise ValueError("STALE_SKILL_REVISION: skill file changed on disk since editor load")
    with tempfile.TemporaryDirectory(prefix="zcg-skill-verify-") as tmp_str:
        stage_f = Path(tmp_str) / "skills" / clean_slug / "SKILL.md"
        stage_f.parent.mkdir(parents=True, exist_ok=True)
        stage_f.write_text(norm_txt, encoding="utf-8")
        fm = parse_skill_frontmatter(stage_f, repo_dir=Path(tmp_str))
        if fm.get("name") != clean_slug or not str(fm.get("description") or "").strip():
            raise ValueError(
                "SKILL_AUDIT_REJECTED: YAML frontmatter requires matching name and description"
            )
        audit = audit_skills_sovereign_profile(ws, target_dir=Path(tmp_str), parent_dir=parent_dir)
    if not audit["passed"]:
        results = audit["sarif"]["runs"][0]["results"]
        first_msg = str(results[0]["message"]["text"]) if results else "policy check failed"
        raise ValueError(f"SKILL_AUDIT_REJECTED: {first_msg}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(norm_txt, encoding="utf-8")
    proj_target = ensure_contained_path(ws / ".agents/skills" / clean_slug / "SKILL.md", ws)
    proj_target.parent.mkdir(parents=True, exist_ok=True)
    proj_target.write_text(norm_txt, encoding="utf-8")
    new_sha = hashlib.sha256(norm_txt.encode("utf-8")).hexdigest()
    return {
        "slug": clean_slug,
        "canonical_rel_path": f"templates/{layer_id}/skills/{clean_slug}/SKILL.md",
        "sha256": new_sha,
        "trust_score": audit["trust_score"],
    }


def _is_governed_commit_path(rel_path: str) -> bool:
    if rel_path in VALID_TRACKER_FILES or rel_path == NODE_MANIFEST_REL_PATH:
        return True
    parts = Path(rel_path).parts
    if (
        len(parts) >= 2
        and parts[0] == "docs"
        and rel_path.endswith(".md")
        and not any(p.startswith(".") for p in parts)
    ):
        return True
    if len(parts) == 5 and parts == ("surfaces", "web", "static", "brand", parts[4]) and parts[4]:
        return True
    return (
        len(parts) == 5
        and parts[0] == "templates"
        and is_kebab_id(parts[1])
        and parts[2] == "skills"
        and is_kebab_id(parts[3])
        and parts[4] == "SKILL.md"
    )


def commit_scoped_workspace_paths(
    workspace_dir: Path, *, rel_paths: Sequence[str], commit_message: str
) -> dict[str, Any]:
    """Create a path-scoped Conventional Commit on governed skill/tracker files with clean index."""
    ws = workspace_dir.resolve()
    msg = commit_message.strip()
    if not msg or "\n" in msg or not msg.startswith(VALID_COMMIT_PREFIXES):
        raise ValueError("INVALID_COMMIT_MESSAGE: single-line Conventional Commit prefix required")
    if not rel_paths:
        raise ValueError("UNSAFE_COMMIT_PATH: at least one target path is required")
    clean_paths: list[str] = []
    for raw_p in rel_paths:
        norm_p = raw_p.strip().replace("\\", "/").lstrip("/")
        ensure_contained_path(ws / norm_p, ws)
        if not _is_governed_commit_path(norm_p) or not (ws / norm_p).is_file():
            raise ValueError(f"UNSAFE_COMMIT_PATH: {raw_p!r} is outside governed UI commit scope")
        if norm_p not in clean_paths:
            clean_paths.append(norm_p)
    git_bin = _require_git_repo(ws)
    staged_proc = _run_git(git_bin, ws, "diff", "--cached", "--name-only")
    if staged_proc.stdout.strip():
        raise ValueError("INDEX_HAS_STAGED_FILES: commit or reset staged terminal files first")
    _run_git(git_bin, ws, "add", "--", *clean_paths)
    diff_proc = _run_git(git_bin, ws, "diff", "--cached", "--quiet")
    if diff_proc.returncode == 0:
        raise ValueError("NOTHING_TO_COMMIT: target files already match HEAD")
    commit_proc = _run_git(git_bin, ws, "commit", "-m", msg, "--", *clean_paths)
    if commit_proc.returncode != 0:
        raise ValueError(f"GIT_COMMIT_FAILED: {commit_proc.stderr.strip() or 'git commit failed'}")
    sha_proc = _run_git(git_bin, ws, "rev-parse", "--short", "HEAD")
    return {
        "commit_sha": sha_proc.stdout.strip(),
        "committed_paths": clean_paths,
        "commit_message": msg,
        "push_command": "git push",
    }
