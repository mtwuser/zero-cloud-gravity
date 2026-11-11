"""Unit tests for zcg.capsules.constants.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

from zcg.capsules import constants as mod


class TestCapsuleConstants:
    """Verify rcap1 capsule, surface, epistemic, and JSON-RPC nominal constants and regexes."""

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

    def test_constants_regex_patterns_match_expected_tokens(self) -> None:
        """Verify Markdown link, backtick path, citation receipt, bold, word, and ANSI regexes."""
        # Arrange
        sample = (
            "[Guide](docs/guides/01.md) `docs/README.md` **Zero Cloud** "
            "gov-iso::docs/law.md#art-1@0123456789abcdef:E3 \x1b[32mok\x1b[0m"
        )

        # Act
        md_hits = mod.MD_LINK_RE.findall(sample)
        bt_hits = mod.BACKTICK_PATH_RE.findall(sample)
        rc_hits = mod.CITATION_RECEIPT_REF_RE.findall(sample)
        bold_hits = mod.BOLD_TERM_RE.findall(sample)
        clean = mod.ANSI_ESCAPE_RE.sub("", sample)

        # Assert
        assert md_hits == [("Guide", "docs/guides/01.md")]
        assert bt_hits == ["docs/README.md"]
        assert rc_hits == [("gov-iso", "docs/law.md")]
        assert bold_hits == ["Zero Cloud"]
        assert "\x1b" not in clean
        assert "zero" in mod.WORD_TOKEN_RE.findall(clean.lower())
