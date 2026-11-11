"""WCAG 2.2 AA accessible HTML5 UI & Collection Component Macros (Cards, Lists, Tables, Forms).

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Final

from zcg.web.templates import (
    ICON_TEMPLATE_GLOBALS,
    ZCG_ICONS,
    SafeHTML,
    escape_html,
    render_icon,
)

__all__ = [
    "ICON_TEMPLATE_GLOBALS",
    "VALID_HYDRATION_STRATEGIES",
    "ZCG_ICONS",
    "render_alert",
    "render_card",
    "render_card_grid",
    "render_file_dropzone",
    "render_form_field",
    "render_icon",
    "render_island",
    "render_item_list",
    "render_kpi_stat",
    "render_modal",
    "render_pagination",
    "render_progress_bar",
    "render_search_bar",
    "render_table",
    "render_tabs",
]

VALID_HYDRATION_STRATEGIES: Final[frozenset[str]] = frozenset({"eager", "visible", "idle"})


def render_card(
    *,
    title: str,
    body: SafeHTML | str,
    subtitle: str = "",
    badge: str = "",
    footer: SafeHTML | str = "",
    card_id: str = "",
) -> SafeHTML:
    """Render an accessible surface card component."""
    id_attr = f' id="{escape_html(card_id)}"' if card_id else ""
    badge_h = f'<span class="zcg-badge">{escape_html(badge)}</span>' if badge else ""
    sub_h = f'<p class="zcg-card__subtitle">{escape_html(subtitle)}</p>' if subtitle else ""
    foot_h = (
        f'<footer class="zcg-card__footer">{escape_html(footer)}</footer>' if str(footer) else ""
    )
    return SafeHTML(
        f'<article class="zcg-card"{id_attr}><header class="zcg-card__header">'
        f"<h3>{escape_html(title)}</h3>{badge_h}</header>{sub_h}"
        f'<div class="zcg-card__body">{escape_html(body)}</div>{foot_h}</article>'
    )


def render_card_grid(
    *,
    items: Sequence[Mapping[str, object]],
    title_key: str = "title",
    body_key: str = "body",
    subtitle_key: str = "",
    badge_key: str = "",
    empty_message: str = "No records available.",
    grid_id: str = "",
) -> SafeHTML:
    """Render a responsive collection grid of surface cards with empty-state fallback."""
    id_attr = f' id="{escape_html(grid_id)}"' if grid_id else ""
    if not items:
        return SafeHTML(
            f'<div class="zcg-card-grid"{id_attr}>'
            f'<p class="zcg-empty">{escape_html(empty_message)}</p></div>'
        )
    cards = "".join(
        render_card(
            title=str(it.get(title_key, "")),
            body=str(it.get(body_key, "")),
            subtitle=str(it.get(subtitle_key, "")) if subtitle_key else "",
            badge=str(it.get(badge_key, "")) if badge_key else "",
        ).value
        for it in items
    )
    return SafeHTML(f'<div class="zcg-card-grid"{id_attr}>{cards}</div>')


def render_item_list(
    *,
    items: Sequence[Mapping[str, object]],
    title_key: str = "title",
    meta_key: str = "",
    badge_key: str = "",
    empty_message: str = "No records available.",
    list_id: str = "",
) -> SafeHTML:
    """Render a semantic compact list collection view with empty-state fallback."""
    id_attr = f' id="{escape_html(list_id)}"' if list_id else ""
    if not items:
        return SafeHTML(
            f'<div class="zcg-list-wrap"{id_attr}>'
            f'<p class="zcg-empty">{escape_html(empty_message)}</p></div>'
        )
    rows: list[str] = []
    for it in items:
        m_val = it.get(meta_key) if meta_key else None
        b_val = it.get(badge_key) if badge_key else None
        mt = (
            f' <span class="zcg-list__meta">{escape_html(m_val)}</span>'
            if m_val is not None
            else ""
        )
        bg = f' <span class="zcg-badge">{escape_html(b_val)}</span>' if b_val is not None else ""
        rows.append(
            f'<li class="zcg-list__item"><strong class="zcg-list__title">'
            f"{escape_html(it.get(title_key, ''))}</strong>{mt}{bg}</li>"
        )
    return SafeHTML(f'<ul class="zcg-list"{id_attr}>{"".join(rows)}</ul>')


def render_table(
    *,
    columns: Sequence[tuple[str, str]],
    rows: Sequence[Mapping[str, object]],
    empty_message: str = "No records available.",
    table_id: str = "",
) -> SafeHTML:
    """Render a semantic HTML5 data table with empty-state fallback."""
    id_attr = f' id="{escape_html(table_id)}"' if table_id else ""
    thead = "".join(f'<th scope="col">{escape_html(lbl)}</th>' for _, lbl in columns)
    if not rows:
        span = max(1, len(columns))
        empty_e = escape_html(empty_message)
        tbody = f'<tr><td colspan="{span}" class="zcg-table__empty">{empty_e}</td></tr>'
    else:
        tbody = "".join(
            "<tr>" + "".join(f"<td>{escape_html(r.get(k, ''))}</td>" for k, _ in columns) + "</tr>"
            for r in rows
        )
    return SafeHTML(
        f'<div class="zcg-table-wrap"><table class="zcg-table"{id_attr}>'
        f"<thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table></div>"
    )


def render_pagination(
    *, page: int, total_pages: int, base_url: str, target_selector: str
) -> SafeHTML:
    """Render Z2 partial-swap pagination controls."""
    cur, total = max(1, page), max(1, total_pages)
    sep = "&amp;" if "?" in base_url else "?"
    burl, tgt = escape_html(base_url), escape_html(target_selector)
    prev_h = (
        f'<button type="button" class="zcg-btn" data-zcg-get="{burl}{sep}page={cur - 1}" '
        f'data-zcg-target="{tgt}">Previous</button>'
        if cur > 1
        else ""
    )
    next_h = (
        f'<button type="button" class="zcg-btn" data-zcg-get="{burl}{sep}page={cur + 1}" '
        f'data-zcg-target="{tgt}">Next</button>'
        if cur < total
        else ""
    )
    return SafeHTML(
        f'<nav class="zcg-pagination" aria-label="Pagination">{prev_h}'
        f'<span class="zcg-pagination__meta">Page {cur} of {total}</span>{next_h}</nav>'
    )


def render_search_bar(
    *,
    action_url: str,
    target_selector: str,
    query: str = "",
    placeholder: str = "Search...",
    input_name: str = "q",
) -> SafeHTML:
    """Render a Z2 partial-swap search form."""
    fid = f"search-{escape_html(input_name)}"
    act, tgt = escape_html(action_url), escape_html(target_selector)
    return SafeHTML(
        f'<form class="zcg-search" action="{act}" method="get" '
        f'data-zcg-get="{act}" data-zcg-target="{tgt}">'
        f'<label class="zcg-sr-only" for="{fid}">{escape_html(placeholder)}</label>'
        f'<input id="{fid}" type="search" name="{escape_html(input_name)}" '
        f'value="{escape_html(query)}" placeholder="{escape_html(placeholder)}">'
        '<button type="submit" class="zcg-btn">Search</button></form>'
    )


def render_form_field(
    *,
    name: str,
    label: str,
    field_type: str = "text",
    value: str = "",
    placeholder: str = "",
    required: bool = False,
    options: Sequence[tuple[str, str]] = (),
    error: str = "",
) -> SafeHTML:
    """Render a WCAG 2.2 AA labeled input, textarea, or select field with validation state."""
    fid = f"field-{escape_html(name)}"
    req = " required" if required else ""
    inv = ' aria-invalid="true"' if error else ""
    if field_type == "textarea":
        ctrl = (
            f'<textarea id="{fid}" name="{escape_html(name)}" '
            f'placeholder="{escape_html(placeholder)}"{req}{inv}>{escape_html(value)}</textarea>'
        )
    elif field_type == "select":
        opts = "".join(
            f'<option value="{escape_html(ov)}"{" selected" if ov == value else ""}>'
            f"{escape_html(ol)}</option>"
            for ov, ol in options
        )
        ctrl = f'<select id="{fid}" name="{escape_html(name)}"{req}{inv}>{opts}</select>'
    else:
        ctrl = (
            f'<input id="{fid}" type="{escape_html(field_type)}" name="{escape_html(name)}" '
            f'value="{escape_html(value)}" placeholder="{escape_html(placeholder)}"{req}{inv}>'
        )
    err_h = f'<p class="zcg-field__error" role="alert">{escape_html(error)}</p>' if error else ""
    return SafeHTML(
        f'<div class="zcg-field"><label for="{fid}">{escape_html(label)}</label>{ctrl}{err_h}</div>'
    )


def render_modal(*, modal_id: str, title: str, body: SafeHTML | str) -> SafeHTML:
    """Render a native HTML5 <dialog> modal container."""
    mid = escape_html(modal_id)
    return SafeHTML(
        f'<dialog id="{mid}" class="zcg-modal" aria-labelledby="{mid}-title">'
        f'<header class="zcg-modal__header"><h3 id="{mid}-title">{escape_html(title)}</h3>'
        f'<button type="button" class="zcg-btn" data-zcg-modal-close="{mid}">'
        f"Close</button></header>"
        f'<div class="zcg-modal__body">{escape_html(body)}</div></dialog>'
    )


def render_tabs(
    *, tabs: Sequence[tuple[str, str, str]], active_tab: str, target_selector: str
) -> SafeHTML:
    """Render an accessible role='tablist' navigation bar wired to Z2 partial swaps."""
    tgt = escape_html(target_selector)
    parts: list[str] = []
    for tid, lbl, url in tabs:
        cls = "zcg-tab is-active" if tid == active_tab else "zcg-tab"
        sel = "true" if tid == active_tab else "false"
        parts.append(
            f'<button type="button" role="tab" class="{cls}" aria-selected="{sel}" '
            f'data-zcg-get="{escape_html(url)}" data-zcg-target="{tgt}">'
            f"{escape_html(lbl)}</button>"
        )
    return SafeHTML(f'<div class="zcg-tabs" role="tablist">{"".join(parts)}</div>')


def render_alert(
    *, message: str, severity: str = "info", code: str = "", hint: str = ""
) -> SafeHTML:
    """Render a structured status or error alert banner."""
    sev = escape_html(severity.lower())
    code_attr = f' data-error-code="{escape_html(code)}"' if code else ""
    hint_h = f'<p class="zcg-alert__hint">{escape_html(hint)}</p>' if hint else ""
    return SafeHTML(
        f'<div class="zcg-alert zcg-alert--{sev}" role="alert"{code_attr}>'
        f'<p class="zcg-alert__message">{escape_html(message)}</p>{hint_h}</div>'
    )


def render_file_dropzone(
    *, action_url: str, target_selector: str, field_name: str = "file", accept: str = ""
) -> SafeHTML:
    """Render a multipart/form-data file upload form bound to Z2 partial swap."""
    fid = f"upload-{escape_html(field_name)}"
    act, tgt = escape_html(action_url), escape_html(target_selector)
    acc = f' accept="{escape_html(accept)}"' if accept else ""
    return SafeHTML(
        f'<form class="zcg-dropzone" action="{act}" method="post" '
        f'enctype="multipart/form-data" data-zcg-post="{act}" data-zcg-target="{tgt}">'
        f'<label for="{fid}">Select file to upload</label>'
        f'<input id="{fid}" type="file" name="{escape_html(field_name)}" required{acc}>'
        '<button type="submit" class="zcg-btn">Upload</button></form>'
    )


def render_progress_bar(
    *, progress_ratio: float, label: str = "", poll_url: str = "", poll_interval_ms: int = 1000
) -> SafeHTML:
    """Render a progress bar optionally polling until HTTP 286 Stop Polling."""
    clamped = min(1.0, max(0.0, float(progress_ratio)))
    pct = round(clamped * 100)
    poll_attrs = (
        f' data-zcg-poll="{escape_html(poll_url)}" data-zcg-interval="{int(poll_interval_ms)}"'
        if poll_url and clamped < 1.0
        else ""
    )
    lbl_h = (
        f'<span class="zcg-progress__label">{escape_html(label)} ({pct}%)</span>' if label else ""
    )
    return SafeHTML(
        f'<div class="zcg-progress"{poll_attrs}>{lbl_h}'
        f'<progress value="{pct}" max="100">{pct}%</progress></div>'
    )


def render_kpi_stat(*, label: str, value: str, delta: str = "", tone: str = "neutral") -> SafeHTML:
    """Render a compact KPI metric card."""
    delta_h = f'<span class="zcg-kpi__delta">{escape_html(delta)}</span>' if delta else ""
    return SafeHTML(
        f'<div class="zcg-kpi zcg-kpi--{escape_html(tone)}">'
        f'<span class="zcg-kpi__label">{escape_html(label)}</span>'
        f'<strong class="zcg-kpi__value">{escape_html(value)}</strong>{delta_h}</div>'
    )


def render_island(
    *,
    name: str,
    props: Mapping[str, object] | None = None,
    strategy: str = "visible",
    placeholder: str = "",
    module_src: str = "",
) -> SafeHTML:
    """Render a Z3 progressive-hydration island container."""
    if strategy not in VALID_HYDRATION_STRATEGIES:
        raise ValueError(f"Invalid hydration strategy {strategy!r}")
    props_json = escape_html(json.dumps(dict(props or {}), separators=(",", ":")))
    mod_attr = f' data-module="{escape_html(module_src)}"' if module_src else ""
    return SafeHTML(
        f'<div class="zcg-island" data-island="{escape_html(name)}" '
        f'data-hydrate="{escape_html(strategy)}" data-props="{props_json}"{mod_attr}>'
        f"{escape_html(placeholder)}</div>"
    )
