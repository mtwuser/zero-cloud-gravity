"""Tiered CLI dispatcher and console entrypoint for ZeroCloudGravity ('zcg').

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from zcg.cli.commands import (
    C2_LIFECYCLE_SUBCOMMANDS,
    C3_GOVERNANCE_SUBCOMMANDS,
    dispatch_c2,
    dispatch_c3,
)
from zcg.cli.discovery import (
    C1_DISCOVERY_SUBCOMMANDS,
    SUBTREE_SUBCOMMANDS,
    WORKSTATION_SUBCOMMANDS,
    dispatch_c1,
    dispatch_subtree,
    dispatch_workstation,
)
from zcg.cli.parser import CLIAuthorityBlockedError, CLIUsageError
from zcg.core.constants import REPO_DIR
from zcg.core.manifests import read_version


def dispatch_zcg_cli(
    repo_dir: Path, dry_run: bool, subcmd: str, raw_args: list[str]
) -> tuple[int, dict[str, Any] | None, str | None]:
    """Route a zcg CLI subcommand by family and return (exit_code, payload, error_msg)."""
    eff_dry = dry_run or "--dry-run" in raw_args or "-n" in raw_args
    rest = [a for a in raw_args if a not in ("--dry-run", "-n")]
    try:
        if subcmd in C1_DISCOVERY_SUBCOMMANDS:
            c1_res = dispatch_c1(repo_dir, eff_dry, subcmd, rest)
            code = 1 if subcmd == "lint-arch" and not c1_res.get("passed", True) else 0
            return code, c1_res, None
        if subcmd in C2_LIFECYCLE_SUBCOMMANDS:
            return 0, dispatch_c2(repo_dir, eff_dry, subcmd, rest), None
        if subcmd in C3_GOVERNANCE_SUBCOMMANDS:
            return 0, dispatch_c3(repo_dir, eff_dry, subcmd, rest), None
        if subcmd in SUBTREE_SUBCOMMANDS:
            return 0, dispatch_subtree(repo_dir, eff_dry, subcmd, rest), None
        if subcmd in WORKSTATION_SUBCOMMANDS:
            ws_res = dispatch_workstation(repo_dir, eff_dry, subcmd, rest)
            return (0 if ws_res["passed"] else 1), ws_res, None
        raise CLIUsageError(f"Unknown subcommand: {subcmd}")
    except CLIAuthorityBlockedError as exc:
        return 2, exc.payload, exc.message
    except (CLIUsageError, ValueError) as exc:
        return 1, None, str(exc)


def main(argv: list[str] | None = None) -> int:
    """Console entrypoint for 'zcg' (returns 0 on success, 1 on usage/validation, 2 on blocked)."""
    args = list(sys.argv[1:] if argv is None else argv)
    env_repo = os.environ.get("ZCG_DIR", "").strip()
    repo_dir = Path(env_repo).resolve() if env_repo else REPO_DIR
    dry_run = False
    idx = 0
    while idx < len(args) and args[idx].startswith("-"):
        flag = args[idx]
        if flag in ("-v", "--version"):
            print(json.dumps({"name": "zero-cloud-gravity", "version": read_version(repo_dir)}))
            return 0
        if flag in ("-h", "--help"):
            all_cmds = (
                *C1_DISCOVERY_SUBCOMMANDS,
                *C2_LIFECYCLE_SUBCOMMANDS,
                *C3_GOVERNANCE_SUBCOMMANDS,
                *SUBTREE_SUBCOMMANDS,
                *WORKSTATION_SUBCOMMANDS,
            )
            help_doc = {
                "usage": "zcg [--repo-dir <dir>] [--dry-run] <subcommand> [args]",
                "subcommands": list(all_cmds),
            }
            print(json.dumps(help_doc, indent=2))
            return 0
        if flag in ("-n", "--dry-run"):
            dry_run, idx = True, idx + 1
        elif flag == "--repo-dir" and idx + 1 < len(args):
            repo_dir, idx = Path(args[idx + 1]).resolve(), idx + 2
        else:
            print(f"Error: Unknown global option {flag}", file=sys.stderr)
            return 1
    if idx >= len(args):
        print("Error: Missing subcommand (run 'zcg --help')", file=sys.stderr)
        return 1
    code, payload, err_msg = dispatch_zcg_cli(repo_dir, dry_run, args[idx], args[idx + 1 :])
    if err_msg is not None:
        print(f"Error: {err_msg}", file=sys.stderr)
    if payload is not None and not payload.get("streamed"):
        print(json.dumps(payload, indent=2))
    return code
