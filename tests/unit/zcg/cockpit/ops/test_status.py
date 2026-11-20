"""Unit tests for zcg.cockpit.ops.status.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from zcg.cockpit.ops import status
from zcg.governance.workspace import scaffolder


class TestStatus:
    """Verify single-call workspace status digest across project, business, and hybrid nodes."""

    def test_inspect_workspace_status_project_business_and_hybrid_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify standalone project, pure business node, and git-backed hybrid cockpit node."""
        # Arrange — 1. Unmanifested standalone project (no git, no session, no cockpit)
        engine = tmp_path / "zcg-engine"
        scaffolder.scaffold_template_pack(
            engine, template_name="academic-base", kind="context-stack", rule_filename="acad.md"
        )
        scaffolder.scaffold_template_pack(
            engine,
            template_name="software-engineering",
            kind="context-stack",
            rule_filename="swe.md",
        )

        proj = tmp_path / "plain-proj"
        proj.mkdir()
        proj_st = status.inspect_workspace_status(engine, proj)
        assert proj_st["layer_role"] == "project"
        assert proj_st["posture"]["governance_posture"] == "sovereign"
        assert proj_st["surface_origin"]["origin_mode"] == "loopback"
        assert proj_st["active_cockpit"] is None
        assert proj_st["horizon"] is None
        assert proj_st["workspace_mode"] == "technical"

        # 2. Pure business corporate node
        corp = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(corp, layer_id="corp-iso", layer_role="corporate")
        corp_st = status.inspect_workspace_status(engine, corp)
        assert corp_st["workspace_mode"] == "business"
        assert "dev.corp-iso.localhost" in corp_st["surface_origin"]["canonical_origin"]

        # 2b. Private personal workstation defaults surface_origin to 'pro' (0 'dev.' prefix)
        pers = tmp_path / "persona-profile"
        scaffolder.configure_node_manifest(
            pers, layer_id="persona-profile", layer_role="workstation", precedence=90
        )
        pers_st = status.inspect_workspace_status(engine, pers)
        assert (
            pers_st["surface_origin"]["canonical_origin"] == "http://persona-profile.localhost:8790"
        )

        # 3. Hybrid node with git, SESSION UUID, WORKTASK, rmap rule, custom skill, and cockpit
        hyb = tmp_path / "hyb-iso"
        scaffolder.configure_node_manifest(hyb, layer_id="hyb-iso", layer_role="department")
        (hyb / ".git").mkdir()
        (hyb / "corporate").mkdir()
        (hyb / "WORKTASK.md").write_text("# Active Tasks\n- [ ] T1\n", "utf-8")
        (hyb / ".agents/rules").mkdir(parents=True)
        (hyb / ".agents/rules/acad.md").write_text("# Acad\n", "utf-8")
        (hyb / ".agents/rules/swe.md").write_text("# SWE\n", "utf-8")
        (hyb / ".agents/skills/custom-sk").mkdir(parents=True)
        (hyb / ".agents/skills/custom-sk/SKILL.md").write_text("# Custom\n", "utf-8")
        (hyb / ".agents/SESSION.md").write_text(
            "Session zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz "
            "12345678-1234-5678-1234-567812345678 active\n",
            "utf-8",
        )
        (hyb / ".agents/runtime").mkdir(parents=True)
        (hyb / ".agents/runtime/cockpit.json").write_text(
            json.dumps(
                {
                    "plugin_id": "node-work-cockpit",
                    "status": "active",
                    "daemon_active": True,
                    "intranet_topology": {
                        "localhost_url": "http://127.0.0.1:8830/?env=dev",
                        "local_subdomain_url": "http://dev.hyb-iso.localhost:8830/?env=dev",
                        "local_environment_urls": {"dev": "http://127.0.0.1:8830/?env=dev"},
                        "local_subdomain_urls": {
                            "dev": "http://dev.hyb-iso.localhost:8830/?env=dev"
                        },
                        "active_subdomain_url": "https://dev.hyb-iso.intranet.local",
                    },
                }
            ),
            "utf-8",
        )
        git_proc = subprocess.CompletedProcess(["git"], 0, stdout="## master\n", stderr="")
        with patch("zcg.cockpit.ops.status.subprocess.run", return_value=git_proc):
            hyb_st = status.inspect_workspace_status(engine, hyb, parent_dir=corp)
        # Act

        # Assert
        assert hyb_st["workspace_mode"] == "hybrid"
        assert hyb_st["active_cockpit"]["plugin_id"] == "node-work-cockpit"
        assert (
            hyb_st["active_cockpit"]["localhost_url"]
            == "http://dev.hyb-iso.localhost:8830/?env=dev"
        )
        assert hyb_st["active_cockpit"]["environment_urls"] == {
            "dev": "http://dev.hyb-iso.localhost:8830/?env=dev"
        }
        assert (
            hyb_st["session_state"]["last_conversation_id"]
            == "12345678-1234-5678-1234-567812345678"
        )
        assert hyb_st["command_taxonomy"]["skill_rings"]["workspace_layer_skills"] == ["custom-sk"]
        assert hyb_st["git_state"]["is_git_repo"] is True
        assert hyb_st["node_health"]["contract_rev"] == status.NODE_HEALTH_CONTRACT_REV
        assert proj_st["node_health"]["overall_state"] == "UNCONFIGURED"

    def test_evaluate_node_health_four_state_epistemic_transitions_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify OPTIMAL, ATTENTION, CRITICAL, and Blue UNCONFIGURED health transitions."""
        # Arrange
        ws = tmp_path / "health-node"
        scaffolder.configure_node_manifest(
            ws, layer_id="health-node", layer_role="workstation", precedence=90
        )
        (ws / ".git").mkdir()
        (ws / ".gitignore").write_text(".zcg/\n", "utf-8")
        (ws / "README.md").write_text("# Health Node\n\nConfigured.\n", "utf-8")
        (ws / "WORKTASK.md").write_text("# Work\n- [x] Done\n", "utf-8")
        git_clean_synced = subprocess.CompletedProcess(
            ["git"], 0, stdout="## master...origin/master\n", stderr=""
        )
        git_ahead_behind = [
            "## master...origin/master [ahead 2, behind 1, tag: x]",
            " M README.md",
        ]

        # Act
        with patch("zcg.cockpit.ops.status.subprocess.run", return_value=git_clean_synced):
            opt_no_sk = status.evaluate_node_health(
                ws,
                setup_state_str="configured",
                has_origin_remote=True,
                git_governance={"makefile_outdated": False},
            )
        low_sec_doc = status.evaluate_node_health(
            ws,
            setup_state_str="configured",
            is_git_repo=False,
            git_status_lines=[],
            security_posture={"score": 60, "checks": {"overlay_integrity": True}},
            skill_trust={"score": 100, "passed": True, "scanned_skill_count": 1},
        )
        opt_full = status.evaluate_node_health(
            ws,
            setup_state_str="configured",
            is_git_repo=True,
            git_status_lines=["## master...origin/master"],
            security_posture={"score": 100, "checks": {"overlay_integrity": True}},
            skill_trust={"score": 100, "passed": True, "scanned_skill_count": 3},
            git_governance={"makefile_outdated": False},
            horizon={"downward_sync_needed": False},
            agent_diff={"in_sync": True},
        )
        attn_doc = status.evaluate_node_health(
            ws,
            setup_state_str="configured",
            is_git_repo=True,
            git_status_lines=git_ahead_behind,
            security_posture={"score": 80, "checks": {"overlay_integrity": True}},
            skill_trust={
                "score": 95,
                "passed": False,
                "scanned_skill_count": 2,
                "tiers": {"tier1_security_finding_count": 0},
            },
            git_governance={"makefile_outdated": True},
        )
        no_rem_doc = status.evaluate_node_health(
            ws,
            setup_state_str="configured",
            is_git_repo=True,
            git_status_lines=["## master"],
            has_origin_remote=False,
            security_posture={"score": 100, "checks": {"overlay_integrity": True}},
            skill_trust={"score": 100, "passed": True, "scanned_skill_count": 1},
            git_governance={},
        )
        crit_doc = status.evaluate_node_health(
            ws,
            setup_state_str="configured",
            is_git_repo=False,
            git_status_lines=[],
            security_posture={"score": 60, "checks": {"overlay_integrity": False}},
            skill_trust={"score": 40, "passed": False, "scanned_skill_count": 1},
        )

        # Assert
        assert opt_no_sk["overall_state"] == "OPTIMAL"
        assert opt_no_sk["dimensions"]["skill_trust"]["state"] == "UNCONFIGURED"
        assert opt_full["overall_state"] == "OPTIMAL"
        assert opt_full["unconfigured_dimensions"] == []
        assert attn_doc["overall_state"] == "ATTENTION"
        assert attn_doc["dimensions"]["sync_safety"]["ahead"] == 2
        assert attn_doc["dimensions"]["sync_safety"]["behind"] == 1
        assert attn_doc["dimensions"]["sync_safety"]["dirty"] == 1
        assert attn_doc["dimensions"]["operational_drift"]["state"] == "ATTENTION"
        assert no_rem_doc["overall_state"] == "OPTIMAL"
        assert no_rem_doc["dimensions"]["sync_safety"]["state"] == "UNCONFIGURED"
        assert crit_doc["overall_state"] == "CRITICAL"
        assert crit_doc["dimensions"]["security_posture"]["state"] == "CRITICAL"
        assert crit_doc["dimensions"]["skill_trust"]["state"] == "CRITICAL"
        assert low_sec_doc["overall_state"] == "CRITICAL"
