"""Composable Purpose x Role x Active Stacks Makefile, .agents/zcg.mk, and skills.json synthesis.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from zcg.core import constants
from zcg.core.blueprints import resolve_template_lineage_chain
from zcg.core.manifests import load_node_manifest

_RETIRED_MAKEFILE_TARGETS: Final[tuple[str, ...]] = (
    "backup-system",
    "audit-system",
    "restore-system",
    "install-antigravity",
    "provision-plugin",
    "restart-plugin",
    "healthcheck-plugin",
    "teardown-plugin",
)


def has_active_plugin_stack(
    active_templates: Sequence[str], search_roots: tuple[Path, ...] = (constants.REPO_DIR,)
) -> bool:
    """Return True if active_templates or their transitive lineage includes a plugin-stack pack."""
    if any(t in constants.BUILTIN_COCKPIT_PLUGINS for t in active_templates):
        return True
    for _name, tpl_dir in resolve_template_lineage_chain(active_templates, search_roots):
        if tpl_dir.parent.name == "plugin-stack":
            return True
        if (tj := tpl_dir / "template.json").is_file() and isinstance(
            json.loads(tj.read_text(encoding="utf-8")).get("runtime_service"), dict
        ):
            return True
    return False


def compose_node_makefile_targets(
    layer_role: str,
    *,
    active_templates: Sequence[str] = (),
    purpose: str | None = None,
    has_plugin_stack: bool | None = None,
    allow_external_links: bool = True,
    search_roots: tuple[Path, ...] = (constants.REPO_DIR,),
) -> list[str]:
    """Compose node Makefile targets across base, hierarchy, plugin_ops, and workstation blocks."""
    blocks = constants.MAKEFILE_COMPOSABLE_BLOCKS
    role = (
        "project"
        if purpose == "standalone-project"
        else (layer_role if layer_role in constants.LAYER_ROLE_MAKEFILE_TARGETS else "department")
    )
    targets = list(blocks["base"])
    if role == "corporate":
        targets.remove("complete")
    if role == "project":
        targets.remove("mcp-test")
    if not allow_external_links:
        targets = [t for t in targets if t not in ("link", "unlink")]
    targets.extend(
        ("promote", "authority", "env-gate") if role == "project" else blocks["hierarchy"]
    )
    eff_plugin = (
        has_plugin_stack
        if has_plugin_stack is not None
        else (
            has_active_plugin_stack(active_templates, search_roots)
            if active_templates
            else role != "project"
        )
    )
    if eff_plugin:
        targets.extend(blocks["plugin_ops"])
    if role == "workstation":
        targets.extend(blocks["workstation_host_ops"])
    return [t for t in targets if t in constants.LAYER_MAKEFILE_RECIPES]


def render_layer_makefile(
    layer_id: str,
    layer_role: str,
    effective_parent: Path,
    repo_dir: Path,
    *,
    active_templates: Sequence[str] = (),
    purpose: str | None = None,
    has_plugin_stack: bool | None = None,
    allow_external_links: bool = True,
    extra_search_roots: Sequence[Path] = (),
) -> str:
    """Render a composable Zero-Cloud Node Makefile scoped by Purpose x Role x Active Stacks."""
    ep_res, rd_res = effective_parent.resolve(), repo_dir.resolve()
    p_val = str(ep_res) if ep_res != rd_res else ""
    dev_repo = "$(HOME)/Projects/dev-$(notdir $(ZCG_DIR))"
    contrib_cfg = (
        f"CONTRIB_REPO ?= $(if $(wildcard {dev_repo}/{constants.NODE_MANIFEST_REL_PATH}),"
        f"{dev_repo},$(ZCG_DIR))\nTARGET_REPO ?= $(CONTRIB_REPO)\n"
        if layer_role == "corporate"
        else "TARGET_REPO ?= $(PARENT_DIR)\n"
    )
    sel = compose_node_makefile_targets(
        layer_role,
        active_templates=active_templates,
        purpose=purpose,
        has_plugin_stack=has_plugin_stack,
        allow_external_links=allow_external_links,
        search_roots=(*extra_search_roots, effective_parent, repo_dir, constants.REPO_DIR),
    )
    phony, help_l = " ".join(["help", *sel]), "\n".join(f'\t@echo "  make {t}"' for t in sel)
    recipes = "\n".join(f"{t}:\n{constants.LAYER_MAKEFILE_RECIPES[t]}" for t in sel)
    return (
        f"{constants.MAKEFILE_ROLE_HEADER_PREFIX} — {layer_id} ({layer_role})\n"
        "ZCG_DIR ?= $(HOME)/zero-cloud-gravity\n"
        "ZCG_BIN ?= $(if $(wildcard $(ZCG_DIR)/.venv/bin/zcg),$(ZCG_DIR)/.venv/bin/zcg,zcg)\n"
        f"PARENT_DIR ?= {p_val}\n{contrib_cfg}"
        "PARENT_FLAG = $(if $(PARENT_DIR),--parent-dir $(PARENT_DIR),)\n"
        "PR_FLAGS ?= --create-pr\n\n"
        f".PHONY: {phony}\n"
        f'help:\n\t@echo "Zero-Cloud Node: {layer_id} ({layer_role})"\n{help_l}\n\n{recipes}\n'
    )


def render_project_zcg_mk(layer_id: str, effective_parent: Path, repo_dir: Path) -> str:
    """Render non-invasive .agents/zcg.mk exposing prefixed zcg-* targets for project repos."""
    ep_res, rd_res = effective_parent.resolve(), repo_dir.resolve()
    p_val = str(ep_res) if ep_res != rd_res else ""
    phony = " ".join(constants.PROJECT_ZCG_MK_TARGETS)
    sync_act = (
        f"$(if $(wildcard $(CURDIR)/{constants.NODE_MANIFEST_REL_PATH}),sync-layer,apply-project)"
    )
    return (
        f"# Zero-Cloud Non-Invasive Governance Include (.agents/zcg.mk) — {layer_id}\n"
        "ZCG_DIR ?= $(HOME)/zero-cloud-gravity\n"
        "ZCG_BIN ?= $(if $(wildcard $(ZCG_DIR)/.venv/bin/zcg),$(ZCG_DIR)/.venv/bin/zcg,zcg)\n"
        f"ZCG_PARENT_DIR ?= {p_val}\n"
        "ZCG_PARENT_FLAG = $(if $(ZCG_PARENT_DIR),--parent-dir $(ZCG_PARENT_DIR),)\n"
        "ZCG_PR_FLAGS ?= --create-pr\n\n"
        f".PHONY: {phony}\n"
        f'zcg-help:\n\t@echo "Zero-Cloud Project Governance ({layer_id}):"\n'
        '\t@echo "  make zcg-status | zcg-sync | zcg-diff | zcg-task | zcg-complete | '
        'zcg-consult | zcg-promote"\n\n'
        "zcg-status:\n\t@$(ZCG_BIN) status $(CURDIR) $(ZCG_PARENT_FLAG)\n"
        f"zcg-sync:\n\t@$(ZCG_BIN) {sync_act} $(CURDIR) $(ZCG_PARENT_FLAG)\n"
        "zcg-diff:\n\t@$(ZCG_BIN) diff-project $(CURDIR) $(ZCG_PARENT_FLAG)\n"
        'zcg-task:\n\t@$(ZCG_BIN) start-task $(CURDIR) --task "$(TASK)" '
        "$(if $(TICKET),--ticket $(TICKET),)\n"
        "zcg-complete:\n\t@$(ZCG_BIN) complete-task $(CURDIR) $(ZCG_PARENT_FLAG) "
        '--task "$(TASK)" $(if $(DELIVERABLE),--deliverable "$(DELIVERABLE)",) '
        '$(if $(SUMMARY),--summary "$(SUMMARY)",) $(if $(CREATE_PR),--create-pr,)\n'
        "zcg-consult:\n\t@$(ZCG_BIN) consult-layer $(CURDIR) $(ZCG_PARENT_FLAG) "
        '--layer $(if $(LAYER),$(LAYER),self) --query "$(QUERY)" '
        "$(if $(PATH_TARGET),--path $(PATH_TARGET),) $(if $(TIER),--tier $(TIER),)\n"
        "zcg-promote:\n\t@$(ZCG_BIN) promote-from-project $(CURDIR) --source $(SOURCE) "
        "$(if $(ZCG_PARENT_DIR),--upstream-dir $(ZCG_PARENT_DIR),) "
        "$(if $(LAYER),--to-layer $(LAYER),) $(if $(TEMPLATE),--to-template $(TEMPLATE),) "
        "$(ZCG_PR_FLAGS)\n"
    )


def render_project_makefile_stub(layer_id: str) -> str:
    """Render minimal root Makefile stub including .agents/zcg.mk when no native Makefile exists."""
    return (
        f"{constants.MAKEFILE_PROJECT_HEADER_PREFIX} — {layer_id}\n"
        f"-include {constants.PROJECT_ZCG_MK_REL_PATH}\n"
    )


def is_makefile_outdated(
    ws_dir: Path,
    role: str,
    *,
    active_templates: Sequence[str] | None = None,
    allow_external_links: bool = True,
    search_roots: tuple[Path, ...] = (constants.REPO_DIR,),
) -> bool:
    """Return True if ws_dir/Makefile is a generated Makefile missing composable parity."""
    mk_path = ws_dir / "Makefile"
    if not mk_path.is_file():
        return False
    mk_txt = mk_path.read_text(encoding="utf-8")
    if role == "project":
        return mk_txt.startswith(constants.MAKEFILE_ROLE_HEADER_PREFIX)
    if not mk_txt.startswith(constants.MAKEFILE_ROLE_HEADER_PREFIX):
        return False
    if active_templates is not None:
        tpls: Sequence[str] = active_templates
    elif (ws_dir / constants.NODE_MANIFEST_REL_PATH).is_file():
        tpls = [str(x) for x in load_node_manifest(ws_dir).get("default_stack_templates", [])]
    else:
        tpls = ()
    roots = (ws_dir, *search_roots)
    req_t = compose_node_makefile_targets(
        role, active_templates=tpls, allow_external_links=allow_external_links, search_roots=roots
    )
    unwanted_plugin = (
        bool(tpls) and not has_active_plugin_stack(tpls, roots) and "\nactivate-plugin:\n" in mk_txt
    )
    return (
        any(f"\n{t}:\n" not in mk_txt for t in req_t)
        or any(f"\n{old}:\n" in mk_txt for old in _RETIRED_MAKEFILE_TARGETS)
        or unwanted_plugin
        or "ZCG_BIN ?=" not in mk_txt
        or "--upstream-dir $(TARGET_REPO)" not in mk_txt
    )


def sync_workspace_makefile(
    target_dir: Path,
    *,
    layer_id: str,
    layer_role: str,
    effective_parent: Path,
    repo_dir: Path,
    active_templates: Sequence[str] = (),
    purpose: str | None = None,
    has_plugin_stack: bool | None = None,
    allow_external_links: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Materialize composable Makefile or non-invasive .agents/zcg.mk preserving custom rules."""
    mk_path = target_dir / "Makefile"
    cur_mk = mk_path.read_text(encoding="utf-8") if mk_path.is_file() else ""
    _head, sep, rest = cur_mk.partition(constants.MAKEFILE_CUSTOM_TARGETS_MARKER)
    c_tail = f"\n{sep}{rest.strip()}\n" if sep else ""
    files_written: list[str] = []
    is_proj = layer_role == "project"
    if is_proj:
        zcg_mk_path = target_dir / constants.PROJECT_ZCG_MK_REL_PATH
        files_written.append(constants.PROJECT_ZCG_MK_REL_PATH)
        if not dry_run:
            zcg_mk_path.parent.mkdir(parents=True, exist_ok=True)
            zcg_mk_path.write_text(
                render_project_zcg_mk(layer_id, effective_parent, repo_dir), encoding="utf-8"
            )
        is_gen = not cur_mk or cur_mk.startswith(
            (constants.MAKEFILE_ROLE_HEADER_PREFIX, constants.MAKEFILE_PROJECT_HEADER_PREFIX)
        )
        desired = render_project_makefile_stub(layer_id) + c_tail
    else:
        is_gen = not cur_mk or cur_mk.startswith(constants.MAKEFILE_ROLE_HEADER_PREFIX)
        desired = (
            render_layer_makefile(
                layer_id, layer_role, effective_parent, repo_dir,
                active_templates=active_templates, purpose=purpose,
                has_plugin_stack=has_plugin_stack, allow_external_links=allow_external_links,
                extra_search_roots=(target_dir,),
            ) + c_tail
        )  # fmt: skip
    upgraded = is_gen and cur_mk != desired
    if upgraded:
        files_written.append("Makefile")
        if not dry_run:
            mk_path.parent.mkdir(parents=True, exist_ok=True)
            mk_path.write_text(desired, encoding="utf-8")
    return {
        "makefile_upgraded": upgraded,
        "makefile_preserved": bool(cur_mk) and not is_gen,
        "zcg_mk_written": is_proj,
        "files_written": files_written,
    }


def build_skills_manifest(
    *,
    active_templates: Sequence[tuple[str, Path]],
    known_templates: Sequence[tuple[str, Path]] = (),
    extra_enabled_skills: Sequence[str] = (),
    include_all_bases: bool = False,
) -> dict[str, Any]:
    """Compute filtered zcg-skills-v1 payload from active template lineage and base taxonomy."""
    active_pack_ids = {"universal-base", *(n for n, _ in active_templates)}
    valid_kinds = constants.VALID_TEMPLATE_KINDS
    active_stack_groups = sorted(
        {
            "human-stack",
            *(d.parent.name for _, d in active_templates if d.parent.name in valid_kinds),
        }
    )
    enabled: set[str] = set(extra_enabled_skills)
    for base_id, sk_tuple in constants.BASE_SKILL_TAXONOMY.items():
        if include_all_bases or base_id in active_pack_ids:
            enabled.update(sk_tuple)
    for _tname, tdir in active_templates:
        enabled.update(sf.parent.name for sf in sorted((tdir / "skills").glob("*/SKILL.md")))
    all_known: set[str] = set(enabled)
    for sk_tuple in constants.BASE_SKILL_TAXONOMY.values():
        all_known.update(sk_tuple)
    for _kname, kdir in known_templates:
        all_known.update(sf.parent.name for sf in sorted((kdir / "skills").glob("*/SKILL.md")))
    enabled_sorted = sorted(enabled)
    disabled_sorted = sorted(all_known - enabled)
    return {
        "schema_version": constants.SKILLS_MANIFEST_CONTRACT_REV,
        "active_stack_groups": active_stack_groups,
        "active_templates": sorted(active_pack_ids),
        "enabled_skills": enabled_sorted,
        "disabled_skills": disabled_sorted,
        "entries": [
            {
                "path": ".agents/skills",
                "include_only": enabled_sorted,
                "exclude": disabled_sorted,
            }
        ],
    }


def write_skills_manifest(
    target_dir: Path,
    *,
    active_templates: Sequence[tuple[str, Path]],
    known_templates: Sequence[tuple[str, Path]] = (),
    extra_enabled_skills: Sequence[str] = (),
    include_all_bases: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write .agents/skills.json (zcg-skills-v1) and return the computed manifest dictionary."""
    doc = build_skills_manifest(
        active_templates=active_templates,
        known_templates=known_templates,
        extra_enabled_skills=extra_enabled_skills,
        include_all_bases=include_all_bases,
    )
    if not dry_run:
        dest = target_dir / constants.SKILLS_MANIFEST_REL_PATH
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def materialize_agent_companion_files(
    target_project_dir: Path,
    *,
    repo_dir: Path,
    engine_dir: Path,
    root_manifest: dict[str, Any],
    active_templates: Sequence[tuple[str, Path]],
    known_templates: Sequence[tuple[str, Path]],
    copied_files: Sequence[str],
    dry_run: bool = False,
) -> list[str]:
    """Materialize .agents/zcg.mk (on project workspaces) and filtered .agents/skills.json."""
    emitted: list[str] = []
    m_rel = constants.NODE_MANIFEST_REL_PATH
    tgt_m = load_node_manifest(target_project_dir) if (target_project_dir / m_rel).is_file() else {}
    if str(tgt_m.get("layer_role", "project")) == "project":
        emitted.append(constants.PROJECT_ZCG_MK_REL_PATH)
        if not dry_run:
            zcg_mk = target_project_dir / constants.PROJECT_ZCG_MK_REL_PATH
            zcg_mk.parent.mkdir(parents=True, exist_ok=True)
            proj_id = str(tgt_m.get("layer_id") or target_project_dir.name)
            zcg_mk.write_text(render_project_zcg_mk(proj_id, repo_dir, engine_dir), "utf-8")
    extra_sk = [
        Path(f).parent.name
        for f in copied_files
        if f.startswith(".agents/skills/") and f.endswith("/SKILL.md")
    ]
    is_oss_self = (
        repo_dir.resolve() == target_project_dir.resolve()
        and root_manifest.get("entity_kind") == "open-source"
    )
    write_skills_manifest(
        target_project_dir,
        active_templates=active_templates,
        known_templates=known_templates,
        extra_enabled_skills=extra_sk,
        include_all_bases=is_oss_self,
        dry_run=dry_run,
    )
    emitted.append(constants.SKILLS_MANIFEST_REL_PATH)
    return emitted
