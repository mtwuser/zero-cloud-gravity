"""Executable AST Hexagonal Boundary and 1:1:1 AAA Test Enforcer ('zcg lint-arch').

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import ast
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import NODE_MANIFEST_REL_PATH

DOMAIN_FILENAMES: Final[frozenset[str]] = frozenset({"models.py", "entities.py", "service.py"})
INFRA_MODULE_SEGMENTS: Final[frozenset[str]] = frozenset(
    {
        "infrastructure",
        "adapters",
        "router",
        "repository",
        "sqlite_repo",
        "asgi",
        "server",
        "dependencies",
    }
)
FORBIDDEN_DOMAIN_IO_PACKAGES: Final[frozenset[str]] = frozenset(
    {
        "sqlite3",
        "subprocess",
        "socket",
        "http",
        "urllib",
        "asyncio",
        "shutil",
        "tempfile",
        "webbrowser",
        "sqlalchemy",
        "starlette",
        "httpx",
        "aiohttp",
        "requests",
        "redis",
        "psycopg",
        "asyncpg",
        "uvicorn",
        "alembic",
    }
)
FORBIDDEN_UNIT_DB_FIXTURES: Final[frozenset[str]] = frozenset(
    {"db_session", "db_engine", "sqlite_conn", "sqlite_session"}
)
SKIP_SCAN_DIRS: Final[frozenset[str]] = frozenset(
    {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
)


@dataclass(frozen=True, slots=True)
class BoundaryViolation:
    """Single AST architectural or 1:1:1 test contract violation."""

    file: str
    line: int
    symbol: str
    rule: str

    def to_dict(self) -> dict[str, object]:
        """Serialize violation to a JSON-compatible dictionary."""
        return {
            "file": self.file,
            "line": self.line,
            "symbol": self.symbol,
            "rule": self.rule,
        }


def _should_skip_path(path: Path) -> bool:
    return any(part in SKIP_SCAN_DIRS for part in path.parts)


def _is_domain_file(path: Path) -> bool:
    return path.name in DOMAIN_FILENAMES or "domain" in path.parts


def _is_type_checking_guard(test: ast.expr) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _extract_runtime_imports(tree: ast.AST) -> list[tuple[int, str]]:
    tc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_guard(node.test):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    tc_lines.add(child.lineno)
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and node.lineno not in tc_lines:
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module and node.lineno not in tc_lines:
            imports.append((node.lineno, node.module))
    return imports


def _is_infra_import(module_name: str) -> bool:
    return bool(INFRA_MODULE_SEGMENTS.intersection(module_name.split(".")))


def _is_forbidden_io_import(module_name: str) -> bool:
    root_pkg = module_name.split(".", maxsplit=1)[0]
    return root_pkg in FORBIDDEN_DOMAIN_IO_PACKAGES


def check_domain_module(file_path: Path) -> list[BoundaryViolation]:
    """Audit a single Python file for Hexagonal Functional Core boundary violations."""
    if not file_path.is_file() or file_path.suffix != ".py" or not _is_domain_file(file_path):
        return []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [BoundaryViolation(str(file_path), exc.lineno or 1, file_path.name, "syntax-error")]
    violations: list[BoundaryViolation] = []
    for lineno, mod_name in _extract_runtime_imports(tree):
        if _is_infra_import(mod_name):
            violations.append(
                BoundaryViolation(str(file_path), lineno, mod_name, "domain-imports-infrastructure")
            )
        elif _is_forbidden_io_import(mod_name):
            violations.append(
                BoundaryViolation(str(file_path), lineno, mod_name, "domain-imports-io-package")
            )
    return violations


def _check_empty_init_files(scan_roots: tuple[Path, ...]) -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    for sroot in scan_roots:
        if not sroot.is_dir():
            continue
        for init_f in sorted(sroot.rglob("__init__.py")):
            if _should_skip_path(init_f):
                continue
            if init_f.read_text(encoding="utf-8").strip():
                violations.append(
                    BoundaryViolation(str(init_f), 1, "__init__.py", "non-empty-init-file")
                )
    return violations


def _load_excluded_contexts(project_root: Path) -> dict[str, frozenset[str]]:
    manifest_path = project_root / NODE_MANIFEST_REL_PATH
    if not manifest_path.is_file():
        return {}
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    exc_map = raw.get("excluded_contexts") if isinstance(raw, dict) else None
    if not isinstance(exc_map, dict):
        return {}
    return {
        str(ctx): frozenset(str(x) for x in blocked if str(x))
        for ctx, blocked in exc_map.items()
        if isinstance(blocked, list) and blocked
    }


def _check_excluded_contexts(
    src_root: Path, excluded_map: dict[str, frozenset[str]]
) -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    for ctx_name, blocked_set in excluded_map.items():
        for candidate_dir in sorted(src_root.rglob(ctx_name)):
            if not candidate_dir.is_dir() or _should_skip_path(candidate_dir):
                continue
            for py_f in sorted(candidate_dir.rglob("*.py")):
                if _should_skip_path(py_f):
                    continue
                try:
                    tree = ast.parse(py_f.read_text(encoding="utf-8"))
                except SyntaxError:
                    continue
                for lineno, mod_name in _extract_runtime_imports(tree):
                    if blocked_set.intersection(mod_name.split(".")):
                        violations.append(
                            BoundaryViolation(
                                str(py_f), lineno, mod_name, "excluded-context-import"
                            )
                        )
    return violations


def _has_aaa_markers(lines: list[str], start_line: int, end_line: int) -> bool:
    span = itertools.islice(lines, max(0, start_line - 1), end_line)
    comments = " ".join(ln.split("#", maxsplit=1)[1] for ln in span if "#" in ln)
    return "Act" in comments and "Assert" in comments


def check_test_suite(
    tests_dir: Path, *, source_root: Path | None = None
) -> list[BoundaryViolation]:
    """Audit tests/ for flat/orphan files, 1 Test* class/file, DB fixtures, and AAA markers."""
    if not tests_dir.is_dir():
        return []
    violations: list[BoundaryViolation] = []
    for tf in sorted(tests_dir.rglob("test_*.py")):
        if _should_skip_path(tf):
            continue
        rel_parts = tf.relative_to(tests_dir).parts
        if len(rel_parts) == 1:
            violations.append(BoundaryViolation(str(tf), 1, tf.name, "flat-test-file"))
        elif rel_parts[0] == "unit" and source_root is not None:
            unit_rel = tf.relative_to(tests_dir / "unit")
            stem = tf.stem.removeprefix("test_")
            if not (source_root / unit_rel.parent / f"{stem}.py").is_file():
                violations.append(BoundaryViolation(str(tf), 1, tf.name, "orphan-test-file"))
        src_txt = tf.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src_txt)
        except SyntaxError as exc:
            violations.append(BoundaryViolation(str(tf), exc.lineno or 1, tf.name, "syntax-error"))
            continue
        t_classes = [
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name.startswith("Test")
        ]
        if len(t_classes) != 1:
            ln = t_classes[1].lineno if len(t_classes) > 1 else 1
            violations.append(
                BoundaryViolation(
                    str(tf), ln, f"{len(t_classes)} Test* classes", "one-test-class-per-file"
                )
            )
        lines = src_txt.splitlines()
        is_unit = "unit" in rel_parts
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            if is_unit:
                for arg in node.args.args:
                    if arg.arg in FORBIDDEN_UNIT_DB_FIXTURES:
                        violations.append(
                            BoundaryViolation(
                                str(tf), node.lineno, arg.arg, "db-fixture-in-unit-test"
                            )
                        )
            if not _has_aaa_markers(lines, node.lineno, node.end_lineno or node.lineno):
                violations.append(
                    BoundaryViolation(str(tf), node.lineno, node.name, "missing-aaa-comments")
                )
    return violations


def lint_architecture(target_dir: Path, *, check_tests: bool = True) -> dict[str, Any]:
    """Run full Hexagonal AST boundary, 0-byte __init__.py, and 1:1:1 test suite audit."""
    root = target_dir.resolve()
    has_src = (root / "src").is_dir()
    src_root = root / "src" if has_src else root
    violations: list[BoundaryViolation] = []
    for py_file in sorted(src_root.rglob("*.py")):
        if not _should_skip_path(py_file):
            violations.extend(check_domain_module(py_file))
    init_roots = (root / "src", root / "tests") if has_src else (root,)
    violations.extend(_check_empty_init_files(init_roots))
    if exc_map := _load_excluded_contexts(root):
        violations.extend(_check_excluded_contexts(src_root, exc_map))
    if check_tests and (root / "tests").is_dir():
        violations.extend(
            check_test_suite(root / "tests", source_root=src_root if has_src else None)
        )
    return {
        "target_dir": str(root),
        "passed": len(violations) == 0,
        "violation_count": len(violations),
        "violations": [v.to_dict() for v in violations],
    }
