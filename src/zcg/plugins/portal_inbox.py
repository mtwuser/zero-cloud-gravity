"""Universal local exposure/presence switch, facet cards, and R3 Cockpit Mailbox triage.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import datetime as dt
import html
import json
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import INDIVIDUAL_MIN_PRECEDENCE, NODE_MANIFEST_REL_PATH
from zcg.core.domain import is_kebab_id
from zcg.core.manifests import ensure_contained_path, load_node_manifest
from zcg.plugins.portal_channels import (
    CONTACT_INBOX_REL_PATH,
    HANDSHAKE_QUEUE_REL_PATH,
    MAX_PORTAL_FIELD_LEN,
    VALID_HANDSHAKE_PURPOSES,
)
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.auth.surface_access import SurfaceAccessPolicy
from zcg.web.capabilities.appearance import resolve_request_ring
from zcg.web.http.channels import DeliveryChannel, build_swap_response_headers
from zcg.web.http.request import Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.template_ast import sanitize_url
from zcg.web.ui.templates import render_icon

VALID_PUBLIC_EXPOSURE_MODES: Final[tuple[str, ...]] = (
    "online", "inbox-only", "members-only", "disabled",
)  # fmt: skip
VALID_INBOX_TRIAGE_DECISIONS: Final[tuple[str, ...]] = ("accepted", "archived", "blocked")
FORBIDDEN_PUBLIC_FACET_PILLARS: Final[frozenset[str]] = frozenset({"security"})
INBOX_TRIAGE_REL_PATH: Final[str] = ".zcg/runtime/portal/inbox_triage.json"

EXPOSURE_MODE_LABELS: Final[dict[str, str]] = {
    "online": "Online & Available",
    "inbox-only": "Mailbox Only (Offline)",
    "members-only": "Trusted Circles Only (R1/R2)",
    "disabled": "Disabled (1-Click Kill-Switch)",
}


@dataclass(frozen=True, slots=True)
class PublicExposureSpec:
    """Declarative outward exposure mode, availability banner, and connectable facet cards."""

    mode: str
    availability_note: str
    public_facets: tuple[dict[str, str], ...]


def parse_public_exposure_spec(manifest: Mapping[str, Any] | None) -> PublicExposureSpec:
    """Parse system/zcg-node.json -> public_exposure while blocking private security facets."""
    m = manifest if isinstance(manifest, Mapping) else {}
    vis = str(m.get("visibility") or "private").strip().lower()
    is_ind = str(m.get("entity_kind") or "").strip().lower() == "individual" or (
        int(m.get("precedence", 50)) >= INDIVIDUAL_MIN_PRECEDENCE
    )
    raw = m.get("public_exposure")
    cfg = raw if isinstance(raw, Mapping) else {}
    def_mode = "online" if vis == "public" else ("disabled" if is_ind else "inbox-only")
    raw_mode = str(cfg.get("mode") or def_mode).strip().lower()
    mode = raw_mode if raw_mode in VALID_PUBLIC_EXPOSURE_MODES else def_mode
    note = str(cfg.get("availability_note") or "").strip()[:MAX_PORTAL_FIELD_LEN]

    facets: list[dict[str, str]] = []
    raw_facets = cfg.get("public_facets")
    if isinstance(raw_facets, list):
        for item in raw_facets:
            if not isinstance(item, Mapping):
                continue
            pillar = str(item.get("pillar") or "").strip().lower()
            if pillar in FORBIDDEN_PUBLIC_FACET_PILLARS:
                raise ValueError(
                    f"PRIVATE_SECURITY_FACET_FORBIDDEN: pillar {pillar!r} cannot be public"
                )
            lbl = str(item.get("label") or "").strip()
            summ = str(item.get("summary") or "").strip()
            purp = str(item.get("purpose") or "personal-connection").strip().lower()
            eff_purp = purp if purp in VALID_HANDSHAKE_PURPOSES else "personal-connection"
            raw_u = str(item.get("public_url") or "#contact").strip()
            safe_u = sanitize_url(raw_u) if raw_u else "#contact"
            if is_kebab_id(pillar) and lbl:
                facets.append({
                    "pillar": pillar, "label": lbl, "summary": summ, "purpose": eff_purp,
                    "public_url": safe_u if safe_u != "#" else "#contact",
                })  # fmt: skip
    return PublicExposureSpec(mode=mode, availability_note=note, public_facets=tuple(facets))


def enforce_portal_exposure_gate(spec: PublicExposureSpec, *, caller_ring: str) -> None:
    """Enforce owner kill-switch ('disabled') and 'members-only' gate on /portal surfaces."""
    ring = caller_ring.strip().upper() or "R0"
    if spec.mode == "disabled" and ring != "R3":
        raise WebAppError("Public portal surface is currently disabled by the sovereign node owner", error_code="PUBLIC_SURFACE_DISABLED_BY_OWNER", http_status=int(HTTPStatus.SERVICE_UNAVAILABLE), severity=ErrorSeverity.WARNING)  # fmt: skip  # noqa: E501
    if spec.mode == "members-only" and ring == "R0":
        raise WebAppError("Public portal is restricted to authenticated R1/R2 contacts", error_code="PUBLIC_PORTAL_MEMBERS_ONLY", http_status=int(HTTPStatus.FORBIDDEN), severity=ErrorSeverity.WARNING)  # fmt: skip  # noqa: E501


def build_public_exposure_context(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return template variables for /portal exposure mode, availability note, and facets."""
    exp = parse_public_exposure_spec(manifest)
    return {"exposure_mode": exp.mode, "availability_note": exp.availability_note, "public_facets": list(exp.public_facets)}  # fmt: skip  # noqa: E501


def check_workspace_portal_exposure(workspace_dir: Path | None, *, caller_ring: str) -> None:
    """Load live manifest when workspace_dir is set and enforce portal exposure gate."""
    live_man = load_node_manifest(workspace_dir) if workspace_dir is not None else {}
    enforce_portal_exposure_gate(parse_public_exposure_spec(live_man), caller_ring=caller_ring)


def _read_jsonl(ws: Path, rel_path: str) -> list[dict[str, Any]]:
    target = ensure_contained_path(ws / rel_path, ws)
    if not target.is_file():
        return []
    out: list[dict[str, Any]] = []
    for ln in target.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            loaded = json.loads(ln)
            if isinstance(loaded, dict):
                out.append(loaded)
    return out


def _read_triage_map(ws: Path) -> dict[str, dict[str, str]]:
    target = ensure_contained_path(ws / INBOX_TRIAGE_REL_PATH, ws)
    if not target.is_file():
        return {}
    loaded = json.loads(target.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def inspect_portal_mailbox(workspace_dir: Path | None) -> dict[str, Any]:
    """Read local .zcg/runtime/portal/ contact & handshake queues merged with R3 triage state."""
    if workspace_dir is None:
        return {"items": [], "pending_count": 0, "total_count": 0}
    ws = workspace_dir.resolve()
    triage = _read_triage_map(ws)
    items: list[dict[str, Any]] = []
    for msg in _read_jsonl(ws, CONTACT_INBOX_REL_PATH):
        iid = str(msg.get("receipt_id") or "")
        st = str((triage.get(iid) or {}).get("decision") or "pending")
        items.append({
            "item_id": iid, "kind": "contact", "recorded_at": str(msg.get("recorded_at") or ""),
            "sender": f"{msg.get('sender_name', '')} <{msg.get('sender_contact', '')}>",
            "topic": str(msg.get("subject") or "Inquiry"), "detail": str(msg.get("message") or ""),
            "triage_status": st,
        })  # fmt: skip
    for hs in _read_jsonl(ws, HANDSHAKE_QUEUE_REL_PATH):
        iid = str(hs.get("request_id") or "")
        st = str((triage.get(iid) or {}).get("decision") or "pending")
        items.append({
            "item_id": iid, "kind": "handshake", "recorded_at": str(hs.get("recorded_at") or ""),
            "sender": str(hs.get("peer_node_id") or ""), "topic": str(hs.get("purpose") or ""),
            "detail": str(hs.get("note") or hs.get("peer_domain_or_repo") or ""),
            "triage_status": st,
        })  # fmt: skip
    items.sort(key=lambda r: str(r["recorded_at"]), reverse=True)
    pending_n = sum(1 for r in items if r["triage_status"] == "pending")
    return {"items": items, "pending_count": pending_n, "total_count": len(items)}


def triage_portal_mailbox_item(
    workspace_dir: Path, *, item_id: str, decision: str
) -> dict[str, Any]:
    """Record an R3 owner triage decision (accepted|archived|blocked) in .zcg/runtime/portal/."""
    ws = workspace_dir.resolve()
    clean_id, clean_dec = item_id.strip(), decision.strip().lower()
    if not clean_id or len(clean_id) > MAX_PORTAL_FIELD_LEN:
        raise ValueError("INVALID_INBOX_ITEM_ID: item_id must be non-blank")
    if clean_dec not in VALID_INBOX_TRIAGE_DECISIONS:
        raise ValueError(
            f"INVALID_INBOX_TRIAGE_DECISION: {decision!r} not in {VALID_INBOX_TRIAGE_DECISIONS}"
        )
    triage = _read_triage_map(ws)
    triage[clean_id] = {"decision": clean_dec, "updated_at": dt.datetime.now(dt.UTC).isoformat()}
    dest = ensure_contained_path(ws / INBOX_TRIAGE_REL_PATH, ws)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(triage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"item_id": clean_id, "decision": clean_dec}


def update_public_exposure_mode(
    workspace_dir: Path, *, mode: str, availability_note: str = ""
) -> dict[str, Any]:
    """Update system/zcg-node.json -> public_exposure (mode & availability_note) for R3 ops."""
    ws = workspace_dir.resolve()
    clean_mode = mode.strip().lower()
    if clean_mode not in VALID_PUBLIC_EXPOSURE_MODES:
        raise ValueError(
            f"INVALID_PUBLIC_EXPOSURE_MODE: {mode!r} not in {VALID_PUBLIC_EXPOSURE_MODES}"
        )
    m_path = ws / NODE_MANIFEST_REL_PATH
    if not m_path.is_file():
        raise ValueError("WORKSPACE_MANIFEST_MISSING: system/zcg-node.json is required")
    manifest = load_node_manifest(ws)
    raw_exp = manifest.get("public_exposure")
    cur_exp = dict(raw_exp) if isinstance(raw_exp, Mapping) else {}
    cur_exp["mode"] = clean_mode
    cur_exp["availability_note"] = availability_note.strip()[:MAX_PORTAL_FIELD_LEN]
    manifest["public_exposure"] = cur_exp
    m_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cur_exp


def _render_inbox_panel_html(
    exp: PublicExposureSpec, box: Mapping[str, Any], pfx: str, view_mode: str = ""
) -> str:
    opts = "".join(
        f"<option value='{m}'{' selected' if m == exp.mode else ''}>"
        f"{html.escape(EXPOSURE_MODE_LABELS[m])}</option>"
        for m in VALID_PUBLIC_EXPOSURE_MODES
    )
    note_h, vm_h = (
        html.escape(exp.availability_note, quote=True),
        html.escape(view_mode, quote=True),
    )
    rows: list[str] = []
    for it in box.get("items", ()):
        iid, st = html.escape(str(it["item_id"]), quote=True), html.escape(str(it["triage_status"]))
        btns = "".join(
            f"<form method='post' action='{pfx}/triage' data-zcg-post='{pfx}/triage' "
            "data-zcg-target='#zcg-inbox-stage' style='display:inline;'>"
            f"<input type='hidden' name='mode' value='{vm_h}'>"
            f"<input type='hidden' name='item_id' value='{iid}'>"
            f"<input type='hidden' name='decision' value='{dec}'>"
            "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
            f"{dec.capitalize()}</button></form> "
            for dec in VALID_INBOX_TRIAGE_DECISIONS
        )
        rows.append(
            f"<tr><td><code>{iid}</code></td><td>{html.escape(str(it['kind']))}</td>"
            f"<td>{html.escape(str(it['sender']))}</td><td><strong>{html.escape(str(it['topic']))}"
            f"</strong><br><small>{html.escape(str(it['detail']))}</small></td>"
            f"<td><span class='zcg-chip'>{st}</span></td><td>{btns}</td></tr>"
        )
    tbl = (
        "<table class='zcg-table' aria-label='Pending portal requests'><thead><tr><th>ID</th>"
        "<th>Kind</th><th>Sender / Peer</th><th>Topic &amp; Note</th><th>Status</th>"
        f"<th>Triage</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        if rows
        else "<p><small>0 requests in local mailbox (.zcg/runtime/portal/).</small></p>"
    )
    if view_mode == "workspace":
        return (
            f"<section class='zcg-card' id='zcg-inbox-stage'><div class='zcg-card__header'>"
            f"<h3>{render_icon('globe')} External Mailbox</h3>"
            f"<span class='zcg-badge'>Pending: {int(box['pending_count'])} · Total: "
            f"{int(box['total_count'])}</span></div>"
            f"<p class='zcg-muted-note'>Exposure: <code>{html.escape(exp.mode)}</code> · "
            "Configure public visibility inside <code>/admin</code>.</p>"
            f"{tbl}</section>"
        )
    exp_form = (
        f"<form class='zcg-tabs' method='post' action='{pfx}/exposure' "
        f"data-zcg-post='{pfx}/exposure' data-zcg-target='#zcg-inbox-stage'>"
        f"<input type='hidden' name='view_mode' value='{vm_h}'>"
        f"<label>Public Portal Mode <select name='mode' aria-label='Exposure mode'>{opts}</select></label>"  # noqa: E501
        f"<label>Public Status Banner <input type='text' name='availability_note' value='{note_h}' "
        "placeholder='Optional banner (e.g. Open for B2B advisory)' aria-label='Availability status'></label>"  # noqa: E501
        "<button type='submit' class='zcg-btn zcg-btn--sm'>Apply Exposure State</button></form>"
    )
    mode_guide = (
        "<ul class='zcg-muted-note' style='margin:0.55rem 0;'>"
        "<li><strong>Disabled</strong>: <code>/portal</code> returns <code>503</code> to outsiders "
        "and hides <code>Public Web</code> + <code>Env</code> switcher.</li>"
        "<li><strong>Mailbox Only</strong>: accepts local messages/handshakes in "
        "<code>.zcg/runtime/portal/</code> while offline.</li>"
        "<li><strong>Trusted Circles (R1/R2)</strong>: requires OIDC sign-in (ideal for private CV dossiers).</li>"  # noqa: E501
        "<li><strong>Online &amp; Available</strong>: opens public <code>R0</code> <code>/portal</code>, "  # noqa: E501
        "enables <code>DEV | PRO</code> stage testing, and delegates to your Root 0 hub.</li></ul>"
    )
    prev_btn = "<a class='zcg-btn zcg-btn--secondary zcg-btn--sm' href='/portal?format=html' target='_blank' rel='noopener noreferrer'>Preview Local /portal ↗</a>"  # noqa: E501
    if view_mode == "admin":
        facets_s = ", ".join(f["pillar"] for f in exp.public_facets) or "none"
        return (
            f"<section class='zcg-card' id='zcg-inbox-stage'><div class='zcg-card__header'>"
            f"<h3>{render_icon('globe')} Public Exposure</h3><div class='zcg-tabs'>"
            f"<span class='zcg-badge'>Mode: {html.escape(exp.mode)} · Mailbox: "
            f"{int(box['pending_count'])} pending / {int(box['total_count'])} total</span>"
            f"{prev_btn}</div></div><p class='zcg-muted-note'>Controls whether this node's public "
            "website (<code>/portal</code>) and inbound contact queue are open or strictly closed.</p>"  # noqa: E501
            f"{exp_form}{mode_guide}<p class='zcg-muted-note'>Active public facets: "
            f"<code>{html.escape(facets_s)}</code> · Triage incoming items in Workspace "
            "<code>External Mailbox</code>.</p></section>"
        )
    return (
        f"<section class='zcg-card' id='zcg-inbox-stage'><div class='zcg-card__header'>"
        f"<h3>{render_icon('globe')} Public Exposure &amp; External Mailbox</h3>"
        f"<span class='zcg-badge'>Mode: {html.escape(exp.mode)} · Pending: "
        f"{int(box['pending_count'])}</span></div>{exp_form}{tbl}</section>"
    )


def _extract_req_map(req: Request) -> Mapping[str, Any]:
    if "urlencoded" in req.content_type.lower():
        return req.form()
    if req.body.strip() and isinstance(parsed := req.json(), Mapping):
        return parsed
    return {}


def create_portal_inbox_router(
    workspace_dir: Path,
    *,
    policy: SurfaceAccessPolicy | None = None,
    prefix: str = "/api/modules/portal-inbox",
) -> APIRouter:
    """Create R3-guarded Cockpit APIRouter for local exposure control and mailbox triage."""
    ws = workspace_dir.resolve()
    clean_pfx = prefix.rstrip("/") or "/api/modules/portal-inbox"
    router = APIRouter(prefix=clean_pfx, tags=("portal-inbox",))

    def _require_r3(req: Request) -> None:
        if resolve_request_ring(req, policy) != "R3":
            raise WebAppError(
                "Inspecting or triaging local portal mailbox requires R3 operator authority",
                error_code="R3_OPERATOR_REQUIRED",
                http_status=int(HTTPStatus.FORBIDDEN),
                severity=ErrorSeverity.WARNING,
            )

    def _snapshot_response(
        req: Request, view_mode: str = "", *, refresh_shell: bool = False
    ) -> WebResponse:
        m_doc = load_node_manifest(ws) if (ws / NODE_MANIFEST_REL_PATH).is_file() else {}
        exp, box = parse_public_exposure_spec(m_doc), inspect_portal_mailbox(ws)
        eff_vm = (view_mode or req.query("mode", "")).strip().lower()
        frag = _render_inbox_panel_html(exp, box, clean_pfx, eff_vm)
        data = {"exposure": {"mode": exp.mode, "availability_note": exp.availability_note, "public_facets": list(exp.public_facets)}, "mailbox": box}  # fmt: skip  # noqa: E501
        hdrs = build_swap_response_headers(refresh=True) if refresh_shell else None
        return respond(req, html_fragment=frag, data=data, headers=hdrs)

    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="Inspect R3 mailbox & exposure")
    def get_inbox(req: Request) -> WebResponse:
        _require_r3(req)
        return _snapshot_response(req)

    @router.post("/exposure", channel=DeliveryChannel.SWAP_SYNC, summary="Set local exposure mode")
    def set_exposure(req: Request) -> WebResponse:
        _require_r3(req)
        pl = _extract_req_map(req)
        try:
            update_public_exposure_mode(
                ws, mode=str(pl.get("mode") or ""),
                availability_note=str(pl.get("availability_note") or ""),
            )  # fmt: skip
        except ValueError as exc:
            raise WebAppError(
                str(exc), error_code=str(exc).partition(":")[0] or "INVALID_EXPOSURE_UPDATE",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY), action=ErrorAction.FIX_INPUT,
            ) from exc  # fmt: skip
        return _snapshot_response(req, str(pl.get("view_mode") or ""), refresh_shell=True)

    @router.post("/triage", channel=DeliveryChannel.SWAP_SYNC, summary="Triage mailbox request")
    def post_triage(req: Request) -> WebResponse:
        _require_r3(req)
        pl = _extract_req_map(req)
        try:
            triage_portal_mailbox_item(
                ws, item_id=str(pl.get("item_id") or ""), decision=str(pl.get("decision") or "")
            )
        except ValueError as exc:
            raise WebAppError(
                str(exc), error_code=str(exc).partition(":")[0] or "INVALID_INBOX_TRIAGE",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY), action=ErrorAction.FIX_INPUT,
            ) from exc  # fmt: skip
        return _snapshot_response(req, str(pl.get("mode") or ""))

    return router
