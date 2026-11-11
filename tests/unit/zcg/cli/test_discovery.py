"""Unit tests for zcg.cli.discovery.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.cli import discovery
from zcg.cli.parser import CLIAuthorityBlockedError, CLIUsageError
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance import scaffolder


class TestDiscovery:
    """Verify C1 read-only discovery handlers and mounted subtree CLI dispatchers."""

    def test_dispatch_c1_across_all_discovery_subcommands_expected(self, tmp_path: Path) -> None:
        """Verify list-templates, status, horizon, compare, diff, authority, and consult."""
        # Arrange
        repo = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(repo, layer_id="corp-iso", layer_role="corporate")
        scaffolder.scaffold_template_pack(
            repo, template_name="ops-pack", kind="context-stack", register_binding=True
        )
        sub = repo / "layers/dept-a"
        scaffolder.configure_node_manifest(sub, layer_id="dept-a", layer_role="department")
        m_path = repo / NODE_MANIFEST_REL_PATH
        m_data = json.loads(m_path.read_text("utf-8"))
        m_data["mounted_layers"] = [{"name": "dept-a"}]
        m_data["federated_mcps"] = [{"id": "mcp-1"}]
        m_path.write_text(json.dumps(m_data), "utf-8")

        proj = tmp_path / "plain-proj"
        proj.mkdir()

        # Act — 1. list-templates
        lt_res = discovery.dispatch_c1(repo, False, "list-templates", [str(repo)])
        assert lt_res["count"] == 1
        assert len(lt_res["federated_mcps"]) == 1
        assert len(lt_res["ephemeral_bots"]) == 1

        # 2. status, inspect-horizon, compare-upstream
        with patch("zcg.cli.discovery.inspect_workspace_status", return_value={"ok": "status"}):
            assert discovery.dispatch_c1(repo, False, "status", []) == {"ok": "status"}
        with patch(
            "zcg.cli.discovery.horizon.inspect_layer_horizon", return_value={"ok": "horizon"}
        ):
            assert discovery.dispatch_c1(repo, False, "inspect-horizon", []) == {"ok": "horizon"}
        with patch(
            "zcg.cli.discovery.horizon.compare_upstream_templates", return_value={"ok": "cmp"}
        ):
            assert (
                discovery.dispatch_c1(repo, True, "compare-upstream", ["--apply-safe"])["ok"]
                == "cmp"
            )

        # 3. diff-project & lint-arch on manifested node vs unmanifested project
        assert "in_sync" in discovery.dispatch_c1(repo, False, "diff-project", [str(repo)])
        assert "in_sync" in discovery.dispatch_c1(repo, False, "diff-project", [str(proj)])
        assert discovery.dispatch_c1(repo, False, "lint-arch", [str(proj), "--no-tests"])["passed"]

        # 4. check-authority allowed vs blocked
        with patch(
            "zcg.cli.discovery.authority.verify_layer_operation_authority",
            return_value={"allowed": True},
        ):
            assert discovery.dispatch_c1(repo, False, "check-authority", ["--op", "status"]) == {
                "allowed": True
            }
        with (
            patch(
                "zcg.cli.discovery.authority.verify_layer_operation_authority",
                return_value={"allowed": False, "remediation": "Blocked"},
            ),
            pytest.raises(CLIAuthorityBlockedError),
        ):
            discovery.dispatch_c1(repo, False, "check-authority", ["--op", "sync-layer"])

        # 5. consult-layer
        with patch(
            "zcg.cli.discovery.promotion.consult_layer_ephemeral", return_value={"ok": "consult"}
        ):
            c_res = discovery.dispatch_c1(
                repo, False, "consult-layer", ["--layer", "root", "--query", "policy"]
            )
        # Assert
        assert c_res == {"ok": "consult"}

    def test_dispatch_subtree_list_and_pull_all_expected(self, tmp_path: Path) -> None:
        """Verify space-separated and hyphenated subtree list, pull-all, and register."""
        # Arrange
        repo = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(repo, layer_id="corp-iso", layer_role="corporate")

        # Act
        ls_res = discovery.dispatch_subtree(repo, False, "subtree-list", [str(repo)])
        ls_space = discovery.dispatch_subtree(repo, False, "subtree", ["list", str(repo)])
        pull_res = discovery.dispatch_subtree(repo, True, "subtree-pull-all", [])
        pull_space = discovery.dispatch_subtree(repo, True, "subtree", ["pull-all"])
        with (
            patch("zcg.cli.discovery.enforce_cli_authority"),
            patch(
                "zcg.cli.discovery.bootstrap.register_mounted_subtree",
                return_value={"registered": "gov-iso"},
            ),
        ):
            reg_space = discovery.dispatch_subtree(
                repo, True, "subtree", ["register", "gov-iso", "https://example.org/gov-iso.git"]
            )

        # Assert
        assert ls_res["count"] == 0 and ls_space["count"] == 0
        assert pull_res["dry_run"] is True and pull_space["dry_run"] is True
        assert reg_space == {"registered": "gov-iso"}
        with pytest.raises(CLIUsageError, match="Usage: zcg subtree"):
            discovery.dispatch_subtree(repo, False, "subtree", [])
        with pytest.raises(CLIUsageError, match="Usage: zcg subtree register"):
            discovery.dispatch_subtree(repo, False, "subtree", ["register", "only-name"])

    def test_dispatch_workstation_host_scripts_and_dry_run_expected(self, tmp_path: Path) -> None:
        """Verify workstation host script execution, dry-run flag handling, and missing script."""
        # Arrange
        eng = tmp_path / "engine"
        (eng / "scripts").mkdir(parents=True)
        missing_res_dir = tmp_path / "empty-engine"
        missing_res_dir.mkdir()
        b_sh = eng / "scripts/workstation-backup.sh"
        b_sh.write_text('#!/usr/bin/env bash\necho "args:$*"\nexit 0\n', encoding="utf-8")
        b_sh.chmod(0o755)
        a_sh = eng / "scripts/workstation-audit.sh"
        a_sh.write_text('#!/usr/bin/env bash\necho "audit:$*"\nexit 0\n', encoding="utf-8")
        a_sh.chmod(0o755)

        # Act
        dry_backup = discovery.dispatch_workstation(eng, True, "workstation-backup", ["/tmp"])
        dry_audit = discovery.dispatch_workstation(eng, True, "workstation-audit", ["--clean"])
        live_backup = discovery.dispatch_workstation(eng, False, "workstation-backup", ["/tmp"])

        # Assert
        assert dry_backup["passed"] is True and "--dry-run" in dry_backup["output"]
        assert dry_audit["passed"] is True and "--clean" not in dry_audit["output"]
        assert live_backup["passed"] is True and "--dry-run" not in live_backup["output"]
        with pytest.raises(CLIUsageError, match="Missing workstation script"):
            discovery.dispatch_workstation(missing_res_dir, False, "install-antigravity", [])
