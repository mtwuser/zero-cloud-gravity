"""Headless WORKROAD.md, roadmaps/*.md, and WORKVALI.md section inspectors and checkbox mutator.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from zcg.core.markdown_scan import (
    iter_unfenced_lines,
    parse_checkbox_line,
    parse_heading_line,
    scan_markdown_checkboxes,
    scan_markdown_headings,
)

VALID_TOGGLE_TRACKERS: Final[tuple[str, ...]] = ("WORKVALI.md", "WORKROAD.md", "ROADMAP.md")
VALID_TOGGLE_STATES: Final[tuple[str, ...]] = (" ", "/", "x")
_STRIP_MD = str.maketrans("", "", "*_`~[]()")


def _norm_text(text: str) -> str:
    return text.translate(_STRIP_MD).strip().lower()


def parse_sectioned_checkboxes(markdown_text: str) -> list[dict[str, Any]]:
    """Group unfenced Markdown checkbox items under their nearest preceding ATX heading."""
    sections: list[dict[str, Any]] = []
    cur_heading = "General"
    cur_items: list[dict[str, str]] = []
    for lineno, raw_line in iter_unfenced_lines(markdown_text):
        hd = parse_heading_line(raw_line, lineno=lineno, max_level=3)
        if hd is not None:
            if cur_items:
                sections.append({"heading": cur_heading, "items": cur_items})
                cur_items = []
            cur_heading = hd.text
            continue
        chk = parse_checkbox_line(raw_line, lineno=lineno)
        if chk is not None:
            cur_items.append({"lineno": str(chk.lineno), "state": chk.state, "body": chk.body})
    if cur_items:
        sections.append({"heading": cur_heading, "items": cur_items})
    return sections


def inspect_roadmap_tracker(workspace_dir: Path) -> dict[str, Any]:
    """Inspect WORKROAD.md (or ROADMAP.md) milestones alongside roadmaps/*.md documents."""
    ws = workspace_dir.resolve()
    tracker_name = next((n for n in ("WORKROAD.md", "ROADMAP.md") if (ws / n).is_file()), "")
    raw_txt = (ws / tracker_name).read_text(encoding="utf-8") if tracker_name else ""
    sections = parse_sectioned_checkboxes(raw_txt) if raw_txt else []
    flat = [it for sec in sections for it in sec["items"]]
    open_n = sum(1 for x in flat if x["state"] == " ")
    prog_n = sum(1 for x in flat if x["state"] == "/")
    done_n = sum(1 for x in flat if x["state"] == "x")

    rm_dir = ws / "roadmaps"
    roadmap_docs: list[dict[str, Any]] = []
    if rm_dir.is_dir():
        for doc_p in sorted(rm_dir.glob("*.md")):
            doc_txt = doc_p.read_text(encoding="utf-8")
            hds = scan_markdown_headings(doc_txt, max_level=2)
            chks = scan_markdown_checkboxes(doc_txt)
            roadmap_docs.append(
                {
                    "rel_path": f"roadmaps/{doc_p.name}",
                    "title": hds[0].text if hds else doc_p.stem.replace("_", " ").title(),
                    "checkbox_count": len(chks),
                }
            )
    return {
        "has_tracker": bool(tracker_name),
        "tracker_file": tracker_name or "WORKROAD.md",
        "open_count": open_n,
        "in_progress_count": prog_n,
        "done_count": done_n,
        "total_count": len(flat),
        "sections": sections,
        "roadmap_docs": roadmap_docs,
    }


def inspect_validation_tracker(workspace_dir: Path) -> dict[str, Any]:
    """Inspect WORKVALI.md QA, mastery, and promotion sign-off checklists."""
    ws = workspace_dir.resolve()
    vali_path = ws / "WORKVALI.md"
    has_file = vali_path.is_file()
    raw_txt = vali_path.read_text(encoding="utf-8") if has_file else ""
    sections = parse_sectioned_checkboxes(raw_txt) if raw_txt else []
    flat = [it for sec in sections for it in sec["items"]]
    verified_n = sum(1 for x in flat if x["state"] == "x")
    pending_n = len(flat) - verified_n
    pct = round((100 * verified_n) / len(flat)) if flat else 0
    return {
        "has_tracker": has_file,
        "tracker_file": "WORKVALI.md",
        "pending_count": pending_n,
        "verified_count": verified_n,
        "total_count": len(flat),
        "completion_pct": pct,
        "sections": sections,
    }


def toggle_tracker_checkbox(
    workspace_dir: Path,
    *,
    tracker: str,
    task_query: str,
    target_state: str = "x",
) -> dict[str, Any]:
    """Update a checkbox state (' ', '/', or 'x') inside WORKVALI.md or WORKROAD.md."""
    clean_trk = tracker.strip()
    clean_q = _norm_text(task_query)
    clean_st = target_state if target_state == " " else target_state.strip().lower()
    if clean_trk not in VALID_TOGGLE_TRACKERS:
        raise ValueError(f"UNSUPPORTED_TOGGLE_TRACKER: {tracker!r} not in {VALID_TOGGLE_TRACKERS}")
    if not clean_q:
        raise ValueError("INVALID_TOGGLE_QUERY: task_query must be non-empty")
    if clean_st not in VALID_TOGGLE_STATES:
        raise ValueError(f"INVALID_TOGGLE_STATE: {target_state!r} not in {VALID_TOGGLE_STATES}")
    trk_path = workspace_dir.resolve() / clean_trk
    if not trk_path.is_file():
        raise ValueError(f"TRACKER_NOT_FOUND: {clean_trk} does not exist in workspace")
    raw_txt = trk_path.read_text(encoding="utf-8")
    lines = raw_txt.splitlines()
    matched = next(
        (
            chk
            for ln_no, raw_ln in iter_unfenced_lines(raw_txt)
            if (chk := parse_checkbox_line(raw_ln, lineno=ln_no)) is not None
            and clean_q in _norm_text(chk.body)
        ),
        None,
    )
    if matched is None:
        raise ValueError(f"TRACKER_ITEM_NOT_FOUND: no item matching {task_query!r} in {clean_trk}")
    lines[matched.lineno - 1] = matched.format_line(state=clean_st)
    trk_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        "action": "toggle",
        "tracker": clean_trk,
        "state": clean_st,
        "task": matched.body,
    }
