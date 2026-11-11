"""Unit tests for zcg.cockpit.status.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from zcg.cockpit import status
from zcg.governance import scaffolder


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
        assert proj_st["active_cockpit"] is None
        assert proj_st["horizon"] is None
        assert proj_st["workspace_mode"] == "technical"

        # 2. Pure business corporate node
        corp = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(corp, layer_id="corp-iso", layer_role="corporate")
        corp_st = status.inspect_workspace_status(engine, corp)
        assert corp_st["workspace_mode"] == "business"

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
            "Session 12345678-1234-5678-1234-567812345678 active\n", "utf-8"
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
                        "local_environment_urls": {"dev": "http://127.0.0.1:8830/?env=dev"},
                        "active_subdomain_url": "https://dev.hyb-iso.intranet.local",
                    },
                }
            ),
            "utf-8",
        )
        git_proc = subprocess.CompletedProcess(["git"], 0, stdout="## master\n", stderr="")
        with patch("zcg.cockpit.status.subprocess.run", return_value=git_proc):
            hyb_st = status.inspect_workspace_status(engine, hyb, parent_dir=corp)
        # Act

        # Assert
        assert hyb_st["workspace_mode"] == "hybrid"
        assert hyb_st["active_cockpit"]["plugin_id"] == "node-work-cockpit"
        assert (
            hyb_st["session_state"]["last_conversation_id"]
            == "12345678-1234-5678-1234-567812345678"
        )
        assert hyb_st["command_taxonomy"]["skill_rings"]["workspace_layer_skills"] == ["custom-sk"]
        assert hyb_st["git_state"]["is_git_repo"] is True
