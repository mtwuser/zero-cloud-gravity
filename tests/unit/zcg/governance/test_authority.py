"""Unit tests for zcg.governance.authority.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance import authority


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    path = node_dir / NODE_MANIFEST_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestAuthority:
    """Verify actor resolution, audit ledger, proposal staging, RBAC, and 1-hop OSS gates."""

    def test_append_tracker_and_git_email_resolution_variants_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify idempotent tracker appends and Git email env/subprocess/error fallbacks."""
        # Arrange
        ws = tmp_path / "node-iso"
        ws.mkdir()
        authority.append_tracker_line(ws, "WORKTASK.md", "- [ ] First item", "node-iso")
        authority.append_tracker_line(ws, "WORKTASK.md", "- [ ] First item", "node-iso")
        (ws / "WORKROAD.md").write_text("# Road", encoding="utf-8")
        authority.append_tracker_line(ws, "WORKROAD.md", "- [ ] Road item", "node-iso")

        # Act
        assert (ws / "WORKTASK.md").read_text("utf-8").count("First item") == 1
        assert "\n- [ ] Road item\n" in (ws / "WORKROAD.md").read_text("utf-8")

        monkeypatch.setenv("ZCG_GIT_USER_EMAIL", "env@corp-iso.example")
        assert authority.resolve_git_user_email(ws) == "env@corp-iso.example"

        monkeypatch.delenv("ZCG_GIT_USER_EMAIL", raising=False)
        ok_proc = subprocess.CompletedProcess(
            ["git"], 0, stdout="git@corp-iso.example\n", stderr=""
        )
        with patch("zcg.governance.authority.subprocess.run", return_value=ok_proc):
            assert authority.resolve_git_user_email(ws) == "git@corp-iso.example"
            role_res = authority.resolve_actor_layer_role(ws)
            assert role_res["actor_email"] == "git@corp-iso.example"

        bad_proc = subprocess.CompletedProcess(["git"], 1, stdout="", stderr="")
        with patch("zcg.governance.authority.subprocess.run", return_value=bad_proc):
            assert authority.resolve_git_user_email(ws) == ""

        with patch("zcg.governance.authority.subprocess.run", side_effect=OSError("no git")):
            assert authority.resolve_git_user_email(ws) == ""

        explicit_role = authority.resolve_actor_layer_role(ws, actor_email="lead@corp-iso.example")
        # Assert
        assert explicit_role["actor_email"] == "lead@corp-iso.example"

    def test_record_event_stage_proposal_and_configure_authority_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify governance events, proposal staging, and layer_authority validation."""
        # Arrange
        ws = tmp_path / "squad-iso"
        ws.mkdir()

        # Act — missing manifest & empty role guards
        with pytest.raises(ValueError, match="Missing node manifest"):
            authority.configure_layer_authority(ws, owner_role="Lead", authorized_emails=[])

        _write_manifest(ws, {"layer_id": "squad-iso", "layer_role": "squad"})
        with pytest.raises(ValueError, match="owner_role must be a non-empty"):
            authority.configure_layer_authority(ws, owner_role="  ", authorized_emails=[])

        dry_cfg = authority.configure_layer_authority(
            ws, owner_role="Squad Lead", authorized_emails=[], dry_run=True
        )
        assert dry_cfg["layer_authority"]["escalation_contact"] == "Squad Lead (squad-iso)"

        live_cfg = authority.configure_layer_authority(
            ws, owner_role="Squad Lead", authorized_emails=["lead@corp-iso.example", " "]
        )
        assert "<lead@corp-iso.example>" in live_cfg["layer_authority"]["escalation_contact"]

        # Dry-run vs allowed vs blocked/staged events
        authority.record_governance_event(ws, operation="op", status="blocked", dry_run=True)
        assert not (ws / "logs/governance_audit.jsonl").exists()

        authority.record_governance_event(ws, operation="op", status="allowed", message="ok")
        assert not (ws / ".agents/SESSION.md").exists()

        authority.record_governance_event(ws, operation="op", status="blocked", message="halt")
        authority.record_governance_event(ws, operation="op", status="blocked", message="halt")
        assert (ws / ".agents/SESSION.md").read_text("utf-8").count("halt") == 1

        dry_stg = authority.stage_non_destructive_proposal(
            ws, scope_tag="up", file_name="r.md", content="# R", operation="sync", dry_run=True
        )
        assert not dry_stg.exists()

        live_stg = authority.stage_non_destructive_proposal(
            ws, scope_tag="up", file_name="r.md", content="# R", operation="sync"
        )
        assert live_stg.is_file()
        # Assert
        assert "Staged Governance Proposal" in (ws / "WORKTASK.md").read_text("utf-8")

    def test_verify_layer_operation_authority_inheritance_and_rbac_branches_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify inherited upstream asset blocks, consumer ops, hierarchy, and pool checks."""
        # Arrange
        parent = tmp_path / "dept-iso"
        _write_manifest(
            parent,
            {
                "layer_id": "dept-iso",
                "layer_role": "department",
                "precedence": 30,
                "governing_root_id": "corp-iso",
                "layer_authority": {
                    "authorized_emails": ["dept-owner@corp-iso.example"],
                    "maintainer_emails": ["dept-maint@corp-iso.example"],
                },
            },
        )
        ws = tmp_path / "squad-iso"
        _write_manifest(
            ws,
            {
                "layer_id": "squad-iso",
                "layer_role": "squad",
                "precedence": 50,
                "governing_root_id": "corp-iso",
                "default_stack_templates": ["science-base", "squad-iso"],
                "upstream_layer": {"layer_id": "dept-iso"},
                "layer_authority": {
                    "owner_role": "Squad Owner",
                    "authorized_emails": ["owner@corp-iso.example"],
                    "maintainer_emails": ["maint@corp-iso.example"],
                    "validator_emails": ["val@corp-iso.example"],
                },
            },
        )
        sci_tpl = ws / "templates/context-stack/science-base"
        (sci_tpl / "rules").mkdir(parents=True)
        (sci_tpl / "rules/science-base.md").write_text("# Sci\n", encoding="utf-8")
        (sci_tpl / "skills/sci-guide").mkdir(parents=True)
        (sci_tpl / "skills/sci-guide/SKILL.md").write_text("# Skill\n", encoding="utf-8")

        # Act — inherited paths blocked
        for inh_path in (
            ".agents/rules/layer-30-dept.md",
            "templates/context-stack/science-base/rules/science-base.md",
            "templates/science-base/rules/science-base.md",
            ".agents/rules/science-base.md",
            ".agents/skills/sci-guide/SKILL.md",
        ):
            res = authority.verify_layer_operation_authority(
                ws, operation="edit", actor_email="owner@corp-iso.example", target_rel_path=inh_path
            )
            assert res["allowed"] is False
            assert res["reason_code"] == "INHERITED_UPSTREAM_ASSET_IMMUTABLE"

        # Own template & unrelated path are not blocked as inherited
        own_res = authority.verify_layer_operation_authority(
            ws,
            operation="status",
            actor_email="anyone@corp-iso.example",
            target_rel_path="templates/squad-iso/rules/squad-iso.md",
        )
        assert own_res["allowed"] is True
        assert own_res["reason_code"] == "CONSUMER_OPERATION_ALLOWED"

        # Validator allowed on record-decision; upstream owner & maintainer hierarchical pass
        val_ok = authority.verify_layer_operation_authority(
            ws, operation="record-decision", actor_email="val@corp-iso.example"
        )
        assert val_ok["allowed"] is True

        hier_owner = authority.verify_layer_operation_authority(
            ws,
            operation="release",
            actor_email="dept-owner@corp-iso.example",
            parent_dir=parent,
        )
        assert hier_owner["reason_code"] == "UPSTREAM_HIERARCHICAL_AUTHORITY"

        hier_maint = authority.verify_layer_operation_authority(
            ws,
            operation="delegate-to-child",
            actor_email="dept-maint@corp-iso.example",
            parent_dir=parent,
        )
        assert hier_maint["reason_code"] == "UPSTREAM_HIERARCHICAL_AUTHORITY"

        # Unauthorized actor with record_blocked True vs False, and actor_email=None
        unauth_logged = authority.verify_layer_operation_authority(
            ws, operation="release", actor_email="stranger@corp-iso.example", record_blocked=True
        )
        assert unauth_logged["reason_code"] == "UNAUTHORIZED_ACTOR_EMAIL"

        # Assert
        with patch("zcg.governance.authority.resolve_git_user_email", return_value=""):
            unauth_quiet = authority.verify_layer_operation_authority(
                ws, operation="release", actor_email=None, record_blocked=False
            )
            assert unauth_quiet["allowed"] is False

    def test_verify_oss_agnosticism_and_single_hop_upstream_gates_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify OSS private-token leak detection and 1-hop / Root 0 / Peer Root 0 gates."""
        # Arrange
        oss_root = tmp_path / "zcg-oss"
        _write_manifest(
            oss_root,
            {
                "layer_id": "zero-cloud-gravity",
                "layer_role": "workstation",
                "entity_kind": "open-source",
            },
        )
        corp_a = tmp_path / "corp-alpha"
        _write_manifest(
            corp_a,
            {
                "layer_id": "acmevault-corp",
                "layer_role": "corporate",
                "precedence": 10,
                "mounted_layers": [{"name": "dept-ops", "layer_id": "dept-ops"}, "ignore"],
                "upstream_layer": {"layer_id": "other-parent"},
                "layer_authority": {
                    "authorized_emails": [
                        "lead@gmail.com",
                        "owner@*.acmevault.io",
                        "no-at-sign",
                    ]
                },
            },
        )
        corp_b = tmp_path / "corp-beta"
        _write_manifest(
            corp_b,
            {
                "layer_id": "zenithgrid-corp",
                "layer_role": "corporate",
                "precedence": 10,
            },
        )
        squad = tmp_path / "squad-x"
        _write_manifest(
            squad,
            {
                "layer_id": "squad-x",
                "layer_role": "squad",
                "precedence": 50,
                "upstream_layer": {"layer_id": "dept-ops"},
            },
        )

        # Act — agnosticism clean vs leaked
        authority.verify_oss_promotion_agnosticism(corp_a, "Generic ISO policy.", "rule.md")
        with pytest.raises(ValueError, match="OSS_AGNOSTICISM_VIOLATION"):
            authority.verify_oss_promotion_agnosticism(
                corp_a, "Internal acmevault endpoint.", "rule.md"
            )

        # 2-hop bypass from squad -> corp_b
        with pytest.raises(ValueError, match="CROSS_TIER_PROMOTION_BYPASS"):
            authority.verify_single_hop_upstream(squad, corp_b, actor_email="owner@acmevault.io")

        # Root 0 -> OSS root: unauthorized vs authorized
        with pytest.raises(ValueError, match="UNAUTHORIZED_OSS_PROMOTION"):
            authority.verify_single_hop_upstream(
                corp_a, oss_root, actor_email="outsider@example.com"
            )
        authority.verify_single_hop_upstream(corp_a, oss_root, actor_email="owner@sub.acmevault.io")

        # Peer Root 0 -> Peer Root 0: unauthorized vs authorized
        # Assert
        with pytest.raises(ValueError, match="UNAUTHORIZED_INTER_ROOT_PROMOTION"):
            authority.verify_single_hop_upstream(corp_a, corp_b, actor_email="outsider@example.com")
        authority.verify_single_hop_upstream(corp_a, corp_b, actor_email="lead@gmail.com")

        # Normal 1-hop squad -> matching non-OSS parent
        dept = tmp_path / "dept-ops"
        _write_manifest(dept, {"layer_id": "dept-ops", "layer_role": "department"})
        authority.verify_single_hop_upstream(squad, dept, actor_email="dev@example.com")
