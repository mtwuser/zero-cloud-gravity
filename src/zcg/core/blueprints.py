"""Zero-Cloud Node onboarding blueprint, lineage, and setup-state renderers.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from zcg.core.constants import (
    DEFAULT_INTERACTION_LANGUAGE,
    DEFAULT_SQUAD_ONBOARDING_SPEC,
    HUMAN_STACK_BLUEPRINT_HINT,
    INDIVIDUAL_MIN_PRECEDENCE,
    INTERACTION_LANGUAGE_LABELS,
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

_KICKOFF_HEADING = "## Initial Chat Kickoff Prompt (4-Phase Customizable Progression)"
_TEXT_FENCE_OPEN = "```text\n"
_TEXT_FENCE_CLOSE = "\n```"


def extract_kickoff_prompt(markdown_text: str) -> str:
    """Extract the fenced ```text kickoff prompt block following the canonical heading."""
    if _KICKOFF_HEADING not in markdown_text:
        return ""
    tail = markdown_text.split(_KICKOFF_HEADING, 1)[1].lstrip()
    if not tail.startswith(_TEXT_FENCE_OPEN) or _TEXT_FENCE_CLOSE not in tail:
        return ""
    return tail.removeprefix(_TEXT_FENCE_OPEN).split(_TEXT_FENCE_CLOSE, 1)[0].strip()


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
                "software-engineering"
                if p_grp in ("tool-stack", "plugin-stack") and not ext
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
    is_academic = (
        bool({"academic-base", "academic-curriculum", "tutor-study-cockpit"} & lin_names)
        and layer_role != "workstation"
    )
    is_ind_pillar = (
        entity_kind == "individual" or effective_prec >= INDIVIDUAL_MIN_PRECEDENCE
    ) and layer_role != "workstation"
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
    prompt_scope = scope_hint.removeprefix("[Fill: ").removesuffix("]")
    phase_b = (
        f"Phase B (Workstation Host Coupling, machine/* Branches & 1-Hop Pillars): Audit host "
        f"configs/manifests (make workstation-audit), keep master for universal habits while "
        f"isolating host overrides on machine/* branches, and output zcg {next_cmd_goal}."
        if layer_role == "workstation"
        else (
            f"Phase B (Master Pedagogical DNA, Parallel specialty/* Tracks & Syllabus): Keep "
            f"master strictly for universal teaching rules in templates/{own_tpl_id}/rules/"
            f"{own_tpl_id}.md, create/switch specialty/<track> branches, author SYLLABUS.md "
            "across School (M1) -> University (M2) -> Professional (M3) -> Mastery (M4), set "
            "domain-<topic>:M1 in .agents/SESSION.md, and scaffold our first lesson."
            if is_academic
            else (
                f"Phase B (Sovereign Personal Pillar Rules, Context Tracks & Knowledge Feeds): "
                f"Keep master for core pillar invariants in templates/{own_tpl_id}/rules/"
                f"{own_tpl_id}.md, isolate parallel tracks via context_branches, link read-only "
                "knowledge-feed or scoped peer nodes (zcg link), and initialize "
                "docs/architecture/ and WORKROAD.md."
                if is_ind_pillar
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
        )
    )
    phase_d = (
        "Phase D (Workstation Sync, Host Audit & Enrichment): Run make sync STRATEGY=reconcile "
        "&& make diff, verify make workstation-audit, and promote universal engine improvements "
        "upward via /enrich before /sclose."
        if layer_role == "workstation"
        else (
            f"Phase D (Two-Level Personal Reconciliation & Sync): Reconcile cross-subject or "
            f"cross-track improvements into {layer_id}:master, run make sync STRATEGY=reconcile, "
            f"and promote universal workstation habits 1-hop upward to {parent_label} via /enrich "
            "and make promote before /sclose."
            if (is_academic or is_ind_pillar)
            else (
                "Phase D (Upward Enrichment & Sync Reconciliation): Reconcile upstream updates "
                "via make sync STRATEGY=reconcile (make upstream-diff), verify make env-gate "
                "ENV=tst|pre|pro, and promote reusable rules upward via /enrich and make promote "
                "before /sclose."
            )
        )
    )
    agents_prefix = (
        "antigravity/.gemini/config/AGENTS.md and " if layer_role == "workstation" else ""
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
        f"/sopen — Configure Zero-Cloud Node '{layer_id}' ({tier_title}, "
        f"lang={interaction_language}):\n"
        f"- Mission & Scope: [Customize: {prompt_scope}]\n"
        "- Authorized Owner: [Customize: Role title & owner@domain]\n"
        f"Phase A (Setup & Purpose Alignment): Write the Mission & Authorized Owner above into "
        f"README.md (replacing all [Fill: ...] placeholders) and {NODE_MANIFEST_REL_PATH} "
        f"(zcg set-authority). Tailor {agents_prefix}"
        f"templates/{own_tpl_id}/rules/{own_tpl_id}.md with our mission and invariants "
        "without duplicating upstream rules, then "
        "run make sync && make diff and initialize WORKROAD.md / WORKTASK.md.\n"
        f"{phase_b}\n"
        "Phase C (Daily Bounded-Lot Execution & Verification): Claim work via make task "
        'TASK="<id>", execute 1 bounded lot per turn (3-5 files) with active-layer verification, '
        "and checkpoint via /continue.\n"
        f"{phase_d} Finally, mark '- [x] Complete `Layer Setup Blueprint`' in WORKTASK.md and run "
        "make activate-plugin to unlock the configured Node Workspace web UI.\n```\n\n"
        "## Upstream Upgrade & Version Reconciliation Prompt (4-Step Guided Flow)\n\n```text\n"
        "Step 1 (Topology & Horizon Audit): /sopen — Run make status (inspect sync_topology "
        "4-stage DAG & promotion_pipeline), make horizon, and make upstream-diff against "
        f"{parent_label}.\n"
        "Step 2 (Zero-Loss Node & Schema Reconciliation): Run make sync STRATEGY=reconcile "
        f"(or STRATEGY=merge) to upgrade Makefile, {NODE_MANIFEST_REL_PATH}, and inherited "
        f"templates while preserving sovereign rules in templates/{own_tpl_id}/rules/"
        f"{own_tpl_id}.md.\n"
        "Step 3 (Selective Stack & Node Plugin Review): Evaluate whether any newly available "
        "context-stack, tool-stack, or plugin-stack pack adds genuine value without "
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
    is_pending = unconfigured_ws_clone or unfilled_wt or unfilled_bp
    raw_prompt = extract_kickoff_prompt(rm_txt) or extract_kickoff_prompt(lin_txt)
    prompt_block = (
        raw_prompt
        if raw_prompt
        else (
            f"Phase A (Personal Root 0 Setup): Run zcg init-fork --id {ws_dir.name} "
            "--role workstation --precedence 90 --entity-kind individual.\n"
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
