"""Unit tests for zcg.governance.workflows.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance import workflows


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    path = node_dir / NODE_MANIFEST_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestWorkflows:
    """Verify task-branch onboarding, upward completion receipts, and 1-hop child delegation."""

    def test_start_task_workflow_slugs_subtasks_and_guards_expected(self, tmp_path: Path) -> None:
        """Verify validation guards, ticket/slug derivation, subtasks, and SESSION.md updates."""
        # Arrange
        ws = tmp_path / "squad-iso"
        _write_manifest(ws, {"layer_id": "squad-iso", "layer_role": "squad"})

        # Act — guards & fallback slug
        assert workflows._derive_branch_slug("***") == "work-item"
        with pytest.raises(ValueError, match="task_query must be a non-empty"):
            workflows.start_task_workflow(ws, task_query=" ")
        with pytest.raises(ValueError, match="Invalid tracker"):
            workflows.start_task_workflow(ws, task_query="x", tracker="BAD.md")
        with pytest.raises(ValueError, match="Tracker file not found"):
            workflows.start_task_workflow(ws, task_query="x")

        (ws / "WORKTASK.md").write_text(
            "# Tasks\n"
            "- [ ] **[P0 · Delegated from `dept-iso` (department)]**: Telemetry gateway\n"
            "  - [ ] Subtask 1\n"
            "\n"
            "- [ ] **[EX-02]** Existing ticket task\n"
            "- [ ] Plain task without ticket\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="No task matching"):
            workflows.start_task_workflow(ws, task_query="nonexistent")

        dry_res = workflows.start_task_workflow(
            ws, task_query="Telemetry gateway", ticket_id="TEL-01", dry_run=True
        )
        assert dry_res["branch_name"] == "feature/TEL-01-p0-telemetry-gateway"
        assert dry_res["subtasks"] == ["- [ ] Subtask 1"]
        assert not (ws / ".agents/SESSION.md").exists()

        # Live claim three times (missing SESSION.md, existing ticket, and end-of-file task)
        first = workflows.start_task_workflow(
            ws, task_query="Telemetry gateway", ticket_id="TEL-01"
        )
        assert first["origin_layer_id"] == "dept-iso"
        ex_res = workflows.start_task_workflow(ws, task_query="Existing ticket")
        assert ex_res["ticket_id"] == "EX-02"

        second = workflows.start_task_workflow(ws, task_query="Plain task", branch_prefix="")
        assert second["branch_name"] == "feature/plain-task-without-ticket"
        # Assert
        assert (ws / ".agents/SESSION.md").read_text("utf-8").count("## Active Task") == 1

    def test_complete_task_workflow_direct_and_staged_parent_reporting_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify task completion, parent tracker updates, and non-destructive PR receipts."""
        # Arrange
        parent = tmp_path / "dept-iso"
        _write_manifest(
            parent,
            {
                "layer_id": "dept-iso",
                "layer_role": "department",
                "layer_authority": {"authorized_emails": ["owner@corp-iso.example"]},
            },
        )
        ws = tmp_path / "squad-iso"
        _write_manifest(
            ws,
            {
                "layer_id": "squad-iso",
                "layer_role": "squad",
                "upstream_layer": {"layer_id": "dept-iso"},
            },
        )

        # Act — guards
        with pytest.raises(ValueError, match="task_query must be a non-empty"):
            workflows.complete_task_workflow(ws, task_query="")
        with pytest.raises(ValueError, match="Invalid tracker"):
            workflows.complete_task_workflow(ws, task_query="x", tracker="NOPE.md")
        with pytest.raises(ValueError, match="Tracker file not found"):
            workflows.complete_task_workflow(ws, task_query="x")

        (ws / "WORKTASK.md").write_text(
            "# Tasks\n"
            "- [/] **[TEL-01 · Delegated from `dept-iso`]**: Build gateway\n"
            "- [/] Local item\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="No task matching"):
            workflows.complete_task_workflow(ws, task_query="missing")

        # 1. Dry-run without parent
        dry_local = workflows.complete_task_workflow(ws, task_query="Local item", dry_run=True)
        assert dry_local["parent_tracker_updated"] is False

        # 2. Authorized parent: first appends ## Outbound Delegations, second replaces in-place
        comp1 = workflows.complete_task_workflow(
            ws,
            task_query="TEL-01",
            deliverable="src/gw.py",
            parent_dir=parent,
            actor_email="owner@corp-iso.example",
        )
        assert comp1["parent_tracker_updated"] is True
        assert "## Outbound Delegations" in (parent / "WORKTASK.md").read_text("utf-8")

        comp2 = workflows.complete_task_workflow(
            ws,
            task_query="TEL-01",
            deliverable="src/gw.py",
            summary="Refined gateway",
            parent_dir=parent,
            actor_email="owner@corp-iso.example",
        )
        assert comp2["parent_tracker_updated"] is True
        assert "Refined gateway" in (parent / "WORKTASK.md").read_text("utf-8")

        # Dry-run with authorized parent skips disk write cleanly
        workflows.complete_task_workflow(
            ws,
            task_query="TEL-01",
            parent_dir=parent,
            actor_email="owner@corp-iso.example",
            dry_run=True,
        )

        # 3. Unauthorized actor or create_pr stages non-destructive receipt
        staged = workflows.complete_task_workflow(
            ws,
            task_query="Local item",
            parent_dir=parent,
            actor_email="dev@corp-iso.example",
            create_pr=True,
        )
        # Assert
        assert staged["staged_completion_receipt"] is not None

    def test_delegate_directive_to_child_across_surfaces_and_ownership_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 1-hop child delegation guards, rules/docs/tracker surfaces, and staging."""
        # Arrange
        org_group = tmp_path / "corp-iso-org"
        sib_dept = org_group / "dept-ext"
        _write_manifest(
            sib_dept,
            {
                "layer_id": "dept-ext",
                "layer_role": "department",
                "governing_root_id": "corp-iso",
                "layer_authority": {"authorized_emails": ["ext-owner@corp-iso.example"]},
            },
        )
        ws = tmp_path / "corp-iso"
        _write_manifest(
            ws,
            {
                "layer_id": "corp-iso",
                "layer_role": "corporate",
                "precedence": 10,
                "mounted_layers": [{"name": "dept-sub", "branch": "main"}],
                "layer_authority": {"authorized_emails": ["corp-owner@corp-iso.example"]},
            },
        )
        child = ws / "layers/dept-sub"
        _write_manifest(
            child,
            {
                "layer_id": "dept-sub",
                "layer_role": "department",
                "governing_root_id": "corp-iso",
            },
        )

        # Act — input & authority guards
        with pytest.raises(ValueError, match="Invalid child_layer"):
            workflows.delegate_directive_to_child(ws, child_layer="BAD_ID", directive="x")
        with pytest.raises(ValueError, match="Invalid priority"):
            workflows.delegate_directive_to_child(ws, child_layer="dept-sub", priority="P9")
        with pytest.raises(ValueError, match="Invalid tracker"):
            workflows.delegate_directive_to_child(ws, child_layer="dept-sub", tracker="bad")
        with pytest.raises(ValueError, match="Invalid or missing source_rel_path"):
            workflows.delegate_directive_to_child(
                ws, child_layer="dept-sub", source_rel_path="missing.md"
            )
        with pytest.raises(ValueError, match="directive must be a non-empty"):
            workflows.delegate_directive_to_child(ws, child_layer="dept-sub")
        with pytest.raises(ValueError, match="DELEGATION_AUTHORITY_DENIED"):
            workflows.delegate_directive_to_child(
                ws, child_layer="dept-sub", directive="x", actor_email="guest@corp-iso.example"
            )
        with pytest.raises(ValueError, match="Target 1-hop child layer not found"):
            workflows.delegate_directive_to_child(
                ws,
                child_layer="unknown-child",
                directive="x",
                actor_email="corp-owner@corp-iso.example",
            )

        # Cross-owner sibling child -> proposal staged + external git push command
        cross_res = workflows.delegate_directive_to_child(
            ws,
            child_layer="dept-ext",
            directive="Adopt audit [SEC-10]",
            actor_email="corp-owner@corp-iso.example",
        )
        assert cross_res["delivery_mode"] == "proposal_pr"
        assert "git push origin" in cross_res["subtree_push_command"]

        # Sibling owned by same actor on feature branch -> TARGET_BRANCH_GUARD
        _write_manifest(
            sib_dept,
            {
                "layer_id": "dept-ext",
                "layer_role": "department",
                "governing_root_id": "corp-iso",
                "layer_authority": {"authorized_emails": ["corp-owner@corp-iso.example"]},
            },
        )
        with patch(
            "zcg.governance.workflows.inspect_git_governance_state",
            return_value={"reconciliation_guard": {"on_trunk_branch": False}},
        ):
            guard_res = workflows.delegate_directive_to_child(
                ws,
                child_layer="dept-ext",
                directive="Branch guard check",
                actor_email="corp-owner@corp-iso.example",
            )
        assert len(guard_res["staged_proposals"]) == 1

        # Mounted child owned: rules (new -> existing staged), docs/guides (new -> existing staged),
        # and WORKTASK.md with source tracker file
        r1 = workflows.delegate_directive_to_child(
            ws,
            child_layer="dept-sub",
            directive="Rule body",
            tracker="rules",
            actor_email="corp-owner@corp-iso.example",
        )
        assert r1["delivery_mode"] == "direct_subtree"
        r2 = workflows.delegate_directive_to_child(
            ws,
            child_layer="dept-sub",
            directive="Rule conflict",
            tracker="rules",
            actor_email="corp-owner@corp-iso.example",
        )
        assert r2["delivery_mode"] == "proposal_pr"

        d1 = workflows.delegate_directive_to_child(
            ws,
            child_layer="dept-sub",
            directive="Guide body",
            tracker="docs",
            actor_email="corp-owner@corp-iso.example",
        )
        assert len(d1["updated_paths"]) == 1
        d2 = workflows.delegate_directive_to_child(
            ws,
            child_layer="dept-sub",
            directive="Guide conflict",
            tracker="docs",
            actor_email="corp-owner@corp-iso.example",
        )
        assert len(d2["staged_proposals"]) == 1

        (ws / "WORKROAD.md").write_text("# Road\n- [ ] Milestone A\n", encoding="utf-8")
        for _ in range(2):
            wt_deliv = workflows.delegate_directive_to_child(
                ws,
                child_layer="dept-sub",
                directive="Execute milestone",
                source_rel_path="WORKROAD.md",
                tracker="WORKTASK.md",
                actor_email="corp-owner@corp-iso.example",
            )
        assert "zcg subtree-push dept-sub main" in wt_deliv["subtree_push_command"]
        # Assert
        assert "Delivered to `dept-sub`" in (ws / "WORKROAD.md").read_text("utf-8")

        # Dry-run coverage across rules, docs, and WORKTASK.md
        for dry_trk in ("rules", "docs", "WORKTASK.md"):
            workflows.delegate_directive_to_child(
                ws,
                child_layer="dept-sub",
                directive="Dry run",
                source_rel_path="WORKROAD.md",
                tracker=dry_trk,
                force_overwrite=True,
                actor_email="corp-owner@corp-iso.example",
                dry_run=True,
            )
