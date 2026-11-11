"""Unit tests for zcg.web.capabilities.telemetry_router.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import TYPE_CHECKING, Any

from zcg.web.capabilities.telemetry_router import create_telemetry_router
from zcg.web.factory import create_web_app
from zcg.web.probes import HeartbeatJitterTracker, SamplingCadenceCalculator
from zcg.web.resilience import BulkheadIsolationGuard
from zcg.web.telemetry import RouteSignalCollector

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


class TestTelemetryRouter:
    """Verify cadence probes, route signals, Audit DAG sealing/tamper detection, and guards."""

    def test_inspect_telemetry_reports_live_route_signals_and_default_dependencies_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET '' with both injected collectors and default constructor fallbacks."""
        # Arrange
        signals = RouteSignalCollector()
        signals.record(method="GET", route="/api/items", status_code=200, latency_ms=12.4)
        rtr_custom = create_telemetry_router(
            tmp_path,
            surface_label="portal-a",
            signal_collector=signals,
            jitter_tracker=HeartbeatJitterTracker(),
            bulkhead=BulkheadIsolationGuard(),
            cadence=SamplingCadenceCalculator(3.0),
            prefix="/api/tel-custom",
        )
        rtr_default = create_telemetry_router(tmp_path, prefix="/api/tel-default")
        app = create_web_app(routers=(rtr_custom, rtr_default))

        async def _scenario() -> tuple[dict[str, Any], bytes, dict[str, Any]]:
            _, b_json = await _call(app, "GET", "/api/tel-custom")
            _, b_swap = await _call(
                app, "GET", "/api/tel-custom", headers=[(b"hx-request", b"true")]
            )
            _, b_def = await _call(app, "GET", "/api/tel-default")
            return json.loads(b_json), b_swap, json.loads(b_def)

        # Act
        custom_data, custom_html, def_data = asyncio.run(_scenario())

        # Assert
        assert custom_data["surface_label"] == "portal-a"
        assert custom_data["cycle_period_seconds"] == 3.0
        assert "GET /api/items" in custom_data["routes"]
        assert b"Runtime Telemetry (portal-a)" in custom_html
        assert def_data["cycle_period_seconds"] == 2.0

    def test_audit_dag_sealing_and_history_listing_json_and_swap_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify empty GET /audit, POST /audit decision sealing, and VERIFIED chain history."""
        # Arrange
        tok = "tel-csrf-01"
        app = create_web_app(routers=(create_telemetry_router(tmp_path),), csrf_token=tok)
        swap = [(b"hx-request", b"true")]
        swap_csrf = [*swap, (b"x-zcg-csrf-token", tok.encode())]

        async def _scenario() -> dict[str, Any]:
            _, b_empty = await _call(app, "GET", "/api/telemetry/audit", headers=swap)
            s_post, b_post = await _call(
                app,
                "POST",
                "/api/telemetry/audit",
                headers=swap_csrf,
                body=json.dumps(
                    {
                        "rationale": "Verified latency SLO",
                        "utilization_ratio": 0.9,
                        "active_heavy_tasks": 2,
                    }
                ).encode(),
            )
            _, b_hist_json = await _call(app, "GET", "/api/telemetry/audit")
            _, b_hist_swap = await _call(app, "GET", "/api/telemetry/audit", headers=swap)
            return {
                "empty": b_empty,
                "s_post": s_post,
                "post_html": b_post,
                "hist": json.loads(b_hist_json),
                "hist_html": b_hist_swap,
            }

        # Act
        out = asyncio.run(_scenario())

        # Assert
        assert b"No audit decisions sealed yet." in out["empty"]
        assert out["s_post"] == 201 and b"SHIELDED" in out["post_html"]
        assert out["hist"]["decisions_count"] == 1 and out["hist"]["integrity_verified"] is True
        assert b"VERIFIED" in out["hist_html"]

    def test_audit_dag_detects_tampered_sqlite_chain_expected(self, tmp_path: Path) -> None:
        """Verify SQLite tamper corruption flips integrity_verified=False and badge TAMPERED."""
        # Arrange
        app = create_web_app(routers=(create_telemetry_router(tmp_path),))

        async def _seed() -> None:
            await _call(
                app,
                "POST",
                "/api/telemetry/audit",
                body=json.dumps({"rationale": "Baseline seal"}).encode(),
            )

        asyncio.run(_seed())
        db_file = tmp_path / ".agents/telemetry/runtime_audit_dag.sqlite3"
        conn = sqlite3.connect(db_file)
        try:
            with conn:
                conn.execute("UPDATE telemetry_audit_dag SET rationale = 'forged'")
        finally:
            conn.close()

        # Act
        _, b_swap = asyncio.run(
            _call(app, "GET", "/api/telemetry/audit", headers=[(b"hx-request", b"true")])
        )
        _, b_json = asyncio.run(_call(app, "GET", "/api/telemetry/audit"))

        # Assert
        assert b"TAMPERED" in b_swap
        assert json.loads(b_json)["integrity_verified"] is False

    def test_bipolar_payload_rationale_and_csrf_guards_expected(self, tmp_path: Path) -> None:
        """Verify 403 CSRF, 400 non-dict JSON, and 422 missing rationale on POST /audit."""
        # Arrange
        app = create_web_app(routers=(create_telemetry_router(tmp_path),))

        async def _scenario() -> tuple[int, int, int]:
            s_csrf, _ = await _call(
                app, "POST", "/api/telemetry/audit", headers=[(b"hx-request", b"true")], body=b"{}"
            )
            s_400, _ = await _call(app, "POST", "/api/telemetry/audit", body=b"[1, 2]")
            s_422, _ = await _call(app, "POST", "/api/telemetry/audit", body=b"")
            return s_csrf, s_400, s_422

        # Act
        statuses = asyncio.run(_scenario())

        # Assert
        assert statuses == (403, 400, 422)
