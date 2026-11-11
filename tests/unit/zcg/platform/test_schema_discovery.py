"""Unit test suite for src/zcg/platform/schema_discovery.py.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import pytest

from zcg.platform.schema_discovery import (
    FieldDecision,
    SchemaDiscovery,
    SchemaProposer,
    SchemaStatus,
    SchemaValidationGate,
    StructureAnalyzer,
    ValidationAction,
)
from zcg.platform.type_registry import (
    FieldAnalysis,
    FieldMapping,
    SemanticMappingResult,
    SemanticType,
    StructuralPattern,
    StructureAnalysisResult,
    WireType,
)


class _CustomObject:
    def __str__(self) -> str:
        return "custom-val"


class TestSchemaDiscovery:
    """Verify StructureAnalyzer, SchemaProposer, SchemaValidationGate, and SchemaDiscovery."""

    def test_analyzer_empty_and_invalid_sample_size_expected(self) -> None:
        """Verify StructureAnalyzer rejects non-positive sample sizes and handles empty input."""
        # Arrange
        analyzer = StructureAnalyzer(max_sample_size=5)

        # Act
        empty_res = analyzer.analyze([])

        # Assert
        assert empty_res == StructureAnalysisResult()
        with pytest.raises(ValueError, match="max_sample_size"):
            StructureAnalyzer(max_sample_size=0)

    def test_analyzer_nested_wire_types_patterns_and_missing_keys_expected(self) -> None:
        """Verify nested flattening, wire-type coverage, regex/epoch patterns, and null padding."""
        # Arrange
        analyzer = StructureAnalyzer(max_sample_size=3)
        records: list[dict[str, object]] = [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "ops@example.org",
                "url": "https://node.local/status",
                "ts": "2026-11-10T22:00:00Z",
                "ip": "127.0.0.1",
                "digest": "abcdef0123456789abcdef0123456789",
                "epoch": 1_700_000_000,
                "plain_int": 42,
                "flag": True,
                "ratio": 0.95,
                "tags": ["a", "b"],
                "raw": b"bytes",
                "null_only": None,
                "custom": _CustomObject(),
                "meta": {"nested_num": 10},
            },
            {
                "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "email": "dev@example.org",
                "url": "http://node.local/healthz",
                "ts": "2026-11-10 23:00:00",
                "ip": "10.0.0.1",
                "digest": "0123456789abcdef0123456789abcdef",
                "epoch": 1_700_000_100,
                "plain_int": 43,
                "flag": False,
                "ratio": 0.85,
                "tags": ("c",),
                "raw": bytearray(b"bin"),
                "null_only": None,
                "custom": _CustomObject(),
            },
            {
                "id": "7ba7b810-9dad-11d1-80b4-00c04fd430c9",
                "email": "sec@example.org",
                "url": "https://node.local/metrics",
                "ts": "2026-11-10T23:30:00Z",
                "ip": "192.168.1.1",
                "digest": "fedcba9876543210fedcba9876543210",
                "epoch": 10,
                "plain_int": 44,
                "flag": True,
                "ratio": 0.75,
                "tags": ["d"],
                "raw": b"more",
                "null_only": None,
                "custom": _CustomObject(),
            },
            {"id": "ignored-beyond-sample-cap"},
        ]

        # Act
        res = analyzer.analyze(records)
        by_name = {f.name: f for f in res.fields}

        # Assert
        assert res.total_records == 4
        assert res.sample_size == 3
        assert res.nesting_levels == 1
        assert by_name["id"].patterns == (StructuralPattern.UUID,)
        assert by_name["email"].patterns == (StructuralPattern.EMAIL,)
        assert by_name["url"].patterns == (StructuralPattern.URL,)
        assert by_name["ts"].patterns == (StructuralPattern.ISO_TIMESTAMP,)
        assert by_name["ip"].patterns == (StructuralPattern.IPV4,)
        assert by_name["digest"].patterns == (StructuralPattern.HEXADECIMAL,)
        assert by_name["epoch"].patterns == (StructuralPattern.UNIX_EPOCH,)
        assert by_name["plain_int"].patterns == ()
        assert by_name["flag"].wire_type == WireType.BOOLEAN
        assert by_name["ratio"].wire_type == WireType.FLOAT
        assert by_name["tags"].wire_type == WireType.ARRAY
        assert by_name["raw"].wire_type == WireType.BYTES
        assert by_name["null_only"].wire_type == WireType.NULL
        assert by_name["custom"].wire_type == WireType.STRING
        assert by_name["meta.nested_num"].nullable is True
        assert StructureAnalyzer.detect_wire_type(None) == WireType.NULL
        assert StructureAnalyzer.detect_wire_type({"k": 1}) == WireType.OBJECT

    def test_proposer_edge_cases_expected(self) -> None:
        """Verify SchemaProposer string signature attachment and blank family guard."""
        # Arrange
        proposer = SchemaProposer()
        analysis = StructureAnalysisResult(
            fields=(
                FieldAnalysis(
                    name="code",
                    wire_type=WireType.STRING,
                    min_length=None,
                    max_length=None,
                    sample_values=("AB-1", "AB-2"),
                ),
            ),
            total_records=2,
            sample_size=2,
        )
        mapping = SemanticMappingResult(
            mappings=(
                FieldMapping("code", WireType.STRING, SemanticType.IDENTIFIER, 0.94),
                FieldMapping("orphan", WireType.INTEGER, SemanticType.QUANTITY, 0.70),
            ),
            avg_confidence=0.82,
        )

        # Act
        proposal = proposer.propose(family="inventory", analysis=analysis, mapping=mapping)

        # Assert
        assert proposal.fields[0].signature is not None
        assert proposal.fields[0].signature.length_bounds is None
        assert proposal.fields[0].signature.positional_anchors == ((2, "-"),)
        assert proposal.fields[1].signature is None
        with pytest.raises(ValueError, match="must not be blank"):
            proposer.propose(family="   ", analysis=analysis, mapping=mapping)

    def test_end_to_end_discovery_and_validation_gate_lifecycle_expected(self) -> None:
        """Verify SchemaDiscovery pipeline and SchemaValidationGate state transitions."""
        # Arrange
        discovery = SchemaDiscovery(max_sample_size=10)
        gate = SchemaValidationGate()
        records = [
            {
                "entity_id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Primary Guidance Document",
                "role_tag": "candidate",
                "flag": True,
                "internal_note": "drop-me",
            },
            {
                "entity_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "title": "Secondary Guidance Document",
                "role_tag": "onboarding",
                "flag": False,
                "internal_note": "drop-me-too",
            },
        ]

        # Act
        proposal = discovery.discover(family="hr_records", records=records)
        validated = gate.validate(
            proposal,
            [
                FieldDecision("entity_id", ValidationAction.ACCEPT),
                FieldDecision("role_tag", ValidationAction.ADJUST, SemanticType.CLASSIFIER),
                FieldDecision(
                    "title", ValidationAction.REGISTER_CUSTOM, custom_type_name="hr_headline"
                ),
                FieldDecision("internal_note", ValidationAction.REJECT),
            ],
        )
        active = gate.activate(validated)
        zero_conf_validated = gate.validate(
            proposal,
            [
                FieldDecision(f.name, ValidationAction.REJECT)
                for f in proposal.fields
                if f.name != "flag"
            ],
        )
        rejected_by_decisions = gate.validate(
            proposal,
            [FieldDecision(f.name, ValidationAction.REJECT) for f in proposal.fields],
        )
        rejected_all = gate.reject_all(active)

        # Assert
        assert proposal.status == SchemaStatus.PENDING_PROPOSAL
        assert len(validated.fields) == 4
        assert validated.status == SchemaStatus.VALIDATED
        assert active.status == SchemaStatus.ACTIVE
        assert active.to_dict()["status"] == "active"
        assert zero_conf_validated.avg_confidence == 0.0
        assert rejected_by_decisions.status == SchemaStatus.REJECTED
        assert rejected_all.status == SchemaStatus.REJECTED
        assert rejected_all.fields == ()
        with pytest.raises(ValueError, match="Cannot activate"):
            gate.activate(proposal)
