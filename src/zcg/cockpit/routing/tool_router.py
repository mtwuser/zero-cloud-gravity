"""Composable Cockpit APIRouter (/api/tools) for 3-Origin Skills Studio & .zcg/tools/ Sandboxes.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Any, NoReturn

from zcg.cockpit.ops.tool_studio import render_commit_skill_form, render_tools_and_skills_html
from zcg.core.manifests import load_node_manifest
from zcg.governance.policy.model_currency import resolve_node_agent_guidance
from zcg.governance.runtime.skill_auditor import audit_skills_sovereign_profile
from zcg.governance.runtime.tool_catalog import (
    DEFAULT_ISOLATED_TOOL_CATALOG,
    IsolatedToolDescriptor,
    resolve_tool_node_relevance,
)
from zcg.governance.runtime.tool_isolation import (
    DecisionEvaluationRequest,
    deprovision_isolated_tool_manifest,
    provision_isolated_tool_manifest,
    resolve_tool_runtime_dir,
    run_isolated_tool_inspection,
)
from zcg.governance.workspace.onboarding_studio import (
    discard_markdown_draft,
    load_markdown_draft,
    save_markdown_draft,
)
from zcg.governance.workspace.surface_mutations import (
    commit_scoped_workspace_paths,
    delete_node_skill,
    inspect_workspace_skills_studio,
    is_workspace_path_dirty,
    save_node_skill_verified,
)
from zcg.providers.gemini_decisions import evaluate_node_decisions
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import JSON_CONTENT_TYPE, Request, WebResponse, respond
from zcg.web.http.router import APIRouter

_CONFLICT_CODES: frozenset[str] = frozenset(
    {"STALE_SKILL_REVISION", "INDEX_HAS_STAGED_FILES", "NOTHING_TO_COMMIT"}
)


def _extract_body_dict(req: Request) -> dict[str, Any]:
    if "application/x-www-form-urlencoded" in req.content_type.lower():
        return dict(req.form())
    if not req.body.strip():
        return {}
    parsed = req.json()
    if not isinstance(parsed, Mapping):
        raise WebAppError(
            "Request body must be a JSON object",
            error_code="INVALID_TOOLS_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    return dict(parsed)


def _raise_domain_error(exc: ValueError, fallback_code: str) -> NoReturn:
    msg = str(exc)
    code = msg.partition(":")[0] or fallback_code
    st = HTTPStatus.CONFLICT if code in _CONFLICT_CODES else HTTPStatus.UNPROCESSABLE_ENTITY
    raise WebAppError(msg, error_code=code, http_status=int(st)) from exc


def _require_tool_id(req: Request, catalog: Mapping[str, IsolatedToolDescriptor]) -> str:
    tid = req.path_params.get("tool_id", "")
    if tid not in catalog:
        raise WebAppError(
            f"Unknown isolated tool {tid!r}",
            error_code="TOOL_NOT_FOUND",
            http_status=int(HTTPStatus.NOT_FOUND),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    return tid


def _parse_decision_items(raw_items: Any) -> list[DecisionEvaluationRequest]:
    if not raw_items:
        return [
            DecisionEvaluationRequest(
                "gate-01", "yes_no", "env-gate", "Are node verification gates green?", (), 0.92
            )
        ]
    if not isinstance(raw_items, list) or not all(isinstance(x, Mapping) for x in raw_items):
        raise ValueError("items must be a JSON array of decision request objects")
    return [
        DecisionEvaluationRequest(
            item_id=str(it.get("item_id") or f"item-{idx}"),
            task_kind=str(it.get("task_kind") or "yes_no"),
            use_case=str(it.get("use_case") or "env-gate"),
            prompt=str(it.get("prompt") or ""),
            choices=tuple(str(c) for c in (it.get("choices") or ())),
            prior_score=float(it.get("prior_score", 0.5)),
        )
        for idx, it in enumerate(raw_items, start=1)
    ]


def create_tool_stack_router(
    workspace_dir: Path,
    *,
    parent_dir: Path | None = None,
    catalog: Mapping[str, IsolatedToolDescriptor] | None = None,
) -> APIRouter:
    """Create composable zcg.web APIRouter (/api/tools) for Skill Studio & .zcg/tools/."""
    ws = workspace_dir.resolve()
    eff_catalog = DEFAULT_ISOLATED_TOOL_CATALOG if catalog is None else catalog
    router = APIRouter(prefix="/api/tools", tags=("tool-stack",))

    def _tool_items() -> list[dict[str, Any]]:
        man = load_node_manifest(ws)
        return [
            {
                **spec.to_dict(),
                "provisioned": (resolve_tool_runtime_dir(ws, tid) / "tool-runtime.json").is_file(),
                "recommended": resolve_tool_node_relevance(tid, man),
            }
            for tid, spec in eff_catalog.items()
        ]

    def _build_studio_payload(skill_slug: str, action: str) -> dict[str, Any]:
        studio = inspect_workspace_skills_studio(ws, skill_slug=skill_slug, parent_dir=parent_dir)
        sel = studio.get("selected_skill")
        if isinstance(sel, dict) and sel.get("editable"):
            sel["is_dirty"] = is_workspace_path_dirty(ws, str(sel["canonical_rel_path"]))
        draft_key = ""
        if action == "new":
            draft_key = "skill:custom-node-skill"
        elif action == "duplicate" and isinstance(sel, dict):
            draft_key = f"skill:{studio['layer_id']}-{sel['slug']}"
        elif isinstance(sel, dict) and sel.get("editable"):
            draft_key = f"skill:{sel['slug']}"
        guidance = resolve_node_agent_guidance(load_node_manifest(ws))
        payload: dict[str, Any] = {**studio, "agent_guidance": guidance}
        if draft_key:
            payload["draft"] = load_markdown_draft(ws, draft_key)
        return payload

    @router.get("", summary="List Skill Trust Studio, active skills, and isolated tool-stack")
    def list_tools(request: Request) -> WebResponse:
        audit = audit_skills_sovereign_profile(ws, parent_dir=parent_dir)
        act_q = request.query("action", "").strip().lower()
        mode_q = request.query("mode", "").strip().lower()
        studio = _build_studio_payload(request.query("skill", ""), act_q)
        items = _tool_items()
        return respond(
            request,
            html_fragment=render_tools_and_skills_html(studio, items, action=act_q, mode=mode_q),
            data={
                "tools": items,
                "skill_trust_score": audit["trust_score"],
                "skill_audit_tiers": audit["tiers"],
                "skills": studio["skills"],
                "selected_skill": studio["selected_skill"],
                "agent_guidance": studio["agent_guidance"],
            },
        )

    @router.post(
        "/skills/draft", channel=DeliveryChannel.SWAP_SYNC, summary="Auto-save skill draft"
    )
    def save_skill_draft(request: Request) -> WebResponse:
        body = _extract_body_dict(request)
        try:
            saved = save_markdown_draft(
                ws,
                draft_key=str(body.get("draft_key") or ""),
                content=str(body.get("content") or ""),
                rel_path=str(body.get("rel_path") or ""),
            )
        except ValueError as exc:
            _raise_domain_error(exc, "INVALID_MARKDOWN_DRAFT")
        frag = f"<div class='zcg-alert'>Draft saved ({saved['line_count']} lines).</div>"
        return respond(request, html_fragment=frag, data=saved)

    @router.post(
        "/skills/draft/discard", channel=DeliveryChannel.SWAP_SYNC, summary="Discard skill draft"
    )
    def discard_skill_draft(request: Request) -> WebResponse:
        body = _extract_body_dict(request)
        draft_key = str(body.get("draft_key") or request.query("draft_key", "")).strip()
        res = discard_markdown_draft(ws, draft_key)
        slug_q = str(body.get("skill_slug") or request.query("skill", "")).strip()
        act_q = str(body.get("action") or request.query("action", "")).strip().lower()
        mode_q = str(body.get("mode") or request.query("mode", "")).strip().lower()
        studio = _build_studio_payload(slug_q, act_q)
        alert = "<div class='zcg-alert'>Discarded unapplied draft.</div>"
        frag = render_tools_and_skills_html(
            studio, _tool_items(), action=act_q, mode=mode_q, banner_html=alert
        )
        return respond(request, html_fragment=frag, data=res)

    @router.post("/skills/save", channel=DeliveryChannel.SWAP_SYNC, summary="Audit and save skill")
    def save_skill(request: Request) -> WebResponse:
        body = _extract_body_dict(request)
        try:
            saved = save_node_skill_verified(
                ws,
                skill_slug=str(body.get("skill_slug") or ""),
                content=str(body.get("content") or ""),
                expected_sha256=str(body.get("expected_sha256") or ""),
                parent_dir=parent_dir,
            )
        except ValueError as exc:
            _raise_domain_error(exc, "SKILL_AUDIT_REJECTED")
        saved_slug = str(saved["slug"])
        discard_markdown_draft(ws, "skill:custom-node-skill")
        discard_markdown_draft(ws, f"skill:{saved_slug}")
        p_h = html.escape(saved["canonical_rel_path"])
        if str(body.get("commit_now") or "") == "1":
            msg = str(body.get("commit_message") or "").strip() or (
                f"feat(skills): update {saved_slug}"
            )
            try:
                com = commit_scoped_workspace_paths(
                    ws, rel_paths=(str(saved["canonical_rel_path"]),), commit_message=msg
                )
            except ValueError as exc:
                _raise_domain_error(exc, "COMMIT_REJECTED")
            sha_h = html.escape(str(com["commit_sha"]))
            frag = (
                f"<div class='zcg-alert'>Verified &amp; saved <code>{p_h}</code> "
                f"(0-drift) and committed <code>{sha_h}</code>.</div>"
            )
            return respond(request, html_fragment=frag, data={**saved, "commit": com})
        c_form = render_commit_skill_form(saved_slug)
        frag = (
            f"<div class='zcg-alert'>Verified &amp; saved <code>{p_h}</code> (0-drift).</div>"
            f"<div class='zcg-dirty-banner'><span>🟡 <code>{p_h}</code> saved on disk "
            f"(uncommitted in Git)</span>{c_form}</div>"
        )
        return respond(request, html_fragment=frag, data=saved)

    @router.post("/skills/delete", channel=DeliveryChannel.SWAP_SYNC, summary="Delete node skill")
    def remove_skill(request: Request) -> WebResponse:
        body = _extract_body_dict(request)
        try:
            deleted = delete_node_skill(ws, skill_slug=str(body.get("skill_slug") or ""))
        except ValueError as exc:
            _raise_domain_error(exc, "SKILL_DELETE_REJECTED")
        mode_q = str(body.get("mode") or request.query("mode", "")).strip().lower()
        studio = inspect_workspace_skills_studio(ws, parent_dir=parent_dir)
        guidance = resolve_node_agent_guidance(load_node_manifest(ws))
        sl_h = html.escape(deleted["slug"])
        alert = f"<div class='zcg-alert'>Deleted node skill <code>{sl_h}</code>.</div>"
        frag = render_tools_and_skills_html(
            {**studio, "agent_guidance": guidance}, _tool_items(), mode=mode_q, banner_html=alert
        )
        return respond(request, html_fragment=frag, data=deleted)

    @router.post("/skills/commit", channel=DeliveryChannel.SWAP_SYNC, summary="Commit node skill")
    def commit_skill(request: Request) -> WebResponse:
        body = _extract_body_dict(request)
        slug = str(body.get("skill_slug") or "").strip()
        lid = str(inspect_workspace_skills_studio(ws, parent_dir=parent_dir)["layer_id"])
        rel_p = str(body.get("rel_path") or f"templates/{lid}/skills/{slug}/SKILL.md")
        try:
            res = commit_scoped_workspace_paths(
                ws, rel_paths=(rel_p,), commit_message=str(body.get("commit_message") or "")
            )
        except ValueError as exc:
            _raise_domain_error(exc, "COMMIT_REJECTED")
        sha_h = html.escape(res["commit_sha"])
        frag = f"<div class='zcg-alert'>Committed <code>{sha_h}</code>.</div>"
        return respond(request, html_fragment=frag, data=res)

    @router.post("/{tool_id}/provision", channel=DeliveryChannel.SWAP_SYNC)
    def provision_tool(request: Request) -> WebResponse:
        tid = _require_tool_id(request, eff_catalog)
        doc = provision_isolated_tool_manifest(ws, tid, parent_dir=parent_dir, catalog=eff_catalog)
        tid_h = html.escape(tid)
        frag = (
            "<div class='zcg-alert'>Provisioned isolated tool runtime "
            f"<code>{tid_h}</code> under <code>.zcg/tools/{tid_h}/</code>.</div>"
        )
        return respond(request, html_fragment=frag, data=doc)

    @router.post("/{tool_id}/deprovision", channel=DeliveryChannel.SWAP_SYNC)
    def deprovision_tool(request: Request) -> WebResponse:
        tid = _require_tool_id(request, eff_catalog)
        doc = deprovision_isolated_tool_manifest(ws, tid, catalog=eff_catalog)
        mode_q = request.query("mode", "").strip().lower()
        studio = inspect_workspace_skills_studio(ws, parent_dir=parent_dir)
        alert = f"<div class='zcg-alert'>Disabled tool <code>{html.escape(tid)}</code>.</div>"
        frag = render_tools_and_skills_html(studio, _tool_items(), mode=mode_q, banner_html=alert)
        return respond(request, html_fragment=frag, data=doc)

    @router.get("/{tool_id}/inspect", channel=DeliveryChannel.SWAP_SYNC)
    def inspect_tool(request: Request) -> WebResponse:
        tid = _require_tool_id(request, eff_catalog)
        info = run_isolated_tool_inspection(ws, tid, parent_dir=parent_dir, catalog=eff_catalog)
        det = "".join(f"<li><code>{html.escape(d)}</code></li>" for d in info["details"])
        head_h = html.escape(info["headline"])
        frag = f"<div class='zcg-card'><strong>{head_h}</strong><ul>{det}</ul></div>"
        return respond(request, html_fragment=frag, data=info)

    @router.get("/skill-auditor/sarif", summary="Export zcg-skill-auditor SARIF 2.1.0 report")
    def export_sarif(_request: Request) -> WebResponse:
        report = audit_skills_sovereign_profile(ws, parent_dir=parent_dir)
        return WebResponse(
            int(HTTPStatus.OK),
            JSON_CONTENT_TYPE,
            json.dumps(report).encode("utf-8"),
            DeliveryChannel.ISLAND_SYNC,
        )

    @router.post("/decisions/evaluate", summary="Evaluate Gemini Decisions or LiteRT batch")
    def evaluate_decisions(request: Request) -> WebResponse:
        payload = request.json() if request.body.strip() else {}
        if not isinstance(payload, Mapping):
            raise WebAppError(
                "Decision evaluation body must be a JSON object",
                error_code="INVALID_DECISIONS_PAYLOAD",
                http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        try:
            reqs = _parse_decision_items(payload.get("items"))
            result = evaluate_node_decisions(
                ws,
                reqs,
                parent_dir=parent_dir,
                shared_input=str(payload.get("shared_input") or ""),
                offline_override=bool(payload.get("offline_override", False)),
            )
        except ValueError as exc:
            raise WebAppError(
                str(exc),
                error_code="INVALID_DECISION_REQUEST",
                http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            ) from exc
        return WebResponse(
            int(HTTPStatus.OK),
            JSON_CONTENT_TYPE,
            json.dumps(result).encode("utf-8"),
            DeliveryChannel.ISLAND_SYNC,
        )

    return router
