"""Zero-dependency Structure Analyzer, Schema Proposer, and Validation Gate.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Final

from zcg.platform.type_registry import (
    CanonicalTypeRegistry,
    FieldAnalysis,
    SemanticMapper,
    SemanticMappingResult,
    SemanticType,
    StructuralPattern,
    StructureAnalysisResult,
    TypeSignature,
    WireType,
    compute_shannon_entropy,
    detect_charset,
    detect_positional_anchors,
)

DEFAULT_MAX_SAMPLE_SIZE: Final[int] = 10_000
MAX_SAMPLE_VALUES: Final[int] = 5
UNIX_EPOCH_MIN_SECONDS: Final[int] = 946_684_800
UNIX_EPOCH_MAX_SECONDS: Final[int] = 4_102_444_800
PATTERN_MAJORITY_RATIO: Final[float] = 0.50
DEFAULT_SCHEMA_VERSION: Final[str] = "v1"


class SchemaStatus(StrEnum):
    """Lifecycle states of a discovered schema proposal."""

    PENDING_PROPOSAL = "pending_proposal"
    VALIDATED = "validated"
    ACTIVE = "active"
    REJECTED = "rejected"


class ValidationAction(StrEnum):
    """Human review actions applicable to individual field proposals."""

    ACCEPT = "accept"
    ADJUST = "adjust"
    REGISTER_CUSTOM = "register_custom"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class FieldProposal:
    """Proposed schema contract for a single field."""

    name: str
    wire_type: WireType
    semantic_type: SemanticType
    confidence: float
    signature: TypeSignature | None = None
    indexable: bool = False
    display_hint: str = "default"
    custom_type_name: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize field proposal to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "wire_type": self.wire_type.value,
            "semantic_type": self.semantic_type.value,
            "confidence": self.confidence,
            "indexable": self.indexable,
            "display_hint": self.display_hint,
            "custom_type_name": self.custom_type_name,
        }


@dataclass(frozen=True, slots=True)
class SchemaProposal:
    """Complete discovered schema proposal with lifecycle state."""

    family: str
    status: SchemaStatus
    fields: tuple[FieldProposal, ...] = ()
    version: str = DEFAULT_SCHEMA_VERSION
    avg_confidence: float = 0.0
    total_records: int = 0
    sample_size: int = 0

    def to_dict(self) -> dict[str, object]:
        """Serialize schema proposal to a JSON-compatible dictionary."""
        return {
            "family": self.family,
            "version": self.version,
            "status": self.status.value,
            "avg_confidence": self.avg_confidence,
            "total_records": self.total_records,
            "sample_size": self.sample_size,
            "fields": [f.to_dict() for f in self.fields],
        }


@dataclass(frozen=True, slots=True)
class FieldDecision:
    """Reviewer decision applied to a single field proposal."""

    field_name: str
    action: ValidationAction
    new_semantic_type: SemanticType | None = None
    custom_type_name: str | None = None


_PRIMITIVE_WIRE_MAP: Final[dict[type, WireType]] = {
    bool: WireType.BOOLEAN,
    int: WireType.INTEGER,
    float: WireType.FLOAT,
    str: WireType.STRING,
    list: WireType.ARRAY,
    tuple: WireType.ARRAY,
    bytes: WireType.BYTES,
    bytearray: WireType.BYTES,
}
_PATTERN_REGEXES: Final[tuple[tuple[StructuralPattern, re.Pattern[str]], ...]] = (
    (
        StructuralPattern.UUID,
        re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I),
    ),
    (StructuralPattern.EMAIL, re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")),
    (StructuralPattern.URL, re.compile(r"^https?://")),
    (StructuralPattern.ISO_TIMESTAMP, re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")),
    (StructuralPattern.IPV4, re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")),
    (StructuralPattern.HEXADECIMAL, re.compile(r"^[0-9a-f]{16,}$", re.I)),
)
_DISPLAY_HINTS: Final[dict[SemanticType, str]] = {
    SemanticType.IDENTIFIER: "monospace",
    SemanticType.FINGERPRINT: "monospace+truncate",
    SemanticType.TEMPORAL: "relative_time",
    SemanticType.QUANTITY: "formatted_number",
    SemanticType.EMAIL_ADDRESS: "link_mailto",
    SemanticType.GEOLOCATION: "map_pin",
    SemanticType.MONETARY_AMOUNT: "currency",
    SemanticType.CLASSIFIER: "badge",
    SemanticType.SEQUENCE: "monospace",
    SemanticType.OPAQUE_PAYLOAD: "collapsed",
}
_INDEXABLE_TYPES: Final[frozenset[SemanticType]] = frozenset(
    {
        SemanticType.IDENTIFIER,
        SemanticType.FINGERPRINT,
        SemanticType.TEMPORAL,
        SemanticType.EMAIL_ADDRESS,
    }
)


class StructureAnalyzer:
    """Pure Functional Core service analyzing raw record dictionaries."""

    def __init__(self, *, max_sample_size: int = DEFAULT_MAX_SAMPLE_SIZE) -> None:
        if max_sample_size < 1:
            raise ValueError("max_sample_size must be >= 1")
        self._max_sample_size = max_sample_size

    def analyze(self, records: Sequence[Mapping[str, Any]]) -> StructureAnalysisResult:
        """Analyze a batch of records into per-field wire types, patterns, and statistics."""
        total_records = len(records)
        if total_records == 0:
            return StructureAnalysisResult()
        sample = list(itertools.islice(records, self._max_sample_size))
        sample_size = len(sample)
        field_values: dict[str, list[Any]] = {}
        field_depths: dict[str, int] = {}
        for record in sample:
            for key, (val, depth) in self._flatten_record(record).items():
                field_values.setdefault(key, []).append(val)
                field_depths[key] = max(field_depths.get(key, 0), depth)
        fields: list[FieldAnalysis] = []
        max_depth = 0
        for name in sorted(field_values):
            values = field_values[name]
            depth = field_depths[name]
            max_depth = max(max_depth, depth)
            if (missing := sample_size - len(values)) > 0:
                values.extend([None] * missing)
            fields.append(self._analyze_field(name, values, sample_size, depth))
        return StructureAnalysisResult(tuple(fields), total_records, sample_size, max_depth)

    @staticmethod
    def _flatten_record(
        record: Mapping[str, Any], _prefix: str = "", _depth: int = 0
    ) -> dict[str, tuple[Any, int]]:
        out: dict[str, tuple[Any, int]] = {}
        for key, value in record.items():
            full_key = f"{_prefix}{key}"
            if isinstance(value, Mapping):
                for nkey, nval in StructureAnalyzer._flatten_record(
                    value, f"{full_key}.", _depth + 1
                ).items():
                    out[nkey] = nval
            else:
                out[full_key] = (value, _depth)
        return out

    @staticmethod
    def detect_wire_type(value: Any) -> WireType:
        """Classify a single Python runtime value into its transport WireType."""
        if value is None:
            return WireType.NULL
        if isinstance(value, Mapping):
            return WireType.OBJECT
        return _PRIMITIVE_WIRE_MAP.get(type(value), WireType.STRING)

    @staticmethod
    def _detect_patterns(non_null: list[Any], wire_type: WireType) -> tuple[StructuralPattern, ...]:
        threshold = len(non_null) * PATTERN_MAJORITY_RATIO
        if wire_type == WireType.INTEGER:
            epochs = sum(
                1
                for v in non_null
                if isinstance(v, int)
                and not isinstance(v, bool)
                and UNIX_EPOCH_MIN_SECONDS <= v <= UNIX_EPOCH_MAX_SECONDS
            )
            return (StructuralPattern.UNIX_EPOCH,) if epochs > threshold else ()
        if wire_type == WireType.STRING:
            str_vals = [str(v) for v in non_null]
            return tuple(
                p
                for p, rx in _PATTERN_REGEXES
                if sum(1 for s in str_vals if rx.match(s)) > threshold
            )
        return ()

    @staticmethod
    def _analyze_field(name: str, values: list[Any], total: int, depth: int) -> FieldAnalysis:
        null_count = sum(1 for v in values if v is None)
        non_null = [v for v in values if v is not None]
        if not non_null:
            return FieldAnalysis(
                name, WireType.NULL, nullable=True, nullability_ratio=1.0, nesting_depth=depth
            )
        wire_type = Counter(StructureAnalyzer.detect_wire_type(v) for v in non_null).most_common(1)[
            0
        ][0]
        patterns = StructureAnalyzer._detect_patterns(non_null, wire_type)
        unique_strs = list(dict.fromkeys(str(v) for v in non_null))
        cardinality = len(unique_strs)
        min_len: int | None = None
        max_len: int | None = None
        if wire_type == WireType.STRING:
            lengths = [len(str(v)) for v in non_null]
            min_len, max_len = min(lengths), max(lengths)
        samples = tuple(itertools.islice(unique_strs, MAX_SAMPLE_VALUES))
        return FieldAnalysis(
            name,
            wire_type,
            patterns,
            null_count > 0,
            round(null_count / total, 4),
            cardinality,
            round(cardinality / total, 4),
            min_len,
            max_len,
            depth,
            samples,
        )


class SchemaProposer:
    """Synthesizes SchemaProposal contracts from analysis and semantic mappings."""

    def propose(
        self, *, family: str, analysis: StructureAnalysisResult, mapping: SemanticMappingResult
    ) -> SchemaProposal:
        """Build a PENDING_PROPOSAL schema with string signatures and indexability hints."""
        clean_family = family.strip()
        if not clean_family:
            raise ValueError("Schema family must not be blank")
        analysis_map = {f.name: f for f in analysis.fields}
        proposals: list[FieldProposal] = []
        for fm in mapping.mappings:
            fa = analysis_map.get(fm.field_name)
            sig: TypeSignature | None = None
            if fa is not None and fm.wire_type == WireType.STRING:
                bounds = (
                    (fa.min_length, fa.max_length)
                    if fa.min_length is not None and fa.max_length is not None
                    else None
                )
                sig = TypeSignature(
                    bounds,
                    detect_charset(fa.sample_values),
                    compute_shannon_entropy(fa.sample_values),
                    detect_positional_anchors(fa.sample_values),
                )
            proposals.append(
                FieldProposal(
                    fm.field_name,
                    fm.wire_type,
                    fm.semantic_type,
                    fm.confidence,
                    sig,
                    fm.semantic_type in _INDEXABLE_TYPES,
                    _DISPLAY_HINTS.get(fm.semantic_type, "default"),
                )
            )
        return SchemaProposal(
            clean_family,
            SchemaStatus.PENDING_PROPOSAL,
            tuple(proposals),
            DEFAULT_SCHEMA_VERSION,
            mapping.avg_confidence,
            analysis.total_records,
            analysis.sample_size,
        )


class SchemaValidationGate:
    """State machine governing human review and activation of SchemaProposal contracts."""

    def validate(
        self, proposal: SchemaProposal, decisions: Sequence[FieldDecision]
    ) -> SchemaProposal:
        """Apply reviewer field decisions and transition to VALIDATED or REJECTED."""
        decision_map = {d.field_name: d for d in decisions}
        accepted: list[FieldProposal] = []
        for field in proposal.fields:
            dec = decision_map.get(field.name)
            if dec is None or dec.action == ValidationAction.ACCEPT:
                accepted.append(field)
            elif dec.action == ValidationAction.ADJUST:
                accepted.append(
                    replace(field, semantic_type=dec.new_semantic_type or field.semantic_type)
                )
            elif dec.action == ValidationAction.REGISTER_CUSTOM:
                accepted.append(
                    replace(
                        field,
                        semantic_type=SemanticType.UNKNOWN,
                        custom_type_name=dec.custom_type_name,
                    )
                )
        new_status = SchemaStatus.VALIDATED if accepted else SchemaStatus.REJECTED
        confs = [f.confidence for f in accepted if f.confidence > 0.0]
        avg_conf = round(sum(confs) / len(confs), 4) if confs else 0.0
        return replace(proposal, fields=tuple(accepted), status=new_status, avg_confidence=avg_conf)

    def activate(self, proposal: SchemaProposal) -> SchemaProposal:
        """Promote a VALIDATED schema proposal to ACTIVE."""
        if proposal.status != SchemaStatus.VALIDATED:
            raise ValueError(f"Cannot activate schema in status {proposal.status.value!r}")
        return replace(proposal, status=SchemaStatus.ACTIVE)

    def reject_all(self, proposal: SchemaProposal) -> SchemaProposal:
        """Reject an entire schema proposal and clear its fields."""
        return replace(proposal, fields=(), status=SchemaStatus.REJECTED, avg_confidence=0.0)


class SchemaDiscovery:
    """End-to-end pure pipeline chaining StructureAnalyzer -> SemanticMapper -> SchemaProposer."""

    def __init__(
        self,
        *,
        max_sample_size: int = DEFAULT_MAX_SAMPLE_SIZE,
        registry: CanonicalTypeRegistry | None = None,
    ) -> None:
        self._analyzer = StructureAnalyzer(max_sample_size=max_sample_size)
        self._mapper = SemanticMapper(registry=registry)
        self._proposer = SchemaProposer()

    def discover(self, *, family: str, records: Sequence[Mapping[str, Any]]) -> SchemaProposal:
        """Discover a schema proposal directly from a sequence of raw records."""
        analysis = self._analyzer.analyze(records)
        mapping = self._mapper.map_fields(analysis)
        return self._proposer.propose(family=family, analysis=analysis, mapping=mapping)
