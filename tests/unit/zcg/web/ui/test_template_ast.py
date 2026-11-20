"""Unit tests for zcg.web.ui.template_ast.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from zcg.web.ui.template_ast import (
    SafeHTML,
    compile_template_source,
    escape_html,
    evaluate_template_nodes,
    html_t,
    sanitize_url,
)


@dataclass(frozen=True)
class _SampleAuthor:
    name: str
    note: str | None = None


class TestTemplateAst:
    """Verify deterministic AST compilation, evaluation, SafeHTML, and sanitize_url guards."""

    def test_sanitize_url_and_escape_html_across_schemes_and_control_bytes_expected(self) -> None:
        """Verify SafeHTML passthrough, HTML escaping, and URL scheme/host sanitization."""
        # Arrange
        trusted = SafeHTML("<b>OK</b>")
        untrusted = '<a href="x">'

        # Act
        s_html = escape_html(trusted)
        e_html = escape_html(untrusted)
        s_str = str(trusted)

        # Assert
        assert s_html == "<b>OK</b>" and s_str == "<b>OK</b>"
        assert e_html == "&lt;a href=&quot;x&quot;&gt;"
        assert sanitize_url("") == ""
        assert sanitize_url("http://localhost:8000/a\nb") == "#"
        assert sanitize_url("#top") == "#top" and sanitize_url("?page=2") == "?page=2"
        assert sanitize_url("/dashboard") == "/dashboard"
        assert sanitize_url("//evil.example/x") == "#"
        assert sanitize_url("items/2") == "items/2"
        assert sanitize_url("mailto:ops@iso.example", allow_mailto=True) == "mailto:ops@iso.example"
        assert sanitize_url("mailto:ops@iso.example", allow_mailto=False) == "#"
        assert sanitize_url("https://user@iso.example/x") == "#"
        assert sanitize_url("https://iso.example/docs") == "https://iso.example/docs"
        assert sanitize_url("http://portal.localhost:8790/a") == "http://portal.localhost:8790/a"
        assert sanitize_url("http://evil.example/a") == "#"
        assert sanitize_url("javascript:alert(1)") == "#"

    def test_compile_and_evaluate_blocks_if_else_for_include_and_safe_url_expected(self) -> None:
        """Verify AST compilation and evaluation across blocks, if/else, for, and include."""
        # Arrange
        partials = {
            "row.html": (
                "<li>{{ loop.index }}:{{ it.title }} ({{ author.name }}{{ author.note }})</li>"
            ),
            "self.html": '{% include "self.html" %}',
        }
        src = (
            '{% extends "base.html" %}'
            "{% block content %}"
            '{% if active %}<a href="{{ link | safe_url }}">Go</a>{% else %}Off{% endif %}'
            "{% if not empty_flag %}<ul>{% for it in rows %}"
            '{% include "row.html" %}{% endfor %}</ul>{% endif %}'
            "{% for x in non_seq %}NEVER{% endfor %}{{ author.missing }}{{ absent }}"
            "{% endblock %}Tail"
        )

        # Act
        compiled = compile_template_source(src)
        out_on = evaluate_template_nodes(
            compiled.nodes,
            compiled.blocks,
            {
                "active": True,
                "link": "javascript:alert(1)",
                "empty_flag": False,
                "rows": [{"title": "Alpha"}, {"title": "Beta"}],
                "author": _SampleAuthor(name="Operator"),
                "non_seq": "text",
            },
            lambda name: partials[name],
        )
        out_off = evaluate_template_nodes(
            compiled.nodes,
            compiled.blocks,
            {"active": False, "empty_flag": True},
            lambda name: partials[name],
        )
        cyc_compiled = compile_template_source(partials["self.html"])

        # Assert
        assert compiled.extends_name == "base.html"
        assert '<a href="#">Go</a>' in out_on
        assert "<li>1:Alpha (Operator)</li><li>2:Beta (Operator)</li>" in out_on
        assert out_on.endswith("Tail") and "NEVER" not in out_on
        assert out_off == "OffTail"
        with pytest.raises(ValueError, match="MAX_TEMPLATE_INCLUDE_DEPTH"):
            evaluate_template_nodes(cyc_compiled.nodes, {}, {}, lambda name: partials[name])

    def test_compile_template_source_rejects_malformed_tags_and_mismatched_frames_expected(
        self,
    ) -> None:
        """Verify deterministic syntax errors across all malformed variable and block forms."""
        # Arrange
        bad_inputs = (
            ("Hello {{ title", "Unclosed template tag"),
            ("{{ _private }}", "Invalid template variable identifier"),
            ("{{ link | bad_flt }}", "Unsupported template filter"),
            ("{% unknown %}", "Unsupported or malformed template statement"),
            ("{% if bad-cond %}", "Unsupported or malformed template statement"),
            ("{% for x %}", "Unsupported or malformed template statement"),
            ("{% include bad %}", "Unsupported or malformed template statement"),
            ('<p>x</p>{% extends "base.html" %}', "must appear once"),
            ("{% else %}", "Unexpected \\{% else %\\}"),
            ("{% if a %}1{% else %}2{% else %}3{% endif %}", "Unexpected \\{% else %\\}"),
            ("{% endblock %}", "Unexpected \\{% endblock %\\}"),
            ("{% if a %}1{% endfor %}", "without matching"),
            ("{% block body %}unclosed", "Unclosed template block"),
        )

        # Act
        caught: list[str] = []
        for raw_tpl, expected_msg in bad_inputs:
            with pytest.raises(ValueError, match=expected_msg) as exc_info:
                compile_template_source(raw_tpl)
            caught.append(str(exc_info.value))

        # Assert
        assert len(caught) == len(bad_inputs)

    def test_html_t_auto_escapes_sanitizes_urls_joins_iterables_and_guards_specs_expected(
        self,
    ) -> None:
        """Verify PEP 750 html_t across empty, default, url, mailto_url, join, and error guards."""
        # Arrange
        raw_txt = "<script>\"x\"&'y'</script>"
        trusted = SafeHTML("<em>ok</em>")
        safe_link = "https://iso.example/docs?a=1&b=2"
        evil_link = "javascript:alert(1)"
        mail_link = "mailto:ops@iso.example"
        rows = [SafeHTML("<li>A</li>"), "<b>B</b>"]
        empty_rows: tuple[str, ...] = ()

        # Act
        out_empty = html_t(t"")
        out_full = html_t(
            t"<p>{raw_txt}{trusted}</p>"
            t'<a href="{safe_link:url}">S</a>'
            t'<a href="{evil_link:url}">E</a>'
            t'<a href="{mail_link:mailto_url}">M</a>'
            t'<a href="{evil_link:mailto_url}">X</a>'
            t"<ul>{rows:join}{empty_rows:join}</ul>"
        )

        # Assert
        assert out_empty == SafeHTML("")
        assert isinstance(out_full, SafeHTML)
        assert "&lt;script&gt;&quot;x&quot;&amp;&#x27;y&#x27;&lt;/script&gt;<em>ok</em>" in (
            out_full.value
        )
        assert 'href="https://iso.example/docs?a=1&amp;b=2"' in out_full.value
        assert 'href="#">E</a>' in out_full.value
        assert 'href="mailto:ops@iso.example">M</a>' in out_full.value
        assert 'href="#">X</a>' in out_full.value
        assert "<ul><li>A</li>&lt;b&gt;B&lt;/b&gt;</ul>" in out_full.value
        for bad_val in ("text", b"bytes", {"a": 1}, 42):
            with pytest.raises(ValueError, match="requires a non-string Iterable"):
                html_t(t"{bad_val:join}")
        with pytest.raises(ValueError, match="Unsupported html_t format_spec"):
            html_t(t"{raw_txt:bad_spec}")
