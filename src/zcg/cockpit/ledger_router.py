"""Cohesive 1:1 Sovereign Node Work Ledger & T2 Job Queue Router ('create_work_ledger_router').

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

from zcg.core.domain import generate_identifier
from zcg.web.channels import Tier, build_swap_response_headers
from zcg.web.components import render_card, render_kpi_stat, render_progress_bar, render_table
from zcg.web.request import Request, WebResponse, respond
from zcg.web.resilience import DeferredJobQueue
from zcg.web.router import APIRouter
from zcg.web.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.templates import SafeHTML

DEFAULT_WORK_LEDGER_PREFIX: Final[str] = "/api/modules/work-ledger"


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
            "Work ledger payload must be a JSON object",
            error_code="INVALID_LEDGER_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    return parsed


def create_work_ledger_router(
    workspace_dir: Path,
    *,
    job_queue: DeferredJobQueue,
    prefix: str = DEFAULT_WORK_LEDGER_PREFIX,
) -> APIRouter:
    """Create a 1:1 Sovereign Node Work Ledger & T2 Deferred Job Queue APIRouter."""
    ws = workspace_dir.resolve()
    router = APIRouter(prefix=prefix, tags=("work-ledger",))

    @router.get("", summary="Inspect sprint ledger metrics, env-gates, and active T2 jobs")
    def inspect_work_ledger(req: Request) -> WebResponse:
        node_doc = _read_json_dict(ws / "surfaces/data/node_scope.json")
        net_doc = _read_json_dict(ws / "surfaces/data/network_scope.json")
        raw_ledger = node_doc.get("own_node_ledger")
        ledger = raw_ledger if isinstance(raw_ledger, dict) else {}
        raw_gates = net_doc.get("environment_gates")
        gates = raw_gates if isinstance(raw_gates, dict) else {}
        jobs = [
            {"task_id": r.task_id, "status": r.status.value, "progress": r.progress}
            for r in job_queue.records()
        ]
        body_html = SafeHTML(
            render_kpi_stat(label="Open", value=str(ledger.get("total_open_items", 0))).value
            + render_kpi_stat(
                label="In Progress", value=str(ledger.get("total_in_progress_items", 0))
            ).value
            + render_kpi_stat(label="Active Jobs", value=str(job_queue.active_count)).value
            + render_table(
                columns=(("task_id", "Job ID"), ("status", "Status")),
                rows=jobs,
                empty_message="No deferred jobs queued.",
            ).value
        )
        frag = render_card(title="Work & Sprint Ledger", body=body_html).value
        return respond(
            req,
            html_fragment=frag,
            data={
                "capability": "work_ledger",
                "own_node_ledger": ledger,
                "environment_gates": gates,
                "active_jobs": job_queue.active_count,
                "jobs": jobs,
            },
        )

    @router.post("/jobs", summary="Register an idempotent T2 sprint background job")
    def register_work_job(req: Request) -> WebResponse:
        data = _extract_dict_payload(req)
        tid = str(data.get("task_id") or "").strip() or generate_identifier()
        rec = job_queue.get(tid) or job_queue.register(tid, tier=Tier.T2)
        prog = render_progress_bar(
            progress_ratio=rec.progress, label=rec.task_id, poll_url="/api/poll/status"
        ).value
        return respond(
            req,
            html_fragment=prog,
            data={
                "capability": "work_ledger",
                "task_id": rec.task_id,
                "status": rec.status.value,
                "progress": rec.progress,
                "active_jobs": job_queue.active_count,
            },
            status=int(HTTPStatus.CREATED),
            headers=build_swap_response_headers(trigger="workLedgerJobRegistered"),
        )

    @router.post("/jobs/{task_id}/progress", summary="Update progress on a T2 sprint job")
    def update_work_job_progress(req: Request) -> WebResponse:
        tid = req.path_params["task_id"]
        if job_queue.get(tid) is None:
            raise WebAppError(
                f"Work ledger job not found: {tid}",
                error_code="LEDGER_JOB_NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND),
                severity=ErrorSeverity.WARNING,
            )
        data = _extract_dict_payload(req)
        ratio = float(data.get("progress", 1.0))
        rec = job_queue.update_progress(tid, ratio)
        prog = render_progress_bar(
            progress_ratio=rec.progress, label=rec.task_id, poll_url="/api/poll/status"
        ).value
        return respond(
            req,
            html_fragment=prog,
            data={
                "capability": "work_ledger",
                "task_id": rec.task_id,
                "status": rec.status.value,
                "progress": rec.progress,
                "active_jobs": job_queue.active_count,
            },
            headers=build_swap_response_headers(trigger="workLedgerJobUpdated"),
        )

    return router
