"""Continuous Validation Scoring (CVS) and Statistical Schema Drift Detection.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from zcg.platform.type_registry import SemanticType

WEIGHT_COMPLETENESS: Final[float] = 0.25
WEIGHT_CONSISTENCY: Final[float] = 0.30
WEIGHT_NULL_HEALTH: Final[float] = 0.25
WEIGHT_ENTROPY: Final[float] = 0.20

DRIFT_THRESHOLD_LOW: Final[float] = 0.05
DRIFT_THRESHOLD_MEDIUM: Final[float] = 0.10
DRIFT_THRESHOLD_HIGH: Final[float] = 0.20
DRIFT_THRESHOLD_CRITICAL: Final[float] = 0.35


@dataclass(frozen=True, slots=True)
class FieldValidationMetric:
    """Validation health metrics for a single dataset field."""

    name: str
    null_ratio: float
    type_consistency: float
    semantic_type: SemanticType

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("FieldValidationMetric.name must not be blank")
        if not 0.0 <= self.null_ratio <= 1.0:
            raise ValueError("null_ratio must be in [0.0, 1.0]")
        if not 0.0 <= self.type_consistency <= 1.0:
            raise ValueError("type_consistency must be in [0.0, 1.0]")


@dataclass(frozen=True, slots=True)
class DatasetValidationSnapshot:
    """Point-in-time dataset validation metrics evaluated by ContinuousValidationScorer."""

    source: str
    total_records: int
    fields: tuple[FieldValidationMetric, ...] = ()
    expected_field_count: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ValidationScoreResult:
    """Composite and per-dimension Continuous Validation Score in [0.0, 1.0]."""

    source: str
    timestamp: datetime
    overall_score: float
    completeness_score: float
    consistency_score: float
    null_health_score: float
    entropy_score: float

    def to_dict(self) -> dict[str, object]:
        """Serialize validation score result to a JSON-compatible dictionary."""
        return {
            "source": self.source,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "overall_score": self.overall_score,
            "completeness_score": self.completeness_score,
            "consistency_score": self.consistency_score,
            "null_health_score": self.null_health_score,
            "entropy_score": self.entropy_score,
        }


class DriftSeverity(StrEnum):
    """Severity bands for detected statistical or structural schema drift."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class DimensionDrift:
    """Drift delta and severity for a single validation dimension."""

    dimension: str
    baseline_value: float
    current_value: float
    delta: float
    severity: DriftSeverity


@dataclass(frozen=True, slots=True)
class SchemaDriftReport:
    """Aggregate report produced by SchemaDriftDetector."""

    source: str
    overall_drift: float
    overall_severity: DriftSeverity
    dimensions: tuple[DimensionDrift, ...] = ()
    fields_added: tuple[str, ...] = ()
    fields_removed: tuple[str, ...] = ()
    has_schema_change: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize schema drift report to a JSON-compatible dictionary."""
        return {
            "source": self.source,
            "overall_drift": self.overall_drift,
            "overall_severity": self.overall_severity.value,
            "fields_added": list(self.fields_added),
            "fields_removed": list(self.fields_removed),
            "has_schema_change": self.has_schema_change,
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "baseline_value": d.baseline_value,
                    "current_value": d.current_value,
                    "delta": d.delta,
                    "severity": d.severity.value,
                }
                for d in self.dimensions
            ],
        }


def classify_drift_severity(delta: float) -> DriftSeverity:
    """Classify absolute score delta against nominal drift cut-points."""
    abs_delta = round(abs(delta), 6)
    if abs_delta >= DRIFT_THRESHOLD_CRITICAL:
        return DriftSeverity.CRITICAL
    if abs_delta >= DRIFT_THRESHOLD_HIGH:
        return DriftSeverity.HIGH
    if abs_delta >= DRIFT_THRESHOLD_MEDIUM:
        return DriftSeverity.MEDIUM
    if abs_delta >= DRIFT_THRESHOLD_LOW:
        return DriftSeverity.LOW
    return DriftSeverity.NONE


class ContinuousValidationScorer:
    """Computes Continuous Validation Scores from DatasetValidationSnapshot metrics."""

    def score(self, snapshot: DatasetValidationSnapshot) -> ValidationScoreResult:
        """Evaluate completeness, consistency, null health, and semantic entropy."""
        completeness = self._score_completeness(snapshot)
        consistency = self._score_consistency(snapshot)
        null_health = self._score_null_health(snapshot)
        entropy = self._score_entropy(snapshot)
        overall = (
            WEIGHT_COMPLETENESS * completeness
            + WEIGHT_CONSISTENCY * consistency
            + WEIGHT_NULL_HEALTH * null_health
            + WEIGHT_ENTROPY * entropy
        )
        return ValidationScoreResult(
            source=snapshot.source,
            timestamp=snapshot.timestamp,
            overall_score=round(overall, 4),
            completeness_score=round(completeness, 4),
            consistency_score=round(consistency, 4),
            null_health_score=round(null_health, 4),
            entropy_score=round(entropy, 4),
        )

    @staticmethod
    def _score_completeness(snapshot: DatasetValidationSnapshot) -> float:
        if snapshot.expected_field_count <= 0:
            return 1.0
        return min(len(snapshot.fields) / snapshot.expected_field_count, 1.0)

    @staticmethod
    def _score_consistency(snapshot: DatasetValidationSnapshot) -> float:
        if not snapshot.fields:
            return 1.0
        return sum(f.type_consistency for f in snapshot.fields) / len(snapshot.fields)

    @staticmethod
    def _score_null_health(snapshot: DatasetValidationSnapshot) -> float:
        if not snapshot.fields:
            return 1.0
        return 1.0 - (sum(f.null_ratio for f in snapshot.fields) / len(snapshot.fields))

    @staticmethod
    def _score_entropy(snapshot: DatasetValidationSnapshot) -> float:
        type_counts = Counter(f.semantic_type for f in snapshot.fields)
        num_types = len(type_counts)
        if num_types <= 1:
            return 0.0
        total = sum(type_counts.values())
        entropy = -sum((cnt / total) * math.log2(cnt / total) for cnt in type_counts.values())
        return entropy / math.log2(num_types)


class SchemaDriftDetector:
    """Compares validation score snapshots and field sets for drift and schema changes."""

    def compare_scores(
        self, baseline: ValidationScoreResult, current: ValidationScoreResult
    ) -> SchemaDriftReport:
        """Compute per-dimension and overall drift between baseline and current scores."""
        pairs = (
            ("completeness", baseline.completeness_score, current.completeness_score),
            ("consistency", baseline.consistency_score, current.consistency_score),
            ("null_health", baseline.null_health_score, current.null_health_score),
            ("entropy", baseline.entropy_score, current.entropy_score),
        )
        dims = tuple(
            DimensionDrift(
                dimension=name,
                baseline_value=round(bval, 4),
                current_value=round(cval, 4),
                delta=round(cval - bval, 4),
                severity=classify_drift_severity(cval - bval),
            )
            for name, bval, cval in pairs
        )
        overall_delta = round(current.overall_score - baseline.overall_score, 4)
        return SchemaDriftReport(
            source=current.source,
            overall_drift=overall_delta,
            overall_severity=classify_drift_severity(overall_delta),
            dimensions=dims,
        )

    def detect_schema_changes(
        self, baseline: DatasetValidationSnapshot, current: DatasetValidationSnapshot
    ) -> SchemaDriftReport:
        """Detect added or removed field names between two dataset snapshots."""
        base_names = {f.name for f in baseline.fields}
        curr_names = {f.name for f in current.fields}
        added = tuple(sorted(curr_names - base_names))
        removed = tuple(sorted(base_names - curr_names))
        changed = bool(added or removed)
        return SchemaDriftReport(
            source=current.source,
            overall_drift=0.0,
            overall_severity=DriftSeverity.HIGH if changed else DriftSeverity.NONE,
            fields_added=added,
            fields_removed=removed,
            has_schema_change=changed,
        )
