"""Node manifest parameterization, polymorphic template scaffolding, and project projection.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from zcg.core import constants, domain, manifests
from zcg.core.blueprints import render_lineage_markdown, resolve_template_lineage_chain
from zcg.core.surface_composer import materialize_agent_companion_files
from zcg.governance.runtime.node_updates import read_engine_version
from zcg.governance.workspace.antigravity_sync import sync_workspace_antigravity_surfaces
from zcg.governance.workspace.baseline_fallback import reconcile_workspace_global_baseline

MIN_PRECEDENCE, MAX_PRECEDENCE, DEFAULT_BOT_TTL_SECONDS = 0, 100, 300
_SKILL_VERB_CLAUSES: tuple[str, ...] = (
    "Audit statutory boundaries covering", "Orchestrate operational workflows inside",
    "Validate epistemic checkpoints governing", "Synthesize architectural contracts targeting",
    "Inspect runtime telemetry protecting", "Curate ledger deliverables across",
    "Coordinate capability rings securing", "Govern modular surfaces enforcing",
)  # fmt: skip


def build_guide_skill_description(template_name: str) -> str:
    """Build a deterministic verb-led SKILL.md description preventing Jaccard overlap."""
    return f"{_SKILL_VERB_CLAUSES[sum(ord(c) for c in template_name) % 8]} {template_name}."


def upgrade_boilerplate_guide_skill(own_td: Path | None, own_id: str) -> bool:
    """Upgrade untouched default 'Guide for <id>.' boilerplate in templates/<id>/skills/."""
    sk = own_td / "skills" / f"{own_id}-guide/SKILL.md" if own_td else None
    old_d = f'description: "Guide for {own_id}."'
    if sk is None or not sk.is_file() or old_d not in (txt := sk.read_text("utf-8")):
        return False
    new_d = f'description: "{build_guide_skill_description(own_id)}"'
    sk.write_text(txt.replace(old_d, new_d, 1), "utf-8")
    return True


def merge_unique_strings(*groups: Iterable[str]) -> list[str]:
    """Return deduplicated non-empty strings preserving first-seen order."""
    return list(dict.fromkeys(s.strip() for g in groups for s in g if s and s.strip()))


def ensure_canonical_environments(manifest: dict[str, Any], layer_id: str) -> bool:
    """Ensure all 4 canonical environments (dev, tst, pre, pro) exist in manifest."""
    raw_envs = manifest.get("environments")
    envs: dict[str, Any] = dict(raw_envs) if isinstance(raw_envs, dict) else {}
    fb_gr = [f"Enforce {layer_id} governance invariants"]
    def_gr = list((envs.get("pre") or envs.get("dev") or {}).get("default_guardrails") or fb_gr)
    specs = (
        ("dev", "read-write-local", f"Local {layer_id} workspace"),
        ("tst", "read-and-test-trigger", f"Integration & QA validation for {layer_id}"),
        ("pre", "strictly-read-only", f"Pre-production staging audit for {layer_id}"),
        ("pro", "strictly-read-only-audited", f"Production governance enforcement for {layer_id}"),
    )
    changed = any(k not in envs for k, _, _ in specs)
    manifest["environments"] = {
        k: envs.get(k) or {"description": d, "access_mode": m, "default_guardrails": list(def_gr)}
        for k, m, d in specs
    }
    for fm in (x for x in manifest.get("federated_mcps", []) if isinstance(x, dict)):
        fe = list(fm.get("environments") or [])
        if "dev" in fe and "pre" in fe and "tst" not in fe:
            fm["environments"], changed = ["dev", "tst", *[e for e in fe if e != "dev"]], True
    return changed


def configure_node_manifest(
    repo_dir: Path, *, layer_id: str, layer_role: str = "squad", precedence: int | None = None,
    description: str | None = None, upstream_url: str | None = None,
    upstream_id: str | None = None, upstream_branch: str | None = None,
    entity_kind: str | None = None, governing_root_id: str | None = None,
    interaction_language: str | None = None, prune_default_templates: bool = False,
    engine_dir: Path | None = None, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Parameterize system/zcg-node.json (zcg-node-v1) for a Zero-Cloud Node."""
    if not domain.is_kebab_id(layer_id):
        raise ValueError(f"Invalid layer_id {layer_id!r}: must be kebab-case")
    if layer_role not in constants.VALID_LAYER_ROLES:
        raise ValueError(f"Invalid layer_role {layer_role!r}")
    if entity_kind is not None and entity_kind not in constants.VALID_ENTITY_KINDS:
        raise ValueError(f"Invalid entity_kind {entity_kind!r}")
    if interaction_language and interaction_language not in constants.VALID_INTERACTION_LANGUAGES:
        raise ValueError(f"Invalid interaction_language {interaction_language!r}")
    r_prec = constants.ROLE_DEFAULT_PRECEDENCE[layer_role]
    eff_prec = precedence if precedence is not None else r_prec
    if eff_prec < MIN_PRECEDENCE or eff_prec > MAX_PRECEDENCE:
        raise ValueError(f"Invalid precedence {eff_prec}: must be 0..100")
    manifest_path = repo_dir / constants.NODE_MANIFEST_REL_PATH
    base_m = manifests.load_node_manifest(repo_dir)
    up_default = {
        "layer_id": "mtwuser/zero-cloud-gravity", "branch": "master",
        "repository": "https://github.com/mtwuser/zero-cloud-gravity.git",
    }  # fmt: skip
    def_desc = f"Zero-Cloud {layer_role} node ({layer_id})"
    manifest: dict[str, Any] = {
        "mounted_layers_dir": "layers", "mounted_layers": [],
        "default_stack_templates": manifests.discover_layer_template_names(repo_dir),
        "baseline_guardrails": [], "surface_bindings": [],
        "environments": {}, "federated_mcps": [], **base_m,
        "schema_version": constants.NODE_MANIFEST_CONTRACT_REV, "layer_id": layer_id,
        "layer_role": layer_role, "precedence": eff_prec,
        "description": description or base_m.get("description") or def_desc,
    }  # fmt: skip
    opt_f = (("entity_kind", entity_kind), ("governing_root_id", governing_root_id))
    for ok, ov in (*opt_f, ("interaction_language", interaction_language)):
        if ov is not None:
            manifest[ok] = ov
    raw_up = manifest.get("upstream_layer")
    up_opts = (("repository", upstream_url), ("layer_id", upstream_id), ("branch", upstream_branch))
    manifest["upstream_layer"] = {
        **up_default, **(dict(raw_up) if isinstance(raw_up, dict) else {}),
        **{k: v for k, v in up_opts if v is not None},
    }  # fmt: skip
    ensure_canonical_environments(manifest, layer_id)
    if not manifests.is_oss_root_manifest(manifest):
        manifest["engine_version"] = read_engine_version(engine_dir or constants.REPO_DIR)
    if prune_default_templates:
        st_s = constants.CANONICAL_STARTER_TEMPLATES
        manifest["default_stack_templates"] = [
            t for t in manifest.get("default_stack_templates", []) if t not in st_s
        ]  # fmt: skip
        manifest["surface_bindings"] = [
            b for b in manifest.get("surface_bindings", []) if isinstance(b, dict)
            and not any(
                f"/{p}/" in str(r) for p in st_s
                for r in [*b.get("rule_files", []), *b.get("canonical_templates", [])]
            )
        ]  # fmt: skip
    if not dry_run:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return manifest


def scaffold_template_pack(
    repo_dir: Path, *, template_name: str, kind: str = "tool-stack",
    description: str | None = None, register_binding: bool = False,
    rule_filename: str | None = None, scopes: list[str] | None = None,
    planes: list[str] | None = None, traits: list[str] | None = None,
    globs: list[str] | None = None, include_starter_skill: bool = True, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Scaffold a sovereign or polymorphic template pack under templates/<template_name>/."""
    if not domain.is_kebab_id(template_name):
        raise ValueError(f"Invalid template_name {template_name!r}: must be kebab-case")
    if kind not in constants.VALID_TEMPLATE_KINDS:
        raise ValueError(f"Invalid template kind {kind!r}")
    eff_rule = rule_filename or "policy.md"
    if not eff_rule.endswith(".md") or "/" in eff_rule or ".." in eff_rule:
        raise ValueError(f"Invalid rule_filename {eff_rule!r}: must be a simple .md filename")
    if manifests.resolve_template_dir(repo_dir, template_name) is not None:
        raise ValueError(f"Template directory already exists: templates/{template_name}")
    tpl_dir = manifests.resolve_template_dest_dir(repo_dir, template_name)
    rel_tpl = str(tpl_dir.relative_to(repo_dir)).replace("\\", "/")
    is_tech = kind in ("tool-stack", "plugin-stack")
    desc = description or f"{template_name} ({kind}) governance and template pack"
    mode, def_res = ("transversal", "L1") if is_tech else ("authoritative", "L2")
    binding_entry: dict[str, Any] = {
        "binding_id": f"{template_name}-surface-binding", "description": desc, "mode": mode,
        "target_globs": globs or ["*"], "architectural_planes": planes or ["*"],
        "scopes": scopes or ["*"], "traits": traits or ["*"], "default_resolution": def_res,
        "invariants": [f"Enforce {template_name} ({kind}) rules and canonical assets"],
        "rule_files": [f"{rel_tpl}/rules/{eff_rule}"],
        "canonical_templates": [] if is_tech else [f"{rel_tpl}/assets/canonical_snippet.md"],
        "ephemeral_fork_policy": {
            "bot_role": f"{template_name}-guardian", "trigger": "on_surface_match",
            "model_tier": "flash" if is_tech else "inherit", "access_mode": "strictly-read-only",
            "mount_templates": [template_name], "resolution": def_res,
            "ttl_seconds": DEFAULT_BOT_TTL_SECONDS, "handback_contract": "4-channel-digest+rcap1",
        },
    }  # fmt: skip
    rt_svc = {
        "service_id": template_name, "framework": template_name,
        "bound_surfaces": ["surfaces/web/", "surfaces/data/"], "healthcheck_endpoint": "/healthz",
    }  # fmt: skip
    rt_extra = {"runtime_service": rt_svc} if kind == "plugin-stack" else {}
    tpl_manifest = {
        "schema_version": constants.TEMPLATE_MANIFEST_CONTRACT_REV, "template_id": template_name,
        "kind": kind, "target_role": "domain-policy" if kind == "context-stack" else "squad",
        "description": desc, "recommended_surface_bindings": [binding_entry], **rt_extra,
    }  # fmt: skip
    wt_doc = f"# Active Work Tasks — {template_name}\n\n- [ ] Initial setup\n"
    mk_doc = ".PHONY: install verify\ninstall:\n\t@echo 'Install'\nverify:\n\t@echo 'Verify'\n"
    sn_doc = {f"{rel_tpl}/assets/canonical_snippet.md": f"<!-- Asset: {template_name} -->\n"}
    tech_d = {f"{rel_tpl}/governance/WORKTASK.md": wt_doc, f"{rel_tpl}/governance/Makefile": mk_doc}
    extra_files = tech_d if is_tech else sn_doc
    sk_txt = (
        f'---\nname: {template_name}-guide\ndescription: "{build_guide_skill_description(template_name)}"\n---\n\n'  # noqa: E501
        f"# {template_name} Guide\n\n1. Review `{rel_tpl}/rules/{eff_rule}`.\n"
        "2. Verify invariants via `zcg diff-project` and promote upward via `--create-pr`.\n"
    )
    sk_doc = {f"{rel_tpl}/skills/{template_name}-guide/SKILL.md": sk_txt} if include_starter_skill else {}  # noqa: E501  # fmt: skip
    r_txt = (
        f'---\ntrigger: always_on\ndescription: "Rules for {template_name} ({kind})."\n---\n\n'
        f"# {template_name} Governance Rules ({kind})\n\n## Scope & Surface Target\n"
        f"- **Template Pack**: `{rel_tpl}/` (`{kind}`).\n\n## Normative Invariants\n"
        f"- Follow the canonical patterns defined in `{rel_tpl}/`.\n\n"
        "## Verification & Sign-Off Gates\n- [ ] Verify zero drift via `zcg diff-project`.\n"
    )
    files_to_write: dict[str, str] = {
        f"{rel_tpl}/template.json": json.dumps(tpl_manifest, indent=2, ensure_ascii=False) + "\n",
        f"{rel_tpl}/rules/{eff_rule}": r_txt, **sk_doc, **extra_files,
    }  # fmt: skip
    if not dry_run:
        for rel_path, content in files_to_write.items():
            (full_p := repo_dir / rel_path).parent.mkdir(parents=True, exist_ok=True)
            full_p.write_text(content, encoding="utf-8")
        if (m_path := repo_dir / constants.NODE_MANIFEST_REL_PATH).is_file():
            m = manifests.load_node_manifest(repo_dir)
            cur_t = m.get("default_stack_templates", [])
            m["default_stack_templates"] = merge_unique_strings(cur_t, [template_name])
            if register_binding:
                m["surface_bindings"] = [*m.get("surface_bindings", []), binding_entry]
            m_path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "template_id": template_name, "kind": kind, "dry_run": dry_run,
        "files_created": sorted(files_to_write.keys()), "binding_registered": register_binding,
    }  # fmt: skip


def apply_templates_to_project(
    repo_dir: Path, target_project_dir: Path, *, template_ref: str | None = None,
    layers_filter: list[str] | None = None, include_layer_defaults: bool = False,
    engine_dir: Path | None = None, home_dir: Path | None = None, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Materialize template packs and 0..N layer rules/bindings into a target project."""
    eff_eng, r_prec = engine_dir or repo_dir, constants.ROLE_DEFAULT_PRECEDENCE
    c_prec, s_prec = r_prec["corporate"], r_prec["service-node"]
    root_m = manifests.load_node_manifest(repo_dir) or {
        "layer_id": "root", "layer_role": "corporate", "precedence": c_prec
    }  # fmt: skip
    cand_layers: list[tuple[str, Path, dict[str, Any]]] = [("root", repo_dir, root_m)]
    if (layers_dir := repo_dir / "layers").is_dir():
        subs = sorted(s for s in layers_dir.iterdir() if s.is_dir() and not s.name.startswith("."))
        for s in subs:
            sm = manifests.load_node_manifest(s) or {"layer_id": s.name, "precedence": s_prec}
            cand_layers.append((s.name, s, sm))
    if layers_filter and "all" not in layers_filter:
        allowed = set(layers_filter)
        cand_layers = [
            (n, ld, m) for n, ld, m in cand_layers
            if n in allowed or str(m.get("layer_id")) in allowed
        ]  # fmt: skip
    cand_layers.sort(key=lambda item: (int(item[2].get("precedence", s_prec)), item[0]))
    def_all = [str(t) for t in root_m.get("default_stack_templates", [])]
    def_tpls = [t for t in def_all if t != "universal-base"]
    resolved_templates: list[tuple[str, Path]] = []
    res_td = manifests.resolve_template_dir
    if template_ref:
        raw_list = [r.strip() for r in template_ref.split(",") if r.strip()]
        req_refs = merge_unique_strings(def_tpls, raw_list) if include_layer_defaults else raw_list
        ordered = sorted(cand_layers, key=lambda it: it[0] != "root")
        for raw_ref in req_refs:
            lp, sep, tp = raw_ref.partition(":")
            by_l = (d for n, ld, _ in cand_layers if n == lp and (d := res_td(ld, tp)))
            by_o = (d for _, ld, _ in ordered if (d := res_td(ld, raw_ref)))
            found_d = next(by_l, None) if sep else (next(by_o, None) or res_td(eff_eng, raw_ref))
            if found_d is None:
                if raw_ref in constants.BUILTIN_COCKPIT_PLUGINS:
                    continue
                raise ValueError(f"Template {raw_ref!r} not found in selected layers")
            resolved_templates.append((found_d.name, found_d))
    else:
        for tpl_str in def_tpls:
            if (cand_d := res_td(repo_dir, tpl_str) or res_td(eff_eng, tpl_str)) is not None:
                resolved_templates.append((cand_d.name, cand_d))
    resolved_tpl_name = ",".join(t[0] for t in resolved_templates)
    mat_templates = resolve_template_lineage_chain(resolved_templates, (repo_dir, eff_eng))
    seen_names = {t[0] for t in mat_templates} | set(def_all)
    copied_files, agents_dir = list[str](), target_project_dir / ".agents"

    def _copy_file(src: Path, dest: Path, *, overwrite: bool = True, fm: bool = False) -> None:
        copied_files.append(str(dest.relative_to(target_project_dir)))
        if dry_run:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        if overwrite:
            dest.unlink(missing_ok=True)
        shutil.copy2(src, dest)
        if fm:
            manifests.ensure_rule_file_frontmatter(dest)
        dest.chmod(dest.stat().st_mode | constants.OWNER_WRITABLE_MODE_BIT)

    def _iter_f(d: Path) -> Iterable[Path]:
        return (p for p in sorted(d.rglob("*")) if p.is_file()) if d.is_dir() else ()

    for tpl_name, tpl_dir in mat_templates:
        if not dry_run and tpl_dir.resolve().is_relative_to(target_project_dir.resolve()):
            upgrade_boilerplate_guide_skill(tpl_dir, tpl_name)
        for sub_name in ("rules", "skills"):
            for src_f in _iter_f(tpl_dir / sub_name):
                dest = agents_dir / sub_name / src_f.relative_to(tpl_dir / sub_name)
                _copy_file(src_f, dest, fm=(sub_name == "rules" and dest.suffix == ".md"))
        gov_src = tpl_dir / "governance"
        gov_fs = [*sorted(gov_src.glob("*.md")), *sorted(gov_src.glob("Makefile"))]
        for gf in gov_fs if gov_src.is_dir() else ():
            dest_g = (agents_dir if gf.name == "SESSION.md" else target_project_dir) / gf.name
            if not dest_g.exists():
                _copy_file(gf, dest_g, overwrite=False)
        for af in _iter_f(tpl_dir / "assets"):
            _copy_file(af, agents_dir / "assets" / tpl_name / af.relative_to(tpl_dir / "assets"))
    lineage_rows: list[str] = []
    for name, ldir, m in cand_layers:
        prec, lid = int(m.get("precedence", s_prec)), str(m.get("layer_id", name))
        role = str(m.get("layer_role", "department"))
        bindings = manifests.collect_layer_effective_bindings(ldir, m)
        lineage_rows.append(f"| `{prec}` | `{name}` | `{lid}` | `{role}` | `{len(bindings)}` |")
        layer_agents = ldir / "antigravity/.gemini/config/AGENTS.md"
        dest_rule = agents_dir / "rules" / f"layer-{prec:02d}-{name}.md"
        if name == "root" and repo_dir.resolve() == target_project_dir.resolve():
            if not dry_run:
                dest_rule.unlink(missing_ok=True)
            for sf in sorted((ldir / "antigravity/.gemini/config/skills").glob("*/SKILL.md")):
                _copy_file(sf, agents_dir / "skills" / sf.parent.name / "SKILL.md")
        elif layer_agents.is_file():
            _copy_file(layer_agents, dest_rule, fm=True)
    pruned_plugins: list[str] = []
    known_tpls = {**dict(manifests.iter_layer_template_dirs(eff_eng)), **dict(manifests.iter_layer_template_dirs(repo_dir))}  # noqa: E501  # fmt: skip
    if not layers_filter or "all" in layers_filter:
        if not dry_run and (agents_dir / "rules").is_dir():
            for l_rf in (agents_dir / "rules").glob("layer-*.md"):
                if f".agents/rules/{l_rf.name}" not in copied_files:
                    l_rf.unlink(missing_ok=True)
        for t_name, t_dir in ((k, v) for k, v in sorted(known_tpls.items()) if k not in seen_names):
            r_files = [
                agents_dir / "rules" / rf.name for rf in (t_dir / "rules").glob("*.md")
                if f".agents/rules/{rf.name}" not in copied_files
                and (agents_dir / "rules" / rf.name).is_file()
            ]  # fmt: skip
            s_dirs = [
                agents_dir / "skills" / sf.parent.name for sf in (t_dir / "skills").glob("*/SKILL.md")  # noqa: E501
                if f".agents/skills/{sf.parent.name}/SKILL.md" not in copied_files
                and (agents_dir / "skills" / sf.parent.name).is_dir()
            ]  # fmt: skip
            a_dir, rt_f = agents_dir / "assets" / t_name, agents_dir / "runtime" / f"{t_name}.json"
            if r_files or s_dirs or a_dir.is_dir() or rt_f.is_file():
                pruned_plugins.append(t_name)
                for rf in (*r_files, rt_f) if not dry_run else ():
                    rf.unlink(missing_ok=True)
                for sd in (*s_dirs, a_dir) if not dry_run else ():
                    shutil.rmtree(sd, ignore_errors=True)
    fb_files, fb_pruned = reconcile_workspace_global_baseline(
        target_project_dir, engine_dir=eff_eng, active_template_ids=seen_names,
        already_copied=copied_files, home_dir=home_dir, dry_run=dry_run)  # fmt: skip
    copied_files.extend(fb_files)
    pruned_plugins.extend(fb_pruned)
    comp_files = materialize_agent_companion_files(
        target_project_dir, repo_dir=repo_dir, engine_dir=eff_eng, root_manifest=root_m,
        active_templates=mat_templates, known_templates=list(known_tpls.items()),
        copied_files=copied_files, dry_run=dry_run,
    )  # fmt: skip
    p_dir = repo_dir if repo_dir.resolve() != target_project_dir.resolve() else None
    agy_files = sync_workspace_antigravity_surfaces(
        target_project_dir, active_templates=mat_templates,
        known_templates=list(known_tpls.items()), parent_dir=p_dir, dry_run=dry_run,
    )  # fmt: skip
    lineage_dest, session_dest = agents_dir / "LAYER_LINEAGE.md", agents_dir / "SESSION.md"
    rel_lin = str(lineage_dest.relative_to(target_project_dir))
    copied_files.extend([*comp_files, *agy_files, rel_lin, ".agents/SESSION.md"])
    if not dry_run:
        lineage_dest.parent.mkdir(parents=True, exist_ok=True)
        lang = str(root_m.get("interaction_language") or constants.DEFAULT_INTERACTION_LANGUAGE)
        lin_md = render_lineage_markdown(resolved_tpl_name, lineage_rows, interaction_language=lang)
        lineage_dest.write_text(lin_md, "utf-8")
        if not session_dest.exists():
            s_md = f"# Session State Log\n\n## Session Log\n\n- Initialized (`{resolved_tpl_name or 'default'}`).\n"  # noqa: E501
            session_dest.write_text(s_md, "utf-8")
        gi_file = target_project_dir / ".gitignore"
        if gi_file.is_file() and ".zcg/" not in (gi_txt := gi_file.read_text("utf-8")).splitlines():
            sep = "" if not gi_txt or gi_txt.endswith("\n") else "\n"
            gi_file.write_text(f"{gi_txt}{sep}.zcg/\n", encoding="utf-8")
    return {
        "target_project_dir": str(target_project_dir), "dry_run": dry_run,
        "applied_template": resolved_tpl_name or None, "pruned_plugins": pruned_plugins,
        "participating_layers": [name for name, _d, _m in cand_layers],
        "files_materialized": merge_unique_strings(copied_files),
    }  # fmt: skip
