"""Sovereign Knowledge Space HTML & 0-Regex Markdown Renderer.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import itertools
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final
from urllib.parse import quote

from zcg.core.manifests import strip_markdown_frontmatter
from zcg.core.markdown_scan import (
    is_markdown_list_item,
    parse_checkbox_line,
    parse_heading_line,
    slugify_heading,
)
from zcg.governance.workspace.knowledge_space import render_doc_starter_template
from zcg.web.ui.templates import SafeHTML

VISIBILITY_BADGES: Final[dict[str, str]] = {
    "internal-r3": "🔒 Private (This Node · R3)",
    "network-r2": "🏛️ Shared 1-Hop (R2)",
    "public-r0": "🌐 Public (R0)",
}


def _format_inline(text: str) -> str:
    parts = text.split("`")
    out: list[str] = []
    for idx, seg in enumerate(parts):
        if idx % 2 == 1:
            out.append(f"<code>{html.escape(seg)}</code>")
        else:
            b_parts = seg.split("**")
            rendered = "".join(
                f"<strong>{html.escape(bp)}</strong>" if b_i % 2 == 1 else html.escape(bp)
                for b_i, bp in enumerate(b_parts)
            )
            out.append(rendered)
    return "".join(out)


def _is_table_divider(cells: list[str]) -> bool:
    return bool(cells) and all(
        bool(c.strip()) and all(ch in "-: " for ch in c.strip()) and "-" in c for c in cells
    )


def render_markdown_document_html(md_text: str) -> tuple[SafeHTML, list[tuple[str, str]]]:
    """Render Markdown into safe semantic HTML + (slug, heading) outline without regexes."""
    clean_md = strip_markdown_frontmatter(md_text)
    blocks, toc = list[str](), list[tuple[str, str]]()
    in_fence, fence_ch = False, ""
    fence_buf, list_buf, table_rows = list[str](), list[str](), list[list[str]]()

    def _flush_list() -> None:
        if list_buf:
            blocks.append(f"<ul>{''.join(list_buf)}</ul>")
            list_buf.clear()

    def _flush_table() -> None:
        if not table_rows:
            return
        head = table_rows[0]
        body_r = [r for r in itertools.islice(table_rows, 1, None) if not _is_table_divider(r)]
        th_s = "".join(f"<th>{_format_inline(c)}</th>" for c in head)
        tb_s = "".join(
            "<tr>" + "".join(f"<td>{_format_inline(c)}</td>" for c in row) + "</tr>"
            for row in body_r
        )
        blocks.append(
            "<div class='zcg-table-wrap'><table class='zcg-table'>"
            f"<thead><tr>{th_s}</tr></thead><tbody>{tb_s}</tbody></table></div>"
        )
        table_rows.clear()

    for raw_ln in clean_md.splitlines():
        st = raw_ln.strip()
        if not in_fence and st.startswith(("```", "~~~")):
            _flush_list()
            _flush_table()
            in_fence, fence_ch, fence_buf = True, st[0], []
            continue
        if in_fence:
            if st.startswith(fence_ch * 3) and not st.lstrip(fence_ch).strip():
                code_h = html.escape("\n".join(fence_buf))
                blocks.append(f"<pre class='zcg-doc-pre'><code>{code_h}</code></pre>")
                in_fence, fence_ch, fence_buf = False, "", []
            else:
                fence_buf.append(raw_ln)
            continue
        if st.startswith("|") and st.endswith("|") and len(st) > 2:
            _flush_list()
            table_rows.append([c.strip() for c in st.strip("|").split("|")])
            continue
        _flush_table()
        if not st:
            _flush_list()
            continue
        if st in ("---", "***"):
            _flush_list()
            blocks.append("<hr>")
            continue
        if (hd := parse_heading_line(raw_ln, max_level=4)) is not None:
            _flush_list()
            slug = slugify_heading(hd.text, max_chars=48, fallback=f"sec-{len(toc) + 1}")
            tag = f"h{min(4, max(2, hd.level + 1))}"
            toc.append((slug, hd.text))
            blocks.append(
                f"<{tag} id='{html.escape(slug, True)}'>{_format_inline(hd.text)}</{tag}>"
            )
            continue
        if (cb := parse_checkbox_line(raw_ln)) is not None:
            mark = "☑" if cb.is_done else ("◐" if cb.is_in_progress else "☐")
            list_buf.append(f"<li>{mark} {_format_inline(cb.body)}</li>")
            continue
        if is_markdown_list_item(st):
            item_txt = (
                st.removeprefix("- ").removeprefix("* ").strip()
                if st.startswith(("- ", "* "))
                else st.partition(".")[2].strip()
            )
            list_buf.append(f"<li>{_format_inline(item_txt)}</li>")
            continue
        _flush_list()
        if st.startswith(">"):
            q_body = _format_inline(st.lstrip(">").strip())
            blocks.append(f"<blockquote class='zcg-doc-quote'>{q_body}</blockquote>")
        else:
            blocks.append(f"<p>{_format_inline(st)}</p>")

    if in_fence and fence_buf:
        blocks.append(
            f"<pre class='zcg-doc-pre'><code>{html.escape('\n'.join(fence_buf))}</code></pre>"
        )
    _flush_list()
    _flush_table()
    return SafeHTML("".join(blocks)), toc


def render_doc_dirty_banner_html(pfx: str, rel_doc: str) -> str:
    """Render the contextual uncommitted-file banner with an inline Commit Now form."""
    def_path = html.escape(rel_doc, quote=True)
    return (
        "<div class='zcg-dirty-banner'>"
        f"<span>🟡 <code>{def_path}</code> saved on disk (uncommitted in Git)</span>"
        f"<form method='post' action='{pfx}/commit' data-zcg-post='{pfx}/commit' "
        "data-zcg-target='#zcg-doc-commit-out' class='zcg-tabs'>"
        f"<input type='hidden' name='rel_path' value='{def_path}'>"
        f"<input name='commit_message' value='docs(knowledge): update {def_path}' "
        "aria-label='Commit message' required>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
        "Commit Now</button></form>"
        "<div id='zcg-doc-commit-out' aria-live='polite'></div></div>"
    )


def render_doc_editor_html(
    pfx: str,
    rel_doc: str,
    raw_body: str,
    *,
    is_new: bool,
    has_draft: bool = False,
    updated_at: str = "",
) -> str:
    """Render the unified R3 Markdown auto-draft studio and single save/commit form."""
    eff_rel = rel_doc or "docs/guides/operational-note.md"
    def_path = html.escape(eff_rel, quote=True)
    eff_raw = raw_body or render_doc_starter_template("guide", "Operational Note")
    def_body = html.escape(eff_raw)
    line_count = len(eff_raw.splitlines())
    draft_key = f"doc:{rel_doc or 'new'}"
    props_h = html.escape(
        json.dumps(
            {
                "saveUrl": f"{pfx}/draft",
                "payloadField": "content",
                "draftKey": draft_key,
                "storageKey": f"zcg_md_doc_{rel_doc or 'new'}",
                "hasServerDraft": has_draft,
                "maxLines": 464,
            }
        ),
        quote=True,
    )
    hdr = "+ Create New Knowledge Document" if is_new else f"✏️ Editing <code>{def_path}</code>"
    stamp_s = f" · {html.escape(updated_at)}" if updated_at else ""
    status_txt = (
        f"📝 Unapplied draft restored (.zcg/runtime/ — repo still clean){stamp_s}"
        if has_draft
        else "● Edits auto-save as a private draft outside Git until applied"
    )
    act_val = "new" if is_new else "edit"
    discard_form = (
        f"<form method='post' action='{pfx}/draft/discard' data-zcg-post='{pfx}/draft/discard' "
        "data-zcg-target='#zcg-docs-panel' style='display:inline;'>"
        f"<input type='hidden' name='draft_key' value='{html.escape(draft_key, quote=True)}'>"
        f"<input type='hidden' name='doc' value='{html.escape(rel_doc, quote=True)}'>"
        f"<input type='hidden' name='action' value='{act_val}'>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        "data-draft-discard>Discard Draft</button></form>"
        if has_draft
        else ""
    )
    return (
        "<div class='zcg-card zcg-md-studio' data-island='draft-studio' data-hydrate='eager' "
        f"data-props='{props_h}' style='margin-top:0.75rem;'><h4>{hdr}</h4>"
        "<div class='zcg-card__header' style='margin-bottom:0.55rem;'>"
        f"<span class='zcg-muted-note' data-draft-status>{status_txt}</span>"
        f"<div class='zcg-tabs'><span class='zcg-badge' data-draft-lines>"
        f"{line_count} / 464 lines</span>{discard_form}</div></div>"
        f"<form method='post' action='{pfx}/save' data-zcg-post='{pfx}/save' "
        "data-zcg-target='#zcg-docs-panel'>"
        "<div class='zcg-tabs' style='margin-bottom:0.55rem;'>"
        "<div class='zcg-field'><label>Document Path</label>"
        f"<input name='rel_path' value='{def_path}' aria-label='Document path' required></div>"
        "<div class='zcg-field'><label>Template</label>"
        "<select name='template_kind' aria-label='Document template'>"
        "<option value='guide'>Guide / SOP (Private · R3)</option>"
        "<option value='adr'>Decision ADR (Shared 1-Hop · R2)</option>"
        "<option value='note'>Working Note (Private · R3)</option></select></div></div>"
        "<textarea class='zcg-md-editor' name='content' rows='10' data-draft-input required>"
        f"{def_body}</textarea>"
        "<div class='zcg-tabs' style='margin-top:0.55rem;'>"
        "<label class='zcg-inline-check'><input type='checkbox' name='commit_now' value='1'> "
        "Also commit to Git</label>"
        f"<input name='commit_message' value='docs(knowledge): update {def_path}' "
        "aria-label='Commit message'>"
        "<button type='submit' class='zcg-btn zcg-btn--sm'>Save Document</button></div>"
        "</form></div>"
    )


def render_search_hits_html(pfx: str, query_s: str, hits: Sequence[Mapping[str, str]]) -> str:
    """Render ranked SQLite FTS5 search results with direct swap links."""
    if not query_s:
        return ""
    if not hits:
        q_h = html.escape(query_s)
        return f"<p class='zcg-muted-note'>0 FTS5 matches for <code>{q_h}</code>.</p>"
    li_s = "".join(
        "<li class='zcg-knowledge-row'>"
        f"<a href='{pfx}?source={quote(h['source_id'])}&amp;doc={quote(h['doc'])}' "
        f"data-zcg-get='{pfx}?source={quote(h['source_id'])}&amp;doc={quote(h['doc'])}' "
        "data-zcg-target='#zcg-docs-panel'>"
        f"<span class='zcg-badge'>{html.escape(h['origin_group'])}</span> "
        f"<strong>{html.escape(h['title'])}</strong> (<code>{html.escape(h['doc'])}</code>)</a>"
        f"<small class='zcg-muted-note'>{html.escape(h['snippet'])}</small></li>"
        for h in hits
    )
    return f"<ul class='zcg-knowledge-list' style='margin-bottom:0.75rem;'>{li_s}</ul>"


def render_knowledge_space_chrome(
    *,
    prefix: str,
    eff_origin: str,
    eff_src: str,
    vis_sources: Sequence[Mapping[str, Any]],
    query_str: str,
    hits: Sequence[Mapping[str, str]],
    is_r3: bool,
) -> tuple[str, str]:
    """Render (src_pills_html, search_and_hits_html) for Docs & Knowledge."""
    pfx = html.escape(prefix, quote=True)
    src_pills = (
        "".join(
            "<button type='button' class='zcg-chip"
            f"{' zcg-chip--active' if s['source_id'] == eff_src else ''}' "
            f"data-zcg-get='{pfx}?origin={eff_origin}&amp;source={quote(str(s['source_id']))}' "
            f"data-zcg-target='#zcg-docs-panel'>{html.escape(str(s['label']))}</button>"
            for s in vis_sources
        )
        if len(vis_sources) > 1
        else ""
    )
    new_btn = (
        f"<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        f"data-zcg-get='{pfx}?action=new' data-zcg-target='#zcg-docs-panel'>"
        "+ New Document</button>"
        if is_r3
        else ""
    )
    reset_btn = (
        f"<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        f"data-zcg-get='{pfx}?origin={eff_origin}' data-zcg-target='#zcg-docs-panel'>Reset</button>"
        if query_str.strip()
        else ""
    )
    search_bar = (
        f"<form method='get' action='{pfx}' data-zcg-get='{pfx}' "
        "data-zcg-target='#zcg-docs-panel' class='zcg-filter-bar' style='margin-bottom:0.55rem;'>"
        f"<input type='hidden' name='origin' value='{eff_origin}'>"
        f"<input name='q' value='{html.escape(query_str, True)}' "
        "placeholder='Search titles &amp; full text (SQLite FTS5)...'>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>Search</button>"
        f"{reset_btn}{new_btn}</form>"
    )
    return src_pills, search_bar + render_search_hits_html(pfx, query_str, hits)
