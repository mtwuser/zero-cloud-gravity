"""Loopback /healthz reachability probes, unified constellation/corpus tree, and branch UI.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final
from urllib.parse import urlsplit

from zcg.web.ops.probes import PeerHealthVerdict, probe_peer_healthz
from zcg.web.ui.templates import render_icon

DEFAULT_LOCAL_PROBE_TIMEOUT_SECONDS: Final[float] = 0.08
_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost"})
_DIRECTION_META: Final[dict[str, tuple[str, str]]] = {
    "↑ Governor": ("parent", "↑"),
    "↔ Peer": ("sibling", "↔"),
    "↓ Sub-Node": ("child", "↳"),
    "📚 Corpus": ("corpus", "📚"),
}


def probe_local_node_online(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_LOCAL_PROBE_TIMEOUT_SECONDS,
    probe_fn: Callable[[str], PeerHealthVerdict] | None = None,
    cache: dict[int, bool] | None = None,
) -> tuple[bool, str]:
    """Classify a node/corpus URL as ('online' | 'offline' | 'external') without remote egress."""
    cleaned = url.strip()
    if not cleaned:
        return False, "offline"
    parsed = urlsplit(cleaned)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return False, "offline"
    is_loopback = host in _LOOPBACK_HOSTS or host.endswith(".localhost")
    if not is_loopback:
        return True, "external"
    port = parsed.port
    if port is None or port <= 0:
        return False, "offline"
    if cache is not None and port in cache:
        cached_ok = cache[port]
        return cached_ok, ("online" if cached_ok else "offline")
    eff_probe: Callable[[str], PeerHealthVerdict] = (
        probe_fn
        if probe_fn is not None
        else (lambda u: probe_peer_healthz(u, timeout_seconds=timeout_seconds))
    )
    verdict = eff_probe(f"http://127.0.0.1:{port}")
    ok = bool(verdict.healthy)
    if cache is not None:
        cache[port] = ok
    return ok, ("online" if ok else "offline")


def annotate_cross_node_liveness(
    nav_items: Sequence[Mapping[str, str]],
    *,
    probe_fn: Callable[[str], PeerHealthVerdict] | None = None,
) -> list[dict[str, str]]:
    """Annotate cross-node navigation items with live loopback /healthz reachability."""
    cache: dict[int, bool] = {}
    annotated: list[dict[str, str]] = []
    for item in nav_items:
        ok, liv = probe_local_node_online(
            str(item.get("url") or ""), probe_fn=probe_fn, cache=cache
        )
        base = {str(k): str(v) for k, v in item.items()}
        annotated.append({**base, "online": "true" if ok else "false", "liveness": liv})
    return annotated


def annotate_passport_links_liveness(
    net_links: Mapping[str, Any],
    *,
    probe_fn: Callable[[str], PeerHealthVerdict] | None = None,
) -> dict[str, Any]:
    """Annotate network_representation_links entries with online boolean & liveness tags."""
    cache: dict[int, bool] = {}

    def _tag_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
        raw_u = str(entry.get("cockpit_url") or entry.get("public_url") or "")
        ok, liv = probe_local_node_online(raw_u, probe_fn=probe_fn, cache=cache)
        return {**entry, "online": ok, "liveness": liv}

    def _tag_list(key: str) -> list[dict[str, Any]]:
        raw_seq = net_links.get(key) or []
        return [_tag_entry(e) for e in raw_seq if isinstance(e, Mapping)]

    raw_p = net_links.get("parent_home_node")
    p_tagged = _tag_entry(raw_p) if isinstance(raw_p, Mapping) else None
    return {
        **net_links,
        "parent_home_node": p_tagged,
        "downward_child_nodes": _tag_list("downward_child_nodes"),
        "lateral_peers": _tag_list("lateral_peers"),
        "linked_nodes": _tag_list("linked_nodes"),
        "knowledge_nodes": _tag_list("knowledge_nodes"),
    }


def render_liveness_network_tree_html(layer_id: str, nav_items: Sequence[Mapping[str, str]]) -> str:
    """Render the nested 1-hop constellation + connected corpora tree without dummy root rows."""
    lid_h = html.escape(layer_id)
    has_parent = any(str(it.get("direction") or "") == "↑ Governor" for it in nav_items)
    self_cls = "zcg-tree__item--self" if has_parent else "zcg-tree__item--root-self"
    self_sym = "●" if has_parent else "★"
    self_tag = "Current" if has_parent else "Root 0 · Current"
    self_row = (
        f"<div class='zcg-tree__item {self_cls}' data-liveness='online'>"
        "<span><span class='zcg-live-dot zcg-live-dot--online' aria-hidden='true'></span>"
        f"{self_sym} <strong>{lid_h}</strong> <small>({self_tag})</small></span></div>"
    )
    if not nav_items:
        return (
            f"<nav class='zcg-tree' aria-label='Connected sovereign nodes'>{self_row}"
            "<small style='color:var(--zcg-muted)'>"
            "Standalone sovereign node (0 connected 1-hop or linked peers).</small></nav>"
        )
    buckets: dict[str, list[str]] = {
        "parent": [], "sibling": [], "child": [], "peer": [], "corpus": []
    }  # fmt: skip
    for it in nav_items:
        direction = str(it.get("direction") or "")
        kind, sym = _DIRECTION_META.get(direction, ("peer", "⇄"))
        eff_kind = ("grandchild" if has_parent else "child") if kind == "child" else kind
        hgrp = str(it.get("horizon_group") or "Fleet")
        is_corpus_grp = kind == "corpus" or hgrp in ("Knowledge", "Public Admin")
        cls_extra = " zcg-tree__item--corpus" if (is_corpus_grp and kind != "corpus") else ""
        nid = html.escape(str(it.get("node_id") or ""))
        role_h = html.escape(str(it.get("role_label") or it.get("role") or "node"))
        url_h = html.escape(str(it.get("url") or ""), quote=True)
        hgrp_h = html.escape(hgrp, quote=True)
        liv = str(it.get("liveness") or "online")
        if liv == "offline" or not url_h:
            row_html = (
                f"<span class='zcg-tree__item zcg-tree__item--{eff_kind}{cls_extra} "
                f"zcg-tree__item--offline' aria-disabled='true' data-liveness='offline' "
                f"data-horizon-group='{hgrp_h}' title='{nid} is offline (daemon stopped)'>"
                "<span><span class='zcg-live-dot zcg-live-dot--offline' aria-hidden='true'></span>"
                f"{sym} <strong>{nid}</strong> <small>({role_h} · Offline)</small></span></span>"
            )
        else:
            ext_attrs = " target='_blank' rel='noopener noreferrer'" if liv == "external" else ""
            dot_cls = "external" if liv == "external" else "online"
            ext_mark = " ↗" if liv == "external" else ""
            row_html = (
                f"<a class='zcg-tree__item zcg-tree__item--{eff_kind}{cls_extra}' href='{url_h}'"
                f"{ext_attrs} data-liveness='{html.escape(liv, quote=True)}' "
                f"data-horizon-group='{hgrp_h}'><span>"
                f"<span class='zcg-live-dot zcg-live-dot--{dot_cls}' aria-hidden='true'></span>"
                f"{sym} <strong>{nid}</strong> <small>({role_h}{ext_mark})</small></span></a>"
            )
        dest_key = "corpus" if is_corpus_grp else kind
        buckets[dest_key].append(row_html)
    top_rows = "".join(buckets["parent"])
    hierarchy = f"{top_rows}{self_row}" + "".join((*buckets["child"], *buckets["sibling"]))
    peers_sec = (
        "<div class='zcg-tree__divider'>Explicit Node Links</div>" + "".join(buckets["peer"])
        if buckets["peer"]
        else ""
    )
    corpus_sec = (
        "<div class='zcg-tree__divider'>Knowledge &amp; Corpora</div>" + "".join(buckets["corpus"])
        if buckets["corpus"]
        else ""
    )
    return (
        f"<nav class='zcg-tree' aria-label='Connected sovereign nodes'>"
        f"{hierarchy}{peers_sec}{corpus_sec}</nav>"
    )


def render_menu_constellation_html(nav_items: Sequence[Mapping[str, Any]]) -> str:
    """Render a compact, auto-collapsing (> 6 nodes) 1-Hop section for the User Avatar menu."""
    rows: list[str] = []
    for it in nav_items:
        direction = str(it.get("direction") or "")
        hgrp = str(it.get("horizon_group") or "")
        kind = str(it.get("role") or "")
        if direction == "↑ Governor" or hgrp in ("Knowledge", "Public Admin") or kind == "corpus":
            continue
        sym = "↳" if direction == "↓ Sub-Node" else ("↔" if direction == "↔ Peer" else "⇄")
        nid = html.escape(str(it.get("node_id") or ""))
        role_h = html.escape(str(it.get("role_label") or kind or "node"))
        url_h = html.escape(str(it.get("url") or ""), quote=True)
        liv = str(it.get("liveness") or "online")
        if liv == "offline" or not url_h:
            rows.append(
                "<span class='zcg-menu-node zcg-menu-node--offline' aria-disabled='true' "
                f"title='{nid} is offline'><span class='zcg-live-dot zcg-live-dot--offline' "
                f"aria-hidden='true'></span>{sym} <strong>{nid}</strong> "
                f"<small>({role_h} · Offline)</small></span>"
            )
        else:
            ext_a = " target='_blank' rel='noopener noreferrer'" if liv == "external" else ""
            dot = "external" if liv == "external" else "online"
            rows.append(
                f"<a class='zcg-menu-node' href='{url_h}'{ext_a}>"
                f"<span class='zcg-live-dot zcg-live-dot--{dot}' aria-hidden='true'></span>"
                f"{sym} <strong>{nid}</strong> <small>({role_h})</small></a>"
            )
    if not rows:
        return ""
    open_attr = " open" if len(rows) <= 6 else ""
    return (
        f"<details class='zcg-menu-constellation'{open_attr}>"
        "<summary class='zcg-burger__divider zcg-menu-constellation__toggle'>"
        f"1-Hop Nodes ({len(rows)}) <span aria-hidden='true'>▾</span></summary>"
        f"<div class='zcg-menu-constellation__list'>{''.join(rows)}</div></details>"
    )


def render_branch_switcher_html(
    b_info: Mapping[str, Any],
    *,
    datalist_id: str = "zcg-bp-list",
    target_id: str = "zcg-branch-out",
) -> str:
    """Render strictly real local Git branch chips plus an explicit '+ New branch' action."""
    tgt_h = html.escape(target_id, quote=True)
    chips: list[str] = []
    for raw_t in b_info.get("tracks") or ():
        if not isinstance(raw_t, Mapping):
            continue
        st = str(raw_t.get("status") or "")
        if st not in ("active", "created"):
            continue
        br = html.escape(str(raw_t.get("branch") or ""))
        purp = html.escape(str(raw_t.get("purpose") or "Local workspace branch"), quote=True)
        if st == "active":
            chips.append(
                f"<span class='zcg-chip zcg-chip--active' title='{purp}'>● <code>{br}</code></span>"
            )
        else:
            chips.append(
                "<form method='post' action='/api/modules/node-context/switch-branch' "
                "data-zcg-post='/api/modules/node-context/switch-branch' "
                f"data-zcg-target='#{tgt_h}' style='display:inline;'>"
                "<input type='hidden' name='allow_create' value='0'>"
                f"<input type='hidden' name='branch' value='{br}'>"
                f"<button type='submit' class='zcg-chip zcg-chip--created' "
                f"title='Switch to {br}: {purp}' style='cursor:pointer;'>"
                f"✓ <code>{br}</code></button></form>"
            )
    dl_h = html.escape(datalist_id, quote=True)
    opts = "".join(
        f"<option value='{html.escape(str(bp['branch']), quote=True)}' "
        f"label='{html.escape(str(bp.get('purpose') or ''), quote=True)}'></option>"
        for bp in (b_info.get("blueprints") or ())
        if isinstance(bp, Mapping) and bp.get("branch")
    )
    dl_html = f"<datalist id='{dl_h}'>{opts}</datalist>" if opts else ""
    new_form = (
        "<details class='zcg-new-branch'>"
        "<summary class='zcg-chip zcg-chip--new'>+ New branch</summary>"
        "<form method='post' action='/api/modules/node-context/switch-branch' "
        "data-zcg-post='/api/modules/node-context/switch-branch' "
        f"data-zcg-target='#{tgt_h}' class='zcg-new-branch__form'>"
        "<input type='hidden' name='allow_create' value='1'>"
        f"<input type='text' name='branch' list='{dl_h}' placeholder='feature/context-branch' "
        f"aria-label='New Git branch name' required>{dl_html}"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
        "Create &amp; Switch</button></form></details>"
    )
    return (
        f"<div class='zcg-chip-list'>{''.join(chips)}{new_form}</div>"
        f"<div id='{tgt_h}' aria-live='polite'></div>"
    )


def render_navbar_branch_dropdown_html(b_info: Mapping[str, Any]) -> str:
    """Render the compact top-navbar Git branch switcher popover with '+ New branch'."""
    act_b = html.escape(str(b_info.get("active_branch") or "master"))
    switcher = render_branch_switcher_html(
        b_info, datalist_id="zcg-nav-bp-list", target_id="zcg-nav-branch-out"
    )
    return (
        "<details class='zcg-burger zcg-branch-dd'>"
        f"<summary class='zcg-burger__btn' aria-label='Git branch ({act_b})' "
        f"title='Active Git branch: {act_b}'>{render_icon('branch')} "
        f"<code>{act_b}</code> <span aria-hidden='true'>▾</span></summary>"
        "<div class='zcg-burger__panel zcg-branch-panel'>"
        "<div class='zcg-user-menu__head'><strong>Git Context Branch</strong>"
        "<small>Switch or create a local repository branch</small></div>"
        f"{switcher}</div></details>"
    )


def render_navbar_env_switcher_html(
    *,
    active_env: str,
    promotion_pipeline: str = "staged",
    entity_kind: str = "enterprise",
    stages: Sequence[str] | None = None,
    env_urls: Mapping[str, str] | None = None,
    href_prefix: str = "/",
    can_switch: bool = True,
) -> str:
    """Render the real SSR top-navbar environment switcher when multi-stage promotion applies."""
    clean_e = active_env.strip().lower()
    eff_e = clean_e if clean_e in ("dev", "tst", "pre", "pro") else "pro"
    if stages is None:
        is_direct = (
            promotion_pipeline.strip().lower() == "direct"
            or entity_kind.strip().lower() == "individual"
        )
        eff_stages: tuple[str, ...] = () if is_direct else ("dev", "tst", "pre", "pro")
    else:
        eff_stages = tuple(s for s in stages if s in ("dev", "tst", "pre", "pro"))
    if not eff_stages or not can_switch:
        return ""
    lbl = eff_e.upper()
    urls = env_urls or {}
    sep = "&" if "?" in href_prefix else "?"
    pills = "".join(
        f"<a class='zcg-env-pill zcg-env-pill--{ec}{' is-active' if ec == eff_e else ''}' "
        f"href='{html.escape(str(urls.get(ec) or f'{href_prefix}{sep}env={ec}'), quote=True)}'>"
        f"{ec.upper()}</a>"
        for ec in eff_stages
    )
    dot = (
        f"<span class='zcg-env-dot zcg-env-dot--{eff_e}' aria-hidden='true'></span>"
        if eff_e != "pro"
        else str(render_icon("globe"))
    )
    stage_hint = " · ".join(eff_stages)
    return (
        "<details class='zcg-burger zcg-env-dd'>"
        f"<summary class='zcg-burger__btn' aria-label='Environment ({lbl})' "
        f"title='Switch node environment'>{dot} <span>Env: {lbl}</span> "
        "<span aria-hidden='true'>▾</span></summary>"
        "<div class='zcg-burger__panel'>"
        "<div class='zcg-user-menu__head'><strong>Node Environment</strong>"
        f"<small>Switch active stage ({html.escape(stage_hint)})</small></div>"
        f"<div class='zcg-env-strip' role='group' aria-label='Environment switcher'>{pills}</div>"
        "</div></details>"
    )
