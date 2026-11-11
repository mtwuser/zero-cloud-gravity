"""Stateful Data Pipeline Web Router ('DataPipelineRuntime', 'create_data_pipeline_router').

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any, Final

from zcg.platform.cdc import ChangeDataCapture, InMemoryDataConnector
from zcg.platform.cvs import (
    ContinuousValidationScorer,
    DatasetValidationSnapshot,
    DriftSeverity,
    FieldValidationMetric,
    SchemaDriftDetector,
)
from zcg.platform.schema_discovery import SchemaDiscovery
from zcg.web.channels import build_swap_response_headers
from zcg.web.components import render_card, render_kpi_stat, render_table
from zcg.web.request import Request, WebResponse, respond
from zcg.web.router import APIRouter
from zcg.web.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.templates import SafeHTML

DEFAULT_DATA_PIPELINE_PREFIX: Final[str] = "/api/platform/pipeline"


class DataPipelineRuntime:
    """Instance-scoped stateful coordinator for SchemaDiscovery, CDC, CVS, and drift detection."""

    def __init__(
        self,
        *,
        source_label: str = "dataset",
        seed_records: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self._source_label = source_label
        self._connector = InMemoryDataConnector(source_name=source_label)
        self._cdc = ChangeDataCapture(connector=self._connector)
        self._discovery = SchemaDiscovery()
        self._scorer = ContinuousValidationScorer()
        self._drift = SchemaDriftDetector()
        self._baseline_snapshot: DatasetValidationSnapshot | None = None
        self._batches_processed = 0
        self._cumulative_cdc_events = 0
        self._latest_summary: dict[str, Any] | None = None
        if seed_records:
            self.ingest_batch(seed_records)

    def current_summary(self) -> dict[str, Any]:
        """Return latest pipeline telemetry or empty uninitialized state."""
        if self._latest_summary is not None:
            return dict(self._latest_summary)
        return {
            "capability": "data_pipeline",
            "source": self._source_label,
            "batches_processed": 0,
            "schema_status": "UNINITIALIZED",
            "fields_count": 0,
            "fields": [],
            "batch_cdc_events": 0,
            "cumulative_cdc_events": 0,
            "cvs_overall_score": 0.0,
            "drift_severity": DriftSeverity.NONE.value,
        }

    def ingest_batch(self, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Ingest a non-empty record batch, computing CDC deltas, schema, CVS, and drift."""
        normalized = [dict(r) for r in records]
        if not normalized:
            raise ValueError("Batch records must not be empty")
        proposal = self._discovery.discover(
            family=f"{self._source_label}-schema", records=normalized
        )
        self._connector.push(normalized)
        events = self._cdc.tick()
        snapshot = DatasetValidationSnapshot(
            source=self._source_label,
            total_records=proposal.total_records,
            expected_field_count=len(proposal.fields),
            fields=tuple(
                FieldValidationMetric(f.name, 0.0, 1.0, f.semantic_type) for f in proposal.fields
            ),
        )
        cvs_result = self._scorer.score(snapshot)
        if self._baseline_snapshot is None:
            self._baseline_snapshot = snapshot
            drift_sev = DriftSeverity.NONE.value
        else:
            drift_res = self._drift.detect_schema_changes(self._baseline_snapshot, snapshot)
            drift_sev = drift_res.overall_severity.value
        self._batches_processed += 1
        self._cumulative_cdc_events += len(events)
        summary: dict[str, Any] = {
            "capability": "data_pipeline",
            "source": self._source_label,
            "batches_processed": self._batches_processed,
            "schema_status": proposal.status.value,
            "fields_count": len(proposal.fields),
            "fields": [
                {
                    "name": f.name,
                    "wire_type": f.wire_type.value,
                    "semantic_type": f.semantic_type.value,
                    "confidence": round(f.confidence, 3),
                }
                for f in proposal.fields
            ],
            "batch_cdc_events": len(events),
            "cumulative_cdc_events": self._cumulative_cdc_events,
            "cvs_overall_score": cvs_result.overall_score,
            "drift_severity": drift_sev,
        }
        self._latest_summary = summary
        return dict(summary)


def _render_pipeline_card(summary: Mapping[str, Any]) -> str:
    fields_raw = summary.get("fields", [])
    rows = list(fields_raw) if isinstance(fields_raw, list) else []
    body_html = SafeHTML(
        render_kpi_stat(label="CVS Score", value=f"{summary['cvs_overall_score']:.2f}").value
        + render_kpi_stat(label="CDC Events", value=str(summary["cumulative_cdc_events"])).value
        + render_kpi_stat(label="Drift", value=str(summary["drift_severity"])).value
        + render_table(
            columns=(
                ("name", "Field"),
                ("wire_type", "Wire Type"),
                ("semantic_type", "Semantic Type"),
                ("confidence", "Confidence"),
            ),
            rows=rows,
            empty_message="No batches ingested yet.",
        ).value
    )
    return render_card(
        title=f"Data Pipeline ({summary['source']})",
        badge=str(summary["schema_status"]),
        body=body_html,
    ).value


def create_data_pipeline_router(
    *,
    source_label: str = "dataset",
    seed_records: Sequence[Mapping[str, Any]] = (),
    prefix: str = DEFAULT_DATA_PIPELINE_PREFIX,
) -> APIRouter:
    """Create a domain-neutral Data Pipeline APIRouter binding zcg.platform to zcg.web."""
    runtime = DataPipelineRuntime(source_label=source_label, seed_records=seed_records)
    router = APIRouter(prefix=prefix, tags=("data-pipeline",))

    @router.get("", summary="Inspect current DataPipelineRuntime schema, CDC, CVS, and drift state")
    def inspect_pipeline(req: Request) -> WebResponse:
        summary = runtime.current_summary()
        return respond(req, html_fragment=_render_pipeline_card(summary), data=summary)

    @router.post("", summary="Ingest dataset batch through SchemaDiscovery, CDC, CVS, and drift")
    def ingest_pipeline_batch(req: Request) -> WebResponse:
        payload = req.json() if req.body else None
        if not isinstance(payload, dict):
            raise WebAppError(
                "Pipeline payload must be a JSON object",
                error_code="INVALID_PIPELINE_PAYLOAD",
                http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        raw_recs = payload.get("records")
        if (
            not isinstance(raw_recs, list)
            or not raw_recs
            or not all(isinstance(item, dict) for item in raw_recs)
        ):
            raise WebAppError(
                "Field 'records' must be a non-empty list of JSON objects",
                error_code="INVALID_PIPELINE_RECORDS",
                http_status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        summary = runtime.ingest_batch(raw_recs)
        return respond(
            req,
            html_fragment=_render_pipeline_card(summary),
            data=summary,
            headers=build_swap_response_headers(trigger="dataPipelineEvaluated"),
        )

    return router
