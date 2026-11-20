"""Sovereign Workspace Metrics Studio and collapsible CLI & Tracked Files transparency renderer.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import Any, Final

_KIB: Final[int] = 1024
_MIB: Final[int] = 1024 * 1024
_DIRTY_PENALTY_PER_ITEM: Final[int] = 10
_MAX_PCT: Final[int] = 100


def _clamp_pct(value: int) -> int:
    return max(0, min(_MAX_PCT, value))


def _submap(mapping: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    raw = mapping.get(key)
    return raw if isinstance(raw, Mapping) else {}


def _format_bytes(size_bytes: int) -> str:
    if size_bytes >= _MIB:
        return f"{size_bytes / _MIB:.1f} MB"
    if size_bytes >= _KIB:
        return f"{size_bytes / _KIB:.1f} KB"
    return f"{max(0, size_bytes)} B"


def _render_progress_bar(pct: int, *, label: str) -> str:
    safe_pct = _clamp_pct(pct)
    lbl = html.escape(label, quote=True)
    return (
        f"<div class='zcg-progress' role='progressbar' aria-label='{lbl}' "
        f"aria-valuenow='{safe_pct}' aria-valuemin='0' aria-valuemax='100'>"
        f"<div class='zcg-progress__fill' style='width:{safe_pct}%;'></div></div>"
    )


def render_cli_transparency_hint(
    tracked_files: Sequence[str],
    commands: Sequence[str],
    *,
    summary_label: str = "⌨ CLI & Tracked Files",
) -> str:
    """Render a collapsed-by-default CLI & Tracked Files transparency disclosure panel."""
    clean_files = [item.strip() for item in tracked_files if item.strip()]
    clean_cmds = [cmd.strip() for cmd in commands if cmd.strip()]
    if not clean_files and not clean_cmds:
        return ""
    parts: list[str] = []
    if clean_files:
        files_h = " ".join(f"<code>{html.escape(fp)}</code>" for fp in clean_files)
        parts.append(
            f"<p class='zcg-muted-note' style='margin:0 0 0.35rem 0;'>Tracked files: {files_h}</p>"
        )
    if clean_cmds:
        cmd_chips = " ".join(
            f"<span class='zcg-chip'><code>{html.escape(cmd)}</code> "
            "<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
            f"data-zcg-copy='{html.escape(cmd, quote=True)}'>Copy</button></span>"
            for cmd in clean_cmds
        )
        parts.append(
            "<div class='zcg-tabs' style='gap:0.4rem;align-items:center;'>"
            f"<span>Manual CLI:</span> {cmd_chips}</div>"
        )
    return (
        "<details class='zcg-cli-hint' style='margin-top:0.85rem;' data-zcg-cli-hint>"
        "<summary class='zcg-muted-note' style='cursor:pointer;'>"
        f"<strong>{html.escape(summary_label)}</strong></summary>"
        f"<div style='margin-top:0.45rem;'>{''.join(parts)}</div></details>"
    )


def _render_nodes_table(nodes: Sequence[Mapping[str, Any]], *, scope: str) -> str:
    if not nodes:
        label = "connected corpora" if scope == "corpora" else "nodes"
        return (
            f"<section class='zcg-card' style='margin-top:0.75rem;'>"
            f"<p class='zcg-muted-note'>0 {label} discovered in this scope.</p></section>"
        )
    rows: list[str] = []
    for node in nodes:
        w = _submap(node, "work")
        k = _submap(node, "knowledge")
        v = _submap(node, "vault")
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(str(node.get('node_id') or ''))}</code></td>"
            f"<td>{html.escape(str(node.get('layer_role') or 'project'))}</td>"
            f"<td>{int(w.get('completion_pct', 0))}%</td>"
            f"<td>{int(w.get('backlog_open_count', 0))}</td>"
            f"<td>{int(k.get('total_docs', 0))}</td>"
            f"<td>{int(v.get('vault_files', 0))}</td>"
            "</tr>"
        )
    return (
        "<section class='zcg-card' style='margin-top:0.75rem;'>"
        "<h3>Scope Node Breakdown</h3>"
        "<table class='zcg-table'><thead><tr>"
        "<th>Node</th><th>Role</th><th>Work Done %</th>"
        "<th>Backlog</th><th>Docs</th><th>Vault Files</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></section>"
    )


def render_metrics_view_html(
    report: Mapping[str, Any],
    *,
    posture_score: int = 100,
    skill_trust_score: int = 100,
    health_state: str = "OPTIMAL",
    prefix: str = "/api/modules/work-ledger",
    target_selector: str = "#zcg-work-ledger-panel",
    layer_role: str = "department",
) -> str:
    """Render the dedicated Workspace Metrics view across node, network, and corpora scopes."""
    scope = str(report.get("scope") or "node").strip().lower()
    work = _submap(report, "work")
    know = _submap(report, "knowledge")
    vault = _submap(report, "vault")
    git_sync = _submap(report, "git_sync")
    raw_nodes = report.get("nodes")
    nodes: Sequence[Mapping[str, Any]] = raw_nodes if isinstance(raw_nodes, list | tuple) else ()

    comp_pct = _clamp_pct(int(work.get("completion_pct", 0)))
    work_card = (
        "<section class='zcg-card'>"
        "<div class='zcg-card__header'><h3>Work &amp; Delivery Velocity</h3>"
        f"<span class='zcg-badge'>{comp_pct}% Done</span></div>"
        f"{_render_progress_bar(comp_pct, label='Work completion percentage')}"
        "<div class='zcg-tabs' style='margin-top:0.55rem;'>"
        f"<span class='zcg-badge'>Done: <strong>{int(work.get('done_count', 0))}</strong></span>"
        f"<span class='zcg-badge'>In Progress: <strong>{int(work.get('in_progress_count', 0))}</strong></span>"  # noqa: E501
        f"<span class='zcg-badge'>To Do: <strong>{int(work.get('todo_count', 0))}</strong></span>"
        f"<span class='zcg-badge'>Backlog: <strong>{int(work.get('backlog_open_count', 0))}</strong></span>"  # noqa: E501
        f"<span class='zcg-badge'>Roadmaps: <strong>{int(work.get('roadmap_done_count', 0))}/{int(work.get('roadmap_total_count', 0))}</strong></span>"  # noqa: E501
        f"<span class='zcg-badge'>Validations: <strong>{int(work.get('validation_verified_count', 0))}/{int(work.get('validation_total_count', 0))}</strong></span>"  # noqa: E501
        f"<span class='zcg-badge'>1-Hop Inbox: <strong>{int(work.get('inbox_pending_count', 0))}</strong></span>"  # noqa: E501
        "</div></section>"
    )

    tot_docs = int(know.get("total_docs", 0))
    r3_n, r2_n, r0_n = (
        int(know.get("r3_count", 0)),
        int(know.get("r2_count", 0)),
        int(know.get("r0_count", 0)),
    )
    shared_pct = round((_MAX_PCT * (r2_n + r0_n)) / tot_docs) if tot_docs > 0 else 0
    know_card = (
        "<section class='zcg-card'>"
        "<div class='zcg-card__header'><h3>Knowledge &amp; Visibility Footprint</h3>"
        f"<span class='zcg-badge'>{tot_docs} docs</span></div>"
        f"{_render_progress_bar(shared_pct, label='Shared and public docs ratio')}"
        "<div class='zcg-tabs' style='margin-top:0.55rem;'>"
        f"<span class='zcg-badge'>🔒 Internal (R3): <strong>{r3_n}</strong></span>"
        f"<span class='zcg-badge'>🏛️ 1-Hop Network (R2): <strong>{r2_n}</strong></span>"
        f"<span class='zcg-badge'>🌐 Public (R0): <strong>{r0_n}</strong></span>"
        "</div></section>"
    )

    v_files, v_bytes = int(vault.get("vault_files", 0)), int(vault.get("vault_bytes", 0))
    dirty = int(git_sync.get("git_dirty_count", 0))
    ahead = int(git_sync.get("git_ahead", 0))
    behind = int(git_sync.get("git_behind", 0))
    sync_pct = _clamp_pct(_MAX_PCT - ((dirty + ahead + behind) * _DIRTY_PENALTY_PER_ITEM))
    vault_card = (
        "<section class='zcg-card'>"
        "<div class='zcg-card__header'><h3>Vault &amp; Git Sync Hygiene</h3>"
        f"<span class='zcg-badge'>{sync_pct}% Clean</span></div>"
        f"{_render_progress_bar(sync_pct, label='Git sync hygiene score')}"
        "<div class='zcg-tabs' style='margin-top:0.55rem;'>"
        f"<span class='zcg-badge'>Attachment Vault: <strong>{v_files} files ({_format_bytes(v_bytes)})</strong></span>"  # noqa: E501
        f"<span class='zcg-badge'>Git Dirty: <strong>{dirty}</strong></span>"
        f"<span class='zcg-badge'>Ahead: <strong>{ahead}</strong></span>"
        f"<span class='zcg-badge'>Behind: <strong>{behind}</strong></span>"
        "</div>"
        "<p class='zcg-muted-note' style='margin-top:0.4rem;'>"
        "Vault blobs stay outside Git under <code>.agents/telemetry/vault_blobs/</code>.</p>"
        "</section>"
    )

    safe_posture = _clamp_pct(posture_score)
    safe_skill = _clamp_pct(skill_trust_score)
    posture_card = (
        "<section class='zcg-card'>"
        "<div class='zcg-card__header'><h3>Governance &amp; Posture Snapshot</h3>"
        f"<span class='zcg-badge'>{html.escape(health_state)}</span></div>"
        f"{_render_progress_bar(safe_posture, label='Security posture score')}"
        "<div class='zcg-tabs' style='margin-top:0.55rem;'>"
        f"<span class='zcg-badge'>Security Posture: <strong>{safe_posture}/100</strong></span>"
        f"<span class='zcg-badge'>Skill Trust: <strong>{safe_skill}/100</strong></span>"
        f"<span class='zcg-badge'>Node Health: <strong>{html.escape(health_state)}</strong></span>"
        "</div></section>"
    )

    table_html = (
        _render_nodes_table(nodes, scope=scope) if (len(nodes) > 1 or scope != "node") else ""
    )
    cli_cmds = (
        "zcg status .",
        "make diff",
        *(("make workstation-audit",) if layer_role == "workstation" else ()),
    )
    cli_hint = render_cli_transparency_hint(
        ("WORKTASK.md", "BACKLOG.md", "WORKROAD.md", "WORKVALI.md", "docs/**"),
        cli_cmds,
    )
    return (
        "<div id='zcg-work-ledger-panel' data-work-section='metrics' data-zcg-metrics-view>"
        "<div class='zcg-grid' style='display:grid;gap:0.75rem;"
        "grid-template-columns:repeat(auto-fit,minmax(280px,1fr));'>"
        f"{work_card}{know_card}{vault_card}{posture_card}</div>"
        f"{table_html}{cli_hint}</div>"
    )
