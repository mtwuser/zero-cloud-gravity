"""Composable Node Admin APIRouter (/api/modules/capabilities) for modular capability toggles.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from pathlib import Path
from typing import Any

from zcg.cockpit.ops.metrics_studio import render_cli_transparency_hint
from zcg.governance.policy.module_registry import (
    reset_node_capabilities_default,
    resolve_effective_workspace_modules,
    resolve_node_capability_matrix,
    set_node_capability_enabled,
)
from zcg.governance.workspace.surface_mutations import commit_scoped_workspace_paths
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.auth.surface_access import SurfaceAccessPolicy
from zcg.web.capabilities.appearance import resolve_request_ring
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import Request, WebResponse, respond
from zcg.web.http.router import APIRouter

_CONFLICT_CODES: frozenset[str] = frozenset({"INDEX_HAS_STAGED_FILES", "NOTHING_TO_COMMIT"})


def _extract_req_dict(req: Request) -> dict[str, Any]:
    if "urlencoded" in req.content_type.lower():
        return dict(req.form())
    if not req.body.strip():
        return {}
    parsed = req.json()
    if not isinstance(parsed, Mapping):
        raise WebAppError(
            "Capability request body must be a JSON object",
            error_code="INVALID_CAPABILITY_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    return dict(parsed)


def _render_capability_row(row: Mapping[str, Any], prefix: str, crud_title: str) -> str:
    mod_id = str(row["module_id"])
    mod_q = html.escape(mod_id, quote=True)
    title = crud_title if (mod_id == "crud" and crud_title) else str(row["title"])
    slots = [str(s) for s in row.get("slots", ()) if s != "admin"]
    slot_badges = " ".join(
        "<span class='zcg-badge'>"
        f"{'Workspace (/)' if s == 'workspace' else 'Public (/portal)'}</span>"
        for s in slots
    )
    p_state = str(row["policy_state"])
    reason_h = html.escape(str(row["policy_reason"]), quote=True)
    if p_state == "mandatory":
        pol_html = f"<span class='zcg-chip' title='{reason_h}'>🔒 Mandatory</span>"
    elif p_state == "forbidden":
        pol_html = f"<span class='zcg-chip' title='{reason_h}'>⛔ Blocked</span>"
    else:
        pol_html = "<span class='zcg-chip'>Optional</span>"
    is_on = bool(row["enabled"])
    st_html = "🟢 Active" if is_on else "⚪ Inactive"
    if row["can_toggle"]:
        next_val = "0" if is_on else "1"
        btn_lbl = "Disable" if is_on else "Enable"
        btn_cls = "zcg-btn zcg-btn--secondary zcg-btn--sm" if is_on else "zcg-btn zcg-btn--sm"
        act_html = (
            f"<form method='post' action='{prefix}/toggle' data-zcg-post='{prefix}/toggle' "
            "data-zcg-target='#zcg-capabilities-panel' style='display:inline;'>"
            f"<input type='hidden' name='module_id' value='{mod_q}'>"
            f"<input type='hidden' name='enabled' value='{next_val}'>"
            f"<button type='submit' class='{btn_cls}'>{btn_lbl}</button></form>"
        )
    else:
        act_html = f"<small class='zcg-muted-note'>{html.escape(str(row['policy_reason']))}</small>"
    return (
        f"<tr data-capability-row='{mod_q}'>"
        f"<td><strong>{html.escape(title)}</strong><br>"
        f"<small class='zcg-muted-note'>{html.escape(str(row['purpose']))}</small></td>"
        f"<td>{slot_badges}</td><td>{pol_html}</td><td>{st_html}</td><td>{act_html}</td></tr>"
    )


def _render_capabilities_panel_html(
    matrix: list[dict[str, Any]],
    *,
    prefix: str,
    crud_title: str = "",
    notice_html: str = "",
) -> str:
    active_n = sum(1 for r in matrix if r["enabled"])
    has_override = any(bool(r.get("has_custom_override")) for r in matrix)
    rows_html = "".join(_render_capability_row(r, prefix, crud_title) for r in matrix)
    reset_btn = (
        f"<form method='post' action='{prefix}/toggle' data-zcg-post='{prefix}/toggle' "
        "data-zcg-target='#zcg-capabilities-panel' style='display:inline;'>"
        "<input type='hidden' name='action' value='reset'>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
        "Reset to Archetype Defaults</button></form>"
        if has_override
        else ""
    )
    commit_form = (
        f"<form method='post' action='{prefix}/commit' data-zcg-post='{prefix}/commit' "
        "data-zcg-target='#zcg-cap-commit-out' class='zcg-tabs' style='margin-top:0.75rem;'>"
        "<input name='commit_message' value='chore(node): update enabled workspace capabilities' "
        "aria-label='Conventional commit message' required>"
        "<button type='submit' class='zcg-btn zcg-btn--secondary zcg-btn--sm'>"
        "Commit Capability Config</button></form>"
        "<div id='zcg-cap-commit-out' style='margin-top:0.45rem;' aria-live='polite'></div>"
        if has_override
        else ""
    )
    cli_hint = render_cli_transparency_hint(
        ("system/zcg-node.json",),
        ("zcg status .", "zcg check-env-promotion . --to-env pro"),
    )
    return (
        "<div id='zcg-capabilities-panel'><section class='zcg-card' data-zcg-capabilities>"
        "<div class='zcg-card__header'><h3>Node Capabilities &amp; Surface Activation</h3>"
        f"<div class='zcg-tabs'><span class='zcg-badge'>Active: {active_n}/{len(matrix)}</span>"
        f"{reset_btn}</div></div>"
        "<p class='zcg-muted-note'>Enable only the capabilities this node needs. Disabled "
        "capabilities disappear immediately from <code>Workspace (/)</code> and "
        "<code>Public (/portal)</code> without restarting the daemon.</p>"
        f"{notice_html}"
        "<table class='zcg-table' aria-label='Node modular capabilities'>"
        "<thead><tr><th>Capability</th><th>Surfaces</th><th>Policy</th>"
        f"<th>Status</th><th>Action</th></tr></thead><tbody>{rows_html}</tbody></table>"
        f"{commit_form}{cli_hint}</section></div>"
    )


def create_capability_router(
    workspace_dir: Path,
    *,
    view_archetype: str = "",
    default_modules: Sequence[str] = (),
    crud_title: str = "",
    parent_dir: Path | None = None,
    policy: SurfaceAccessPolicy | None = None,
    prefix: str = "/api/modules/capabilities",
) -> APIRouter:
    """Create R3-guarded APIRouter for inspecting and toggling node Capability Modules."""
    ws = workspace_dir.resolve()
    clean_pfx = prefix.rstrip("/") or "/api/modules/capabilities"
    router = APIRouter(prefix=clean_pfx, tags=("capabilities",))

    def _require_r3(req: Request) -> None:
        if resolve_request_ring(req, policy) != "R3":
            raise WebAppError(
                "Managing node capabilities requires R3 operator authority",
                error_code="R3_OPERATOR_REQUIRED",
                http_status=int(HTTPStatus.FORBIDDEN),
                severity=ErrorSeverity.WARNING,
            )

    def _snapshot(req: Request, notice: str = "") -> WebResponse:
        matrix = resolve_node_capability_matrix(
            ws,
            view_archetype=view_archetype,
            default_modules=default_modules,
            parent_dir=parent_dir,
        )
        eff = list(
            resolve_effective_workspace_modules(
                ws,
                view_archetype=view_archetype,
                default_modules=default_modules,
                parent_dir=parent_dir,
            )
        )
        frag = _render_capabilities_panel_html(
            matrix, prefix=clean_pfx, crud_title=crud_title, notice_html=notice
        )
        return respond(
            req,
            html_fragment=frag,
            data={"enabled_modules": eff, "capabilities": matrix},
        )

    @router.get("", channel=DeliveryChannel.SWAP_SYNC, summary="Inspect node capability matrix")
    def list_capabilities(req: Request) -> WebResponse:
        _require_r3(req)
        return _snapshot(req)

    @router.post(
        "/toggle", channel=DeliveryChannel.SWAP_SYNC, summary="Enable, disable, or reset capability"
    )
    def toggle_capability(req: Request) -> WebResponse:
        _require_r3(req)
        pl = _extract_req_dict(req)
        try:
            if str(pl.get("action") or "").strip().lower() == "reset":
                reset_node_capabilities_default(
                    ws,
                    view_archetype=view_archetype,
                    default_modules=default_modules,
                    parent_dir=parent_dir,
                )
                note = "<div class='zcg-alert'>Restored archetype default capabilities.</div>"
            else:
                raw_en = str(pl.get("enabled") or "").strip().lower()
                is_on = raw_en in ("1", "true", "yes", "on")
                res = set_node_capability_enabled(
                    ws,
                    module_id=str(pl.get("module_id") or ""),
                    enabled=is_on,
                    view_archetype=view_archetype,
                    default_modules=default_modules,
                    parent_dir=parent_dir,
                )
                st_lbl = "Enabled" if res["enabled"] else "Disabled"
                m_h = html.escape(res["module_id"])
                note = f"<div class='zcg-alert'>{st_lbl} capability <code>{m_h}</code>.</div>"
        except ValueError as exc:
            code = str(exc).partition(":")[0] or "INVALID_CAPABILITY_TOGGLE"
            raise WebAppError(
                str(exc),
                error_code=code,
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            ) from exc
        return _snapshot(req, notice=note)

    @router.post(
        "/commit", channel=DeliveryChannel.SWAP_SYNC, summary="Commit system/zcg-node.json"
    )
    def commit_capabilities(req: Request) -> WebResponse:
        _require_r3(req)
        pl = _extract_req_dict(req)
        try:
            res = commit_scoped_workspace_paths(
                ws,
                rel_paths=("system/zcg-node.json",),
                commit_message=str(pl.get("commit_message") or ""),
            )
        except ValueError as exc:
            msg = str(exc)
            code = msg.partition(":")[0] or "COMMIT_REJECTED"
            st = HTTPStatus.CONFLICT if code in _CONFLICT_CODES else HTTPStatus.UNPROCESSABLE_ENTITY
            raise WebAppError(msg, error_code=code, http_status=int(st)) from exc
        sha_h = html.escape(res["commit_sha"])
        return respond(
            req,
            html_fragment=f"<div class='zcg-alert'>Committed <code>{sha_h}</code>.</div>",
            data=res,
        )

    return router
