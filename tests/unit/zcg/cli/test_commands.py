"""Unit tests for zcg.cli.commands.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.cli import commands
from zcg.cli.parser import CLIAuthorityBlockedError, CLIUsageError
from zcg.governance import scaffolder


class TestCommands:
    """Verify C2 lifecycle and C3 sovereign governance CLI command dispatchers."""

    def test_dispatch_c2_across_all_lifecycle_subcommands_expected(self, tmp_path: Path) -> None:
        """Verify bootstrap, sync, apply-project, profile, task, scaffold, fork, and subtree."""
        # Arrange
        repo = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(repo, layer_id="corp-iso", layer_role="corporate")
        proj = tmp_path / "proj-iso"
        proj.mkdir()

        # Act — 1. bootstrap & sync-layer
        with patch(
            "zcg.cli.commands.bootstrap.bootstrap_node_workspace", return_value={"ok": "boot"}
        ):
            b_res = commands.dispatch_c2(
                repo, True, "bootstrap", [str(proj), "--id", "proj-iso", "--precedence", "50"]
            )
        assert b_res == {"ok": "boot"}

        with patch("zcg.cli.commands.bootstrap.sync_node_workspace", return_value={"ok": "sync"}):
            assert commands.dispatch_c2(repo, True, "sync-layer", []) == {"ok": "sync"}

        # 2. apply-project: service-action vs manifested node vs consumer project
        with patch("zcg.cli.commands.manage_plugin_service", return_value={"ok": "svc"}):
            s_res = commands.dispatch_c2(
                repo, True, "apply-project", [str(repo), "--service-action", "activate"]
            )
        assert s_res == {"ok": "svc"}

        with patch(
            "zcg.cli.commands.scaffolder.apply_templates_to_project", return_value={"ok": "app"}
        ):
            assert commands.dispatch_c2(repo, True, "apply-project", [str(repo)]) == {"ok": "app"}
            assert commands.dispatch_c2(repo, True, "apply-project", [str(proj)]) == {"ok": "app"}

        # 3. set-global-profile, start-task, scaffold-template, init-fork, register-subtree
        with pytest.raises(CLIUsageError, match="set-global-profile"):
            commands.dispatch_c2(repo, True, "set-global-profile", [])
        with patch("zcg.cli.commands.set_global_agents_profile", return_value={"ok": "prof"}):
            assert commands.dispatch_c2(repo, True, "set-global-profile", ["technical"]) == {
                "ok": "prof"
            }

        with patch("zcg.cli.commands.workflows.start_task_workflow", return_value={"ok": "task"}):
            assert commands.dispatch_c2(repo, True, "start-task", ["--task", "T1"]) == {
                "ok": "task"
            }

        with pytest.raises(CLIUsageError, match="scaffold-template"):
            commands.dispatch_c2(repo, True, "scaffold-template", ["--kind", "context-stack"])
        with (
            patch("zcg.cli.commands.enforce_cli_authority"),
            patch("zcg.cli.commands.scaffolder.scaffold_template_pack", return_value={"ok": "sc"}),
        ):
            assert commands.dispatch_c2(repo, True, "scaffold-template", ["new-pack"]) == {
                "ok": "sc"
            }

        with pytest.raises(CLIUsageError, match="scaffold-plugin-module"):
            commands.dispatch_c2(repo, True, "scaffold-plugin-module", ["only-plugin"])
        with (
            patch("zcg.cli.commands.enforce_cli_authority"),
            patch("zcg.cli.commands.scaffold_plugin_module", return_value={"ok": "pmod"}),
        ):
            assert commands.dispatch_c2(
                repo, True, "scaffold-plugin-module", ["alpha-portal", "batch-verifier"]
            ) == {"ok": "pmod"}

        # Assert
        with patch("zcg.cli.commands.enforce_cli_authority"):
            f_res = commands.dispatch_c2(
                repo, True, "init-fork", ["--id", "corp-iso", "--precedence", "10"]
            )
            assert f_res["manifest"]["layer_id"] == "corp-iso"

            with pytest.raises(CLIUsageError, match="register-subtree"):
                commands.dispatch_c2(repo, True, "register-subtree", ["only-one"])
            sub_res = commands.dispatch_c2(repo, True, "register-subtree", ["gov-es", ""])
            assert sub_res["registered_layer"]["name"] == "gov-es"

        with patch("zcg.cli.commands.links.link_node", return_value={"ok": "link"}):
            assert commands.dispatch_c2(
                repo, True, "link", ["--target", "org-alpha", "--relation", "hr-process"]
            ) == {"ok": "link"}
        with patch("zcg.cli.commands.links.unlink_node", return_value={"ok": "unlink"}):
            assert commands.dispatch_c2(repo, True, "unlink", ["--target", "org-alpha"]) == {
                "ok": "unlink"
            }
        with patch("zcg.cli.commands.links.spinout_branch_to_project", return_value={"ok": "spin"}):
            assert commands.dispatch_c2(
                repo,
                True,
                "spinout-project",
                [str(proj), "--id", "proj-iso", "--from-branch", "venture/saas"],
            ) == {"ok": "spin"}

    def test_dispatch_c3_across_all_governance_subcommands_expected(self, tmp_path: Path) -> None:
        """Verify complete-task, delegate, promote, roster, authority, git, env-gate, decision."""
        # Arrange
        repo = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(repo, layer_id="corp-iso", layer_role="corporate")

        # Act
        with patch(
            "zcg.cli.commands.workflows.complete_task_workflow", return_value={"ok": "done"}
        ):
            assert commands.dispatch_c3(repo, True, "complete-task", ["--task", "T1"]) == {
                "ok": "done"
            }

        with pytest.raises(CLIUsageError, match="delegate-to-child"):
            commands.dispatch_c3(repo, True, "delegate-to-child", ["--to-child", "dept-a"])
        with patch(
            "zcg.cli.commands.workflows.delegate_directive_to_child", return_value={"ok": "del"}
        ):
            d_res = commands.dispatch_c3(
                repo, True, "delegate-to-child", ["--to-child", "dept-a", "--task", "Do X"]
            )
        assert d_res == {"ok": "del"}

        with patch(
            "zcg.cli.commands.promotion.promote_project_asset_to_layer", return_value={"ok": "pr"}
        ):
            p_res = commands.dispatch_c3(
                repo, True, "promote-from-project", [str(repo), "--source", ".agents/rules/x.md"]
            )
        assert p_res == {"ok": "pr"}

        with patch("zcg.cli.commands.ledger.manage_layer_roster", return_value={"ok": "ros"}):
            assert commands.dispatch_c3(repo, True, "manage-roster", ["--add", "a@b.io"]) == {
                "ok": "ros"
            }

        with patch(
            "zcg.cli.commands.authority.configure_layer_authority", return_value={"ok": "auth"}
        ):
            assert commands.dispatch_c3(repo, True, "set-authority", ["--owner-role", "Lead"]) == {
                "ok": "auth"
            }

        with patch(
            "zcg.cli.commands.ledger.configure_git_governance_policy", return_value={"ok": "git"}
        ):
            assert commands.dispatch_c3(repo, True, "configure-git-policy", []) == {"ok": "git"}

        with patch(
            "zcg.cli.commands.consensus.evaluate_environment_promotion",
            return_value={"allowed": True, "failed_gates": []},
        ):
            assert (
                commands.dispatch_c3(repo, True, "check-env-promotion", ["--to-env", "tst"])[
                    "allowed"
                ]
                is True
            )

        with (
            patch(
                "zcg.cli.commands.consensus.evaluate_environment_promotion",
                return_value={"allowed": False, "failed_gates": ["DIRTY"]},
            ),
            pytest.raises(CLIAuthorityBlockedError, match="Environment promotion blocked"),
        ):
            commands.dispatch_c3(repo, True, "check-env-promotion", ["--to-env", "pro"])

        with patch(
            "zcg.cli.commands.ledger.record_governance_decision", return_value={"ok": "dec"}
        ):
            dec = commands.dispatch_c3(
                repo,
                True,
                "record-decision",
                ["--item", "I1", "--decision", "accepted", "--reason", "Valid"],
            )
        # Assert
        assert dec == {"ok": "dec"}
