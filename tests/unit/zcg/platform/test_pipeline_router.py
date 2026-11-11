"""Unit tests for zcg.platform.pipeline_router.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from zcg.platform.pipeline_router import DataPipelineRuntime, create_data_pipeline_router
from zcg.web.factory import create_web_app


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


class TestPipelineRouter:
    """Verify stateful DataPipelineRuntime CDC/CVS/drift progression and router guards."""

    def test_uninitialized_summary_and_empty_ingest_guard_expected(self) -> None:
        """Verify fresh DataPipelineRuntime reports UNINITIALIZED and rejects empty batches."""
        # Arrange
        runtime = DataPipelineRuntime(source_label="corpus-feed")

        # Act
        initial = runtime.current_summary()
        with pytest.raises(ValueError, match="must not be empty") as exc_empty:
            runtime.ingest_batch(())

        # Assert
        assert initial["schema_status"] == "UNINITIALIZED"
        assert initial["batches_processed"] == 0 and initial["fields"] == []
        assert exc_empty.value is not None

    def test_seeded_router_serves_json_and_html_swap_views_expected(self) -> None:
        """Verify seeded router initializes baseline snapshot and renders HTML swap cards."""
        # Arrange
        seeds = ({"id": "rec-1", "code": "ISO-10", "metric": 98.4},)
        app = create_web_app(
            routers=(create_data_pipeline_router(source_label="atlas", seed_records=seeds),)
        )

        async def _scenario() -> tuple[dict[str, Any], bytes]:
            _, b_json = await _call(app, "GET", "/api/platform/pipeline")
            _, b_swap = await _call(
                app, "GET", "/api/platform/pipeline", headers=[(b"hx-request", b"true")]
            )
            return json.loads(b_json), b_swap

        # Act
        summary, html_frag = asyncio.run(_scenario())

        # Assert
        assert summary["source"] == "atlas" and summary["batches_processed"] == 1
        assert summary["batch_cdc_events"] == 1 and summary["cvs_overall_score"] > 0.0
        assert b"Data Pipeline (atlas)" in html_frag

    def test_successive_post_batches_track_cdc_updates_and_schema_drift_expected(self) -> None:
        """Verify multi-batch POST ingestion accumulates CDC deltas and detects schema drift."""
        # Arrange
        app = create_web_app(routers=(create_data_pipeline_router(source_label="stream"),))
        batch_1 = [{"id": "r1", "code": "A", "score": 10}, {"id": "r2", "code": "B", "score": 20}]
        batch_2 = [{"id": "r1", "code": "A", "score": 15, "extra_flag": True}]

        async def _scenario() -> tuple[dict[str, Any], dict[str, Any]]:
            _, b1 = await _call(
                app,
                "POST",
                "/api/platform/pipeline",
                body=json.dumps({"records": batch_1}).encode(),
            )
            _, b2 = await _call(
                app,
                "POST",
                "/api/platform/pipeline",
                body=json.dumps({"records": batch_2}).encode(),
            )
            return json.loads(b1), json.loads(b2)

        # Act
        first_out, second_out = asyncio.run(_scenario())

        # Assert
        assert first_out["batches_processed"] == 1 and first_out["batch_cdc_events"] == 2
        assert first_out["drift_severity"] == "none"
        assert second_out["batches_processed"] == 2
        assert second_out["cumulative_cdc_events"] == 4
        assert second_out["drift_severity"] != "none"

    def test_bipolar_payload_and_records_validation_guards_expected(self) -> None:
        """Verify 400 non-dict payload, 422 empty records, and 403 missing CSRF on swap."""
        # Arrange
        app = create_web_app(routers=(create_data_pipeline_router(),))

        async def _scenario() -> tuple[int, int, int, int]:
            s_csrf, _ = await _call(
                app,
                "POST",
                "/api/platform/pipeline",
                headers=[(b"hx-request", b"true")],
                body=b"{}",
            )
            s_400, _ = await _call(app, "POST", "/api/platform/pipeline", body=b"")
            s_422_empty, _ = await _call(
                app, "POST", "/api/platform/pipeline", body=json.dumps({"records": []}).encode()
            )
            s_422_type, _ = await _call(
                app,
                "POST",
                "/api/platform/pipeline",
                body=json.dumps({"records": ["bad"]}).encode(),
            )
            return s_csrf, s_400, s_422_empty, s_422_type

        # Act
        statuses = asyncio.run(_scenario())

        # Assert
        assert statuses == (403, 400, 422, 422)
