"""Unit tests for zcg.cli.dispatcher.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.cli import dispatcher
from zcg.cli.parser import CLIAuthorityBlockedError
from zcg.governance import scaffolder


class TestDispatcher:
    """Verify family routing, exit codes (0, 1, 2), global flags, and ZCG_DIR override."""

    def test_dispatch_zcg_cli_routing_and_error_codes_expected(self, tmp_path: Path) -> None:
        """Verify C1/C2/C3/subtree routing plus usage (1) and authority-blocked (2) codes."""
        # Arrange
        ws = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(ws, layer_id="corp-iso", layer_role="corporate")

        # Act
        with patch("zcg.cli.dispatcher.dispatch_c1", return_value={"c": 1}):
            assert dispatcher.dispatch_zcg_cli(ws, False, "status", []) == (0, {"c": 1}, None)
        with patch(
            "zcg.cli.dispatcher.dispatch_c1",
            side_effect=[{"passed": True}, {"passed": False}],
        ):
            assert dispatcher.dispatch_zcg_cli(ws, False, "lint-arch", [])[0] == 0
            assert dispatcher.dispatch_zcg_cli(ws, False, "lint-arch", [])[0] == 1
        with patch("zcg.cli.dispatcher.dispatch_c2", return_value={"c": 2}):
            assert dispatcher.dispatch_zcg_cli(ws, False, "sync-layer", ["-n"]) == (
                0,
                {"c": 2},
                None,
            )
        with patch("zcg.cli.dispatcher.dispatch_c3", return_value={"c": 3}):
            assert dispatcher.dispatch_zcg_cli(ws, False, "manage-roster", []) == (
                0,
                {"c": 3},
                None,
            )
        assert dispatcher.dispatch_zcg_cli(ws, False, "subtree-list", [])[0] == 0
        with patch(
            "zcg.cli.dispatcher.dispatch_workstation",
            side_effect=[{"passed": True}, {"passed": False}],
        ):
            assert dispatcher.dispatch_zcg_cli(ws, True, "workstation-audit", []) == (
                0,
                {"passed": True},
                None,
            )
            assert dispatcher.dispatch_zcg_cli(ws, False, "workstation-audit", []) == (
                1,
                {"passed": False},
                None,
            )

        code_unk, p_unk, err_unk = dispatcher.dispatch_zcg_cli(ws, False, "no-such-cmd", [])
        assert code_unk == 1 and p_unk is None and "Unknown subcommand" in str(err_unk)

        # Assert
        with patch(
            "zcg.cli.dispatcher.dispatch_c1",
            side_effect=CLIAuthorityBlockedError({"allowed": False}, "Blocked"),
        ):
            assert dispatcher.dispatch_zcg_cli(ws, False, "check-authority", []) == (
                2,
                {"allowed": False},
                "Blocked",
            )

    def test_main_global_flags_env_override_and_streams_expected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Verify --version, --help, --repo-dir, --dry-run, ZCG_DIR, and exit codes 0/1/2."""
        # Arrange
        ws = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(ws, layer_id="corp-iso", layer_role="corporate")
        (ws / "VERSION").write_text("1.0.0\n", "utf-8")

        # Act
        with patch(
            "zcg.cli.dispatcher.dispatch_zcg_cli",
            return_value=(0, {"passed": True, "streamed": True}, None),
        ):
            assert dispatcher.main(["install-antigravity"]) == 0
            assert capsys.readouterr().out == ""

        assert dispatcher.main(["--version"]) == 0
        assert dispatcher.main(["--help"]) == 0
        assert dispatcher.main(["--bad-flag"]) == 1
        assert dispatcher.main(["--dry-run"]) == 1
        assert dispatcher.main(["--repo-dir", str(ws), "-n", "subtree-list"]) == 0
        assert dispatcher.main(["--repo-dir", str(ws), "unknown-sub"]) == 1

        with patch(
            "zcg.cli.dispatcher.dispatch_zcg_cli",
            return_value=(2, {"allowed": False}, "Authority denied"),
        ):
            assert dispatcher.main(["check-authority"]) == 2

        with (
            patch.dict("zcg.cli.dispatcher.os.environ", {"ZCG_DIR": str(ws)}),
            patch("zcg.cli.dispatcher.sys.argv", ["zcg", "subtree-list"]),
        ):
            assert dispatcher.main(None) == 0

        captured = capsys.readouterr()
        assert "zero-cloud-gravity" in captured.out
        # Assert
        assert "Authority denied" in captured.err
