"""Zero-LLM stdlib AST codebase graph, 1:1:1 citation links, and M_cluster mass analyzer.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import ast
from collections import deque
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any, Final

from zcg.core.manifests import ensure_contained_path

AST_GRAPH_CONTRACT_REV: Final[str] = "zcg-ast-graph-v1"
CLUSTER_MODULE_MIN_LINES: Final[int] = 380
M_CLUSTER_WARN_LINES: Final[int] = 1200
SPEC_HEADER_PREFIX: Final[str] = "Specification:"


def _extract_spec_target(source_text: str) -> str:
    for raw_line in source_text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith(SPEC_HEADER_PREFIX):
            return stripped.removeprefix(SPEC_HEADER_PREFIX).strip()
    return ""


def _resolve_unit_test_rel_path(ws: Path, src_dir: Path, py_file: Path) -> str:
    rel_mod = py_file.relative_to(src_dir)
    candidate = ws / "tests" / "unit" / rel_mod.parent / f"test_{py_file.stem}.py"
    return candidate.relative_to(ws).as_posix() if candidate.is_file() else ""


def _match_known_module(dotted: str, known_modules: set[str]) -> str:
    cand = dotted.strip(".")
    while cand:
        if cand in known_modules:
            return cand
        cand, _, _ = cand.rpartition(".")
    return ""


def _resolve_relative_base(module_id: str, level: int, sub_module: str | None) -> str:
    anchor = module_id
    for _ in range(level):
        anchor, _, _ = anchor.rpartition(".")
    if sub_module:
        return f"{anchor}.{sub_module}" if anchor else sub_module
    return anchor


def _extract_ast_metadata(
    source_text: str, module_id: str, known_modules: set[str]
) -> tuple[bool, list[str], list[str], list[str]]:
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return False, [], [], []

    classes: list[str] = []
    functions: list[str] = []
    for top in tree.body:
        if isinstance(top, ast.ClassDef) and not top.name.startswith("_"):
            classes.append(top.name)
        elif isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)) and not top.name.startswith(
            "_"
        ):
            functions.append(top.name)

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                matched = _match_known_module(alias.name, known_modules)
                if matched and matched != module_id:
                    imports.add(matched)
        elif isinstance(node, ast.ImportFrom):
            base = (
                _resolve_relative_base(module_id, node.level, node.module)
                if node.level > 0
                else (node.module or "")
            )
            matched_base = _match_known_module(base, known_modules)
            if matched_base and matched_base != module_id:
                imports.add(matched_base)
            for alias in node.names:
                cand = f"{base}.{alias.name}" if base else alias.name
                matched_sub = _match_known_module(cand, known_modules)
                if matched_sub and matched_sub != module_id:
                    imports.add(matched_sub)

    return True, sorted(classes), sorted(functions), sorted(imports)


def _compute_m_clusters(
    line_counts: dict[str, int], mod_imports: dict[str, list[str]]
) -> list[dict[str, Any]]:
    heavy = {m for m, lc in line_counts.items() if lc >= CLUSTER_MODULE_MIN_LINES}
    adj: dict[str, set[str]] = {m: set() for m in heavy}
    for src, targets in mod_imports.items():
        if src not in heavy:
            continue
        for dst in targets:
            if dst in heavy:
                adj[src].add(dst)
                adj[dst].add(src)

    visited: set[str] = set()
    clusters: list[dict[str, Any]] = []
    for start in sorted(heavy):
        if start in visited:
            continue
        comp: list[str] = []
        queue: deque[str] = deque([start])
        visited.add(start)
        while queue:
            curr = queue.popleft()
            comp.append(curr)
            for nxt in sorted(adj[curr]):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        if len(comp) >= 2:
            members = sorted(comp)
            total = sum(line_counts[m] for m in members)
            clusters.append(
                {
                    "modules": members,
                    "module_count": len(members),
                    "total_lines": total,
                    "warn_exceeded": total >= M_CLUSTER_WARN_LINES,
                }
            )
    return clusters


def build_codebase_ast_graph(workspace_dir: Path, *, src_rel_dir: str = "src") -> dict[str, Any]:
    """Build a deterministic zero-LLM stdlib AST module, citation, and M_cluster graph."""
    ws = workspace_dir.resolve()
    src_dir = ensure_contained_path(ws / src_rel_dir, ws)
    if not src_dir.is_dir():
        return {
            "contract_rev": AST_GRAPH_CONTRACT_REV,
            "src_rel_dir": src_rel_dir,
            "module_count": 0,
            "package_count": 0,
            "edge_count": 0,
            "has_cycle": False,
            "cycle_nodes": [],
            "topological_order": [],
            "packages": [],
            "modules": [],
            "edges": [],
            "m_clusters": [],
        }

    py_files = sorted(p for p in src_dir.rglob("*.py") if p.name != "__init__.py")
    file_by_mod: dict[str, Path] = {}
    for pf in py_files:
        mod_id = pf.relative_to(src_dir).with_suffix("").as_posix().replace("/", ".")
        file_by_mod[mod_id] = pf

    known_modules = set(file_by_mod)
    line_counts: dict[str, int] = {}
    mod_imports: dict[str, list[str]] = {}
    pkg_modules: dict[str, list[str]] = {}
    pkg_deps: dict[str, set[str]] = {}
    modules_out: list[dict[str, Any]] = []
    edges_out: list[dict[str, str]] = []

    for mod_id, pf in file_by_mod.items():
        text = pf.read_text(encoding="utf-8")
        lc = len(text.splitlines())
        line_counts[mod_id] = lc
        pkg_id = mod_id.rpartition(".")[0] or mod_id
        pkg_modules.setdefault(pkg_id, []).append(mod_id)
        pkg_deps.setdefault(pkg_id, set())

        spec_target = _extract_spec_target(text)
        unit_rel = _resolve_unit_test_rel_path(ws, src_dir, pf)
        parse_ok, classes, functions, imports = _extract_ast_metadata(text, mod_id, known_modules)
        mod_imports[mod_id] = imports

        for imp in imports:
            edges_out.append(
                {"source": mod_id, "target": imp, "kind": "EXTRACTED", "relation": "imports"}
            )
            imp_pkg = imp.rpartition(".")[0] or imp
            pkg_deps.setdefault(imp_pkg, set())
            if imp_pkg != pkg_id:
                pkg_deps[pkg_id].add(imp_pkg)
        if spec_target:
            edges_out.append(
                {
                    "source": mod_id,
                    "target": spec_target,
                    "kind": "CITED",
                    "relation": "spec-link",
                }
            )
        if unit_rel:
            edges_out.append(
                {
                    "source": mod_id,
                    "target": unit_rel,
                    "kind": "CITED",
                    "relation": "unit-test-link",
                }
            )

        modules_out.append(
            {
                "module_id": mod_id,
                "package_id": pkg_id,
                "rel_path": pf.relative_to(ws).as_posix(),
                "line_count": lc,
                "parse_ok": parse_ok,
                "spec_target": spec_target,
                "unit_test_path": unit_rel,
                "classes": classes,
                "functions": functions,
                "imports": imports,
            }
        )

    packages_out = [
        {
            "package_id": pkg,
            "module_count": len(mods),
            "total_lines": sum(line_counts[m] for m in mods),
            "depends_on": sorted(pkg_deps.get(pkg, set())),
        }
        for pkg, mods in sorted(pkg_modules.items())
    ]

    try:
        topo_order = list(TopologicalSorter(pkg_deps).static_order())
        has_cycle, cycle_nodes = False, list[str]()
    except CycleError as exc:
        has_cycle = True
        topo_order = []
        cycle_nodes = [str(n) for n in exc.args[1]]

    return {
        "contract_rev": AST_GRAPH_CONTRACT_REV,
        "src_rel_dir": src_rel_dir,
        "module_count": len(modules_out),
        "package_count": len(packages_out),
        "edge_count": len(edges_out),
        "has_cycle": has_cycle,
        "cycle_nodes": cycle_nodes,
        "topological_order": topo_order,
        "packages": packages_out,
        "modules": modules_out,
        "edges": edges_out,
        "m_clusters": _compute_m_clusters(line_counts, mod_imports),
    }
