"""Role-Scoped Payload Projection and Hysteresis Threshold Promotion Engine.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

DEFAULT_DROP_OFF_THRESHOLD: Final[float] = 0.40
DEFAULT_PROMOTION_MIN_CYCLES: Final[int] = 3
DEFAULT_MIN_VALIDATION_DELTA: Final[float] = 0.05
DEFAULT_MIN_DELIVERY_DELTA: Final[float] = 0.0


class DisclosureTier(StrEnum):
    """Sensitivity and progressive-disclosure strata for sovereign payload fields."""

    CORE_SUMMARY = "core_summary"
    VERIFIED_COMPETENCY = "verified_competency"
    DAY1_ONBOARDING = "day1_onboarding"
    DEEP_CONTEXT = "deep_context"


class ExchangeStage(StrEnum):
    """Inter-node handshake stages governing field disclosure and shared rule packs."""

    PUBLIC_OVERVIEW = "public_overview"
    CANDIDATE_APPLICATION = "candidate_application"
    B2B_PROPOSAL = "b2b_proposal"
    DAY1_ONBOARDING = "day1_onboarding"


STAGE_DISCLOSURE_TIERS: Final[dict[ExchangeStage, frozenset[DisclosureTier]]] = {
    ExchangeStage.PUBLIC_OVERVIEW: frozenset(
        {DisclosureTier.CORE_SUMMARY, DisclosureTier.DEEP_CONTEXT}
    ),
    ExchangeStage.CANDIDATE_APPLICATION: frozenset(
        {
            DisclosureTier.CORE_SUMMARY,
            DisclosureTier.VERIFIED_COMPETENCY,
            DisclosureTier.DEEP_CONTEXT,
        }
    ),
    ExchangeStage.B2B_PROPOSAL: frozenset(
        {
            DisclosureTier.CORE_SUMMARY,
            DisclosureTier.VERIFIED_COMPETENCY,
            DisclosureTier.DEEP_CONTEXT,
        }
    ),
    ExchangeStage.DAY1_ONBOARDING: frozenset(
        {
            DisclosureTier.CORE_SUMMARY,
            DisclosureTier.VERIFIED_COMPETENCY,
            DisclosureTier.DAY1_ONBOARDING,
            DisclosureTier.DEEP_CONTEXT,
        }
    ),
}


@dataclass(frozen=True, slots=True)
class PayloadFieldSegment:
    """Single typed field segment inside a master sovereign profile or resource."""

    field_id: str
    tier: DisclosureTier
    value: Any
    citation_receipt: str | None = None

    def __post_init__(self) -> None:
        if not self.field_id.strip():
            raise ValueError("PayloadFieldSegment.field_id must not be blank")


@dataclass(frozen=True, slots=True)
class ProjectedRoleCapsule:
    """Non-destructive role-scoped capsule projected for an inter-node handshake."""

    resource_id: str
    target_node_id: str
    stage: ExchangeStage
    is_filtered: bool
    disclosed_fields: dict[str, Any]
    withheld_field_ids: tuple[str, ...]
    citation_receipts: tuple[str, ...]
    shared_packs: tuple[str, ...]
    recommended_zone: str
    payload_digest: str

    def to_dict(self) -> dict[str, object]:
        """Serialize projected capsule to a JSON-compatible dictionary."""
        return {
            "resource_id": self.resource_id,
            "target_node_id": self.target_node_id,
            "stage": self.stage.value,
            "is_filtered": self.is_filtered,
            "disclosed_fields": dict(self.disclosed_fields),
            "withheld_field_ids": list(self.withheld_field_ids),
            "citation_receipts": list(self.citation_receipts),
            "shared_packs": list(self.shared_packs),
            "recommended_zone": self.recommended_zone,
            "payload_digest": self.payload_digest,
        }


class RolePayloadProjector:
    """Projects sovereign resources across DisclosureTier x ExchangeStage boundaries."""

    def __init__(self, *, drop_off_threshold: float = DEFAULT_DROP_OFF_THRESHOLD) -> None:
        if not 0.0 < drop_off_threshold <= 1.0:
            raise ValueError("drop_off_threshold must be in (0.0, 1.0]")
        self._drop_off_threshold = drop_off_threshold

    @property
    def drop_off_threshold(self) -> float:
        """Return configured channel drop-off threshold."""
        return self._drop_off_threshold

    def project(
        self,
        *,
        resource_id: str,
        target_node_id: str,
        stage: ExchangeStage,
        segments: Sequence[PayloadFieldSegment],
        drop_off_rate: float = 0.0,
        shared_packs: Sequence[str] = (),
    ) -> ProjectedRoleCapsule:
        """Derive a minimal-disclosure or onboarding capsule without mutating source data."""
        clean_res = resource_id.strip()
        clean_tgt = target_node_id.strip()
        if not clean_res or not clean_tgt:
            raise ValueError("resource_id and target_node_id must not be blank")
        if not 0.0 <= drop_off_rate <= 1.0:
            raise ValueError("drop_off_rate must be in [0.0, 1.0]")

        allowed_tiers = STAGE_DISCLOSURE_TIERS[stage]
        defer_deep = drop_off_rate >= self._drop_off_threshold
        disclosed: dict[str, Any] = {}
        withheld: list[str] = []
        raw_receipts: list[str] = []

        for seg in segments:
            can_disclose = seg.tier in allowed_tiers and not (
                defer_deep and seg.tier == DisclosureTier.DEEP_CONTEXT
            )
            if can_disclose:
                disclosed[seg.field_id] = seg.value
                if seg.citation_receipt:
                    raw_receipts.append(seg.citation_receipt)
            else:
                withheld.append(seg.field_id)

        receipts = tuple(dict.fromkeys(raw_receipts))
        packs = (
            tuple(dict.fromkeys(p.strip() for p in shared_packs if p.strip()))
            if stage == ExchangeStage.B2B_PROPOSAL
            else ()
        )
        is_filtered = bool(withheld)
        envelope = json.dumps(
            {
                "resource_id": clean_res,
                "target_node_id": clean_tgt,
                "stage": stage.value,
                "disclosed": disclosed,
                "receipts": list(receipts),
                "shared_packs": list(packs),
            },
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(envelope.encode("utf-8")).hexdigest()
        return ProjectedRoleCapsule(
            resource_id=clean_res,
            target_node_id=clean_tgt,
            stage=stage,
            is_filtered=is_filtered,
            disclosed_fields=disclosed,
            withheld_field_ids=tuple(withheld),
            citation_receipts=receipts,
            shared_packs=packs,
            recommended_zone="Z2" if is_filtered else "Z1",
            payload_digest=digest,
        )


@dataclass(frozen=True, slots=True)
class ThresholdObservation:
    """Single cycle observation of a runtime channel or validation policy adjustment."""

    policy_id: str
    target_surface: str
    channel_from: str
    channel_to: str
    validation_delta: float
    delivery_delta: float
    health_score: float = 80.0

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("ThresholdObservation.policy_id must not be blank")
        if not 0.0 <= self.health_score <= 100.0:
            raise ValueError("health_score must be in [0.0, 100.0]")


@dataclass(frozen=True, slots=True)
class ThresholdPromotionProposal:
    """Auditable proposal emitted when a policy adjustment sustains positive gain."""

    policy_id: str
    target_surface: str
    channel_from: str
    channel_to: str
    observed_cycles: int
    mean_validation_delta: float
    mean_delivery_delta: float
    evidence_digest: str
    parent_digest: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize promotion proposal to a JSON-compatible dictionary."""
        return {
            "policy_id": self.policy_id,
            "target_surface": self.target_surface,
            "channel_from": self.channel_from,
            "channel_to": self.channel_to,
            "observed_cycles": self.observed_cycles,
            "mean_validation_delta": self.mean_validation_delta,
            "mean_delivery_delta": self.mean_delivery_delta,
            "evidence_digest": self.evidence_digest,
            "parent_digest": self.parent_digest,
        }


class AdaptiveThresholdPromoter:
    """Evaluates consecutive runtime observations and emits hysteresis promotion proposals."""

    def __init__(
        self,
        *,
        min_cycles: int = DEFAULT_PROMOTION_MIN_CYCLES,
        min_validation_delta: float = DEFAULT_MIN_VALIDATION_DELTA,
        min_delivery_delta: float = DEFAULT_MIN_DELIVERY_DELTA,
    ) -> None:
        if min_cycles < 1:
            raise ValueError("min_cycles must be >= 1")
        self._min_cycles = min_cycles
        self._min_validation_delta = min_validation_delta
        self._min_delivery_delta = min_delivery_delta
        self._history: dict[str, list[ThresholdObservation]] = {}

    def streak_length(self, policy_id: str) -> int:
        """Return consecutive qualifying observations currently recorded for policy_id."""
        return len(self._history.get(policy_id, ()))

    def reset(self) -> None:
        """Clear all recorded observation streaks."""
        self._history.clear()

    def record(
        self, observation: ThresholdObservation, *, parent_digest: str | None = None
    ) -> ThresholdPromotionProposal | None:
        """Record an observation and emit ThresholdPromotionProposal once min_cycles is met."""
        if (
            observation.validation_delta < self._min_validation_delta
            or observation.delivery_delta < self._min_delivery_delta
        ):
            self._history.pop(observation.policy_id, None)
            return None

        bucket = self._history.setdefault(observation.policy_id, [])
        bucket.append(observation)
        count = len(bucket)
        if count < self._min_cycles:
            return None

        mean_val = round(sum(item.validation_delta for item in bucket) / count, 4)
        mean_del = round(sum(item.delivery_delta for item in bucket) / count, 4)
        payload = (
            f"{observation.policy_id}|{observation.target_surface}|"
            f"{count}|{mean_val:.4f}|{mean_del:.4f}|{parent_digest or ''}"
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return ThresholdPromotionProposal(
            policy_id=observation.policy_id,
            target_surface=observation.target_surface,
            channel_from=observation.channel_from,
            channel_to=observation.channel_to,
            observed_cycles=count,
            mean_validation_delta=mean_val,
            mean_delivery_delta=mean_del,
            evidence_digest=digest,
            parent_digest=parent_digest,
        )
