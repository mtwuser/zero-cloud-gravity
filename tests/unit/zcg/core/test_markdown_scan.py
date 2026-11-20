"""Unit tests for zcg.core.markdown_scan.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from zcg.core.markdown_scan import (
    contains_token_id,
    extract_bold_terms,
    extract_citation_receipt_refs,
    extract_fenced_blocks,
    extract_inline_code_paths,
    extract_markdown_links,
    is_markdown_list_item,
    iter_unfenced_lines,
    parse_checkbox_line,
    parse_heading_line,
    scan_markdown_checkboxes,
    scan_markdown_headings,
    slugify_heading,
    split_markdown_sections,
    strip_ansi_csi,
    tokenize_alnum,
)


class TestMarkdownScan:
    """Verify fence-aware Markdown checkbox, heading, section, slug, and token scanning."""

    def test_unfenced_lines_and_checkbox_scanning_ignore_nested_code_fences_expected(self) -> None:
        """Verify 3+ backtick/tilde fences shield fake checkboxes while preserving real items."""
        # Arrange
        doc = (
            "# Tasks\n"
            "- [ ] Open root task\n"
            "  - [/] Indented active subtask\n"
            "````markdown\n"
            "```bash\n"
            "- [ ] Ignored inside 4-backtick outer fence\n"
            "```\n"
            "````\n"
            "~~~python\n"
            "- [x] Ignored inside tilde fence\n"
            "~~~\n"
            "- [X] Completed task\n"
            "- [ ]    \n"
            "- [z] Invalid state\n"
            "Plain paragraph\n"
        )

        # Act
        unfenced = list(iter_unfenced_lines(doc))
        fenced = extract_fenced_blocks(doc)
        items = scan_markdown_checkboxes(doc)
        reformatted = items[0].format_line(state="x", body="Updated task")
        preserved = items[1].format_line()

        # Assert
        assert len(unfenced) == 7
        assert len(fenced) == 2
        assert "- [ ] Ignored inside 4-backtick outer fence" in fenced[0]
        assert fenced[1] == "- [x] Ignored inside tilde fence"
        assert len(items) == 3
        assert items[0].is_open is True and items[0].is_in_progress is False
        assert items[1].is_in_progress is True and items[1].indent == "  "
        assert items[2].is_done is True and items[2].state == "x"
        assert reformatted == "- [x] Updated task"
        assert preserved == "  - [/] Indented active subtask"
        assert parse_checkbox_line("not a list") is None
        assert parse_checkbox_line("- [x]no-space") is None
        assert parse_checkbox_line("- [ ]   ") is None

    def test_headings_and_section_splitting_preserve_fenced_hash_comments_expected(self) -> None:
        """Verify bash '# comment' inside code fences never splits sections or creates headings."""
        # Arrange
        doc = (
            "Preamble intro\n"
            "# Section One\n"
            "```bash\n"
            "# shell comment inside code block\n"
            "## another comment\n"
            "```\n"
            "## Subsection Two\n"
            "##### Deep H5 ignored at max_level=4\n"
            "#    \n"
            "#NoSpaceTag\n"
        )

        # Act
        headings_h4 = scan_markdown_headings(doc, max_level=4)
        sections = split_markdown_sections(doc, max_level=4)
        empty_sections = split_markdown_sections("")

        # Assert
        assert [(h.lineno, h.level, h.text) for h in headings_h4] == [
            (2, 1, "Section One"),
            (7, 2, "Subsection Two"),
        ]
        assert len(sections) == 3
        assert sections[0] == "Preamble intro"
        assert "# shell comment inside code block" in sections[1]
        assert sections[2].startswith("## Subsection Two")
        assert empty_sections == []
        assert parse_heading_line("Plain line") is None
        assert parse_heading_line("#   ") is None
        assert parse_heading_line("#Tag") is None

    def test_slugify_tokenize_list_items_and_word_boundary_tokens_expected(self) -> None:
        """Verify ASCII slug truncation, list item prefixes, and word-boundary token matching."""
        # Arrange
        sample_title = "1. Zero-Cloud Architectural Mandate! ( Café )"

        # Act
        capped_slug = slugify_heading(sample_title, max_chars=24, fallback="section")
        full_slug = slugify_heading("Hello --- World", fallback="section")
        fb_slug = slugify_heading("!!!", fallback="section")
        toks = tokenize_alnum("a E3_gate iso-9001", min_len=2)

        # Assert
        assert capped_slug == "1-zero-cloud-architectur"
        assert full_slug == "hello-world"
        assert fb_slug == "section"
        assert toks == ["e3", "gate", "iso", "9001"]
        assert is_markdown_list_item("- bullet") is True
        assert is_markdown_list_item("* star") is True
        assert is_markdown_list_item("12. numbered") is True
        assert is_markdown_list_item("12.no-space") is False
        assert is_markdown_list_item("plain") is False
        assert contains_token_id("", "DELIV-01") is False
        assert contains_token_id("any", "") is False
        assert contains_token_id("Verified DELIV-010 then DELIV-01!", "DELIV-01") is True
        assert contains_token_id("Only DELIV-010 and X_DELIV-01", "DELIV-01") is False

    def test_inline_links_code_paths_bold_terms_receipts_and_ansi_stripping_expected(self) -> None:
        """Verify inline Markdown link, code path, bold term, receipt, and ANSI CSI scanners."""
        # Arrange
        sample = (
            "[Tag] [Empty]() [Guide](docs/guides/01.md) [Multi\nLine](bad) "
            "`docs/README.md` `zcg status` `.env` `trailing "
            "**hi** **Zero Cloud** **unclosed "
            "gov-iso::docs/law.md#art-1@0123456789abcdef:E3 bad::receipt "
            "\x1b[32;1mok\x1b[0m\x1b[2K"
        )

        # Act
        links = extract_markdown_links(sample)
        clean_links = extract_markdown_links("See [Spec](docs/spec.md) today.")
        unclosed_br = extract_markdown_links("unclosed [label")
        unclosed_paren = extract_markdown_links("[Guide](unclosed")
        code_paths = extract_inline_code_paths(sample)
        bold_terms = extract_bold_terms(sample)
        bold_clean = extract_bold_terms("**Alpha Beta**")
        receipts = extract_citation_receipt_refs(sample)
        stripped = strip_ansi_csi(sample)
        untouched = strip_ansi_csi("plain text")

        # Assert
        assert links == [("Guide", "docs/guides/01.md")]
        assert clean_links == [("Spec", "docs/spec.md")]
        assert unclosed_br == [] and unclosed_paren == []
        assert code_paths == ["docs/README.md"]
        assert bold_terms == ["Zero Cloud"] and bold_clean == ["Alpha Beta"]
        assert receipts == [("gov-iso", "docs/law.md")]
        assert "\x1b[32;1m" not in stripped and "\x1b[0m" not in stripped
        assert "ok\x1b[2K" in stripped
        assert untouched == "plain text"
