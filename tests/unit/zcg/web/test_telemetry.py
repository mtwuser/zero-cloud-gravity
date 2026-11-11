"""Unit tests for zcg.web.telemetry.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

import pytest

from zcg.web.telemetry import (
    GENESIS_PARENT_HASH,
    EndpointTelemetryInput,
    HealthRegime,
    RouteSignalCollector,
    RuntimeTelemetryScorer,
    TelemetryAuditDAG,
    TelemetryGrade,
    TransitionAction,
)


class TestTelemetry:
    """Verify G1..G3 runtime health scoring, RouteSignalCollector, and TelemetryAuditDAG."""

    def test_runtime_telemetry_scorer_regimes_actions_and_grade_eligibility_expected(self) -> None:
        """Verify OPTIMAL/DEGRADED/PROTECTIVE/CRITICAL cut-points and G1 vs G3 auto_eligible."""
        # Arrange
        g1 = RuntimeTelemetryScorer(grade=TelemetryGrade.G1_OBSERVE)
        g3 = RuntimeTelemetryScorer(grade=TelemetryGrade.G3_AUTOMATE)

        # Act
        rep_100_g1 = g1.evaluate(EndpointTelemetryInput(1.0, 1.0, 1.0, 1.0))
        rep_100_g3 = g3.evaluate(EndpointTelemetryInput(1.0, 1.0, 1.0, 1.0))
        rep_80_g3 = g3.evaluate(EndpointTelemetryInput(0.80, 0.80, 0.80, 0.80))
        rep_55 = g3.evaluate(EndpointTelemetryInput(0.55, 0.55, 0.55, 0.55))
        rep_30 = g3.evaluate(EndpointTelemetryInput(0.30, 0.30, 0.30, 0.30))
        rep_25 = g3.evaluate(EndpointTelemetryInput(0.25, 0.25, 0.25, 0.25))
        rep_20 = g3.evaluate(EndpointTelemetryInput(0.20, 0.20, 0.20, 0.20))

        # Assert
        assert g1.grade == TelemetryGrade.G1_OBSERVE
        assert rep_100_g1.regime == HealthRegime.OPTIMAL
        assert rep_100_g1.recommended_action == TransitionAction.CHANNEL_PROMOTE
        assert rep_100_g1.auto_eligible is False
        assert rep_100_g3.auto_eligible is True
        assert rep_80_g3.regime == HealthRegime.OPTIMAL
        assert rep_80_g3.recommended_action == TransitionAction.STABLE
        assert rep_80_g3.auto_eligible is False
        assert rep_55.regime == HealthRegime.DEGRADED
        assert rep_55.recommended_action == TransitionAction.STABLE
        assert rep_30.regime == HealthRegime.PROTECTIVE
        assert rep_30.recommended_action == TransitionAction.CHANNEL_DEMOTE
        assert rep_30.auto_eligible is True
        assert rep_25.regime == HealthRegime.CRITICAL
        assert rep_25.recommended_action == TransitionAction.CHANNEL_DEMOTE
        assert rep_20.regime == HealthRegime.CRITICAL
        assert rep_20.recommended_action == TransitionAction.RETIREMENT

    def test_route_signal_collector_ring_buffer_and_summary_expected(self) -> None:
        """Verify empty defaults, bounded ring eviction, derived ratios, and route aggregation."""
        # Arrange
        collector = RouteSignalCollector(max_signals=2)

        # Act
        empty_input = collector.derive_telemetry_input()
        empty_summary = collector.route_summary()
        collector.record(method="get", route="/notes", status_code=200, latency_ms=10.0)
        collector.record(method="get", route="/notes", status_code=200, latency_ms=20.0)
        collector.record(method="post", route="/notes", status_code=503, latency_ms=180.0)
        retained = collector.signals()
        derived = collector.derive_telemetry_input()
        summary = collector.route_summary()

        # Assert
        assert empty_input.success_ratio == 1.0
        assert empty_summary == {}
        assert len(retained) == 2
        assert retained[0].latency_ms == 20.0 and retained[1].status_code == 503
        assert derived.success_ratio == 0.5
        assert derived.volume_ratio == 1.0
        assert summary["GET /notes"] == {"count": 1, "errors": 0, "mean_latency_ms": 20.0}
        assert summary["POST /notes"] == {"count": 1, "errors": 1, "mean_latency_ms": 180.0}
        with pytest.raises(ValueError, match="max_signals"):
            RouteSignalCollector(max_signals=0)

    def test_telemetry_audit_dag_sqlite_wal_chaining_and_tamper_detection_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify SQLite WAL hash chaining, containment guard, and payload/parent tamper checks."""
        # Arrange
        ws = tmp_path / "alex-work"
        ws.mkdir()
        dag = TelemetryAuditDAG(ws)
        scorer = RuntimeTelemetryScorer(grade=TelemetryGrade.G2_ADVISE)
        rep_ok = scorer.evaluate(EndpointTelemetryInput(0.90, 0.90, 0.90, 0.90))
        rep_deg = scorer.evaluate(EndpointTelemetryInput(0.60, 0.60, 0.60, 0.60))

        # Act
        empty_valid = dag.verify_integrity()
        first = dag.append_decision(layer_id="alex-work", report=rep_ok, rationale="initial probe")
        second = dag.append_decision(
            layer_id="alex-work",
            report=rep_deg,
            rationale="latency spike",
            node_id="aud-iso-002",
            recorded_at_utc="2026-11-10T22:00:00+00:00",
        )
        chain_nodes = dag.list_nodes()
        intact_valid = dag.verify_integrity()

        with contextlib.closing(sqlite3.connect(dag.db_path)) as conn, conn:
            conn.execute(
                "UPDATE telemetry_audit_dag SET rationale = 'forged' WHERE node_id = ?",
                (second.node_id,),
            )
        tampered_payload_valid = dag.verify_integrity()

        with contextlib.closing(sqlite3.connect(dag.db_path)) as conn, conn:
            conn.execute(
                "UPDATE telemetry_audit_dag SET parent_hash = ? WHERE node_id = ?",
                ("f" * 64, second.node_id),
            )
        tampered_parent_valid = dag.verify_integrity()

        # Assert
        assert dag.db_path == ws / ".agents/telemetry/runtime_audit_dag.sqlite3"
        assert empty_valid is True and intact_valid is True
        assert first.parent_hash == GENESIS_PARENT_HASH
        assert second.parent_hash == first.node_hash
        assert len(chain_nodes) == 2
        assert tampered_payload_valid is False
        assert tampered_parent_valid is False
        with pytest.raises(ValueError, match="PATH_CONTAINMENT_VIOLATION"):
            TelemetryAuditDAG(ws, rel_db_path="../escape.sqlite3")
