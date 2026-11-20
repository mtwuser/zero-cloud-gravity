"""Unit tests for zcg.capsules.constants.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

from zcg.capsules import constants as mod


class TestCapsuleConstants:
    """Verify rcap1 capsule, surface, epistemic, and JSON-RPC nominal constants and maps."""

    def test_constants_nominal_invariants_and_maps(self) -> None:
        """Verify envelope prefixes, progression maps, and lifecycle quadrant mappings."""
        # Arrange
        expected_levels = ("L0", "L1", "L2", "L3")

        # Act
        next_map = mod.NEXT_LEVEL_MAP
        quadrants = mod.CITATION_LIFECYCLE_QUADRANTS

        # Assert
        assert mod.CAPSULE_PREFIX == "rcap1"
        assert expected_levels == mod.VALID_CAPSULE_LEVELS
        assert next_map["L0"] == "L1"
        assert next_map["L3"] == "L3"
        assert "Q1_HOT_CORE" in quadrants
        assert "Q4_NORMATIVE_OBSOLESCENCE" in quadrants
        assert mod.MIN_EPHEMERAL_TTL_SECONDS < mod.DEFAULT_EPHEMERAL_TTL_SECONDS
        assert mod.DEFAULT_EPHEMERAL_TTL_SECONDS < mod.MAX_EPHEMERAL_TTL_SECONDS
        assert {"SYLLABUS.md", "WORKTASK.md", "WORKVALI.md"}.issubset(mod.ALLOWED_ROOT_FILES)

    def test_constants_jsonrpc_planes_and_digest_channels_expected(self) -> None:
        """Verify JSON-RPC error codes, plane path rules, and 4-channel digest keys."""
        # Arrange
        expected_rpc_codes = (-32700, -32601, -32602, -32603)

        # Act
        actual_rpc_codes = (
            mod.JSONRPC_PARSE_ERROR,
            mod.JSONRPC_METHOD_NOT_FOUND,
            mod.JSONRPC_INVALID_PARAMS,
            mod.JSONRPC_INTERNAL_ERROR,
        )
        plane_names = tuple(plane for plane, _ in mod.PLANE_PATH_RULES)

        # Assert
        assert actual_rpc_codes == expected_rpc_codes
        assert set(plane_names) == set(mod.VALID_ARCHITECTURAL_PLANES)
        assert len(mod.DIGEST_REQUIRED_CHANNELS) == 4
        assert "the" in mod.CODON_STOPWORDS
        assert "docs/" in mod.ALLOWED_READ_PREFIXES
        assert "src" in mod.STRUCTURAL_PATH_SEGMENTS
