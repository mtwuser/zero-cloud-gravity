"""Unit tests for zcg.governance.work.work_inbox.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from zcg.governance.work.work_inbox import (
    WORK_INBOX_REL_PATH,
    classify_task_metadata,
    enqueue_work_inbox_request,
    filter_kanban_items,
    inspect_work_inbox,
    promote_backlog_item_to_todo,
    triage_work_inbox_request,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestWorkInbox:
    """1:1 unit suite for Kanban metadata filters, Backlog promotion, and Work Inbox triage."""

    def test_classify_and_filter_kanban_items_across_scope_priority_and_track_expected(
        self,
    ) -> None:
        """Verify priority/scope/track extraction and deterministic multi-axis Kanban filtering."""
        # Arrange
        items = [
            {
                "tracker": "WORKTASK.md",
                "state": " ",
                "body": "**[P0 · T1 · Delegated from `corp-root`]** Ship `venture/alpha`",
            },
            {
                "tracker": "WORKTASK.md",
                "state": "/",
                "body": "**[P1]** Audit API *(origin_ref: `dept-sec#wreq-1234`)*",
            },
            {
                "tracker": "WORKTASK.md",
                "state": " ",
                "body": "**[T2 -> `dept-ops`]** Coordinate rollout",
            },
            {
                "tracker": "BACKLOG.md",
                "state": " ",
                "body": "Explore future cache options",
            },
        ]

        # Act
        meta_parent = classify_task_metadata(items[0]["body"])
        meta_origin = classify_task_metadata(items[1]["body"])
        meta_arrow = classify_task_metadata(items[2]["body"])
        meta_own = classify_task_metadata(items[3]["body"])
        only_parent = filter_kanban_items(items, scope_filter="parent")
        only_node = filter_kanban_items(items, scope_filter="node")
        only_network = filter_kanban_items(items, scope_filter="network")
        unknown_scope = filter_kanban_items(items, scope_filter="custom-other")
        only_p1 = filter_kanban_items(items, priority_filter="p1")
        only_track = filter_kanban_items(items, query_filter="venture/alpha")
        all_items = filter_kanban_items(items)

        # Assert
        assert meta_parent == {
            "priority": "P0",
            "scope": "parent",
            "track": "venture/alpha",
            "sprint_id": "",
        }
        assert meta_origin["scope"] == "cross-node" and meta_origin["priority"] == "P1"
        assert meta_arrow["scope"] == "cross-node"
        assert meta_own["scope"] == "own" and meta_own["priority"] == "P2"
        assert len(only_parent) == 1 and len(only_p1) == 1 and len(only_track) == 1
        assert len(only_node) == 1 and only_node[0]["scope"] == "own"
        assert len(only_network) == 3 and all(
            x["scope"] in ("parent", "cross-node") for x in only_network
        )
        assert len(unknown_scope) == 4 and len(all_items) == 4

    def test_promote_backlog_item_to_todo_and_error_guards_expected(self, tmp_path: Path) -> None:
        """Verify 1-click Backlog->To Do promotion and blank/missing/completed error guards."""
        # Arrange
        ws = tmp_path / "node-k"
        ws.mkdir()
        with pytest.raises(ValueError, match="INVALID_PROMOTE_QUERY"):
            promote_backlog_item_to_todo(ws, task_query="   ")
        with pytest.raises(ValueError, match="BACKLOG_NOT_FOUND"):
            promote_backlog_item_to_todo(ws, task_query="BKL-001")

        (ws / "BACKLOG.md").write_text(
            "# Backlog\n\n- [x] **[BKL-000]** Done item\n- [ ] **[BKL-001]** Build FTS5 index\n",
            encoding="utf-8",
        )

        # Act
        res = promote_backlog_item_to_todo(ws, task_query="BKL-001")

        # Assert
        assert res["action"] == "promote" and "BKL-001" in res["promoted_task"]
        assert "BKL-001" not in (ws / "BACKLOG.md").read_text(encoding="utf-8")
        assert "- [ ] **[BKL-001]** Build FTS5 index" in (ws / "WORKTASK.md").read_text("utf-8")
        with pytest.raises(ValueError, match="BACKLOG_ITEM_NOT_FOUND"):
            promote_backlog_item_to_todo(ws, task_query="BKL-000")

    def test_work_inbox_enqueue_inspect_triage_and_bipolar_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify .zcg/runtime/ledger/work_inbox.jsonl enqueue, triage, and malformed resilience."""
        # Arrange
        ws = tmp_path / "dept-eng"
        ws.mkdir()
        assert inspect_work_inbox(ws) == {"pending_count": 0, "total_count": 0, "items": []}

        # Act
        r1 = enqueue_work_inbox_request(
            ws, sender_node="corp-root", summary="Deliver API spec", direction="bad", priority="bad"
        )
        r2 = enqueue_work_inbox_request(
            ws, sender_node="dept-sec", summary="Add rate limit", direction="peer", priority="P0"
        )
        r3 = enqueue_work_inbox_request(ws, sender_node="dept-ops", summary="Optional note")
        raw_p = ws / WORK_INBOX_REL_PATH
        with raw_p.open("a", encoding="utf-8") as fh:
            fh.write('\nnot-json\n[1, 2]\n{"missing_id": 1}\n')

        t_todo = triage_work_inbox_request(ws, request_id=r1["request_id"], decision="accept-todo")
        t_bkl = triage_work_inbox_request(
            ws, request_id=r2["request_id"], decision="accept-backlog"
        )
        t_dec = triage_work_inbox_request(ws, request_id=r3["request_id"], decision="decline")
        snap = inspect_work_inbox(ws)

        # Assert
        assert r1["direction"] == "peer" and r1["priority"] == "P1"
        assert t_todo["target_tracker"] == "WORKTASK.md"
        assert t_bkl["target_tracker"] == "BACKLOG.md"
        assert t_dec["target_tracker"] == ""
        assert "origin_ref: `corp-root#" in (ws / "WORKTASK.md").read_text(encoding="utf-8")
        assert "origin_ref: `dept-sec#" in (ws / "BACKLOG.md").read_text(encoding="utf-8")
        assert not (ws / ".agents/proposals").exists()
        assert snap["pending_count"] == 0 and snap["total_count"] == 3

        with pytest.raises(ValueError, match="INVALID_WORK_REQUEST"):
            enqueue_work_inbox_request(ws, sender_node="BAD_ID", summary="")
        with pytest.raises(ValueError, match="INVALID_INBOX_DECISION"):
            triage_work_inbox_request(ws, request_id=r1["request_id"], decision="invalid")
        with pytest.raises(ValueError, match="WORK_REQUEST_NOT_FOUND"):
            triage_work_inbox_request(ws, request_id="wreq-missing", decision="decline")
        with pytest.raises(ValueError, match="WORK_REQUEST_ALREADY_TRIAGED"):
            triage_work_inbox_request(ws, request_id=r1["request_id"], decision="decline")
