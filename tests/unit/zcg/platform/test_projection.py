"""Unit test suite for src/zcg/platform/projection.py.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import pytest

from zcg.platform.projection import (
    AdaptiveThresholdPromoter,
    DisclosureTier,
    ExchangeStage,
    PayloadFieldSegment,
    RolePayloadProjector,
    ThresholdObservation,
)


class TestProjection:
    """Verify RolePayloadProjector across HR/B2B stages and AdaptiveThresholdPromoter."""

    def test_projector_validation_guards_expected(self) -> None:
        """Verify bipolar validation on RolePayloadProjector and PayloadFieldSegment."""
        # Arrange
        projector = RolePayloadProjector(drop_off_threshold=0.40)

        # Act
        threshold = projector.drop_off_threshold

        # Assert
        assert threshold == 0.40
        with pytest.raises(ValueError, match="drop_off_threshold"):
            RolePayloadProjector(drop_off_threshold=0.0)
        with pytest.raises(ValueError, match="field_id"):
            PayloadFieldSegment("  ", DisclosureTier.CORE_SUMMARY, "x")
        with pytest.raises(ValueError, match="must not be blank"):
            projector.project(
                resource_id="",
                target_node_id="org-alpha",
                stage=ExchangeStage.PUBLIC_OVERVIEW,
                segments=(),
            )
        with pytest.raises(ValueError, match="drop_off_rate"):
            projector.project(
                resource_id="cand-1",
                target_node_id="org-alpha",
                stage=ExchangeStage.PUBLIC_OVERVIEW,
                segments=(),
                drop_off_rate=1.2,
            )

    def test_hr_candidate_vs_day1_onboarding_and_b2b_projection_expected(self) -> None:
        """Verify PII withholding during candidate/B2B stages and full Day-1 disclosure."""
        # Arrange
        projector = RolePayloadProjector(drop_off_threshold=0.40)
        segments = (
            PayloadFieldSegment("headline", DisclosureTier.CORE_SUMMARY, "Systems Engineer"),
            PayloadFieldSegment(
                "distributed_systems",
                DisclosureTier.VERIFIED_COMPETENCY,
                "M3 Verified",
                citation_receipt="alex-tutor::SYLLABUS.md#dist-sys@0123456789abcdef:E2",
            ),
            PayloadFieldSegment("tax_iban_record", DisclosureTier.DAY1_ONBOARDING, "ES00-0000"),
            PayloadFieldSegment("case_study_notes", DisclosureTier.DEEP_CONTEXT, " Extended text "),
        )

        # Act
        cand_cap = projector.project(
            resource_id="profile-001",
            target_node_id="org-alpha",
            stage=ExchangeStage.CANDIDATE_APPLICATION,
            segments=segments,
            drop_off_rate=0.45,
            shared_packs=("software-engineering",),
        )
        b2b_cap = projector.project(
            resource_id="profile-001",
            target_node_id="corp-alpha",
            stage=ExchangeStage.B2B_PROPOSAL,
            segments=segments,
            drop_off_rate=0.10,
            shared_packs=("software-engineering", "nist-csf-security"),
        )
        day1_cap = projector.project(
            resource_id="profile-001",
            target_node_id="org-alpha",
            stage=ExchangeStage.DAY1_ONBOARDING,
            segments=segments,
            drop_off_rate=0.10,
        )

        # Assert
        assert "tax_iban_record" not in cand_cap.disclosed_fields
        assert cand_cap.withheld_field_ids == ("tax_iban_record", "case_study_notes")
        assert cand_cap.shared_packs == ()
        assert cand_cap.recommended_zone == "Z2"
        assert len(cand_cap.citation_receipts) == 1
        assert cand_cap.to_dict()["is_filtered"] is True
        assert "tax_iban_record" not in b2b_cap.disclosed_fields
        assert b2b_cap.shared_packs == ("software-engineering", "nist-csf-security")
        assert "tax_iban_record" in day1_cap.disclosed_fields
        assert day1_cap.is_filtered is False
        assert day1_cap.recommended_zone == "Z1"

    def test_adaptive_threshold_promoter_streak_reset_and_promotion_expected(self) -> None:
        """Verify hysteresis streak accumulation, sub-threshold reset, and proposal emission."""
        # Arrange
        promoter = AdaptiveThresholdPromoter(
            min_cycles=2, min_validation_delta=0.05, min_delivery_delta=0.01
        )
        qualifying = ThresholdObservation(
            policy_id="pol-z2-swap",
            target_surface="/knowledge/search",
            channel_from="Z1:T1",
            channel_to="Z2:T1",
            validation_delta=0.08,
            delivery_delta=0.04,
            health_score=92.0,
        )
        failing = ThresholdObservation(
            policy_id="pol-z2-swap",
            target_surface="/knowledge/search",
            channel_from="Z1:T1",
            channel_to="Z2:T1",
            validation_delta=0.01,
            delivery_delta=0.04,
        )

        # Act
        first = promoter.record(qualifying)
        after_fail = promoter.record(failing)
        streak_after_fail = promoter.streak_length("pol-z2-swap")
        promoter.record(qualifying)
        proposal = promoter.record(qualifying, parent_digest="abc123")
        promoter.reset()

        # Assert
        assert first is None
        assert after_fail is None
        assert streak_after_fail == 0
        assert proposal is not None
        assert proposal.observed_cycles == 2
        assert proposal.mean_validation_delta == 0.08
        assert proposal.to_dict()["parent_digest"] == "abc123"
        assert promoter.streak_length("pol-z2-swap") == 0
        with pytest.raises(ValueError, match="min_cycles"):
            AdaptiveThresholdPromoter(min_cycles=0)
        with pytest.raises(ValueError, match="policy_id"):
            ThresholdObservation("", "/s", "Z1:T1", "Z2:T1", 0.1, 0.1)
        with pytest.raises(ValueError, match="health_score"):
            ThresholdObservation("pol", "/s", "Z1:T1", "Z2:T1", 0.1, 0.1, health_score=105.0)
