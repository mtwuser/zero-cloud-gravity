"""Unit test suite for src/zcg/platform/cvs.py.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import pytest

from zcg.platform.cvs import (
    ContinuousValidationScorer,
    DatasetValidationSnapshot,
    DriftSeverity,
    FieldValidationMetric,
    SchemaDriftDetector,
    classify_drift_severity,
)
from zcg.platform.type_registry import SemanticType


class TestCVS:
    """Verify ContinuousValidationScorer, cut-point severity classification, and DriftDetector."""

    def test_field_metric_validation_and_empty_or_single_type_scoring_expected(self) -> None:
        """Verify FieldValidationMetric bounds and scorer behavior on empty/uniform snapshots."""
        # Arrange
        scorer = ContinuousValidationScorer()
        empty_snap = DatasetValidationSnapshot(source="empty", total_records=0)
        single_snap = DatasetValidationSnapshot(
            source="uniform",
            total_records=5,
            expected_field_count=2,
            fields=(FieldValidationMetric("id", 0.0, 1.0, SemanticType.IDENTIFIER),),
        )

        # Act
        empty_res = scorer.score(empty_snap)
        single_res = scorer.score(single_snap)

        # Assert
        assert empty_res.completeness_score == 1.0
        assert empty_res.entropy_score == 0.0
        assert single_res.completeness_score == 0.5
        assert single_res.entropy_score == 0.0
        with pytest.raises(ValueError, match="must not be blank"):
            FieldValidationMetric("  ", 0.0, 1.0, SemanticType.IDENTIFIER)
        with pytest.raises(ValueError, match="null_ratio"):
            FieldValidationMetric("id", 1.1, 1.0, SemanticType.IDENTIFIER)
        with pytest.raises(ValueError, match="type_consistency"):
            FieldValidationMetric("id", 0.0, -0.1, SemanticType.IDENTIFIER)

    def test_diverse_scoring_and_drift_severity_cut_points_expected(self) -> None:
        """Verify weighted scoring, N vs N+-1 drift cut-points, and schema change detection."""
        # Arrange
        scorer = ContinuousValidationScorer()
        detector = SchemaDriftDetector()
        base_snap = DatasetValidationSnapshot(
            source="sci_corpus",
            total_records=100,
            expected_field_count=2,
            fields=(
                FieldValidationMetric("id", 0.0, 1.0, SemanticType.IDENTIFIER),
                FieldValidationMetric("ts", 0.0, 1.0, SemanticType.TEMPORAL),
            ),
        )
        degraded_snap = DatasetValidationSnapshot(
            source="sci_corpus",
            total_records=100,
            expected_field_count=2,
            fields=(
                FieldValidationMetric("id", 0.40, 0.60, SemanticType.IDENTIFIER),
                FieldValidationMetric("new_col", 0.40, 0.60, SemanticType.NATURAL_TEXT),
            ),
        )

        # Act
        base_score = scorer.score(base_snap)
        curr_score = scorer.score(degraded_snap)
        score_drift = detector.compare_scores(base_score, curr_score)
        schema_changed = detector.detect_schema_changes(base_snap, degraded_snap)
        schema_same = detector.detect_schema_changes(base_snap, base_snap)

        # Assert
        assert base_score.overall_score == 1.0
        assert base_score.to_dict()["overall_score"] == 1.0
        assert classify_drift_severity(0.049) == DriftSeverity.NONE
        assert classify_drift_severity(0.05) == DriftSeverity.LOW
        assert classify_drift_severity(0.10) == DriftSeverity.MEDIUM
        assert classify_drift_severity(0.20) == DriftSeverity.HIGH
        assert classify_drift_severity(-0.35) == DriftSeverity.CRITICAL
        assert score_drift.overall_severity == DriftSeverity.HIGH
        assert score_drift.to_dict()["has_schema_change"] is False
        assert schema_changed.has_schema_change is True
        assert schema_changed.fields_added == ("new_col",)
        assert schema_changed.fields_removed == ("ts",)
        assert schema_changed.overall_severity == DriftSeverity.HIGH
        assert schema_same.overall_severity == DriftSeverity.NONE
