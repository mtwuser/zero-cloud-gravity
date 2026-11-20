"""Unit tests for zcg.cockpit.views.docs_view.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from zcg.cockpit.views.docs_view import (
    render_doc_dirty_banner_html,
    render_doc_editor_html,
    render_knowledge_space_chrome,
    render_markdown_document_html,
    render_search_hits_html,
)


class TestDocsView:
    """1:1 unit suite for 0-regex Markdown HTML rendering, editor forms, and FTS5 chrome."""

    def test_render_markdown_document_html_across_syntax_constructs_expected(self) -> None:
        """Verify headings, fences, tables, checkboxes, lists, quotes, inline code, and bold."""
        # Arrange
        rich_md = (
            "---\nepistemic_grade: E3\n---\n"
            "# Overview\n\n"
            "Lead paragraph with `code_tok` and **bold text**.\n\n"
            "## Matrix\n"
            "| Axis | Role |\n"
            "| :--- | :--- |\n"
            "| X | `Core` |\n\n"
            "- [ ] Todo item\n"
            "- [/] Active item\n"
            "- [x] Done item\n"
            "- Bullet point\n"
            "1. Ordered step\n\n"
            "> Normative callout\n\n"
            "---\n"
            "```python\nx = 1 < 2\n```\n"
            "~~~\nunclosed trailing fence"
        )

        # Act
        rendered, toc = render_markdown_document_html(rich_md)
        clean_rendered, clean_toc = render_markdown_document_html("# Single\n\nClosed doc.\n")
        html_str = rendered.value

        # Assert
        assert len(clean_toc) == 1 and "Closed doc." in clean_rendered.value
        assert [t[1] for t in toc] == ["Overview", "Matrix"]
        assert "<h2 id='overview'>Overview</h2>" in html_str
        assert "<code>code_tok</code>" in html_str and "<strong>bold text</strong>" in html_str
        assert "<table class='zcg-table'>" in html_str and "<th>Axis</th>" in html_str
        assert (
            "☐ Todo item" in html_str and "◐ Active item" in html_str and "☑ Done item" in html_str
        )
        assert "<li>Bullet point</li>" in html_str and "<li>Ordered step</li>" in html_str
        assert "<blockquote class='zcg-doc-quote'>Normative callout</blockquote>" in html_str
        assert "<hr>" in html_str and "x = 1 &lt; 2" in html_str
        assert "unclosed trailing fence" in html_str

    def test_render_editor_search_hits_and_space_chrome_expected(self) -> None:
        """Verify new/edit forms, empty/populated search hits, and R3 vs R0 chrome buttons."""
        # Arrange
        pfx = "/api/modules/docs-reader"
        hits = [
            {
                "source_id": "self",
                "origin_group": "node",
                "doc": "docs/sop.md",
                "title": "SOP",
                "snippet": "Run [gate] cleanly",
            }
        ]
        sources = [{"source_id": "self", "label": "node-a (This Node)"}]
        multi_sources = [*sources, {"source_id": "sci-maths", "label": "sci-maths (Corpus)"}]

        # Act
        ed_new = render_doc_editor_html(pfx, "", "", is_new=True)
        ed_edit = render_doc_editor_html(
            pfx,
            "docs/sop.md",
            "# SOP\n",
            is_new=False,
            has_draft=True,
            updated_at="2026-11-19T12:00:00+00:00",
        )
        dirty_banner = render_doc_dirty_banner_html(pfx, "docs/sop.md")
        hits_none = render_search_hits_html(pfx, "missing", [])
        pills_r3, bar_r3 = render_knowledge_space_chrome(
            prefix=pfx,
            eff_origin="node",
            eff_src="self",
            vis_sources=multi_sources,
            query_str="gate",
            hits=hits,
            is_r3=True,
        )
        pills_single, bar_r0 = render_knowledge_space_chrome(
            prefix=pfx,
            eff_origin="all",
            eff_src="self",
            vis_sources=sources,
            query_str="",
            hits=(),
            is_r3=False,
        )

        # Assert
        assert "+ Create New Knowledge Document" in ed_new
        assert "data-island='draft-studio'" in ed_new and "Discard Draft" not in ed_new
        assert "name='commit_now' value='1'" in ed_new and "checked" not in ed_new
        assert "Editing <code>docs/sop.md</code>" in ed_edit
        assert "Unapplied draft restored" in ed_edit and "Discard Draft" in ed_edit
        assert "2026-11-19T12:00:00+00:00" in ed_edit and "data-draft-lines" in ed_edit
        assert "zcg-dirty-banner" in dirty_banner and "Commit Now" in dirty_banner
        assert "0 FTS5 matches" in hits_none
        assert "node-a" in pills_r3 and "sci-maths" in pills_r3
        assert "zcg-chip--active" in pills_r3 and pills_single == ""
        assert "class='zcg-filter-bar'" in bar_r3 and ">Reset</button>" in bar_r3
        assert "+ New Document" in bar_r3 and "docs/sop.md" in bar_r3
        assert "+ New Document" not in bar_r0 and ">Reset</button>" not in bar_r0
