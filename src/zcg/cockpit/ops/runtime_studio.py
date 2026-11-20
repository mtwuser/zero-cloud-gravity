"""Pure-HTML Runtime & Updates Studio renderer for Antigravity and 1-Hop Node Updates.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

_COMPONENT_KEYS: Final[tuple[str, ...]] = ("agents", "cli", "ide")
_AGY_COPY_BUTTONS: Final[tuple[tuple[str, str], ...]] = (
    ("workspace_path", "Copy Folder Path (Agents App)"),
    ("open_workspace", "Copy Terminal CLI: cd & agy"),
    ("update_agents", "Copy CLI: Update Agents + CLI"),
    ("update_cli", "Copy CLI: Update CLI"),
    ("update_all", "Copy CLI: Install / Update All"),
)


def _render_online_badge(online_comp: Mapping[str, Any]) -> str:
    status = str(online_comp.get("status") or "unreachable")
    inst_h = html.escape(str(online_comp.get("installed_version") or ""))
    lat_raw = online_comp.get("latest_version") or online_comp.get("installed_version") or ""
    lat_h = html.escape(str(lat_raw))
    if status == "up-to-date":
        return f"<span class='zcg-badge'>🟢 Up to date (v{lat_h})</span>"
    if status == "update-available":
        return f"<span class='zcg-badge'>🟠 Update available: v{inst_h} → v{lat_h}</span>"
    if status == "not-installed":
        return f"<span class='zcg-badge'>⚪ Not installed (latest v{lat_h})</span>"
    return "<span class='zcg-badge'>⚠️ Release server unreachable</span>"


def _render_component_row(
    key: str, comp: Mapping[str, Any], online_comp: Mapping[str, Any] | None
) -> str:
    label = html.escape(str(comp.get("label") or key))
    path_h = html.escape(str(comp.get("path") or ""))
    installed = bool(comp.get("installed"))
    ver = str(comp.get("version") or "").strip()
    ver_html = f"🟢 v{html.escape(ver)}" if installed and ver else "⚪ Not installed"
    live_cell = f"<td>{_render_online_badge(online_comp)}</td>" if online_comp is not None else ""
    return (
        f"<tr data-runtime-component='{html.escape(key, quote=True)}'>"
        f"<td><strong>{label}</strong></td><td>{ver_html}</td>"
        f"<td><code>{path_h}</code></td>{live_cell}</tr>"
    )


def _render_local_agy_card(
    local_agy: Mapping[str, Any], online_check: Mapping[str, Any] | None
) -> str:
    comps = local_agy.get("components") or {}
    proj = local_agy.get("workspace_projection") or {}
    cmds = local_agy.get("commands") or {}
    stow_badge = (
        "✓ $HOME Stow Coupled"
        if local_agy.get("home_stow_coupled")
        else "Standalone ($HOME Uncoupled)"
    )
    show_live = bool(online_check and online_check.get("checked") is True)
    online_comps = (online_check.get("components") or {}) if show_live and online_check else {}
    rows = "".join(
        _render_component_row(
            key, comps.get(key) or {}, online_comps.get(key, {}) if show_live else None
        )
        for key in _COMPONENT_KEYS
    )
    live_hdr = "<th>Live Release</th>" if show_live else ""
    rules_n = int(proj.get("rules_count", 0))
    skills_n = int(proj.get("skills_count", 0))
    pin_lbl = "Active" if proj.get("has_session_pin") else "None"
    sidecar_lbl = "Active" if proj.get("has_sidecar") else "None"
    if local_agy.get("online_checks_allowed", True):
        check_ctrl = (
            "<button type='button' class='zcg-btn zcg-btn--sm' "
            "data-zcg-get='/api/modules/runtime/check-updates' "
            "data-zcg-target='#zcg-runtime-panel'>Check Online Releases</button>"
        )
    else:
        check_ctrl = "<span class='zcg-badge'>🔒 Offline Airlock (online checks disabled)</span>"
    copy_btns = "".join(
        "<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        f"data-zcg-copy='{html.escape(str(cmds[key]), quote=True)}'>{lbl}</button>"
        for key, lbl in _AGY_COPY_BUTTONS
        if cmds.get(key)
    )
    return (
        "<div class='zcg-card' data-runtime-card='antigravity'>"
        "<div class='zcg-card__header'><h3>Local Antigravity Environment</h3>"
        f"<span class='zcg-badge'>{html.escape(stow_badge)}</span></div>"
        "<table class='zcg-table' aria-label='Local Antigravity runtime components'>"
        f"<thead><tr><th>Component</th><th>Installed Version</th><th>Path</th>{live_hdr}</tr>"
        f"</thead><tbody>{rows}</tbody></table>"
        "<div class='zcg-tabs' style='margin:0.65rem 0;'>"
        f"<span class='zcg-chip'>Rules: {rules_n}</span>"
        f"<span class='zcg-chip'>Skills: {skills_n}</span>"
        f"<span class='zcg-chip'>Session Pin: {pin_lbl}</span>"
        f"<span class='zcg-chip'>Sidecar: {sidecar_lbl}</span></div>"
        f"<div class='zcg-tabs'>{check_ctrl}{copy_btns}</div></div>"
    )


def _render_node_update_card(update_plan: Mapping[str, Any]) -> str:
    node_ver = str(update_plan.get("node_engine_version") or "").strip() or "unstamped"
    oss_ver = str(update_plan.get("oss_engine_version") or "0.0.0")
    target_ver = str(update_plan.get("target_version") or oss_ver)
    src_kind = str(update_plan.get("update_source_kind") or "oss-engine")
    src_id = str(update_plan.get("update_source_id") or "zero-cloud-gravity")
    src_label = (
        "Open-Source ZeroCloudGravity"
        if src_kind == "oss-engine"
        else f"1-Hop Governing Parent: {src_id}"
    )
    update_avail = bool(update_plan.get("update_available"))
    status_badge = (
        f"🟠 Update / Sync Available -> v{html.escape(target_ver)}"
        if update_avail
        else "🟢 Up to date"
    )
    parent_banner = ""
    if update_plan.get("parent_update_required_first"):
        p_url = str(update_plan.get("parent_admin_url") or "")
        link_h = (
            " <a class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
            f"href='{html.escape(p_url, quote=True)}'>Open Parent Runtime &amp; Updates →</a>"
            if p_url
            else ""
        )
        parent_banner = (
            "<div class='zcg-dirty-banner' role='alert' style='margin:0.65rem 0;'>"
            f"⚠️ 1-Hop Upgrade Law: Governing parent '{html.escape(src_id)}' is behind "
            f"Open-Source ZeroCloudGravity (v{html.escape(oss_ver)}). Update your parent node "
            f"first before syncing this subordinate node.{link_h}</div>"
        )
    cmds = update_plan.get("commands") or {}
    cli_btns: list[str] = []
    if cmds.get("pull_oss"):
        cli_btns.append(
            "<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
            f"data-zcg-copy='{html.escape(str(cmds['pull_oss']), quote=True)}'>"
            "Copy Pull OSS CLI</button>"
        )
    if cmds.get("sync_node"):
        cli_btns.append(
            "<button type='button' class='zcg-btn zcg-btn--sm' "
            f"data-zcg-copy='{html.escape(str(cmds['sync_node']), quote=True)}'>"
            "Copy Sync CLI</button>"
        )
    pending = update_plan.get("pending_releases") or ()
    notes_html = "".join(
        f"<div style='margin:0.5rem 0;'><strong>v{html.escape(str(rel.get('version') or ''))} "
        f"— {html.escape(str(rel.get('title') or ''))}</strong><ul>"
        + "".join(f"<li>{html.escape(str(h))}</li>" for h in (rel.get("highlights") or ()))
        + "</ul></div>"
        for rel in pending
    )
    prompt_raw = str(update_plan.get("reconciliation_prompt") or "")
    prompt_block = ""
    if prompt_raw:
        prompt_h = html.escape(prompt_raw)
        prompt_q = html.escape(prompt_raw, quote=True)
        inner = (
            f"<textarea class='zcg-md-editor' rows='8' readonly "
            f"aria-label='Guided AI Reconciliation Prompt'>{prompt_h}</textarea>"
            "<div class='zcg-tabs' style='margin-top:0.5rem;'>"
            f"<button type='button' class='zcg-btn zcg-btn--sm' data-zcg-copy='{prompt_q}'>"
            "Copy Guided Reconciliation Prompt</button></div>"
        )
        if update_avail:
            prompt_block = (
                f"<div style='margin-top:0.75rem;'><h4>Guided AI Reconciliation Prompt</h4>"
                f"{inner}</div>"
            )
        else:
            prompt_block = (
                "<details style='margin-top:0.75rem;'>"
                "<summary><strong>Guided AI Reconciliation Prompt (Optional)</strong></summary>"
                f"<div style='margin-top:0.5rem;'>{inner}</div></details>"
            )
    return (
        "<div class='zcg-card' data-runtime-card='node-updates'>"
        "<div class='zcg-card__header'>"
        "<h3>ZeroCloudGravity 1-Hop Node Update &amp; Reconciliation</h3>"
        f"<span class='zcg-badge'>{status_badge}</span></div>"
        "<div class='zcg-tabs' style='margin-bottom:0.5rem;'>"
        f"<span class='zcg-chip'>Node Engine: <code>{html.escape(node_ver)}</code></span>"
        f"<span class='zcg-chip'>Source: <strong>{html.escape(src_label)}</strong></span>"
        f"<span class='zcg-chip'>OSS Engine: <code>v{html.escape(oss_ver)}</code></span></div>"
        f"{parent_banner}"
        f"<div class='zcg-tabs' style='margin-top:0.5rem;'>{''.join(cli_btns)}</div>"
        f"{notes_html}{prompt_block}</div>"
    )


def _render_agent_guidance_card(agent_guidance: Mapping[str, Any] | None) -> str:
    if not agent_guidance:
        return ""
    prof = html.escape(str(agent_guidance.get("profile_label") or ""))
    base_m = html.escape(str(agent_guidance.get("recommended_base_model") or ""))
    summary = html.escape(str(agent_guidance.get("auto_orchestration_summary") or ""))
    return (
        "<div class='zcg-card' data-runtime-card='agent-policy'>"
        "<div class='zcg-card__header'>"
        "<h3>Set-and-Forget Agent &amp; Automatic Swarm Policy</h3>"
        f"<span class='zcg-badge'>{prof}</span></div>"
        f"<p><strong>Recommended Base Model:</strong> <code>{base_m}</code></p>"
        f"<p class='zcg-muted-note'>{summary}</p></div>"
    )


def render_runtime_and_updates_html(
    local_agy: Mapping[str, Any],
    update_plan: Mapping[str, Any],
    *,
    online_check: Mapping[str, Any] | None = None,
    agent_guidance: Mapping[str, Any] | None = None,
) -> str:
    """Render the unified Runtime & Updates Studio panel HTML fragment (0 inline scripts)."""
    card_agy = _render_local_agy_card(local_agy, online_check)
    card_upd = _render_node_update_card(update_plan)
    card_pol = _render_agent_guidance_card(agent_guidance)
    return (
        "<div id='zcg-runtime-panel'><section data-zcg-runtime>"
        f"{card_agy}{card_upd}{card_pol}</section></div>"
    )
