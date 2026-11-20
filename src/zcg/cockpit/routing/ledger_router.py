"""Cohesive 1:1 Sovereign Node Work Ledger, Kanban Board, Work Inbox & 1-Hop Router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import html
import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.ops import mesh_studio
from zcg.cockpit.ops.metrics_studio import render_metrics_view_html
from zcg.cockpit.views import work_board, work_views
from zcg.core.constants import NODE_MANIFEST_REL_PATH, VALID_TRACKER_FILES
from zcg.core.domain import generate_identifier, is_kebab_id
from zcg.core.manifests import load_node_manifest
from zcg.core.markdown_scan import scan_markdown_checkboxes
from zcg.governance.policy.authority import append_tracker_line
from zcg.governance.policy.handoff import check_handoff_symmetry
from zcg.governance.policy.mesh_relations import (
    evaluate_node_exchange_grant,
    normalize_workspace_scope,
    resolve_exchange_target_dir,
    resolve_node_relation_grants,
)  # fmt: skip
from zcg.governance.work import work_inbox, work_trackers, workflows
from zcg.governance.work.work_metrics import collect_workspace_metrics
from zcg.governance.workspace import surface_mutations
from zcg.topology.exposure import is_public_portal_enabled
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.http.channels import DeliveryChannel, Tier, build_swap_response_headers
from zcg.web.http.request import Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ops.resilience import DeferredJobQueue
from zcg.web.ui.components import render_card, render_progress_bar, render_table
from zcg.web.ui.templates import SafeHTML

DEFAULT_WORK_LEDGER_PREFIX: Final[str] = "/api/modules/work-ledger"
_COMMIT_CONFLICTS: frozenset[str] = frozenset(
    {"INDEX_HAS_STAGED_FILES", "NOTHING_TO_COMMIT", "WORK_REQUEST_ALREADY_TRIAGED"}
)


def _raise_mutation_error(exc: ValueError, fallback_code: str) -> WebAppError:
    msg = str(exc)
    code = msg.partition(":")[0] or fallback_code
    if code == "MESH_RELATION_FORBIDDEN":
        st = HTTPStatus.FORBIDDEN
    elif code in _COMMIT_CONFLICTS:
        st = HTTPStatus.CONFLICT
    else:
        st = HTTPStatus.UNPROCESSABLE_ENTITY
    return WebAppError(msg, error_code=code, http_status=int(st))


def _dispatch_cross_node_exchange(
    ws: Path, *, mode: str, target: str, directive: str
) -> tuple[dict[str, Any], str]:
    req_verb = "delegate_work" if mode == "delegate" else "propose_work"
    grant = (
        evaluate_node_exchange_grant(ws, target_node=target, required_verb=req_verb)
        if (ws / NODE_MANIFEST_REL_PATH).is_file()
        else None
    )
    if mode == "delegate" and (grant is None or grant.relation_role == "governor"):
        res = workflows.delegate_directive_to_child(ws, child_layer=target, directive=directive)
        work_board.record_outbound_exchange_receipt(
            ws, target_node=target, mode="delegate", summary=directive
        )
        return res, f"<div class='zcg-alert'>Delegated to <code>{html.escape(target)}</code>.</div>"
    src_id = str(load_node_manifest(ws).get("layer_id") or ws.name)
    tdir = resolve_exchange_target_dir(ws, target)
    if tdir is None or not tdir.is_dir():
        raise ValueError(f"EXCHANGE_TARGET_NOT_FOUND: {target!r} is not a connected node")
    handoff = check_handoff_symmetry(ws, directive_text=directive, receiver_dir=tdir)
    norm_dir = handoff["normalized_text"]
    queued = work_inbox.enqueue_work_inbox_request(tdir, sender_node=src_id, summary=norm_dir)
    work_board.record_outbound_exchange_receipt(
        ws, target_node=target, mode=mode, summary=norm_dir, ref_path=queued["request_id"],
    )  # fmt: skip
    res = {
        "mode": mode, "source_node": src_id, "target_node": target,
        "request_id": queued["request_id"], "handoff_passed": handoff["passed"],
    }  # fmt: skip
    lbl = "Delegated task to" if mode == "delegate" else "Sent work request to"
    return res, f"<div class='zcg-alert'>{lbl} <code>{html.escape(target)}</code>.</div>"


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _extract_dict_payload(req: Request) -> dict[str, Any]:
    if "application/x-www-form-urlencoded" in req.content_type.lower():
        return dict(req.form())
    if not req.body:
        return {}
    parsed = req.json()
    if not isinstance(parsed, dict):
        raise WebAppError(
            "Work ledger payload must be a JSON object", error_code="INVALID_LEDGER_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST), severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )  # fmt: skip
    return parsed


def _collect_local_tasks_and_proposals(ws: Path) -> tuple[list[dict[str, str]], list[str]]:
    tasks = [
        {"tracker": trk, "state": it.state, "body": it.body}
        for trk in ("WORKTASK.md", "BACKLOG.md") if (trk_f := ws / trk).is_file()
        for it in scan_markdown_checkboxes(trk_f.read_text(encoding="utf-8"))
    ]  # fmt: skip
    prop_dir = ws / ".agents/proposals"
    proposals = [str(p.relative_to(prop_dir)) for p in sorted(prop_dir.rglob("*.md"))] if prop_dir.is_dir() else []  # noqa: E501  # fmt: skip
    return tasks, proposals


def _build_jobs_drawer(job_queue: DeferredJobQueue | None) -> tuple[list[dict[str, Any]], str]:
    jobs = (
        [{"task_id": r.task_id, "status": r.status.value, "progress": r.progress} for r in job_queue.records()]  # noqa: E501
        if job_queue is not None else []
    )  # fmt: skip
    tbl = render_table(
        columns=(("task_id", "Job ID"), ("status", "Status")), rows=jobs,
        empty_message="No background jobs queued.",
    ).value  # fmt: skip
    drawer = (
        "<details class='zcg-peer-channel' style='margin-top:0.75rem;'>"
        "<summary class='zcg-peer-channel__head'><span><strong>Background Jobs</strong></span>"
        f"<span class='zcg-badge'>{len(jobs)}</span></summary>"
        f"<div class='zcg-peer-channel__body'>{tbl}</div></details>"
    )
    return jobs, drawer


def _extract_posture_snapshot(node_doc: dict[str, Any]) -> tuple[int, int, str]:
    rep = node_doc.get("representation_context")
    nh = rep.get("node_health") if isinstance(rep, dict) else None
    dims = nh.get("dimensions") if isinstance(nh, dict) else None
    sec = dims.get("security_posture") if isinstance(dims, dict) else None
    sk = dims.get("skill_trust") if isinstance(dims, dict) else None
    return (
        int(sec.get("score", 100)) if isinstance(sec, dict) else 100,
        int(sk.get("score", 100)) if isinstance(sk, dict) else 100,
        str(nh.get("overall_state") or "OPTIMAL") if isinstance(nh, dict) else "OPTIMAL",
    )


def render_work_section_fragment(
    workspace_dir: Path, *, section: str = "dashboard",
    prefix: str = DEFAULT_WORK_LEDGER_PREFIX, scope_filter: str = "all",
    priority_filter: str = "all", query_filter: str = "", metrics_scope: str = "",
    ws_scope: str = "all", notice_html: str = "", job_queue: DeferredJobQueue | None = None,
) -> tuple[str, dict[str, Any]]:  # fmt: skip
    """Render one of the 5 governed WORK* views (dashboard/backlog/roadmaps/validations/metrics)."""
    ws, eff_sec = workspace_dir.resolve(), work_views.normalize_work_section(section)
    eff_ws, manifest = normalize_workspace_scope(ws_scope), load_node_manifest(ws)
    node_doc = _read_json_dict(ws / "surfaces/data/node_scope.json")
    net_doc = _read_json_dict(ws / "surfaces/data/network_scope.json")
    raw_ledger, raw_gates = node_doc.get("own_node_ledger"), net_doc.get("environment_gates")
    ledger = raw_ledger if isinstance(raw_ledger, dict) else {}
    gates = raw_gates if isinstance(raw_gates, dict) else {}
    tasks, proposals = _collect_local_tasks_and_proposals(ws)
    inbox, road_d, vali_d = (
        work_inbox.inspect_work_inbox(ws),
        work_trackers.inspect_roadmap_tracker(ws),
        work_trackers.inspect_validation_tracker(ws),
    )
    channels = work_board.collect_counterpart_work_channels(ws, net_doc)
    jobs, jobs_drawer = _build_jobs_drawer(job_queue)
    metrics_d: dict[str, Any] | None = None
    if eff_sec == "backlog":
        frag = work_views.render_backlog_view_html(
            prefix, tasks, notice_html=notice_html, priority_filter=priority_filter,
            query_filter=query_filter, ws_scope=eff_ws,
            tracker_dirty=surface_mutations.is_workspace_path_dirty(ws, "BACKLOG.md"),
        )  # fmt: skip
    elif eff_sec == "roadmaps":
        rm_trk = str(road_d.get("tracker_file") or "WORKROAD.md")
        frag = work_views.render_roadmaps_view_html(
            prefix, road_d, notice_html=notice_html, ws_scope=eff_ws,
            tracker_dirty=surface_mutations.is_workspace_path_dirty(ws, rm_trk),
        )  # fmt: skip
    elif eff_sec == "validations":
        pipe = str((manifest.get("git_governance") or {}).get("promotion_pipeline") or "")
        is_staged = pipe == "staged" or is_public_portal_enabled(manifest)
        frag = work_views.render_validations_view_html(
            prefix, vali_d, environment_gates=gates, show_promotion_gates=is_staged,
            notice_html=notice_html, ws_scope=eff_ws,
            tracker_dirty=surface_mutations.is_workspace_path_dirty(ws, "WORKVALI.md"),
        )  # fmt: skip
    elif eff_sec == "metrics":
        eff_m_scope = metrics_scope.strip().lower() or eff_ws
        metrics_d = collect_workspace_metrics(ws, scope=eff_m_scope)
        p_score, s_score, h_state = _extract_posture_snapshot(node_doc)
        frag = render_metrics_view_html(
            metrics_d, posture_score=p_score, skill_trust_score=s_score,
            health_state=h_state, prefix=prefix,
            layer_role=str(manifest.get("layer_role") or "project"),
        )  # fmt: skip
    else:
        tgt_sel_h = mesh_studio.render_quick_task_target_select_html(
            resolve_node_relation_grants(ws)
        )
        frag = work_views.render_dashboard_kanban_html(
            prefix, tasks, channels, inbox_items=inbox["items"], jobs_drawer_html=jobs_drawer,
            notice_html=notice_html, scope_filter=scope_filter, priority_filter=priority_filter,
            query_filter=query_filter, target_select_html=tgt_sel_h, ws_scope=eff_ws,
            tracker_dirty=surface_mutations.is_workspace_path_dirty(ws, "WORKTASK.md"),
        )  # fmt: skip
    payload: dict[str, Any] = {
        "capability": "work_ledger", "section": eff_sec, "own_node_ledger": ledger,
        "environment_gates": gates, "tasks": tasks, "work_inbox": inbox,
        "roadmaps": road_d, "validations": vali_d, "staged_proposals": proposals,
        "counterpart_channels": channels,
        "active_jobs": job_queue.active_count if job_queue is not None else 0, "jobs": jobs,
        **({"metrics": metrics_d} if metrics_d is not None else {}),
    }  # fmt: skip
    return frag, payload


def create_work_ledger_router(
    workspace_dir: Path, *, job_queue: DeferredJobQueue, prefix: str = DEFAULT_WORK_LEDGER_PREFIX,
) -> APIRouter:  # fmt: skip
    """Create a 1:1 Sovereign Node Work Ledger, Kanban, Work Inbox & 1-Hop APIRouter."""
    ws, router = workspace_dir.resolve(), APIRouter(prefix=prefix, tags=("work-ledger",))

    def _render_panel_snapshot(req: Request, notice_html: str = "") -> tuple[str, dict[str, Any]]:
        raw_sec, eff_ws = (
            req.query("section", "").strip(),
            normalize_workspace_scope(req.query("ws_scope", "")),
        )
        if raw_sec:
            return render_work_section_fragment(
                ws, section=raw_sec, prefix=prefix,
                scope_filter=req.query("scope", "all").strip().lower(),
                priority_filter=req.query("priority", "all").strip(),
                query_filter=req.query("q", "").strip(),
                metrics_scope=req.query("metrics_scope", "").strip().lower(),
                ws_scope=eff_ws, notice_html=notice_html, job_queue=job_queue,
            )  # fmt: skip
        _, payload = render_work_section_fragment(
            ws, prefix=prefix, ws_scope=eff_ws, job_queue=job_queue
        )
        _, jobs_drawer = _build_jobs_drawer(job_queue)
        board_s = work_board.render_work_board_and_channels_html(
            prefix, payload["tasks"], payload["counterpart_channels"],
            inbox_items=payload["work_inbox"]["items"],
            scope_filter=req.query("scope", "all").strip().lower(),
            priority_filter=req.query("priority", "all").strip(),
            query_filter=req.query("q", "").strip(),
        )  # fmt: skip
        card = render_card(title="Work Board", body=SafeHTML(notice_html + board_s + jobs_drawer))
        return f"<div id='zcg-work-ledger-panel'>{card.value}</div>", payload

    @router.get("", summary="Inspect sprint ledger, Kanban tasks, Work Inbox, and T2 jobs")
    def inspect_work_ledger(req: Request) -> WebResponse:
        frag, payload = _render_panel_snapshot(req)
        return respond(req, html_fragment=frag, data=payload)

    @router.post("/tasks", channel=DeliveryChannel.SWAP_SYNC, summary="Mutate, promote, or commit")
    def mutate_local_task(req: Request) -> WebResponse:
        data = _extract_dict_payload(req)
        act, tracker = str(data.get("action") or "add").strip().lower(), str(data.get("tracker") or "WORKTASK.md").strip()  # noqa: E501  # fmt: skip
        txt, ex_tgt = str(data.get("task_text") or "").strip(), str(data.get("exchange_target") or "").strip()  # noqa: E501  # fmt: skip
        if tracker not in VALID_TRACKER_FILES or not txt:
            st_422 = int(HTTPStatus.UNPROCESSABLE_ENTITY)
            raise WebAppError("Valid tracker and non-empty task_text required", error_code="INVALID_TASK_MUTATION", http_status=st_422)  # noqa: E501  # fmt: skip
        note = ""
        try:
            if act == "add" and ex_tgt:
                if not is_kebab_id(ex_tgt):
                    raise ValueError(f"INVALID_EXCHANGE_TARGET: {ex_tgt!r}")
                mg = next((g for g in resolve_node_relation_grants(ws) if g.target_node == ex_tgt), None)  # noqa: E501  # fmt: skip
                ex_mode = "delegate" if (mg and "delegate_work" in mg.allowed_verbs) else "propose"
                res, note = _dispatch_cross_node_exchange(ws, mode=ex_mode, target=ex_tgt, directive=txt)  # noqa: E501  # fmt: skip
            elif act == "add":
                append_tracker_line(ws, tracker, f"- [ ] {txt}", str(load_node_manifest(ws).get("layer_id") or ws.name))  # noqa: E501  # fmt: skip
                res = {"action": "add", "tracker": tracker, "added": txt}
            elif act == "promote":
                res = work_inbox.promote_backlog_item_to_todo(ws, task_query=txt)
            elif act == "claim":
                res = workflows.start_task_workflow(ws, task_query=txt, tracker=tracker)
            elif act == "complete":
                res = workflows.complete_task_workflow(ws, task_query=txt, tracker=tracker)
            elif act == "toggle":
                res = work_trackers.toggle_tracker_checkbox(
                    ws, tracker=tracker, task_query=txt, target_state=str(data.get("target_state") or "x"),  # noqa: E501
                )  # fmt: skip
            elif act == "commit":
                res = surface_mutations.commit_scoped_workspace_paths(ws, rel_paths=(tracker,), commit_message=txt)  # noqa: E501  # fmt: skip
            else:
                raise ValueError(f"UNSUPPORTED_TASK_ACTION: {act!r}")
        except ValueError as exc:
            raise _raise_mutation_error(exc, "TASK_MUTATION_REJECTED") from exc
        act_h, trk_h = html.escape(act), html.escape(tracker)
        note = note or f"<div class='zcg-alert'>Task action <code>{act_h}</code> applied on <code>{trk_h}</code>.</div>"  # noqa: E501  # fmt: skip
        frag, _ = _render_panel_snapshot(req, notice_html=note)
        return respond(req, html_fragment=frag, data=res)

    @router.post("/inbox", channel=DeliveryChannel.SWAP_SYNC, summary="Enqueue or triage inbox")
    def handle_work_inbox(req: Request) -> WebResponse:
        data = _extract_dict_payload(req)
        try:
            if str(data.get("action") or "").strip().lower() == "enqueue":
                res: dict[str, Any] = work_inbox.enqueue_work_inbox_request(
                    ws, sender_node=str(data.get("sender_node") or ""), summary=str(data.get("summary") or ""),  # noqa: E501
                    direction=str(data.get("direction") or "peer"), priority=str(data.get("priority") or "P1"),  # noqa: E501
                )  # fmt: skip
                note = "<div class='zcg-alert'>Enqueued incoming work request.</div>"
            else:
                res = work_inbox.triage_work_inbox_request(
                    ws, request_id=str(data.get("request_id") or ""), decision=str(data.get("decision") or ""),  # noqa: E501
                )  # fmt: skip
                note = f"<div class='zcg-alert'>Work request triaged (<code>{html.escape(str(res['decision']))}</code>).</div>"  # noqa: E501
        except ValueError as exc:
            raise _raise_mutation_error(exc, "INVALID_WORK_INBOX_OP") from exc
        frag, _ = _render_panel_snapshot(req, notice_html=note)
        return respond(req, html_fragment=frag, data=res)

    @router.post("/exchange", channel=DeliveryChannel.SWAP_SYNC, summary="1-hop delegate/propose")
    def exchange_cross_node_task(req: Request) -> WebResponse:
        data = _extract_dict_payload(req)
        mode, target, directive = (
            str(data.get("mode") or "propose").strip().lower(),
            str(data.get("target_node") or "").strip(), str(data.get("directive") or "").strip(),
        )  # fmt: skip
        if not is_kebab_id(target) or not directive:
            st_422 = int(HTTPStatus.UNPROCESSABLE_ENTITY)
            raise WebAppError("Valid kebab-case target_node and non-empty directive required", error_code="INVALID_EXCHANGE_TARGET", http_status=st_422)  # noqa: E501  # fmt: skip
        try:
            res, note = _dispatch_cross_node_exchange(ws, mode=mode, target=target, directive=directive)  # noqa: E501  # fmt: skip
        except ValueError as exc:
            raise _raise_mutation_error(exc, "EXCHANGE_REJECTED") from exc
        frag, _ = _render_panel_snapshot(req, notice_html=note)
        return respond(req, html_fragment=frag, data=res)

    @router.post("/jobs", summary="Register an idempotent T2 sprint background job")
    def register_work_job(req: Request) -> WebResponse:
        data = _extract_dict_payload(req)
        tid = str(data.get("task_id") or "").strip() or generate_identifier()
        rec = job_queue.get(tid) or job_queue.register(tid, tier=Tier.T2)
        prog = render_progress_bar(
            progress_ratio=rec.progress, label=rec.task_id, poll_url="/api/poll/status"
        ).value
        return respond(
            req, html_fragment=prog, status=int(HTTPStatus.CREATED),
            headers=build_swap_response_headers(trigger="workLedgerJobRegistered"),
            data={
                "capability": "work_ledger", "task_id": rec.task_id, "status": rec.status.value,
                "progress": rec.progress, "active_jobs": job_queue.active_count,
            },
        )  # fmt: skip

    @router.post("/jobs/{task_id}/progress", summary="Update progress on a T2 sprint job")
    def update_work_job_progress(req: Request) -> WebResponse:
        tid = req.path_params["task_id"]
        if job_queue.get(tid) is None:
            raise WebAppError(
                f"Work ledger job not found: {tid}", error_code="LEDGER_JOB_NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND), severity=ErrorSeverity.WARNING,
            )  # fmt: skip
        rec = job_queue.update_progress(tid, float(_extract_dict_payload(req).get("progress", 1.0)))
        prog = render_progress_bar(
            progress_ratio=rec.progress, label=rec.task_id, poll_url="/api/poll/status"
        ).value
        return respond(
            req, html_fragment=prog,
            headers=build_swap_response_headers(trigger="workLedgerJobUpdated"),
            data={
                "capability": "work_ledger", "task_id": rec.task_id, "status": rec.status.value,
                "progress": rec.progress, "active_jobs": job_queue.active_count,
            },
        )  # fmt: skip

    return router
