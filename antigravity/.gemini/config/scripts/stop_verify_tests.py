#!/usr/bin/env python3
"""Stop hook: verify unit tests pass across modified workspaces before stopping.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_SUMMARY_TAIL_LINES: int = 3
_STDERR_TAIL_CHARS: int = 200
_GIT_TIMEOUT_SECONDS: int = 5
_PYTEST_TIMEOUT_SECONDS: int = 120
_PYTEST_NO_TESTS_EXIT_CODE: int = 5
_ZCG_REPO_DIR: Path = Path(__file__).resolve().parents[4]
_VENV_DIRS: tuple[str, ...] = ("venv", ".venv", "backend/venv", "backend/.venv")


def resolve_effective_workspaces(
    workspace_paths: list[str], zcg_repo: Path | None = None
) -> list[str]:
    """Return workspace_paths plus the ZeroCloudGravity repo if present and distinct."""
    effective = list(workspace_paths)
    if not effective:
        return []
    cand = zcg_repo if zcg_repo is not None else _ZCG_REPO_DIR
    cand_str = str(cand)
    if (cand / ".git").exists() and cand_str not in effective:
        effective.append(cand_str)
    return effective


def find_venv(workspace_paths: list[str]) -> Path | None:
    """Find the first virtualenv Python interpreter with pytest across workspace_paths."""
    for ws in workspace_paths:
        for venv_dir in _VENV_DIRS:
            venv_bin = Path(ws) / venv_dir / "bin"
            if (venv_bin / "python").exists() and (venv_bin / "pytest").exists():
                return venv_bin / "python"
    return None


def has_python_changes(workspace_path: str) -> bool:
    """Return True if any .py files were modified, staged, or newly created."""
    git_bin = shutil.which("git") or "git"
    with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError):
        unstaged = subprocess.run(
            [git_bin, "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            cwd=workspace_path,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        staged = subprocess.run(
            [git_bin, "diff", "--name-only", "--cached", "--diff-filter=ACMR"],
            check=False,
            capture_output=True,
            text=True,
            cwd=workspace_path,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        untracked = subprocess.run(
            [git_bin, "ls-files", "--others", "--exclude-standard", "--", "*.py"],
            check=False,
            capture_output=True,
            text=True,
            cwd=workspace_path,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        all_files = unstaged.stdout + staged.stdout + untracked.stdout
        return any(f.strip().endswith(".py") for f in all_files.splitlines() if f.strip())
    return True


def run_tests(venv_python: Path, workspace_path: str) -> tuple[bool, str]:
    """Run pytest with ZCG_NO_BROWSER=1 and return (passed, summary)."""
    src_dir = Path(workspace_path) / "src"
    env = {
        **os.environ,
        "ZCG_NO_BROWSER": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        **({"PYTHONPATH": str(src_dir)} if src_dir.is_dir() else {}),
    }
    try:
        res = subprocess.run(
            [str(venv_python), "-m", "pytest", "--tb=line", "-q", "--no-header", "-x"],
            check=False,
            capture_output=True,
            text=True,
            cwd=workspace_path,
            env=env,
            timeout=_PYTEST_TIMEOUT_SECONDS,
        )
        lines = res.stdout.strip().splitlines()
        summary = "\n".join(lines[-_SUMMARY_TAIL_LINES:])
        if res.returncode in (0, _PYTEST_NO_TESTS_EXIT_CODE):
            return True, summary
        err_tail = res.stderr.strip()[-_STDERR_TAIL_CHARS:] if res.stderr else ""
        return False, f"{summary}\n{err_tail}".strip()
    except subprocess.TimeoutExpired:
        return False, "Tests timed out after 120 seconds."


def main() -> None:
    """Verify tests pass across modified workspaces before stopping."""
    payload = json.load(sys.stdin)
    if payload.get("terminationReason", "") not in ("NO_TOOL_CALL", "model_stop"):
        json.dump({"decision": "stop"}, sys.stdout)
        return
    workspace_paths = resolve_effective_workspaces(
        [str(w) for w in payload.get("workspacePaths", [])]
    )
    if not workspace_paths:
        json.dump({"decision": "stop"}, sys.stdout)
        return
    failures: list[str] = []
    for ws in workspace_paths:
        if not has_python_changes(ws):
            continue
        venv_python = find_venv([ws, *workspace_paths])
        if venv_python is None:
            continue
        passed, summary = run_tests(venv_python, ws)
        if not passed:
            failures.append(f"[{Path(ws).name}]\n{summary}")
    if not failures:
        json.dump({"decision": "stop"}, sys.stdout)
    else:
        joined = "\n\n".join(failures)
        json.dump(
            {
                "decision": "continue",
                "reason": f"Tests are FAILING. Fix before stopping.\n\n{joined}",
            },
            sys.stdout,
        )


if __name__ == "__main__":
    main()
