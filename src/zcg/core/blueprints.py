"""Zero-Cloud Node Makefile, onboarding blueprint, lineage, and setup-state renderers.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from zcg.core.constants import (
    DEFAULT_INTERACTION_LANGUAGE,
    DEFAULT_SQUAD_ONBOARDING_SPEC,
    HUMAN_STACK_BLUEPRINT_HINT,
    INDIVIDUAL_MIN_PRECEDENCE,
    INTERACTION_LANGUAGE_LABELS,
    LAYER_MAKEFILE_RECIPES,
    LAYER_ROLE_MAKEFILE_TARGETS,
    MAKEFILE_ROLE_HEADER_PREFIX,
    NODE_MANIFEST_REL_PATH,
    OSS_WORKSTATION_IDS,
    PUBLIC_GOV_MAX_PRECEDENCE,
    PUBLIC_GOV_PREFIXES,
    REPO_DIR,
    ROLE_DEFAULT_COCKPIT_PLUGIN,
    ROLE_ONBOARDING_SPECS,
    TEMPLATE_STACK_GROUP_DIRS,
    TOPOLOGICAL_ROLE_CLASSES,
    VALID_ENTITY_KINDS,
    VALID_LAYER_ROLES,
)  # fmt: skip
from zcg.core.manifests import resolve_template_dir

_KICKOFF_PROMPT_RE = re.compile(
    r"## Initial Chat Kickoff Prompt \(4-Phase Customizable Progression\)\s*"
    r"```text\n([\s\S]*?)\n```"
)


def resolve_template_lineage_chain(
    initial_templates: Sequence[tuple[str, Path] | str],
    search_roots: tuple[Path, ...] = (REPO_DIR,),
) -> list[tuple[str, Path]]:
    """Expand templates transitively via template.json 'extends' and stack-group defaults."""

    def _find(ref: str) -> Path | None:
        return next(
            (r for root in search_roots if (r := resolve_template_dir(root, ref)) is not None), None
        )

    mat: list[tuple[str, Path]] = []
    for item in initial_templates:
        if isinstance(item, tuple):
            mat.append(item)
        elif (d := _find(item)) is not None:
            mat.append((item, d))
    seen, added = {n for n, _ in mat}, True
    while added:
        added = False
        for _n, d in list(mat):
            tj = d / "template.json"
            ext = (
                str(json.loads(tj.read_text(encoding="utf-8")).get("extends") or "")
                if tj.is_file()
                else ""
            )
            p_grp = d.parent.name
            grp_base = (
                "software-engineering" if p_grp in ("framework-stack", "plugin-stack") and not ext
                else ("business-base" if p_grp == "context-stack" and not ext else "")
            )  # fmt: skip
            for cand in (ext, grp_base):
                if cand and cand not in seen and (bd := _find(cand)) is not None:
                    mat.insert(0, (cand, bd))
                    seen.add(cand)
                    added = True
    return mat


def resolve_default_cockpit_plugin(
    layer_role: str,
    entity_kind: str,
    active_templates: Sequence[str],
    search_roots: tuple[Path, ...] = (REPO_DIR,),
) -> str:
    """Resolve the role-default Zero-Cloud Node Cockpit plugin along orthogonal axes."""
    if layer_role in ("workstation", "corporate", "knowledge"):
        return ROLE_DEFAULT_COCKPIT_PLUGIN[layer_role]
    lin = {n for n, _ in resolve_template_lineage_chain(active_templates, search_roots)} | set(
        active_templates
    )
    if "tutor-study-cockpit" in lin or "academic-base" in lin or "academic-curriculum" in lin:
        return ROLE_DEFAULT_COCKPIT_PLUGIN["academic"]
    if "node-work-cockpit" in lin or "business-base" in lin or "corporate-operations" in lin:
        return ROLE_DEFAULT_COCKPIT_PLUGIN["default"]
    if entity_kind == "individual":
        return ROLE_DEFAULT_COCKPIT_PLUGIN["academic"]
    return ROLE_DEFAULT_COCKPIT_PLUGIN["default"]


def is_makefile_outdated(ws_dir: Path, role: str) -> bool:
    """Return True if ws_dir/Makefile is a generated node Makefile missing current targets."""
    req_t = LAYER_ROLE_MAKEFILE_TARGETS.get(role, LAYER_ROLE_MAKEFILE_TARGETS["project"])
    mk_path = ws_dir / "Makefile"
    mk_txt = mk_path.read_text(encoding="utf-8") if mk_path.is_file() else ""
    return mk_txt.startswith(MAKEFILE_ROLE_HEADER_PREFIX) and (
        any(f"\n{t}:\n" not in mk_txt for t in req_t)
        or "ZCG_BIN ?=" not in mk_txt
        or "--upstream-dir $(TARGET_REPO)" not in mk_txt
        or "$(if $(EMAIL),--email $(EMAIL),) --service-action" not in mk_txt
    )


def render_layer_makefile(
    layer_id: str, layer_role: str, effective_parent: Path, repo_dir: Path
) -> str:
    """Render a role-specialized Zero-Cloud Node Makefile powered by the zcg CLI."""
    p_val = (
        str(effective_parent.resolve()) if effective_parent.resolve() != repo_dir.resolve() else ""
    )
    dev_repo = "$(HOME)/Projects/dev-$(notdir $(ZCG_DIR))"
    contrib_cfg = (
        f"CONTRIB_REPO ?= $(if $(wildcard {dev_repo}/{NODE_MANIFEST_REL_PATH}),"
        f"{dev_repo},$(ZCG_DIR))\nTARGET_REPO ?= $(CONTRIB_REPO)\n"
        if layer_role == "corporate"
        else "TARGET_REPO ?= $(PARENT_DIR)\n"
    )
    active = LAYER_ROLE_MAKEFILE_TARGETS.get(layer_role, LAYER_ROLE_MAKEFILE_TARGETS["department"])
    sel = [t for t in active if t in LAYER_MAKEFILE_RECIPES]
    phony = " ".join(["help", *sel])
    help_lines = "\n".join(f'\t@echo "  make {t}"' for t in sel)
    recipes = "\n".join(f"{t}:\n{LAYER_MAKEFILE_RECIPES[t]}" for t in sel)
    return (
        f"{MAKEFILE_ROLE_HEADER_PREFIX} — {layer_id} ({layer_role})\n"
        "ZCG_DIR ?= $(HOME)/zero-cloud-gravity\n"
        "ZCG_BIN ?= $(if $(wildcard $(ZCG_DIR)/.venv/bin/zcg),$(ZCG_DIR)/.venv/bin/zcg,zcg)\n"
        f"PARENT_DIR ?= {p_val}\n{contrib_cfg}"
        "PARENT_FLAG = $(if $(PARENT_DIR),--parent-dir $(PARENT_DIR),)\n"
        "PR_FLAGS ?= --create-pr\n\n"
        f".PHONY: {phony}\n"
        f'help:\n\t@echo "Zero-Cloud Node: {layer_id} ({layer_role})"\n{help_lines}\n\n{recipes}\n'
    )


def render_layer_onboarding_readme(
    layer_id: str,
    layer_role: str,
    effective_prec: int,
    own_tpl_id: str,
    active_templates: list[str],
    parent_id: str | None = None,
    *,
    entity_kind: str | None = None,
    interaction_language: str = DEFAULT_INTERACTION_LANGUAGE,
) -> str:
    """Render a role-specific Zero-Cloud Node Setup Blueprint and 4-Phase Kickoff Prompt."""
    tier_title, scope_hint, children_hint, next_cmd_goal = ROLE_ONBOARDING_SPECS.get(
        layer_role, DEFAULT_SQUAD_ONBOARDING_SPEC
    )
    tpl_csv = ", ".join(f"`{t}`" for t in active_templates) or "`none`"
    parent_label = f"`{parent_id}`" if parent_id else "`open-source-root`"
    def_lbl = INTERACTION_LANGUAGE_LABELS[DEFAULT_INTERACTION_LANGUAGE]
    lang_label = INTERACTION_LANGUAGE_LABELS.get(interaction_language, def_lbl)
    lin_names = {n for n, _ in resolve_template_lineage_chain(active_templates)} | set(
        active_templates
    )
    is_ind_specialty = (
        entity_kind == "individual"
        or effective_prec >= INDIVIDUAL_MIN_PRECEDENCE
        or "academic-base" in lin_names
    ) and layer_role != "workstation"
    is_academic = "academic-base" in lin_names or is_ind_specialty
    branch_strategy = (
        f"`direct` (`['dev', 'pro']` — `master` = common baseline DNA in "
        f"`templates/{own_tpl_id}/rules/{own_tpl_id}.md`; `context_branches` (`specialty/*`, "
        f"`hat/*`, `machine/*`) isolate context/tracks with `0` `env/tst` or `env/pre` branches; "
        f"reconcile shared rules to `master` and universal habits to {parent_label})"
        if (entity_kind == "individual" or effective_prec >= INDIVIDUAL_MIN_PRECEDENCE)
        else (
            "`staged` (`['dev', 'tst', 'pre', 'pro']` — `master` = enacted `pro` baseline + "
            "optional `context_branches` (`specialty/*`, `hat/*`, `machine/*`); work promotes via "
            "`feature/*` or `directive/*` (`dev`) -> `env/tst` -> `env/pre` -> `master` (`pro`))"
        )
    )
    phase_b = (
        f"Phase B (Master Pedagogical DNA, Parallel specialty/* Tracks & Syllabus): Keep master "
        f"strictly for universal teaching rules in templates/{own_tpl_id}/rules/{own_tpl_id}.md, "
        f"create/switch specialty/<track> branches, author SYLLABUS.md across School (M1) -> "
        f"University (M2) -> Professional (M3) -> Mastery (M4), set domain-<topic>:M1 in "
        f".agents/SESSION.md, and scaffold our first lesson."
        if is_academic
        else (
            "Phase B (Epistemic Knowledge & Spec Atlas): Structure "
            "docs/{reference,architecture,guides}/ (< 465 lines) with E3..E0 epistemic "
            "grades and citation_receipt anchors."
            if layer_role == "knowledge"
            else (
                "Phase B (Root 0 Roster, Surface Bindings, Departments & Knowledge Twin): "
                "Configure .github/CODEOWNERS (make roster), surface_bindings, and output "
                f"zcg {next_cmd_goal} plus our symmetric public --role knowledge twin "
                "(org-*/gov-*/sci-*/geo-*)."
                if layer_role == "corporate"
                else "Phase B (Roster, Surface Bindings & Child Topology): Configure "
                ".github/CODEOWNERS (make roster), optional plugin-stack plugins "
                f"(make apply-template), and output zcg {next_cmd_goal}."
            )
        )
    )
    phase_d = (
        f"Phase D (Two-Level Personal Reconciliation & Sync): Reconcile cross-subject pedagogical "
        f"improvements from specialty/* into {layer_id}:master, run make sync STRATEGY=reconcile, "
        f"and promote universal workstation habits 1-hop upward to {parent_label} via /enrich and "
        "make promote before /sclose."
        if is_ind_specialty
        else (
            "Phase D (Upward Enrichment & Sync Reconciliation): Reconcile upstream updates via "
            "make sync STRATEGY=reconcile (make upstream-diff), verify make env-gate "
            "ENV=tst|pre|pro, and promote reusable rules upward via /enrich and make promote "
            "before /sclose."
        )
    )
    return (
        f"# {layer_id} (`{layer_role}`, `precedence: {effective_prec}`)\n\n"
        f"## Layer Setup Blueprint ({tier_title})\n\n"
        f"- **Node ID & Role**: `{layer_id}` (`{layer_role}`, `precedence: {effective_prec}`)\n"
        f"- **1-Hop Upstream Parent**: {parent_label}\n"
        f"- **Active Template Packs**: {tpl_csv}\n"
        f"- **Branch & Promotion Pipeline (`promotion_pipeline`)**: {branch_strategy}\n"
        f"- **Human-Stack Profile (Optional)**: {HUMAN_STACK_BLUEPRINT_HINT}\n"
        f"- **Interaction Language (`--lang`)**: `{interaction_language}` "
        f"(`{lang_label}` — repo artifacts 100% English)\n"
        f"- **Mission, Scope & Core Invariants**: {scope_hint}\n"
        f"- **Downstream Topology (Next Tier)**: {children_hint}\n"
        f"- **Authorized Layer Owner (`set-authority`)**: [Fill: Role title & owner email]\n\n"
        f"## Initial Chat Kickoff Prompt (4-Phase Customizable Progression)\n\n```text\n"
        f"Phase A (Setup & Purpose Alignment): Read the filled Layer Setup Blueprint in README.md, "
        f"{NODE_MANIFEST_REL_PATH}, and .agents/LAYER_LINEAGE.md. Tailor "
        f"antigravity/.gemini/config/AGENTS.md and templates/{own_tpl_id}/rules/{own_tpl_id}.md "
        "with our mission and invariants without duplicating upstream rules, then run make sync "
        "&& make diff and update the Node Work & Sprint Ledger (WORKROAD.md / WORKTASK.md).\n"
        f"{phase_b}\n"
        "Phase C (Daily Bounded-Lot Execution & Verification): Claim work via make task "
        'TASK="<id>", execute 1 bounded lot per turn (3-5 files) with active-layer verification, '
        "and checkpoint via /continue.\n"
        f"{phase_d}\n```\n\n"
        "## Upstream Upgrade & Version Reconciliation Prompt (4-Step Guided Flow)\n\n```text\n"
        "Step 1 (Topology & Horizon Audit): /sopen — Run make status (inspect sync_topology "
        "4-stage DAG & promotion_pipeline), make horizon, and make upstream-diff against "
        f"{parent_label}.\n"
        "Step 2 (Zero-Loss Node & Schema Reconciliation): Run make sync STRATEGY=reconcile "
        f"(or STRATEGY=merge) to upgrade Makefile, {NODE_MANIFEST_REL_PATH}, and inherited "
        f"templates while preserving sovereign rules in templates/{own_tpl_id}/rules/"
        f"{own_tpl_id}.md.\n"
        "Step 3 (Selective Stack & Node Plugin Review): Evaluate whether any newly available "
        "context-stack, framework-stack, or plugin-stack pack adds genuine value without "
        "saturating context, then verify make diff (0 drift).\n"
        "Step 4 (Environment / Mastery Gate & Closure): Validate make env-gate ENV=pro "
        "(or ENV=tst|pre|pro on staged enterprise nodes) and close via /sclose.\n```\n"
    )


def render_lineage_markdown(
    resolved_tpl_name: str,
    rows: list[str],
    *,
    interaction_language: str = DEFAULT_INTERACTION_LANGUAGE,
) -> str:
    """Render .agents/LAYER_LINEAGE.md with participating layers and Level 4 Project Blueprint."""
    tpl_label = resolved_tpl_name or "none"
    def_lbl = INTERACTION_LANGUAGE_LABELS[DEFAULT_INTERACTION_LANGUAGE]
    lang_label = INTERACTION_LANGUAGE_LABELS.get(interaction_language, def_lbl)
    lines = [
        "# Zero-Cloud Node Governance Lineage (`zero-cloud-gravity`)\n",
        f"- **Applied Template Pack**: `{tpl_label}`\n",
        "## Participating Layers (Ordered by Precedence `0..100`)\n",
        "| Precedence | Layer | Layer ID | Role | Surface Bindings |\n|---:|---|---|---|---:|",
        *rows, "",
        "## Project Setup Blueprint (Level 4 — Project & Consumer Workspace)",
        f"- **Applied Template Packs**: `{tpl_label}`",
        "- **Branch & Promotion Pipeline (`promotion_pipeline`)**: `staged` "
        "(`['dev', 'tst', 'pre', 'pro']` — `master` = enacted `pro` baseline; "
        "`dev` is ephemeral `feature/<TICKET>-*` -> `env/tst` -> `env/pre` -> `master` (`pro`))",
        f"- **Human-Stack Profile (Optional)**: {HUMAN_STACK_BLUEPRINT_HINT}",
        f"- **Interaction Language (`--lang`)**: `{interaction_language}` "
        f"(`{lang_label}` — repo artifacts 100% English)",
        "- **Project / Service Purpose**: [Fill: Core product/service mission and bounded context]",
        "- **Architecture & Integrations**: [Fill: Domain modules, stores, and UI/CLI surface]",
        "- **Phase 1 Milestone Goal**: [Fill: Initial vertical slice or MVP deliverable]", "",
        "## Initial Chat Kickoff Prompt (4-Phase Customizable Progression)\n```text",
        "Phase A (Setup & Purpose Alignment): /sopen — Read .agents/LAYER_LINEAGE.md, "
        "all inherited .agents/rules/*.md, and our Project Setup Blueprint.",
        "Phase B (Epistemic Knowledge Atlas & Sprint Ledger): Initialize README.md, "
        "docs/architecture/ (1:1:1 specs or SYLLABUS.md M1..M4), WORKROAD.md, and WORKTASK.md.",
        "Phase C (Daily Bounded-Lot Execution & Verification): Claim Task 1 via make task, "
        "propose the Pre-Edit Scope Blueprint (1 lot/turn), and verify with make verify.",
        "Phase D (Promotion & Reconciliation): Run make sync && make diff, validate "
        "make env-gate ENV=tst|pre|pro, and promote reusable discoveries via /enrich and "
        "make promote before /sclose.\n```",
    ]  # fmt: skip
    return "\n".join(lines) + "\n"


def resolve_workspace_setup_state(ws_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Resolve deterministic 3-stage onboarding state ('uninitialized'|'pending'|'configured')."""
    has_manifest = (ws_dir / NODE_MANIFEST_REL_PATH).is_file()
    lineage_file = ws_dir / ".agents/LAYER_LINEAGE.md"
    has_lineage = lineage_file.is_file()
    ortho_dims = {
        "entity_kinds": list(VALID_ENTITY_KINDS),
        "layer_roles": [*VALID_LAYER_ROLES, "project"],
        "stack_groups": list(TEMPLATE_STACK_GROUP_DIRS),
    }
    if not has_manifest and not has_lineage:
        return {
            "state": "uninitialized", "is_configured": False, "layer_role": None,
            "topological_class": None, "entity_kind": None, "orthogonal_dimensions": ortho_dims,
            "kickoff_prompt": "",
            "next_action": (
                "Run the /sopen Interactive Purpose & Bootstrap Wizard to initialize this "
                "Zero-Cloud Node along its orthogonal dimensions (entity_kind x layer_role)."
            ),
        }  # fmt: skip
    role = str(manifest.get("layer_role", "project")) if has_manifest else "project"
    lid = str(manifest.get("layer_id", ws_dir.name))
    prec = int(manifest.get("precedence", 80 if not has_manifest else 50))
    raw_ek = str(manifest.get("entity_kind") or "").strip().lower()
    unconfigured_ws_clone = (
        role == "workstation"
        and lid == "zero-cloud-gravity-workstation"
        and ws_dir.name not in ("zero-cloud-gravity", "dev-zero-cloud-gravity")
    )
    is_ind = (
        role == "workstation" and (lid not in OSS_WORKSTATION_IDS or unconfigured_ws_clone)
    ) or prec >= INDIVIDUAL_MIN_PRECEDENCE
    is_gov = 1 <= prec <= PUBLIC_GOV_MAX_PRECEDENCE or lid.lower().startswith(PUBLIC_GOV_PREFIXES)
    ek = (
        raw_ek
        if raw_ek in VALID_ENTITY_KINDS
        else ("individual" if is_ind else ("public-government" if is_gov else "enterprise"))
    )
    t_cls = TOPOLOGICAL_ROLE_CLASSES.get(role, "consumer-workspace")
    wt_p, rm_p = ws_dir / "WORKTASK.md", ws_dir / "README.md"
    wt_txt = wt_p.read_text(encoding="utf-8") if wt_p.is_file() else ""
    rm_txt = rm_p.read_text(encoding="utf-8") if rm_p.is_file() else ""
    lin_txt = lineage_file.read_text(encoding="utf-8") if has_lineage else ""
    unfilled_wt = (
        "Complete `Layer Setup Blueprint` in `README.md` and run Kickoff Prompt" in wt_txt
        and "- [x] Complete `Layer Setup Blueprint`" not in wt_txt
    )
    unfilled_bp = "[Fill:" in rm_txt if has_manifest else "[Fill:" in lin_txt
    is_pending = unconfigured_ws_clone if role == "workstation" else (unfilled_wt or unfilled_bp)
    m_prompt = _KICKOFF_PROMPT_RE.search(rm_txt) or _KICKOFF_PROMPT_RE.search(lin_txt)
    prompt_block = (
        m_prompt.group(1).strip()
        if m_prompt
        else (
            f"Phase A (Personal Root 0 Setup): Run zcg init-fork --id {ws_dir.name} "
            "--role workstation --precedence 0 --entity-kind individual.\n"
            "Phase B (Workstation & Hat Branches): Keep master for universal habits and "
            "create hat/* or machine/* branches.\n"
            "Phase C (Mounted Knowledge & Child Nodes): Register gov-*/sci-*/geo-* mounts.\n"
            "Phase D (Reconciliation): Reconcile cross-branch improvements into master."
            if unconfigured_ws_clone
            else ""
        )
    )
    return {
        "state": "pending_customization" if is_pending else "configured",
        "is_configured": not is_pending, "layer_role": role, "topological_class": t_cls,
        "entity_kind": ek, "orthogonal_dimensions": ortho_dims, "kickoff_prompt": prompt_block,
        "next_action": (
            "Present the pre-filled 4-Phase Kickoff Prompt in chat so the user can copy/adapt "
            "or confirm, then mark setup [x] in WORKTASK.md and fill [Fill: ...] fields."
            if is_pending
            else "Zero-Cloud Node is configured. Run standard /sopen session recovery, or pass "
            "'/sopen <customization intent>' to update stacks, branches, or rules."
        ),
    }  # fmt: skip
