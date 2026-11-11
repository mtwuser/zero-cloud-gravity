"""Unit test suite for src/zcg/platform/type_registry.py.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from zcg.platform.type_registry import (
    CanonicalTypeRegistry,
    FieldAnalysis,
    SemanticMapper,
    SemanticMappingResult,
    SemanticType,
    StructuralPattern,
    StructureAnalysisResult,
    TypeMappingRule,
    WireType,
    compute_shannon_entropy,
    detect_charset,
    detect_positional_anchors,
)


class TestTypeRegistry:
    """Verify CanonicalTypeRegistry, signature helpers, and SemanticMapper."""

    def test_signature_helpers_charset_entropy_and_anchors_expected(self) -> None:
        """Verify detect_charset, compute_shannon_entropy, and detect_positional_anchors."""
        # Arrange
        samples = ("AB-1", "AB-2")

        # Act
        anchors = detect_positional_anchors(samples)
        entropy = compute_shannon_entropy(samples)

        # Assert
        assert detect_charset(()) == "unknown"
        assert detect_charset(("---", "::")) == "symbolic"
        assert detect_charset(("01af", "beef")) == "hexadecimal_lower"
        assert detect_charset(("abc1", "xyz2")) == "alphanumeric_lower"
        assert detect_charset(("Abc1",)) == "alphanumeric_mixed"
        assert detect_charset(("niño",)) == "unicode"
        assert compute_shannon_entropy(("",)) == 0.0
        assert entropy == 2.0
        assert detect_positional_anchors(("only-one",)) == ()
        assert anchors == ((2, "-"),)

    def test_registry_pattern_match_and_cardinality_cut_points_expected(self) -> None:
        """Verify high/low cardinality gating, pattern override, and custom rule registration."""
        # Arrange
        registry = CanonicalTypeRegistry()
        initial_count = registry.rule_count
        registry.register_rule(
            TypeMappingRule(SemanticType.MONETARY_AMOUNT, (WireType.FLOAT,), 0.85)
        )
        uuid_low_card = FieldAnalysis(
            name="id",
            wire_type=WireType.STRING,
            patterns=(StructuralPattern.UUID,),
            cardinality=2,
            cardinality_ratio=0.20,
        )
        low_card_cat = FieldAnalysis(
            name="status",
            wire_type=WireType.STRING,
            cardinality=2,
            cardinality_ratio=0.05,
        )

        # Act
        uuid_matches = registry.query(uuid_low_card)
        cat_matches = registry.query(low_card_cat)

        # Assert
        assert registry.rule_count == initial_count + 1
        assert uuid_matches[0] == (uuid_matches[0][0], 0.94)
        assert uuid_matches[0][0].semantic_type == SemanticType.IDENTIFIER
        assert cat_matches[0][0].semantic_type == SemanticType.CLASSIFIER

    def test_semantic_mapper_confidence_floor_alternatives_and_unmapped_expected(self) -> None:
        """Verify empty analysis, UNKNOWN confidence floor, and deduplicated alternatives."""
        # Arrange
        registry = CanonicalTypeRegistry(
            rules=(
                TypeMappingRule(SemanticType.QUANTITY, (WireType.FLOAT,), 0.80),
                TypeMappingRule(SemanticType.QUANTITY, (WireType.FLOAT,), 0.75),
                TypeMappingRule(SemanticType.GEOLOCATION, (WireType.FLOAT,), 0.45),
                TypeMappingRule(SemanticType.SEQUENCE, (WireType.INTEGER,), 0.15),
            )
        )
        mapper = SemanticMapper(registry=registry)
        analysis = StructureAnalysisResult(
            fields=(
                FieldAnalysis(name="lat", wire_type=WireType.FLOAT, cardinality_ratio=0.90),
                FieldAnalysis(name="low_conf", wire_type=WireType.INTEGER, cardinality_ratio=0.50),
                FieldAnalysis(name="flag", wire_type=WireType.BOOLEAN, cardinality_ratio=0.10),
            ),
            total_records=10,
            sample_size=10,
        )

        # Act
        empty_res = mapper.map_fields(StructureAnalysisResult())
        mapped = mapper.map_fields(analysis)
        all_unmapped = mapper.map_fields(
            StructureAnalysisResult(
                fields=(FieldAnalysis(name="flag", wire_type=WireType.BOOLEAN),),
                total_records=1,
                sample_size=1,
            )
        )
        by_name = {m.field_name: m for m in mapped.mappings}

        # Assert
        assert empty_res == SemanticMappingResult()
        assert by_name["lat"].semantic_type == SemanticType.QUANTITY
        assert by_name["lat"].alternatives == (SemanticType.GEOLOCATION,)
        assert by_name["low_conf"].semantic_type == SemanticType.UNKNOWN
        assert by_name["flag"].semantic_type == SemanticType.UNKNOWN
        assert mapped.unmapped_count == 2
        assert mapped.avg_confidence == 0.80
        assert all_unmapped.avg_confidence == 0.0
        assert SemanticMapper().map_fields(StructureAnalysisResult()) == SemanticMappingResult()
