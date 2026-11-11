"""Unit tests for zcg.cockpit.ledger_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from zcg.cockpit.ledger_router import create_work_ledger_router
from zcg.web.factory import create_web_app
from zcg.web.resilience import DeferredJobQueue

if TYPE_CHECKING:
    from pathlib import Path


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> tuple[int, bytes]:
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
    }
    await app(scope, receive, send)
    return int(sent[0]["status"]), b"".join(m.get("body", b"") for m in sent if "body" in m)


class TestLedgerRouter:
    """Verify 1:1 Sovereign Node Work Ledger & T2 DeferredJobQueue APIRouter."""

    def test_inspect_work_ledger_projects_scope_metrics_and_degrades_on_missing_files_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET '' reads own_node_ledger/environment_gates and handles non-dict files."""
        # Arrange
        empty_ws = tmp_path / "empty"
        empty_ws.mkdir()
        bad_ws = tmp_path / "bad"
        (bad_ws / "surfaces/data").mkdir(parents=True)
        (bad_ws / "surfaces/data/node_scope.json").write_text("[1]", "utf-8")
        rich_ws = tmp_path / "rich"
        (rich_ws / "surfaces/data").mkdir(parents=True)
        (rich_ws / "surfaces/data/node_scope.json").write_text(
            json.dumps({"own_node_ledger": {"total_open_items": 3, "total_in_progress_items": 1}}),
            "utf-8",
        )
        (rich_ws / "surfaces/data/network_scope.json").write_text(
            json.dumps({"environment_gates": {"pro": {"allowed": True}}}), "utf-8"
        )
        queue = DeferredJobQueue()
        app = create_web_app(
            routers=(
                create_work_ledger_router(empty_ws, job_queue=queue, prefix="/api/empty"),
                create_work_ledger_router(bad_ws, job_queue=queue, prefix="/api/bad"),
                create_work_ledger_router(rich_ws, job_queue=queue),
            )
        )

        async def _scenario() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bytes]:
            _, b_empty = await _call(app, "GET", "/api/empty")
            _, b_bad = await _call(app, "GET", "/api/bad")
            _, b_rich = await _call(app, "GET", "/api/modules/work-ledger")
            _, b_swap = await _call(
                app, "GET", "/api/modules/work-ledger", headers=[(b"hx-request", b"true")]
            )
            return json.loads(b_empty), json.loads(b_bad), json.loads(b_rich), b_swap

        # Act
        empty_d, bad_d, rich_d, swap_html = asyncio.run(_scenario())

        # Assert
        assert empty_d["own_node_ledger"] == {} and bad_d["own_node_ledger"] == {}
        assert rich_d["own_node_ledger"]["total_open_items"] == 3
        assert rich_d["environment_gates"]["pro"]["allowed"] is True
        assert b"Work &amp; Sprint Ledger" in swap_html

    def test_job_registration_idempotency_form_submission_and_auto_id_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify POST /jobs handles empty body auto-ID, form urlencoded, and idempotent re-post."""
        # Arrange
        queue = DeferredJobQueue()
        app = create_web_app(routers=(create_work_ledger_router(tmp_path, job_queue=queue),))
        form_hdr = [(b"content-type", b"application/x-www-form-urlencoded")]

        async def _scenario() -> tuple[str, str, str, dict[str, Any]]:
            _, b_auto = await _call(app, "POST", "/api/modules/work-ledger/jobs", body=b"")
            _, b_form = await _call(
                app,
                "POST",
                "/api/modules/work-ledger/jobs",
                headers=form_hdr,
                body=urlencode({"task_id": "sprint-01"}).encode(),
            )
            _, b_idem = await _call(
                app,
                "POST",
                "/api/modules/work-ledger/jobs",
                body=json.dumps({"task_id": "sprint-01"}).encode(),
            )
            _, b_list = await _call(app, "GET", "/api/modules/work-ledger")
            return (
                json.loads(b_auto)["task_id"],
                json.loads(b_form)["task_id"],
                json.loads(b_idem)["task_id"],
                json.loads(b_list),
            )

        # Act
        auto_id, form_id, idem_id, listed = asyncio.run(_scenario())

        # Assert
        assert len(auto_id) == 36
        assert form_id == "sprint-01" and idem_id == "sprint-01"
        assert listed["active_jobs"] == 2 and len(listed["jobs"]) == 2

    def test_job_progress_completion_transitions_shared_poll_endpoint_to_286_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify POST /jobs/{id}/progress at 1.0 flips /api/poll/status from 200 to HTTP 286."""
        # Arrange
        app = create_web_app(
            router_factory=lambda st: (create_work_ledger_router(tmp_path, job_queue=st.job_queue),)
        )

        async def _scenario() -> tuple[int, int, dict[str, Any]]:
            await _call(
                app,
                "POST",
                "/api/modules/work-ledger/jobs",
                body=json.dumps({"task_id": "gate-01"}).encode(),
            )
            s_p200, _ = await _call(app, "GET", "/api/poll/status")
            _, b_done = await _call(
                app,
                "POST",
                "/api/modules/work-ledger/jobs/gate-01/progress",
                body=json.dumps({"progress": 1.0}).encode(),
            )
            s_p286, _ = await _call(app, "GET", "/api/poll/status")
            return s_p200, s_p286, json.loads(b_done)

        # Act
        s_before, s_after, done_payload = asyncio.run(_scenario())

        # Assert
        assert s_before == 200
        assert done_payload["status"] == "COMPLETED" and done_payload["active_jobs"] == 0
        assert s_after == 286

    def test_bipolar_payload_csrf_and_missing_job_404_guards_expected(self, tmp_path: Path) -> None:
        """Verify 403 CSRF, 400 non-dict JSON, and 404 unknown job progress update."""
        # Arrange
        queue = DeferredJobQueue()
        app = create_web_app(routers=(create_work_ledger_router(tmp_path, job_queue=queue),))

        async def _scenario() -> tuple[int, int, int]:
            s_csrf, _ = await _call(
                app,
                "POST",
                "/api/modules/work-ledger/jobs",
                headers=[(b"hx-request", b"true")],
                body=b"{}",
            )
            s_400, _ = await _call(app, "POST", "/api/modules/work-ledger/jobs", body=b"[1]")
            s_404, _ = await _call(
                app, "POST", "/api/modules/work-ledger/jobs/missing/progress", body=b"{}"
            )
            return s_csrf, s_400, s_404

        # Act
        statuses = asyncio.run(_scenario())

        # Assert
        assert statuses == (403, 400, 404)
