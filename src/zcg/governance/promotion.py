"""Read-only 1-hop/knowledge consultation and upward asset promotion PR engine.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from zcg.core.constants import (
    AGENTS_MD_MAX_BYTES,
    CAPSULE_DIGEST_HEX_LEN,
    KEBAB_ID_RE,
    MATERIALIZED_RULE_RE,
    NODE_MANIFEST_REL_PATH,
    OWNER_WRITABLE_MODE_BIT,
    ROLE_DEFAULT_PRECEDENCE,
    SKILL_MD_MAX_LINES,
    TEMPLATE_STACK_GROUP_DIRS,
    VALID_AGENT_TIERS,
    VALID_DELEGATION_DIRS,
    VALID_EPISTEMIC_GRADES,
    VALID_TRACKER_FILES,
)
from zcg.core.epistemics import classify_knowledge_domain
from zcg.core.manifests import (
    is_oss_root_manifest,
    load_node_manifest,
    parse_skill_frontmatter,
    resolve_template_dest_dir,
    resolve_template_dir,
    sha256_file,
)
from zcg.governance.authority import (
    resolve_git_user_email,
    stage_non_destructive_proposal,
    verify_layer_operation_authority,
    verify_oss_promotion_agnosticism,
    verify_single_hop_upstream,
)
from zcg.governance.consensus import collect_layer_effective_bindings
from zcg.governance.links import resolve_linked_node_dir
from zcg.topology.identity import (
    classify_inter_layer_relationship,
    resolve_default_parent_dir,
    resolve_mounted_child_dir,
    resolve_node_entity_identity,
)

MAX_CONSULT_MATCHES: int = 8
MAX_CONSULT_EXCERPT_LINES: int = 3
MAX_CONSULT_EXCERPT_CHARS: int = 220
AGENT_ASSET_PREFIX_PARTS: int = 3
TPL_SUBDIR_OFFSET: int = 2
_EPISTEMIC_TAG_RE = re.compile(r"\b(E[0-3])\b")


def consult_layer_ephemeral(
    repo_dir: Path, workspace_dir: Path, *, target_layer: str, query: str,
    target_path: str = "corporate/policy.md", model_tier: str = "flash",
    parent_dir: Path | None = None, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Execute a strictly-read-only 1-hop/knowledge consultation returning a 4-channel digest."""
    clean_layer, clean_q = target_layer.strip(), query.strip()
    if not KEBAB_ID_RE.match(clean_layer):
        raise ValueError(f"Invalid target_layer {target_layer!r}")
    if not clean_q:
        raise ValueError("query must be a non-empty string")
    clean_tier = model_tier.strip().lower() or "flash"
    clean_path = target_path.strip() or "corporate/policy.md"
    if clean_tier not in VALID_AGENT_TIERS:
        raise ValueError(f"Invalid model_tier {model_tier!r}: must be one of {VALID_AGENT_TIERS}")
    ws, root = workspace_dir.resolve(), repo_dir.resolve()
    eff_p = resolve_default_parent_dir(ws, parent_dir)
    ws_id = str(load_node_manifest(ws).get("layer_id", ws.name))
    p_id = str(load_node_manifest(eff_p).get("layer_id", eff_p.name)) if eff_p else ""
    r_id = str(load_node_manifest(root).get("layer_id", root.name))
    sib_dirs = [
        d / clean_layer for b in (ws, ws.parent, eff_p) if b
        for d in (
            b.parent,
            *(
                g for g in sorted(b.parent.glob("*"))
                if g.is_dir() and (g.name.endswith("-org") or "knowledge" in g.name)
            ),
        )
    ]  # fmt: skip
    is_p_alias = clean_layer in ("parent", "upstream", "root", eff_p.name if eff_p else "", p_id)
    cands = [
        ws if clean_layer in ("self", ws.name, ws_id) else None,
        eff_p if eff_p and is_p_alias else None,
        ws / "layers" / clean_layer, eff_p / "layers" / clean_layer if eff_p else None,
        root / "layers" / clean_layer, resolve_linked_node_dir(ws, clean_layer),
        resolve_linked_node_dir(eff_p, clean_layer) if eff_p else None,
        resolve_mounted_child_dir(ws, clean_layer),
        resolve_mounted_child_dir(eff_p, clean_layer) if eff_p else None,
        resolve_mounted_child_dir(root, clean_layer), *sib_dirs,
        root if clean_layer in ("root", "workstation", root.name, r_id) else None,
    ]  # fmt: skip
    eval_root = next(
        (c.resolve() for c in cands if c and (c / NODE_MANIFEST_REL_PATH).is_file()), None
    )
    tpl_only_dir: Path | None = None
    if eval_root is None:
        tpl_host = next((
            h for h in (ws, eff_p, root)
            if h and resolve_template_dir(h, clean_layer) and (h / NODE_MANIFEST_REL_PATH).is_file()
        ), None)  # fmt: skip
        if tpl_host is not None:
            eval_root = tpl_host.resolve()
            tpl_only_dir = resolve_template_dir(eval_root, clean_layer)
    if eval_root is None:
        raise ValueError(f"Target layer or template not found: {clean_layer!r}")
    base_manifest = load_node_manifest(eval_root)
    t_lid = str(base_manifest.get("layer_id", eval_root.name))
    t_role = str(base_manifest.get("layer_role", "department"))
    def_grade = classify_knowledge_domain(t_lid, t_role)["default_epistemic_grade"]
    q_toks = [t for t in re.split(r"\W+", clean_q.lower()) if len(t) >= 2] or [clean_q.lower()]
    def_md_roots = [eval_root / d for d in ("docs", "templates", "corporate", ".agents/rules")]
    md_roots = [tpl_only_dir] if tpl_only_dir else def_md_roots
    matches: list[dict[str, Any]] = []
    for mr in md_roots:
        for mf in sorted(mr.rglob("*.md")) if mr and mr.is_dir() else ():
            rel_f = str(mf.relative_to(eval_root)).replace("\\", "/")
            for blk in re.split(r"(?m)^(?=#{1,4}\s+)", mf.read_text(encoding="utf-8")):
                if blk.strip() and any(tok in blk.lower() for tok in q_toks):
                    hdr = blk.strip().splitlines()[0].lstrip("#").strip() or mf.stem
                    slug = re.sub(r"[^a-z0-9]+", "-", hdr.lower()).strip("-") or mf.stem
                    raw_hex = hashlib.sha256(blk.strip().encode("utf-8")).hexdigest()
                    dig = raw_hex[:CAPSULE_DIGEST_HEX_LEN]
                    gm = _EPISTEMIC_TAG_RE.search(blk)
                    grade = (
                        gm.group(1) if (gm and gm.group(1) in VALID_EPISTEMIC_GRADES) else def_grade
                    )
                    head_lines = blk.strip().splitlines()[:MAX_CONSULT_EXCERPT_LINES]
                    exc = " ".join(ln.strip() for ln in head_lines)[:MAX_CONSULT_EXCERPT_CHARS]
                    matches.append({
                        "section": hdr, "file": rel_f, "excerpt": exc, "epistemic_grade": grade,
                        "citation_receipt": f"{t_lid}::{rel_f}#{slug}@{dig}:{grade}",
                        "capsule_token": f"rcap1:{t_lid}:{slug}:{dig}",
                    })  # fmt: skip
    q_matches = matches[:MAX_CONSULT_MATCHES]
    bindings = collect_layer_effective_bindings(eval_root, base_manifest)
    dept_prec = int(base_manifest.get("precedence", ROLE_DEFAULT_PRECEDENCE["department"]))
    digest = {
        "channel_1_domain_state": {
            "target_layer": clean_layer, "access_mode": "strictly-read-only",
            "layer_id": t_lid, "layer_role": t_role, "precedence": dept_prec,
        },
        "channel_2_affected_surface": {
            "target_path": clean_path, "inferred_plane": "domain",
            "matched_bindings_count": len(bindings),
        },
        "channel_3_invariants_and_constraints": q_matches,
        "channel_4_actionable_delta": {
            "handback_contract": "4-channel-digest+rcap1",
            "capsule_tokens": [m["capsule_token"] for m in q_matches], "match_count": len(matches),
        },
    }  # fmt: skip
    return {
        "workspace_dir": str(ws), "target_layer": clean_layer,
        "resolved_target_dir": str(eval_root), "ephemeral_fork_id": f"eph-consult-{clean_layer}",
        "access_mode": "strictly-read-only", "model_tier": clean_tier, "query": clean_q,
        "target_path": clean_path, "auto_reaped": True, "dry_run": dry_run,
        "capsule_matches": q_matches, "four_channel_digest": digest,
    }  # fmt: skip


def build_upward_promotion_pr_plan(
    project_dir: Path, target_repo_dir: Path, *, source_rel: str, dest_rel: str,
    target_layer: str, target_template: str | None, sha256: str, actor_email: str | None = None,
    contributing_org: str | None = None, contributors: str | None = None,
    validation_context: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    """Build a Pull Request plan anchored in the originating child node's context."""
    proj_m, target_m = load_node_manifest(project_dir), load_node_manifest(target_repo_dir)
    oss_anon = is_oss_root_manifest(target_m)
    src_lid = str(proj_m.get("layer_id", project_dir.name))
    src_role = str(proj_m.get("layer_role", "project"))
    src_prec = int(proj_m.get("precedence", ROLE_DEFAULT_PRECEDENCE["squad"]))
    source_layer_id = "enterprise-root-0" if oss_anon else src_lid
    source_layer_role = "corporate" if oss_anon else src_role
    t_fallback = target_layer if target_layer != "root" else target_repo_dir.name
    target_layer_id = str(target_m.get("layer_id", t_fallback))
    raw_tauth = target_m.get("layer_authority")
    target_auth: dict[str, Any] = raw_tauth if isinstance(raw_tauth, dict) else {}
    owner_role = str(target_auth.get("owner_role", f"Layer Owner ({target_layer_id})"))
    esc = str(target_auth.get("escalation_contact", f"{owner_role} ({target_layer_id})"))
    raw_email = resolve_git_user_email(project_dir) if actor_email is None else actor_email.strip()
    proposer_email = "oss-contributor" if oss_anon else raw_email
    def_org = "Anonymous Organization (default)" if oss_anon else source_layer_id
    def_c = proposer_email or "unspecified"
    def_contrib = "Principal Enterprise Architect" if oss_anon else def_c
    eff_org = (contributing_org or "").strip() or def_org
    eff_contrib = (contributors or "").strip() or def_contrib
    def_ctx = f"Zero-Cloud Node hierarchy ({source_layer_role}, precedence {src_prec})"
    eff_ctx = (validation_context or "").strip() or def_ctx
    asset_slug = re.sub(r"[^a-z0-9]+", "-", Path(source_rel).stem.lower()).strip("-") or "asset"
    sname = Path(source_rel).name
    safe_id = re.sub(r"[^a-z0-9]+", "-", source_layer_id.lower()).strip("-") or "project"
    branch_name = f"promote/oss/{asset_slug}" if oss_anon else f"promote/{safe_id}/{asset_slug}"
    pr_title = (
        f"[OSS Promotion -> {target_layer_id}] Promote {sname}" if oss_anon
        else f"[Promotion: {source_layer_id} -> {target_layer_id}] Promote {sname}"
    )  # fmt: skip
    commit_msg = (
        f"feat(governance): promote {sname} from enterprise root-0" if oss_anon
        else f"feat(governance): promote {sname} from {source_layer_id} ({source_layer_role})"
    )  # fmt: skip
    pr_body = (
        f"## Upward Governance Promotion (`{source_layer_id}` -> `{target_layer_id}`)\n\n"
        f"- **Origin Node**: `{source_layer_id}` (`{source_layer_role}`, `{src_prec}`)\n"
        f"- **Template**: `{target_template or 'layer-root'}` · **SHA-256**: `{sha256}`\n"
        f"- **Path**: `{source_rel}` -> `{dest_rel}`\n"
    )
    gh_args = f"--title {json.dumps(pr_title)} --body {json.dumps(pr_body)}"
    cmds = [
        f"cd {target_repo_dir} && git checkout -b {branch_name}",
        f"cd {target_repo_dir} && git add {dest_rel} && git commit -m {json.dumps(commit_msg)}",
        f"cd {target_repo_dir} && git push -u origin {branch_name}",
        f"cd {target_repo_dir} && gh pr create {gh_args}",
    ]  # fmt: skip
    return {
        "origin_layer_id": source_layer_id, "proposer_email": proposer_email,
        "origin_layer_role": source_layer_role, "contributing_org": eff_org,
        "contributors": eff_contrib, "validation_context": eff_ctx, "reviewer_contact": esc,
        "target_layer_id": target_layer_id, "target_owner_role": owner_role,
        "oss_anonymized": oss_anon, "branch_name": branch_name, "commit_message": commit_msg,
        "pr_title": pr_title, "pr_body": pr_body, "git_pr_commands": cmds,
    }  # fmt: skip


def promote_project_asset_to_layer(
    repo_dir: Path, project_dir: Path, *, source_rel_path: str, target_layer: str = "root",
    target_template: str | None = None, upstream_dir: Path | None = None,
    prepare_pr: bool = False, actor_email: str | None = None,
    contributing_org: str | None = None, contributors: str | None = None,
    validation_context: str | None = None, force_overwrite: bool = False, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Promote a rule, skill, doc, or tracker from <project_dir> into a parent layer or template."""
    src_file = (project_dir / source_rel_path.strip().lstrip("/")).resolve()
    if not src_file.is_relative_to(project_dir.resolve()) or not src_file.is_file():
        raise ValueError(f"Invalid or missing project source file: {source_rel_path!r}")
    repo_resolved = upstream_dir.resolve() if upstream_dir is not None else repo_dir.resolve()
    if upstream_dir is not None:
        verify_single_hop_upstream(project_dir.resolve(), repo_resolved, actor_email=actor_email)
    layer_base = (
        repo_resolved if target_layer in ("", "root") or upstream_dir is not None
        else (repo_resolved / "layers" / target_layer).resolve()
    )  # fmt: skip
    if not layer_base.is_relative_to(repo_resolved) or not layer_base.is_dir():
        raise ValueError(f"Target layer directory not found: {target_layer!r}")
    content, target_m = src_file.read_text(encoding="utf-8"), load_node_manifest(layer_base)
    proj_m = load_node_manifest(project_dir.resolve())
    src_meta = resolve_node_entity_identity(project_dir.resolve(), proj_m)
    tgt_meta = resolve_node_entity_identity(layer_base, target_m)
    rel = classify_inter_layer_relationship(src_meta, tgt_meta)
    is_oss_target = is_oss_root_manifest(target_m)
    s_sc, t_sc = str(src_meta["visibility_scope"]), str(tgt_meta["visibility_scope"])
    is_inter_root_peer = bool(
        upstream_dir is not None and not is_oss_target
        and proj_m.get("layer_id") and target_m.get("layer_id")
        and s_sc.endswith((":root-0", ":dev")) and t_sc.endswith((":root-0", ":dev"))
        and rel["mcp_communication_mode"] == "external-peer-root0-pr-and-readonly-mcp"
    )  # fmt: skip
    if is_oss_target:
        verify_oss_promotion_agnosticism(project_dir.resolve(), content, source_rel_path)
    rel_parts = src_file.relative_to(project_dir.resolve()).parts
    tpl_idx = 2 if len(rel_parts) >= 5 and rel_parts[1] in TEMPLATE_STACK_GROUP_DIRS else 1
    is_tpl_src = (
        len(rel_parts) >= tpl_idx + 3 and rel_parts[0] == "templates"
        and rel_parts[tpl_idx + 1] in ("rules", "skills", "assets")
    )  # fmt: skip
    is_ag_asset = len(rel_parts) >= 4 and (rel_parts[0], rel_parts[1]) == (".agents", "assets")
    is_tracker = len(rel_parts) == 1 and rel_parts[0] in VALID_TRACKER_FILES
    is_gov_dir = len(rel_parts) >= 2 and rel_parts[0] in VALID_DELEGATION_DIRS
    if is_oss_target and (is_tracker or is_gov_dir):
        raise ValueError(f"OSS_PRIVATE_SURFACE_BLOCKED: Refusing '{source_rel_path}' to OSS.")
    if is_inter_root_peer and (is_tracker or (is_gov_dir and rel_parts[0] == "corporate")):
        raise ValueError(f"INTER_ROOT_PRIVATE_SURFACE_BLOCKED: Refusing '{source_rel_path}'.")
    inferred_tpl = rel_parts[2] if is_ag_asset else (rel_parts[tpl_idx] if is_tpl_src else None)
    eff_template, parent_lid = target_template or inferred_tpl, str(target_m.get("layer_id", ""))
    is_ag_rule = len(rel_parts) >= 2 and (rel_parts[0], rel_parts[1]) == (".agents", "rules")
    if (
        not eff_template and is_ag_rule and src_file.name != "AGENTS.md"
        and not MATERIALIZED_RULE_RE.match(src_file.name)
        and parent_lid and resolve_template_dir(layer_base, parent_lid) is not None
    ):  # fmt: skip
        eff_template = parent_lid
    if eff_template and not KEBAB_ID_RE.match(eff_template):
        raise ValueError(f"Invalid target_template {eff_template!r}: must be kebab-case")
    tpl_dest = resolve_template_dest_dir(layer_base, str(eff_template)) if eff_template else None
    if is_tracker or is_gov_dir:
        dest_file = layer_base / Path(*rel_parts)
    elif is_ag_asset or (is_tpl_src and rel_parts[tpl_idx + 1] == "assets"):
        offset = AGENT_ASSET_PREFIX_PARTS if is_ag_asset else tpl_idx + TPL_SUBDIR_OFFSET
        base_d = tpl_dest or (layer_base / "templates" / str(eff_template))
        dest_file = base_d / "assets" / Path(*rel_parts[offset:])
    elif src_file.name == "SKILL.md":
        lines = content.splitlines()
        if len(lines) > SKILL_MD_MAX_LINES or not lines or lines[0].strip() != "---":
            raise ValueError("Promoted SKILL.md must have YAML frontmatter and < 465 lines")
        meta = parse_skill_frontmatter(src_file, project_dir)
        if not KEBAB_ID_RE.match(meta["name"]) or not meta["description"]:
            raise ValueError("Promoted SKILL.md must have kebab-case name and description")
        sub_p = f"skills/{src_file.parent.name}/SKILL.md"
        ag_cfg = layer_base / "antigravity/.gemini/config" / sub_p
        dest_file = tpl_dest / sub_p if tpl_dest else ag_cfg
    elif tpl_dest is not None:
        dest_file = tpl_dest / "rules" / src_file.name
    else:
        dest_file = layer_base / "antigravity/.gemini/config/AGENTS.md"
        is_mat = bool(MATERIALIZED_RULE_RE.match(src_file.name))
        if dest_file.is_file() and src_file.name != "AGENTS.md" and not is_mat:
            raise ValueError(f"Refusing to overwrite AGENTS.md with {src_file.name!r}")
        if len(content.encode("utf-8")) > AGENTS_MD_MAX_BYTES:
            raise ValueError(f"Promoted AGENTS.md exceeds {AGENTS_MD_MAX_BYTES}-byte cap")
    eff_layer = "root" if layer_base == repo_resolved and upstream_dir is None else target_layer
    auth_ok = bool(verify_layer_operation_authority(
        layer_base, operation="release", actor_email=actor_email, record_blocked=False
    )["allowed"])  # fmt: skip
    staged_path, need_stg = None, not auth_ok or (prepare_pr and dest_file.is_file())
    if is_inter_root_peer and not force_overwrite:
        staged_path = str(stage_non_destructive_proposal(
            layer_base, scope_tag=f"from-peer-root-{src_meta['layer_id']}",
            file_name=dest_file.name, content=content, operation="promote-from-project",
            actor_email=actor_email or "", reason_code="INTER_ROOT_PEER_PROPOSAL", dry_run=dry_run,
        ))  # fmt: skip
        prepare_pr = True
    elif not is_tracker and not force_overwrite and need_stg:
        staged_path = str(stage_non_destructive_proposal(
            project_dir.resolve(), scope_tag=f"to-{eff_layer}", file_name=dest_file.name,
            content=content, operation="promote-from-project", actor_email=actor_email or "",
            reason_code="TARGET_PROTECTED_OR_PR_MODE", dry_run=dry_run,
        ))  # fmt: skip
        prepare_pr = True
    elif not dry_run:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        if is_tracker:
            oid = str(proj_m.get("layer_id", project_dir.name))
            orole = str(proj_m.get("layer_role", "project"))
            oprec = int(proj_m.get("precedence", ROLE_DEFAULT_PRECEDENCE["service-node"]))
            hdr = f"## Proposed from `{oid}` (`{orole}`, `precedence: {oprec}`)"
            def_t = f"# {rel_parts[0].removesuffix('.md')} — {layer_base.name}"
            cur = dest_file.read_text("utf-8").rstrip() if dest_file.is_file() else def_t
            dest_file.write_text(f"{cur}\n\n{hdr}\n\n{content.strip()}\n", encoding="utf-8")
        else:
            dest_file.unlink(missing_ok=True)
            shutil.copy2(src_file, dest_file)
            dest_file.chmod(dest_file.stat().st_mode | OWNER_WRITABLE_MODE_BIT)
    src_rel_str = str(src_file.relative_to(project_dir.resolve()))
    dest_rel_str, sha256_str = str(dest_file.relative_to(repo_resolved)), sha256_file(src_file)
    push_cmd = (
        f"zcg subtree-push {eff_layer} feat/promote-{src_file.stem}"
        if eff_layer != "root"
        else None
    )
    collab_mode = (
        "inter-root-peer-pr" if is_inter_root_peer
        else ("oss-sanitized-pr" if is_oss_target else "1hop-hierarchical")
    )  # fmt: skip
    result: dict[str, Any] = {
        "source": src_rel_str, "target_layer": eff_layer, "target_template": eff_template,
        "destination": dest_rel_str, "sha256": sha256_str, "collaboration_mode": collab_mode,
        "subtree_push_command": push_cmd, "staged_proposal": staged_path, "dry_run": dry_run,
    }  # fmt: skip
    if prepare_pr or upstream_dir is not None:
        result["promotion_pr_plan"] = build_upward_promotion_pr_plan(
            project_dir, layer_base, source_rel=src_rel_str,
            dest_rel=str(dest_file.relative_to(layer_base)), target_layer=eff_layer,
            target_template=eff_template, sha256=sha256_str, actor_email=actor_email,
            contributing_org=contributing_org, contributors=contributors,
            validation_context=validation_context,
        )  # fmt: skip
    return result
