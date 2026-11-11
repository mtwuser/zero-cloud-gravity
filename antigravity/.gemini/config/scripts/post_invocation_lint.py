#!/usr/bin/env python3
"""PostInvocation hook: lint, structural, and token-budget checks on modified files.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import ast
import contextlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_MAX_SUMMARY_LINES: int = 15
_MAX_FORCE_CONTINUE_INVOCATIONS: int = 5
_AGENTS_MD_MAX_BYTES: int = 18000
_TOTAL_RULES_BUDGET_MAX_BYTES: int = 80000
_MAX_PYTHON_FILE_LINES: int = 465
_MODEL_DECISION_FRONTMATTER_SCAN_CHARS: int = 300
_CHARS_PER_TOKEN_ESTIMATE: int = 4
_GIT_TIMEOUT_SECONDS: int = 5
_RUFF_TIMEOUT_SECONDS: int = 10
_ZCG_REPO_DIR: Path = Path(__file__).resolve().parents[4]
_VENV_DIRS: tuple[str, ...] = ("venv", ".venv", "backend/venv", "backend/.venv")


def _extract_test_blocks(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [text]
    lines = text.splitlines()
    return [
        "\n".join(lines[node.lineno - 1 : node.end_lineno])
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


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


def check_universal_python_structure(py_files: list[str]) -> list[str]:
    """Enforce < 465-line cap, 0-byte __init__.py, AAA test markers, and 1:1:1 spec headers."""
    violations: list[str] = []
    for file_str in py_files:
        p = Path(file_str)
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        line_count = len(text.splitlines())
        if line_count >= _MAX_PYTHON_FILE_LINES:
            violations.append(
                f"{file_str}:1 [max-file-lines] File has {line_count} lines "
                f"(must be < {_MAX_PYTHON_FILE_LINES}; extract modules and 1:1 tests)"
            )
        norm = "/" + str(p).replace("\\", "/").lstrip("/")
        if "/alembic/versions/" in norm:
            violations.append(
                f"{file_str}:1 [zero-touch-migration] Never modify alembic/versions/*.py manually"
            )
        if p.name == "__init__.py":
            if ("/tests/" in norm or ("/src/" in norm and "_framework/" not in norm)) and text:
                violations.append(
                    f"{file_str}:1 [init-purity] Consumer src/**/__init__.py and "
                    "tests/**/__init__.py must remain 0 bytes"
                )
        elif p.name.startswith("test_") and "def test_" in text:
            blocks = _extract_test_blocks(text)
            missing_aaa = [
                m
                for m in ("# Arrange", "# Act", "# Assert")
                if any(not re.search(rf"(?m)^\s*{re.escape(m)}\b(?!\s*&)", b) for b in blocks)
            ]
            if missing_aaa:
                violations.append(
                    f"{file_str}:1 [missing-aaa] Test file missing {', '.join(missing_aaa)}"
                )
        elif "Specification: docs/architecture/" not in text:
            sib_spec = any(
                "Specification: docs/architecture/"
                in sib.read_text(encoding="utf-8", errors="ignore")
                for sib in p.parent.glob("*.py")
                if sib != p and sib.name != "__init__.py"
            )
            if sib_spec:
                violations.append(
                    f"{file_str}:1 [missing-spec-pointer] Module missing "
                    "'Specification: docs/architecture/<spec>.md' docstring header"
                )
    return violations


def check_universal_doc_structure(doc_files: list[str]) -> list[str]:
    """Enforce < 465-line file cap on root README.md and docs/corporate/**/*.md."""
    violations: list[str] = []
    for file_str in doc_files:
        p = Path(file_str)
        if not p.is_file():
            continue
        line_count = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        if line_count >= _MAX_PYTHON_FILE_LINES:
            violations.append(
                f"{file_str}:1 [max-doc-lines] Documentation file has {line_count} lines "
                f"(must be < {_MAX_PYTHON_FILE_LINES}; split into modular guides/specs)"
            )
    return violations


def check_rules_token_budget(
    workspace_paths: list[str], agents_md_path: Path | None = None
) -> list[str]:
    """Check if active always_on rules exceed token budget limits."""
    global_agents = agents_md_path or (Path(__file__).resolve().parent.parent / "AGENTS.md")
    total_bytes = 0
    warnings: list[str] = []
    if global_agents.is_file():
        agents_size = global_agents.stat().st_size
        total_bytes += agents_size
        if agents_size > _AGENTS_MD_MAX_BYTES:
            warnings.append(
                f"[TOKEN_BUDGET_EXCEEDED] {global_agents}: {agents_size} bytes "
                f"(exceeds {_AGENTS_MD_MAX_BYTES}-byte AGENTS.md cap)"
            )
    for ws in workspace_paths:
        rules_dir = Path(ws) / ".agents" / "rules"
        if rules_dir.is_dir():
            for rf in sorted(rules_dir.glob("*.md")):
                content = rf.read_text(encoding="utf-8", errors="ignore")
                if (
                    "trigger: model_decision"
                    not in content[:_MODEL_DECISION_FRONTMATTER_SCAN_CHARS]
                ):
                    total_bytes += len(content.encode("utf-8"))
    if total_bytes > _TOTAL_RULES_BUDGET_MAX_BYTES:
        est_tok = total_bytes // _CHARS_PER_TOKEN_ESTIMATE
        warnings.append(
            f"[WORKSPACE_RULES_BUDGET_EXCEEDED] Rules total {total_bytes} bytes (~{est_tok} tokens)"
        )
    return warnings


def find_ruff(workspace_paths: list[str]) -> str | None:
    """Find ruff in workspace virtualenvs or fall back to PATH."""
    for ws in workspace_paths:
        for venv_dir in _VENV_DIRS:
            venv_ruff = Path(ws) / venv_dir / "bin" / "ruff"
            if venv_ruff.exists():
                return str(venv_ruff)
    return shutil.which("ruff")


def get_changed_python_files(workspace_path: str) -> list[str]:
    """Return Python files with unstaged, staged, or untracked changes."""
    git_bin = shutil.which("git") or "git"
    files: set[str] = set()
    for cmd in (
        [git_bin, "diff", "--name-only", "--diff-filter=ACMR"],
        [git_bin, "diff", "--name-only", "--cached", "--diff-filter=ACMR"],
        [git_bin, "ls-files", "--others", "--exclude-standard", "--", "*.py"],
    ):
        with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError):
            res = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                cwd=workspace_path,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
            for raw_line in res.stdout.splitlines():
                rel = raw_line.strip()
                if rel.endswith(".py") and not rel.startswith("docs/"):
                    full = Path(workspace_path) / rel
                    if full.exists():
                        files.add(str(full))
    return sorted(files)


def get_changed_doc_files(workspace_path: str) -> list[str]:
    """Return root README.md and docs/corporate/**/*.md files with uncommitted changes."""
    git_bin = shutil.which("git") or "git"
    files: set[str] = set()
    doc_globs = ["README.md", "docs/", "corporate/"]
    untracked_globs = [
        "README.md",
        "docs/*.md",
        "docs/**/*.md",
        "corporate/*.md",
        "corporate/**/*.md",
    ]
    for cmd in (
        [git_bin, "diff", "--name-only", "--diff-filter=ACMR", "--", *doc_globs],
        [git_bin, "diff", "--name-only", "--cached", "--diff-filter=ACMR", "--", *doc_globs],
        [git_bin, "ls-files", "--others", "--exclude-standard", "--", *untracked_globs],
    ):
        with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError):
            res = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                cwd=workspace_path,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
            for raw_line in res.stdout.splitlines():
                rel = raw_line.strip()
                if rel == "README.md" or (
                    rel.startswith(("docs/", "corporate/")) and rel.endswith(".md")
                ):
                    full = Path(workspace_path) / rel
                    if full.exists():
                        files.add(str(full))
    return sorted(files)


def main() -> None:
    """Run ruff check and structural gates across modified workspace files."""
    payload = json.load(sys.stdin)
    raw_workspaces = [str(w) for w in payload.get("workspacePaths", [])]
    invocation_num = int(payload.get("invocationNum") or 0)
    workspace_paths = resolve_effective_workspaces(raw_workspaces)
    if not workspace_paths:
        json.dump({}, sys.stdout)
        return
    ruff = find_ruff(workspace_paths)
    all_lines: list[str] = check_rules_token_budget(workspace_paths)
    for ws in workspace_paths:
        all_lines.extend(check_universal_doc_structure(get_changed_doc_files(ws)))
        ws_files = get_changed_python_files(ws)
        if not ws_files:
            continue
        all_lines.extend(check_universal_python_structure(ws_files))
        ws_ruff = find_ruff([ws, *workspace_paths]) or ruff
        if ws_ruff is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                res = subprocess.run(
                    [ws_ruff, "check", "--no-fix", "--output-format=concise", *ws_files],
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=ws,
                    timeout=_RUFF_TIMEOUT_SECONDS,
                )
                if res.returncode != 0 and res.stdout.strip():
                    all_lines.extend(res.stdout.strip().splitlines())
    if not all_lines:
        json.dump({}, sys.stdout)
        return
    extra = len(all_lines) - _MAX_SUMMARY_LINES
    summary = (
        "\n".join(all_lines[:_MAX_SUMMARY_LINES]) + f"\n... ({extra} more)"
        if extra > 0
        else "\n".join(all_lines)
    )
    can_continue = invocation_num < _MAX_FORCE_CONTINUE_INVOCATIONS
    footer = (
        "Fix these before stopping."
        if can_continue
        else (
            f"Circuit breaker reached ({invocation_num}/{_MAX_FORCE_CONTINUE_INVOCATIONS} "
            "passes); resolve remaining issues before committing."
        )
    )
    response: dict[str, object] = {
        "injectSteps": [
            {
                "ephemeralMessage": (
                    f"Lint or structural issues detected in modified files:\n\n"
                    f"```\n{summary}\n```\n\n{footer}"
                )
            }
        ]
    }
    if can_continue:
        response["terminationBehavior"] = "force_continue"
    json.dump(response, sys.stdout)


if __name__ == "__main__":
    main()
