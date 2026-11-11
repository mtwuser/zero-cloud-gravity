"""Unit tests for zcg.cli.parser.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.cli import parser


class TestParser:
    """Verify CLI flag/positional parsing helpers and authority gate enforcement."""

    def test_parse_options_csv_and_positional_helpers_expected(self, tmp_path: Path) -> None:
        """Verify value/bool flags, CSV splitting, positional paths, and usage errors."""
        # Arrange
        # Act
        opts = parser.parse_cli_options(
            "demo",
            ["--id", "node-a", "--dir", str(tmp_path), "--force"],
            ("--id", "--dir"),
            ("--force",),
        )

        # Assert
        assert parser.opt_str(opts, "id") == "node-a"
        assert parser.opt_str(opts, "missing") is None
        assert parser.opt_path(opts, "dir") == tmp_path.resolve()
        assert parser.opt_path(opts, "missing") is None
        assert opts["force"] is True
        assert parser.split_csv(" a, b ,, c ") == ["a", "b", "c"]
        assert parser.split_csv(None) is None
        assert parser.require_opt_str(opts, "id", "need id") == "node-a"
        assert parser.require_pos_path([str(tmp_path)], "demo <dir>") == tmp_path.resolve()

        t_pos, o_pos = parser.parse_pos_and_options(
            tmp_path, "demo", [str(tmp_path / "sub"), "--id", "x"], ("--id",)
        )
        t_def, o_def = parser.parse_pos_and_options(tmp_path, "demo", ["--id", "y"], ("--id",))
        assert t_pos == (tmp_path / "sub").resolve() and o_pos["id"] == "x"
        assert t_def == tmp_path and o_def["id"] == "y"

        with pytest.raises(parser.CLIUsageError, match="Unknown or incomplete"):
            parser.parse_cli_options("demo", ["--unknown"], ("--id",))
        with pytest.raises(parser.CLIUsageError, match="Usage: zcg demo"):
            parser.require_pos_path(["--flag"], "demo <dir>")
        with pytest.raises(parser.CLIUsageError, match="missing key"):
            parser.require_opt_str({}, "id", "missing key")

    def test_enforce_cli_authority_allowed_and_blocked_expected(self, tmp_path: Path) -> None:
        """Verify enforce_cli_authority passes on allowed and raises CLIAuthorityBlockedError."""
        # Arrange
        # Act
        with patch(
            "zcg.cli.parser.authority.verify_layer_operation_authority",
            return_value={"allowed": True},
        ):
            parser.enforce_cli_authority(tmp_path, "init-fork")

        blocked_verdict = {"allowed": False, "remediation": "Escalate to owner"}
        with (
            patch(
                "zcg.cli.parser.authority.verify_layer_operation_authority",
                return_value=blocked_verdict,
            ),
            pytest.raises(parser.CLIAuthorityBlockedError) as exc_info,
        ):
            parser.enforce_cli_authority(tmp_path, "init-fork")
        assert exc_info.value.payload == blocked_verdict
        # Assert
        assert exc_info.value.message == "Escalate to owner"
