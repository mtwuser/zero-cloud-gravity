"""Zero-checkout DMCP branch readers, GRCC capsule-ref plumbing, and deep-context indexing.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zcg.capsules.codec import (
    parse_capsule_envelope,
    seal_dmcp_context_frame,
    verify_dmcp_context_frame,
)
from zcg.capsules.constants import (
    ALLOWED_READ_PREFIXES,
    ALLOWED_ROOT_FILES,
    CAPSULE_ABSTRACTION_LAYERS,
    CITATION_LIFECYCLE_QUADRANTS,
    DEFAULT_EPHEMERAL_TTL_SECONDS,
    DEFAULT_SPECIALTY_BRANCH_PREFIX,
    GRCC_CAPSULE_BLOB_PATH,
    VALID_GRCC_OPERATIONS,
)
from zcg.core.constants import (
    CANONICAL_SCIENCE_TRUNKS,
    CAPSULE_DIGEST_HEX_LEN,
    CAPSULE_REF_NAMESPACE,
    EPISTEMIC_GRADE_LABELS,
    GIT_CMD_TIMEOUT_SECONDS,
    SAFE_GIT_REF_RE,
    VALID_KNOWLEDGE_PREFIXES,
)
from zcg.core.epistemics import classify_knowledge_domain, resolve_knowledge_mount_endpoints


def _run_git_plumbing(
    repo_dir: Path, args: list[str], *, stdin_text: str | None = None, check: bool = False
) -> subprocess.CompletedProcess[str]:
    git_bin = shutil.which("git") or "git"
    git_env = {
        "GIT_AUTHOR_NAME": "zcg-mcp-grcc",
        "GIT_AUTHOR_EMAIL": "grcc@zcg-mcp.local",
        "GIT_COMMITTER_NAME": "zcg-mcp-grcc",
        "GIT_COMMITTER_EMAIL": "grcc@zcg-mcp.local",
        **os.environ,
    }
    return subprocess.run(  # noqa: S603
        [git_bin, "-C", str(repo_dir), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=git_env,
        timeout=GIT_CMD_TIMEOUT_SECONDS,
        check=check,
    )


def resolve_git_branch_commit_sha(branch_ref: str, target_base: Path) -> tuple[str, str]:
    """Validate branch_ref safety and resolve its commit SHA without mutating HEAD."""
    clean_ref = branch_ref.strip()
    if (
        not clean_ref
        or ".." in clean_ref
        or clean_ref.startswith("-")
        or not SAFE_GIT_REF_RE.match(clean_ref)
    ):
        raise ValueError(f"Invalid or unsafe branch_ref: {branch_ref!r}")
    proc = _run_git_plumbing(target_base, ["rev-parse", "--verify", f"{clean_ref}^{{commit}}"])
    if proc.returncode != 0:
        raise ValueError(f"DMCP_BRANCH_REF_NOT_FOUND: Git ref {clean_ref!r} not found")
    return clean_ref, proc.stdout.strip()


def read_git_branch_document(
    target_base: Path, relative_path: str, branch_ref: str
) -> tuple[str, str]:
    """Read an allowlisted, path-contained file from branch_ref via git show."""
    base_res = target_base.resolve()
    clean_rel = relative_path.strip().lstrip("/")
    if not clean_rel or ".." in Path(clean_rel).parts:
        raise ValueError(f"PATH_CONTAINMENT_VIOLATION: Invalid relative path {relative_path!r}")
    cand = (base_res / clean_rel).resolve()
    if not cand.is_relative_to(base_res):
        raise ValueError(f"PATH_CONTAINMENT_VIOLATION: Path escapes root: {relative_path!r}")
    rel_str = str(cand.relative_to(base_res)).replace("\\", "/")
    if rel_str not in ALLOWED_ROOT_FILES and not any(
        rel_str.startswith(p) for p in ALLOWED_READ_PREFIXES
    ):
        raise ValueError(f"Access denied for {relative_path!r}: outside readable surfaces.")
    clean_ref, commit_sha = resolve_git_branch_commit_sha(branch_ref, base_res)
    proc = _run_git_plumbing(base_res, ["show", f"{clean_ref}:{rel_str}"])
    if proc.returncode != 0:
        raise FileNotFoundError(f"Document {rel_str!r} not found on branch_ref {clean_ref!r}")
    return proc.stdout, commit_sha


def list_git_branch_markdown_files(
    target_base: Path, branch_ref: str, *, scope: str = "all", target_path: str = ""
) -> tuple[str, list[tuple[str, str]]]:
    """List and read scoped Markdown documents on branch_ref without mutating HEAD."""
    base_res = target_base.resolve()
    clean_ref, commit_sha = resolve_git_branch_commit_sha(branch_ref, base_res)
    proc = _run_git_plumbing(base_res, ["ls-tree", "-r", "--name-only", clean_ref])
    clean_t, docs_out = target_path.strip().lstrip("/"), list[tuple[str, str]]()
    for raw_line in proc.stdout.splitlines():
        rel_p = raw_line.strip()
        if not rel_p.endswith(".md"):
            continue
        in_scope = (
            (rel_p == clean_t)
            or (scope in ("all", "global") and rel_p == "antigravity/.gemini/config/AGENTS.md")
            or (scope in ("all", "templates") and rel_p.startswith("templates/"))
            or (
                scope in ("all", "docs")
                and (
                    rel_p.startswith("docs/")
                    or (
                        scope == "all"
                        and (
                            rel_p in ALLOWED_ROOT_FILES
                            or rel_p.startswith(("corporate/", "surfaces/", "roadmaps/"))
                        )
                    )
                )
            )
        )
        if in_scope:
            with contextlib.suppress(ValueError, FileNotFoundError):
                txt, _ = read_git_branch_document(base_res, rel_p, clean_ref)
                docs_out.append((rel_p, txt))
    return commit_sha, docs_out


def compute_grcc_scope_fingerprint(
    layer_id: str, branch_ref: str, task_scope: str
) -> tuple[str, str]:
    """Compute a deterministic HMAC-SHA256 GRCC scope fingerprint and refs/zcg/capsules/<fp> ref."""
    lid = layer_id.strip() or "root"
    bref = branch_ref.strip() or "master"
    tscope = task_scope.strip() or "default"
    fp = hmac.new(b"grcc-scope-v1", f"{lid}:{bref}:{tscope}".encode(), hashlib.sha256).hexdigest()[
        :CAPSULE_DIGEST_HEX_LEN
    ]
    return fp, f"{CAPSULE_REF_NAMESPACE}/{fp}"


def orchestrate_dmcp_branch_projection(
    repo_dir: Path, parent_layer_id: str, arguments: dict[str, Any], *, default_secret: str
) -> dict[str, Any]:
    """Project a zero-checkout DMCP branch context frame with fail-closed master fallback."""
    branch_ref = str(arguments.get("branch_ref") or "master").strip()
    task_step_id = str(arguments.get("task_step_id") or "step-1").strip()
    target_path = str(arguments.get("target_path") or "").strip()
    globs = [str(g) for g in arguments.get("target_globs", []) if str(g).strip()] or ["**"]
    ttl_seconds = int(arguments.get("ttl_seconds") or DEFAULT_EPHEMERAL_TTL_SECONDS)
    session_key = str(arguments.get("resonance_key") or default_secret).strip()
    incoming_token = str(arguments.get("context_frame_token") or "").strip()
    parent_frame_hash = "genesis"
    if incoming_token:
        verified_in = verify_dmcp_context_frame(
            incoming_token,
            expected_repo_id=parent_layer_id,
            session_key=session_key,
            target_path=target_path,
        )
        if not verified_in["verified"]:
            return {"action": "project-branch", "zero_checkout": True, **verified_in}
        parent_frame_hash = str(verified_in["frame_hash"])
    valid_ref = (
        bool(branch_ref)
        and ".." not in branch_ref
        and not branch_ref.startswith("-")
        and bool(SAFE_GIT_REF_RE.match(branch_ref))
    )
    sha_proc = (
        _run_git_plumbing(repo_dir, ["rev-parse", "--verify", f"{branch_ref}^{{commit}}"])
        if valid_ref
        else None
    )
    if sha_proc is None or sha_proc.returncode != 0:
        return {
            "action": "project-branch",
            "verified": False,
            "error_code": "DMCP_CONTEXT_FRAME_INVALID",
            "reason": f"Branch ref {branch_ref!r} not found or invalid",
            "effective_branch_ref": "master",
            "fallback_activated": True,
            "zero_checkout": True,
        }
    sealed = seal_dmcp_context_frame(
        parent_layer_id,
        branch_ref,
        sha_proc.stdout.strip(),
        task_step_id,
        globs,
        parent_frame_hash=parent_frame_hash,
        ttl_seconds=ttl_seconds,
        session_key=session_key,
    )
    return {
        "action": "project-branch",
        "verified": True,
        "error_code": None,
        "fallback_activated": False,
        "effective_branch_ref": branch_ref,
        "zero_checkout": True,
        **sealed,
    }


def orchestrate_grcc_capsule_ref(
    repo_dir: Path, parent_layer_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute GRCC O(1) probe, pre-sealed .rcap1 commit chaining, unfold, or ref pruning."""
    grcc_op = str(arguments.get("grcc_op") or "probe").strip().lower()
    if grcc_op not in VALID_GRCC_OPERATIONS:
        raise ValueError(f"Invalid grcc_op {grcc_op!r}: must be one of {VALID_GRCC_OPERATIONS}")
    branch_ref = str(arguments.get("branch_ref") or "master").strip()
    task_scope = str(
        arguments.get("task_step_id") or arguments.get("target_path") or "default"
    ).strip()
    scope_fp, capsule_ref = compute_grcc_scope_fingerprint(parent_layer_id, branch_ref, task_scope)

    def _read_lineage() -> tuple[str | None, str | None]:
        proc = _run_git_plumbing(repo_dir, ["log", "-n", "1", "--format=%H:%P", capsule_ref])
        if proc.returncode != 0 or not proc.stdout.strip():
            return None, None
        c_sha, _, p_raw = proc.stdout.strip().partition(":")
        return c_sha, (p_raw.split()[0] if p_raw.strip() else None)

    if grcc_op == "probe":
        if remote := str(arguments.get("remote") or "").strip():
            r_proc = _run_git_plumbing(repo_dir, ["ls-remote", "--exit-code", remote, capsule_ref])
            exists = r_proc.returncode == 0 and bool(r_proc.stdout.strip())
            c_sha, p_sha = (r_proc.stdout.split()[0] if exists else None), None
        else:
            c_sha, p_sha = _read_lineage()
            exists = c_sha is not None
        return {
            "action": "chain-capsule-ref",
            "grcc_op": "probe",
            "exists": exists,
            "capsule_ref": capsule_ref,
            "scope_fingerprint": scope_fp,
            "commit_sha": c_sha,
            "parent_commit_sha": p_sha,
            "zero_checkout": True,
        }

    if grcc_op == "seal":
        capsule_token = str(arguments.get("capsule_token") or "").strip()
        if not capsule_token:
            raise ValueError("Missing required 'capsule_token' for grcc_op='seal'")
        header, _, _, _ = parse_capsule_envelope(capsule_token)
        parent_sha, _ = _read_lineage()
        blob_sha = _run_git_plumbing(
            repo_dir, ["hash-object", "-w", "--stdin"], stdin_text=capsule_token, check=True
        ).stdout.strip()
        agents_tree = _run_git_plumbing(
            repo_dir, ["mktree"], stdin_text=f"100644 blob {blob_sha}\tcapsule.rcap1\n", check=True
        ).stdout.strip()
        root_tree = _run_git_plumbing(
            repo_dir, ["mktree"], stdin_text=f"040000 tree {agents_tree}\t.agents\n", check=True
        ).stdout.strip()
        c_args = [
            "commit-tree",
            root_tree,
            *(["-p", parent_sha] if parent_sha else []),
            "-m",
            f"grcc({task_scope}): pre-sealed rcap1 capsule",
        ]
        commit_sha = _run_git_plumbing(repo_dir, c_args, check=True).stdout.strip()
        _run_git_plumbing(repo_dir, ["update-ref", capsule_ref, commit_sha], check=True)
        return {
            "action": "chain-capsule-ref",
            "grcc_op": "seal",
            "sealed": True,
            "capsule_ref": capsule_ref,
            "scope_fingerprint": scope_fp,
            "blob_path": GRCC_CAPSULE_BLOB_PATH,
            "commit_sha": commit_sha,
            "parent_commit_sha": parent_sha,
            "capsule_header": header,
            "zero_checkout": True,
        }

    if grcc_op == "unfold":
        show_proc = _run_git_plumbing(repo_dir, ["show", f"{capsule_ref}:{GRCC_CAPSULE_BLOB_PATH}"])
        if show_proc.returncode != 0:
            raise ValueError(f"GRCC_CAPSULE_REF_NOT_FOUND: No pre-sealed capsule at {capsule_ref}")
        capsule_token = show_proc.stdout.strip()
        header, _, _, _ = parse_capsule_envelope(capsule_token)
        c_sha, parent_sha = _read_lineage()
        return {
            "action": "chain-capsule-ref",
            "grcc_op": "unfold",
            "capsule_ref": capsule_ref,
            "scope_fingerprint": scope_fp,
            "blob_path": GRCC_CAPSULE_BLOB_PATH,
            "commit_sha": c_sha,
            "parent_commit_sha": parent_sha,
            "capsule_token": capsule_token,
            "capsule_header": header,
            "zero_checkout": True,
        }

    _run_git_plumbing(repo_dir, ["update-ref", "-d", capsule_ref])
    return {
        "action": "chain-capsule-ref",
        "grcc_op": "prune",
        "pruned": True,
        "capsule_ref": capsule_ref,
        "scope_fingerprint": scope_fp,
        "zero_checkout": True,
    }


def discover_deep_context_index(target_dir: Path, mounted: list[dict[str, Any]]) -> dict[str, Any]:
    """Discover specialty/* branches, refs/zcg/capsules/* refs, and mounted knowledge corpora."""
    proc = _run_git_plumbing(
        target_dir,
        [
            "for-each-ref",
            "--format=%(refname)",
            f"refs/heads/{DEFAULT_SPECIALTY_BRANCH_PREFIX}",
            CAPSULE_REF_NAMESPACE,
        ],
    )
    lines = proc.stdout.splitlines() if proc.returncode == 0 else []
    return {
        "specialty_branches": [
            ln.removeprefix("refs/heads/").strip()
            for ln in lines
            if ln.strip().startswith(f"refs/heads/{DEFAULT_SPECIALTY_BRANCH_PREFIX}")
        ],
        "grcc_capsule_refs": [
            ln.strip() for ln in lines if ln.strip().startswith(f"{CAPSULE_REF_NAMESPACE}/")
        ],
        "mounted_subtrees_count": len(mounted),
        "knowledge_nodes": [
            resolve_knowledge_mount_endpoints(m, target_dir)
            for m in mounted
            if classify_knowledge_domain(
                str(m.get("name") or ""), str(m.get("layer_role") or "project")
            )["is_knowledge_node"]
        ],
        "supported_knowledge_prefixes": list(VALID_KNOWLEDGE_PREFIXES),
        "canonical_science_trunks": {k: list(v) for k, v in CANONICAL_SCIENCE_TRUNKS.items()},
        "epistemic_grades": dict(EPISTEMIC_GRADE_LABELS),
        "abstraction_gradient": dict(CAPSULE_ABSTRACTION_LAYERS),
        "citation_lifecycle_quadrants": dict(CITATION_LIFECYCLE_QUADRANTS),
    }
