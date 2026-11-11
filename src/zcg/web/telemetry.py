"""Multi-grade runtime telemetry scorer, route signal collector, and SQLite Audit DAG.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import statistics
import uuid
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from zcg.core.manifests import ensure_contained_path
from zcg.web.channels import BaseStrEnum

WEIGHT_VOLUME: Final[float] = 0.30
WEIGHT_LATENCY: Final[float] = 0.25
WEIGHT_SUCCESS: Final[float] = 0.30
WEIGHT_TREND: Final[float] = 0.15

MIN_RATIO: Final[float] = 0.0
MAX_RATIO: Final[float] = 1.0
SCORE_SCALE_MAX: Final[float] = 100.0

OPTIMAL_SCORE_MIN: Final[float] = 80.0
DEGRADED_SCORE_MIN: Final[float] = 55.0
PROTECTIVE_SCORE_MIN: Final[float] = 30.0
PROMOTE_SCORE_MIN: Final[float] = 85.0
RETIRE_SCORE_MAX: Final[float] = 20.0

DEFAULT_MAX_ROUTE_SIGNALS: Final[int] = 256
LATENCY_PENALTY_SPAN_MS: Final[float] = 1000.0
AUDIT_DB_REL_PATH: Final[str] = ".agents/telemetry/runtime_audit_dag.sqlite3"
GENESIS_PARENT_HASH: Final[str] = "0" * 64


class TelemetryGrade(BaseStrEnum):
    """Progressive runtime observability and automation governance grade."""

    G1_OBSERVE = "G1"
    G2_ADVISE = "G2"
    G3_AUTOMATE = "G3"


class HealthRegime(BaseStrEnum):
    """Objective 4-state operational health regime for web/API endpoints."""

    OPTIMAL = "OPTIMAL"
    DEGRADED = "DEGRADED"
    PROTECTIVE = "PROTECTIVE"
    CRITICAL = "CRITICAL"


class TransitionAction(BaseStrEnum):
    """Recommended channel or lifecycle action derived from composite health score."""

    STABLE = "STABLE"
    CHANNEL_PROMOTE = "CHANNEL_PROMOTE"
    CHANNEL_DEMOTE = "CHANNEL_DEMOTE"
    RETIREMENT = "RETIREMENT"


def _clamp_unit(value: float) -> float:
    return min(MAX_RATIO, max(MIN_RATIO, float(value)))


@dataclass(frozen=True, slots=True)
class EndpointTelemetryInput:
    """Normalized [0.0..1.0] operational telemetry signals for composite scoring."""

    volume_ratio: float = MAX_RATIO
    latency_health_ratio: float = MAX_RATIO
    success_ratio: float = MAX_RATIO
    trend_ratio: float = MAX_RATIO


@dataclass(frozen=True, slots=True)
class TelemetryScoreReport:
    """Composite runtime health score, regime, and G1..G3 transition decision."""

    score: float
    normalized_score: float
    regime: HealthRegime
    grade: TelemetryGrade
    recommended_action: TransitionAction
    auto_eligible: bool


class RuntimeTelemetryScorer:
    """Evaluate 4-weight composite health scores and G1..G3 transition eligibility."""

    def __init__(self, *, grade: TelemetryGrade = TelemetryGrade.G1_OBSERVE) -> None:
        self._grade = grade

    @property
    def grade(self) -> TelemetryGrade:
        """Return the configured observability governance grade (G1, G2, or G3)."""
        return self._grade

    def evaluate(self, metrics: EndpointTelemetryInput) -> TelemetryScoreReport:
        """Compute weighted score [0..100], HealthRegime, and TransitionAction."""
        norm = (
            WEIGHT_VOLUME * _clamp_unit(metrics.volume_ratio)
            + WEIGHT_LATENCY * _clamp_unit(metrics.latency_health_ratio)
            + WEIGHT_SUCCESS * _clamp_unit(metrics.success_ratio)
            + WEIGHT_TREND * _clamp_unit(metrics.trend_ratio)
        )
        score = round(norm * SCORE_SCALE_MAX, 2)
        if score >= OPTIMAL_SCORE_MIN:
            regime = HealthRegime.OPTIMAL
        elif score >= DEGRADED_SCORE_MIN:
            regime = HealthRegime.DEGRADED
        elif score >= PROTECTIVE_SCORE_MIN:
            regime = HealthRegime.PROTECTIVE
        else:
            regime = HealthRegime.CRITICAL

        if score >= PROMOTE_SCORE_MIN:
            action = TransitionAction.CHANNEL_PROMOTE
        elif score >= DEGRADED_SCORE_MIN:
            action = TransitionAction.STABLE
        elif score > RETIRE_SCORE_MAX:
            action = TransitionAction.CHANNEL_DEMOTE
        else:
            action = TransitionAction.RETIREMENT

        auto_ok = self._grade == TelemetryGrade.G3_AUTOMATE and action != TransitionAction.STABLE
        return TelemetryScoreReport(
            score=score,
            normalized_score=round(norm, 4),
            regime=regime,
            grade=self._grade,
            recommended_action=action,
            auto_eligible=auto_ok,
        )


@dataclass(frozen=True, slots=True)
class RequestSignal:
    """Immutable per-request latency and HTTP status observation."""

    method: str
    route: str
    status_code: int
    latency_ms: float


class RouteSignalCollector:
    """Bounded per-instance ring buffer summarizing route latency and error rates."""

    def __init__(self, *, max_signals: int = DEFAULT_MAX_ROUTE_SIGNALS) -> None:
        if max_signals < 1:
            raise ValueError(f"max_signals must be >= 1, got {max_signals}")
        self._max_signals = max_signals
        self._signals: deque[RequestSignal] = deque(maxlen=max_signals)

    def record(
        self, *, method: str, route: str, status_code: int, latency_ms: float
    ) -> RequestSignal:
        """Record a single request telemetry observation."""
        sig = RequestSignal(method.upper(), route, int(status_code), max(0.0, float(latency_ms)))
        self._signals.append(sig)
        return sig

    def signals(self) -> tuple[RequestSignal, ...]:
        """Return all retained signals in chronological order."""
        return tuple(self._signals)

    def derive_telemetry_input(self) -> EndpointTelemetryInput:
        """Project collected signals into normalized EndpointTelemetryInput ratios."""
        if not self._signals:
            return EndpointTelemetryInput()
        n = len(self._signals)
        ok_ratio = sum(1 for s in self._signals if s.status_code < 500) / n
        mean_ms = statistics.fmean(s.latency_ms for s in self._signals)
        lat_ratio = _clamp_unit(1.0 - (mean_ms / LATENCY_PENALTY_SPAN_MS))
        vol_ratio = _clamp_unit(max(0.5, n / self._max_signals))
        return EndpointTelemetryInput(
            volume_ratio=vol_ratio,
            latency_health_ratio=lat_ratio,
            success_ratio=ok_ratio,
            trend_ratio=ok_ratio,
        )

    def route_summary(self) -> dict[str, dict[str, float | int]]:
        """Aggregate request count, 5xx error count, and mean latency per route."""
        buckets: dict[str, list[RequestSignal]] = {}
        for sig in self._signals:
            buckets.setdefault(f"{sig.method} {sig.route}", []).append(sig)
        return {
            key: {
                "count": len(items),
                "errors": sum(1 for x in items if x.status_code >= 500),
                "mean_latency_ms": round(statistics.fmean(x.latency_ms for x in items), 2),
            }
            for key, items in sorted(buckets.items())
        }


@dataclass(frozen=True, slots=True)
class AuditDecisionNode:
    """Immutable SHA-256 hash-chained runtime governance decision record."""

    node_id: str
    parent_hash: str
    layer_id: str
    grade: TelemetryGrade
    regime: HealthRegime
    action: TransitionAction
    score: float
    rationale: str
    recorded_at_utc: str
    node_hash: str


def compute_audit_node_hash(
    *,
    node_id: str,
    parent_hash: str,
    layer_id: str,
    grade: TelemetryGrade,
    regime: HealthRegime,
    action: TransitionAction,
    score: float,
    rationale: str,
    recorded_at_utc: str,
) -> str:
    """Compute a canonical SHA-256 digest chaining parent_hash to decision fields."""
    canonical_map = {
        "action": action.value, "grade": grade.value, "layer_id": layer_id,
        "node_id": node_id, "parent_hash": parent_hash, "rationale": rationale,
        "recorded_at_utc": recorded_at_utc, "regime": regime.value,
        "score": round(float(score), 2),
    }  # fmt: skip
    canonical = json.dumps(canonical_map, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TelemetryAuditDAG:
    """SQLite WAL append-only hash-chained audit ledger under .agents/telemetry/."""

    def __init__(self, workspace_root: Path, *, rel_db_path: str = AUDIT_DB_REL_PATH) -> None:
        ws = workspace_root.resolve()
        self._db_path = ensure_contained_path(ws / rel_db_path, ws)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    @property
    def db_path(self) -> Path:
        """Return the resolved SQLite database file path inside the workspace."""
        return self._db_path

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS telemetry_audit_dag ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT NOT NULL UNIQUE, "
                "parent_hash TEXT NOT NULL, layer_id TEXT NOT NULL, grade TEXT NOT NULL, "
                "regime TEXT NOT NULL, action TEXT NOT NULL, score REAL NOT NULL, "
                "rationale TEXT NOT NULL, recorded_at_utc TEXT NOT NULL, "
                "node_hash TEXT NOT NULL UNIQUE)"
            )

    def append_decision(
        self, *, layer_id: str, report: TelemetryScoreReport, rationale: str,
        node_id: str | None = None, recorded_at_utc: str | None = None,
    ) -> AuditDecisionNode:  # fmt: skip
        """Append a SHA-256 parent-chained decision node to the SQLite WAL ledger."""
        resolved_id = node_id or f"aud-{uuid.uuid4().hex}"
        resolved_ts = recorded_at_utc or datetime.now(UTC).isoformat()
        rounded_score = round(float(report.score), 2)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT node_hash FROM telemetry_audit_dag ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            parent_hash = str(row[0]) if row is not None else GENESIS_PARENT_HASH
            digest = compute_audit_node_hash(
                node_id=resolved_id, parent_hash=parent_hash, layer_id=layer_id,
                grade=report.grade, regime=report.regime, action=report.recommended_action,
                score=rounded_score, rationale=rationale, recorded_at_utc=resolved_ts,
            )  # fmt: skip
            vals = (
                resolved_id, parent_hash, layer_id, report.grade.value,
                report.regime.value, report.recommended_action.value,
                rounded_score, rationale, resolved_ts, digest,
            )  # fmt: skip
            conn.execute(
                "INSERT INTO telemetry_audit_dag ("
                "node_id, parent_hash, layer_id, grade, regime, action, "
                "score, rationale, recorded_at_utc, node_hash"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                vals,
            )
        return AuditDecisionNode(
            resolved_id, parent_hash, layer_id, report.grade, report.regime,
            report.recommended_action, rounded_score, rationale, resolved_ts, digest,
        )  # fmt: skip

    def list_nodes(self) -> tuple[AuditDecisionNode, ...]:
        """Return all persisted audit decision nodes in append sequence order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT node_id, parent_hash, layer_id, grade, regime, action, "
                "score, rationale, recorded_at_utc, node_hash "
                "FROM telemetry_audit_dag ORDER BY seq ASC"
            ).fetchall()
        out: list[AuditDecisionNode] = []
        for r in rows:
            item = AuditDecisionNode(
                str(r[0]), str(r[1]), str(r[2]), TelemetryGrade(str(r[3])),
                HealthRegime(str(r[4])), TransitionAction(str(r[5])),
                float(r[6]), str(r[7]), str(r[8]), str(r[9]),
            )  # fmt: skip
            out.append(item)
        return tuple(out)

    def verify_integrity(self) -> bool:
        """Verify parent-hash continuity and SHA-256 payload digests from genesis."""
        expected_parent = GENESIS_PARENT_HASH
        for node in self.list_nodes():
            if node.parent_hash != expected_parent:
                return False
            recomputed = compute_audit_node_hash(
                node_id=node.node_id, parent_hash=node.parent_hash, layer_id=node.layer_id,
                grade=node.grade, regime=node.regime, action=node.action,
                score=node.score, rationale=node.rationale, recorded_at_utc=node.recorded_at_utc,
            )  # fmt: skip
            if node.node_hash != recomputed:
                return False
            expected_parent = node.node_hash
        return True
