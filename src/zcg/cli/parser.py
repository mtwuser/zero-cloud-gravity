"""Typed option, flag, and authority parser utilities for the 'zcg' CLI.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from zcg.governance import authority


class CLIUsageError(ValueError):
    """Raised when CLI arguments or subcommands are missing or invalid."""


class CLIAuthorityBlockedError(RuntimeError):
    """Raised when a layer authority or environment gate blocks an operation (exit code 2)."""

    def __init__(self, payload: dict[str, Any], message: str) -> None:
        """Initialize blocked error with JSON verdict payload and stderr message."""
        super().__init__(message)
        self.payload, self.message = payload, message


def parse_cli_options(
    subcmd: str, args: list[str], vflags: tuple[str, ...], bflags: tuple[str, ...] = ()
) -> dict[str, object]:
    """Parse value flags (--flag <val>) and boolean flags (--flag) for a CLI subcommand."""
    out: dict[str, object] = {}
    idx = 0
    while idx < len(args):
        arg, key = args[idx], args[idx].removeprefix("--").replace("-", "_")
        if arg in vflags and idx + 1 < len(args):
            out[key], idx = args[idx + 1], idx + 2
        elif arg in bflags:
            out[key], idx = True, idx + 1
        else:
            raise CLIUsageError(f"Unknown or incomplete {subcmd} argument: {arg}")
    return out


def split_csv(val: object) -> list[str] | None:
    """Split a comma-separated option value into trimmed non-empty strings."""
    return [x.strip() for x in str(val).split(",") if x.strip()] if val else None


def opt_str(opts: dict[str, object], key: str) -> str | None:
    """Return optional string value from parsed CLI options."""
    return str(opts[key]) if key in opts else None


def opt_path(opts: dict[str, object], key: str) -> Path | None:
    """Return optional resolved Path from parsed CLI options."""
    return Path(str(opts[key])).resolve() if key in opts else None


def require_pos_path(rest: list[str], usage: str) -> Path:
    """Require a leading positional directory argument or raise CLIUsageError."""
    if not rest or rest[0].startswith("-"):
        raise CLIUsageError(f"Usage: zcg {usage}")
    return Path(rest[0]).resolve()


def require_opt_str(opts: dict[str, object], key: str, message: str) -> str:
    """Require a non-empty string option or raise CLIUsageError."""
    if not opts.get(key):
        raise CLIUsageError(message)
    return str(opts[key])


def parse_pos_and_options(
    repo_dir: Path,
    subcmd: str,
    args: list[str],
    vflags: tuple[str, ...],
    bflags: tuple[str, ...] = (),
) -> tuple[Path, dict[str, object]]:
    """Parse an optional leading positional path (defaulting to repo_dir) plus CLI flags."""
    has_pos = bool(args and not args[0].startswith("--"))
    target = Path(args[0]).resolve() if has_pos else repo_dir
    return target, parse_cli_options(subcmd, args[1:] if has_pos else args, vflags, bflags)


def enforce_cli_authority(target: Path, op: str) -> None:
    """Verify actor authority for <op> on <target> or raise CLIAuthorityBlockedError."""
    verdict = authority.verify_layer_operation_authority(target, operation=op)
    if not verdict["allowed"]:
        raise CLIAuthorityBlockedError(verdict, str(verdict["remediation"]))
