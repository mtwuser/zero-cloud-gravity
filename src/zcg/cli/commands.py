"""C2 Lifecycle and C3 Sovereign Governance command handlers for the 'zcg' CLI.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

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
    split_csv,
)
from zcg.cockpit.lifecycle import manage_plugin_service
from zcg.cockpit.plugin_sdk import scaffold_plugin_module
from zcg.cockpit.workstation import set_global_agents_profile
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.core.manifests import load_node_manifest
from zcg.governance import (
    authority,
    bootstrap,
    consensus,
    ledger,
    links,
    promotion,
    scaffolder,
    workflows,
)

C2_LIFECYCLE_SUBCOMMANDS: tuple[str, ...] = (
    "bootstrap", "bootstrap-workspace", "sync-layer", "apply-project",
    "set-global-profile", "start-task", "scaffold-template", "scaffold-plugin-module",
    "init-fork", "register-subtree", "link", "unlink", "spinout-project",
)  # fmt: skip
C3_GOVERNANCE_SUBCOMMANDS: tuple[str, ...] = (
    "complete-task", "delegate-to-child", "promote-from-project", "manage-roster",
    "set-authority", "configure-git-policy", "check-env-promotion", "record-decision",
)  # fmt: skip


def dispatch_c2(repo_dir: Path, dry_run: bool, subcmd: str, rest: list[str]) -> dict[str, Any]:
    """Execute C2 node lifecycle, bootstrap, sync, and template materialization subcommands."""
    if subcmd in ("bootstrap", "bootstrap-workspace"):
        tdir = require_pos_path(rest, f"{subcmd} <target-dir> --id <layer-id> [...]")
        vf: tuple[str, ...] = (
            "--id", "--role", "--precedence", "--description", "--parent-dir",
            "--upstream-url", "--upstream-id", "--upstream-branch", "--templates",
            "--template-name", "--entity-kind", "--governing-root", "--lang",
        )  # fmt: skip
        opts = parse_cli_options(subcmd, rest[1:], vf, ("--no-scaffold-own",))
        lid = require_opt_str(opts, "id", f"Missing required --id <layer-id> for {subcmd}.")
        return bootstrap.bootstrap_node_workspace(
            repo_dir,
            tdir,
            layer_id=lid,
            layer_role=str(opts.get("role", "department")),
            precedence=int(str(opts["precedence"])) if "precedence" in opts else None,
            description=opt_str(opts, "description"),
            upstream_repo=opt_str(opts, "upstream_url"),
            upstream_branch=str(opts.get("upstream_branch", "master")),
            upstream_layer_id=opt_str(opts, "upstream_id"),
            parent_dir=opt_path(opts, "parent_dir"),
            templates=split_csv(opts.get("templates")),
            own_template_name=opt_str(opts, "template_name"),
            entity_kind=opt_str(opts, "entity_kind"),
            governing_root_id=opt_str(opts, "governing_root"),
            interaction_language=opt_str(opts, "lang"),
            scaffold_own_template=not bool(opts.get("no_scaffold_own", False)),
            dry_run=dry_run,
        )
    if subcmd == "sync-layer":
        vf = ("--parent-dir", "--templates", "--strategy")
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf)
        return bootstrap.sync_node_workspace(
            repo_dir,
            tdir,
            parent_dir=opt_path(opts, "parent_dir"),
            templates=split_csv(opts.get("templates")),
            strategy=str(opts.get("strategy", "reconcile")),
            dry_run=dry_run,
        )
    if subcmd == "apply-project":
        tdir = require_pos_path(rest, "apply-project <target-project-dir> [options]")
        vf = ("--template", "--layers", "--parent-dir", "--service-action", "--env", "--email")
        opts = parse_cli_options(subcmd, rest[1:], vf, ("--include-defaults",))
        p_dir, mp = opt_path(opts, "parent_dir"), tdir / NODE_MANIFEST_REL_PATH
        if opts.get("service_action"):
            eff_em = opt_str(opts, "email") or authority.resolve_git_user_email(tdir)
            return manage_plugin_service(
                tdir,
                action=str(opts["service_action"]),
                plugin_id=opt_str(opts, "template"),
                target_env=str(opts.get("env", "dev")),
                actor_email=eff_em,
                parent_dir=p_dir,
                dry_run=dry_run,
            )
        is_non_ws = mp.is_file() and load_node_manifest(tdir).get("layer_role") != "workstation"
        bdir = p_dir if p_dir is not None else (tdir if is_non_ws else repo_dir)
        inc_def = bool(opts.get("include_defaults", False)) or p_dir is not None or is_non_ws
        return scaffolder.apply_templates_to_project(
            bdir,
            tdir,
            template_ref=opt_str(opts, "template"),
            layers_filter=split_csv(opts.get("layers")),
            include_layer_defaults=inc_def,
            engine_dir=repo_dir,
            dry_run=dry_run,
        )
    if subcmd == "set-global-profile":
        if not rest or rest[0].startswith("-"):
            raise CLIUsageError("Usage: zcg set-global-profile <profile> [--lang <code>] [--stow]")
        opts = parse_cli_options(subcmd, rest[1:], ("--lang", "--workstation-dir"), ("--stow",))
        return set_global_agents_profile(
            repo_dir,
            rest[0],
            interaction_language=opt_str(opts, "lang"),
            workstation_dir=opt_path(opts, "workstation_dir"),
            run_stow=bool(opts.get("stow", False)),
            dry_run=dry_run,
        )
    if subcmd == "start-task":
        vf = ("--task", "--tracker", "--ticket", "--prefix")
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf)
        return workflows.start_task_workflow(
            tdir,
            task_query=require_opt_str(opts, "task", "Usage: zcg start-task [<dir>] --task <id>"),
            tracker=str(opts.get("tracker", "WORKTASK.md")),
            ticket_id=opt_str(opts, "ticket"),
            branch_prefix=str(opts.get("prefix", "feature")),
            dry_run=dry_run,
        )
    if subcmd == "scaffold-template":
        if not rest or rest[0].startswith("-"):
            raise CLIUsageError("Usage: zcg scaffold-template <template-name> [options]")
        vf = ("--kind", "--description", "--rule-file")
        opts = parse_cli_options(subcmd, rest[1:], vf, ("--register-binding",))
        enforce_cli_authority(repo_dir, "scaffold-template")
        return scaffolder.scaffold_template_pack(
            repo_dir,
            template_name=rest[0],
            kind=str(opts.get("kind", "framework-stack")),
            description=opt_str(opts, "description"),
            register_binding=bool(opts.get("register_binding", False)),
            rule_filename=opt_str(opts, "rule_file"),
            dry_run=dry_run,
        )
    if subcmd == "scaffold-plugin-module":
        if len(rest) < 2 or rest[0].startswith("-") or rest[1].startswith("-"):
            raise CLIUsageError(
                "Usage: zcg scaffold-plugin-module <plugin-id> <module-name> [options]"
            )
        opts = parse_cli_options(subcmd, rest[2:], ("--prefix", "--description"))
        enforce_cli_authority(repo_dir, "scaffold-plugin-module")
        return scaffold_plugin_module(
            repo_dir,
            plugin_id=rest[0],
            module_name=rest[1],
            route_prefix=opt_str(opts, "prefix"),
            description=opt_str(opts, "description"),
            dry_run=dry_run,
        )
    if subcmd == "init-fork":
        vf = (
            "--id", "--role", "--precedence", "--description", "--upstream-url",
            "--upstream-id", "--upstream-branch", "--entity-kind", "--governing-root", "--lang",
        )  # fmt: skip
        opts = parse_cli_options(subcmd, rest, vf, ("--prune-default-templates",))
        lid = require_opt_str(opts, "id", "Missing required --id <layer-id> for init-fork.")
        enforce_cli_authority(repo_dir, "init-fork")
        manifest = scaffolder.configure_node_manifest(
            repo_dir,
            layer_id=lid,
            layer_role=str(opts.get("role", "squad")),
            precedence=int(str(opts["precedence"])) if "precedence" in opts else None,
            description=opt_str(opts, "description"),
            upstream_url=opt_str(opts, "upstream_url"),
            upstream_id=opt_str(opts, "upstream_id"),
            upstream_branch=opt_str(opts, "upstream_branch"),
            entity_kind=opt_str(opts, "entity_kind"),
            governing_root_id=opt_str(opts, "governing_root"),
            interaction_language=opt_str(opts, "lang"),
            prune_default_templates=bool(opts.get("prune_default_templates", False)),
            dry_run=dry_run,
        )
        return {"dry_run": dry_run, "manifest": manifest}
    if subcmd == "link":
        vf = ("--target", "--relation", "--ref", "--url", "--packs", "--description")
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf)
        tgt = require_opt_str(opts, "target", "Usage: zcg link [<dir>] --target <node-id>")
        return links.link_node(
            tdir,
            target_id=tgt,
            relation=str(opts.get("relation", "lateral-peer")),
            target_ref=str(opts.get("ref", "")),
            cockpit_url=str(opts.get("url", "")),
            shared_packs=split_csv(opts.get("packs")),
            description=str(opts.get("description", "")),
            dry_run=dry_run,
        )
    if subcmd == "unlink":
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, ("--target",))
        tgt = require_opt_str(opts, "target", "Usage: zcg unlink [<dir>] --target <node-id>")
        return links.unlink_node(tdir, target_id=tgt, dry_run=dry_run)
    if subcmd == "spinout-project":
        tdir = require_pos_path(rest, "spinout-project <target-dir> --id <id> --from-branch <ref>")
        vf = (
            "--id", "--from-branch", "--source-dir", "--role", "--precedence",
            "--description", "--templates", "--packs",
        )  # fmt: skip
        opts = parse_cli_options(subcmd, rest[1:], vf)
        pid = require_opt_str(opts, "id", "Missing required --id <project-id> for spinout-project.")
        br = require_opt_str(opts, "from_branch", "Missing required --from-branch <branch>.")
        src_d = opt_path(opts, "source_dir") or repo_dir
        return links.spinout_branch_to_project(
            repo_dir,
            src_d,
            tdir,
            project_id=pid,
            from_branch=br,
            layer_role=str(opts.get("role", "project")),
            precedence=int(str(opts.get("precedence", 80))),
            description=opt_str(opts, "description"),
            templates=split_csv(opts.get("templates")),
            shared_packs=split_csv(opts.get("packs")),
            dry_run=dry_run,
        )
    if len(rest) < 2:
        raise CLIUsageError("Usage: zcg register-subtree <layer-name> <repo-url> [branch]")
    enforce_cli_authority(repo_dir, "register-subtree")
    return bootstrap.register_mounted_subtree(
        repo_dir, rest[0], rest[1], rest[2] if len(rest) >= 3 else "master", dry_run=dry_run
    )


def dispatch_c3(repo_dir: Path, dry_run: bool, subcmd: str, rest: list[str]) -> dict[str, Any]:
    """Execute C3 sovereign governance, delegation, promotion, RBAC, and env-gate subcommands."""
    if subcmd == "complete-task":
        vf: tuple[str, ...] = (
            "--task", "--deliverable", "--summary", "--tracker", "--parent-dir", "--email",
        )  # fmt: skip
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf, ("--create-pr",))
        return workflows.complete_task_workflow(
            tdir,
            task_query=require_opt_str(
                opts, "task", "Usage: zcg complete-task [<dir>] --task <id>"
            ),
            deliverable=str(opts.get("deliverable", "")),
            summary=str(opts.get("summary", "")),
            tracker=str(opts.get("tracker", "WORKTASK.md")),
            parent_dir=opt_path(opts, "parent_dir"),
            actor_email=opt_str(opts, "email"),
            create_pr=bool(opts.get("create_pr", False)),
            dry_run=dry_run,
        )
    if subcmd == "delegate-to-child":
        vf = ("--to-child", "--task", "--source", "--ticket", "--priority", "--surface", "--email")
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf, ("--force", "--create-pr"))
        u_msg = "Usage: zcg delegate-to-child [<dir>] --to-child <layer> (--task <t>|--source <f>)"
        child = require_opt_str(opts, "to_child", u_msg)
        if not opts.get("task") and not opts.get("source"):
            raise CLIUsageError(u_msg)
        return workflows.delegate_directive_to_child(
            tdir,
            child_layer=child,
            directive=str(opts.get("task", "")),
            source_rel_path=opt_str(opts, "source"),
            ticket_id=opt_str(opts, "ticket"),
            priority=str(opts.get("priority", "P1")),
            tracker=str(opts.get("surface", "WORKTASK.md")),
            actor_email=opt_str(opts, "email"),
            force_overwrite=bool(opts.get("force", False)),
            create_pr=bool(opts.get("create_pr", False)),
            dry_run=dry_run,
        )
    if subcmd == "promote-from-project":
        tdir = require_pos_path(rest, "promote-from-project <target-project-dir> --source <path>")
        vf = (
            "--source", "--to-layer", "--to-template", "--upstream-dir",
            "--email", "--org", "--contributors", "--context",
        )  # fmt: skip
        opts = parse_cli_options(subcmd, rest[1:], vf, ("--create-pr", "--force"))
        src = require_opt_str(opts, "source", "Missing required --source <rel-path>.")
        return promotion.promote_project_asset_to_layer(
            repo_dir,
            tdir,
            source_rel_path=src,
            target_layer=str(opts.get("to_layer", "root")),
            target_template=opt_str(opts, "to_template"),
            upstream_dir=opt_path(opts, "upstream_dir"),
            prepare_pr=bool(opts.get("create_pr", False)),
            actor_email=opt_str(opts, "email"),
            contributing_org=opt_str(opts, "org"),
            contributors=opt_str(opts, "contributors"),
            validation_context=opt_str(opts, "context"),
            force_overwrite=bool(opts.get("force", False)),
            dry_run=dry_run,
        )
    if subcmd == "manage-roster":
        vf = ("--add", "--remove", "--role", "--title", "--squad")
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf, ("--no-codeowners",))
        return ledger.manage_layer_roster(
            tdir,
            add_email=opt_str(opts, "add"),
            remove_email=opt_str(opts, "remove"),
            member_role=str(opts.get("role", "member")),
            title=str(opts.get("title", "")),
            squad=str(opts.get("squad", "")),
            dry_run=dry_run,
        )
    if subcmd == "set-authority":
        vf = ("--owner-role", "--emails", "--contact")
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf)
        role = require_opt_str(opts, "owner_role", "Missing required --owner-role <role>.")
        return authority.configure_layer_authority(
            tdir,
            owner_role=role,
            authorized_emails=split_csv(opts.get("emails")) or [],
            escalation_contact=opt_str(opts, "contact"),
            dry_run=dry_run,
        )
    if subcmd == "configure-git-policy":
        bf = ("--no-codeowners", "--no-require-pr")
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, ("--protected",), bf)
        return ledger.configure_git_governance_policy(
            tdir,
            protected_branches=split_csv(opts.get("protected")),
            require_pr_on_protected=not bool(opts.get("no_require_pr", False)),
            sync_codeowners=not bool(opts.get("no_codeowners", False)),
            dry_run=dry_run,
        )
    if subcmd == "check-env-promotion":
        vf = ("--to-env", "--branch", "--email", "--parent-dir", "--files")
        tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf)
        eff_em = opt_str(opts, "email") or authority.resolve_git_user_email(tdir)
        u_msg = "Usage: zcg check-env-promotion [<dir>] --to-env <env>"
        res = consensus.evaluate_environment_promotion(
            tdir,
            target_env=require_opt_str(opts, "to_env", u_msg),
            current_branch=opt_str(opts, "branch"),
            actor_email=eff_em,
            parent_dir=opt_path(opts, "parent_dir"),
            changed_files=split_csv(opts.get("files")),
            dry_run=dry_run,
        )
        if not res["allowed"]:
            msg = "Environment promotion blocked: " + "; ".join(res["failed_gates"])
            raise CLIAuthorityBlockedError(res, msg)
        return res
    vf = ("--item", "--decision", "--reason", "--tracker", "--email")
    tdir, opts = parse_pos_and_options(repo_dir, subcmd, rest, vf)
    u_msg = "Usage: zcg record-decision [<dir>] --item <ref> --decision <dec> --reason <txt>"
    eff_em = opt_str(opts, "email") or authority.resolve_git_user_email(tdir)
    return ledger.record_governance_decision(
        tdir,
        item_ref=require_opt_str(opts, "item", u_msg),
        decision=require_opt_str(opts, "decision", u_msg),
        reason=require_opt_str(opts, "reason", u_msg),
        tracker=str(opts.get("tracker", "WORKTASK.md")),
        actor_email=eff_em,
        dry_run=dry_run,
    )
