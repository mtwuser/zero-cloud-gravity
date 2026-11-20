"""Dedicated 1:1 WORK* view renderers: Dashboard (Kanban), Backlog, Roadmaps, and Validations.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import Any, Final
from urllib.parse import quote

from zcg.cockpit.ops.mesh_studio import render_corpora_scope_alert_html
from zcg.cockpit.ops.metrics_studio import render_cli_transparency_hint
from zcg.cockpit.views import work_board
from zcg.governance.work import work_inbox
from zcg.web.ui.components import render_tabs
from zcg.web.ui.templates import SafeHTML, render_icon

VALID_WORK_SECTIONS: Final[tuple[str, ...]] = (
    "dashboard", "backlog", "roadmaps", "validations", "metrics",
)  # fmt: skip
WORK_SECTION_TITLES: Final[dict[str, str]] = {
    "dashboard": "Dashboard", "backlog": "Backlog",
    "roadmaps": "Roadmaps", "validations": "Validations", "metrics": "Metrics",
}  # fmt: skip
CORE_WORKSPACE_TABS: Final[tuple[tuple[str, str, str], ...]] = (
    ("docs", "Docs & Knowledge", "/api/modules/docs-reader"),
    *((s, WORK_SECTION_TITLES[s], f"/api/modules/work-ledger?section={s}") for s in VALID_WORK_SECTIONS),  # noqa: E501
)  # fmt: skip
WORK_VIEW_SPECS: Final[dict[str, dict[str, Any]]] = {
    "dashboard": {
        "tracked_files": ("WORKTASK.md",), "id_prefix": "[TASK-NNN]",
        "add_label": "+ Add Task (To Do)", "placeholder": "[TASK-NNN] New task in WORKTASK.md...",
        "cli_commands": ('make task TASK="[TASK-001] ..."', 'make complete TASK="TASK-001"', "zcg status ."),  # noqa: E501
    },
    "backlog": {
        "tracked_files": ("BACKLOG.md",), "id_prefix": "[BKL-NNN]",
        "add_label": "+ Add Backlog Item", "placeholder": "[BKL-NNN] New backlog item...",
        "cli_commands": ("zcg inspect-horizon .", "zcg status ."),
    },
    "roadmaps": {
        "tracked_files": ("WORKROAD.md", "roadmaps/*.md"), "id_prefix": "[ROAD-NNN]",
        "add_label": "+ Add Milestone", "placeholder": "[ROAD-NNN] Strategic milestone in WORKROAD.md...",  # noqa: E501
        "cli_commands": ("zcg inspect-horizon .", "zcg compare-upstream ."),
    },
    "validations": {
        "tracked_files": ("WORKVALI.md",), "id_prefix": "[VAL-NNN]",
        "add_label": "+ Add Validation Check", "placeholder": "[VAL-NNN] QA, mastery, or sign-off check...",  # noqa: E501
        "cli_commands": ("zcg status .",),
    },
}  # fmt: skip
_EXCLUDED_SIDEBAR_CAPABILITIES: Final[frozenset[str]] = frozenset(
    {"work_ledger", "docs_reader", "spatial_atlas", "telemetry", "tool_stack", "node_mesh"}
)
_TRANSVERSAL_TITLES: Final[dict[str, str]] = {"docs": "Docs & Knowledge", "atlas": "Network Atlas"}


def normalize_work_section(raw_section: str) -> str:
    """Normalize a work view slug ('overview' -> 'dashboard', fallback -> 'dashboard')."""
    clean = raw_section.strip().lower()
    return clean if clean in VALID_WORK_SECTIONS else "dashboard"


def resolve_workspace_view_title(
    wb_modules: Sequence[Mapping[str, Any]], raw_view: str = ""
) -> str:
    """Resolve the human stage heading for a Workspace ?view= or ?tab= parameter."""
    clean_v = raw_view.strip().lower()
    eff_v = "dashboard" if clean_v in ("", "overview") else clean_v
    mod_titles = {str(m["module_id"]): str(m["title"]) for m in wb_modules}
    return (
        WORK_SECTION_TITLES.get(eff_v)
        or _TRANSVERSAL_TITLES.get(eff_v)
        or mod_titles.get(eff_v)
        or "Dashboard"
    )


def build_workspace_sidebar_tabs(
    wb_modules: Sequence[Mapping[str, Any]], swap_urls: Mapping[str, str], *,
    show_mailbox: bool, raw_view: str = "",
) -> tuple[SafeHTML, SafeHTML, str]:  # fmt: skip
    """Build (core_work_tabs, optional_capability_tabs, resolved_view_id) for Workspace (/)."""
    clean_v = raw_view.strip().lower()
    eff_v = "dashboard" if clean_v in ("", "overview") else clean_v
    cap_list = [
        (str(m["module_id"]), str(m["title"]), swap_urls[str(m["module_id"])])
        for m in wb_modules
        if str(m["module_id"]) not in _EXCLUDED_SIDEBAR_CAPABILITIES
        and (str(m["module_id"]) != "portal_inbox" or show_mailbox)
    ]
    core_html = render_tabs(tabs=CORE_WORKSPACE_TABS, active_tab=eff_v, target_selector="#zcg-capability-stage")  # noqa: E501  # fmt: skip
    cap_html = render_tabs(tabs=cap_list, active_tab=eff_v, target_selector="#zcg-capability-stage") if cap_list else SafeHTML("")  # noqa: E501  # fmt: skip
    return core_html, cap_html, eff_v


def _render_tracker_quick_form(
    pfx: str, tgt: str, *, section: str, tracker: str, extra_inputs_html: str = "",
) -> str:  # fmt: skip
    spec = WORK_VIEW_SPECS[section]
    sec_h, trk_h = html.escape(section, quote=True), html.escape(tracker, quote=True)
    lbl_h = html.escape(str(spec["add_label"]), quote=True)
    ph_h = html.escape(str(spec["placeholder"]), quote=True)
    return (
        f"<form method='post' action='{pfx}/tasks?section={sec_h}' "
        f"data-zcg-post='{pfx}/tasks?section={sec_h}' data-zcg-target='{tgt}' "
        f"class='zcg-quick-add-bar'><input type='hidden' name='tracker' value='{trk_h}'>"
        f"<input type='hidden' name='action' value='add'><input name='task_text' "
        f"placeholder='{ph_h}' aria-label='{lbl_h}' required>{extra_inputs_html}"
        f"<button type='submit' class='zcg-btn zcg-btn--sm'>{lbl_h}</button></form>"
    )


def _render_toggle_sections(
    pfx: str, tgt: str, *, section: str, tracker: str, sections: Sequence[Mapping[str, Any]],
    ws_scope: str, verify_mode: bool,
) -> list[str]:  # fmt: skip
    trk_q, blocks = html.escape(tracker, quote=True), list[str]()
    for sec in sections:
        raw_items = sec["items"]
        sec_items = (
            work_inbox.filter_kanban_items(raw_items, scope_filter=ws_scope)
            if ws_scope in ("node", "network") else raw_items
        )  # fmt: skip
        if not sec_items:
            continue
        rows: list[str] = []
        for it in sec_items:
            st, body = str(it["state"]), str(it["body"])
            is_x = st == "x"
            lead = (
                f"<code>[{'x' if is_x else ' '}]</code>"
                if verify_mode
                else f"<span class='zcg-chip'>{'Done' if is_x else ('Active' if st == '/' else 'Planned')}</span>"  # noqa: E501
            )
            btn_c = (
                "zcg-btn zcg-btn--secondary zcg-btn--sm"
                if (is_x or not verify_mode) else "zcg-btn zcg-btn--sm"
            )  # fmt: skip
            btn_l = "Reopen" if is_x else ("Verify ✓" if verify_mode else "Mark Done ✓")
            q_b = html.escape(work_board.task_query_snippet(body), True)
            rows.append(
                f"<li class='zcg-knowledge-row'><span>{lead} {html.escape(body)}</span>"
                f"<form method='post' action='{pfx}/tasks?section={section}' "
                f"data-zcg-post='{pfx}/tasks?section={section}' data-zcg-target='{tgt}'>"
                f"<input type='hidden' name='action' value='toggle'>"
                f"<input type='hidden' name='tracker' value='{trk_q}'>"
                f"<input type='hidden' name='target_state' value='{' ' if is_x else 'x'}'>"
                f"<input type='hidden' name='task_text' value='{q_b}'>"
                f"<button type='submit' class='{btn_c}'>{btn_l}</button></form></li>"
            )
        h_txt = html.escape(str(sec["heading"]))
        blocks.append(f"<h4>{h_txt}</h4><ul class='zcg-knowledge-list'>{''.join(rows)}</ul>")
    return blocks


def _render_filter_bar(
    pfx: str, tgt: str, *, section: str, priority_filter: str, query_filter: str,
    has_filter: bool, placeholder: str,
) -> str:  # fmt: skip
    up = priority_filter.upper()
    p_opts = "".join(f"<option value='{p}'{' selected' if p == up else ''}>{p}</option>" for p in work_inbox.VALID_TASK_PRIORITIES)  # noqa: E501  # fmt: skip
    rst = (
        f"<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        f"data-zcg-get='{pfx}?section={section}' data-zcg-target='{tgt}'>Reset</button>"
        if has_filter else ""
    )  # fmt: skip
    return (
        f"<form method='get' action='{pfx}' data-zcg-get='{pfx}' data-zcg-target='{tgt}' "
        f"class='zcg-filter-bar'><input type='hidden' name='section' value='{section}'>"
        "<select name='priority' aria-label='Priority filter'><option value='all'>"
        f"All Priorities</option>{p_opts}</select><input name='q' "
        f"value='{html.escape(query_filter, True)}' placeholder='{html.escape(placeholder, True)}'>"
        f"<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>Filter</button>"
        f"{rst}</form>"
    )


def _render_work_section_shell(
    pfx: str, tgt: str, section: str, *, tracker: str, body_html: str, notice_html: str,
    tracker_dirty: bool, ws_scope: str, badge_html: str = "", extra_cli: Sequence[str] = (),
) -> str:  # fmt: skip
    spec, sec_h, trk_h = (
        WORK_VIEW_SPECS[section], html.escape(section, quote=True), html.escape(tracker, quote=True)
    )  # fmt: skip
    dirty_bar = (
        f"<div class='zcg-dirty-banner' role='status'><span>🟡 <code>{trk_h}</code> saved on "
        f"disk (uncommitted in Git)</span><form method='post' action='{pfx}/tasks?section={sec_h}' "
        f"data-zcg-post='{pfx}/tasks?section={sec_h}' data-zcg-target='{tgt}' class='zcg-tabs'>"
        f"<input type='hidden' name='tracker' value='{trk_h}'><input type='hidden' name='action' "
        f"value='commit'><input name='task_text' value='chore(work): update {trk_h}' "
        "aria-label='Conventional commit message' required><button type='submit' "
        "class='zcg-btn zcg-btn--secondary zcg-btn--sm'>Commit Now</button></form></div>"
        if tracker_dirty else ""
    )  # fmt: skip
    cli_h = render_cli_transparency_hint(spec["tracked_files"], (*spec["cli_commands"], *extra_cli))
    hdr = (
        f"<div class='zcg-card__header'><span class='zcg-muted-note'>"
        f"<code>{html.escape(tracker)}</code> · <code>{spec['id_prefix']}</code></span>"
        f"{badge_html}</div>"
    )
    return (
        f"<div id='zcg-work-ledger-panel' data-work-section='{section}'>{notice_html}{dirty_bar}"
        f"{render_corpora_scope_alert_html(ws_scope)}<section class='zcg-card'>"
        f"{hdr}{body_html}{cli_h}</section></div>"
    )


def _render_gate_pill(env_key: str, gate: Any) -> str:
    g_map = gate if isinstance(gate, Mapping) else {}
    allowed = bool(g_map.get("allowed"))
    tip = "" if allowed else "; ".join(str(x) for x in (g_map.get("failed_gates") or ()))
    t_attr = f" title='{html.escape(tip, quote=True)}'" if tip else ""
    return f"<span class='zcg-badge'{t_attr}>Gate [{html.escape(env_key.upper())}]: <strong>{'READY' if allowed else 'BLOCKED'}</strong></span>"  # noqa: E501


def render_dashboard_kanban_html(
    prefix: str, items: Sequence[Mapping[str, str]], channels: Sequence[Mapping[str, Any]], *,
    inbox_items: Sequence[Mapping[str, str]] = (), jobs_drawer_html: str = "",
    notice_html: str = "", scope_filter: str = "all", priority_filter: str = "all",
    query_filter: str = "", tracker_dirty: bool = False, target_select_html: str = "",
    ws_scope: str = "all", target_selector: str = "#zcg-work-ledger-panel",
) -> str:  # fmt: skip
    """Render the direct Dashboard view: Filters + Quick-Add + Work Inbox + WORKTASK Kanban."""
    pfx, tgt = html.escape(prefix.rstrip("/"), quote=True), html.escape(target_selector, quote=True)
    all_wt = [t for t in items if t.get("tracker") == "WORKTASK.md"]
    eff_sc = scope_filter if scope_filter != "all" else (ws_scope if ws_scope in ("node", "network") else "all")  # noqa: E501  # fmt: skip
    filtered = work_inbox.filter_kanban_items(
        all_wt, scope_filter=eff_sc, priority_filter=priority_filter, query_filter=query_filter,
    )  # fmt: skip
    has_f = scope_filter != "all" or priority_filter != "all" or bool(query_filter.strip())
    filter_bar = _render_filter_bar(
        pfx, tgt, section="dashboard", priority_filter=priority_filter,
        query_filter=query_filter, has_filter=has_f, placeholder="Filter track or keyword...",
    )  # fmt: skip
    quick_bar = _render_tracker_quick_form(
        pfx, tgt, section="dashboard", tracker="WORKTASK.md", extra_inputs_html=target_select_html,
    )  # fmt: skip
    inbox_html = work_board.render_inbox_drawer_html(pfx, inbox_items, tgt)
    kanban_html = work_board.render_kanban_columns_html(pfx, filtered, tgt)
    ch_html, ch_open = (
        work_board.render_channels_stack_html(pfx, channels, tgt),
        " open" if ws_scope == "network" else "",
    )
    ch_drawer = (
        f"<details class='zcg-peer-channel'{ch_open} style='margin-top:0.85rem;'>"
        "<summary class='zcg-peer-channel__head'><span><strong>1-Hop Shared Work Channels</strong>"
        f"</span><span class='zcg-badge'>{len(channels)} counterparts</span></summary>"
        f"<div class='zcg-peer-channel__body'><div class='zcg-channel-stack'>{ch_html}</div>"
        "</div></details>"
    )
    body = f"{filter_bar}{quick_bar}{inbox_html}{kanban_html}{ch_drawer}{jobs_drawer_html}"
    return _render_work_section_shell(
        pfx, tgt, "dashboard", tracker="WORKTASK.md", body_html=body,
        notice_html=notice_html, tracker_dirty=tracker_dirty, ws_scope=ws_scope,
    )  # fmt: skip


def render_backlog_view_html(
    prefix: str, items: Sequence[Mapping[str, str]], *, notice_html: str = "",
    priority_filter: str = "all", query_filter: str = "", tracker_dirty: bool = False,
    ws_scope: str = "all", target_selector: str = "#zcg-work-ledger-panel",
) -> str:  # fmt: skip
    """Render the dedicated Backlog view over BACKLOG.md with 1-click Promote to To Do."""
    pfx, tgt = html.escape(prefix.rstrip("/"), quote=True), html.escape(target_selector, quote=True)
    raw_bkl = [t for t in items if t.get("tracker") == "BACKLOG.md"]
    eff_sc = ws_scope if ws_scope in ("node", "network") else "all"
    filtered = work_inbox.filter_kanban_items(
        raw_bkl, scope_filter=eff_sc, priority_filter=priority_filter, query_filter=query_filter
    )
    open_n = sum(1 for x in raw_bkl if x.get("state") == " ")
    has_f = priority_filter != "all" or bool(query_filter.strip())
    filter_bar = _render_filter_bar(
        pfx, tgt, section="backlog", priority_filter=priority_filter, query_filter=query_filter,
        has_filter=has_f, placeholder="Filter [BKL-NNN], track, or keyword...",
    )  # fmt: skip
    quick_bar = _render_tracker_quick_form(pfx, tgt, section="backlog", tracker="BACKLOG.md")
    rows: list[str] = []
    for item in filtered:
        body, st = str(item.get("body") or ""), str(item.get("state") or " ")
        prio, trk = html.escape(str(item.get("priority") or "P2")), str(item.get("track") or "main")
        trk_s = f" <span class='zcg-chip'>{html.escape(trk)}</span>" if trk != "main" else ""
        q_b = html.escape(work_board.task_query_snippet(body), quote=True)
        prom = (
            f"<form method='post' action='{pfx}/tasks?section=backlog' "
            f"data-zcg-post='{pfx}/tasks?section=backlog' data-zcg-target='{tgt}'>"
            "<input type='hidden' name='action' value='promote'>"
            "<input type='hidden' name='tracker' value='BACKLOG.md'>"
            f"<input type='hidden' name='task_text' value='{q_b}'>"
            "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
            "Promote to To Do →</button></form>"
            if st == " " else "<span class='zcg-chip zcg-chip--active'>Completed</span>"
        )  # fmt: skip
        rows.append(
            f"<li class='zcg-knowledge-row'><span><span class='zcg-badge'>{prio}</span>{trk_s} "
            f"{html.escape(body)}</span>{prom}</li>"
        )
    list_h = (
        f"<ul class='zcg-knowledge-list'>{''.join(rows)}</ul>"
        if rows else "<p class='zcg-muted-note'>0 matching backlog items in BACKLOG.md.</p>"
    )  # fmt: skip
    badge = f"<span class='zcg-badge'>{open_n} open · {len(raw_bkl)} total</span>"
    return _render_work_section_shell(
        pfx, tgt, "backlog", tracker="BACKLOG.md", badge_html=badge,
        body_html=f"{filter_bar}{quick_bar}{list_h}",
        notice_html=notice_html, tracker_dirty=tracker_dirty, ws_scope=ws_scope,
    )  # fmt: skip


def render_roadmaps_view_html(
    prefix: str, roadmap_data: Mapping[str, Any], *, notice_html: str = "",
    tracker_dirty: bool = False, ws_scope: str = "all",
    target_selector: str = "#zcg-work-ledger-panel",
) -> str:  # fmt: skip
    """Render the dedicated Roadmaps view over WORKROAD.md and roadmaps/*.md."""
    pfx, tgt = html.escape(prefix.rstrip("/"), quote=True), html.escape(target_selector, quote=True)
    trk = str(roadmap_data.get("tracker_file") or "WORKROAD.md")
    quick_bar = _render_tracker_quick_form(pfx, tgt, section="roadmaps", tracker=trk)
    sec_blocks = _render_toggle_sections(
        pfx, tgt, section="roadmaps", tracker=trk, sections=roadmap_data.get("sections") or (),
        ws_scope=ws_scope, verify_mode=False,
    )  # fmt: skip
    docs_li = "".join(
        f"<li class='zcg-knowledge-row'><span>{render_icon('book')} "
        f"<strong>{html.escape(str(d['title']))}</strong> <code>{html.escape(str(d['rel_path']))}</code>"  # noqa: E501
        f"</span><button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        f"data-zcg-get='/api/modules/docs-reader?origin=node&amp;doc={quote(str(d['rel_path']))}' "
        "data-zcg-target='#zcg-capability-stage'>Read Roadmap →</button></li>"
        for d in (roadmap_data.get("roadmap_docs") or ())
    )
    docs_blk = f"<h4>Architecture &amp; Horizon Documents (<code>roadmaps/*.md</code>)</h4><ul class='zcg-knowledge-list'>{docs_li}</ul>" if docs_li else ""  # noqa: E501  # fmt: skip
    body_h = "".join(sec_blocks) or (
        "<p class='zcg-muted-note'>No milestone checkboxes recorded in "
        f"<code>{html.escape(trk)}</code> yet. Add your first milestone above.</p>"
    )
    badge = (
        f"<span class='zcg-badge'>Open: {roadmap_data.get('open_count', 0)} · "
        f"Active: {roadmap_data.get('in_progress_count', 0)} · "
        f"Done: {roadmap_data.get('done_count', 0)}</span>"
    )
    return _render_work_section_shell(
        pfx, tgt, "roadmaps", tracker=trk, badge_html=badge,
        body_html=f"{quick_bar}{body_h}{docs_blk}",
        notice_html=notice_html, tracker_dirty=tracker_dirty, ws_scope=ws_scope,
    )  # fmt: skip


def render_validations_view_html(
    prefix: str, vali_data: Mapping[str, Any], *,
    environment_gates: Mapping[str, Any] | None = None,
    show_promotion_gates: bool | None = None, notice_html: str = "",
    tracker_dirty: bool = False, ws_scope: str = "all",
    target_selector: str = "#zcg-work-ledger-panel",
) -> str:  # fmt: skip
    """Render the dedicated Validations view over WORKVALI.md and environment promotion gates."""
    pfx, tgt = html.escape(prefix.rstrip("/"), quote=True), html.escape(target_selector, quote=True)
    quick_bar = _render_tracker_quick_form(pfx, tgt, section="validations", tracker="WORKVALI.md")
    show_gates = bool(environment_gates) if show_promotion_gates is None else show_promotion_gates
    gate_pills = (
        "".join(_render_gate_pill(str(k), v) for k, v in (environment_gates or {}).items())
        if show_gates else ""
    )  # fmt: skip
    gate_row = f"<div class='zcg-tabs' style='margin-bottom:0.65rem;'>{gate_pills}</div>" if gate_pills else ""  # noqa: E501  # fmt: skip
    sec_blocks = _render_toggle_sections(
        pfx, tgt, section="validations", tracker="WORKVALI.md",
        sections=vali_data.get("sections") or (), ws_scope=ws_scope, verify_mode=True,
    )  # fmt: skip
    body_h = "".join(sec_blocks) or (
        "<p class='zcg-muted-note'>No validation items in <code>WORKVALI.md</code> yet. "
        "Add manual QA, mastery, or promotion checks above.</p>"
    )
    ver_n, tot_n, pct = (
        int(vali_data.get("verified_count", 0)), int(vali_data.get("total_count", 0)),
        int(vali_data.get("completion_pct", 0)),
    )  # fmt: skip
    badge = f"<span class='zcg-badge'>Verified: {ver_n}/{tot_n} ({pct}%)</span>"
    return _render_work_section_shell(
        pfx, tgt, "validations", tracker="WORKVALI.md", badge_html=badge,
        body_html=f"{gate_row}{quick_bar}{body_h}", notice_html=notice_html,
        tracker_dirty=tracker_dirty, ws_scope=ws_scope,
        extra_cli=("make env-gate ENV=pro",) if show_gates else (),
    )  # fmt: skip
