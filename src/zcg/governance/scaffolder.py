"""Node manifest parameterization, polymorphic template scaffolding, and project projection.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from zcg.core.blueprints import render_lineage_markdown, resolve_template_lineage_chain
from zcg.core.constants import (
    BUILTIN_COCKPIT_PLUGINS,
    CANONICAL_STARTER_TEMPLATES,
    DEFAULT_INTERACTION_LANGUAGE,
    KEBAB_ID_RE,
    NODE_MANIFEST_CONTRACT_REV,
    NODE_MANIFEST_REL_PATH,
    OWNER_WRITABLE_MODE_BIT,
    ROLE_DEFAULT_PRECEDENCE,
    TEMPLATE_MANIFEST_CONTRACT_REV,
    VALID_ENTITY_KINDS,
    VALID_INTERACTION_LANGUAGES,
    VALID_LAYER_ROLES,
    VALID_TEMPLATE_KINDS,
)
from zcg.core.manifests import (
    discover_layer_template_names,
    ensure_rule_file_frontmatter,
    iter_layer_template_dirs,
    load_node_manifest,
    resolve_template_dest_dir,
    resolve_template_dir,
)
from zcg.governance.consensus import collect_layer_effective_bindings

MIN_PRECEDENCE, MAX_PRECEDENCE, DEFAULT_BOT_TTL_SECONDS = 0, 100, 300


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
    dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Parameterize system/zcg-node.json (zcg-node-v1) for a Zero-Cloud Node."""
    if not KEBAB_ID_RE.match(layer_id):
        raise ValueError(f"Invalid layer_id {layer_id!r}: must be kebab-case")
    if layer_role not in VALID_LAYER_ROLES:
        raise ValueError(f"Invalid layer_role {layer_role!r}: must be one of {VALID_LAYER_ROLES}")
    if entity_kind is not None and entity_kind not in VALID_ENTITY_KINDS:
        raise ValueError(f"Invalid entity_kind {entity_kind!r}: must be in {VALID_ENTITY_KINDS}")
    if interaction_language is not None and interaction_language not in VALID_INTERACTION_LANGUAGES:
        raise ValueError(f"Invalid interaction_language {interaction_language!r}")
    eff_prec = precedence if precedence is not None else ROLE_DEFAULT_PRECEDENCE[layer_role]
    if eff_prec < MIN_PRECEDENCE or eff_prec > MAX_PRECEDENCE:
        raise ValueError(f"Invalid precedence {eff_prec}: must be 0..100")
    manifest_path, base_m = repo_dir / NODE_MANIFEST_REL_PATH, load_node_manifest(repo_dir)
    up_default = {
        "layer_id": "mtwuser/zero-cloud-gravity", "branch": "master",
        "repository": "https://github.com/mtwuser/zero-cloud-gravity.git",
    }  # fmt: skip
    def_desc = f"Zero-Cloud {layer_role} node ({layer_id})"
    manifest: dict[str, Any] = {
        "mounted_layers_dir": "layers", "mounted_layers": [],
        "default_stack_templates": discover_layer_template_names(repo_dir),
        "baseline_guardrails": [], "surface_bindings": [],
        "environments": {}, "federated_mcps": [], **base_m,
        "schema_version": NODE_MANIFEST_CONTRACT_REV, "layer_id": layer_id,
        "layer_role": layer_role, "precedence": eff_prec,
        "description": description or base_m.get("description") or def_desc,
    }  # fmt: skip
    for key, val in (
        ("entity_kind", entity_kind), ("governing_root_id", governing_root_id),
        ("interaction_language", interaction_language),
    ):  # fmt: skip
        if val is not None:
            manifest[key] = val
    raw_up = manifest.get("upstream_layer")
    upstream = {**up_default, **(dict(raw_up) if isinstance(raw_up, dict) else {})}
    for key, val in (
        ("repository", upstream_url), ("layer_id", upstream_id), ("branch", upstream_branch),
    ):  # fmt: skip
        if val is not None:
            upstream[key] = val
    manifest["upstream_layer"] = upstream
    ensure_canonical_environments(manifest, layer_id)
    if prune_default_templates:
        manifest["default_stack_templates"] = [
            t for t in manifest.get("default_stack_templates", [])
            if t not in CANONICAL_STARTER_TEMPLATES
        ]  # fmt: skip
        manifest["surface_bindings"] = [
            b for b in manifest.get("surface_bindings", [])
            if isinstance(b, dict) and not any(
                f"/{p}/" in str(r) for p in CANONICAL_STARTER_TEMPLATES
                for r in [*b.get("rule_files", []), *b.get("canonical_templates", [])]
            )
        ]  # fmt: skip
    if not dry_run:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return manifest


def scaffold_template_pack(
    repo_dir: Path, *, template_name: str, kind: str = "framework-stack",
    description: str | None = None, register_binding: bool = False,
    rule_filename: str | None = None, scopes: list[str] | None = None,
    planes: list[str] | None = None, traits: list[str] | None = None,
    globs: list[str] | None = None, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Scaffold a sovereign or polymorphic template pack under templates/<template_name>/."""
    if not KEBAB_ID_RE.match(template_name):
        raise ValueError(f"Invalid template_name {template_name!r}: must be kebab-case")
    if kind not in VALID_TEMPLATE_KINDS:
        raise ValueError(f"Invalid template kind {kind!r}: must be one of {VALID_TEMPLATE_KINDS}")
    eff_rule = rule_filename or "policy.md"
    if not eff_rule.endswith(".md") or "/" in eff_rule or ".." in eff_rule:
        raise ValueError(f"Invalid rule_filename {eff_rule!r}: must be a simple .md filename")
    if resolve_template_dir(repo_dir, template_name) is not None:
        raise ValueError(f"Template directory already exists: templates/{template_name}")
    tpl_dir = resolve_template_dest_dir(repo_dir, template_name)
    rel_tpl = str(tpl_dir.relative_to(repo_dir)).replace("\\", "/")
    is_tech = kind in ("framework-stack", "plugin-stack")
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
        "schema_version": TEMPLATE_MANIFEST_CONTRACT_REV, "template_id": template_name,
        "kind": kind, "target_role": "domain-policy" if kind == "context-stack" else "squad",
        "description": desc, "recommended_surface_bindings": [binding_entry], **rt_extra,
    }  # fmt: skip
    wt_doc = f"# Active Work Tasks — {template_name}\n\n- [ ] Initial setup\n"
    mk_doc = ".PHONY: install verify\ninstall:\n\t@echo 'Install'\nverify:\n\t@echo 'Verify'\n"
    sn_doc = f"<!-- Canonical asset for {template_name} ({kind}) -->\n"
    extra_files = (
        {f"{rel_tpl}/governance/WORKTASK.md": wt_doc, f"{rel_tpl}/governance/Makefile": mk_doc}
        if is_tech
        else {f"{rel_tpl}/assets/canonical_snippet.md": sn_doc}
    )
    files_to_write: dict[str, str] = {
        f"{rel_tpl}/template.json": json.dumps(tpl_manifest, indent=2, ensure_ascii=False) + "\n",
        f"{rel_tpl}/rules/{eff_rule}": (
            f'---\ntrigger: always_on\ndescription: "Rules for {template_name} ({kind})."\n---\n\n'
            f"# {template_name} Governance Rules ({kind})\n\n## Scope & Surface Target\n"
            f"- **Template Pack**: `{rel_tpl}/` (`{kind}`).\n\n## Normative Invariants\n"
            f"- Follow the canonical patterns defined in `{rel_tpl}/`.\n\n"
            "## Verification & Sign-Off Gates\n- [ ] Verify zero drift via `zcg diff-project`.\n"
        ),
        f"{rel_tpl}/skills/{template_name}-guide/SKILL.md": (
            f'---\nname: {template_name}-guide\ndescription: "Guide for {template_name}."\n---\n\n'
            f"# {template_name} Guide\n\n1. Review `{rel_tpl}/rules/{eff_rule}`.\n"
            "2. Verify invariants via `zcg diff-project` and promote upward via `--create-pr`.\n"
        ),
        **extra_files,
    }
    if not dry_run:
        for rel_path, content in files_to_write.items():
            full_path = repo_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
        if (m_path := repo_dir / NODE_MANIFEST_REL_PATH).is_file():
            m = load_node_manifest(repo_dir)
            def_st = m.get("default_stack_templates", [])
            m["default_stack_templates"] = merge_unique_strings(def_st, [template_name])
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
    engine_dir: Path | None = None, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Materialize template packs and 0..N layer rules/bindings into a target project."""
    eff_eng = engine_dir or repo_dir
    c_prec, s_prec = ROLE_DEFAULT_PRECEDENCE["corporate"], ROLE_DEFAULT_PRECEDENCE["service-node"]
    root_m = load_node_manifest(repo_dir) or {
        "layer_id": "root", "layer_role": "corporate", "precedence": c_prec,
    }  # fmt: skip
    cand_layers: list[tuple[str, Path, dict[str, Any]]] = [("root", repo_dir, root_m)]
    if (layers_dir := repo_dir / "layers").is_dir():
        subs = (
            s for s in sorted(layers_dir.iterdir()) if s.is_dir() and not s.name.startswith(".")
        )
        for sub in subs:
            sub_m = load_node_manifest(sub) or {
                "layer_id": sub.name, "layer_role": "department", "precedence": s_prec,
            }  # fmt: skip
            cand_layers.append((sub.name, sub, sub_m))
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
    if template_ref:
        raw_list = [r.strip() for r in template_ref.split(",") if r.strip()]
        req_refs = merge_unique_strings(def_tpls, raw_list) if include_layer_defaults else raw_list
        ordered = sorted(cand_layers, key=lambda it: it[0] != "root")
        for raw_ref in req_refs:
            lp, sep, tp = raw_ref.partition(":")
            by_l = (
                d for n, ld, _ in cand_layers if n == lp and (d := resolve_template_dir(ld, tp))
            )
            by_o = (d for _, ld, _ in ordered if (d := resolve_template_dir(ld, raw_ref)))
            fb_d = next(by_o, None) or resolve_template_dir(eff_eng, raw_ref)
            found_d = next(by_l, None) if sep else fb_d
            if found_d is None:
                if raw_ref in BUILTIN_COCKPIT_PLUGINS:
                    continue
                raise ValueError(f"Template {raw_ref!r} not found in selected layers")
            resolved_templates.append((found_d.name, found_d))
    else:
        for tpl_str in def_tpls:
            cand_d = resolve_template_dir(repo_dir, tpl_str) or resolve_template_dir(
                eff_eng, tpl_str
            )
            if cand_d is not None:
                resolved_templates.append((cand_d.name, cand_d))
    resolved_tpl_name = ",".join(t[0] for t in resolved_templates)
    mat_templates = resolve_template_lineage_chain(resolved_templates, (repo_dir, eff_eng))
    seen_names = {t[0] for t in mat_templates} | set(def_all)
    copied_files, agents_dir = list[str](), target_project_dir / ".agents"

    def _copy_file(src: Path, dest: Path, *, overwrite: bool = True, fm: bool = False) -> None:
        if dry_run:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        if overwrite:
            dest.unlink(missing_ok=True)
        shutil.copy2(src, dest)
        if fm:
            ensure_rule_file_frontmatter(dest)
        dest.chmod(dest.stat().st_mode | OWNER_WRITABLE_MODE_BIT)

    def _iter_f(d: Path) -> Iterable[Path]:
        return (p for p in sorted(d.rglob("*")) if p.is_file()) if d.is_dir() else ()

    for tpl_name, tpl_dir in mat_templates:
        for sub_name in ("rules", "skills"):
            for src_f in _iter_f(tpl_dir / sub_name):
                dest = agents_dir / sub_name / src_f.relative_to(tpl_dir / sub_name)
                copied_files.append(str(dest.relative_to(target_project_dir)))
                _copy_file(src_f, dest, fm=(sub_name == "rules" and dest.suffix == ".md"))
        gov_src = tpl_dir / "governance"
        gov_fs = [*sorted(gov_src.glob("*.md")), *sorted(gov_src.glob("Makefile"))]
        for gf in gov_fs if gov_src.is_dir() else ():
            dest_g = (agents_dir if gf.name == "SESSION.md" else target_project_dir) / gf.name
            if not dest_g.exists():
                copied_files.append(str(dest_g.relative_to(target_project_dir)))
                _copy_file(gf, dest_g, overwrite=False)
        for af in _iter_f(tpl_dir / "assets"):
            dest_a = agents_dir / "assets" / tpl_name / af.relative_to(tpl_dir / "assets")
            copied_files.append(str(dest_a.relative_to(target_project_dir)))
            _copy_file(af, dest_a)
    lineage_rows: list[str] = []
    for name, ldir, m in cand_layers:
        prec, lid = int(m.get("precedence", s_prec)), str(m.get("layer_id", name))
        role = str(m.get("layer_role", "department"))
        bindings = collect_layer_effective_bindings(ldir, m)
        lineage_rows.append(f"| `{prec}` | `{name}` | `{lid}` | `{role}` | `{len(bindings)}` |")
        layer_agents = ldir / "antigravity/.gemini/config/AGENTS.md"
        dest_rule = agents_dir / "rules" / f"layer-{prec:02d}-{name}.md"
        if name == "root" and repo_dir.resolve() == target_project_dir.resolve():
            if not dry_run:
                dest_rule.unlink(missing_ok=True)
            for sf in sorted((ldir / "antigravity/.gemini/config/skills").glob("*/SKILL.md")):
                dest_sk = agents_dir / "skills" / sf.parent.name / "SKILL.md"
                copied_files.append(str(dest_sk.relative_to(target_project_dir)))
                _copy_file(sf, dest_sk)
        elif layer_agents.is_file():
            copied_files.append(str(dest_rule.relative_to(target_project_dir)))
            _copy_file(layer_agents, dest_rule, fm=True)
    pruned_plugins: list[str] = []
    if not layers_filter or "all" in layers_filter:
        if not dry_run and (agents_dir / "rules").is_dir():
            for l_rf in (agents_dir / "rules").glob("layer-*.md"):
                if f".agents/rules/{l_rf.name}" not in copied_files:
                    l_rf.unlink(missing_ok=True)
        known_tpls = {
            **dict(iter_layer_template_dirs(eff_eng)), **dict(iter_layer_template_dirs(repo_dir))
        }  # fmt: skip
        for t_name, t_dir in ((k, v) for k, v in sorted(known_tpls.items()) if k not in seen_names):
            r_files = [
                agents_dir / "rules" / rf.name for rf in (t_dir / "rules").glob("*.md")
                if f".agents/rules/{rf.name}" not in copied_files
                and (agents_dir / "rules" / rf.name).is_file()
            ]  # fmt: skip
            s_dirs = [
                agents_dir / "skills" / sf.parent.name
                for sf in (t_dir / "skills").glob("*/SKILL.md")
                if f".agents/skills/{sf.parent.name}/SKILL.md" not in copied_files
                and (agents_dir / "skills" / sf.parent.name).is_dir()
            ]  # fmt: skip
            a_dir, rt_f = agents_dir / "assets" / t_name, agents_dir / "runtime" / f"{t_name}.json"
            if r_files or s_dirs or a_dir.is_dir() or rt_f.is_file():
                pruned_plugins.append(t_name)
                if not dry_run:
                    for rf in (*r_files, rt_f):
                        rf.unlink(missing_ok=True)
                    for sd in (*s_dirs, a_dir):
                        shutil.rmtree(sd, ignore_errors=True)
    lineage_dest, session_dest = agents_dir / "LAYER_LINEAGE.md", agents_dir / "SESSION.md"
    copied_files.extend([str(lineage_dest.relative_to(target_project_dir)), ".agents/SESSION.md"])
    if not dry_run:
        lineage_dest.parent.mkdir(parents=True, exist_ok=True)
        lang = str(root_m.get("interaction_language") or DEFAULT_INTERACTION_LANGUAGE)
        lineage_md = render_lineage_markdown(
            resolved_tpl_name, lineage_rows, interaction_language=lang
        )
        lineage_dest.write_text(lineage_md, encoding="utf-8")
        if not session_dest.exists():
            lbl = resolved_tpl_name or "default"
            s_md = f"# Session State Log\n\n## Session Log\n\n- Initialized (`{lbl}`).\n"
            session_dest.write_text(s_md, encoding="utf-8")
    return {
        "target_project_dir": str(target_project_dir), "dry_run": dry_run,
        "applied_template": resolved_tpl_name or None, "pruned_plugins": pruned_plugins,
        "participating_layers": [name for name, _d, _m in cand_layers],
        "files_materialized": merge_unique_strings(copied_files),
    }  # fmt: skip
