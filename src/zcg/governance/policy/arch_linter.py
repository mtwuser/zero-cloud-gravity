"""Executable AST Hexagonal Boundary, Package DAG, and 1:1:1 AAA Test Enforcer ('zcg lint-arch').

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import ast
import itertools
import json
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance.policy.model_currency import check_model_currency_policy

DOMAIN_FILENAMES: Final[frozenset[str]] = frozenset({"models.py", "entities.py", "service.py"})
INFRA_MODULE_SEGMENTS: Final[frozenset[str]] = frozenset({
    "infrastructure", "adapters", "router", "repository",
    "sqlite_repo", "asgi", "server", "dependencies",
})  # fmt: skip
FORBIDDEN_DOMAIN_IO_PACKAGES: Final[frozenset[str]] = frozenset({
    "sqlite3", "subprocess", "socket", "http", "urllib", "asyncio", "shutil",
    "tempfile", "webbrowser", "sqlalchemy", "starlette", "httpx", "aiohttp",
    "requests", "redis", "psycopg", "asyncpg", "uvicorn", "alembic",
})  # fmt: skip
FORBIDDEN_UNIT_DB_FIXTURES = frozenset({"db_session", "db_engine", "sqlite_conn", "sqlite_session"})
SKIP_SCAN_DIRS: Final[frozenset[str]] = frozenset({
    ".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"
})  # fmt: skip
RETIRED_STACK_DIRS: Final[frozenset[str]] = frozenset({"framework-stack"})
FORBIDDEN_SINGLE_FILE_ROOT_DIRS: Final[frozenset[str]] = frozenset({"mk"})
MAX_PACKAGE_MODULE_FANOUT: Final[int] = 10
NON_EXEC_SCRIPT_MIME_TYPES: Final[frozenset[str]] = frozenset({
    "application/json", "application/ld+json", "importmap", "speculationrules"
})  # fmt: skip
ALLOWED_REGEX_MODULES: Final[frozenset[str]] = frozenset()


class _InlineScriptDetector(HTMLParser):
    """HTML5 parser detecting executable inline script elements lacking an external src."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._open_exec_line: int | None = None
        self.violation_lines: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        attr_map = {k: (v or "").strip() for k, v in attrs}
        script_type = attr_map.get("type", "").lower().partition(";")[0].strip()
        if not attr_map.get("src") and script_type not in NON_EXEC_SCRIPT_MIME_TYPES:
            self._open_exec_line = self.getpos()[0]

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._open_exec_line is not None:
            self.violation_lines.append(self._open_exec_line)
            self._open_exec_line = None


def _find_inline_script_lines(markup: str) -> list[int]:
    if "<script" not in (low := markup.lower()) or "</script>" not in low:
        return []
    detector = _InlineScriptDetector()
    detector.feed(markup)
    return detector.violation_lines


@dataclass(frozen=True, slots=True)
class BoundaryViolation:
    """Single AST architectural or 1:1:1 test contract violation."""

    file: str
    line: int
    symbol: str
    rule: str

    def to_dict(self) -> dict[str, object]:
        """Serialize violation to a JSON-compatible dictionary."""
        return {"file": self.file, "line": self.line, "symbol": self.symbol, "rule": self.rule}


def _should_skip_path(path: Path) -> bool:
    return any(part in SKIP_SCAN_DIRS for part in path.parts)


def _iter_py_files(root_dir: Path) -> list[Path]:
    return [f for f in sorted(root_dir.rglob("*.py")) if not _should_skip_path(f)]


def _parse_py_ast(py_file: Path) -> ast.AST | None:
    try:
        return ast.parse(py_file.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def _extract_runtime_imports(tree: ast.AST) -> list[tuple[int, str]]:
    tc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and (
            (isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING")
            or (isinstance(node.test, ast.Attribute) and node.test.attr == "TYPE_CHECKING")
        ):
            tc_lines.update(
                c.lineno for c in ast.walk(node) if isinstance(c, (ast.Import, ast.ImportFrom))
            )
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and node.lineno not in tc_lines:
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.lineno not in tc_lines:
            imports.append((node.lineno, node.module))
    return imports


def check_domain_module(file_path: Path) -> list[BoundaryViolation]:
    """Audit a single Python file for Hexagonal Functional Core boundary violations."""
    is_dom = file_path.name in DOMAIN_FILENAMES or "domain" in file_path.parts
    if not file_path.is_file() or file_path.suffix != ".py" or not is_dom:
        return []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [BoundaryViolation(str(file_path), exc.lineno or 1, file_path.name, "syntax-error")]
    violations: list[BoundaryViolation] = []
    for lineno, mod_name in _extract_runtime_imports(tree):
        if INFRA_MODULE_SEGMENTS.intersection(mod_name.split(".")):
            rule = "domain-imports-infrastructure"
        elif mod_name.split(".", maxsplit=1)[0] in FORBIDDEN_DOMAIN_IO_PACKAGES:
            rule = "domain-imports-io-package"
        else:
            continue
        violations.append(BoundaryViolation(str(file_path), lineno, mod_name, rule))
    return violations


def _check_regex_allowlist(py_file: Path, src_root: Path, tree: ast.AST) -> list[BoundaryViolation]:
    mod_id = ".".join(py_file.relative_to(src_root).with_suffix("").parts)
    if not mod_id.startswith("zcg."):
        return []
    return [
        BoundaryViolation(str(py_file), ln, mod, "allowed-regex-modules")
        for ln, mod in _extract_runtime_imports(tree)
        if mod == "re" or mod.startswith("re.")
    ]


def _check_empty_init_files(scan_roots: tuple[Path, ...]) -> list[BoundaryViolation]:
    return [
        BoundaryViolation(str(init_f), 1, "__init__.py", "non-empty-init-file")
        for sroot in (r for r in scan_roots if r.is_dir())
        for init_f in sorted(sroot.rglob("__init__.py"))
        if not _should_skip_path(init_f) and init_f.read_text(encoding="utf-8").strip()
    ]


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
            prefix = candidate_dir.parent.relative_to(src_root).parts
            plen = len(prefix)
            for py_f in _iter_py_files(candidate_dir):
                if (tree := _parse_py_ast(py_f)) is None:
                    continue
                for ln, mod in _extract_runtime_imports(tree):
                    parts = tuple(mod.split("."))
                    if len(parts) > plen and parts[:plen] == prefix and parts[plen] in blocked_set:
                        violations.append(
                            BoundaryViolation(str(py_f), ln, mod, "excluded-context-import")
                        )
    return violations


def _check_package_dir_dag(pkg_parent: Path, src_root: Path) -> list[BoundaryViolation]:
    subpkgs = sorted(
        d.name
        for d in pkg_parent.iterdir()
        if d.is_dir() and not _should_skip_path(d) and not d.name.startswith(".")
    )
    if len(subpkgs) < 2:
        return []
    pkg_set, prefix = frozenset(subpkgs), pkg_parent.relative_to(src_root).parts
    plen = len(prefix)
    graph: dict[str, set[str]] = {name: set() for name in subpkgs}
    edges: dict[tuple[str, str], tuple[str, int, str]] = {}
    for pkg in subpkgs:
        for py_f in _iter_py_files(pkg_parent / pkg):
            if (tree := _parse_py_ast(py_f)) is None:
                continue
            for lineno, mod_name in _extract_runtime_imports(tree):
                parts = tuple(mod_name.split("."))
                if len(parts) > plen and parts[:plen] == prefix:
                    dep = parts[plen]
                    if dep in pkg_set and dep != pkg:
                        graph[pkg].add(dep)
                        edges.setdefault((pkg, dep), (str(py_f), lineno, mod_name))
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        chain = list(reversed(exc.args[1]))
        fpath, ln, mod = edges[(chain[0], chain[1])]
        lbl = f"{' -> '.join(chain)} ({mod})"
        return [BoundaryViolation(fpath, ln, lbl, "cyclic-package-dependency")]
    return []


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
    fn_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for tf in sorted(tests_dir.rglob("test_*.py")):
        if _should_skip_path(tf):
            continue
        rel_parts = tf.relative_to(tests_dir).parts
        if len(rel_parts) == 1:
            violations.append(BoundaryViolation(str(tf), 1, tf.name, "flat-test-file"))
        elif rel_parts[0] == "unit" and source_root is not None:
            u_par = tf.relative_to(tests_dir / "unit").parent
            if not (source_root / u_par / f"{tf.stem.removeprefix('test_')}.py").is_file():
                violations.append(BoundaryViolation(str(tf), 1, tf.name, "orphan-test-file"))
        src_txt = tf.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src_txt)
        except SyntaxError as exc:
            violations.append(BoundaryViolation(str(tf), exc.lineno or 1, tf.name, "syntax-error"))
            continue
        t_cls = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name.startswith("Test")]
        if len(t_cls) != 1:
            ln, msg = (t_cls[1].lineno if len(t_cls) > 1 else 1), f"{len(t_cls)} Test* classes"
            violations.append(BoundaryViolation(str(tf), ln, msg, "one-test-class-per-file"))
        lines, is_unit = src_txt.splitlines(), "unit" in rel_parts
        t_fns = (
            n for n in ast.walk(tree) if isinstance(n, fn_types) and n.name.startswith("test_")
        )
        for node in t_fns:
            if is_unit:
                violations.extend(
                    BoundaryViolation(str(tf), node.lineno, a.arg, "db-fixture-in-unit-test")
                    for a in node.args.args if a.arg in FORBIDDEN_UNIT_DB_FIXTURES
                )  # fmt: skip
            if not _has_aaa_markers(lines, node.lineno, node.end_lineno or node.lineno):
                rule = "missing-aaa-comments"
                violations.append(BoundaryViolation(str(tf), node.lineno, node.name, rule))
    return violations


def _check_workspace_hygiene(root: Path, src_root: Path) -> list[BoundaryViolation]:
    tpl = root / "templates"
    violations = [
        BoundaryViolation(str(root / d), 1, d, "single-file-root-sprawl")
        for d in sorted(FORBIDDEN_SINGLE_FILE_ROOT_DIRS) if (root / d).is_dir()
    ]  # fmt: skip
    if tpl.is_dir():
        violations.extend(
            BoundaryViolation(str(tpl / r), 1, r, "retired-stack-directory")
            for r in sorted(RETIRED_STACK_DIRS) if (tpl / r).is_dir()
        )  # fmt: skip
    add = violations.append
    for pkg in sorted(d for d in src_root.rglob("*") if d.is_dir() and not _should_skip_path(d)):
        n_mods = sum(1 for f in pkg.glob("*.py") if f.name != "__init__.py")
        if n_mods > MAX_PACKAGE_MODULE_FANOUT:
            add(BoundaryViolation(str(pkg), 1, f"{n_mods} modules", "flat-package-fanout"))
        has_sub = any((sd / "__init__.py").is_file() for sd in pkg.iterdir() if sd.is_dir())
        if has_sub and (n_mods > 1 or (len(pkg.relative_to(src_root).parts) >= 2 and n_mods > 0)):
            add(BoundaryViolation(str(pkg), 1, f"{n_mods} flat + subpkgs", "mixed-package-depth"))
    violations.extend(BoundaryViolation(*v) for v in check_model_currency_policy(root))
    return violations


def _check_fragment_inline_scripts(root: Path, src_root: Path) -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    scopes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for py_f in _iter_py_files(src_root):
        if "tests" in py_f.relative_to(root).parts or (tree := _parse_py_ast(py_f)) is None:
            continue
        skip_ids = {
            id(s.body[0].value)
            for s in ast.walk(tree)
            if isinstance(s, scopes) and s.body and isinstance(s.body[0], ast.Expr)
        }
        cands: list[tuple[int, str]] = []
        for n in ast.walk(tree):
            if isinstance(n, ast.JoinedStr):
                skip_ids.update(id(v) for v in n.values)
                txt = "".join(
                    v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}"
                    for v in n.values
                )
                cands.append((n.lineno, txt))
        cands.extend(
            (n.lineno, n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip_ids
        )
        violations.extend(
            BoundaryViolation(str(py_f), ln, "<script>", "fragment-inline-script")
            for ln, txt in sorted(cands) if _find_inline_script_lines(txt)
        )  # fmt: skip
    for pat in (
        "src/**/assets/templates/**/*.html",
        "templates/**/web/templates/**/*.html",
        "surfaces/web/templates/**/*.html",
    ):
        for hf in sorted(root.glob(pat)):
            if not _should_skip_path(hf):
                violations.extend(
                    BoundaryViolation(str(hf), ln, "<script>", "fragment-inline-script")
                    for ln in _find_inline_script_lines(hf.read_text(encoding="utf-8"))
                )
    return violations


def lint_architecture(target_dir: Path, *, check_tests: bool = True) -> dict[str, Any]:
    """Run full Hexagonal AST boundary, acyclic DAG, 0-byte __init__.py, and 1:1:1 test audit."""
    root = target_dir.resolve()
    has_src = (root / "src").is_dir()
    src_root = root / "src" if has_src else root
    violations = _check_workspace_hygiene(root, src_root)
    violations.extend(_check_fragment_inline_scripts(root, src_root))
    for dp in (
        src_root,
        *(d for d in sorted(src_root.iterdir()) if d.is_dir() and not _should_skip_path(d)),
    ):
        violations.extend(_check_package_dir_dag(dp, src_root))
    for py_file in _iter_py_files(src_root):
        violations.extend(check_domain_module(py_file))
        if (tree := _parse_py_ast(py_file)) is not None:
            violations.extend(_check_regex_allowlist(py_file, src_root, tree))
    init_roots = (root / "src", root / "tests") if has_src else (root,)
    violations.extend(_check_empty_init_files(init_roots))
    if exc_map := _load_excluded_contexts(root):
        violations.extend(_check_excluded_contexts(src_root, exc_map))
    if check_tests and (t_dir := root / "tests").is_dir():
        violations.extend(check_test_suite(t_dir, source_root=src_root if has_src else None))
    return {
        "target_dir": str(root), "passed": len(violations) == 0,
        "violation_count": len(violations), "violations": [v.to_dict() for v in violations],
    }  # fmt: skip
