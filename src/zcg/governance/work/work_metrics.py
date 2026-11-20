"""Headless workspace work, knowledge, attachment vault, and Git sync hygiene metrics.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import NODE_MANIFEST_REL_PATH, VALID_KNOWLEDGE_PREFIXES
from zcg.core.manifests import load_node_manifest
from zcg.core.markdown_scan import scan_markdown_checkboxes
from zcg.governance.policy.mesh_relations import resolve_node_relation_grants
from zcg.governance.work.work_inbox import inspect_work_inbox
from zcg.governance.work.work_trackers import inspect_roadmap_tracker, inspect_validation_tracker
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_governance_posture

METRICS_CONTRACT_REV: Final[str] = "zcg-work-metrics-v1"
VALID_METRICS_SCOPES: Final[tuple[str, ...]] = ("all", "node", "network", "corpora")
_MAX_FRONTMATTER_LINES: Final[int] = 25
_VAULT_BLOBS_REL_PATH: Final[str] = ".agents/telemetry/vault_blobs"
_NODE_SCOPE_REL_PATH: Final[str] = "surfaces/data/node_scope.json"
_VALID_DOC_VISIBILITIES: Final[frozenset[str]] = frozenset(
    {"internal-r3", "network-r2", "public-r0"}
)


def _is_knowledge_manifest(node_id: str, manifest: dict[str, Any]) -> bool:
    role = str(manifest.get("layer_role") or "").strip().lower()
    return role == "knowledge" or node_id.startswith(VALID_KNOWLEDGE_PREFIXES)


def _extract_doc_visibility(md_text: str, *, is_readme: bool, is_knowledge: bool) -> str:
    lines = md_text.splitlines()
    if lines and lines[0].strip() == "---":
        for raw_ln in itertools.islice(lines, 1, _MAX_FRONTMATTER_LINES):
            clean = raw_ln.strip()
            if clean == "---":
                break
            key, sep, val = clean.partition(":")
            if sep and key.strip().lower() == "visibility":
                cand = val.strip().strip("'\"").lower()
                if cand in _VALID_DOC_VISIBILITIES:
                    return cand
    return "public-r0" if (is_readme or is_knowledge) else "network-r2"


def _scan_node_docs(node_dir: Path, *, is_knowledge: bool) -> dict[str, int]:
    r3_n, r2_n, r0_n = 0, 0, 0
    doc_files: list[tuple[Path, bool]] = []
    readme = node_dir / "README.md"
    if readme.is_file():
        doc_files.append((readme, True))
    docs_dir = node_dir / "docs"
    if docs_dir.is_dir():
        doc_files.extend((md_p, False) for md_p in sorted(docs_dir.rglob("*.md")))
    for md_path, is_readme in doc_files:
        vis = _extract_doc_visibility(
            md_path.read_text(encoding="utf-8", errors="replace"),
            is_readme=is_readme,
            is_knowledge=is_knowledge,
        )
        if vis == "internal-r3":
            r3_n += 1
        elif vis == "public-r0":
            r0_n += 1
        else:
            r2_n += 1
    return {
        "total_docs": r3_n + r2_n + r0_n,
        "r3_count": r3_n,
        "r2_count": r2_n,
        "r0_count": r0_n,
    }


def _scan_vault_blobs(node_dir: Path) -> dict[str, int]:
    v_dir = node_dir / _VAULT_BLOBS_REL_PATH
    if not v_dir.is_dir():
        return {"vault_files": 0, "vault_bytes": 0}
    files_n, total_b = 0, 0
    for item in sorted(v_dir.rglob("*")):
        if item.is_file() and item.suffix.lower() != ".json":
            files_n += 1
            total_b += item.stat().st_size
    return {"vault_files": files_n, "vault_bytes": total_b}


def _read_sync_safety(node_dir: Path) -> dict[str, int]:
    sc_path = node_dir / _NODE_SCOPE_REL_PATH
    if not sc_path.is_file():
        return {"git_dirty_count": 0, "git_ahead": 0, "git_behind": 0}
    try:
        raw = json.loads(sc_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"git_dirty_count": 0, "git_ahead": 0, "git_behind": 0}
    if not isinstance(raw, dict):
        return {"git_dirty_count": 0, "git_ahead": 0, "git_behind": 0}
    rep = raw.get("representation_context")
    nh = rep.get("node_health") if isinstance(rep, dict) else None
    dims = nh.get("dimensions") if isinstance(nh, dict) else None
    ss = dims.get("sync_safety") if isinstance(dims, dict) else None
    if not isinstance(ss, dict):
        return {"git_dirty_count": 0, "git_ahead": 0, "git_behind": 0}
    return {
        "git_dirty_count": int(ss.get("dirty", 0)),
        "git_ahead": int(ss.get("ahead", 0)),
        "git_behind": int(ss.get("behind", 0)),
    }


def _collect_single_node_metrics(node_dir: Path) -> dict[str, Any]:
    manifest = load_node_manifest(node_dir)
    node_id = str(manifest.get("layer_id") or node_dir.name)
    layer_role = str(manifest.get("layer_role") or "project")
    is_know = _is_knowledge_manifest(node_id, manifest)

    wt_path = node_dir / "WORKTASK.md"
    wt_items = (
        scan_markdown_checkboxes(wt_path.read_text(encoding="utf-8")) if wt_path.is_file() else []
    )
    todo_n = sum(1 for item in wt_items if item.state == " ")
    prog_n = sum(1 for item in wt_items if item.state == "/")
    done_n = sum(1 for item in wt_items if item.state == "x")
    tot_wt = todo_n + prog_n + done_n
    comp_pct = round((100 * done_n) / tot_wt) if tot_wt else 0

    bkl_path = node_dir / "BACKLOG.md"
    bkl_items = (
        scan_markdown_checkboxes(bkl_path.read_text(encoding="utf-8")) if bkl_path.is_file() else []
    )
    bkl_open = sum(1 for item in bkl_items if item.state == " ")

    road = inspect_roadmap_tracker(node_dir)
    vali = inspect_validation_tracker(node_dir)
    inbox = inspect_work_inbox(node_dir)

    return {
        "node_id": node_id,
        "layer_role": layer_role,
        "is_knowledge_node": is_know,
        "work": {
            "todo_count": todo_n,
            "in_progress_count": prog_n,
            "done_count": done_n,
            "total_count": tot_wt,
            "completion_pct": comp_pct,
            "backlog_open_count": bkl_open,
            "backlog_total_count": len(bkl_items),
            "roadmap_total_count": int(road["total_count"]),
            "roadmap_done_count": int(road["done_count"]),
            "validation_total_count": int(vali["total_count"]),
            "validation_verified_count": int(vali["verified_count"]),
            "inbox_pending_count": int(inbox["pending_count"]),
        },
        "knowledge": _scan_node_docs(node_dir, is_knowledge=is_know),
        "vault": _scan_vault_blobs(node_dir),
        "git_sync": _read_sync_safety(node_dir),
    }


def _discover_1hop_and_linked_nodes(
    ws: Path, own_manifest: dict[str, Any], *, parent_dir: Path | None
) -> list[tuple[Path, dict[str, Any]]]:
    seen: set[Path] = {ws}
    found: list[tuple[Path, dict[str, Any]]] = []

    def _consider(cand: Path) -> None:
        resolved = cand.resolve()
        if resolved in seen or not (resolved / NODE_MANIFEST_REL_PATH).is_file():
            return
        cm = load_node_manifest(resolved)
        if not resolve_governance_posture(resolved, cm)["allow_cross_workspace_1hop_read"]:
            return
        seen.add(resolved)
        found.append((resolved, cm))

    eff_parent = parent_dir.resolve() if parent_dir is not None else resolve_default_parent_dir(ws)
    if eff_parent is not None:
        _consider(eff_parent)

    layers_dir = ws / "layers"
    if layers_dir.is_dir():
        for child in sorted(layers_dir.iterdir()):
            if child.is_dir():
                _consider(child)

    own_id = str(own_manifest.get("layer_id") or ws.name)
    gov_id = str(own_manifest.get("governing_root_id") or "").strip()
    allowed_peers: set[str] = (
        {
            g.target_node
            for g in resolve_node_relation_grants(ws, parent_dir=parent_dir)
            if "consult_context" in g.allowed_verbs
        }
        if gov_id
        else set()
    )
    for sib in sorted(ws.parent.iterdir()):
        if not sib.is_dir() or not (sib / NODE_MANIFEST_REL_PATH).is_file():
            continue
        sm = load_node_manifest(sib)
        s_gov = str(sm.get("governing_root_id") or "").strip()
        s_id = str(sm.get("layer_id") or sib.name)
        if s_gov == own_id or (
            gov_id
            and s_gov == gov_id
            and (_is_knowledge_manifest(s_id, sm) or s_id in allowed_peers)
        ):
            _consider(sib)

    raw_links = own_manifest.get("linked_nodes")
    if isinstance(raw_links, list):
        for ref in raw_links:
            ref_s = (
                str(ref.get("path") or ref.get("local_path") or "").strip()
                if isinstance(ref, dict)
                else str(ref).strip()
            )
            if ref_s:
                cand_p = Path(ref_s)
                if cand_p.is_dir():
                    _consider(cand_p)

    return found


def _aggregate_nodes(nodes: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    todo_n = sum(int(n["work"]["todo_count"]) for n in nodes)
    prog_n = sum(int(n["work"]["in_progress_count"]) for n in nodes)
    done_n = sum(int(n["work"]["done_count"]) for n in nodes)
    tot_wt = todo_n + prog_n + done_n
    return {
        "work": {
            "todo_count": todo_n,
            "in_progress_count": prog_n,
            "done_count": done_n,
            "total_count": tot_wt,
            "completion_pct": round((100 * done_n) / tot_wt) if tot_wt else 0,
            "backlog_open_count": sum(int(n["work"]["backlog_open_count"]) for n in nodes),
            "backlog_total_count": sum(int(n["work"]["backlog_total_count"]) for n in nodes),
            "roadmap_total_count": sum(int(n["work"]["roadmap_total_count"]) for n in nodes),
            "roadmap_done_count": sum(int(n["work"]["roadmap_done_count"]) for n in nodes),
            "validation_total_count": sum(int(n["work"]["validation_total_count"]) for n in nodes),
            "validation_verified_count": sum(
                int(n["work"]["validation_verified_count"]) for n in nodes
            ),
            "inbox_pending_count": sum(int(n["work"]["inbox_pending_count"]) for n in nodes),
        },
        "knowledge": {
            "total_docs": sum(int(n["knowledge"]["total_docs"]) for n in nodes),
            "r3_count": sum(int(n["knowledge"]["r3_count"]) for n in nodes),
            "r2_count": sum(int(n["knowledge"]["r2_count"]) for n in nodes),
            "r0_count": sum(int(n["knowledge"]["r0_count"]) for n in nodes),
        },
        "vault": {
            "vault_files": sum(int(n["vault"]["vault_files"]) for n in nodes),
            "vault_bytes": sum(int(n["vault"]["vault_bytes"]) for n in nodes),
        },
        "git_sync": {
            "git_dirty_count": sum(int(n["git_sync"]["git_dirty_count"]) for n in nodes),
            "git_ahead": sum(int(n["git_sync"]["git_ahead"]) for n in nodes),
            "git_behind": sum(int(n["git_sync"]["git_behind"]) for n in nodes),
        },
    }


def collect_workspace_metrics(
    workspace_dir: Path,
    *,
    scope: str = "node",
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Collect pure-filesystem work, knowledge, vault, and Git sync metrics across a scope."""
    clean_scope = scope.strip().lower()
    eff_scope = clean_scope if clean_scope in VALID_METRICS_SCOPES else "node"
    ws = workspace_dir.resolve()
    own_m = load_node_manifest(ws)

    if eff_scope == "node":
        target_dirs = [ws]
    else:
        peers = _discover_1hop_and_linked_nodes(ws, own_m, parent_dir=parent_dir)
        non_know = [
            d
            for d, cm in peers
            if not _is_knowledge_manifest(str(cm.get("layer_id") or d.name), cm)
        ]
        corpora = [
            d for d, cm in peers if _is_knowledge_manifest(str(cm.get("layer_id") or d.name), cm)
        ]
        if eff_scope == "corpora":
            target_dirs = corpora
        elif eff_scope == "all":
            target_dirs = [ws, *non_know, *corpora]
        else:
            target_dirs = [ws, *non_know]

    nodes = [_collect_single_node_metrics(d) for d in target_dirs]
    agg = _aggregate_nodes(nodes)
    return {
        "contract_rev": METRICS_CONTRACT_REV,
        "scope": eff_scope,
        "node_id": str(own_m.get("layer_id") or ws.name),
        "node_count": len(nodes),
        "work": agg["work"],
        "knowledge": agg["knowledge"],
        "vault": agg["vault"],
        "git_sync": agg["git_sync"],
        "nodes": nodes,
    }
