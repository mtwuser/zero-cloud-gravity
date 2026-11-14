"""Mounted subtree registrar, one-shot node bootstrapper, and template synchronizer.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import shutil
import subprocess
from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

from zcg.cockpit.lifecycle import manage_plugin_service
from zcg.cockpit.workstation import PROFILE_TEMPLATE_CHAIN, register_antigravity_workspace
from zcg.core import blueprints, constants, epistemics, manifests, surface_composer
from zcg.governance import horizon, scaffolder
from zcg.topology import identity, posture, subtrees

if TYPE_CHECKING:
    from pathlib import Path

STUB_README_MAX_LINES: int = 10


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def _find_tpl(roots: list[Path], name: str) -> Path | None:
    return next((d for r in roots if (d := manifests.resolve_template_dir(r, name))), None)


def _tpl_doc(roots: list[Path], name: str) -> dict[str, Any]:
    td = _find_tpl(roots, name)
    tj = td / "template.json" if td else None
    res: dict[str, Any] = json.loads(tj.read_text("utf-8")) if tj and tj.is_file() else {}
    return res


def _is_incompatible_root_plugin(name: str, role: str, roots: list[Path], kind: str = "") -> bool:
    doc = {} if kind == "open-source" else _tpl_doc(roots, name)
    tr = doc.get("target_role")
    return doc.get("kind") == "plugin-stack" and tr in ("workstation", "corporate") and tr != role


def register_mounted_subtree(
    repo_dir: Path, layer_name: str, repo_url: str, branch: str = "master", *, dry_run: bool = False
) -> dict[str, Any]:
    """Upsert a mounted subtree entry inside system/zcg-node.json -> mounted_layers."""
    if not constants.KEBAB_ID_RE.match(layer_name):
        raise ValueError(f"Invalid layer_name {layer_name!r}")
    root_manifest_path = repo_dir / constants.NODE_MANIFEST_REL_PATH
    if not root_manifest_path.is_file():
        raise ValueError(f"Missing root manifest: {root_manifest_path}")
    root_m = manifests.load_node_manifest(repo_dir)
    sub_m = manifests.load_node_manifest(repo_dir / "layers" / layer_name)
    reg_info = constants.DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY.get(layer_name, {})
    is_know = layer_name.startswith(constants.VALID_KNOWLEDGE_PREFIXES)
    sub_role = str(sub_m.get("layer_role") or ("knowledge" if is_know else "department"))
    eff_url = repo_url or str(reg_info.get("public_url", ""))
    role_prec = constants.ROLE_DEFAULT_PRECEDENCE
    sub_prec = int(sub_m.get("precedence", role_prec.get(sub_role, role_prec["department"])))
    reg_extra = {
        "public_url": eff_url,
        "canonical_authority_url": str(reg_info.get("canonical_authority_url", eff_url)),
        "stewardship_stage": str(reg_info.get("stewardship_stage", "public-community")),
    } if reg_info else {}  # fmt: skip
    entry: dict[str, Any] = {
        "name": layer_name, "layer_id": str(sub_m.get("layer_id") or layer_name),
        "layer_role": sub_role, "branch": branch, "precedence": sub_prec, **reg_extra,
        "repository": eff_url,
    }  # fmt: skip
    existing = [
        x for x in root_m.get("mounted_layers", [])
        if isinstance(x, dict) and x.get("name") != layer_name
    ]  # fmt: skip
    existing.append(entry)
    svc_prec = role_prec["service-node"]
    existing.sort(key=lambda it: (int(it.get("precedence", svc_prec)), str(it.get("name", ""))))
    root_m["mounted_layers"] = existing
    if not dry_run:
        _write_json(root_manifest_path, root_m)
    return {"registered_layer": entry, "total_mounted_layers": len(existing), "dry_run": dry_run}


def _sync_templates_from_roots(
    target_dir: Path, effective_parent: Path, repo_dir: Path, tpl_names: list[str], *,
    skip_id: str = "", check_newer: bool = False, strategy: str = "accept-upstream",
    dry_run: bool = False,
) -> tuple[list[str], list[dict[str, Any]]]:  # fmt: skip
    same_p = effective_parent.resolve() == repo_dir.resolve()
    roots = [repo_dir] if same_p else [effective_parent, repo_dir]
    expanded = list(dict.fromkeys(t for t in tpl_names if t and t != skip_id))
    for tpl_name in list(expanded):
        cur = tpl_name
        while (
            (ext := str(_tpl_doc(roots, cur).get("extends") or ""))
            and ext != skip_id
            and ext not in expanded
        ):
            expanded.insert(expanded.index(tpl_name), ext)
            cur = ext
    copied, conflicts = list[str](), list[dict[str, Any]]()
    for tpl_name in expanded:
        src_tpl = _find_tpl(roots, tpl_name)
        dest_tpl = manifests.resolve_template_dest_dir(target_dir, tpl_name, src_tpl=src_tpl)
        local_tpl = manifests.resolve_template_dir(target_dir, tpl_name) or dest_tpl
        if src_tpl is not None and src_tpl.resolve() != dest_tpl.resolve():
            is_newer = check_newer and subtrees.is_dest_template_newer(src_tpl, local_tpl)
            did_copy, c_list = horizon.reconcile_template_pack_sync(
                target_dir, tpl_name, src_tpl, dest_tpl,
                strategy=strategy, is_local_newer=is_newer, dry_run=dry_run,
            )  # fmt: skip
            if did_copy:
                copied.append(tpl_name)
            conflicts.extend(c_list)
    return copied, conflicts


def bootstrap_node_workspace(
    repo_dir: Path, target_dir: Path, *, layer_id: str, layer_role: str | None = None,
    purpose: str | None = None, from_parent: str | None = None,
    precedence: int | None = None, description: str | None = None,
    upstream_repo: str | None = None, upstream_branch: str = "master",
    upstream_layer_id: str | None = None, parent_dir: Path | None = None,
    templates: list[str] | None = None, own_template_name: str | None = None,
    entity_kind: str | None = None, governing_root_id: str | None = None,
    interaction_language: str | None = None, scaffold_own_template: bool = True,
    home_dir: Path | None = None, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """One-shot initializer for a sovereign or managed Zero-Cloud Node workspace."""
    if not constants.KEBAB_ID_RE.match(layer_id):
        raise ValueError(f"Invalid layer_id {layer_id!r}")
    arch = posture.resolve_purpose_archetype(purpose, layer_role=layer_role) if purpose else None
    eff_role = str(arch["default_role"]) if arch else (layer_role or "department")
    if eff_role not in constants.VALID_LAYER_ROLES:
        raise ValueError(f"Invalid layer_role {eff_role!r}")
    entity_kind = entity_kind or (str(arch["default_entity_kind"]) if arch else None)
    role_prec = constants.ROLE_DEFAULT_PRECEDENCE
    eff_prec = precedence if precedence is not None else role_prec.get(eff_role, 80)
    stack = ExitStack()
    try:
        rem_p = stack.enter_context(posture.open_parent_source(from_parent, branch=upstream_branch))
        eff_pdir = rem_p[0] if rem_p is not None else parent_dir
        if rem_p is not None and rem_p[1] == "git-remote":
            upstream_repo = upstream_repo or str(from_parent).strip()
        eff_parent, inherited_templates = eff_pdir or repo_dir, list[str]()
        if (eff_parent / constants.NODE_MANIFEST_REL_PATH).is_file():
            pm = manifests.load_node_manifest(eff_parent)
            p_ent = identity.resolve_node_entity_identity(eff_parent, pm)
            p_role = pm.get("layer_role")
            non_oss = p_ent["entity_kind"] != "open-source"
            if non_oss and (eff_pdir or p_role not in (None, "workstation")):
                entity_kind = entity_kind or str(p_ent["entity_kind"])
                def_root = p_ent["governing_root_id"] or pm.get("layer_id", eff_parent.name)
                governing_root_id = governing_root_id or str(def_root)
                upstream_layer_id = upstream_layer_id or pm.get("layer_id")
                interaction_language = interaction_language or pm.get("interaction_language")
                upstream_repo = upstream_repo or pm.get("repository")
                if not upstream_repo and (eff_parent / ".git").exists():
                    git_bin = shutil.which("git") or "/usr/bin/git"
                    proc = subprocess.run(  # noqa: S603
                        [git_bin, "config", "--get", "remote.origin.url"],
                        cwd=eff_parent, check=False, capture_output=True, text=True,
                    )  # fmt: skip
                    upstream_repo = proc.stdout.strip() or None
                raw_inh = [str(pt) for pt in pm.get("default_stack_templates", [])]
                inherited_templates = scaffolder.merge_unique_strings([
                    pt for pt in raw_inh
                    if not _is_incompatible_root_plugin(pt, eff_role, [eff_parent, repo_dir])
                ])  # fmt: skip
        ind_chain = (*PROFILE_TEMPLATE_CHAIN["academic"], *PROFILE_TEMPLATE_CHAIN["technical"])
        is_ind = entity_kind == "individual"
        ind_def = [tp for tp, _ in ind_chain if tp != "universal-base"] if is_ind else []
        arch_tpls = list(arch["default_templates"]) if arch else []
        dom_cls = epistemics.classify_knowledge_domain(layer_id, eff_role)
        dom_def = arch_tpls or dom_cls["default_stack_templates"] or ind_def
        was_unboot = not (target_dir / constants.NODE_MANIFEST_REL_PATH).is_file()
        pub_reg = constants.DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY
        know_mounts = [t for t in (templates or []) if t in pub_reg and t != layer_id]
        tpl_inputs = [t for t in (templates or []) if t not in know_mounts]
        req_tpls = scaffolder.merge_unique_strings(inherited_templates, tpl_inputs or dom_def)
        sync_args = (target_dir, eff_parent, repo_dir, req_tpls)
        copied_templates, _ = _sync_templates_from_roots(*sync_args, dry_run=dry_run)
        manifest_res = scaffolder.configure_node_manifest(
            target_dir, layer_id=layer_id, layer_role=eff_role, dry_run=dry_run,
            precedence=eff_prec, description=description, prune_default_templates=True,
            upstream_url=upstream_repo, upstream_branch=upstream_branch, entity_kind=entity_kind,
            upstream_id=upstream_layer_id, governing_root_id=governing_root_id,
            interaction_language=interaction_language,
        )  # fmt: skip
        p_ext = {"governance_posture": arch["default_governance_posture"]} if arch else {}
        s_roots = (eff_parent, repo_dir)
        lin = blueprints.resolve_template_lineage_chain(req_tpls, s_roots)
        req_lin, ent_s = {n for n, _ in lin} | set(req_tpls), str(entity_kind or "")
        def_cockpit = blueprints.resolve_default_cockpit_plugin(eff_role, ent_s, req_tpls, s_roots)
        has_plug = surface_composer.has_active_plugin_stack(req_tpls, (target_dir, *s_roots))
        own_tpl_id = own_template_name or layer_id
        all_tpls = scaffolder.merge_unique_strings(
            req_tpls, [own_tpl_id] if scaffold_own_template else [],
            [] if has_plug else [def_cockpit],
        )  # fmt: skip
        manifest_res = {**manifest_res, **p_ext, "default_stack_templates": list(all_tpls)}
        if not dry_run:
            _write_json(target_dir / constants.NODE_MANIFEST_REL_PATH, manifest_res)
        for km in know_mounts if not dry_run else ():
            register_mounted_subtree(target_dir, km, "")
        is_se_sq = eff_role == "squad" and "software-engineering" in req_lin
        own_kind = "framework-stack" if is_se_sq else "context-stack"
        scaffold_res = (
            scaffolder.scaffold_template_pack(
                target_dir, template_name=own_tpl_id, kind=own_kind, dry_run=dry_run,
                description=description or f"{layer_id} ({eff_role}) governance pack",
                register_binding=True, rule_filename=f"{own_tpl_id}.md",
            )
            if scaffold_own_template else None
        )  # fmt: skip
        if not dry_run:
            manifest_res = manifests.load_node_manifest(target_dir)
        ag_rule = (
            f'---\ntrigger: always_on\ndescription: "Rules for {layer_id} ({eff_role})."\n---\n\n'
            f"# {layer_id} Node Rules (`{eff_role}`, `precedence: {eff_prec}`)\n\n"
            f"> Governed by `{constants.NODE_MANIFEST_REL_PATH}` (`layer_id: {layer_id}`).\n\n"
            f"## Scope & Surface Target\n- Governs `{layer_id}` (`{eff_role}`).\n\n"
            f"## Normative Invariants\n- Respect *Lex Superior* (`0..100`) & `{own_tpl_id}`.\n\n"
            "## Verification & Sign-Off Gates\n"
            "- [ ] Verify `zcg diff-project` parity before commit.\n"
        )
        m_lang = manifest_res.get("interaction_language") or interaction_language
        eff_lang = str(m_lang or constants.DEFAULT_INTERACTION_LANGUAGE)
        readme_md = blueprints.render_layer_onboarding_readme(
            layer_id, eff_role, eff_prec, own_tpl_id, all_tpls, upstream_layer_id,
            entity_kind=entity_kind, interaction_language=eff_lang,
        )  # fmt: skip
        ag_plain = f"{manifests.strip_markdown_frontmatter(ag_rule)}\n"
        baseline_files = {
            ".gitignore": "__pycache__/\n*.pyc\n.ruff_cache/\n.mypy_cache/\n.pytest_cache/\n"
            "logs/\n.agents/runtime/\n.agents/telemetry/\n.agents/SESSION.md\n",
            "layers/.gitkeep": "", "README.md": readme_md,
            "WORKTASK.md": f"# Active Work Tasks — {layer_id}\n\n- [x] Initial layer bootstrap.\n"
            "- [ ] Complete `Layer Setup Blueprint` in `README.md` and run Kickoff Prompt.\n",
            "antigravity/.gemini/config/AGENTS.md": ag_plain,
            "BACKLOG.md": f"# Backlog & In-Flight Maintainability Ledger — {layer_id}\n\n",
            "CHANGELOG.md": f"# Changelog — {layer_id}\n\n## [Unreleased]\n- Initial bootstrap.\n",
        }  # fmt: skip
        created_baseline: list[str] = []
        for rel_path, content in baseline_files.items():
            dest_file = target_dir / rel_path
            is_stub = (
                was_unboot and rel_path == "README.md" and dest_file.is_file()
                and len(dest_file.read_text("utf-8").splitlines()) < STUB_README_MAX_LINES
            )  # fmt: skip
            if not dest_file.exists() or is_stub:
                created_baseline.append(rel_path)
                if not dry_run:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_text(content, encoding="utf-8")
        had_mk = (target_dir / "Makefile").exists()
        p_info = posture.resolve_governance_posture(target_dir, manifest_res, parent_dir=eff_pdir)
        mk_boot = surface_composer.sync_workspace_makefile(
            target_dir, layer_id=layer_id, layer_role=eff_role, effective_parent=eff_parent,
            repo_dir=repo_dir, active_templates=all_tpls,
            purpose=arch["purpose"] if arch else None,
            allow_external_links=bool(p_info["allow_external_peer_links"]), dry_run=dry_run,
        )  # fmt: skip
        mk_files = [f for f in mk_boot["files_written"] if f != "Makefile" or not had_mk]
        created_baseline.extend(mk_files)
        for sub_d in ("reference", "architecture", "guides") if not dry_run else ():
            (target_dir / "docs" / sub_d).mkdir(parents=True, exist_ok=True)
            (target_dir / "docs" / sub_d / ".gitkeep").touch(exist_ok=True)
        tpl_ref_arg = ",".join(all_tpls) or None
        apply_res: dict[str, Any] = {"applied_template": tpl_ref_arg, "files_materialized": []}
        cockpit_res: dict[str, Any] = {"services": []}
        if not dry_run:
            apply_res = scaffolder.apply_templates_to_project(
                target_dir, target_dir, template_ref=tpl_ref_arg, layers_filter=["all"],
                engine_dir=repo_dir, dry_run=False,
            )  # fmt: skip
            cockpit_res = manage_plugin_service(
                target_dir, action="activate", target_env="dev", parent_dir=eff_parent
            )  # fmt: skip
        ide_reg = register_antigravity_workspace(target_dir, home_dir=home_dir, dry_run=dry_run)
        topo_out = ((cockpit_res.get("services") or [{}])[0].get("intranet_topology")) or {}
        c_url, d_url = topo_out.get("localhost_url"), topo_out.get("local_subdomain_dashboard_url")
        return {
            "target_dir": str(target_dir), "layer_id": layer_id, "dry_run": dry_run,
            "layer_role": eff_role, "purpose": arch["purpose"] if arch else None,
            "precedence": eff_prec, "active_cockpit_url": c_url, "active_dashboard_url": d_url,
            "antigravity_workspace": ide_reg, "copied_templates": copied_templates,
            "scaffolded_template": scaffold_res["template_id"] if scaffold_res else None,
            "baseline_files_created": sorted(created_baseline),
            "applied_template": apply_res.get("applied_template"), "manifest": manifest_res,
            "files_materialized": apply_res.get("files_materialized", []),
        }  # fmt: skip
    finally:
        stack.close()


def sync_node_workspace(
    repo_dir: Path, target_dir: Path, *, parent_dir: Path | None = None,
    templates: list[str] | None = None, strategy: str = "reconcile", dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Propagate upstream template updates into target_dir/templates/ and refresh .agents/."""
    if strategy not in constants.VALID_SYNC_STRATEGIES:
        raise ValueError(f"Invalid sync strategy {strategy!r}")
    manifest_path = target_dir / constants.NODE_MANIFEST_REL_PATH
    if not manifest_path.is_file():
        raise ValueError(f"Missing target node manifest: {manifest_path}")
    manifest = manifests.load_node_manifest(target_dir)
    own_id, ent_k = str(manifest.get("layer_id") or ""), str(manifest.get("entity_kind") or "")
    own_role = str(manifest.get("layer_role") or "department")
    eff_parent = identity.resolve_default_parent_dir(target_dir, parent_dir) or repo_dir
    s_roots = [target_dir, eff_parent, repo_dir]
    raw_def = [str(t) for t in manifest.get("default_stack_templates", [])]
    def_tpls = [t for t in raw_def if not _is_incompatible_root_plugin(t, own_role, s_roots, ent_k)]
    pruned_root = len(def_tpls) != len(raw_def)
    stack_templates = scaffolder.merge_unique_strings(def_tpls, templates or [])
    p_arg = eff_parent if eff_parent != repo_dir else None
    ent_id = identity.resolve_node_entity_identity(target_dir, manifest, parent_dir=p_arg)
    resolved_root = ent_id["governing_root_id"]
    stale_rev = manifest.get("schema_version") != constants.NODE_MANIFEST_CONTRACT_REV
    root_backfill = (manifest.get("governing_root_id") != resolved_root) and bool(resolved_root)
    env_backfill = scaffolder.ensure_canonical_environments(manifest, own_id)
    dirty_m = stale_rev or bool(templates) or root_backfill or env_backfill or pruned_root
    if not dry_run and dirty_m:
        manifest["schema_version"] = constants.NODE_MANIFEST_CONTRACT_REV
        manifest["layer_role"] = own_role
        manifest["default_stack_templates"] = list(stack_templates)
        if root_backfill:
            manifest["governing_root_id"] = resolved_root
        _write_json(manifest_path, manifest)
    existing_tpls = [
        n for n, _p in manifests.iter_layer_template_dirs(target_dir)
        if own_role == "workstation" or n not in constants.CANONICAL_STARTER_TEMPLATES
    ]  # fmt: skip
    candidate_tpls = list(dict.fromkeys([*stack_templates, *existing_tpls]))
    synced_templates, conflicts = _sync_templates_from_roots(
        target_dir, eff_parent, repo_dir, candidate_tpls,
        skip_id=own_id, check_newer=True, strategy=strategy, dry_run=dry_run,
    )  # fmt: skip
    active_set = {*candidate_tpls, *synced_templates}
    tpl_rev = constants.TEMPLATE_MANIFEST_CONTRACT_REV
    for tname, tdir in manifests.iter_layer_template_dirs(target_dir) if not dry_run else ():
        if tname in constants.CANONICAL_STARTER_TEMPLATES and tname not in active_set:
            shutil.rmtree(tdir, ignore_errors=True)
        else:
            manifests.stamp_schema_rev(tdir / "template.json", tpl_rev)
    if (
        not dry_run
        and (own_td := manifests.resolve_template_dir(target_dir, own_id))
        and (ag_r := target_dir / ".agents/rules" / f"{own_id}.md").is_file()
        and (tpl_r := own_td / "rules" / f"{own_id}.md").is_file()
        and ag_r.stat().st_mtime_ns > tpl_r.stat().st_mtime_ns
    ):
        shutil.copy2(ag_r, tpl_r)
    synced_children = subtrees.sync_mounted_children_into_parent(
        target_dir, manifest.get("mounted_layers", []), dry_run=dry_run
    )
    p_info = posture.resolve_governance_posture(target_dir, manifest, parent_dir=p_arg)
    mk_sync = surface_composer.sync_workspace_makefile(
        target_dir, layer_id=own_id, layer_role=own_role, effective_parent=eff_parent,
        repo_dir=repo_dir, active_templates=stack_templates,
        allow_external_links=bool(p_info["allow_external_peer_links"]), dry_run=dry_run,
    )  # fmt: skip
    plugin_svcs = [
        {"template": t, **rs} for t in stack_templates
        if isinstance(rs := _tpl_doc([target_dir, repo_dir], t).get("runtime_service"), dict)
    ]  # fmt: skip
    apply_res = scaffolder.apply_templates_to_project(
        target_dir, target_dir, template_ref=",".join(stack_templates) or None,
        layers_filter=["all"], engine_dir=repo_dir, dry_run=dry_run,
    )  # fmt: skip
    return {
        "target_dir": str(target_dir), "layer_id": own_id, "strategy": strategy,
        "dry_run": dry_run, "makefile_upgraded": bool(mk_sync["makefile_upgraded"]),
        "synced_templates": synced_templates, "reconciliation_conflicts": conflicts,
        "synced_mounted_layers": synced_children, "plugin_services_redeployed": plugin_svcs,
        "applied_template": apply_res.get("applied_template"),
        "pruned_plugins": apply_res.get("pruned_plugins", []),
        "files_materialized": apply_res.get("files_materialized", []),
        "participating_layers": apply_res.get("participating_layers", []),
    }  # fmt: skip
