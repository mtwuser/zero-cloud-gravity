"""Canonical Semantic Type Registry, Signatures, and Semantic Mapper.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import itertools
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

HIGH_CARDINALITY_THRESHOLD: Final[float] = 0.80
LOW_CARDINALITY_THRESHOLD: Final[float] = 0.10
MIN_MAPPING_CONFIDENCE_THRESHOLD: Final[float] = 0.30
MIN_ANCHOR_SAMPLES: Final[int] = 2

_HEX_CHARS: Final[frozenset[str]] = frozenset("0123456789abcdef")
_ALNUM_LOWER: Final[frozenset[str]] = frozenset("0123456789abcdefghijklmnopqrstuvwxyz")
_ALNUM_MIXED: Final[frozenset[str]] = _ALNUM_LOWER | frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


class WireType(StrEnum):
    """Transport-level data type observed in raw record payloads."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    BYTES = "bytes"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


class StructuralPattern(StrEnum):
    """Deterministic format patterns recognized across scalar field values."""

    UUID = "uuid"
    EMAIL = "email"
    URL = "url"
    ISO_TIMESTAMP = "iso_timestamp"
    UNIX_EPOCH = "unix_epoch"
    IPV4 = "ipv4"
    HEXADECIMAL = "hexadecimal"


class SemanticType(StrEnum):
    """Canonical semantic meaning inferred from wire types and structural patterns."""

    IDENTIFIER = "identifier"
    FINGERPRINT = "fingerprint"
    NATURAL_TEXT = "natural_text"
    QUANTITY = "quantity"
    TEMPORAL = "temporal"
    GEOLOCATION = "geolocation"
    MONETARY_AMOUNT = "monetary_amount"
    EMAIL_ADDRESS = "email_address"
    SEQUENCE = "sequence"
    CLASSIFIER = "classifier"
    OPAQUE_PAYLOAD = "opaque_payload"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TypeSignature:
    """Statistical character-class and entropy signature for string fields."""

    length_bounds: tuple[int, int] | None
    charset: str
    entropy_per_char: float
    positional_anchors: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FieldAnalysis:
    """Statistical and structural profile of a single discovered field."""

    name: str
    wire_type: WireType
    patterns: tuple[StructuralPattern, ...] = ()
    nullable: bool = False
    nullability_ratio: float = 0.0
    cardinality: int = 0
    cardinality_ratio: float = 0.0
    min_length: int | None = None
    max_length: int | None = None
    nesting_depth: int = 0
    sample_values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StructureAnalysisResult:
    """Aggregate result produced by StructureAnalyzer across a record batch."""

    fields: tuple[FieldAnalysis, ...] = ()
    total_records: int = 0
    sample_size: int = 0
    nesting_levels: int = 0


@dataclass(frozen=True, slots=True)
class TypeMappingRule:
    """Rule mapping compatible wire types and patterns to a canonical SemanticType."""

    semantic_type: SemanticType
    wire_types: tuple[WireType, ...]
    base_confidence: float
    patterns: tuple[StructuralPattern, ...] = ()
    pattern_confidence: float = 0.0
    cardinality_hint: str | None = None


@dataclass(frozen=True, slots=True)
class FieldMapping:
    """Semantic classification output for a single analyzed field."""

    field_name: str
    wire_type: WireType
    semantic_type: SemanticType
    confidence: float
    alternatives: tuple[SemanticType, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticMappingResult:
    """Aggregate semantic mapping output across all analyzed fields."""

    mappings: tuple[FieldMapping, ...] = ()
    unmapped_count: int = 0
    avg_confidence: float = 0.0


def detect_charset(values: Sequence[str]) -> str:
    """Classify the dominant character set across non-empty string samples."""
    if not values:
        return "unknown"
    chars = {ch for val in values for ch in val if ch.isalnum()}
    if not chars:
        return "symbolic"
    if chars <= _HEX_CHARS:
        return "hexadecimal_lower"
    if chars <= _ALNUM_LOWER:
        return "alphanumeric_lower"
    if chars <= _ALNUM_MIXED:
        return "alphanumeric_mixed"
    return "unicode"


def compute_shannon_entropy(values: Sequence[str]) -> float:
    """Compute mean per-character Shannon entropy across non-empty strings."""
    entropies = [
        -sum((cnt / len(val)) * math.log2(cnt / len(val)) for cnt in Counter(val).values())
        for val in values
        if val
    ]
    return round(sum(entropies) / len(entropies), 2) if entropies else 0.0


def detect_positional_anchors(values: Sequence[str]) -> tuple[tuple[int, str], ...]:
    """Identify invariant non-alphanumeric delimiter positions across samples."""
    if len(values) < MIN_ANCHOR_SAMPLES:
        return ()
    min_len = min(len(v) for v in values)
    anchors: list[tuple[int, str]] = []
    for pos in range(min_len):
        chars = {v[pos] for v in values}
        if len(chars) == 1 and not (ch := next(iter(chars))).isalnum():
            anchors.append((pos, ch))
    return tuple(anchors)


DEFAULT_CANONICAL_TYPE_RULES: Final[tuple[TypeMappingRule, ...]] = (
    TypeMappingRule(
        SemanticType.IDENTIFIER,
        (WireType.STRING,),
        0.50,
        (StructuralPattern.UUID,),
        0.94,
        "high",
    ),
    TypeMappingRule(
        SemanticType.FINGERPRINT,
        (WireType.STRING,),
        0.40,
        (StructuralPattern.HEXADECIMAL,),
        0.97,
        "high",
    ),
    TypeMappingRule(
        SemanticType.TEMPORAL,
        (WireType.STRING,),
        0.30,
        (StructuralPattern.ISO_TIMESTAMP,),
        0.99,
    ),
    TypeMappingRule(
        SemanticType.TEMPORAL,
        (WireType.INTEGER,),
        0.30,
        (StructuralPattern.UNIX_EPOCH,),
        0.99,
    ),
    TypeMappingRule(
        SemanticType.EMAIL_ADDRESS,
        (WireType.STRING,),
        0.20,
        (StructuralPattern.EMAIL,),
        0.96,
    ),
    TypeMappingRule(SemanticType.NATURAL_TEXT, (WireType.STRING,), 0.60, cardinality_hint="high"),
    TypeMappingRule(SemanticType.QUANTITY, (WireType.INTEGER, WireType.FLOAT), 0.70),
    TypeMappingRule(SemanticType.GEOLOCATION, (WireType.FLOAT,), 0.30),
    TypeMappingRule(SemanticType.CLASSIFIER, (WireType.STRING,), 0.50, cardinality_hint="low"),
    TypeMappingRule(
        SemanticType.OPAQUE_PAYLOAD,
        (WireType.BYTES, WireType.ARRAY, WireType.OBJECT),
        0.80,
    ),
)


class CanonicalTypeRegistry:
    """Catalog of universal and custom semantic type inference rules."""

    def __init__(self, rules: Sequence[TypeMappingRule] | None = None) -> None:
        self._rules: list[TypeMappingRule] = list(
            DEFAULT_CANONICAL_TYPE_RULES if rules is None else rules
        )

    @property
    def rule_count(self) -> int:
        """Return total registered mapping rules."""
        return len(self._rules)

    def register_rule(self, rule: TypeMappingRule) -> None:
        """Append a custom domain mapping rule."""
        self._rules.append(rule)

    def query(self, field: FieldAnalysis) -> list[tuple[TypeMappingRule, float]]:
        """Evaluate compatible rules and return (rule, confidence) sorted descending."""
        candidates: list[tuple[TypeMappingRule, float]] = []
        for rule in self._rules:
            if field.wire_type not in rule.wire_types:
                continue
            pattern_match = bool(rule.patterns and any(p in field.patterns for p in rule.patterns))
            if (
                rule.cardinality_hint == "high"
                and field.cardinality_ratio < HIGH_CARDINALITY_THRESHOLD
                and not pattern_match
            ):
                continue
            if (
                rule.cardinality_hint == "low"
                and field.cardinality_ratio >= LOW_CARDINALITY_THRESHOLD
            ):
                continue
            conf = rule.pattern_confidence if pattern_match else rule.base_confidence
            candidates.append((rule, conf))
        candidates.sort(key=lambda item: item[1], reverse=True)
        return candidates


class SemanticMapper:
    """Maps analyzed fields to canonical semantic types via CanonicalTypeRegistry."""

    def __init__(self, *, registry: CanonicalTypeRegistry | None = None) -> None:
        self._registry = registry or CanonicalTypeRegistry()

    def map_fields(self, analysis: StructureAnalysisResult) -> SemanticMappingResult:
        """Infer semantic types and confidence scores for all fields in analysis."""
        if not analysis.fields:
            return SemanticMappingResult()
        mappings: list[FieldMapping] = []
        unmapped = 0
        total_conf = 0.0
        for field in analysis.fields:
            candidates = self._registry.query(field)
            if not candidates or candidates[0][1] < MIN_MAPPING_CONFIDENCE_THRESHOLD:
                mappings.append(
                    FieldMapping(field.name, field.wire_type, SemanticType.UNKNOWN, 0.0)
                )
                unmapped += 1
                continue
            best_rule, best_conf = candidates[0]
            alts = tuple(
                dict.fromkeys(
                    r.semantic_type
                    for r, c in itertools.islice(candidates, 1, None)
                    if c >= MIN_MAPPING_CONFIDENCE_THRESHOLD
                    and r.semantic_type != best_rule.semantic_type
                )
            )
            mappings.append(
                FieldMapping(field.name, field.wire_type, best_rule.semantic_type, best_conf, alts)
            )
            total_conf += best_conf
        mapped_count = len(mappings) - unmapped
        avg_conf = round(total_conf / mapped_count, 4) if mapped_count > 0 else 0.0
        return SemanticMappingResult(tuple(mappings), unmapped, avg_conf)
