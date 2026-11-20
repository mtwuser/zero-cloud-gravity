"""Sovereign Kanban task metadata, Backlog->To Do promotion, and cross-node Work Inbox.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from zcg.core.domain import generate_identifier, is_kebab_id
from zcg.core.manifests import load_node_manifest
from zcg.core.markdown_scan import iter_unfenced_lines, parse_checkbox_line
from zcg.governance.policy.authority import append_tracker_line

WORK_INBOX_REL_PATH: Final[str] = ".zcg/runtime/ledger/work_inbox.jsonl"
WORK_INBOX_DECISIONS_REL_PATH: Final[str] = ".zcg/runtime/ledger/work_inbox_decisions.jsonl"
VALID_TASK_PRIORITIES: Final[tuple[str, ...]] = ("P0", "P1", "P2", "P3")
VALID_SCOPE_FILTERS: Final[tuple[str, ...]] = ("all", "own", "parent", "cross-node")
VALID_INBOX_DECISIONS: Final[tuple[str, ...]] = ("accept-todo", "accept-backlog", "decline")
VALID_INBOX_DIRECTIONS: Final[tuple[str, ...]] = ("parent", "child", "peer")
_TRACK_PREFIXES: Final[tuple[str, ...]] = (
    "venture/",
    "specialty/",
    "engagement/",
    "opportunity/",
    "feature/",
    "context/",
)
_REQ_ID_CHARS: Final[int] = 8
_INLINE_PUNCT = str.maketrans("", "", "*_`~[]()")


def _strip_md(text: str) -> str:
    return text.translate(_INLINE_PUNCT)


def classify_task_metadata(body: str) -> dict[str, str]:
    """Extract deterministic priority, relational scope, and track from a Markdown task body."""
    low = body.lower()
    upper_tokens = {t.strip(".,:;!") for t in _strip_md(body).upper().split()}
    prio = next((p for p in VALID_TASK_PRIORITIES if p in upper_tokens), "P2")
    if "delegated from" in low or "origin_ref:" in low:
        scope = "parent" if "delegated from" in low else "cross-node"
    elif " -> `" in body or " -> " in body:
        scope = "cross-node"
    else:
        scope = "own"
    clean_words = (w.strip("`'\"()[],.:;*") for w in body.split())
    track = next((w for w in clean_words if w.startswith(_TRACK_PREFIXES)), "main")
    return {"priority": prio, "scope": scope, "track": track, "sprint_id": ""}


def _matches_scope_filter(item_scope: str, scope_filter: str) -> bool:
    if scope_filter == "node":
        return item_scope == "own"
    if scope_filter == "network":
        return item_scope in ("parent", "cross-node")
    if scope_filter != "all" and scope_filter in VALID_SCOPE_FILTERS:
        return item_scope == scope_filter
    return True


def filter_kanban_items(
    items: Sequence[Mapping[str, str]],
    *,
    scope_filter: str = "all",
    priority_filter: str = "all",
    query_filter: str = "",
) -> list[dict[str, str]]:
    """Enrich and filter Kanban/Backlog items across scope, priority, and track/query."""
    eff_scope = scope_filter.strip().lower() or "all"
    eff_prio = priority_filter.strip().upper() or "ALL"
    eff_q = query_filter.strip().lower()
    matched: list[dict[str, str]] = []
    for raw in items:
        body = str(raw.get("body") or "")
        meta = classify_task_metadata(body)
        if not _matches_scope_filter(meta["scope"], eff_scope):
            continue
        if eff_prio != "ALL" and eff_prio in VALID_TASK_PRIORITIES and meta["priority"] != eff_prio:
            continue
        if eff_q and eff_q not in body.lower() and eff_q not in meta["track"].lower():
            continue
        matched.append({**{str(k): str(v) for k, v in raw.items()}, **meta})
    return matched


def promote_backlog_item_to_todo(workspace_dir: Path, *, task_query: str) -> dict[str, Any]:
    """Promote an unchecked item from BACKLOG.md into the To Do column of WORKTASK.md."""
    clean_q = task_query.strip()
    if not clean_q:
        raise ValueError("INVALID_PROMOTE_QUERY: task_query must be non-empty")
    ws = workspace_dir.resolve()
    bkl_path = ws / "BACKLOG.md"
    if not bkl_path.is_file():
        raise ValueError("BACKLOG_NOT_FOUND: BACKLOG.md does not exist in workspace")
    raw_bkl = bkl_path.read_text(encoding="utf-8")
    lines = raw_bkl.splitlines()
    norm_q = _strip_md(clean_q).lower()
    match_item = next(
        (
            chk
            for ln_no, line in iter_unfenced_lines(raw_bkl)
            if (chk := parse_checkbox_line(line, lineno=ln_no)) is not None
            and chk.state == " "
            and norm_q in _strip_md(line).lower()
        ),
        None,
    )
    if match_item is None:
        raise ValueError(f"BACKLOG_ITEM_NOT_FOUND: no open item matching {clean_q!r} in BACKLOG.md")
    rm_idx = match_item.lineno - 1
    kept = [ln for idx, ln in enumerate(lines) if idx != rm_idx]
    bkl_path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    lid = str(load_node_manifest(ws).get("layer_id") or ws.name)
    append_tracker_line(ws, "WORKTASK.md", f"- [ ] {match_item.body}", lid)
    return {
        "action": "promote",
        "promoted_task": match_item.body,
        "source_tracker": "BACKLOG.md",
        "target_tracker": "WORKTASK.md",
    }


def _read_jsonl_dicts(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    out: list[dict[str, str]] = []
    for raw_ln in path.read_text(encoding="utf-8").splitlines():
        clean = raw_ln.strip()
        if not clean:
            continue
        try:
            parsed = json.loads(clean)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            out.append({str(k): str(v) for k, v in parsed.items()})
    return out


def enqueue_work_inbox_request(
    receiver_dir: Path,
    *,
    sender_node: str,
    summary: str,
    direction: str = "peer",
    priority: str = "P1",
    origin_ref: str = "",
) -> dict[str, str]:
    """Append an incoming cross-node work request into .zcg/runtime/ledger/work_inbox.jsonl."""
    clean_sender = sender_node.strip()
    clean_sum = summary.strip()
    clean_dir = direction.strip().lower() or "peer"
    clean_prio = priority.strip().upper() or "P1"
    if not is_kebab_id(clean_sender) or not clean_sum:
        raise ValueError("INVALID_WORK_REQUEST: valid sender_node and non-empty summary required")
    if clean_dir not in VALID_INBOX_DIRECTIONS:
        clean_dir = "peer"
    if clean_prio not in VALID_TASK_PRIORITIES:
        clean_prio = "P1"
    short_id = "".join(itertools.islice(generate_identifier(), _REQ_ID_CHARS))
    entry = {
        "request_id": f"wreq-{short_id}",
        "timestamp": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sender_node": clean_sender,
        "direction": clean_dir,
        "priority": clean_prio,
        "summary": clean_sum,
        "origin_ref": origin_ref.strip() or f"{clean_sender}#wreq-{short_id}",
    }
    inbox_path = receiver_dir.resolve() / WORK_INBOX_REL_PATH
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    with inbox_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {**entry, "status": "pending"}


def inspect_work_inbox(workspace_dir: Path) -> dict[str, Any]:
    """Inspect pending and triaged cross-node work requests for a sovereign node."""
    ws = workspace_dir.resolve()
    decisions = {
        d["request_id"]: d["decision"]
        for d in _read_jsonl_dicts(ws / WORK_INBOX_DECISIONS_REL_PATH)
        if d.get("request_id") and d.get("decision")
    }
    items: list[dict[str, str]] = []
    for req in _read_jsonl_dicts(ws / WORK_INBOX_REL_PATH):
        rid = req.get("request_id", "")
        if not rid or not req.get("sender_node"):
            continue
        status = decisions.get(rid, "pending")
        items.append({**req, "status": status})
    items.sort(key=lambda x: (0 if x["status"] == "pending" else 1, x.get("timestamp", "")))
    pending_n = sum(1 for x in items if x["status"] == "pending")
    return {"pending_count": pending_n, "total_count": len(items), "items": items}


def triage_work_inbox_request(
    workspace_dir: Path, *, request_id: str, decision: str
) -> dict[str, Any]:
    """Accept an incoming work request into WORKTASK.md or BACKLOG.md, or decline cleanly."""
    clean_id = request_id.strip()
    clean_dec = decision.strip().lower()
    if clean_dec not in VALID_INBOX_DECISIONS:
        raise ValueError(f"INVALID_INBOX_DECISION: decision must be one of {VALID_INBOX_DECISIONS}")
    ws = workspace_dir.resolve()
    inbox = inspect_work_inbox(ws)
    target = next((it for it in inbox["items"] if it["request_id"] == clean_id), None)
    if target is None:
        raise ValueError(f"WORK_REQUEST_NOT_FOUND: unknown request_id {request_id!r}")
    if target["status"] != "pending":
        raise ValueError(f"WORK_REQUEST_ALREADY_TRIAGED: {clean_id!r} is {target['status']!r}")

    target_tracker = ""
    if clean_dec in ("accept-todo", "accept-backlog"):
        target_tracker = "WORKTASK.md" if clean_dec == "accept-todo" else "BACKLOG.md"
        lid = str(load_node_manifest(ws).get("layer_id") or ws.name)
        line = (
            f"- [ ] **[{target['priority']}]** {target['summary']} "
            f"*(origin_ref: `{target['origin_ref']}`)*"
        )
        append_tracker_line(ws, target_tracker, line, lid)

    dec_entry = {
        "request_id": clean_id,
        "decision": clean_dec,
        "timestamp": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    dec_path = ws / WORK_INBOX_DECISIONS_REL_PATH
    dec_path.parent.mkdir(parents=True, exist_ok=True)
    with dec_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dec_entry, ensure_ascii=False) + "\n")
    return {
        "request_id": clean_id,
        "decision": clean_dec,
        "target_tracker": target_tracker,
        "sender_node": target["sender_node"],
    }
