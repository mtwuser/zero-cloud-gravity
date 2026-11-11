#!/usr/bin/env python3
"""PostToolUse hook: auto-format edited Python files with ruff.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

_VENV_DIRS: tuple[str, ...] = ("venv", ".venv", "backend/venv", "backend/.venv")
_FORMAT_TIMEOUT_SECONDS: int = 10


def _find_ruff(workspace_paths: list[str]) -> str | None:
    for ws in workspace_paths:
        for venv_dir in _VENV_DIRS:
            candidate = Path(ws) / venv_dir / "bin" / "ruff"
            if candidate.exists():
                return str(candidate)
    return shutil.which("ruff")


def main() -> None:
    """Format the edited Python file with ruff if available and emit empty JSON."""
    payload = json.load(sys.stdin)
    args = payload.get("toolCall", {}).get("args", {})
    target = str(args.get("Path") or "")
    if not target or not target.endswith(".py"):
        json.dump({}, sys.stdout)
        return
    workspace_paths = [str(w) for w in payload.get("workspacePaths", [])]
    target_path = Path(target)
    if not target_path.is_absolute():
        for ws in workspace_paths:
            candidate = Path(ws) / target_path
            if candidate.exists():
                target_path = candidate
                break
    if target_path.exists() and (ruff_bin := _find_ruff(workspace_paths)):
        with contextlib.suppress(subprocess.TimeoutExpired, OSError):
            subprocess.run(
                [ruff_bin, "format", str(target_path)],
                check=False,
                capture_output=True,
                timeout=_FORMAT_TIMEOUT_SECONDS,
            )
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
