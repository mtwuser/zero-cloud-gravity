"""HTML presenter for the 3-Origin Node Skills Studio and isolated Tool-Stack Sandboxes.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping
from typing import Any


def render_commit_skill_form(raw_slug: str) -> str:
    """Render the path-scoped Conventional Commit form for a verified node-owned skill."""
    def_slug = html.escape(raw_slug, quote=True)
    return (
        "<form method='post' action='/api/tools/skills/commit' "
        "data-zcg-post='/api/tools/skills/commit' data-zcg-target='#zcg-skill-save-out' "
        f"class='zcg-tabs' style='margin-top:0.55rem;'><input type='hidden' name='skill_slug' "
        f"value='{def_slug}'><input name='commit_message' value='feat(skills): update {def_slug}' "
        "aria-label='Conventional commit message' required>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
        "Commit Saved Skill</button></form>"
    )


def _render_skill_table(rows: list[dict[str, Any]], empty_msg: str, *, mode: str = "") -> str:
    if not rows:
        return f"<p class='zcg-muted-note'>{empty_msg}</p>"
    m_q = f"&amp;mode={html.escape(mode, quote=True)}" if mode else ""
    m_val = html.escape(mode, quote=True)
    tr_list: list[str] = []
    for s in rows:
        slug_h, slug_q = html.escape(str(s["slug"])), html.escape(str(s["slug"]), quote=True)
        tier = str(s.get("origin_tier") or ("node" if s.get("editable") else "engine"))
        badge = (
            "✏️ Node-Owned"
            if tier == "node"
            else ("🏛️ Parent Layer" if tier == "parent" else "⚙️ Core / Stack")
        )
        act_lbl, act_q = ("Edit", "edit") if s["editable"] else ("View", "view")
        del_btn = (
            "<form method='post' action='/api/tools/skills/delete' "
            "data-zcg-post='/api/tools/skills/delete' data-zcg-target='#zcg-tools-panel' "
            f"style='display:inline;margin-left:0.35rem;'><input type='hidden' name='skill_slug' "
            f"value='{slug_q}'><input type='hidden' name='mode' value='{m_val}'>"
            "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
            "Delete</button></form>"
            if s["editable"]
            else ""
        )
        tr_list.append(
            f"<tr><td><code>{slug_h}</code></td><td><span class='zcg-chip'>{badge}</span></td>"
            f"<td><small>{html.escape(str(s['source']))}</small></td>"
            f"<td><button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
            f"data-zcg-get='/api/tools?skill={slug_q}&amp;action={act_q}{m_q}' "
            f"data-zcg-target='#zcg-tools-panel'>{act_lbl}</button>{del_btn}</td></tr>"
        )
    return (
        "<table class='zcg-table' aria-label='Active workspace skills'>"
        "<thead><tr><th>Skill</th><th>Origin</th><th>Source</th><th>Actions</th></tr></thead>"
        f"<tbody>{''.join(tr_list)}</tbody></table>"
    )


def _render_skill_detail_html(
    studio: Mapping[str, Any], sel: dict[str, Any] | None, action: str, *, mode: str = ""
) -> str:
    lid = str(studio["layer_id"])
    lid_h = html.escape(lid)
    m_q = f"&amp;mode={html.escape(mode, quote=True)}" if mode else ""
    if sel is not None and not sel.get("editable") and action != "duplicate":
        sl_q, sl_h = html.escape(str(sel["slug"]), quote=True), html.escape(str(sel["slug"]))
        src_h = html.escape(str(sel["source"]))
        return (
            "<div class='zcg-card' style='margin-top:0.85rem;'><div class='zcg-card__header'>"
            f"<h4>🔒 Viewing Read-Only Skill: <code>{sl_h}</code> "
            f"<span class='zcg-badge'>{src_h}</span></h4>"
            "<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
            f"data-zcg-get='/api/tools?skill={sl_q}&amp;action=duplicate{m_q}' "
            "data-zcg-target='#zcg-tools-panel'>Duplicate as Node Skill</button></div>"
            f"<p class='zcg-muted-note'>Built-in engine or parent-layer skill. Click "
            f"<strong>Duplicate as Node Skill</strong> to customize for <code>{lid_h}</code>.</p>"
            f"<pre class='zcg-doc-pre'><code>{html.escape(str(sel['content']))}</code></pre></div>"
        )
    if sel is None and action != "new":
        return (
            "<p class='zcg-muted-note' style='margin-top:0.75rem;'>Select <strong>View</strong> "
            "to inspect a core/parent skill, <strong>Edit</strong> to modify a node skill, or "
            "click <strong>+ New Node Skill</strong> above.</p>"
        )
    if action == "duplicate" and sel is not None:
        raw_slug = f"{lid}-{sel['slug']}"
        raw_body = str(sel["content"]).replace(f"name: {sel['slug']}", f"name: {raw_slug}", 1)
        hdr = f"<h4>📋 Duplicate as Node Skill (<code>{html.escape(raw_slug)}</code>)</h4>"
        raw_sha, src_slug = "", str(sel["slug"])
    elif sel is not None:
        raw_slug, raw_sha, raw_body = str(sel["slug"]), str(sel["sha256"]), str(sel["content"])
        hdr = f"<h4>✏️ Editing Node Skill: <code>{html.escape(raw_slug)}</code></h4>"
        src_slug = raw_slug
    else:
        raw_slug, raw_sha, src_slug = "custom-node-skill", "", ""
        raw_body = (
            "---\nname: custom-node-skill\n"
            "description: Execute a single deterministic domain workflow.\n---\n\n# Custom Skill\n"
        )
        hdr = "<h4>+ Create New Node Skill</h4>"
    draft_raw = studio.get("draft")
    draft = draft_raw if isinstance(draft_raw, Mapping) else {}
    has_draft = bool(draft.get("has_draft"))
    if has_draft and str(draft.get("content") or "").strip():
        raw_body = str(draft["content"])
    draft_updated = str(draft.get("updated_at") or "")
    line_count = len(raw_body.splitlines())
    draft_key = f"skill:{raw_slug}"
    props_h = html.escape(
        json.dumps(
            {
                "saveUrl": "/api/tools/skills/draft",
                "payloadField": "content",
                "draftKey": draft_key,
                "storageKey": f"zcg_md_skill_{raw_slug}",
                "hasServerDraft": has_draft,
                "maxLines": 464,
            }
        ),
        quote=True,
    )
    stamp_s = f" · {html.escape(draft_updated)}" if draft_updated else ""
    status_txt = (
        f"📝 Unapplied draft restored (.zcg/runtime/ — repo still clean){stamp_s}"
        if has_draft
        else "● Edits auto-save as a private draft outside Git until applied"
    )
    act_q = html.escape(action or "edit", quote=True)
    m_val = html.escape(mode, quote=True)
    discard_form = (
        "<form method='post' action='/api/tools/skills/draft/discard' "
        "data-zcg-post='/api/tools/skills/draft/discard' data-zcg-target='#zcg-tools-panel' "
        "style='display:inline;'>"
        f"<input type='hidden' name='draft_key' value='{html.escape(draft_key, quote=True)}'>"
        f"<input type='hidden' name='skill_slug' value='{html.escape(src_slug, quote=True)}'>"
        f"<input type='hidden' name='action' value='{act_q}'>"
        f"<input type='hidden' name='mode' value='{m_val}'>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        "data-draft-discard>Discard Draft</button></form>"
        if has_draft
        else ""
    )
    def_slug, def_sha, def_body = (
        html.escape(raw_slug, quote=True),
        html.escape(raw_sha, quote=True),
        html.escape(raw_body),
    )
    dirty_html = ""
    if sel is not None and bool(sel.get("is_dirty")) and raw_sha:
        rel_h = html.escape(
            str(sel.get("canonical_rel_path") or f"templates/{lid}/skills/{raw_slug}/SKILL.md")
        )
        dirty_html = (
            "<div class='zcg-dirty-banner'>"
            f"<span>🟡 <code>{rel_h}</code> saved on disk (uncommitted in Git)</span>"
            f"{render_commit_skill_form(raw_slug)}</div>"
        )
    return (
        "<div class='zcg-card zcg-md-studio' data-island='draft-studio' data-hydrate='eager' "
        f"data-props='{props_h}' style='margin-top:0.85rem;'>{hdr}"
        "<div class='zcg-card__header' style='margin-bottom:0.55rem;'>"
        f"<span class='zcg-muted-note' data-draft-status>{status_txt}</span>"
        f"<div class='zcg-tabs'><span class='zcg-badge' data-draft-lines>"
        f"{line_count} / 464 lines</span>{discard_form}</div></div>"
        f"{dirty_html}<form method='post' action='/api/tools/skills/save' "
        "data-zcg-post='/api/tools/skills/save' data-zcg-target='#zcg-skill-save-out'>"
        f"<input type='hidden' name='expected_sha256' value='{def_sha}'>"
        f"<div class='zcg-field'><label>Node Skill Slug (<code>templates/{lid_h}/skills/"
        "&lt;slug&gt;/SKILL.md</code>)</label>"
        f"<input name='skill_slug' value='{def_slug}' required></div>"
        "<div class='zcg-field'><label>SKILL.md Content (Audited before save)</label>"
        "<textarea class='zcg-md-editor' name='content' rows='10' data-draft-input required>"
        f"{def_body}</textarea></div>"
        "<div class='zcg-tabs' style='margin-top:0.55rem;'>"
        "<label class='zcg-inline-check'><input type='checkbox' name='commit_now' value='1'> "
        "Also commit to Git</label>"
        f"<input name='commit_message' value='feat(skills): update {def_slug}' "
        "aria-label='Commit message'>"
        "<button type='submit' class='zcg-btn zcg-btn--sm'>Audit &amp; Save Skill</button>"
        "</div></form>"
        "<div id='zcg-skill-save-out' style='margin-top:0.55rem;' aria-live='polite'></div></div>"
    )


def _render_tool_rows_html(rows: list[dict[str, Any]], *, mode: str = "") -> str:
    m_q = f"?mode={html.escape(mode, quote=True)}" if mode else ""
    out: list[str] = []
    for it in rows:
        tid_h, tid_q = html.escape(it["tool_id"]), html.escape(it["tool_id"], quote=True)
        prov = bool(it["provisioned"])
        st_lbl, prov_lbl = ("ready", "Re-Provision") if prov else ("unprovisioned", "Enable")
        cli_h = html.escape(str(it.get("cli_command") or "zcg status ."))
        dis_btn = (
            f"<form method='post' action='/api/tools/{tid_q}/deprovision{m_q}' "
            f"data-zcg-post='/api/tools/{tid_q}/deprovision{m_q}' "
            "data-zcg-target='#zcg-tools-panel' style='display:inline;margin-left:0.35rem;'>"
            "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
            "Disable</button></form>"
            if prov
            else ""
        )
        run_btn = (
            "<button type='button' class='zcg-btn zcg-btn--sm' style='margin-right:0.35rem;' "
            f"data-zcg-get='/api/tools/{tid_q}/inspect' data-zcg-target='#zcg-tool-prov-out'>"
            "Run Check / Inspect</button>"
            if prov
            else ""
        )
        out.append(
            "<li class='zcg-knowledge-row' style='align-items:flex-start;flex-wrap:nowrap;'>"
            "<div style='flex:1 1 0;min-width:0;'>"
            f"<code>{tid_h}</code> — {st_lbl} <small>({html.escape(it['display_name'])})</small>"
            f"<div class='zcg-muted-note'>{html.escape(it['summary'])} · "
            f"CLI: <code>{cli_h}</code></div></div>"
            f"<div style='flex-shrink:0;'>{run_btn}"
            f"<form method='post' action='/api/tools/{tid_q}/provision{m_q}' "
            f"data-zcg-post='/api/tools/{tid_q}/provision{m_q}' "
            "data-zcg-target='#zcg-tool-prov-out' style='display:inline;'>"
            f"<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>{prov_lbl}"
            f"</button></form>{dis_btn}</div></li>"
        )
    return "".join(out)


def _render_agent_guidance_html(guidance: Mapping[str, Any] | None) -> str:
    if not guidance:
        return ""
    prof_h = html.escape(str(guidance.get("profile_label") or ""))
    model_h = html.escape(str(guidance.get("recommended_base_model") or ""))
    alt_h = html.escape(str(guidance.get("velocity_alternative") or ""))
    auto_h = html.escape(str(guidance.get("auto_orchestration_summary") or ""))
    cal_h = html.escape(str(guidance.get("continuous_calibration_rule") or ""))
    return (
        "<article class='zcg-card' style='margin-bottom:0.85rem;' data-zcg-agent-guidance>"
        "<h3>🧭 Set-and-Forget Agent &amp; Automatic Swarm Policy</h3>"
        "<ul class='zcg-knowledge-list'>"
        f"<li><strong>Active Node Profile:</strong> {prof_h}</li>"
        f"<li><strong>Default Base Model (Select Once):</strong> <code>{model_h}</code> "
        f"<span class='zcg-muted-note'>(Alternative: {alt_h} — avoid pinning "
        "<code>Orchestrator</code> globally; speak naturally without typing "
        "<code>/teamwork</code>)</span></li>"
        f"<li><strong>Automatic Multi-Agent Deduction (<code>Mandate #12</code>):</strong> "
        f"{auto_h}</li>"
        f"<li><strong>Continuous Stack &amp; Model-Currency Gate:</strong> {cal_h}</li>"
        "</ul></article>"
    )


def render_tools_and_skills_html(
    studio: Mapping[str, Any],
    tools: list[dict[str, Any]],
    *,
    action: str = "",
    mode: str = "",
    banner_html: str = "",
) -> str:
    """Render Skills Studio (?mode=skills), Tools & Sandboxes (?mode=tools), or both."""
    sel = studio.get("selected_skill") if isinstance(studio.get("selected_skill"), dict) else None
    all_sk: list[dict[str, Any]] = list(studio.get("skills", ()))
    owned_sk = [s for s in all_sk if s.get("origin_tier") == "node" or s.get("editable")]
    parent_sk = [s for s in all_sk if s.get("origin_tier") == "parent"]
    eng_sk = [s for s in all_sk if not s.get("editable") and s.get("origin_tier") != "parent"]
    m_q = f"&amp;mode={html.escape(mode, quote=True)}" if mode else ""
    lid_h = html.escape(str(studio["layer_id"]))
    owned_msg = "0 node-owned skills yet. Click '+ New Node Skill' or duplicate a core skill."
    owned_tbl = _render_skill_table(owned_sk, owned_msg, mode=mode)
    parent_sec = (
        f"<h4 style='margin-top:0.85rem;'>🏛️ Inherited from Parent Layer ({len(parent_sk)})</h4>"
        + _render_skill_table(parent_sk, "", mode=mode)
        if parent_sk
        else ""
    )
    eng_tbl = _render_skill_table(eng_sk, "0 core or stack skills projected.", mode=mode)
    skills_card = (
        "<article class='zcg-card'><div class='zcg-card__header'>"
        "<h3>Node Skills &amp; Inherited Capabilities</h3><div class='zcg-tabs'>"
        f"<span class='zcg-badge'>Skill Trust: {int(studio['trust_score'])}/100</span>"
        "<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        f"data-zcg-get='/api/tools?action=new{m_q}' data-zcg-target='#zcg-tools-panel'>"
        "+ New Node Skill</button></div></div>"
        f"<h4>✏️ Node-Owned Skills (<code>templates/{lid_h}/skills/</code> · {len(owned_sk)})</h4>"
        f"{owned_tbl}{parent_sec}"
        f"<h4 style='margin-top:0.85rem;'>⚙️ ZeroCloudGravity Core &amp; Stack Skills "
        f"(Engine Baseline · {len(eng_sk)})</h4>{eng_tbl}"
        f"{_render_skill_detail_html(studio, sel, action, mode=mode)}</article>"
    )
    rec_tools = [t for t in tools if t.get("recommended")]
    opt_tools = [t for t in tools if not t.get("recommended")]
    rec_html = (
        f"<h4>⭐ Recommended for This Node ({len(rec_tools)})</h4>"
        f"<ul class='zcg-knowledge-list'>{_render_tool_rows_html(rec_tools, mode=mode)}</ul>"
        if rec_tools
        else ""
    )
    opt_hdr = f"<h4 style='margin-top:0.85rem;'>Optional &amp; Specialized ({len(opt_tools)})</h4>"
    opt_html = (
        f"{opt_hdr}<ul class='zcg-knowledge-list'>{_render_tool_rows_html(opt_tools, mode=mode)}"
        "</ul>"
        if opt_tools
        else ""
    )
    tools_card = (
        "<article class='zcg-card'><h3>Isolated Tool-Stack Runtimes (<code>.zcg/tools/</code>)</h3>"
        "<p class='zcg-muted-note'>Enable read-only sandboxed tools for this node and execute "
        "on-demand audits or diagnostics.</p>"
        "<div id='zcg-tool-prov-out' style='margin:0.55rem 0;' aria-live='polite'></div>"
        f"{rec_html}{opt_html}</article>"
    )
    guidance_raw = studio.get("agent_guidance")
    guidance_html = _render_agent_guidance_html(
        guidance_raw if isinstance(guidance_raw, Mapping) else None
    )
    skills_section = f"{guidance_html}{skills_card}"
    body = (
        skills_section
        if mode == "skills"
        else (tools_card if mode == "tools" else f"{skills_section}{tools_card}")
    )
    return f"<div id='zcg-tools-panel'>{banner_html}<section data-zcg-tools>{body}</section></div>"
