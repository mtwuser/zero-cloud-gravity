"""Composable Runtime Observability, Cadence Probes & Audit DAG Router ('create_telemetry_router').

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

from zcg.web.channels import build_swap_response_headers
from zcg.web.components import render_card, render_item_list, render_kpi_stat, render_table
from zcg.web.probes import HeartbeatJitterTracker, SamplingCadenceCalculator
from zcg.web.request import Request, WebResponse, respond
from zcg.web.resilience import BulkheadIsolationGuard, ContextLoadSnapshot
from zcg.web.router import APIRouter
from zcg.web.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.telemetry import (
    EndpointTelemetryInput,
    RouteSignalCollector,
    RuntimeTelemetryScorer,
    TelemetryAuditDAG,
    TelemetryGrade,
)
from zcg.web.templates import SafeHTML

DEFAULT_TELEMETRY_PREFIX: Final[str] = "/api/telemetry"
DEFAULT_CADENCE_CYCLE_SECONDS: Final[float] = 2.0


def _parse_json_dict(req: Request) -> dict[str, Any]:
    if not req.body:
        return {}
    parsed = req.json()
    if not isinstance(parsed, dict):
        raise WebAppError(
            "Telemetry payload must be a JSON object",
            error_code="INVALID_TELEMETRY_PAYLOAD",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )
    return parsed


def create_telemetry_router(
    workspace_dir: Path,
    *,
    surface_label: str = "web-app",
    signal_collector: RouteSignalCollector | None = None,
    jitter_tracker: HeartbeatJitterTracker | None = None,
    bulkhead: BulkheadIsolationGuard | None = None,
    cadence: SamplingCadenceCalculator | None = None,
    prefix: str = DEFAULT_TELEMETRY_PREFIX,
) -> APIRouter:
    """Create a domain-neutral Runtime Telemetry, Cadence Probe, and Audit DAG APIRouter."""
    ws = workspace_dir.resolve()
    eff_signals = signal_collector if signal_collector is not None else RouteSignalCollector()
    eff_jitter = jitter_tracker if jitter_tracker is not None else HeartbeatJitterTracker()
    eff_bulkhead = bulkhead if bulkhead is not None else BulkheadIsolationGuard()
    eff_cadence = (
        cadence if cadence is not None else SamplingCadenceCalculator(DEFAULT_CADENCE_CYCLE_SECONDS)
    )
    router = APIRouter(prefix=prefix, tags=("telemetry",))

    @router.get("", summary="Inspect cadence probes, route signals, bulkhead, and Audit DAG")
    def inspect_telemetry(req: Request) -> WebResponse:
        sched = eff_cadence.compute_next_schedule(jitter_seed=0.0)
        j_snap = eff_jitter.record_tick()
        bh_dec = eff_bulkhead.evaluate(ContextLoadSnapshot(0.35, 0))
        rep = RuntimeTelemetryScorer(grade=TelemetryGrade.G2_ADVISE).evaluate(
            eff_signals.derive_telemetry_input()
        )
        dag = TelemetryAuditDAG(ws)
        nodes = dag.list_nodes()
        integrity_ok = dag.verify_integrity()
        route_rows = [
            {"route": r_name, **metrics} for r_name, metrics in eff_signals.route_summary().items()
        ]
        body_html = SafeHTML(
            render_kpi_stat(label="Regime", value=rep.regime.value, delta=f"{rep.score:.1f}").value
            + render_kpi_stat(label="Bulkhead", value=bh_dec.status.value).value
            + render_kpi_stat(label="Audit DAG", value=str(len(nodes))).value
            + render_table(
                columns=(
                    ("route", "Route"),
                    ("count", "Calls"),
                    ("mean_latency_ms", "Mean ms"),
                    ("errors", "5xx Errors"),
                ),
                rows=route_rows,
                empty_message="No route signals recorded yet.",
            ).value
        )
        frag = render_card(
            title=f"Runtime Telemetry ({surface_label})",
            badge=j_snap.status.value,
            body=body_html,
        ).value
        return respond(
            req,
            html_fragment=frag,
            data={
                "capability": "telemetry",
                "surface_label": surface_label,
                "health_regime": rep.regime.value,
                "health_score": rep.score,
                "cycle_period_seconds": sched.cycle_period_seconds,
                "recommended_sample_interval_seconds": sched.recommended_sample_interval_seconds,
                "minimum_window_seconds": sched.minimum_window_seconds,
                "jitter_status": j_snap.status.value,
                "bulkhead_status": bh_dec.status.value,
                "decisions_count": len(nodes),
                "integrity_verified": integrity_ok,
                "routes": eff_signals.route_summary(),
            },
        )

    @router.get("/audit", summary="Inspect hash-chained Audit DAG decision history")
    def list_audit_decisions(req: Request) -> WebResponse:
        dag = TelemetryAuditDAG(ws)
        nodes = dag.list_nodes()
        integrity_ok = dag.verify_integrity()
        rows = [
            {
                "decision_id": n.node_id,
                "action": n.action.value,
                "regime": n.regime.value,
                "rationale": n.rationale,
                "node_hash": n.node_hash,
            }
            for n in nodes
        ]
        list_html = render_item_list(
            items=rows,
            title_key="rationale",
            meta_key="action",
            badge_key="regime",
            empty_message="No audit decisions sealed yet.",
        )
        frag = render_card(
            title="Audit Decision DAG",
            badge="VERIFIED" if integrity_ok else "TAMPERED",
            body=list_html,
        ).value
        return respond(
            req,
            html_fragment=frag,
            data={
                "capability": "telemetry",
                "decisions_count": len(nodes),
                "integrity_verified": integrity_ok,
                "decisions": rows,
            },
        )

    @router.post("/audit", summary="Append hash-chained Audit DAG decision")
    def append_audit_decision(req: Request) -> WebResponse:
        data = _parse_json_dict(req)
        rationale = str(data.get("rationale") or "").strip()
        if not rationale:
            raise WebAppError(
                "Field 'rationale' is required to seal an audit decision",
                error_code="MISSING_AUDIT_RATIONALE",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        bh_dec = eff_bulkhead.evaluate(
            ContextLoadSnapshot(
                float(data.get("utilization_ratio", 0.35)),
                int(data.get("active_heavy_tasks", 0)),
            )
        )
        rep = RuntimeTelemetryScorer(grade=TelemetryGrade.G3_AUTOMATE).evaluate(
            EndpointTelemetryInput(volume_ratio=float(data.get("volume_ratio", 0.95)))
        )
        dag = TelemetryAuditDAG(ws)
        node = dag.append_decision(layer_id=surface_label, report=rep, rationale=rationale)
        frag = render_card(
            title=f"Audit Decision Sealed ({node.action.value})",
            badge=bh_dec.status.value,
            body=f"Hash: {node.node_hash} | Rationale: {rationale}",
        ).value
        return respond(
            req,
            html_fragment=frag,
            data={
                "capability": "telemetry",
                "decision_id": node.node_id,
                "node_hash": node.node_hash,
                "bulkhead_status": bh_dec.status.value,
                "recommended_tier": bh_dec.recommended_tier.value,
                "regime": rep.regime.value,
                "integrity_verified": dag.verify_integrity(),
            },
            status=int(HTTPStatus.CREATED),
            headers=build_swap_response_headers(trigger="auditDecisionAppended"),
        )

    return router
