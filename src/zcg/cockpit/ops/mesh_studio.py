"""Governed Mesh & Role Policy Studio, Workspace Scope Lens, and Quick-Task Target Selector.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final

from zcg.cockpit.views.mesh_liveness import probe_local_node_online
from zcg.core.constants import (
    NODE_MANIFEST_REL_PATH,
    VALID_KNOWLEDGE_PREFIXES,
    VALID_NODE_LINK_RELATIONS,
)
from zcg.core.domain import is_kebab_id
from zcg.core.manifests import load_node_manifest
from zcg.governance.policy.mesh_relations import (
    VALID_MESH_TOPOLOGY_MODES,
    NodeRelationGrant,
    is_airlocked_wallet_node,
    normalize_workspace_scope,
    resolve_mesh_governance_policy,
    resolve_node_relation_grants,
)
from zcg.topology.posture import PERSONAL_CONSTELLATION_PILLARS
from zcg.web.ui.template_ast import sanitize_url

if TYPE_CHECKING:
    from pathlib import Path

_WORKSPACE_SCOPE_PILLS: Final[tuple[tuple[str, str], ...]] = (
    ("all", "🌐 All"),
    ("node", "📍 This Node"),
    ("network", "🏛️ 1-Hop"),
    ("corpora", "📚 Corpora"),
)
_GOVERNOR_ROLES: Final[frozenset[str]] = frozenset({"workstation", "corporate", "department"})
_TOPOLOGY_LABELS: Final[dict[str, str]] = {
    "full-mesh": "Full Mesh (All non-wallet pillars peer-ready)",
    "hierarchical-only": "Hierarchical Only (Strict vertical chain)",
    "curated-matrix": "Curated Matrix (Explicit lateral channels)",
}
_VERB_PRESETS: Final[tuple[tuple[str, str], ...]] = (
    ("consult_context,propose_work", "Consult + Propose"),
    ("consult_context,propose_work,delegate_work,validate_gate", "Full Delegation + Gate"),
)


def render_workspace_scope_bar_html(active_scope: str = "all") -> str:
    """Render the persistent 4-pill Workspace Scope Lens for the Workspace header."""
    eff = normalize_workspace_scope(active_scope)
    btns = "".join(
        f"<button type='button' class='zcg-tab{' is-active' if s == eff else ''}' "
        f"data-ws-scope='{s}' aria-pressed='{'true' if s == eff else 'false'}'>{lbl}</button>"
        for s, lbl in _WORKSPACE_SCOPE_PILLS
    )
    return (
        f"<div class='zcg-ws-scope' data-zcg-ws-scope='{eff}' role='group' "
        f"aria-label='Workspace visibility scope'>{btns}</div>"
    )


def render_corpora_scope_alert_html(ws_scope: str) -> str:
    """Render the Corpora read-only scope banner with a direct Docs & Knowledge shortcut."""
    if ws_scope != "corpora":
        return ""
    return (
        "<div class='zcg-alert' style='margin-bottom:0.65rem;'>"
        "<span>📚 Connected knowledge corpora are read-only reference feeds.</span> "
        "<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
        "data-zcg-get='/api/modules/docs-reader?origin=corpus' "
        "data-zcg-target='#zcg-capability-stage'>Browse Connected Corpora →</button></div>"
    )


def render_quick_task_target_select_html(grants: Sequence[NodeRelationGrant]) -> str:
    """Render the Quick-Add target node dropdown when authorized 1-hop work grants exist."""
    routable = [
        g for g in grants if "delegate_work" in g.allowed_verbs or "propose_work" in g.allowed_verbs
    ]
    if not routable:
        return ""
    opts = ["<option value=''>📍 This Node (WORKTASK.md)</option>"]
    for g in routable:
        tgt_q, tgt_h = html.escape(g.target_node, quote=True), html.escape(g.target_node)
        if "delegate_work" in g.allowed_verbs:
            pfx = "↓ Delegate"
        else:
            pfx = "↑ Propose" if g.relation_role == "governed-child" else "↔ Request"
        opts.append(f"<option value='{tgt_q}'>{pfx}: {tgt_h}</option>")
    return f"<select name='exchange_target' aria-label='Task target node'>{''.join(opts)}</select>"


def is_corpus_link(entry: Mapping[str, Any]) -> bool:
    """Return True when a linked_nodes entry represents a knowledge corpus feed."""
    nid, rel = str(entry.get("node_id") or ""), str(entry.get("relation") or "")
    return (
        str(entry.get("layer_role") or "") == "knowledge"
        or rel.startswith("knowledge")
        or nid.startswith(VALID_KNOWLEDGE_PREFIXES)
    )


def build_constellation_pillars(
    ws: Path, lid: str, manifest: dict[str, Any]
) -> list[dict[str, str]]:
    """Build the 6 personal constellation pillar rows and local presence/airlock status."""
    persona = lid
    for sfx in (f"-{p}" for p in PERSONAL_CONSTELLATION_PILLARS):
        if persona.endswith(sfx) and len(persona) > len(sfx):
            persona = persona.removesuffix(sfx)
            break
    l_ids = {str(x.get("node_id") or "") for x in manifest.get("linked_nodes", []) if isinstance(x, dict)}  # noqa: E501  # fmt: skip
    gov_r, up = str(manifest.get("governing_root_id") or ""), manifest.get("upstream_layer")
    up_id = str(up.get("layer_id") or "") if isinstance(up, dict) else ""
    rows: list[dict[str, str]] = []
    for pillar in PERSONAL_CONSTELLATION_PILLARS:
        cid = f"{persona}-{pillar}"
        cands = (ws.parent / cid, ws.parent.parent / cid, ws / "Projects" / cid, ws.parent / "Projects" / cid)  # noqa: E501  # fmt: skip
        present = lid == cid or cid in l_ids or cid in (gov_r, up_id) or any((d / NODE_MANIFEST_REL_PATH).is_file() for d in cands)  # noqa: E501  # fmt: skip
        air = "R3 local-only (via work)" if pillar == "wallet" else "peer-ready"
        rows.append({"pillar": pillar, "node_id": cid, "status": "active" if present else "blueprint", "airlock": air})  # noqa: E501  # fmt: skip
    return rows


def render_link_form_html(link_endpoint: str, *, target_sel: str = "#zcg-mesh-panel") -> str:
    """Render the explicit cross-network node link form for the Mesh Studio."""
    ep_h, tgt_h = html.escape(link_endpoint, quote=True), html.escape(target_sel, quote=True)
    opts = "".join(
        f'<option value="{html.escape(r, quote=True)}">{html.escape(r)}</option>'
        for r in VALID_NODE_LINK_RELATIONS
    )
    return (
        f'<form class="zcg-form" method="post" action="{ep_h}" data-zcg-post="{ep_h}" '
        f'data-zcg-target="{tgt_h}" style="margin-top:0.85rem;"><div class="zcg-grid">'
        '<label class="zcg-field"><span>Remote Git URL or Local Node Ref</span>'
        '<input type="text" name="from_source" placeholder="https://github.com/org/node.git"></label>'
        '<label class="zcg-field"><span>Target Node ID (optional with URL)</span>'
        '<input type="text" name="target_id" placeholder="org-partner"></label>'
        f'<label class="zcg-field"><span>Relation</span><select name="relation">{opts}</select>'
        '</label></div><div style="margin-top:0.65rem;">'
        '<button type="submit" class="zcg-btn zcg-btn--sm">Connect Sovereign Node</button>'
        "</div></form>"
    )


def render_unlink_btn(unlink_ep: str, node_id: str, label: str = "Disconnect") -> str:
    """Render an inline disconnect/cleanup button for an explicit linked node."""
    ep_h, nid_h = html.escape(unlink_ep, quote=True), html.escape(node_id, quote=True)
    return (
        f'<form method="post" action="{ep_h}" data-zcg-post="{ep_h}" '
        'data-zcg-target="#zcg-mesh-panel" style="display:inline;">'
        f'<input type="hidden" name="target_id" value="{nid_h}">'
        f'<button type="submit" class="zcg-btn zcg-btn--secondary zcg-btn--sm">{html.escape(label)}'
        "</button></form>"
    )


def render_mesh_governance_card_html(
    ws: Path, *, clean_prefix: str, children: Sequence[Mapping[str, Any]]
) -> str:
    """Render the Root 0 Governed Mesh & Role Policy editor or subordinate inherited policy view."""
    pol = resolve_mesh_governance_policy(ws)
    grants = resolve_node_relation_grants(ws)
    gov_h = html.escape(pol.governed_by)
    has_m = (ws / NODE_MANIFEST_REL_PATH).is_file()
    m_role = str(load_node_manifest(ws).get("layer_role") or "") if has_m else ""
    is_governor = not pol.inherited_from_parent and (bool(children) or m_role in _GOVERNOR_ROLES)
    if not is_governor:
        grant_badges = "".join(
            f"<span class='zcg-badge'>{html.escape(g.target_node)} · "
            f"{html.escape(g.relation_role)} · "
            f"{html.escape(', '.join(g.allowed_verbs) or 'airlocked')}</span>"
            for g in grants
        )
        grants_h = (
            f"<div class='zcg-chip-list' style='margin-top:0.5rem;'>{grant_badges}</div>"
            if grant_badges
            else "<p class='zcg-muted-note'>0 active 1-hop relation grants resolved.</p>"
        )
        return (
            "<article class='zcg-card' style='margin-top:0.85rem;'>"
            f"<h3>Inherited Mesh Role Policy (Governed by <code>{gov_h}</code>)</h3>"
            f"<p><span class='zcg-badge'>Topology: {html.escape(pol.topology_mode)}</span></p>"
            f"{grants_h}</article>"
        )
    ep_q = html.escape(f"{clean_prefix}/policy", quote=True)
    mode_opts = "".join(
        f"<option value='{m}'{' selected' if m == pol.topology_mode else ''}>"
        f"{html.escape(_TOPOLOGY_LABELS[m])}</option>"
        for m in VALID_MESH_TOPOLOGY_MODES
    )
    mode_form = (
        f"<form method='post' action='{ep_q}' data-zcg-post='{ep_q}' "
        "data-zcg-target='#zcg-mesh-panel' class='zcg-tabs' style='margin-bottom:0.65rem;'>"
        f"<select name='topology_mode' aria-label='Mesh topology mode'>{mode_opts}</select>"
        "<button type='submit' class='zcg-btn zcg-btn--sm'>Save Policy</button></form>"
    )
    ch_rows = "".join(
        "<li class='zcg-knowledge-row'><span>"
        f"<code>{html.escape(r.source_node)}</code> "
        f"{'↔' if r.reciprocal else '→'} <code>{html.escape(r.target_node)}</code> "
        f"<span class='zcg-badge'>{html.escape(', '.join(r.allowed_verbs))}</span></span>"
        f"<form method='post' action='{ep_q}' data-zcg-post='{ep_q}' "
        "data-zcg-target='#zcg-mesh-panel' style='display:inline;'>"
        "<input type='hidden' name='action_kind' value='remove_channel'>"
        f"<input type='hidden' name='source' value='{html.escape(r.source_node, quote=True)}'>"
        f"<input type='hidden' name='target' value='{html.escape(r.target_node, quote=True)}'>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>Remove</button>"
        "</form></li>"
        for r in pol.lateral_channels
    )
    ch_list = (
        f"<ul class='zcg-knowledge-list'>{ch_rows}</ul>"
        if ch_rows
        else "<p class='zcg-muted-note'>0 curated lateral channels configured.</p>"
    )
    non_wallet = list(
        dict.fromkeys(
            cid
            for c in children
            if (cid := str(c.get("node_id") or "").strip()) and not is_airlocked_wallet_node(cid)
        )
    )
    add_form = ""
    if len(non_wallet) >= 2:
        c_opts = "".join(
            f"<option value='{html.escape(cid, quote=True)}'>{html.escape(cid)}</option>"
            for cid in non_wallet
        )
        v_opts = "".join(f"<option value='{v}'>{lbl}</option>" for v, lbl in _VERB_PRESETS)
        add_form = (
            f"<form method='post' action='{ep_q}' data-zcg-post='{ep_q}' "
            "data-zcg-target='#zcg-mesh-panel' class='zcg-quick-add-bar' "
            "style='margin-top:0.65rem;'>"
            "<input type='hidden' name='action_kind' value='add_channel'>"
            f"<select name='source' aria-label='Source child node'>{c_opts}</select>"
            f"<select name='target' aria-label='Target child node'>{c_opts}</select>"
            f"<select name='verbs' aria-label='Allowed relation verbs'>{v_opts}</select>"
            "<label class='zcg-inline-check'><input type='checkbox' name='reciprocal' "
            "value='1' checked> Reciprocal</label>"
            "<button type='submit' class='zcg-btn zcg-btn--sm'>Authorize Channel</button></form>"
        )
    return (
        "<article class='zcg-card' style='margin-top:0.85rem;'>"
        f"<h3>Governed Mesh &amp; Role Policy (<code>{gov_h}</code>)</h3>"
        f"{mode_form}{ch_list}{add_form}</article>"
    )


def resolve_local_node_workspace_dir(ws: Path, node_id: str) -> Path | None:
    """Resolve a local 1-hop child or sibling workspace directory for a valid kebab-case node ID."""
    if not is_kebab_id(node_id):
        return None
    candidates = (
        ws / "layers" / node_id,
        ws.parent / node_id,
        ws / "Projects" / node_id,
        ws.parent / "Projects" / node_id,
        ws.parent / f"{ws.name}-org" / node_id,
        ws.parent.parent / node_id,
    )
    for cand in candidates:
        if (cand / NODE_MANIFEST_REL_PATH).is_file():
            manifest = load_node_manifest(cand)
            if str(manifest.get("layer_id") or cand.name) == node_id:
                return cand.resolve()
    return None


def render_hierarchy_node_row_html(
    ws: Path,
    *,
    sym: str,
    nid: str,
    kind: str,
    role_label: str,
    clean_prefix: str,
    entry: Mapping[str, Any] | None = None,
    cache: dict[int, bool] | None = None,
) -> str:
    """Render one 1-hop hierarchy list row with live status and 1-click local wakeup controls."""
    raw_url = str((entry or {}).get("cockpit_url") or (entry or {}).get("public_url") or "").strip()
    online, _ = probe_local_node_online(raw_url, cache=cache) if raw_url else (False, "offline")
    if online:
        escaped_url = html.escape(sanitize_url(raw_url), quote=True)
        rhs = (
            "<span class='zcg-badge'>🟢 Online</span> "
            f"<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='{escaped_url}'>"
            "Open Workspace →</a>"
        )
    elif (
        kind in ("child", "sibling")
        and (local_dir := resolve_local_node_workspace_dir(ws, nid)) is not None
    ):
        act_ep = html.escape(f"{clean_prefix}/activate", quote=True)
        nid_q = html.escape(nid, quote=True)
        dir_q = html.escape(str(local_dir), quote=True)
        rhs = (
            "<div class='zcg-tabs'><span class='zcg-badge'>⚪ Offline</span>"
            f"<form method='post' action='{act_ep}' data-zcg-post='{act_ep}' "
            "data-zcg-target='#zcg-mesh-panel' style='display:inline;'>"
            f"<input type='hidden' name='target_id' value='{nid_q}'>"
            "<button type='submit' class='zcg-btn zcg-btn--sm'>Start Workspace</button></form>"
            "<button type='button' class='zcg-btn zcg-btn--secondary zcg-btn--sm' "
            f"data-zcg-copy='zcg apply-project {dir_q} --service-action activate'>"
            "Copy Start CLI</button></div>"
        )
    elif raw_url:
        rhs = "<span class='zcg-badge'>⚪ Offline</span>"
    else:
        rhs = ""
    return (
        f"<li class='zcg-knowledge-row'><span>{sym} <strong>{html.escape(nid)}</strong> "
        f"<span class='zcg-badge'>{html.escape(kind)} · {html.escape(role_label)}</span>"
        f"</span>{rhs}</li>"
    )


def activate_local_mesh_node(ws: Path, target_id: str) -> dict[str, Any]:
    """Activate a local 1-hop child or sibling workspace daemon and refresh parent node scopes."""
    from zcg.cockpit.ops import lifecycle

    target_dir = resolve_local_node_workspace_dir(ws, target_id.strip())
    if target_dir is None:
        raise ValueError(
            f"TARGET_WORKSPACE_NOT_FOUND: local workspace for {target_id!r} not found."
        )
    parent_dir = ws if (ws / NODE_MANIFEST_REL_PATH).is_file() else None
    res = lifecycle.manage_plugin_service(
        target_dir, action="activate", target_env="", parent_dir=parent_dir
    )
    svc = res["services"][0] if res.get("services") else {}
    topo = svc.get("intranet_topology") or {}
    url = str(topo.get("local_subdomain_url") or f"http://127.0.0.1:{topo.get('port', 8750)}/")
    if (ws / "surfaces/data/node_scope.json").is_file():
        lifecycle.manage_plugin_service(ws, action="provision", target_env="")
    return {
        "activated_node_id": res["layer_id"],
        "workspace_dir": str(target_dir),
        "cockpit_url": url,
        "environment": res["environment"],
    }


def parse_mesh_policy_mutation(
    payload: Mapping[str, Any], *, content_type: str
) -> tuple[dict[str, Any] | None, tuple[str, str] | None]:
    """Parse add_channel or remove_channel action parameters from a mesh policy POST payload."""
    act_kind = str(payload.get("action_kind") or "").strip().lower()
    add_ch: dict[str, Any] | None = None
    if act_kind == "add_channel":
        raw_v = payload.get("verbs")
        verbs = (
            [str(x).strip() for x in raw_v if str(x).strip()]
            if isinstance(raw_v, list | tuple)
            else [x.strip() for x in str(raw_v or "").split(",") if x.strip()]
        )
        def_rec = "urlencoded" not in content_type.lower()
        raw_rec = payload.get("reciprocal", def_rec)
        recip = (
            raw_rec
            if isinstance(raw_rec, bool)
            else str(raw_rec).strip().lower() in ("1", "true", "on", "yes")
        )
        add_ch = {
            "source": str(payload.get("source") or "").strip(),
            "target": str(payload.get("target") or "").strip(),
            "verbs": verbs,
            "reciprocal": recip,
        }
    rem_ch = (
        (str(payload.get("source") or "").strip(), str(payload.get("target") or "").strip())
        if act_kind == "remove_channel"
        else None
    )
    return add_ch, rem_ch
