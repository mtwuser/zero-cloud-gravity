"""Sovereign 3-Origin Knowledge Space, Ephemeral SQLite FTS5 Search & Guided .md Authoring.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import contextlib
import itertools
import sqlite3
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import VALID_KNOWLEDGE_PREFIXES
from zcg.core.manifests import (
    ensure_contained_path,
    load_node_manifest,
    strip_markdown_frontmatter,
)
from zcg.core.markdown_scan import parse_heading_line, tokenize_alnum
from zcg.governance.policy.mesh_relations import (
    resolve_exchange_target_dir,
    resolve_node_relation_grants,
)
from zcg.governance.workspace.links import resolve_linked_node_dir
from zcg.topology.identity import resolve_default_parent_dir

DOCS_FTS_DB_REL_PATH: Final[str] = ".zcg/runtime/docs_fts.sqlite3"
MAX_SOURCE_FILES: Final[int] = 60
MAX_DOC_LINES: Final[int] = 464
DEFAULT_SEARCH_LIMIT: Final[int] = 15
VALID_ORIGIN_GROUPS: Final[tuple[str, ...]] = ("all", "node", "network", "corpus")
VALID_DOC_VISIBILITIES: Final[tuple[str, ...]] = ("internal-r3", "network-r2", "public-r0")
_ROOT_DOC_NAMES: Final[tuple[str, ...]] = ("README.md", "CHANGELOG.md")

DOC_TEMPLATES: Final[dict[str, str]] = {
    "guide": (
        "---\nvisibility: internal-r3\nstatus: draft\n---\n\n"
        "# {title}\n\n## Purpose & Scope\n\nDescribe the operational objective and audience.\n\n"
        "## Procedure\n\n1. Step one.\n2. Step two.\n"
    ),
    "adr": (
        "---\nvisibility: network-r2\nstatus: draft\n---\n\n"
        "# ADR: {title}\n\n## Context\n\nState the problem and architectural constraints.\n\n"
        "## Decision\n\nDocument the selected option and rationale.\n\n"
        "## Consequences\n\nList downstream impacts and verification gates.\n"
    ),
    "note": (
        "---\nvisibility: internal-r3\nstatus: draft\n---\n\n"
        "# {title}\n\n## Key Takeaways\n\n- Primary observation.\n- Next action.\n"
    ),
}


def extract_doc_visibility(md_text: str) -> str:
    """Extract frontmatter visibility ('internal-r3' | 'network-r2' | 'public-r0')."""
    lines = md_text.splitlines()
    if lines and lines[0].strip() == "---":
        for ln in itertools.islice(lines, 1, 25):
            st = ln.strip()
            if st == "---":
                break
            key, sep, val = st.partition(":")
            if sep and key.strip().lower() == "visibility":
                cand = val.strip().strip("'\"").lower()
                if cand in VALID_DOC_VISIBILITIES:
                    return cand
    return "network-r2"


def list_workspace_markdown_files(root_dir: Path, *, include_private_r3: bool = True) -> list[str]:
    """List up to MAX_SOURCE_FILES relative Markdown paths under root_dir."""
    cands: list[str] = [nm for nm in _ROOT_DOC_NAMES if (root_dir / nm).is_file()]
    docs_dir = root_dir / "docs"
    if docs_dir.is_dir():
        for md_file in sorted(docs_dir.rglob("*.md")):
            cands.append(str(md_file.relative_to(root_dir)))
    if include_private_r3:
        return list(itertools.islice(cands, MAX_SOURCE_FILES))
    shared: list[str] = []
    for rel in cands:
        raw = (root_dir / rel).read_text(encoding="utf-8", errors="replace")
        if extract_doc_visibility(raw) != "internal-r3":
            shared.append(rel)
            if len(shared) >= MAX_SOURCE_FILES:
                break
    return shared


def _discover_1hop_child_dirs(ws: Path, own_id: str) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for parent_cand in (ws.parent, ws.parent / "Projects"):
        if not parent_cand.is_dir():
            continue
        for sub in sorted(parent_cand.iterdir()):
            if not sub.is_dir() or sub == ws or not (sub / "system/zcg-node.json").is_file():
                continue
            cm = load_node_manifest(sub)
            cid = str(cm.get("layer_id") or sub.name).strip()
            if str(cm.get("governing_root_id") or "").strip() == own_id and not cid.endswith(
                "-wallet"
            ):
                found.append((cid, sub))
    return found


def resolve_knowledge_space_sources(
    workspace_dir: Path, *, parent_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Discover readable Markdown sources grouped by ('node' | 'network' | 'corpus')."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    own_id = str(manifest.get("layer_id") or ws.name)
    sources: list[dict[str, Any]] = [
        {
            "source_id": "self",
            "label": f"{own_id} (This Node)",
            "kind": "node",
            "origin_group": "node",
            "root_dir": ws,
            "files": list_workspace_markdown_files(ws, include_private_r3=True),
        }
    ]
    seen_ids: set[str] = {"self", own_id}

    def _try_add(sid: str, label: str, kind: str, origin_group: str, cand_dir: Path | None) -> None:
        clean_id = sid.strip()
        if not clean_id or clean_id in seen_ids or cand_dir is None or not cand_dir.is_dir():
            return
        files = list_workspace_markdown_files(
            cand_dir, include_private_r3=(origin_group != "network")
        )
        if not files:
            return
        seen_ids.add(clean_id)
        sources.append(
            {
                "source_id": clean_id,
                "label": label,
                "kind": kind,
                "origin_group": origin_group,
                "root_dir": cand_dir.resolve(),
                "files": files,
            }
        )

    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    if eff_parent is not None and eff_parent != ws:
        pm = load_node_manifest(eff_parent)
        pid = str(pm.get("layer_id") or eff_parent.name)
        _try_add(pid, f"{pid} (Parent / Root 0)", "parent", "network", eff_parent)

    for cid, cdir in _discover_1hop_child_dirs(ws, own_id):
        _try_add(cid, f"{cid} (1-Hop Child)", "child", "network", cdir)

    layers_dir = ws / "layers"
    if layers_dir.is_dir():
        for sub in sorted(layers_dir.iterdir()):
            if sub.is_dir():
                _try_add(sub.name, f"{sub.name} (Mounted Layer)", "mounted", "network", sub)

    for grant in resolve_node_relation_grants(ws, parent_dir=parent_dir):
        if grant.relation_role == "governed-peer" and "consult_context" in grant.allowed_verbs:
            pdir = resolve_exchange_target_dir(ws, grant.target_node, parent_dir=parent_dir)
            _try_add(
                grant.target_node,
                f"{grant.target_node} (Governed Peer)",
                "peer",
                "network",
                pdir,
            )

    for mnt in (x for x in manifest.get("mounted_layers", []) if isinstance(x, dict)):
        mid = str(mnt.get("layer_id") or mnt.get("name") or "").strip()
        sib = (ws.parent / mid).resolve() if mid else None
        _try_add(mid, f"{mid} (Knowledge Corpus)", "corpus", "corpus", sib)

    for lnk in (x for x in manifest.get("linked_nodes", []) if isinstance(x, dict)):
        lid = str(lnk.get("node_id") or "").strip()
        lrole = str(lnk.get("layer_role") or "")
        lrel = str(lnk.get("relation") or "")
        is_corpus = (
            lrole == "knowledge"
            or lid.startswith(VALID_KNOWLEDGE_PREFIXES)
            or lrel.startswith("knowledge")
        )
        tdir = resolve_linked_node_dir(ws, lid)
        if is_corpus:
            _try_add(lid, f"{lid} (Linked Corpus)", "corpus", "corpus", tdir)
        elif not lid.endswith("-wallet"):
            _try_add(lid, f"{lid} (Linked Peer)", "peer", "network", tdir)
    return sources


def _extract_doc_title(md_text: str, fallback: str) -> str:
    for ln in strip_markdown_frontmatter(md_text).splitlines():
        if (hd := parse_heading_line(ln, max_level=3)) is not None:
            return hd.text
    return fallback


def search_knowledge_space(
    workspace_dir: Path,
    query: str,
    *,
    origin_filter: str = "all",
    parent_dir: Path | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, str]]:
    """Index readable Markdown sources into ephemeral SQLite FTS5 and return ranked matches."""
    tokens = tokenize_alnum(query.lower())
    if not tokens:
        return []
    fts_expr = " AND ".join(f'"{tok}"*' for tok in tokens)
    ws = workspace_dir.resolve()
    eff_origin = origin_filter.strip().lower() or "all"
    sources = resolve_knowledge_space_sources(ws, parent_dir=parent_dir)
    db_path = ws / DOCS_FTS_DB_REL_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    rows_to_index: list[tuple[str, str, str, str, str]] = []
    for src in sources:
        if (
            eff_origin != "all"
            and eff_origin in VALID_ORIGIN_GROUPS
            and src["origin_group"] != eff_origin
        ):
            continue
        rdir: Path = src["root_dir"]
        for rel_f in src["files"]:
            raw_txt = (rdir / rel_f).read_text(encoding="utf-8", errors="replace")
            title = _extract_doc_title(raw_txt, rel_f)
            rows_to_index.append(
                (
                    src["source_id"],
                    src["origin_group"],
                    rel_f,
                    title,
                    strip_markdown_frontmatter(raw_txt),
                )
            )

    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("DROP TABLE IF EXISTS docs_fts")
        conn.execute(
            "CREATE VIRTUAL TABLE docs_fts USING fts5("
            "source_id UNINDEXED, origin_group UNINDEXED, rel_path, title, body)"
        )
        conn.executemany("INSERT INTO docs_fts VALUES (?, ?, ?, ?, ?)", rows_to_index)
        cur = conn.execute(
            "SELECT source_id, origin_group, rel_path, title, "
            "snippet(docs_fts, 4, '[', ']', ' … ', 14) "
            "FROM docs_fts WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_expr, max(1, int(limit))),
        )
        hits = cur.fetchall()

    return [
        {
            "source_id": str(h[0]),
            "origin_group": str(h[1]),
            "doc": str(h[2]),
            "title": str(h[3]),
            "snippet": str(h[4]),
        }
        for h in hits
    ]


def render_doc_starter_template(template_kind: str, title: str) -> str:
    """Render a clean Markdown starter template ('guide' | 'adr' | 'note')."""
    clean_k = template_kind.strip().lower()
    tpl = DOC_TEMPLATES.get(clean_k, DOC_TEMPLATES["guide"])
    eff_title = title.strip() or "New Knowledge Document"
    return tpl.format(title=eff_title)


def save_knowledge_document(
    workspace_dir: Path,
    *,
    rel_path: str,
    content: str = "",
    template_kind: str = "guide",
    title: str = "",
) -> dict[str, Any]:
    """Validate path containment under docs/ and write a local Markdown knowledge document."""
    ws = workspace_dir.resolve()
    raw_rel = rel_path.strip().replace("\\", "/").lstrip("/")
    if not raw_rel:
        raise ValueError("UNSAFE_DOC_PATH: non-empty docs/<name>.md path is required")
    norm_rel = raw_rel if raw_rel.startswith("docs/") else f"docs/{raw_rel}"
    if not norm_rel.lower().endswith(".md"):
        norm_rel = f"{norm_rel}.md"
    docs_root = (ws / "docs").resolve()
    try:
        target = ensure_contained_path(ws / norm_rel, docs_root)
    except ValueError as exc:
        raise ValueError(f"UNSAFE_DOC_PATH: {exc}") from exc
    if any(part.startswith(".") for part in target.relative_to(docs_root).parts):
        raise ValueError("UNSAFE_DOC_PATH: hidden path segments are not allowed under docs/")

    eff_body = content if content.strip() else render_doc_starter_template(template_kind, title)
    final_txt = eff_body.rstrip() + "\n"
    line_cnt = len(final_txt.splitlines())
    if line_cnt > MAX_DOC_LINES:
        raise ValueError(
            f"DOC_LINE_BUDGET_EXCEEDED: {line_cnt} lines exceeds {MAX_DOC_LINES}-line maximum"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(final_txt, encoding="utf-8")
    rel_clean = str(target.relative_to(ws))
    return {
        "doc": rel_clean,
        "lines": line_cnt,
        "template_kind": template_kind if template_kind in DOC_TEMPLATES else "guide",
    }
