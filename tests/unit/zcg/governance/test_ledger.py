"""Unit tests for zcg.governance.ledger.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import NODE_MANIFEST_CONTRACT_REV, NODE_MANIFEST_REL_PATH
from zcg.governance import ledger


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    path = node_dir / NODE_MANIFEST_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestLedger:
    """Verify Git branch policy, RBAC roster, branch state, decisions, and work ledger."""

    def test_configure_git_governance_policy_and_roster_management_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify individual/enterprise Git policies, CODEOWNERS sync, and RBAC roster CRUD."""
        # Arrange
        ws = tmp_path / "node-iso"
        ws.mkdir()

        # Act — validation guards
        with pytest.raises(ValueError, match="Missing node manifest"):
            ledger.configure_git_governance_policy(ws)
        with pytest.raises(ValueError, match="Missing node manifest"):
            ledger.manage_layer_roster(ws)

        _write_manifest(
            ws,
            {
                "schema_version": NODE_MANIFEST_CONTRACT_REV,
                "layer_id": "node-iso",
                "layer_role": "department",
                "entity_kind": "individual",
                "precedence": 88,
            },
        )
        with pytest.raises(ValueError, match="Invalid member_role"):
            ledger.manage_layer_roster(ws, member_role="invalid-role")

        ind_dry = ledger.configure_git_governance_policy(ws, sync_codeowners=False, dry_run=True)
        assert ind_dry["git_governance"]["promotion_pipeline"] == "direct"
        assert ind_dry["codeowners_file"] is None
        ledger.configure_git_governance_policy(ws, sync_codeowners=False, dry_run=False)
        ledger.manage_layer_roster(ws)

        # Enterprise node with roster additions and removals
        corp = tmp_path / "corp-iso"
        _write_manifest(
            corp,
            {
                "schema_version": NODE_MANIFEST_CONTRACT_REV,
                "layer_id": "corp-iso",
                "layer_role": "corporate",
                "precedence": 10,
                "layer_authority": {"authorized_emails": ["*@corp-iso.example"]},
            },
        )
        dry_roster = ledger.manage_layer_roster(
            corp, add_email="owner@corp-iso.example", member_role="owner", dry_run=True
        )
        assert dry_roster["dry_run"] is True
        assert not (corp / ".github/CODEOWNERS").exists()

        ledger.manage_layer_roster(
            corp,
            add_email="owner@corp-iso.example, ,owner2@corp-iso.example",
            member_role="owner",
            title="Chief Architect",
            squad="core",
        )
        ledger.manage_layer_roster(
            corp, add_email="maint@corp-iso.example", member_role="maintainer"
        )
        ledger.manage_layer_roster(corp, add_email="val@corp-iso.example", member_role="validator")
        removed = ledger.manage_layer_roster(corp, remove_email="owner2@corp-iso.example")
        assert "owner@corp-iso.example" in removed["authorized_emails"]
        assert "owner2@corp-iso.example" not in removed["authorized_emails"]
        assert (corp / ".github/CODEOWNERS").is_file()

        # No-op call when CODEOWNERS already exists refreshes policy cleanly
        noop_res = ledger.manage_layer_roster(corp)
        # Assert
        assert noop_res["validator_emails"] == ["val@corp-iso.example"]

    def test_inspect_git_governance_state_across_branches_and_alerts_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify branch category/environment inference, .git HEAD lookup, and stale proposals."""
        # Arrange
        ws = tmp_path / "squad-iso"
        _write_manifest(
            ws,
            {
                "schema_version": "outdated-rev",
                "layer_id": "squad-iso",
                "layer_role": "squad",
                "precedence": 50,
            },
        )
        (ws / ".git").mkdir()
        (ws / "logs").mkdir()
        (ws / "logs/governance_audit.jsonl").write_text(
            json.dumps({"status": "allowed", "operation": "status"})
            + "\n"
            + json.dumps({"status": "blocked", "operation": "release"})
            + "\n",
            encoding="utf-8",
        )
        prop_dir = ws / ".agents/proposals/from-upstream"
        prop_dir.mkdir(parents=True)
        stale_p = prop_dir / "old.md"
        fresh_p = prop_dir / "new.md"
        stale_p.write_text("# Old\n", encoding="utf-8")
        fresh_p.write_text("# New\n", encoding="utf-8")
        os.utime(stale_p, (1_000_000.0, 1_000_000.0))

        git_proc = subprocess.CompletedProcess(["git"], 0, stdout="master\n", stderr="")
        with patch("zcg.governance.ledger.subprocess.run", return_value=git_proc):
            trunk_state = ledger.inspect_git_governance_state(ws)
        # Act

        # Assert trunk state
        assert trunk_state["current_branch"] == "master"
        assert trunk_state["branch_category"] == "protected-trunk-or-env"
        assert trunk_state["active_environment"] == "pro"
        assert trunk_state["manifest_contracts_outdated"] is True
        assert len(trunk_state["stale_proposals"]) == 1
        assert len(trunk_state["recent_governance_alerts"]) == 1

        # Branch taxonomy matrix
        cases = (
            ("specialty/robotics", "specialty-lens", "dev"),
            ("hat/reviewer", "personal-workstation", "dev"),
            ("promote/rule-1", "governance-pr", "dev"),
            ("feature/t1", "tactical-process", "dev"),
            ("env/pre", "protected-trunk-or-env", "pre"),
            ("tst/smoke", "custom", "tst"),
        )
        for br_name, exp_cat, exp_env in cases:
            st = ledger.inspect_git_governance_state(ws, current_branch=br_name)
            assert st["branch_category"] == exp_cat
            assert st["active_environment"] == exp_env

        # Workspace without .git defaults to main
        plain = tmp_path / "plain-iso"
        plain.mkdir()
        assert ledger.inspect_git_governance_state(plain)["current_branch"] == "main"

    def test_record_decision_and_summarize_work_orchestration_ledger_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify human governance decisions and Work & Sprint Ledger summarization."""
        # Arrange
        ws = tmp_path / "squad-iso"
        _write_manifest(ws, {"layer_id": "squad-iso", "layer_role": "squad"})

        # Act — decision validation & recording
        with pytest.raises(ValueError, match="Invalid decision"):
            ledger.record_governance_decision(ws, item_ref="r", decision="bad", reason="x")
        with pytest.raises(ValueError, match="Both item_ref and reason"):
            ledger.record_governance_decision(ws, item_ref=" ", decision="approve", reason="")

        dry_dec = ledger.record_governance_decision(
            ws, item_ref="prop.md", decision="reject", reason="Needs tests", dry_run=True
        )
        assert dry_dec["status"] == "rejected"
        assert not (ws / "WORKTASK.md").exists()

        app_dec = ledger.record_governance_decision(
            ws,
            item_ref="prop.md",
            decision="approve",
            reason="Verified",
            actor_email="lead@corp-iso.example",
        )
        assert "- [x]" in app_dec["recorded_entry"]

        # Populate WORKTASK.md with own, delegated, completed-delegated, and outbound items
        (ws / "WORKTASK.md").write_text(
            "# Active Work Tasks\n"
            "- [ ] Own open task\n"
            "- [/] Own in-progress task\n"
            "- [x] Own completed task\n"
            "- [x] **[T-1 · Delegated from `dept-iso`]**: Completed directive\n"
            "- [ ] **[T-2 -> `sub-iso`]**: Outbound item\n"
            f"{app_dec['recorded_entry']}\n",
            encoding="utf-8",
        )
        empty_prop_ws = tmp_path / "clean-iso"
        empty_prop_ws.mkdir()
        assert (
            ledger.summarize_work_orchestration_ledger(empty_prop_ws)["inter_layer_exchange"][
                "inbound_proposals"
            ]
            == []
        )

        (ws / ".agents/proposals").mkdir(parents=True, exist_ok=True)
        (ws / ".agents/proposals/cand.md").write_text("# Candidate\n", encoding="utf-8")

        summary = ledger.summarize_work_orchestration_ledger(ws)
        assert summary["own_node_ledger"]["total_open_items"] == 1
        assert summary["own_node_ledger"]["total_in_progress_items"] == 1
        assert summary["own_node_ledger"]["total_completed_items"] == 1
        assert len(summary["own_node_ledger"]["active_node_tasks"]) == 2
        assert len(summary["inter_layer_exchange"]["inbound_directives"]) == 1
        assert len(summary["inter_layer_exchange"]["outbound_deliverables"]) == 2
        # Assert
        assert summary["inter_layer_exchange"]["inbound_proposals"] == [".agents/proposals/cand.md"]
