"""Task-branch workflow onboarding, completion reporting, and 1-hop child delegation.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zcg.core.constants import (
    ROLE_DEFAULT_PRECEDENCE,
    VALID_DELEGATION_DIRS,
    VALID_DELEGATION_SURFACES,
    VALID_TRACKER_FILES,
)  # fmt: skip
from zcg.core.domain import extract_ticket_ids, is_kebab_id
from zcg.core.manifests import (
    ensure_rule_file_frontmatter,
    load_node_manifest,
    resolve_template_dir,
)  # fmt: skip
from zcg.core.markdown_scan import iter_unfenced_lines, parse_checkbox_line, tokenize_alnum
from zcg.governance.policy.authority import (
    stage_non_destructive_proposal,
    verify_layer_operation_authority,
)  # fmt: skip
from zcg.governance.work.ledger import inspect_git_governance_state
from zcg.topology.identity import resolve_mounted_child_dir

MAX_BRANCH_SLUG_TOKENS: int = 5
MAX_BRANCH_SLUG_CHARS: int = 40
_INLINE_MD_PUNCT = str.maketrans("", "", "*_`~")


def _strip_inline_md(text: str) -> str:
    return text.translate(_INLINE_MD_PUNCT)


def _strip_delegated_clause(text: str) -> str:
    marker = "delegated from"
    idx = text.lower().find(marker)
    if idx == -1:
        return text
    after = text[idx + len(marker) :].lstrip()
    close_paren = after.find(")")
    has_role = "(" in after[: close_paren + 1] if close_paren != -1 else False
    return (text[:idx] + after[close_paren + 1 :]) if has_role else text


def _extract_delegated_origin(text: str) -> str:
    marker = "delegated from"
    idx = text.lower().find(marker)
    if idx == -1:
        return ""
    first_tok = text[idx + len(marker) :].lstrip().partition(" ")[0].strip("`[]():.,*")
    low_tok = first_tok.lower()
    return low_tok if is_kebab_id(low_tok) else ""


def _derive_branch_slug(task_text: str, *, strip_ticket: str = "") -> str:
    low_plain = _strip_delegated_clause(_strip_inline_md(task_text)).lower()
    low_ticket = strip_ticket.strip().lower()
    if low_ticket:
        low_plain = low_plain.replace(low_ticket, " ")
    tokens = tokenize_alnum(low_plain)
    slug = "-".join(tokens[:MAX_BRANCH_SLUG_TOKENS])[:MAX_BRANCH_SLUG_CHARS].strip("-")
    return slug or "work-item"


def start_task_workflow(
    workspace_dir: Path, *, task_query: str, tracker: str = "WORKTASK.md",
    ticket_id: str | None = None, branch_prefix: str = "feature", dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Claim a task in <tracker>, mark it [/], update SESSION.md, and return branch metadata."""
    clean_q = task_query.strip()
    if not clean_q:
        raise ValueError("task_query must be a non-empty string")
    if tracker not in VALID_TRACKER_FILES:
        raise ValueError(f"Invalid tracker {tracker!r}: must be one of {VALID_TRACKER_FILES}")
    ws = workspace_dir.resolve()
    trk_file = ws / tracker
    if not trk_file.is_file():
        raise ValueError(f"Tracker file not found: {trk_file}")
    m = load_node_manifest(ws)
    layer_id, layer_role = str(m.get("layer_id", ws.name)), str(m.get("layer_role", "project"))
    raw_trk = trk_file.read_text(encoding="utf-8")
    lines = raw_trk.splitlines()
    norm_q = _strip_inline_md(clean_q).lower()
    match_item = next(
        (
            chk
            for ln_no, line in iter_unfenced_lines(raw_trk)
            if (chk := parse_checkbox_line(line, lineno=ln_no)) is not None
            and norm_q in _strip_inline_md(line).lower()
        ),
        None,
    )
    if match_item is None:
        raise ValueError(f"No task matching {clean_q!r} found in {tracker}")
    match_idx, matched_body = match_item.lineno - 1, match_item.body
    subtasks: list[str] = []
    for sub_line in lines[match_idx + 1 :]:
        if sub_line.startswith(("  ", "\t")) and sub_line.strip():
            subtasks.append(sub_line.strip())
        elif sub_line.strip():
            break
    found_tickets = extract_ticket_ids(matched_body)
    eff_ticket = (ticket_id or "").strip().upper() or (found_tickets[0] if found_tickets else "")
    if eff_ticket and not found_tickets:
        matched_body = f"**[{eff_ticket}]** {matched_body}"
    lines[match_idx] = match_item.format_line(state="/", body=matched_body)
    origin_id = _extract_delegated_origin(matched_body)
    slug = _derive_branch_slug(matched_body, strip_ticket=eff_ticket)
    pfx = branch_prefix.strip().strip("/") or "feature"
    branch_name = f"{pfx}/{eff_ticket}-{slug}" if eff_ticket else f"{pfx}/{slug}"
    session_rel, session_file = ".agents/SESSION.md", ws / ".agents/SESSION.md"
    if not dry_run:
        trk_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        session_file.parent.mkdir(parents=True, exist_ok=True)
        def_s = "# Session State Log\n\n## Session Log\n\n- Initialized.\n"
        existing = session_file.read_text(encoding="utf-8") if session_file.is_file() else def_s
        cleaned = existing.partition("\n## Active Task\n")[0].rstrip()
        active_block = (
            f"\n\n## Active Task\n- **Tracker**: `{tracker}`\n"
            f"- **Ticket ID**: `{eff_ticket or 'unassigned'}`\n"
            f"- **Origin Layer**: `{origin_id or layer_id}`\n"
            f"- **Branch**: `{branch_name}`\n- **Task**: {matched_body}\n"
        )
        session_file.write_text(cleaned + active_block, encoding="utf-8")
    return {
        "workspace_dir": str(ws), "layer_id": layer_id, "layer_role": layer_role,
        "tracker": tracker, "task_query": clean_q, "ticket_id": eff_ticket,
        "origin_layer_id": origin_id, "matched_task": matched_body, "task_status": "in_progress",
        "subtasks": subtasks, "branch_name": branch_name,
        "git_branch_command": f"git checkout -b {branch_name}",
        "session_file": session_rel, "dry_run": dry_run,
    }  # fmt: skip


def complete_task_workflow(
    workspace_dir: Path, *, task_query: str, deliverable: str = "", summary: str = "",
    tracker: str = "WORKTASK.md", parent_dir: Path | None = None,
    actor_email: str | None = None, create_pr: bool = False, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Mark a task [x] in <tracker> and report reciprocal completion upward to the parent layer."""
    clean_q = task_query.strip()
    if not clean_q:
        raise ValueError("task_query must be a non-empty string")
    if tracker not in VALID_TRACKER_FILES:
        raise ValueError(f"Invalid tracker {tracker!r}: must be one of {VALID_TRACKER_FILES}")
    ws = workspace_dir.resolve()
    trk_file = ws / tracker
    if not trk_file.is_file():
        raise ValueError(f"Tracker file not found: {trk_file}")
    manifest = load_node_manifest(ws)
    layer_id = str(manifest.get("layer_id", ws.name))
    up_cfg = manifest.get("upstream_layer")
    up_id_default = str(up_cfg.get("layer_id", "")) if isinstance(up_cfg, dict) else ""
    raw_trk = trk_file.read_text(encoding="utf-8")
    lines = raw_trk.splitlines()
    deliv_sfx = f" *(Deliverable: `{deliverable.strip()}`)*" if deliverable.strip() else ""
    norm_q = _strip_inline_md(clean_q).lower()
    match_item = next(
        (
            chk
            for ln_no, line in iter_unfenced_lines(raw_trk)
            if (chk := parse_checkbox_line(line, lineno=ln_no)) is not None
            and norm_q in _strip_inline_md(line).lower()
        ),
        None,
    )
    if match_item is None:
        raise ValueError(f"No task matching {clean_q!r} found in {tracker}")
    matched_body = match_item.body
    new_b = matched_body if deliv_sfx in matched_body else f"{matched_body}{deliv_sfx}"
    lines[match_item.lineno - 1] = match_item.format_line(state="x", body=new_b)
    if not dry_run:
        trk_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    found_tickets = extract_ticket_ids(matched_body) or extract_ticket_ids(clean_q.upper())
    eff_ticket = found_tickets[0] if found_tickets else _derive_branch_slug(clean_q).upper()
    origin_id = _extract_delegated_origin(matched_body) or up_id_default
    res_parent = parent_dir.resolve() if parent_dir else None
    parent_updated, staged_receipt = False, None
    comp_line = (
        f"- [x] **[{eff_ticket} -> `{layer_id}` (`{tracker}`, stage: `completed (pro)`)]**: "
        f"{summary.strip() or matched_body}{deliv_sfx}"
    )
    if res_parent is not None and res_parent.is_dir():
        auth_ok = verify_layer_operation_authority(
            res_parent, operation="release", actor_email=actor_email, record_blocked=False
        )["allowed"]
        if auth_ok and not create_pr:
            parent_updated, p_wt = True, res_parent / "WORKTASK.md"
            if not dry_run:
                p_txt = p_wt.read_text("utf-8") if p_wt.is_file() else f"# Tasks — {origin_id}\n"
                p_lines, replaced = p_txt.splitlines(), False
                for i, pl in enumerate(p_lines):
                    if eff_ticket.lower() in pl.lower() and "->" in pl:
                        p_lines[i], replaced = comp_line, True
                        break
                if replaced:
                    p_wt.write_text("\n".join(p_lines) + "\n", encoding="utf-8")
                else:
                    p_hdr = "## Outbound Delegations"
                    p_base = p_txt.rstrip() if p_hdr in p_txt else f"{p_txt.rstrip()}\n\n{p_hdr}"
                    p_wt.write_text(f"{p_base}\n{comp_line}\n", encoding="utf-8")
        else:
            staged_receipt = str(stage_non_destructive_proposal(
                ws, scope_tag=f"to-{origin_id or res_parent.name}",
                file_name=f"completion-{eff_ticket.lower()}.md", content=comp_line,
                operation="complete-task", dry_run=dry_run, actor_email=actor_email or "",
                reason_code="UPWARD_COMPLETION_RECEIPT",
            ))  # fmt: skip
    branch_name = f"feature/{eff_ticket}-completed"
    commit_msg = f"feat(governance): complete {eff_ticket} in {layer_id} and report upward"
    t_repo = str(res_parent or ws)
    pr_cmds = [
        f"cd {t_repo} && git checkout -b {branch_name}",
        f"cd {t_repo} && git add WORKTASK.md && git commit -m {json.dumps(commit_msg)}",
        f"cd {t_repo} && git push -u origin {branch_name}",
    ]
    return {
        "workspace_dir": str(ws), "layer_id": layer_id, "dry_run": dry_run,
        "ticket_id": eff_ticket, "origin_layer_id": origin_id, "task_status": "completed",
        "deliverable": deliverable.strip(), "parent_tracker_updated": parent_updated,
        "staged_completion_receipt": staged_receipt,
        "completion_pr_plan": {"branch_name": branch_name, "git_pr_commands": pr_cmds},
    }  # fmt: skip


def delegate_directive_to_child(
    workspace_dir: Path, *, child_layer: str, directive: str = "",
    source_rel_path: str | None = None, ticket_id: str | None = None, priority: str = "P1",
    tracker: str = "WORKTASK.md", actor_email: str | None = None,
    force_overwrite: bool = False, create_pr: bool = False, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Delegate a 1-hop downward directive or governance artifact into child node/<tracker>."""
    clean_child, clean_dir = child_layer.strip(), directive.strip()
    if not is_kebab_id(clean_child):
        raise ValueError(f"Invalid child_layer {child_layer!r}: must be kebab-case")
    if priority not in ("P0", "P1", "P2"):
        raise ValueError(f"Invalid priority {priority!r}: must be P0, P1, or P2")
    if tracker not in VALID_DELEGATION_SURFACES:
        raise ValueError(f"Invalid tracker/surface {tracker!r}; see VALID_DELEGATION_SURFACES")
    ws, src_file, src_body = workspace_dir.resolve(), None, ""
    if source_rel_path:
        src_file = (ws / source_rel_path.strip().lstrip("/")).resolve()
        if not src_file.is_relative_to(ws) or not src_file.is_file():
            raise ValueError(f"Invalid or missing source_rel_path: {source_rel_path!r}")
        src_body = src_file.read_text(encoding="utf-8").strip()
    if not clean_dir and not src_body:
        raise ValueError("directive must be a non-empty string or source_rel_path must be provided")
    verdict = verify_layer_operation_authority(
        ws, operation="delegate-to-child", actor_email=actor_email
    )
    if not verdict["allowed"]:
        raise ValueError(f"DELEGATION_AUTHORITY_DENIED: {verdict['remediation']}")
    m = load_node_manifest(ws)
    pid, prole = str(m.get("layer_id", ws.name)), str(m.get("layer_role", "corporate"))
    mnt_dir = ws / "layers" / clean_child
    cand_dir = mnt_dir if mnt_dir.is_dir() else resolve_mounted_child_dir(ws, clean_child)
    is_1hop = cand_dir is not None and (
        cand_dir.is_relative_to(ws) or load_node_manifest(cand_dir).get("governing_root_id") == pid
    )
    tdir = cand_dir if is_1hop else None
    if tdir is None:
        raise ValueError(f"Target 1-hop child layer not found: {clean_child!r}")
    pprec = int(m.get("precedence", ROLE_DEFAULT_PRECEDENCE["corporate"]))
    eff_text = clean_dir or f"Delivered `{src_file.name if src_file else tracker}`"
    deliv_tickets = [t for t in extract_ticket_ids(eff_text) if len(t.partition("-")[2]) >= 2]
    eff_ticket = (ticket_id or "").strip().upper() or (
        deliv_tickets[0] if deliv_tickets else f"{pid.upper()}-{clean_child.upper()}-01"
    )
    entry = (
        f"- [ ] **[{priority} · {eff_ticket} · Delegated from `{pid}` "
        f"(`{prole}`, `precedence: {pprec}`)]**: {eff_text}"
    )
    def_fn = f"{eff_ticket.lower()}.md" if tracker in VALID_TRACKER_FILES else "delegated-item.md"
    fname = src_file.name if src_file is not None else def_fn
    updated, staged = list[str](), list[str]()
    stg_kw: dict[str, Any] = {
        "scope_tag": f"from-{pid}", "file_name": fname, "dry_run": dry_run,
        "operation": "delegate-to-child", "actor_email": actor_email or "",
    }  # fmt: skip
    c_auth = verify_layer_operation_authority(
        tdir, operation="delegate-to-child", actor_email=actor_email, record_blocked=False
    )
    t_on_trunk = (
        tdir.is_relative_to(ws)
        or inspect_git_governance_state(tdir)["reconciliation_guard"]["on_trunk_branch"]
    )
    is_child_owner = bool(c_auth["allowed"]) and not create_pr and (t_on_trunk or force_overwrite)
    if not is_child_owner:
        p_body = src_body or (f"# {eff_text}\n" if tracker == "rules" else entry)
        r_code = (
            "TARGET_BRANCH_GUARD" if (c_auth["allowed"] and not create_pr and not t_on_trunk)
            else "CROSS_OWNER_CHILD_DELEGATION"
        )  # fmt: skip
        p_path = stage_non_destructive_proposal(tdir, content=p_body, reason_code=r_code, **stg_kw)
        staged.append(str(p_path))
    elif tracker == "rules":
        ctpl = str(load_node_manifest(tdir).get("layer_id") or clean_child)
        r_dest = (resolve_template_dir(tdir, ctpl) or (tdir / "templates" / ctpl)) / "rules" / fname
        r_body = src_body or f"# {eff_text}\n"
        if r_dest.is_file() and not force_overwrite:
            staged.append(str(stage_non_destructive_proposal(tdir, content=r_body, **stg_kw)))
        else:
            for rp in (r_dest, tdir / ".agents/rules" / fname):
                updated.append(str(rp))
                if not dry_run:
                    rp.parent.mkdir(parents=True, exist_ok=True)
                    rp.write_text(f"{r_body.rstrip()}\n", encoding="utf-8")
                    ensure_rule_file_frontmatter(rp, sync_in_place=True)
    elif tracker in VALID_DELEGATION_DIRS:
        tfile = tdir / tracker / fname
        hdr_body = (
            f"> **Delivered from**: `{pid}` (`{prole}`, `precedence: {pprec}`)\n\n"
            f"{src_body or eff_text}"
        )
        if tfile.is_file() and not force_overwrite:
            staged.append(str(stage_non_destructive_proposal(tdir, content=hdr_body, **stg_kw)))
        else:
            updated.append(str(tfile))
            if not dry_run:
                tfile.parent.mkdir(parents=True, exist_ok=True)
                tfile.write_text(f"{hdr_body}\n", encoding="utf-8")
    else:
        tfile = tdir / tracker
        updated.append(str(tfile))
        if not dry_run:
            def_wt = f"# Active Work Tasks — {clean_child}\n\n"
            cur = tfile.read_text("utf-8") if tfile.is_file() else def_wt
            blk = f"{entry}\n\n{src_body}" if (src_body and clean_dir) else entry
            if entry not in cur:
                tfile.write_text(f"{cur}{'' if cur.endswith('\n') else '\n'}{blk}\n", "utf-8")
    p_wt, p_hdr = ws / "WORKTASK.md", "## Outbound Delegations"
    p_entry = (
        f"- [/] **[{eff_ticket} -> `{clean_child}` (`{tracker}`, stage: `delegated`)]**: {eff_text}"
    )
    if not dry_run:
        p_cur = p_wt.read_text("utf-8") if p_wt.is_file() else f"# Active Work Tasks — {pid}\n"
        p_base = p_cur.rstrip() if p_hdr in p_cur else f"{p_cur.rstrip()}\n\n{p_hdr}"
        if p_entry not in p_base:
            p_wt.write_text(f"{p_base}\n{p_entry}\n", encoding="utf-8")
    if src_file is not None and src_file.name in VALID_TRACKER_FILES:
        note = f"- *Delivered to `{clean_child}` (`{tracker}`)*"
        if not dry_run and note not in src_body:
            src_file.write_text(f"{src_body}\n{note}\n", encoding="utf-8")
    c_br = next(
        (
            str(e.get("branch") or "master") for e in (m.get("mounted_layers") or [])
            if isinstance(e, dict) and e.get("name") in (clean_child, tdir.name)
        ),
        "master",
    )  # fmt: skip
    deliv_mode = "direct_subtree" if (is_child_owner and not staged) else "proposal_pr"
    push_br = c_br if deliv_mode == "direct_subtree" else f"delegate/{eff_ticket.lower()}"
    push_cmd = (
        f"zcg subtree-push {tdir.name} {push_br}"
        if tdir.is_relative_to(ws)
        else (
            f"cd {tdir} && git add -u && git commit -m "
            f"'docs(governance): sync {eff_ticket} from {pid}' && git push origin {c_br}"
        )
    )
    return {
        "parent_layer_id": pid, "parent_layer_role": prole, "dry_run": dry_run,
        "child_layer": clean_child, "ticket_id": eff_ticket, "priority": priority,
        "tracker": tracker, "delivery_mode": deliv_mode,
        "actor_is_child_owner": bool(c_auth["allowed"]),
        "subtree_push_command": push_cmd, "delegated_entry": entry,
        "parent_ledger_entry": p_entry, "updated_paths": updated, "staged_proposals": staged,
    }  # fmt: skip
