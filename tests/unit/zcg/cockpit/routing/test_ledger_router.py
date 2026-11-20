"""Unit tests for zcg.cockpit.routing.ledger_router.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from zcg.cockpit.routing.ledger_router import create_work_ledger_router
from zcg.web.http.factory import create_web_app
from zcg.web.ops.resilience import DeferredJobQueue

if TYPE_CHECKING:
    from pathlib import Path


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
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
        "query_string": query.encode("latin1"),
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
        (rich_ws / "system").mkdir(parents=True)
        (rich_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "rich-ws",
                    "layer_role": "workstation",
                    "entity_kind": "individual",
                    "precedence": 90,
                    "git_governance": {"promotion_pipeline": "direct"},
                }
            ),
            "utf-8",
        )
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
        hx = [(b"hx-request", b"true")]

        async def _scenario() -> tuple[Any, Any, Any, bytes, bytes, bytes]:
            _, b_empty = await _call(app, "GET", "/api/empty")
            _, b_bad = await _call(app, "GET", "/api/bad")
            _, b_rich = await _call(app, "GET", "/api/modules/work-ledger")
            _, b_swap = await _call(app, "GET", "/api/modules/work-ledger", headers=hx)
            _, b_val = await _call(
                app, "GET", "/api/modules/work-ledger", query="section=validations", headers=hx
            )
            _, b_met = await _call(
                app, "GET", "/api/modules/work-ledger", query="section=metrics", headers=hx
            )
            return json.loads(b_empty), json.loads(b_bad), json.loads(b_rich), b_swap, b_val, b_met

        # Act
        empty_d, bad_d, rich_d, swap_html, val_direct_h, met_ws_h = asyncio.run(_scenario())

        # Assert
        assert empty_d["own_node_ledger"] == {} and bad_d["own_node_ledger"] == {}
        assert rich_d["own_node_ledger"]["total_open_items"] == 3
        assert rich_d["environment_gates"]["pro"]["allowed"] is True
        assert b"Work Board" in swap_html and b"Background Jobs" in swap_html
        assert b"zcg-kanban" in swap_html
        assert b"Gate [" not in val_direct_h and b"make env-gate ENV=pro" not in val_direct_h
        assert b"make workstation-audit" in met_ws_h and b"metrics_scope=" not in met_ws_h

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

    def test_task_studio_mutations_scoped_commit_and_1hop_exchange_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify POST /tasks (add/claim/complete/commit) and POST /exchange (delegate/propose)."""
        # Arrange
        parent_ws = tmp_path / "corp-iso"
        child_ws = parent_ws / "layers/squad-iso"
        sib_ws = parent_ws / "layers/squad-ops"
        for node_d, lid, role in (
            (parent_ws, "corp-iso", "corporate"),
            (child_ws, "squad-iso", "squad"),
            (sib_ws, "squad-ops", "squad"),
        ):
            node_d.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-b", "master", str(node_d)], check=True, capture_output=True
            )
            subprocess.run(["git", "-C", str(node_d), "config", "user.name", "ISO"], check=True)
            subprocess.run(
                ["git", "-C", str(node_d), "config", "user.email", "iso@example.org"], check=True
            )
            (node_d / "system").mkdir(exist_ok=True)
            m_doc: dict[str, Any] = {
                "layer_id": lid,
                "layer_role": role,
                "governing_root_id": "corp-iso",
            }
            if lid == "squad-iso":
                m_doc["git_governance"] = {"promotion_pipeline": "staged"}
            if lid == "corp-iso":
                m_doc["capability_policy"] = {
                    "mesh_governance": {
                        "topology_mode": "curated-matrix",
                        "lateral_channels": [
                            {
                                "source_node": "squad-iso",
                                "target_node": "squad-ops",
                                "allowed_verbs": ["consult_context", "propose_work"],
                                "reciprocal": False,
                            }
                        ],
                    }
                }
            (node_d / "system/zcg-node.json").write_text(json.dumps(m_doc), encoding="utf-8")
            (node_d / "WORKTASK.md").write_text("# Tasks\n", encoding="utf-8")
            (node_d / "BACKLOG.md").write_text(
                "# Backlog\n\n- [ ] **[BKL-01]** Queued item\n", encoding="utf-8"
            )
            (node_d / "WORKVALI.md").write_text("# QA\n\n- [ ] Check header\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(node_d), "add", "."], check=True)
            subprocess.run(["git", "-C", str(node_d), "commit", "-m", "chore: init"], check=True)
        (child_ws / ".agents/proposals").mkdir(parents=True)
        (child_ws / ".agents/proposals/sync-rule.md").write_text("# Rule\n", encoding="utf-8")
        bare_ws = tmp_path / "bare-node"
        bare_ws.mkdir()
        q, tok = DeferredJobQueue(), f"tok-{tmp_path.name}"
        app_p = create_web_app(
            csrf_token=tok, routers=(create_work_ledger_router(parent_ws, job_queue=q),)
        )
        app_c = create_web_app(
            csrf_token=tok, routers=(create_work_ledger_router(child_ws, job_queue=q),)
        )
        app_s = create_web_app(
            csrf_token=tok, routers=(create_work_ledger_router(sib_ws, job_queue=q),)
        )
        app_b = create_web_app(
            csrf_token=tok, routers=(create_work_ledger_router(bare_ws, job_queue=q),)
        )
        ch = [(b"x-zcg-csrf-token", tok.encode("latin1")), (b"content-type", b"application/json")]

        async def _post(
            app: Any, sub: str, obj: dict[str, Any], *, query: str = ""
        ) -> tuple[int, bytes]:
            return await _call(
                app,
                "POST",
                f"/api/modules/work-ledger/{sub}",
                query=query,
                headers=ch,
                body=json.dumps(obj).encode(),
            )

        async def _scenario() -> list[tuple[int, bytes]]:
            ops: tuple[tuple[Any, str, dict[str, Any]], ...] = (
                (app_c, "tasks", {"action": "add", "task_text": "**T1**: Audit UI"}),
                (app_c, "tasks", {"action": "claim", "task_text": "Audit UI"}),
                (app_c, "tasks", {"action": "complete", "task_text": "Audit UI"}),
                (app_c, "tasks", {"action": "commit", "task_text": "docs(ledger): complete T1"}),
                (app_c, "tasks", {"action": "commit", "task_text": "docs(ledger): nothing"}),
                (app_c, "tasks", {"action": "bad", "task_text": "x"}),
                (app_c, "tasks", {"tracker": "BAD.md", "task_text": ""}),
                (app_c, "tasks", {"action": "promote", "tracker": "BACKLOG.md", "task_text": "BKL-01"}),  # noqa: E501
                (app_p, "inbox", {"action": "enqueue", "sender_node": "squad-iso", "summary": "API ready"}),  # noqa: E501
                (app_p, "inbox", {"request_id": "missing", "decision": "decline"}),
                (app_p, "exchange", {"mode": "delegate", "target_node": "squad-iso", "directive": "Run QA"}),  # noqa: E501
                (app_c, "exchange", {"mode": "propose", "target_node": "corp-iso", "directive": "Sync spec"}),  # noqa: E501
            )  # fmt: skip
            tail_ops: tuple[tuple[Any, str, dict[str, Any]], ...] = (
                (app_c, "exchange", {"mode": "propose", "target_node": "missing-node", "directive": "x"}),  # noqa: E501
                (app_c, "exchange", {"target_node": "BAD_ID", "directive": ""}),
                (app_c, "exchange", {"mode": "propose", "target_node": "squad-ops", "directive": "Align CI"}),  # noqa: E501
                (app_s, "exchange", {"mode": "propose", "target_node": "squad-iso", "directive": "Denied"}),  # noqa: E501
                (app_b, "exchange", {"mode": "propose", "target_node": "missing-node", "directive": "No dir"}),  # noqa: E501
                (app_p, "tasks", {"action": "add", "task_text": "Direct child", "exchange_target": "squad-iso"}),  # noqa: E501
                (app_c, "tasks", {"action": "add", "task_text": "Direct sibling", "exchange_target": "squad-ops"}),  # noqa: E501
                (app_c, "tasks", {"action": "add", "task_text": "Bad tgt", "exchange_target": "BAD_ID"}),  # noqa: E501
            )  # fmt: skip
            head = [await _post(a, s, p) for a, s, p in ops]
            get_p = await _call(
                app_p, "GET", "/api/modules/work-ledger", headers=[(b"hx-request", b"true")]
            )
            return [*head, get_p, *[await _post(a, s, p) for a, s, p in tail_ops]]

        # Act
        results = asyncio.run(_scenario())
        enq_id = json.loads(results[8][1])["request_id"]
        st_tri, _ = asyncio.run(
            _post(app_p, "inbox", {"request_id": enq_id, "decision": "accept-todo"})
        )
        st_tri_dup, _ = asyncio.run(
            _post(app_p, "inbox", {"request_id": enq_id, "decision": "decline"})
        )
        st_tog, _ = asyncio.run(
            _post(
                app_c,
                "tasks",
                {
                    "action": "toggle",
                    "tracker": "WORKVALI.md",
                    "task_text": "Check header",
                    "target_state": "x",
                },
                query="section=validations",
            )
        )
        (child_ws / "surfaces/data").mkdir(parents=True, exist_ok=True)
        (child_ws / "surfaces/data/network_scope.json").write_text(
            json.dumps({"environment_gates": {"pro": {"allowed": True}}}), encoding="utf-8"
        )
        sec_htmls = [
            asyncio.run(
                _call(
                    app_c,
                    "GET",
                    "/api/modules/work-ledger",
                    query=f"section={s}",
                    headers=[(b"hx-request", b"true")],
                )
            )[1]
            for s in ("dashboard", "backlog", "roadmaps", "validations", "metrics")
        ]
        (child_ws / "surfaces/data/node_scope.json").write_text(
            json.dumps(
                {
                    "representation_context": {
                        "node_health": {
                            "overall_state": "ATTENTION",
                            "dimensions": {
                                "security_posture": {"score": 88},
                                "skill_trust": {"score": 92},
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        _, metrics_net_b = asyncio.run(
            _call(
                app_c,
                "GET",
                "/api/modules/work-ledger",
                query="section=metrics&metrics_scope=network",
            )
        )
        _, metrics_ws_b = asyncio.run(
            _call(
                app_c, "GET", "/api/modules/work-ledger", query="section=metrics&ws_scope=corpora"
            )
        )
        metrics_net_d, metrics_ws_d = json.loads(metrics_net_b), json.loads(metrics_ws_b)

        # Assert
        codes = [r[0] for r in results]
        expected_codes = [
            200, 200, 200, 200, 409, 422, 422, 200, 200, 422, 200, 200, 200, 403, 422,
            200, 403, 422, 200, 200, 422,
        ]  # fmt: skip
        assert codes == expected_codes
        assert st_tri == 200 and st_tri_dup == 409 and st_tog == 200
        assert all(b"data-work-section=" in h for h in sec_htmls)
        assert b"name='exchange_target'" in sec_htmls[0]
        assert b"zcg-dirty-banner" in sec_htmls[3] and b"WORKVALI.md" in sec_htmls[3]
        assert b"Gate [PRO]" in sec_htmls[3] and b"make env-gate ENV=pro" in sec_htmls[3]
        assert b"zcg-dirty-banner" not in sec_htmls[2]
        assert b"data-zcg-metrics-view" in sec_htmls[-1]
        assert b"make workstation-audit" not in sec_htmls[-1]
        assert metrics_net_d["section"] == "metrics"
        assert metrics_net_d["metrics"]["scope"] == "network"
        assert metrics_ws_d["metrics"]["scope"] == "corpora"
        assert b"from-squad-iso" in results[12][1]
        assert b"MESH_RELATION_FORBIDDEN" in results[16][1]
        assert b"EXCHANGE_TARGET_NOT_FOUND" in results[17][1]
        assert not (parent_ws / ".agents/proposals").exists()
