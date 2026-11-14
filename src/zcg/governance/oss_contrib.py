"""Isolated Open-Source engine workflows (oss-push-branch, oss-promote-master, oss-publish).

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import SAFE_GIT_REF_RE
from zcg.core.manifests import load_node_manifest
from zcg.governance.authority import verify_layer_operation_authority
from zcg.topology.identity import resolve_node_entity_identity

VALID_OSS_ACTIONS: Final[tuple[str, ...]] = ("push-branch", "promote-master", "publish")
DEFAULT_OSS_REMOTE_URL: Final[str] = "git@github.com:mtwuser/zero-cloud-gravity.git"
_DEV_ORIGIN_RE: Final[re.Pattern[str]] = re.compile(r"(^|/|:)dev-[a-z0-9-]+(\.git)?$")


def should_expose_oss_targets(
    workspace_dir: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Return True when oss-* targets should appear in make help (dev clone or OSS_CONTRIB=1)."""
    eff_env = os.environ if env is None else env
    if eff_env.get("OSS_CONTRIB", "").strip() == "1":
        return True
    ws = workspace_dir.resolve()
    return resolve_node_entity_identity(ws).get("visibility_scope") == "private:open-source:dev"


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    git_bin = shutil.which("git") or "/usr/bin/git"
    return subprocess.run(  # noqa: S603
        [git_bin, *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _require_dev_clone_and_branch(ws: Path, action: str) -> str:
    if resolve_node_entity_identity(ws).get("visibility_scope") != "private:open-source:dev":
        raise ValueError(
            "[OSS_DEV_ONLY_BLOCKED] target is strictly scoped to private dev-<repo> clones "
            "(visibility_scope=private:open-source:dev)"
        )
    origin_url = _git(ws, "config", "--get", "remote.origin.url", check=False).stdout.strip()
    if not _DEV_ORIGIN_RE.search(origin_url):
        raise ValueError(
            "[OSS_DEV_ORIGIN_MISMATCH] origin remote must point to a private dev-<repo> repository"
        )
    if _git(ws, "status", "--porcelain", check=False).stdout.strip():
        raise ValueError("working tree is dirty — commit changes first")
    branch = _git(ws, "branch", "--show-current", check=False).stdout.strip()
    if not branch or branch in ("master", "main"):
        raise ValueError(
            f"[OSS_BRANCH_REQUIRED] switch to a feature/* or fix/* branch before running "
            f"make oss-{action}"
        )
    return branch


def _run_optional_workstation_sync(ws: Path) -> None:
    sync_sh = ws / "scripts/workstation-sync.sh"
    if sync_sh.is_file():
        subprocess.run([str(sync_sh), "--sync", "--no-browser"], cwd=ws, check=True)  # noqa: S603


def _export_sterile_snapshot(
    ws: Path,
    *,
    remote_url: str,
    eff_ver: str,
    clean_contrib: str,
    create_pr: bool,
    dry_run: bool,
) -> dict[str, Any]:
    git_bin = shutil.which("git") or "/usr/bin/git"
    target_br = clean_contrib or f"release/v{eff_ver}"
    has_v1 = bool(
        _git(ws, "ls-remote", "--tags", remote_url, "refs/tags/v1.0.0", check=False).stdout.strip()
    )
    orphan_root = (not create_pr) and (not has_v1)
    with tempfile.TemporaryDirectory() as tmp_dir:
        pub_dir = Path(tmp_dir) / "pub"
        if orphan_root:
            pub_dir.mkdir(parents=True, exist_ok=True)
            _git(pub_dir, "init", "--quiet", "-b", "master")
            _git(pub_dir, "remote", "add", "origin", remote_url)
        else:
            _git(ws, "clone", "--quiet", remote_url, str(pub_dir))
            if create_pr:
                _git(pub_dir, "checkout", "--quiet", "-B", target_br)
            for child in pub_dir.iterdir():
                if child.name == ".git":
                    continue
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        arch_proc = subprocess.run(  # noqa: S603
            [git_bin, "-C", str(ws), "archive", "--format=tar", "HEAD"],
            check=True,
            capture_output=True,
        )
        with tarfile.open(fileobj=io.BytesIO(arch_proc.stdout), mode="r:") as tf:
            tf.extractall(pub_dir, filter="data")
        for wf in pub_dir.glob("WORK*.md"):
            wf.unlink()
        (pub_dir / "BACKLOG.md").unlink(missing_ok=True)
        (pub_dir / ".github/dependabot.yml").unlink(missing_ok=True)
        shutil.rmtree(pub_dir / "roadmaps", ignore_errors=True)
        u_email = _git(ws, "config", "user.email", check=False).stdout.strip() or "zcg@localhost"
        u_name = _git(ws, "config", "user.name", check=False).stdout.strip() or "ZeroCloudGravity"
        _git(pub_dir, "config", "user.email", u_email)
        _git(pub_dir, "config", "user.name", u_name)
        _git(pub_dir, "add", "-A")
        commit_msg = (
            f"chore(contrib): export {target_br} snapshot"
            if clean_contrib
            else f"chore(release): publish ZeroCloudGravity v{eff_ver}"
        )
        if _git(pub_dir, "diff", "--cached", "--quiet", check=False).returncode != 0:
            _git(pub_dir, "commit", "--quiet", "-m", commit_msg)
        commits = int(_git(pub_dir, "rev-list", "--count", "HEAD").stdout.strip())
        if create_pr:
            if dry_run:
                msg = (
                    f"[oss-publish CREATE_PR=1 DRY_RUN=1] Prepared branch {target_br} "
                    f"(commits={commits}) for {remote_url}"
                )
            else:
                _git(pub_dir, "push", "-u", "origin", target_br, "--force-with-lease")
                msg = (
                    f"Pushed PR branch '{target_br}' to {remote_url} — open PR against master "
                    "to run CI before merging."
                )
        else:
            _git(pub_dir, "tag", "-f", "-a", f"v{eff_ver}", "-m", f"Release v{eff_ver}")
            if dry_run:
                msg = (
                    f"[oss-publish DRY_RUN=1] Prepared v{eff_ver} "
                    f"(orphan_root={1 if orphan_root else 0}, commits={commits}) for {remote_url}"
                )
            else:
                if orphan_root:
                    _git(pub_dir, "push", "--force", "origin", "master", "--tags")
                else:
                    _git(pub_dir, "push", "origin", "master", "--follow-tags")
                _run_optional_workstation_sync(ws)
                msg = f"Published ZeroCloudGravity v{eff_ver} to {remote_url}."
    return {
        "action": "publish",
        "release_version": eff_ver,
        "target_branch": target_br,
        "create_pr": create_pr,
        "orphan_root": orphan_root,
        "commits": commits,
        "dry_run": dry_run,
        "message": msg,
    }


def run_oss_action(
    workspace_dir: Path,
    action: str,
    *,
    remote_url: str = DEFAULT_OSS_REMOTE_URL,
    release_version: str | None = None,
    contrib_branch: str = "",
    create_pr: bool = False,
    verify: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute isolated OSS engine workflow (push-branch, promote-master, or publish)."""
    if action not in VALID_OSS_ACTIONS:
        raise ValueError(f"Invalid OSS action {action!r}; must be one of {VALID_OSS_ACTIONS}")
    ws = workspace_dir.resolve()
    if action in ("push-branch", "promote-master"):
        branch = _require_dev_clone_and_branch(ws, action)
        if action == "push-branch":
            if verify:
                subprocess.run([str(ws / "scripts/verify-repo.sh")], cwd=ws, check=True)  # noqa: S603
            if dry_run:
                msg = (
                    f"[oss-push-branch DRY_RUN=1] Would push branch '{branch}' to private origin "
                    "for GitHub Actions validation"
                )
            else:
                _git(ws, "push", "-u", "origin", branch)
                msg = (
                    f"Pushed '{branch}' to private origin — confirm GitHub Actions is green, "
                    "then run 'make oss-promote-master'."
                )
            return {"action": action, "branch": branch, "dry_run": dry_run, "message": msg}
        if dry_run:
            msg = (
                f"[oss-promote-master DRY_RUN=1] Would fast-forward master from '{branch}', "
                f"push origin master, delete '{branch}', and sync workstation"
            )
        else:
            _git(ws, "checkout", "master")
            _git(ws, "pull", "--ff-only", "origin", "master")
            _git(ws, "merge", "--ff-only", branch)
            _git(ws, "push", "origin", "master")
            _git(ws, "branch", "-d", branch)
            _git(ws, "push", "origin", "--delete", branch, check=False)
            _run_optional_workstation_sync(ws)
            msg = (
                f"Promoted '{branch}' onto master, cleaned temporary branch, and synchronized "
                "workstation."
            )
        return {"action": action, "branch": branch, "dry_run": dry_run, "message": msg}
    if verify:
        subprocess.run([str(ws / "scripts/verify-repo.sh")], cwd=ws, check=True)  # noqa: S603
    if _git(ws, "status", "--porcelain", check=False).stdout.strip():
        raise ValueError("working tree is dirty")
    ver_file = (ws / "VERSION").read_text(encoding="utf-8").strip()
    eff_ver = (release_version or ver_file).strip()
    if eff_ver != ver_file:
        raise ValueError(
            f"[OSS_PUBLISH_GUARD_BLOCKED] RELEASE_VERSION ({eff_ver}) "
            f"must match VERSION ({ver_file})"
        )
    clean_contrib = contrib_branch.strip()
    if clean_contrib and (not SAFE_GIT_REF_RE.match(clean_contrib) or ".." in clean_contrib):
        raise ValueError(f"Invalid CONTRIB_BRANCH {clean_contrib!r}")
    if not clean_contrib:
        chlog = (ws / "CHANGELOG.md").read_text("utf-8") if (ws / "CHANGELOG.md").is_file() else ""
        if re.search(r"^## \[Unreleased\]", chlog, re.M):
            raise ValueError(
                "[OSS_UNRELEASED_CHANGELOG_BLOCKED] CHANGELOG.md still has [Unreleased] "
                "(or pass CREATE_PR=1 CONTRIB_BRANCH=contrib/<slug>)"
            )
        if _git(
            ws, "ls-remote", "--tags", remote_url, f"refs/tags/v{eff_ver}", check=False
        ).stdout.strip():
            raise ValueError(
                f"[OSS_TAG_ALREADY_PUBLISHED] tag v{eff_ver} already exists on {remote_url}"
            )
    if load_node_manifest(ws).get("entity_kind") != "open-source":
        raise ValueError("[OSS_PERSONAL_REPO_PUBLISH_BLOCKED] entity_kind must be open-source")
    if not create_pr and not verify_layer_operation_authority(ws, operation="release")["allowed"]:
        raise ValueError(
            "[UNAUTHORIZED_OSS_RELEASE] caller lacks release authority (use CREATE_PR=1)"
        )
    return _export_sterile_snapshot(
        ws,
        remote_url=remote_url,
        eff_ver=eff_ver,
        clean_contrib=clean_contrib,
        create_pr=create_pr,
        dry_run=dry_run,
    )
