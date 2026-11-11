"""Surface ownership bindings, multi-layer co-owner consensus, and environment promotion gates.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Any

from zcg.core.blueprints import resolve_template_lineage_chain
from zcg.core.constants import (
    DEFAULT_ENV_BRANCH_MAP,
    NODE_MANIFEST_REL_PATH,
    REPO_DIR,
    VALID_ENVIRONMENTS,
)
from zcg.core.manifests import load_node_manifest, resolve_template_dir
from zcg.governance.authority import record_governance_event
from zcg.governance.ledger import inspect_git_governance_state
from zcg.topology.identity import (
    classify_inter_layer_relationship,
    match_manifest_actor_role,
    resolve_default_parent_dir,
    resolve_hierarchical_actor_profile,
    resolve_node_entity_identity,
)

GLOB_WILDCARD_SUFFIX_LEN: int = 2
BASE_BINDING_SPECIFICITY: int = 40
TRAIT_SPECIFICITY_WEIGHT: int = 10
BUSINESS_PHASE_SEMANTICS: dict[str, str] = {
    "dev": "drafting-and-proposal",
    "tst": "peer-and-squad-review",
    "pre": "departmental-consensus",
    "pro": "enacted-corporate-policy",
}
TECHNICAL_PHASE_SEMANTICS: dict[str, str] = {
    "dev": "feature-development",
    "tst": "integration-and-qa",
    "pre": "staging-verification",
    "pro": "production-release",
}
_DECISION_RE = re.compile(r"GOVERNANCE DECISION:\s*(APPROVED|REJECTED|DEFERRED|BLOCKED)")


def collect_layer_effective_bindings(
    layer_dir: Path, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    """Merge manifest surface_bindings with active template.json recommended_surface_bindings."""
    effective, seen_ids = list[dict[str, Any]](), set[str]()
    candidates = list(manifest.get("surface_bindings") or [])
    for tpl_name in manifest.get("default_stack_templates", []):
        tpl_dir = resolve_template_dir(Path(layer_dir), str(tpl_name))
        meta_file = tpl_dir / "template.json" if tpl_dir is not None else None
        if meta_file is not None and meta_file.is_file():
            loaded = json.loads(meta_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                candidates.extend(loaded.get("recommended_surface_bindings", []))
    for raw_b in candidates:
        if isinstance(raw_b, dict):
            bid = str(raw_b.get("binding_id", ""))
            if not bid or bid not in seen_ids:
                if bid:
                    seen_ids.add(bid)
                effective.append(raw_b)
    return effective


def _glob_matches(rel_path: str, pattern: str) -> bool:
    norm_path = rel_path.strip().replace("\\", "/").lstrip("/")
    norm_pat = pattern.strip().replace("\\", "/").lstrip("/")
    collapsed = norm_pat.replace("/**/", "/").removeprefix("**/")
    prefix_pat = norm_pat[:-GLOB_WILDCARD_SUFFIX_LEN]
    return bool(
        norm_pat == "**"
        or fnmatch.fnmatchcase(norm_path, norm_pat)
        or fnmatch.fnmatchcase(norm_path, collapsed)
        or (norm_pat.endswith("/**") and norm_path.startswith(prefix_pat))
    )


def match_authoritative_surface_bindings(
    layer_nodes: list[tuple[str, Path, dict[str, Any]]], target_paths: list[str]
) -> list[dict[str, Any]]:
    """Resolve authoritative layer bindings governing each path in target_paths."""
    matches: list[dict[str, Any]] = []
    for raw_path in target_paths:
        norm_path = raw_path.strip().replace("\\", "/").lstrip("/")
        if not norm_path:
            continue
        path_hits: list[tuple[int, int, str, dict[str, Any]]] = []
        for lid, ldir, manifest in layer_nodes:
            prec = int(manifest.get("precedence", 50))
            for b in collect_layer_effective_bindings(ldir, manifest):
                mode = str(b.get("mode", "authoritative")).strip().lower()
                globs = [str(g).strip() for g in b.get("target_globs", []) if str(g).strip()]
                is_specific = (
                    mode == "authoritative" and globs and "**" not in globs and "*" not in globs
                )
                if is_specific and any(_glob_matches(norm_path, g) for g in globs):
                    traits = [t for t in b.get("traits", []) if str(t).strip(" *")]
                    spec = BASE_BINDING_SPECIFICITY + (TRAIT_SPECIFICITY_WEIGHT * len(traits))
                    item = {
                        "target_path": norm_path,
                        "owning_layer_id": lid,
                        "owning_layer_dir": str(ldir),
                        "precedence": prec,
                        "binding_id": str(b.get("binding_id", f"{lid}-binding")),
                        "specificity_score": spec,
                    }
                    path_hits.append((prec, -spec, lid, item))
        if path_hits:
            path_hits.sort(key=lambda x: (x[0], x[1], x[2]))
            co_owners = list({lid_k: h for _, _, lid_k, h in reversed(path_hits)}.values())
            co_owners.reverse()
            matches.append({**co_owners[0], "co_owning_layers": co_owners})
    return matches


def evaluate_multilayer_surface_consensus(
    ws: Path,
    surf_hits: list[dict[str, Any]],
    *,
    clean_env: str,
    eff_actor: str,
    role_prof: dict[str, Any],
    wt_txt: str,
    parent_dir: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Evaluate N-layer surface co-ownership, mutual entity scope, and consensus state."""
    ws_entity = resolve_node_entity_identity(ws, parent_dir=parent_dir)
    req_roles = ("owner",) if clean_env == "pro" else ("owner", "maintainer", "validator")
    part, appr, div, pend, blk = list[str](), list[str](), list[str](), list[str](), list[str]()
    ext_block, gates = False, list[str]()
    for hit in surf_hits:
        t_path = str(hit["target_path"])
        co_owners: list[dict[str, Any]] = list(hit.get("co_owning_layers") or [hit])
        for co in co_owners:
            own_id, own_dir = str(co["owning_layer_id"]), Path(str(co["owning_layer_dir"]))
            own_prec = int(co["precedence"])
            part.append(own_id)
            own_m = load_node_manifest(own_dir)
            own_role, _ = match_manifest_actor_role(own_m, eff_actor)
            own_entity = resolve_node_entity_identity(own_dir, own_m)
            rel = classify_inter_layer_relationship(ws_entity, own_entity)
            is_int = bool(rel["relationship_scope"] == "internal")
            dec = "PENDING"
            for ln in wt_txt.splitlines():
                if (m := _DECISION_RE.search(ln)) and (t_path in ln or own_id in ln):
                    dec = m.group(1)
            no_neg = dec not in ("REJECTED", "DEFERRED", "BLOCKED")
            root_ok = (
                is_int
                and str(role_prof["effective_role"]) == "owner"
                and int(role_prof["precedence"]) <= own_prec
                and no_neg
            )
            auth_ok = dec == "APPROVED" or ((own_role in req_roles) and no_neg) or root_ok
            st = (
                "simulated_in_dev_tst"
                if clean_env in ("dev", "tst")
                else (
                    "blocked_deadlock"
                    if dec == "BLOCKED"
                    else (
                        "divergent_iteration_required"
                        if dec in ("REJECTED", "DEFERRED")
                        else ("authorized" if auth_ok else "blocked_surface_authority")
                    )
                )
            )
            co["status"], co["ledger_decision"], co["relationship"] = st, dec, rel
            if st in ("simulated_in_dev_tst", "authorized"):
                appr.append(own_id)
            elif st == "divergent_iteration_required":
                div.append(own_id)
                gates.append(
                    f"INTER_DEPT_ITERATION_REQUIRED: '{t_path}' diverged in '{own_id}' ({dec})."
                )
            elif st == "blocked_deadlock":
                blk.append(own_id)
                if is_int:
                    gates.append(
                        f"CROSS_DEPT_ESCALATION_TO_ROOT_REQUIRED: '{t_path}' blocked by '{own_id}'."
                    )
                elif rel["external_category"] == "external:public-government":
                    ext_block = True
                    gates.append(
                        f"PUBLIC_REGULATORY_COMPLIANCE_REQUIRED: '{t_path}' blocked by '{own_id}'."
                    )
                else:
                    ext_block = True
                    gates.append(
                        f"CROSS_ENTITY_ESCALATION_REQUIRED: '{t_path}' blocked by '{own_id}'."
                    )
            else:
                pend.append(own_id)
                gates.append(f"SURFACE_AUTHORITY_REQUIRED: '{t_path}' governed by '{own_id}'.")
    c_st = (
        "ESCALATE_INTER_ENTITY_ROOTS"
        if ext_block
        else (
            "ESCALATE_TO_ROOT"
            if blk
            else ("ITERATION_REQUIRED" if (div or pend) else "RECONCILED_FLOW")
        )
    )
    return {
        "consensus_status": c_st,
        "workspace_entity": ws_entity,
        "participating_layers": list(dict.fromkeys(part)),
        "approved_layers": list(dict.fromkeys(appr)),
        "divergent_layers": list(dict.fromkeys(div)),
        "pending_layers": list(dict.fromkeys(pend)),
        "blocked_layers": list(dict.fromkeys(blk)),
    }, gates


def evaluate_environment_promotion(
    workspace_dir: Path,
    *,
    target_env: str,
    actor_email: str | None = None,
    current_branch: str | None = None,
    parent_dir: Path | None = None,
    changed_files: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Verify intrinsic promotion gates for transitioning to dev, tst, pre, or pro."""
    clean_env = target_env.strip().lower()
    if clean_env not in VALID_ENVIRONMENTS:
        raise ValueError(f"Invalid target_env {target_env!r}: must be one of {VALID_ENVIRONMENTS}")
    ws, manifest = workspace_dir.resolve(), load_node_manifest(workspace_dir.resolve())
    raw_auth = manifest.get("layer_authority")
    auth: dict[str, Any] = raw_auth if isinstance(raw_auth, dict) else {}
    auth_emails = [str(e).lower() for e in auth.get("authorized_emails", []) if str(e).strip()]
    val_emails = [str(e).lower() for e in auth.get("validator_emails", []) if str(e).strip()]
    eff_actor = (actor_email or "").strip().lower()
    role_prof = resolve_hierarchical_actor_profile(ws, actor_email=eff_actor, parent_dir=parent_dir)
    eff_role = str(role_prof["effective_role"])
    def_tpls = [str(x) for x in manifest.get("default_stack_templates", [])]
    lin_tpls = {n for n, _ in resolve_template_lineage_chain(def_tpls, (ws, REPO_DIR))} | set(
        def_tpls
    )
    is_biz = (
        str(manifest.get("layer_role", "")) in ("corporate", "department", "domain-policy")
        or "business-base" in lin_tpls
    )
    sem_map = BUSINESS_PHASE_SEMANTICS if is_biz else TECHNICAL_PHASE_SEMANTICS
    failed_gates: list[str] = []
    wt_txt = (ws / "WORKTASK.md").read_text("utf-8") if (ws / "WORKTASK.md").is_file() else ""
    wv_txt = (ws / "WORKVALI.md").read_text("utf-8") if (ws / "WORKVALI.md").is_file() else ""
    if clean_env in ("tst", "pre", "pro") and re.search(r"^\s*-\s*\[ \]\s*.*P0", wt_txt, re.M):
        failed_gates.append("OPEN_P0_WORKTASKS: Resolve all unchecked P0 items in WORKTASK.md.")
    if clean_env in ("pre", "pro") and re.search(r"^\s*-\s*\[ \]", wv_txt, re.M):
        failed_gates.append("UNVERIFIED_WORKVALI_ITEMS: Complete open checks in WORKVALI.md.")
    if (
        clean_env == "tst"
        and eff_actor
        and role_prof["has_configured_roster"]
        and eff_role == "consumer"
    ):
        failed_gates.append(
            f"UNAUTHORIZED_TST_VALIDATION: Consumer '{actor_email}' cannot promote to 'tst'."
        )
    if (
        clean_env == "pre"
        and (val_emails or role_prof["local_role"] == "member")
        and eff_role not in ("owner", "maintainer", "validator")
    ):
        act_lbl = actor_email or "<unset>"
        failed_gates.append(f"UNAUTHORIZED_PRE_VALIDATION: Actor '{act_lbl}' lacks validator role.")
    if clean_env == "pro":
        if not (ws / "CHANGELOG.md").is_file():
            failed_gates.append("MISSING_CHANGELOG: CHANGELOG.md is required for 'pro' release.")
        if auth_emails and eff_role != "owner":
            act_lbl = actor_email or "<unset>"
            failed_gates.append(f"UNAUTHORIZED_PRO_RELEASE: Actor '{act_lbl}' is not owner.")
    eff_p = resolve_default_parent_dir(ws, parent_dir)
    cand_roots = [ws, *(sorted((ws / "layers").iterdir()) if (ws / "layers").is_dir() else ())]
    if eff_p is not None and eff_p.is_dir():
        p_subs = sorted((eff_p / "layers").iterdir()) if (eff_p / "layers").is_dir() else ()
        cand_roots.extend([eff_p, *p_subs])
    valid_dirs = dict.fromkeys(
        r.resolve() for r in cand_roots if (r / NODE_MANIFEST_REL_PATH).is_file()
    )
    layer_nodes = [
        (str((m := load_node_manifest(d)).get("layer_id", d.name)), d, m) for d in valid_dirs
    ]
    surf_hits = match_authoritative_surface_bindings(layer_nodes, changed_files or [])
    consensus_summary, surf_gates = evaluate_multilayer_surface_consensus(
        ws,
        surf_hits,
        clean_env=clean_env,
        eff_actor=eff_actor,
        role_prof=role_prof,
        wt_txt=wt_txt,
        parent_dir=eff_p,
    )
    failed_gates.extend(surf_gates)
    allowed, req_branch = len(failed_gates) == 0, DEFAULT_ENV_BRANCH_MAP[clean_env]
    git_state = inspect_git_governance_state(ws, current_branch=current_branch)
    if not allowed:
        record_governance_event(
            ws,
            operation=f"check-env-promotion:{clean_env}",
            status="blocked",
            actor_email=actor_email or "",
            reason_code="ENV_PROMOTION_GATE_FAILED",
            message="; ".join(failed_gates),
            dry_run=dry_run,
        )
    promo_cmd = f"git checkout -B {req_branch}" if req_branch != "feature/*" else ""
    return {
        "workspace_dir": str(ws),
        "current_environment": git_state["active_environment"],
        "target_environment": clean_env,
        "phase_semantics": sem_map[clean_env],
        "required_branch": req_branch,
        "allowed": allowed,
        "failed_gates": failed_gates,
        "actor_role_profile": role_prof,
        "surface_ownership": surf_hits,
        "inter_departmental_consensus": consensus_summary,
        "git_promotion_command": promo_cmd,
    }
