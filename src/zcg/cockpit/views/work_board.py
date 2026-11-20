"""Visual 3-column Kanban Work Board, Filter Bar, Work Inbox & 1-Hop Shared Work Channels.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import itertools
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.views.shell_chrome import resolve_human_role_label
from zcg.core.constants import INDIVIDUAL_MIN_PRECEDENCE, VALID_KNOWLEDGE_PREFIXES
from zcg.core.manifests import load_node_manifest
from zcg.governance.policy.mesh_relations import (
    is_airlocked_wallet_node,
    resolve_mesh_governance_policy,
)
from zcg.governance.work.work_inbox import (
    VALID_SCOPE_FILTERS,
    VALID_TASK_PRIORITIES,
    filter_kanban_items,
    inspect_work_inbox,
)  # fmt: skip
from zcg.topology.network import discover_network_topology

OUTBOUND_RECEIPTS_REL_PATH: Final[str] = ".zcg/runtime/ledger/outbound_exchange.jsonl"
MAX_COLUMN_CARDS: Final[int] = 10
MAX_QUERY_SNIPPET_CHARS: Final[int] = 48
_DIR_RANK: Final[dict[str, int]] = {"parent": 0, "child": 1, "peer": 2}
_SCOPE_LABELS: Final[dict[str, str]] = {
    "all": "All Scopes", "own": "Own Node", "parent": "↑ From Parent", "cross-node": "↓/↔ Cross-Node",  # noqa: E501
}  # fmt: skip


def record_outbound_exchange_receipt(
    workspace_dir: Path, *, target_node: str, mode: str, summary: str, ref_path: str = ""
) -> dict[str, str]:
    """Append a gitignored outbound 1-hop delegation/request receipt for sender visibility."""
    entry = {
        "timestamp": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_node": target_node.strip(), "mode": mode.strip(),
        "summary": summary.strip(), "ref_path": ref_path.strip(),
    }  # fmt: skip
    out_file = workspace_dir.resolve() / OUTBOUND_RECEIPTS_REL_PATH
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_outbound_exchange_receipts(workspace_dir: Path) -> list[dict[str, str]]:
    """Read recorded outbound 1-hop task/request receipts from .zcg/runtime/ledger/."""
    out_file = workspace_dir.resolve() / OUTBOUND_RECEIPTS_REL_PATH
    if not out_file.is_file():
        return []
    receipts: list[dict[str, str]] = []
    for raw_ln in out_file.read_text(encoding="utf-8").splitlines():
        if not (clean := raw_ln.strip()):
            continue
        try:
            doc = json.loads(clean)
        except json.JSONDecodeError:
            continue
        if isinstance(doc, dict) and doc.get("target_node"):
            receipts.append({str(k): str(v) for k, v in doc.items()})
    return receipts


def collect_counterpart_work_channels(
    workspace_dir: Path, net_scope: Mapping[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Group 1-hop shared work (pending Work Inbox + outbound receipts) by counterpart node."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    m_prec = int(manifest.get("precedence", 50))
    def_ek = "individual" if m_prec >= INDIVIDUAL_MIN_PRECEDENCE else "enterprise"
    ek = str(manifest.get("entity_kind") or def_ek)
    raw_nl = (net_scope or {}).get("network_representation_links")
    if isinstance(raw_nl, Mapping) and any(
        raw_nl.get(k) for k in ("parent_home_node", "downward_child_nodes", "lateral_peers")
    ):
        p_raw, ch_raw = raw_nl.get("parent_home_node"), raw_nl.get("downward_child_nodes") or []
        pr_raw, ln_raw = raw_nl.get("lateral_peers") or [], raw_nl.get("linked_nodes") or []
    else:
        conn = discover_network_topology(ws, manifest)["node_connection_summary"]
        p_raw, ch_raw = conn["upward_governor"], conn["downward_governed_nodes"]
        pr_raw, ln_raw = conn["lateral_peers"], conn["linked_nodes"]
    channels: dict[str, dict[str, Any]] = {}

    def _register(nid: str, lrole: str, direction: str, *, mode_override: str = "") -> None:
        clean_id = nid.strip()
        if not clean_id or clean_id in channels:
            return
        is_del = mode_override == "delegate" or (not mode_override and direction == "child")
        arrow = "↑" if direction == "parent" else ("↓" if direction == "child" else "↔")
        act_lbl = "Delegate Directive (↓)" if is_del else f"Send Work Request ({arrow})"
        channels[clean_id] = {
            "node_id": clean_id, "direction": direction, "arrow": arrow,
            "human_role": resolve_human_role_label(clean_id, lrole, entity_kind=ek),
            "allowed_mode": "delegate" if is_del else "propose",
            "action_label": act_lbl, "inbound": [], "outbound": [],
        }  # fmt: skip

    own_id, pol = str(manifest.get("layer_id") or ws.name), resolve_mesh_governance_policy(ws)
    if isinstance(p_raw, Mapping) and p_raw.get("node_id"):
        _register(str(p_raw["node_id"]), str(p_raw.get("layer_role") or "root"), "parent")
    for ch in (c for c in ch_raw if isinstance(c, Mapping)):
        cid = str(ch.get("node_id") or "")
        if not is_airlocked_wallet_node(cid):
            _register(cid, str(ch.get("layer_role") or "child"), "child")
    for pr in (p for p in pr_raw if isinstance(p, Mapping)):
        pid = str(pr.get("node_id") or "").strip()
        if not pid or is_airlocked_wallet_node(pid) or pol.topology_mode == "hierarchical-only":
            continue
        if pol.topology_mode == "full-mesh":
            _register(pid, str(pr.get("layer_role") or "peer"), "peer")
            continue
        rule = next(
            (r for r in pol.lateral_channels if (r.source_node == own_id and r.target_node == pid) or (r.target_node == own_id and r.source_node == pid and r.reciprocal)),  # noqa: E501
            None,
        )  # fmt: skip
        if rule and ("propose_work" in rule.allowed_verbs or "delegate_work" in rule.allowed_verbs):
            ovr = "delegate" if "delegate_work" in rule.allowed_verbs else "propose"
            _register(pid, str(pr.get("layer_role") or "peer"), "peer", mode_override=ovr)
    for lnk in (x for x in ln_raw if isinstance(x, Mapping)):
        lid, lrole = str(lnk.get("node_id") or ""), str(lnk.get("layer_role") or "project")
        is_know = (
            lrole == "knowledge"
            or lid.startswith(VALID_KNOWLEDGE_PREFIXES)
            or str(lnk.get("relation") or "").startswith("knowledge")
        )
        if not is_know and not is_airlocked_wallet_node(lid):
            _register(lid, lrole, "peer")
    for req in inspect_work_inbox(ws)["items"]:
        if req.get("status") != "pending":
            continue
        sender = str(req["sender_node"])
        _register(sender, "peer", str(req.get("direction") or "peer"))
        channels[sender]["inbound"].append({
            "request_id": req["request_id"], "path": f"from-{sender}/{req['request_id']}",
            "summary": req["summary"], "priority": req.get("priority", "P1"),
        })  # fmt: skip

    for rec in read_outbound_exchange_receipts(ws):
        tgt = rec["target_node"]
        _register(tgt, "peer", "peer")
        channels[tgt]["outbound"].append(rec)

    enriched = [
        {**c, "active_count": len(c["inbound"]) + len(c["outbound"])} for c in channels.values()
    ]
    return sorted(
        enriched,
        key=lambda c: (0 if c["active_count"] > 0 else 1, _DIR_RANK[c["direction"]], c["node_id"]),
    )


def task_query_snippet(body: str) -> str:
    """Extract a concise non-Markdown prefix for deterministic task mutation matching."""
    clean = body.replace("**", "").replace("`", "").strip()
    head = clean.partition(":")[0].strip() or clean
    return "".join(itertools.islice(head, MAX_QUERY_SNIPPET_CHARS)).rstrip()


def _render_kanban_card(pfx: str, item: Mapping[str, str], target_sel: str) -> str:
    body = str(item.get("body") or "")
    state = str(item.get("state") or " ")
    prio = html.escape(str(item.get("priority") or "P2"))
    track = str(item.get("track") or "main")
    trk_chip = f" <span class='zcg-chip'>{html.escape(track)}</span>" if track != "main" else ""
    q_val = html.escape(task_query_snippet(body), quote=True)
    btn_html = ""
    if state in (" ", "/"):
        act_v = "claim" if state == " " else "complete"
        btn_l = "Start →" if state == " " else "Complete ✓"
        btn_c = "zcg-btn zcg-btn--secondary zcg-btn--sm" if state == " " else "zcg-btn zcg-btn--sm"
        btn_html = (
            f"<form method='post' action='{pfx}/tasks' data-zcg-post='{pfx}/tasks' "
            f"data-zcg-target='{target_sel}' class='zcg-kanban-card__act'>"
            f"<input type='hidden' name='action' value='{act_v}'>"
            "<input type='hidden' name='tracker' value='WORKTASK.md'>"
            f"<input type='hidden' name='task_text' value='{q_val}'>"
            f"<button type='submit' class='{btn_c}'>{btn_l}</button></form>"
        )
    return (
        f"<article class='zcg-kanban-card zcg-kanban-card--{html.escape(state.strip() or 'todo')}'>"
        f"<div><span class='zcg-badge'>{prio}</span>{trk_chip}</div>"
        f"<p>{html.escape(body)}</p>{btn_html}</article>"
    )


def render_kanban_columns_html(
    pfx: str, wt_items: Sequence[Mapping[str, str]], target_sel: str
) -> str:
    """Render the 3-column To Do | In Progress | Done Kanban board for WORKTASK.md."""
    cols = (
        ("todo", "To Do", [t for t in wt_items if t.get("state") == " "]),
        ("doing", "In Progress", [t for t in wt_items if t.get("state") == "/"]),
        ("done", "Done", [t for t in wt_items if t.get("state") == "x"]),
    )
    col_parts: list[str] = []
    for slug, title, bucket in cols:
        shown = list(itertools.islice(bucket, MAX_COLUMN_CARDS))
        cards_s = (
            "".join(_render_kanban_card(pfx, it, target_sel) for it in shown)
            or "<p class='zcg-muted-note'>0 items</p>"
        )
        extra = len(bucket) - len(shown)
        more_s = f"<small class='zcg-muted-note'>+{extra} more in WORKTASK.md</small>" if extra > 0 else ""  # noqa: E501  # fmt: skip
        col_parts.append(
            f"<section class='zcg-kanban-col' data-kanban-col='{slug}'>"
            f"<header class='zcg-kanban-col__head'><strong>{title}</strong>"
            f"<span class='zcg-badge'>{len(bucket)}</span></header>"
            f"<div class='zcg-kanban-col__cards'>{cards_s}{more_s}</div></section>"
        )
    return f"<div class='zcg-kanban'>{''.join(col_parts)}</div>"


def render_inbox_drawer_html(pfx: str, inbox_items: Sequence[Mapping[str, str]], tgt: str) -> str:
    """Render the Incoming Work Requests triage drawer when pending requests exist."""
    pending = [r for r in inbox_items if r.get("status") == "pending"]
    if not pending:
        return ""
    btns = (
        ("accept-todo", "Accept → To Do", "zcg-btn zcg-btn--sm"),
        ("accept-backlog", "Accept → Backlog", "zcg-btn zcg-btn--secondary zcg-btn--sm"),
        ("decline", "Decline", "zcg-btn zcg-btn--secondary zcg-btn--sm"),
    )
    rows = "".join(
        "<li class='zcg-knowledge-row'><span>"
        f"<span class='zcg-badge'>{html.escape(str(r.get('priority', 'P1')))}</span> "
        f"<code>from-{html.escape(str(r['sender_node']))}</code>: "
        f"{html.escape(str(r['summary']))}</span><span class='zcg-tabs'>"
        + "".join(
            f"<form method='post' action='{pfx}/inbox' data-zcg-post='{pfx}/inbox' "
            f"data-zcg-target='{tgt}' style='display:inline;'>"
            f"<input type='hidden' name='request_id' value='{html.escape(r['request_id'], True)}'>"
            f"<input type='hidden' name='decision' value='{dec}'>"
            f"<button type='submit' class='{cls}'>{lbl}</button></form>"
            for dec, lbl, cls in btns
        )
        + "</span></li>"
        for r in pending
    )
    return (
        "<details class='zcg-peer-channel is-active' open style='margin-bottom:0.75rem;'>"
        "<summary class='zcg-peer-channel__head'><span><strong>📥 Incoming Work Requests</strong>"
        f"</span><span class='zcg-badge'>{len(pending)} pending</span></summary>"
        f"<div class='zcg-peer-channel__body'><ul class='zcg-knowledge-list'>{rows}</ul>"
        "</div></details>"
    )


def _render_channel_card(pfx: str, ch: Mapping[str, Any], target_sel: str) -> str:
    nid, nid_q = html.escape(str(ch["node_id"])), html.escape(str(ch["node_id"]), quote=True)
    role_h, arr, cnt = html.escape(str(ch["human_role"])), html.escape(str(ch["arrow"])), int(ch["active_count"])  # noqa: E501  # fmt: skip
    open_attr, cls_mod = (" open", " is-active") if cnt > 0 else ("", " is-idle")
    bdg_lbl = f"{cnt} active" if cnt > 0 else "0 pending"
    in_rows = "".join(
        f"<li><span class='zcg-badge'>← Inbound</span> <code>{html.escape(i['path'])}</code>: "
        f"{html.escape(i['summary'])}</li>"
        for i in ch["inbound"]
    )
    out_rows = "".join(
        f"<li><span class='zcg-badge'>→ Sent ({html.escape(o.get('mode', 'propose'))})</span> "
        f"{html.escape(o.get('summary', ''))}</li>"
        for o in ch["outbound"]
    )
    items_ul = (
        f"<ul class='zcg-channel-list'>{in_rows}{out_rows}</ul>" if (in_rows or out_rows)
        else "<p class='zcg-muted-note'>No active shared tasks on this channel yet.</p>"
    )  # fmt: skip
    mode_q, act_lbl = html.escape(str(ch["allowed_mode"]), quote=True), html.escape(str(ch["action_label"]))  # noqa: E501  # fmt: skip
    return (
        f"<details class='zcg-peer-channel{cls_mod}' data-counterpart='{nid_q}'{open_attr}>"
        f"<summary class='zcg-peer-channel__head'><span>{arr} <strong>{nid}</strong> "
        f"<small>({role_h})</small></span><span class='zcg-badge'>{bdg_lbl}</span></summary>"
        f"<div class='zcg-peer-channel__body'>{items_ul}"
        f"<form method='post' action='{pfx}/exchange' data-zcg-post='{pfx}/exchange' "
        f"data-zcg-target='{target_sel}' class='zcg-tabs'>"
        f"<input type='hidden' name='mode' value='{mode_q}'>"
        f"<input type='hidden' name='target_node' value='{nid_q}'>"
        f"<input name='directive' placeholder='Send work request to {nid_q}...' required>"
        f"<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>{act_lbl}"
        "</button></form></div></details>"
    )


def render_channels_stack_html(pfx: str, channels: Sequence[Mapping[str, Any]], tgt: str) -> str:
    """Render the counterpart-node 1-Hop shared work channel cards or standalone form."""
    if channels:
        return "".join(_render_channel_card(pfx, ch, tgt) for ch in channels)
    return (
        "<p class='zcg-muted-note'>Standalone node (0 connected 1-hop counterparts). "
        "Link a parent, child, or peer node to exchange shared work.</p>"
        f"<form method='post' action='{pfx}/exchange' data-zcg-post='{pfx}/exchange' "
        f"data-zcg-target='{tgt}' class='zcg-tabs'>"
        "<select name='mode' aria-label='Exchange mode'>"
        "<option value='propose'>Send Work Request (Parent / Peer)</option>"
        "<option value='delegate'>Delegate Downward (1-Hop Child)</option></select>"
        "<input name='target_node' placeholder='target-node-id' required>"
        "<input name='directive' placeholder='Scoped task or request text' required>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
        "Send</button></form>"
    )


def render_work_board_and_channels_html(
    prefix: str, items: Sequence[Mapping[str, str]], channels: Sequence[Mapping[str, Any]], *,
    inbox_items: Sequence[Mapping[str, str]] = (), scope_filter: str = "all",
    priority_filter: str = "all", query_filter: str = "",
    target_selector: str = "#zcg-work-ledger-panel",
) -> str:  # fmt: skip
    """Render Filter Bar, Work Inbox, 3-column Kanban, Backlog promotion, and 1-Hop channels."""
    pfx = html.escape(prefix.rstrip("/"), quote=True)
    tgt = html.escape(target_selector, quote=True)
    filtered = filter_kanban_items(
        items, scope_filter=scope_filter, priority_filter=priority_filter, query_filter=query_filter
    )
    wt_items = [t for t in filtered if t.get("tracker") == "WORKTASK.md"]
    bkl_items = [t for t in filtered if t.get("tracker") == "BACKLOG.md"]
    kanban_s = render_kanban_columns_html(pfx, wt_items, tgt)

    bkl_li: list[str] = []
    for b in itertools.islice(bkl_items, MAX_COLUMN_CARDS):
        b_body, b_st = str(b.get("body", "")), str(b.get("state", " "))
        q_b = html.escape(task_query_snippet(b_body), True)
        prom_btn = (
            f" <form method='post' action='{pfx}/tasks' data-zcg-post='{pfx}/tasks' "
            f"data-zcg-target='{tgt}' style='display:inline;'><input type='hidden' name='action' "
            f"value='promote'><input type='hidden' name='tracker' value='BACKLOG.md'>"
            f"<input type='hidden' name='task_text' value='{q_b}'><button type='submit' "
            "class='zcg-btn zcg-btn--secondary zcg-btn--sm'>Promote to To Do →</button></form>"
            if b_st == " " else ""
        )  # fmt: skip
        bkl_li.append(
            f"<li class='zcg-knowledge-row'><span><code>[{html.escape(b_st)}]</code> "
            f"{html.escape(b_body)}</span>{prom_btn}</li>"
        )
    bkl_rows = "".join(bkl_li) or "<li>0 backlog items in BACKLOG.md.</li>"
    bkl_html = (
        "<details class='zcg-peer-channel' style='margin-top:0.75rem;'>"
        "<summary class='zcg-peer-channel__head'><span><strong>Backlog</strong> "
        f"<small>(<code>BACKLOG.md</code>)</small></span><span class='zcg-badge'>"
        f"{len(bkl_items)} items</span></summary><div class='zcg-peer-channel__body'>"
        f"<ul class='zcg-knowledge-list'>{bkl_rows}</ul></div></details>"
    )
    sc_opts = "".join(f"<option value='{s}'{' selected' if s == scope_filter else ''}>{_SCOPE_LABELS[s]}</option>" for s in VALID_SCOPE_FILTERS)  # noqa: E501  # fmt: skip
    pr_opts = "<option value='all'>All Priorities</option>" + "".join(f"<option value='{p}'{' selected' if p == priority_filter.upper() else ''}>{p}</option>" for p in VALID_TASK_PRIORITIES)  # noqa: E501  # fmt: skip
    filter_bar = (
        f"<form method='get' action='{pfx}' data-zcg-get='{pfx}' data-zcg-target='{tgt}' "
        f"class='zcg-tabs' style='margin-bottom:0.55rem;'><select name='scope' "
        f"aria-label='Scope filter'>{sc_opts}</select><select name='priority' "
        f"aria-label='Priority filter'>{pr_opts}</select><input name='q' "
        f"value='{html.escape(query_filter, True)}' placeholder='Filter track or keyword...'>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>Filter</button>"
        "</form>"
    )
    quick_bar = (
        f"<form method='post' action='{pfx}/tasks' data-zcg-post='{pfx}/tasks' "
        f"data-zcg-target='{tgt}' class='zcg-tabs' style='margin-bottom:0.75rem;'>"
        "<select name='tracker' aria-label='Target tracker'><option value='WORKTASK.md'>"
        "WORKTASK.md (To Do)</option><option value='BACKLOG.md'>BACKLOG.md (Backlog)</option>"
        "</select><select name='action' aria-label='Task action'><option value='add'>+ Add Item"
        "</option><option value='commit'>Commit Tracker</option></select><input name='task_text' "
        "placeholder='New task or Conventional Commit' required>"
        "<button type='submit' class='zcg-btn zcg-btn--sm'>Apply</button></form>"
    )
    ch_html, inbox_html = render_channels_stack_html(pfx, channels, tgt), render_inbox_drawer_html(pfx, inbox_items, tgt)  # noqa: E501  # fmt: skip
    return (
        "<div class='zcg-work-studio' style='margin-top:0.55rem;'>"
        f"{inbox_html}{filter_bar}{quick_bar}{kanban_s}{bkl_html}"
        "<h4 style='margin-top:1rem;'>1-Hop Shared Work by Counterpart Node</h4>"
        f"<div class='zcg-channel-stack'>{ch_html}</div>"
        "<div id='zcg-ledger-out' style='margin-top:0.55rem;' aria-live='polite'></div></div>"
    )
