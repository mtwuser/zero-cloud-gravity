"""Ephemeral fork root resolution, copy-on-write helpers, inspection, and TTL reaping.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from zcg.core.constants import (
    KEBAB_ID_RE,
    NODE_MANIFEST_REL_PATH,
    OWNER_DIR_RWX_BITS,
    VALID_DYNAMIC_RESOLUTION_POLICIES,
)


def _is_writable_or_creatable(target: Path) -> bool:
    curr = target
    while not curr.exists() and curr.parent != curr:
        curr = curr.parent
    return curr.exists() and os.access(curr, os.W_OK)


def default_ephemeral_root(repo_dir: Path, ephemeral_root: Path | None = None) -> Path:
    """Return the resolved directory holding active ephemeral forks (with /tmp fallback if ro)."""
    if ephemeral_root is not None:
        return ephemeral_root.resolve()
    if env_override := os.environ.get("ZCG_EPHEMERAL_ROOT", "").strip():
        return Path(env_override).resolve()
    candidate = (repo_dir.resolve() / "logs/ephemeral_forks").resolve()
    if candidate.is_dir() or _is_writable_or_creatable(candidate):
        return candidate
    tmp_fallback = (Path(tempfile.gettempdir()).resolve() / "zcg_ephemeral_forks").resolve()
    return tmp_fallback if _is_writable_or_creatable(tmp_fallback) else candidate


def ensure_dirs_writable(root: Path) -> None:
    """Ensure owner rwx bits on root and all non-symlink subdirectories for cleanup."""
    for d in (root, *(p for p in root.rglob("*") if not p.is_symlink() and p.is_dir())):
        d.chmod(d.stat().st_mode | OWNER_DIR_RWX_BITS)


def _link_or_copy_file(src_str: str, dst_str: str) -> str:
    with contextlib.suppress(OSError):
        os.link(src_str, dst_str)
        return dst_str
    return shutil.copy2(src_str, dst_str)


def copy_zero_copy(src: Path, dst: Path) -> None:
    """Materialize src into dst via hardlinks when supported, falling back to copy2."""
    if src.is_dir():
        shutil.copytree(
            src, dst, symlinks=True, dirs_exist_ok=True, copy_function=_link_or_copy_file
        )
        ensure_dirs_writable(dst)
    else:
        _link_or_copy_file(str(src), str(dst))


def reap_expired_ephemeral_forks(
    repo_dir: Path, ephemeral_root: Path | None = None, now_epoch: float | None = None
) -> list[str]:
    """Delete expired or corrupted ephemeral forks under ephemeral_root."""
    root = default_ephemeral_root(repo_dir, ephemeral_root)
    if not root.is_dir():
        return []
    now, reaped = (now_epoch if now_epoch is not None else time.time()), list[str]()
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        m_path = child / NODE_MANIFEST_REL_PATH
        expired = not m_path.is_file()
        if not expired:
            try:
                data = json.loads(m_path.read_text(encoding="utf-8"))
                expired = now >= float(
                    data.get("ephemeral_metadata", {}).get("expires_at_epoch", 0.0)
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                expired = True
        if expired:
            ensure_dirs_writable(child)
            shutil.rmtree(child, ignore_errors=True)
            reaped.append(child.name)
    return reaped


def inspect_ephemeral_forks(
    repo_dir: Path,
    fork_id: str | None = None,
    ephemeral_root: Path | None = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """List active ephemeral forks or inspect a specific fork_id after TTL cleanup."""
    reaped = reap_expired_ephemeral_forks(repo_dir, ephemeral_root, now_epoch=now_epoch)
    root = default_ephemeral_root(repo_dir, ephemeral_root)
    now, forks = (now_epoch if now_epoch is not None else time.time()), list[dict[str, Any]]()
    for child in sorted(root.iterdir()) if root.is_dir() else ():
        m_path = child / NODE_MANIFEST_REL_PATH
        if not m_path.is_file() or (fork_id and child.name != fork_id):
            continue
        data = json.loads(m_path.read_text(encoding="utf-8"))
        meta = data.get("ephemeral_metadata", {})
        rem = max(0.0, round(float(meta.get("expires_at_epoch", 0.0)) - now, 1))
        forks.append(
            {
                "fork_id": child.name,
                "fork_dir": str(child),
                "bot_role": str(meta.get("bot_role", "")),
                "persistence_mode": str(meta.get("persistence_mode", "dynamic")),
                "resolution_policy": str(meta.get("resolution_policy", "ttl-expired")),
                "model_tier": str(meta.get("model_tier", "flash")),
                "access_mode": str(meta.get("access_mode", "strictly-read-only")),
                "ephemeral_scope": str(meta.get("ephemeral_scope", "intra-layer")),
                "actor_role": str(meta.get("actor_role", "member")),
                "remaining_ttl_seconds": rem,
                "default_stack_templates": list(data.get("default_stack_templates", [])),
            }
        )
    if fork_id and not forks:
        if fork_id in reaped:
            raise FileNotFoundError(f"EPHEMERAL_FORK_EXPIRED: Ephemeral fork {fork_id!r} expired.")
        raise FileNotFoundError(f"Ephemeral fork {fork_id!r} not found.")
    return {"active_count": len(forks), "reaped_expired": reaped, "forks": forks}


def reap_ephemeral_fork(
    repo_dir: Path,
    fork_id: str,
    ephemeral_root: Path | None = None,
    dry_run: bool = False,
    resolution_reason: str = "goal-resolved",
) -> dict[str, Any]:
    """Explicitly reap one ephemeral fork by fork_id or 'all' active ephemeral forks."""
    clean_reason = resolution_reason.strip().lower() or "goal-resolved"
    if clean_reason not in VALID_DYNAMIC_RESOLUTION_POLICIES:
        raise ValueError(f"Invalid resolution_reason {clean_reason!r}")
    root, reaped = default_ephemeral_root(repo_dir, ephemeral_root), list[str]()
    if fork_id == "all":
        for child in sorted(root.iterdir()) if root.is_dir() else ():
            if child.is_dir():
                reaped.append(child.name)
                if not dry_run:
                    ensure_dirs_writable(child)
                    shutil.rmtree(child, ignore_errors=True)
    else:
        if not KEBAB_ID_RE.match(fork_id):
            raise ValueError(f"Invalid fork_id {fork_id!r}: must be kebab-case or 'all'")
        target = (root / fork_id).resolve()
        if not target.is_relative_to(root) or not target.is_dir():
            raise FileNotFoundError(f"Ephemeral fork {fork_id!r} not found under {root}")
        reaped.append(fork_id)
        if not dry_run:
            ensure_dirs_writable(target)
            shutil.rmtree(target, ignore_errors=True)
    if not dry_run:
        with contextlib.suppress(OSError):
            root.rmdir()
            root.parent.rmdir()
    return {"dry_run": dry_run, "reaped_forks": reaped, "resolution_reason": clean_reason}
