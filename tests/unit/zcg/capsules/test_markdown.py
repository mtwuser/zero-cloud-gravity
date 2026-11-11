"""Unit tests for zcg.capsules.markdown.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

from pathlib import Path

from zcg.capsules.markdown import (
    extract_axiom_skeleton,
    extract_codon_tags,
    extract_l3_links,
    iter_markdown_sections,
    merge_unique_strings,
    read_non_empty_lines,
    resolve_section_hierarchy,
    slugify_codon,
)


class TestCapsuleMarkdown:
    """Verify Markdown sectioning, promoter codons, L1 exon skeletons, and L3 link discovery."""

    def test_read_non_empty_lines_missing_and_comments(self, tmp_path: Path) -> None:
        """Ignore missing files, blank lines, and hash-prefixed comments."""
        # Arrange
        missing = tmp_path / "missing.txt"
        present = tmp_path / "packages.txt"
        present.write_text("# header\n\n  git  \n  # indented comment\nripgrep\n", encoding="utf-8")

        # Act
        empty_res = read_non_empty_lines(missing)
        items = read_non_empty_lines(present)

        # Assert
        assert empty_res == []
        assert items == ["git", "ripgrep"]

    def test_merge_unique_strings_and_slugify_codon(self) -> None:
        """Deduplicate strings in first-seen order and bound empty or punctuation slugs."""
        # Arrange
        groups = ([" alpha ", "", "beta"], ["beta", "gamma"])

        # Act
        merged = merge_unique_strings(*groups)
        normal_slug = slugify_codon("1. Zero-Cloud Architectural Mandate!")
        fallback_slug = slugify_codon("!!!")

        # Assert
        assert merged == ["alpha", "beta", "gamma"]
        assert normal_slug == "1-zero-cloud-architectur"
        assert fallback_slug == "section"

    def test_extract_codon_tags_caps_and_filters_stopwords(self) -> None:
        """Extract up to five non-stopword semantic tags across heading and bold terms."""
        # Arrange
        heading = "The Must Use Architecture Security"
        body = (
            "Enforce **Topology Containment**, **Capsule Governance**, "
            "and **Ephemeral Verification**."
        )

        # Act
        capped = extract_codon_tags(heading, body)
        short = extract_codon_tags("Pure Node", "Plain prose without bold.")

        # Assert
        assert len(capped) == 5
        assert "architecture" in capped
        assert "the" not in capped
        assert short == ["pure", "node"]

    def test_extract_axiom_skeleton_folds_code_tables_and_overflow_bullets(self) -> None:
        """Retain mandates, lead sentence, and bullets while folding tables, code, and prose."""
        # Arrange
        body_lines = [
            "Lead summary line.",
            "Extra prose line folded.",
            "> [!IMPORTANT] Critical note",
            "**Mandate:** Zero-Backward cutover.",
            "### Subheading ignored without folding",
            "| Col | Val |",
            "---",
            "```python",
            "x = 1",
            "```",
            "  - nested bullet folded",
            *[f"- Bullet item {i}" for i in range(10)],
        ]

        # Act
        skeleton = extract_axiom_skeleton("Core Policy", body_lines)
        clean_skeleton = extract_axiom_skeleton("Minimal", ["- Single bullet"])

        # Assert
        assert "## Core Policy" in skeleton
        assert "Lead summary line." in skeleton
        assert "> [!IMPORTANT] Critical note" in skeleton
        assert "**Mandate:** Zero-Backward cutover." in skeleton
        assert "- Bullet item 7" in skeleton
        assert "- Bullet item 8" not in skeleton
        assert "detail/table/code lines folded in rcap1:L1" in skeleton
        assert "folded" not in clean_skeleton

    def test_iter_markdown_sections_and_resolve_hierarchy(self) -> None:
        """Partition Markdown headings outside fenced code and build H1 > H2 > H3 breadcrumbs."""
        # Arrange
        lines = [
            "# Root Spec",
            "Intro",
            "```md",
            "## Ignored In Code",
            "```",
            "## Domain A",
            "### Rule A1",
            "Body A1",
            "## Domain B",
            "Body B",
        ]

        # Act
        empty_sections = iter_markdown_sections([], "Default")
        sections = iter_markdown_sections(lines, "Default")
        depth_a1, crumb_a1 = resolve_section_hierarchy(lines, 7, "Rule A1")
        depth_b, crumb_b = resolve_section_hierarchy(lines, 9, "Domain B")
        depth_zero, crumb_zero = resolve_section_hierarchy(["Plain line"], 1, "Fallback")

        # Assert
        assert empty_sections == []
        assert [s[0] for s in sections] == ["Root Spec", "Domain A", "Rule A1", "Domain B"]
        assert (depth_a1, crumb_a1) == (3, "Root Spec > Domain A > Rule A1")
        assert (depth_b, crumb_b) == (2, "Root Spec > Domain B")
        assert (depth_zero, crumb_zero) == (1, "Fallback")

    def test_extract_l3_links_filters_external_outside_and_deduplicates(
        self, tmp_path: Path
    ) -> None:
        """Discover path-contained readable L3 targets from links, backticks, and receipts."""
        # Arrange
        (tmp_path / "docs").mkdir()
        (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
        guide = tmp_path / "docs/guide.md"
        guide.write_text("# Guide\n", encoding="utf-8")
        secret = tmp_path / "src_secret.txt"
        secret.write_text("deny", encoding="utf-8")
        source = tmp_path / "docs/spec.md"
        source.write_text("# Spec\n", encoding="utf-8")
        text = (
            "[Ext](https://google.com) [Empty](#anchor) [Guide](guide.md#sec) "
            "`docs/guide.md` `README.md` `src_secret.txt` `missing.md` "
            "gov-iso::docs/guide.md#sec@0123456789abcdef:E2"
        )

        # Act
        links = extract_l3_links(source, text, tmp_path)

        # Assert
        paths = [item["path"] for item in links]
        assert paths == ["docs/guide.md", "README.md"]
        assert all(len(item["sha256"]) == 16 for item in links)
