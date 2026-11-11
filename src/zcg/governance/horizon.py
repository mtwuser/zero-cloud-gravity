"""1-hop horizon radar, section-level template diffing, and reconciliation strategies.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import contextlib
import difflib
import itertools
import json
import re
import shutil
from pathlib import Path
from typing import Any

from zcg.core import manifests
from zcg.core.constants import MATERIALIZED_RULE_RE, REPO_DIR
from zcg.governance import authority
from zcg.topology.identity import resolve_default_parent_dir, resolve_hierarchical_actor_profile
from zcg.topology.network import discover_network_topology
from zcg.topology.subtrees import inspect_mounted_children_drifts

MAX_DIFF_PREVIEW_LINES, FRONTMATTER_OPEN_LEN, FRONTMATTER_CLOSE_LEN = 20, 4, 5
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$")


def diff_project_against_layers(repo_dir: Path, project_dir: Path) -> dict[str, Any]:
    """Compare digests between <project_dir>/.agents/ and node layers/templates."""
    layer_sources: dict[str, list[tuple[str, Path]]] = {}
    agents_dir, proj_resolved = project_dir / ".agents", project_dir.resolve()
    subs = [
        (s.name, s) for s in sorted((repo_dir / "layers").glob("*"))
        if s.is_dir() and not s.name.startswith(".")
    ]  # fmt: skip
    eng_dirs = [("engine", REPO_DIR)] if repo_dir.resolve() != REPO_DIR.resolve() else []
    for lname, ldir in [("root", repo_dir), *subs, *eng_dirs]:
        for tname, tdir in manifests.iter_layer_template_dirs(ldir):
            tag = f"{lname}:{tname}"
            for rf in sorted((tdir / "rules").glob("*.md")):
                layer_sources.setdefault(f"rules/{rf.name}", []).append((tag, rf))
            for sf in sorted((tdir / "skills").glob("*/SKILL.md")):
                layer_sources.setdefault(f"skills/{sf.parent.name}/SKILL.md", []).append((tag, sf))
            for af in (p for p in sorted((tdir / "assets").rglob("*")) if p.is_file()):
                rel_a = str(af.relative_to(tdir / "assets")).replace("\\", "/")
                layer_sources.setdefault(f"assets/{tname}/{rel_a}", []).append((tag, af))
        ag_sk = ldir / "antigravity/.gemini/config/skills"
        for sf in sorted(ag_sk.glob("*/SKILL.md")) if lname != "engine" else ():
            k, v = f"skills/{sf.parent.name}/SKILL.md", (f"layer:{lname}", sf)
            cur = layer_sources.get(k, [])
            layer_sources[k] = [v, *cur] if proj_resolved == repo_dir.resolve() else [*cur, v]
    in_sync, modified_in_project, novel_in_project = [], [], []
    r_files = [(f"rules/{rf.name}", rf) for rf in sorted((agents_dir / "rules").glob("*.md"))]
    s_glob = sorted((agents_dir / "skills").glob("*/SKILL.md"))
    s_files = [(f"skills/{sf.parent.name}/SKILL.md", sf) for sf in s_glob]
    a_files = [
        (str(af.relative_to(agents_dir)).replace("\\", "/"), af)
        for af in sorted((agents_dir / "assets").rglob("*")) if af.is_file()
    ]  # fmt: skip
    for rel_key, pfile in [*r_files, *s_files, *a_files]:
        if not pfile.resolve().is_relative_to(proj_resolved):
            raise ValueError(f"Outbound symlink escape denied in project_dir: {rel_key}")
        candidates: list[tuple[str, Path]] = list(layer_sources.get(rel_key, []))
        if m := MATERIALIZED_RULE_RE.match(pfile.name):
            sub_name, rel_ag = m.group(2), "antigravity/.gemini/config/AGENTS.md"
            sub_ag = (repo_dir if sub_name == "root" else repo_dir / "layers" / sub_name) / rel_ag
            if sub_ag.is_file():
                candidates = [(f"layer:{sub_name}", sub_ag)]
        if candidates:
            p_bytes, fm_fn = pfile.read_bytes(), manifests.ensure_rule_file_frontmatter
            sync_origin = next(
                (
                    o
                    for o, sp in candidates
                    if p_bytes in (sp.read_bytes(), fm_fn(sp, sync_in_place=False).encode())
                ),
                None,
            )
            if sync_origin is not None:
                in_sync.append({"file": rel_key, "source": sync_origin})
            else:
                origin, src_path = candidates[0]
                base_r = REPO_DIR if origin.startswith("engine:") else repo_dir
                rel_t = str(src_path.relative_to(base_r))
                modified_in_project.append(
                    {"file": rel_key, "source": origin, "target_path": rel_t}
                )
        else:
            novel_in_project.append(rel_key)
    return {
        "project_dir": str(project_dir), "in_sync": in_sync,
        "modified_in_project": modified_in_project, "novel_in_project": novel_in_project,
    }  # fmt: skip


def _clear_upstream_proposal_residue(
    target_dir: Path, prop_dir: Path, tpl_name: str, src_tpl: Path, local_tpl: Path
) -> None:
    for pf in prop_dir.glob(f"{tpl_name}-*.md"):
        pf.unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        prop_dir.rmdir()
        prop_dir.parent.rmdir()
    token = f".agents/proposals/from-upstream/{tpl_name}-"
    for fp in (target_dir / "WORKTASK.md", target_dir / ".agents/SESSION.md"):
        if fp.is_file() and token in (raw := fp.read_text(encoding="utf-8")):
            kept = "\n".join(ln for ln in raw.splitlines() if token not in ln)
            cleaned = kept.removesuffix("\n\n## Governance Alerts & Pending Decisions")
            fp.write_text(f"{cleaned.rstrip()}\n", encoding="utf-8")
    local_tpl.mkdir(parents=True, exist_ok=True)
    tj, rdir = local_tpl / "template.json", src_tpl / "rules"
    td: dict[str, Any] = json.loads(tj.read_text("utf-8")) if tj.is_file() else {}
    r_glob = sorted(rdir.glob("*.md")) if rdir.is_dir() else ()
    td["reconciled_upstream_sha256"] = {rf.name: manifests.sha256_file(rf) for rf in r_glob}
    tj.write_text(json.dumps(td, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def reconcile_template_pack_sync(
    target_dir: Path, tpl_name: str, src_tpl: Path, dest_tpl: Path, *,
    strategy: str = "reconcile", is_local_newer: bool = False, dry_run: bool = False,
) -> tuple[bool, list[dict[str, Any]]]:  # fmt: skip
    """Reconcile an upstream template pack into dest_tpl using the requested sync strategy."""
    prop_dir = target_dir / ".agents/proposals/from-upstream"
    local_tpl = manifests.resolve_template_dir(target_dir, tpl_name) or dest_tpl
    if strategy == "keep-local" and local_tpl.is_dir():
        if not dry_run:
            _clear_upstream_proposal_residue(target_dir, prop_dir, tpl_name, src_tpl, local_tpl)
        return False, []
    if strategy == "reconcile" and is_local_newer:
        tj = local_tpl / "template.json"
        tj_d = json.loads(tj.read_text("utf-8")) if tj.is_file() else {}
        rec_raw = tj_d.get("reconciled_upstream_sha256")
        rec_map: dict[str, Any] = rec_raw if isinstance(rec_raw, dict) else {}
        conflicts: list[dict[str, Any]] = []
        for src_rf in sorted((src_tpl / "rules").glob("*.md")):
            src_sha, loc_rf = manifests.sha256_file(src_rf), local_tpl / "rules" / src_rf.name
            if (loc_rf.is_file() and manifests.sha256_file(loc_rf) == src_sha) or rec_map.get(
                src_rf.name
            ) == src_sha:
                continue
            staged = authority.stage_non_destructive_proposal(
                target_dir, scope_tag="from-upstream", file_name=f"{tpl_name}-{src_rf.name}",
                content=src_rf.read_text(encoding="utf-8"), operation="sync-layer",
                reason_code="UPSTREAM_TEMPLATE_CONFLICT", dry_run=dry_run,
            )  # fmt: skip
            rel_stg = str(staged.relative_to(target_dir.resolve())).replace("\\", "/")
            strats = ("accept-upstream", "merge", "keep-local")
            conflicts.append({
                "template": tpl_name, "staged_proposal": rel_stg,
                "rule_file": f"templates/{tpl_name}/rules/{src_rf.name}",
                "resolution_commands": [f"make sync STRATEGY={s}" for s in strats],
            })  # fmt: skip
        return False, conflicts
    preserved: dict[str, list[str]] = {}
    if strategy == "merge" and (local_tpl / "rules").is_dir():
        for dest_rf in sorted((local_tpl / "rules").glob("*.md")):
            src_rf = src_tpl / "rules" / dest_rf.name
            src_txt = src_rf.read_text(encoding="utf-8") if src_rf.is_file() else ""
            raw_blocks = re.split(r"(?m)^(?=#+\s)", dest_rf.read_text(encoding="utf-8"))
            blocks = [
                b.strip() for b in raw_blocks
                if b.strip().startswith("#") and b.strip().splitlines()[0].strip() not in src_txt
            ]  # fmt: skip
            if blocks:
                preserved[dest_rf.name] = blocks
    if not dry_run:
        for old_d in (local_tpl, dest_tpl):
            shutil.rmtree(old_d, ignore_errors=True)
        dest_tpl.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_tpl, dest_tpl)
        for rname, blocks in preserved.items():
            rf, joined = dest_tpl / "rules" / rname, "\n\n".join(blocks)
            rf.write_text(f"{rf.read_text('utf-8').rstrip()}\n\n{joined}\n", encoding="utf-8")
        _clear_upstream_proposal_residue(target_dir, prop_dir, tpl_name, src_tpl, dest_tpl)
    return True, []


def _parse_markdown_sections_map(markdown_text: str) -> list[tuple[str, str]]:
    text = markdown_text.strip()
    end_idx = text.find("\n---\n", FRONTMATTER_OPEN_LEN) if text.startswith("---\n") else -1
    content = text[end_idx + FRONTMATTER_CLOSE_LEN :].strip() if end_idx != -1 else text
    sections, cur_heading, cur_lines = list[tuple[str, str]](), "# Preamble", list[str]()
    for line in [*content.splitlines(), "# __END__"]:
        if _HEADING_RE.match(line.strip()):
            body_str = "\n".join(cur_lines).strip()
            if cur_heading != "# Preamble" or body_str:
                sections.append((cur_heading, body_str))
            cur_heading, cur_lines = line.strip(), []
        else:
            cur_lines.append(line)
    return sections


def _cmp_row(
    tpl: str, rel_file: str, status: str, rec: str,
    in_s: list[str], up_o: list[str], loc_o: list[str], div: list[dict[str, Any]],
) -> dict[str, Any]:  # fmt: skip
    return {
        "template": tpl, "rule_file": rel_file, "status": status, "in_sync_sections": in_s,
        "upstream_only_sections": up_o, "local_only_sections": loc_o,
        "diverged_sections": div, "recommended_action": rec,
    }  # fmt: skip


def compare_upstream_templates(
    repo_dir: Path, target_dir: Path, *, parent_dir: Path | None = None,
    template_filter: str | None = None, apply_upstream_only: bool = False, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Compare rule sections between upstream (parent/OSS) and local workspace templates."""
    ws, up = target_dir.resolve(), (parent_dir or repo_dir).resolve()
    ws_m, up_m = manifests.load_node_manifest(ws), manifests.load_node_manifest(up)
    def_st, r_fn = (
        (str(x) for x in ws_m.get("default_stack_templates", [])),
        manifests.resolve_template_dir,
    )
    cand_tpls = list(
        dict.fromkeys([*def_st, *(n for n, _ in manifests.iter_layer_template_dirs(ws))])
    )
    cand_tpls = [t for t in cand_tpls if not template_filter or t == template_filter.strip()]
    rows, safe_applied = list[dict[str, Any]](), list[str]()
    for tpl in cand_tpls:
        up_tdir, ws_tdir = r_fn(up, tpl), r_fn(ws, tpl)
        if up_tdir is None or ws_tdir is None:
            continue
        up_rules = {p.name: p for p in sorted((up_tdir / "rules").glob("*.md"))}
        ws_rules = {p.name: p for p in sorted((ws_tdir / "rules").glob("*.md"))}
        for rname in sorted(set(up_rules) | set(ws_rules)):
            up_rf, ws_rf = up_rules.get(rname), ws_rules.get(rname)
            rel_f = str((ws_rf or (ws_tdir / "rules" / rname)).relative_to(ws)).replace("\\", "/")
            if up_rf is not None and ws_rf is None:
                up_secs = [h for h, _b in _parse_markdown_sections_map(up_rf.read_text("utf-8"))]
                if apply_upstream_only:
                    safe_applied.append(rel_f)
                    if not dry_run:
                        (ws_tdir / "rules").mkdir(parents=True, exist_ok=True)
                        shutil.copy2(up_rf, ws_tdir / "rules" / rname)
                st_u, rc_u = "upstream_only_file", "adopt_upstream_file"
                rows.append(_cmp_row(tpl, rel_f, st_u, rc_u, [], up_secs, [], []))
            elif ws_rf is not None and up_rf is None:
                ws_secs = [h for h, _b in _parse_markdown_sections_map(ws_rf.read_text("utf-8"))]
                st_l, rc_l = "local_only_file", "keep_local_or_promote"
                rows.append(_cmp_row(tpl, rel_f, st_l, rc_l, [], [], ws_secs, []))
            else:
                assert up_rf is not None and ws_rf is not None  # noqa: S101
                up_map = dict(_parse_markdown_sections_map(up_rf.read_text("utf-8")))
                ws_map = dict(_parse_markdown_sections_map(ws_rf.read_text("utf-8")))
                in_sync = [h for h in up_map if h in ws_map and up_map[h] == ws_map[h]]
                up_only = [h for h in up_map if h not in ws_map]
                loc_only = [h for h in ws_map if h not in up_map]
                up_newer = up_rf.stat().st_mtime_ns > ws_rf.stat().st_mtime_ns
                diverged = [
                    {
                        "heading": h, "recommended_action": "review_and_merge_section",
                        "drift_direction": "upstream_newer" if up_newer else "local_newer",
                        "diff_preview": "\n".join(itertools.islice(difflib.unified_diff(
                            ws_map[h].splitlines(), up_map[h].splitlines(), lineterm=""
                        ), MAX_DIFF_PREVIEW_LINES)),
                    }
                    for h in up_map if h in ws_map and up_map[h] != ws_map[h]
                ]  # fmt: skip
                if apply_upstream_only and up_only:
                    safe_applied.append(rel_f)
                    if not dry_run:
                        extra = "".join(f"\n\n{h}\n\n{up_map[h]}" for h in up_only)
                        ws_rf.write_text(f"{ws_rf.read_text('utf-8').rstrip()}{extra}\n", "utf-8")
                has_add = bool(up_only or loc_only)
                st = "diverged" if diverged else ("section_additions" if has_add else "in_sync")
                fb_rec = "adopt_upstream_sections" if up_only else "keep_local_or_promote"
                rec = (
                    "none"
                    if st == "in_sync"
                    else ("review_diverged_sections" if diverged else fb_rec)
                )
                rows.append(_cmp_row(tpl, rel_f, st, rec, in_sync, up_only, loc_only, diverged))
    summary = {
        "files_compared": len(rows),
        "in_sync_files": sum(1 for f in rows if f["status"] == "in_sync"),
        "files_with_upstream_additions": sum(1 for f in rows if f["upstream_only_sections"]),
        "files_with_local_customizations": sum(1 for f in rows if f["local_only_sections"]),
        "files_with_diverged_sections": sum(1 for f in rows if f["diverged_sections"]),
    }  # fmt: skip
    return {
        "workspace_dir": str(ws), "upstream_dir": str(up), "dry_run": dry_run,
        "layer_id": str(ws_m.get("layer_id", ws.name)), "template_filter": template_filter,
        "upstream_layer_id": str(up_m.get("layer_id", up.name)), "summary": summary,
        "apply_upstream_only": apply_upstream_only, "safe_applied_files": safe_applied,
        "file_comparisons": rows,
    }  # fmt: skip


def inspect_layer_horizon(
    repo_dir: Path, workspace_dir: Path, *,
    parent_dir: Path | None = None, actor_email: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    """Inspect 1-hop downward propagation & quiet upward promotion candidates for a node."""
    ws, eff_p = workspace_dir.resolve(), resolve_default_parent_dir(workspace_dir, parent_dir)
    up, oss = (eff_p or repo_dir).resolve(), repo_dir.resolve()
    r_fn = manifests.resolve_template_dir
    ws_m, up_m = manifests.load_node_manifest(ws), manifests.load_node_manifest(up)
    is_oss = manifests.is_oss_root_manifest(up_m)
    eff_em = authority.resolve_git_user_email(ws) if actor_email is None else actor_email.strip()
    role_prof = resolve_hierarchical_actor_profile(ws, actor_email=eff_em, parent_dir=eff_p)
    a_kw = {"operation": "release", "actor_email": actor_email, "record_blocked": False}
    auth_v = authority.verify_layer_operation_authority(ws, parent_dir=eff_p, **a_kw)  # type: ignore[arg-type]
    up_auth_v = authority.verify_layer_operation_authority(up, **a_kw)  # type: ignore[arg-type]
    def_st = (str(x) for x in ws_m.get("default_stack_templates", []))
    cand_tpls = [*def_st, *(n for n, _ in manifests.iter_layer_template_dirs(ws))]
    tpl_pairs = [
        (t, u, w) for t in dict.fromkeys(cand_tpls) if (u := r_fn(up, t)) and (w := r_fn(ws, t))
    ]  # fmt: skip
    drifts: list[dict[str, Any]] = []
    for tpl, up_tdir, ws_tdir in tpl_pairs:
        tj = ws_tdir / "template.json"
        rec_raw = (json.loads(tj.read_text("utf-8")) if tj.is_file() else {}).get(
            "reconciled_upstream_sha256"
        )
        rec_map: dict[str, Any] = rec_raw if isinstance(rec_raw, dict) else {}
        for ws_rf in sorted((ws_tdir / "rules").glob("*.md")):
            up_rf = up_tdir / "rules" / ws_rf.name
            if not up_rf.is_file() or manifests.sha256_file(ws_rf) != manifests.sha256_file(up_rf):
                rel_src, rec_sha = (
                    str(ws_rf.relative_to(ws)).replace("\\", "/"),
                    rec_map.get(ws_rf.name),
                )
                up_newer = up_rf.is_file() and (
                    manifests.sha256_file(up_rf) != rec_sha if isinstance(rec_sha, str)
                    else up_rf.stat().st_mtime_ns > ws_rf.stat().st_mtime_ns
                )  # fmt: skip
                oss_ok = False
                with contextlib.suppress(ValueError):
                    authority.verify_oss_promotion_agnosticism(
                        ws, ws_rf.read_text("utf-8"), rel_src
                    )
                    oss_ok = True
                p_base = f"zcg promote-from-project {ws} --source"
                cmd = f"{p_base} {rel_src} --to-template {tpl} --upstream-dir {up} --create-pr"
                drifts.append({
                    "template": tpl, "rule_file": rel_src, "oss_agnostic": oss_ok,
                    "promote_command": cmd,
                    "drift_direction": "upstream_newer" if up_newer else "workspace_newer",
                })  # fmt: skip
    local_diff = diff_project_against_layers(ws, ws)
    child_drifts = inspect_mounted_children_drifts(ws, ws_m.get("mounted_layers", []))
    miss_sk = any(
        not (w / sf.relative_to(u)).is_file()
        for _, u, w in tpl_pairs for sf in (u / "skills").rglob("SKILL.md")
    )  # fmt: skip
    rem = {
        str(e.get("name") or e.get("layer_id") or "").strip()
        for e in (ws_m.get("mounted_layers") or [])
        if isinstance(e, dict) and str(e.get("repository") or "").strip()
    }  # fmt: skip
    need_sync = (
        any(d["drift_direction"] == "upstream_newer" for d in drifts)
        or miss_sk or any(str(d["layer_id"]) not in rem for d in child_drifts)
    )  # fmt: skip
    up_drifts = [d for d in drifts if d["drift_direction"] == "workspace_newer"]
    p_cmd = f"zcg promote-from-project {ws} --source .agents"
    novel_cmds = [
        f"{p_cmd}/{r} --upstream-dir {up} --create-pr" for r in local_diff["novel_in_project"]
    ]
    up_sugg: list[Any] = (
        [d for d in up_drifts if d["oss_agnostic"]] if is_oss
        else [*(d["promote_command"] for d in up_drifts), *novel_cmds]
    )  # fmt: skip
    sync_sfx = f" --parent-dir {up}" if eff_p is not None else ""
    ver_map = {
        k: vf.read_text("utf-8").strip() if (vf := d / "VERSION").is_file() else None
        for k, d in (("oss", oss), ("up", up), ("ws", ws))
    }
    return {
        "workspace_dir": str(ws), "layer_id": str(ws_m.get("layer_id", ws.name)),
        "layer_role": str(ws_m.get("layer_role", "project")), "is_oss_community_horizon": is_oss,
        "actor_is_layer_owner": bool(auth_v["allowed"]), "actor_role_profile": role_prof,
        "sync_topology": discover_network_topology(ws, ws_m, eff_p)["sync_topology"],
        "immediate_upstream_dir": str(up), "actor_is_upstream_owner": bool(up_auth_v["allowed"]),
        "immediate_upstream_id": str(up_m.get("layer_id", up.name)),
        "immediate_upstream_role": str(up_m.get("layer_role", "unknown")),
        "oss_root_version": ver_map["oss"], "upstream_version": ver_map["up"],
        "workspace_version": ver_map["ws"], "downward_sync_needed": need_sync,
        "child_sync_needed": bool(child_drifts), "shared_template_drifts": drifts,
        "downward_sync_command": f"zcg sync-layer {ws}{sync_sfx}",
        "downstream_layer_drifts": child_drifts, "upward_promotion_suggestions": up_sugg,
    }  # fmt: skip
