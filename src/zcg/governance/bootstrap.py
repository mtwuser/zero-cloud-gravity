"""Mounted subtree registrar, one-shot node bootstrapper, and template synchronizer.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zcg.cockpit.lifecycle import manage_plugin_service
from zcg.cockpit.workstation import PROFILE_TEMPLATE_CHAIN, register_antigravity_workspace
from zcg.core.blueprints import (
    render_layer_makefile,
    render_layer_onboarding_readme,
    resolve_default_cockpit_plugin,
    resolve_template_lineage_chain,
)
from zcg.core.constants import (
    BUILTIN_COCKPIT_PLUGINS,
    CANONICAL_STARTER_TEMPLATES,
    DEFAULT_INTERACTION_LANGUAGE,
    DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY,
    KEBAB_ID_RE,
    MAKEFILE_CUSTOM_TARGETS_MARKER,
    MAKEFILE_ROLE_HEADER_PREFIX,
    NODE_MANIFEST_CONTRACT_REV,
    NODE_MANIFEST_REL_PATH,
    ROLE_DEFAULT_PRECEDENCE,
    TEMPLATE_MANIFEST_CONTRACT_REV,
    VALID_KNOWLEDGE_PREFIXES,
    VALID_LAYER_ROLES,
    VALID_SYNC_STRATEGIES,
)
from zcg.core.epistemics import classify_knowledge_domain
from zcg.core.manifests import (
    iter_layer_template_dirs,
    load_node_manifest,
    resolve_template_dest_dir,
    resolve_template_dir,
    stamp_schema_rev,
)
from zcg.governance.horizon import reconcile_template_pack_sync
from zcg.governance.scaffolder import (
    apply_templates_to_project,
    configure_node_manifest,
    ensure_canonical_environments,
    merge_unique_strings,
    scaffold_template_pack,
)
from zcg.topology.identity import resolve_default_parent_dir, resolve_node_entity_identity
from zcg.topology.subtrees import is_dest_template_newer, sync_mounted_children_into_parent

STUB_README_MAX_LINES: int = 10


def register_mounted_subtree(
    repo_dir: Path, layer_name: str, repo_url: str, branch: str = "master", *, dry_run: bool = False
) -> dict[str, Any]:
    """Upsert a mounted subtree entry inside system/zcg-node.json -> mounted_layers."""
    if not KEBAB_ID_RE.match(layer_name):
        raise ValueError(f"Invalid layer_name {layer_name!r}")
    root_manifest_path = repo_dir / NODE_MANIFEST_REL_PATH
    if not root_manifest_path.is_file():
        raise ValueError(f"Missing root manifest: {root_manifest_path}")
    root_m = load_node_manifest(repo_dir)
    sub_m = load_node_manifest(repo_dir / "layers" / layer_name)
    reg_info = DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY.get(layer_name, {})
    def_r = "knowledge" if layer_name.startswith(VALID_KNOWLEDGE_PREFIXES) else "department"
    sub_id = str(sub_m.get("layer_id") or layer_name)
    sub_role = str(sub_m.get("layer_role") or def_r)
    eff_url = repo_url or str(reg_info.get("public_url", ""))
    dept_prec = ROLE_DEFAULT_PRECEDENCE.get(sub_role, ROLE_DEFAULT_PRECEDENCE["department"])
    svc_prec = ROLE_DEFAULT_PRECEDENCE["service-node"]
    reg_extra = {
        "public_url": eff_url,
        "canonical_authority_url": str(reg_info.get("canonical_authority_url", eff_url)),
        "stewardship_stage": str(reg_info.get("stewardship_stage", "public-community")),
    } if reg_info else {}  # fmt: skip
    entry: dict[str, Any] = {
        "name": layer_name, "layer_id": sub_id, "layer_role": sub_role, "branch": branch,
        "precedence": int(sub_m.get("precedence", dept_prec)), **reg_extra, "repository": eff_url,
    }  # fmt: skip
    existing = [
        x for x in root_m.get("mounted_layers", [])
        if isinstance(x, dict) and x.get("name") != layer_name
    ]  # fmt: skip
    existing.append(entry)
    existing.sort(key=lambda it: (int(it.get("precedence", svc_prec)), str(it.get("name", ""))))
    root_m["mounted_layers"] = existing
    if not dry_run:
        m_txt = json.dumps(root_m, indent=2, ensure_ascii=False) + "\n"
        root_manifest_path.write_text(m_txt, "utf-8")
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
        while src_d := next((d for r in roots if (d := resolve_template_dir(r, cur))), None):
            tj = src_d / "template.json"
            ext = (
                str(json.loads(tj.read_text("utf-8")).get("extends") or "") if tj.is_file() else ""
            )
            if not ext or ext == skip_id or ext in expanded:
                break
            expanded.insert(expanded.index(tpl_name), ext)
            cur = ext
    copied, conflicts = list[str](), list[dict[str, Any]]()
    for tpl_name in expanded:
        src_tpl = next((d for r in roots if (d := resolve_template_dir(r, tpl_name))), None)
        dest_tpl = resolve_template_dest_dir(target_dir, tpl_name, src_tpl=src_tpl)
        local_tpl = resolve_template_dir(target_dir, tpl_name) or dest_tpl
        if src_tpl is not None and src_tpl.resolve() != dest_tpl.resolve():
            is_newer = check_newer and is_dest_template_newer(src_tpl, local_tpl)
            did_copy, c_list = reconcile_template_pack_sync(
                target_dir, tpl_name, src_tpl, dest_tpl,
                strategy=strategy, is_local_newer=is_newer, dry_run=dry_run,
            )  # fmt: skip
            if did_copy:
                copied.append(tpl_name)
            conflicts.extend(c_list)
    return copied, conflicts


def bootstrap_node_workspace(
    repo_dir: Path, target_dir: Path, *, layer_id: str, layer_role: str = "department",
    precedence: int | None = None, description: str | None = None,
    upstream_repo: str | None = None, upstream_branch: str = "master",
    upstream_layer_id: str | None = None, parent_dir: Path | None = None,
    templates: list[str] | None = None, own_template_name: str | None = None,
    entity_kind: str | None = None, governing_root_id: str | None = None,
    interaction_language: str | None = None, scaffold_own_template: bool = True,
    home_dir: Path | None = None, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """One-shot initializer for a sovereign Zero-Cloud Node workspace."""
    if not KEBAB_ID_RE.match(layer_id):
        raise ValueError(f"Invalid layer_id {layer_id!r}")
    if layer_role not in VALID_LAYER_ROLES:
        raise ValueError(f"Invalid layer_role {layer_role!r}")
    svc_prec = ROLE_DEFAULT_PRECEDENCE["service-node"]
    def_p = ROLE_DEFAULT_PRECEDENCE.get(layer_role, svc_prec)
    eff_prec = precedence if precedence is not None else def_p
    eff_parent, inherited_templates = parent_dir or repo_dir, list[str]()
    if (eff_parent / NODE_MANIFEST_REL_PATH).is_file():
        pm = load_node_manifest(eff_parent)
        p_ent, p_role = resolve_node_entity_identity(eff_parent, pm), pm.get("layer_role")
        if p_ent["entity_kind"] != "open-source" and (
            parent_dir is not None or p_role not in (None, "workstation")
        ):
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
            inherited_templates = merge_unique_strings(
                [str(pt) for pt in pm.get("default_stack_templates", [])]
            )
    ind_chain = (*PROFILE_TEMPLATE_CHAIN["academic"], *PROFILE_TEMPLATE_CHAIN["technical"])
    ind_all = [tp for tp, _ in ind_chain if tp != "universal-base"]
    ind_def = ind_all if entity_kind == "individual" else []
    dom_def = classify_knowledge_domain(layer_id, layer_role)["default_stack_templates"] or ind_def
    was_unboot = not (target_dir / NODE_MANIFEST_REL_PATH).is_file()
    know_mounts = [
        t for t in (templates or []) if t in DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY and t != layer_id
    ]  # fmt: skip
    tpl_inputs = [t for t in (templates or []) if t not in know_mounts]
    req_tpls = merge_unique_strings(inherited_templates, tpl_inputs or dom_def)
    copied_templates, _ = _sync_templates_from_roots(
        target_dir, eff_parent, repo_dir, req_tpls, dry_run=dry_run
    )
    manifest_res = configure_node_manifest(
        target_dir, layer_id=layer_id, layer_role=layer_role, dry_run=dry_run,
        precedence=eff_prec, description=description, prune_default_templates=True,
        upstream_url=upstream_repo, upstream_branch=upstream_branch, entity_kind=entity_kind,
        upstream_id=upstream_layer_id, governing_root_id=governing_root_id,
        interaction_language=interaction_language,
    )  # fmt: skip
    s_roots = (eff_parent, repo_dir)
    req_lin = {n for n, _ in resolve_template_lineage_chain(req_tpls, s_roots)} | set(req_tpls)
    def_cockpit = resolve_default_cockpit_plugin(
        layer_role, str(entity_kind or ""), req_tpls, s_roots
    )
    has_plug = any(
        t in BUILTIN_COCKPIT_PLUGINS
        or (
            (td := resolve_template_dir(target_dir, t) or resolve_template_dir(repo_dir, t))
            and (tj := td / "template.json").is_file()
            and "runtime_service" in tj.read_text("utf-8")
        )
        for t in req_tpls
    )
    own_tpl_id = own_template_name or layer_id
    all_tpls = merge_unique_strings(
        req_tpls, [own_tpl_id] if scaffold_own_template else [], [] if has_plug else [def_cockpit]
    )
    if not dry_run and all_tpls:
        m_path = target_dir / NODE_MANIFEST_REL_PATH
        m_data = {**load_node_manifest(target_dir), "default_stack_templates": list(all_tpls)}
        m_path.write_text(json.dumps(m_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for km in know_mounts if not dry_run else ():
        register_mounted_subtree(target_dir, km, "")
    is_sw_squad = layer_role == "squad" and "software-engineering" in req_lin
    own_kind = "framework-stack" if is_sw_squad else "context-stack"
    scaffold_res = None
    if scaffold_own_template:
        scaffold_res = scaffold_template_pack(
            target_dir, template_name=own_tpl_id, kind=own_kind, dry_run=dry_run,
            description=description or f"{layer_id} ({layer_role}) governance pack",
            register_binding=True, rule_filename=f"{own_tpl_id}.md",
        )  # fmt: skip
    ag_rule = (
        f'---\ntrigger: always_on\ndescription: "Rules for {layer_id} ({layer_role})."\n---\n\n'
        f"# {layer_id} Node Rules (`{layer_role}`, `precedence: {eff_prec}`)\n\n"
        f"> Governed by `{NODE_MANIFEST_REL_PATH}` (`layer_id: {layer_id}`).\n\n"
        f"## Scope & Surface Target\n- Governs `{layer_id}` (`{layer_role}`).\n\n"
        f"## Normative Invariants\n- Respect *Lex Superior* (`0..100`) & `{own_tpl_id}`.\n\n"
        "## Verification & Sign-Off Gates\n- [ ] Verify `zcg diff-project` parity before commit.\n"
    )
    m_lang = manifest_res.get("interaction_language") or interaction_language
    eff_lang = str(m_lang or DEFAULT_INTERACTION_LANGUAGE)
    readme_md = render_layer_onboarding_readme(
        layer_id, layer_role, eff_prec, own_tpl_id, all_tpls, upstream_layer_id,
        entity_kind=entity_kind, interaction_language=eff_lang,
    )  # fmt: skip
    wt_md = (
        f"# Active Work Tasks — {layer_id}\n\n- [x] Initial layer bootstrap.\n"
        "- [ ] Complete `Layer Setup Blueprint` in `README.md` and run Kickoff Prompt.\n"
    )
    git_ign = (
        "__pycache__/\n*.pyc\n.ruff_cache/\n.mypy_cache/\n.pytest_cache/\n"
        "logs/\n.agents/runtime/\n.agents/telemetry/\n.agents/SESSION.md\n"
    )
    baseline_files = {
        ".gitignore": git_ign, "layers/.gitkeep": "", "README.md": readme_md,
        "WORKTASK.md": wt_md,
        "BACKLOG.md": f"# Backlog & In-Flight Maintainability Ledger — {layer_id}\n\n",
        "CHANGELOG.md": f"# Changelog — {layer_id}\n\n## [Unreleased]\n- Initial bootstrap.\n",
        "Makefile": render_layer_makefile(layer_id, layer_role, eff_parent, repo_dir),
        "antigravity/.gemini/config/AGENTS.md": ag_rule,
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
    for sub_d in ("reference", "architecture", "guides") if not dry_run else ():
        (target_dir / "docs" / sub_d).mkdir(parents=True, exist_ok=True)
        (target_dir / "docs" / sub_d / ".gitkeep").touch(exist_ok=True)
    tpl_ref_arg = ",".join(all_tpls) or None
    apply_res: dict[str, Any] = {"applied_template": tpl_ref_arg, "files_materialized": []}
    cockpit_res: dict[str, Any] = {"services": []}
    if not dry_run:
        apply_res = apply_templates_to_project(
            target_dir, target_dir, template_ref=tpl_ref_arg, layers_filter=["all"],
            engine_dir=repo_dir, dry_run=False,
        )  # fmt: skip
        cockpit_res = manage_plugin_service(
            target_dir, action="activate", target_env="dev", parent_dir=eff_parent, dry_run=False
        )  # fmt: skip
    ide_reg = register_antigravity_workspace(target_dir, home_dir=home_dir, dry_run=dry_run)
    topo_out = ((cockpit_res.get("services") or [{}])[0].get("intranet_topology")) or {}
    c_url, d_url = topo_out.get("localhost_url"), topo_out.get("local_subdomain_dashboard_url")
    return {
        "target_dir": str(target_dir), "layer_id": layer_id, "dry_run": dry_run,
        "layer_role": layer_role, "precedence": eff_prec,
        "active_cockpit_url": c_url, "active_dashboard_url": d_url,
        "antigravity_workspace": ide_reg, "copied_templates": copied_templates,
        "scaffolded_template": scaffold_res["template_id"] if scaffold_res else None,
        "baseline_files_created": sorted(created_baseline),
        "applied_template": apply_res.get("applied_template"), "manifest": manifest_res,
        "files_materialized": apply_res.get("files_materialized", []),
    }  # fmt: skip


def sync_node_workspace(
    repo_dir: Path, target_dir: Path, *, parent_dir: Path | None = None,
    templates: list[str] | None = None, strategy: str = "reconcile", dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Propagate upstream template updates into target_dir/templates/ and refresh .agents/."""
    if strategy not in VALID_SYNC_STRATEGIES:
        raise ValueError(f"Invalid sync strategy {strategy!r}; must be in {VALID_SYNC_STRATEGIES}")
    manifest_path = target_dir / NODE_MANIFEST_REL_PATH
    if not manifest_path.is_file():
        raise ValueError(f"Missing target node manifest: {manifest_path}")
    manifest = load_node_manifest(target_dir)
    own_id = str(manifest.get("layer_id") or "")
    own_role = str(manifest.get("layer_role") or "department")
    def_tpls = [str(t) for t in manifest.get("default_stack_templates", [])]
    stack_templates = merge_unique_strings(def_tpls, templates or [])
    eff_parent = resolve_default_parent_dir(target_dir, parent_dir) or repo_dir
    p_arg = eff_parent if eff_parent != repo_dir else None
    ent_id = resolve_node_entity_identity(target_dir, manifest, parent_dir=p_arg)
    resolved_root = ent_id["governing_root_id"]
    stale_rev = manifest.get("schema_version") != NODE_MANIFEST_CONTRACT_REV
    root_backfill = (manifest.get("governing_root_id") != resolved_root) and bool(resolved_root)
    env_backfill = ensure_canonical_environments(manifest, own_id)
    if not dry_run and (stale_rev or bool(templates) or root_backfill or env_backfill):
        manifest["schema_version"], manifest["layer_role"] = NODE_MANIFEST_CONTRACT_REV, own_role
        manifest["default_stack_templates"] = list(stack_templates)
        if root_backfill:
            manifest["governing_root_id"] = resolved_root
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8")
    existing_tpls = [
        n for n, _p in iter_layer_template_dirs(target_dir)
        if own_role == "workstation" or n not in CANONICAL_STARTER_TEMPLATES
    ]  # fmt: skip
    candidate_tpls = list(dict.fromkeys([*stack_templates, *existing_tpls]))
    synced_templates, conflicts = _sync_templates_from_roots(
        target_dir, eff_parent, repo_dir, candidate_tpls,
        skip_id=own_id, check_newer=True, strategy=strategy, dry_run=dry_run,
    )  # fmt: skip
    active_set = {*candidate_tpls, *synced_templates}
    for tname, tdir in iter_layer_template_dirs(target_dir) if not dry_run else ():
        if tname in CANONICAL_STARTER_TEMPLATES and tname not in active_set:
            shutil.rmtree(tdir, ignore_errors=True)
        else:
            stamp_schema_rev(tdir / "template.json", TEMPLATE_MANIFEST_CONTRACT_REV)
    if (
        not dry_run
        and (own_td := resolve_template_dir(target_dir, own_id))
        and (ag_r := target_dir / ".agents/rules" / f"{own_id}.md").is_file()
        and (tpl_r := own_td / "rules" / f"{own_id}.md").is_file()
        and ag_r.stat().st_mtime_ns > tpl_r.stat().st_mtime_ns
    ):
        shutil.copy2(ag_r, tpl_r)
    synced_children = sync_mounted_children_into_parent(
        target_dir, manifest.get("mounted_layers", []), dry_run=dry_run
    )
    makefile_path = target_dir / "Makefile"
    cur_mk = makefile_path.read_text(encoding="utf-8") if makefile_path.is_file() else ""
    _head, sep, rest = cur_mk.partition(MAKEFILE_CUSTOM_TARGETS_MARKER)
    c_tail = f"\n{sep}{rest.strip()}\n" if sep else ""
    new_mk = render_layer_makefile(own_id, own_role, eff_parent, repo_dir) + c_tail
    is_gen_mk = not cur_mk or cur_mk.startswith(MAKEFILE_ROLE_HEADER_PREFIX)
    mk_upgraded = is_gen_mk and cur_mk != new_mk
    if not dry_run and mk_upgraded:
        makefile_path.write_text(new_mk, encoding="utf-8")
    plugin_svcs = [
        {"template": t, **rs} for t in stack_templates
        if (td := resolve_template_dir(target_dir, t) or resolve_template_dir(repo_dir, t))
        and (tj := td / "template.json").is_file()
        and isinstance(rs := json.loads(tj.read_text("utf-8")).get("runtime_service"), dict)
    ]  # fmt: skip
    apply_res = apply_templates_to_project(
        target_dir, target_dir, template_ref=",".join(stack_templates) or None,
        layers_filter=["all"], engine_dir=repo_dir, dry_run=dry_run,
    )  # fmt: skip
    return {
        "target_dir": str(target_dir), "layer_id": own_id, "strategy": strategy,
        "dry_run": dry_run, "makefile_upgraded": mk_upgraded, "synced_templates": synced_templates,
        "reconciliation_conflicts": conflicts, "synced_mounted_layers": synced_children,
        "plugin_services_redeployed": plugin_svcs,
        "applied_template": apply_res.get("applied_template"),
        "pruned_plugins": apply_res.get("pruned_plugins", []),
        "files_materialized": apply_res.get("files_materialized", []),
        "participating_layers": apply_res.get("participating_layers", []),
    }  # fmt: skip
