"""Unit tests for zcg.governance.work.work_trackers.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from zcg.governance.work import work_trackers

if TYPE_CHECKING:
    from pathlib import Path


class TestWorkTrackers:
    """Verify headless WORKROAD.md, roadmaps/*.md, and WORKVALI.md inspection and mutations."""

    def test_inspect_roadmap_and_validation_trackers_across_populated_and_empty_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify section grouping, counts, roadmaps/*.md discovery, and empty fallbacks."""
        # Arrange
        empty_ws = tmp_path / "empty-node"
        empty_ws.mkdir()
        rich_ws = tmp_path / "rich-node"
        (rich_ws / "roadmaps").mkdir(parents=True)
        (rich_ws / "WORKROAD.md").write_text(
            "# Node Roadmap\n\n"
            "- [ ] Top-level item\n\n"
            "## Empty Heading\n\n"
            "## Phase 1\n"
            "- [x] Foundation complete\n"
            "- [/] Active milestone\n",
            encoding="utf-8",
        )
        (rich_ws / "roadmaps/v1_plan.md").write_text(
            "# Horizon Plan v1\n\n- [x] Step 1\n", encoding="utf-8"
        )
        (rich_ws / "roadmaps/no_heading.md").write_text("Plain roadmap text.\n", encoding="utf-8")
        (rich_ws / "WORKVALI.md").write_text(
            "## Smoke Checks\n- [x] Healthz 200\n- [ ] Visual layout\n",
            encoding="utf-8",
        )

        # Act
        empty_sec = work_trackers.parse_sectioned_checkboxes("# Heading With Zero Checkboxes\n")
        empty_rm = work_trackers.inspect_roadmap_tracker(empty_ws)
        empty_vl = work_trackers.inspect_validation_tracker(empty_ws)
        rich_rm = work_trackers.inspect_roadmap_tracker(rich_ws)
        rich_vl = work_trackers.inspect_validation_tracker(rich_ws)

        # Assert
        assert empty_sec == []
        assert empty_rm["has_tracker"] is False and empty_rm["total_count"] == 0
        assert empty_vl["has_tracker"] is False and empty_vl["completion_pct"] == 0
        assert rich_rm["has_tracker"] is True and rich_rm["tracker_file"] == "WORKROAD.md"
        assert (
            rich_rm["open_count"],
            rich_rm["in_progress_count"],
            rich_rm["done_count"],
        ) == (1, 1, 1)
        assert [s["heading"] for s in rich_rm["sections"]] == ["Node Roadmap", "Phase 1"]
        assert len(rich_rm["roadmap_docs"]) == 2
        assert rich_rm["roadmap_docs"][0]["title"] == "No Heading"
        assert rich_rm["roadmap_docs"][1]["title"] == "Horizon Plan v1"
        assert rich_vl["verified_count"] == 1 and rich_vl["pending_count"] == 1
        assert rich_vl["completion_pct"] == 50

    def test_toggle_tracker_checkbox_nominal_and_bipolar_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify checkbox toggling in WORKVALI.md/WORKROAD.md and deterministic ValueErrors."""
        # Arrange
        ws = tmp_path / "vali-node"
        ws.mkdir()
        (ws / "WORKVALI.md").write_text(
            "## Verification\n- [ ] **V1**: Check header crumb\n", encoding="utf-8"
        )

        # Act
        done_res = work_trackers.toggle_tracker_checkbox(
            ws, tracker="WORKVALI.md", task_query="V1", target_state="x"
        )
        after_done = (ws / "WORKVALI.md").read_text(encoding="utf-8")
        reopen_res = work_trackers.toggle_tracker_checkbox(
            ws, tracker="WORKVALI.md", task_query="Check header", target_state=" "
        )
        after_reopen = (ws / "WORKVALI.md").read_text(encoding="utf-8")

        # Assert
        assert done_res["state"] == "x" and "- [x] **V1**: Check header crumb" in after_done
        assert reopen_res["state"] == " " and "- [ ] **V1**: Check header crumb" in after_reopen
        with pytest.raises(ValueError, match="UNSUPPORTED_TOGGLE_TRACKER"):
            work_trackers.toggle_tracker_checkbox(ws, tracker="WORKTASK.md", task_query="V1")
        with pytest.raises(ValueError, match="INVALID_TOGGLE_QUERY"):
            work_trackers.toggle_tracker_checkbox(ws, tracker="WORKVALI.md", task_query="   ")
        with pytest.raises(ValueError, match="INVALID_TOGGLE_STATE"):
            work_trackers.toggle_tracker_checkbox(
                ws, tracker="WORKVALI.md", task_query="V1", target_state="z"
            )
        with pytest.raises(ValueError, match="TRACKER_NOT_FOUND"):
            work_trackers.toggle_tracker_checkbox(ws, tracker="WORKROAD.md", task_query="V1")
        with pytest.raises(ValueError, match="TRACKER_ITEM_NOT_FOUND"):
            work_trackers.toggle_tracker_checkbox(ws, tracker="WORKVALI.md", task_query="missing")
