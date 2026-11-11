"""C1 Discovery and mounted subtree command handlers for the 'zcg' CLI.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from zcg.cli.parser import (
    CLIAuthorityBlockedError,
    CLIUsageError,
    enforce_cli_authority,
    opt_path,
    opt_str,
    parse_cli_options,
    parse_pos_and_options,
    require_opt_str,
    require_pos_path,
)
from zcg.cockpit.status import inspect_workspace_status
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.core.manifests import discover_templates_catalog, load_node_manifest
from zcg.governance import arch_linter, authority, bootstrap, horizon, promotion
from zcg.topology.subtrees import (
    inspect_mounted_children_drifts,
    sync_mounted_children_into_parent,
)

C1_DISCOVERY_SUBCOMMANDS: tuple[str, ...] = (
    "list-templates",
    "status",
    "inspect-horizon",
    "compare-upstream",
    "diff-project",
    "lint-arch",
    "check-authority",
    "consult-layer",
)
SUBTREE_SUBCOMMANDS: tuple[str, ...] = ("subtree", "subtree-list", "subtree-pull-all")
WORKSTATION_SUBCOMMANDS: tuple[str, ...] = (
    "install-antigravity",
    "workstation-sync",
    "workstation-backup",
    "workstation-audit",
    "workstation-restore",
)
_WORKSTATION_SCRIPT_MAP: dict[str, str] = {
    "install-antigravity": "scripts/install-antigravity.sh",
    "workstation-sync": "scripts/workstation-sync.sh",
    "workstation-backup": "scripts/workstation-backup.sh",
    "workstation-audit": "scripts/workstation-audit.sh",
    "workstation-restore": "scripts/workstation-restore.sh",
}


def dispatch_c1(repo_dir: Path, dry_run: bool, subcmd: str, rest: list[str]) -> dict[str, Any]:
    """Execute C1 read-only discovery & horizon inspection subcommands."""
    if subcmd == "list-templates":
        tdir = Path(rest[0]).resolve() if rest and not rest[0].startswith("-") else repo_dir
        root_m = load_node_manifest(tdir)
        mounted = [
            {**e, "relative_path": str(e.get("relative_path") or f"layers/{e.get('name', '')}")}
            for e in root_m.get("mounted_layers", [])
            if isinstance(e, dict)
        ]
        cat = discover_templates_catalog(tdir, mounted)
        sub_dirs = [
            tdir / str(x["relative_path"])
            for x in mounted
            if (tdir / str(x["relative_path"])).is_dir()
        ]
        ms = [load_node_manifest(d) for d in [tdir, *sub_dirs]]
        mcps = [x for m in ms for x in (m.get("federated_mcps") or []) if isinstance(x, dict)]
        sbs = [b for m in ms for b in (m.get("surface_bindings") or []) if isinstance(b, dict)]
        bots = [
            b["ephemeral_fork_policy"]
            for b in sbs
            if isinstance(b.get("ephemeral_fork_policy"), dict)
        ]
        return {
            "count": len(cat),
            "templates": cat,
            "federated_mcps": mcps,
            "ephemeral_bots": bots,
        }
    if subcmd == "status":
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, ("--parent-dir",))
        return inspect_workspace_status(repo_dir, tdir, parent_dir=opt_path(opts, "parent_dir"))
    if subcmd == "inspect-horizon":
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, ("--parent-dir", "--email"))
        return horizon.inspect_layer_horizon(
            repo_dir,
            tdir,
            parent_dir=opt_path(opts, "parent_dir"),
            actor_email=opt_str(opts, "email"),
        )
    if subcmd == "compare-upstream":
        tdir, opts = parse_pos_and_options(
            repo_dir, subcmd, rest, ("--parent-dir", "--template"), ("--apply-safe",)
        )
        return horizon.compare_upstream_templates(
            repo_dir,
            tdir,
            parent_dir=opt_path(opts, "parent_dir"),
            template_filter=opt_str(opts, "template"),
            apply_upstream_only=bool(opts.get("apply_safe", False)),
            dry_run=dry_run,
        )
    if subcmd == "diff-project":
        tdir = require_pos_path(rest, "diff-project <target-project-dir> [--parent-dir <dir>]")
        opts = parse_cli_options(subcmd, rest[1:], ("--parent-dir",))
        p_opt = opt_path(opts, "parent_dir")
        bdir = tdir if (tdir / NODE_MANIFEST_REL_PATH).is_file() else (p_opt or repo_dir)
        return horizon.diff_project_against_layers(bdir, tdir)
    if subcmd == "lint-arch":
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, (), ("--no-tests",))
        return arch_linter.lint_architecture(tdir, check_tests=not bool(opts.get("no_tests")))
    if subcmd == "check-authority":
        vf: tuple[str, ...] = ("--op", "--email", "--file", "--parent-dir")
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf)
        op = require_opt_str(opts, "op", "Missing required --op <operation> for check-authority.")
        verdict = authority.verify_layer_operation_authority(
            tdir,
            operation=op,
            actor_email=opt_str(opts, "email"),
            target_rel_path=opt_str(opts, "file"),
            parent_dir=opt_path(opts, "parent_dir"),
        )
        if not verdict["allowed"]:
            raise CLIAuthorityBlockedError(verdict, str(verdict["remediation"]))
        return verdict
    vf = ("--layer", "--query", "--path", "--tier", "--parent-dir")
    tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf)
    u_msg = "Usage: zcg consult-layer [<dir>] --layer <id> --query <text>"
    return promotion.consult_layer_ephemeral(
        repo_dir,
        tdir,
        target_layer=require_opt_str(opts, "layer", u_msg),
        query=require_opt_str(opts, "query", u_msg),
        target_path=str(opts.get("path", "corporate/policy.md")),
        model_tier=str(opts.get("tier", "flash")),
        parent_dir=opt_path(opts, "parent_dir"),
        dry_run=dry_run,
    )


def dispatch_subtree(repo_dir: Path, dry_run: bool, subcmd: str, rest: list[str]) -> dict[str, Any]:
    """Execute mounted subtree listing, registration, and rollup synchronization subcommands."""
    act, args = subcmd, rest
    if subcmd == "subtree":
        if not rest or rest[0] not in ("list", "pull", "pull-all", "register"):
            raise CLIUsageError("Usage: zcg subtree <list|pull|pull-all|register> [args]")
        act = (
            "subtree-list"
            if rest[0] == "list"
            else ("register-subtree" if rest[0] == "register" else "subtree-pull-all")
        )
        args = rest[1:]
    if act == "register-subtree":
        if len(args) < 2:
            raise CLIUsageError("Usage: zcg subtree register <layer-name> <repo-url> [branch]")
        enforce_cli_authority(repo_dir, "register-subtree")
        return bootstrap.register_mounted_subtree(
            repo_dir, args[0], args[1], args[2] if len(args) >= 3 else "master", dry_run=dry_run
        )
    tdir = Path(args[0]).resolve() if args and not args[0].startswith("-") else repo_dir
    m = load_node_manifest(tdir)
    mounts = [e for e in (m.get("mounted_layers") or []) if isinstance(e, dict)]
    if act == "subtree-list":
        return {"workspace_dir": str(tdir), "mounted_layers": mounts, "count": len(mounts)}
    drifts = inspect_mounted_children_drifts(tdir, mounts)
    synced = sync_mounted_children_into_parent(tdir, mounts, dry_run=dry_run)
    return {"workspace_dir": str(tdir), "dry_run": dry_run, "drifts": drifts, "synced": synced}


def dispatch_workstation(
    repo_dir: Path, dry_run: bool, subcmd: str, rest: list[str]
) -> dict[str, Any]:
    """Execute Google Antigravity installer and Ubuntu physical workstation host scripts."""
    script_path = repo_dir / _WORKSTATION_SCRIPT_MAP[subcmd]
    if not script_path.is_file():
        raise CLIUsageError(f"Missing workstation script: {script_path}")
    cmd_args = [
        a for a in rest if not (dry_run and subcmd == "workstation-audit" and a == "--clean")
    ]
    if dry_run and subcmd != "workstation-audit":
        cmd_args = [*cmd_args, "--dry-run"]
    proc = subprocess.run(  # noqa: S603
        [str(script_path), *cmd_args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "ZCG_ENGINE_DIR": str(repo_dir), "NO_COLOR": "1"},
    )
    return {
        "subcommand": subcmd,
        "script": str(script_path),
        "dry_run": dry_run,
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "output": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
