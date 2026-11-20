"""Unit tests for zcg.web.ui.templates.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import Request
from zcg.web.ui.templates import (
    SafeHTML,
    TemplateCatalog,
    escape_html,
    html_t,
    render_icon,
    sanitize_url,
)


@dataclass(frozen=True)
class _AuthorBadge:
    name: str
    note: str | None = None


class TestTemplates:
    """Verify SafeHTML escaping, cascading TemplateCatalog inheritance, and respond_template."""

    def test_escape_html_preserves_safe_html_and_escapes_untrusted_strings_expected(self) -> None:
        """Verify SafeHTML passes verbatim while raw strings escape HTML entities and quotes."""
        # Arrange
        trusted = SafeHTML("<strong>Verified</strong>")
        untrusted = '<script>alert("xss")</script>'

        # Act
        safe_out = escape_html(trusted)
        escaped_out = escape_html(untrusted)
        str_repr = str(trusted)
        t_out = html_t(t"<div>{trusted}:{untrusted}</div>")

        # Assert
        assert safe_out == "<strong>Verified</strong>"
        assert str_repr == "<strong>Verified</strong>"
        assert "&lt;script&gt;" in escaped_out and "&quot;xss&quot;" in escaped_out
        assert isinstance(t_out, SafeHTML)
        assert "<strong>Verified</strong>:&lt;script&gt;" in t_out.value

    def test_template_catalog_cascading_dirs_inheritance_and_blocks_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify search_dirs priority over BUILTIN_TEMPLATES, extends/blocks, and block slicing."""
        # Arrange
        override_dir = tmp_path / "override_tpl"
        plugin_dir = tmp_path / "plugin_tpl"
        override_dir.mkdir()
        plugin_dir.mkdir()
        (plugin_dir / "page.html").write_text(
            '{% extends "base.html" %}\n'
            "{% block content %}<section>{{ heading }} {{ badge }}</section>{% endblock %}\n",
            encoding="utf-8",
        )
        (override_dir / "fragment.html").write_text(
            "{% block body %}<p>{{ label }}</p>{% endblock %}", encoding="utf-8"
        )
        catalog = TemplateCatalog((override_dir, plugin_dir))

        # Act
        full_html = catalog.render(
            "page.html",
            {"title": "Portal", "heading": "A & B", "badge": SafeHTML("<em>OK</em>")},
        )
        block_html = catalog.render(
            "page.html", {"heading": "Partial", "badge": "!"}, block_name="content"
        )
        standalone_html = catalog.render("fragment.html", {"label": "Standalone"})

        # Assert
        assert len(catalog.search_dirs) == 2
        assert "<title>Portal</title>" in full_html.value
        assert 'rel="icon" type="image/svg+xml" href="/static/img/logo.svg"' in full_html.value
        assert 'class="zcg-brand-logo"' in full_html.value
        assert "A &amp; B <em>OK</em>" in full_html.value
        assert block_html.value == "<section>Partial !</section>"
        assert standalone_html.value == "<p>Standalone</p>"

    def test_respond_template_switches_partial_swap_block_full_and_boosted_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify respond_template emits SWAP_SYNC on Z2 swaps and ISLAND_SYNC on full/boosted."""
        # Arrange
        tpl_dir = tmp_path / "tpl"
        tpl_dir.mkdir()
        (tpl_dir / "page.html").write_text(
            '{% extends "base.html" %}\n{% block content %}<p>{{ msg }}</p>{% endblock %}\n',
            encoding="utf-8",
        )
        (tpl_dir / "part.html").write_text("<span>{{ msg }}</span>", encoding="utf-8")
        catalog = TemplateCatalog((tpl_dir,))
        req_full = Request({"type": "http", "method": "GET", "path": "/"})
        req_swap = Request(
            {"type": "http", "method": "GET", "path": "/", "headers": [(b"hx-request", b"true")]}
        )
        req_boost = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"hx-request", b"true"), (b"hx-boosted", b"true")],
            }
        )

        # Act
        resp_full = catalog.respond_template(
            req_full, template_name="page.html", context={"title": "Home", "msg": "Full"}
        )
        resp_part = catalog.respond_template(
            req_swap, template_name="page.html", partial_name="part.html", context={"msg": "Part"}
        )
        resp_blk = catalog.respond_template(
            req_swap, template_name="page.html", block_name="content", context={"msg": "Blk"}
        )
        resp_tpl_swap = catalog.respond_template(
            req_swap, template_name="part.html", context={"msg": "Direct"}
        )
        resp_boost = catalog.respond_template(
            req_boost, template_name="page.html", partial_name="part.html", context={"msg": "Boost"}
        )

        # Assert
        assert (
            resp_full.channel == DeliveryChannel.ISLAND_SYNC
            and b"<!doctype html>" in resp_full.body
        )
        assert (
            resp_part.channel == DeliveryChannel.SWAP_SYNC
            and resp_part.body == b"<span>Part</span>"
        )
        assert resp_blk.channel == DeliveryChannel.SWAP_SYNC and resp_blk.body == b"<p>Blk</p>"
        assert resp_tpl_swap.body == b"<span>Direct</span>"
        assert (
            resp_boost.channel == DeliveryChannel.ISLAND_SYNC
            and b"<!doctype html>" in resp_boost.body
        )

    def test_template_catalog_rejects_traversal_and_missing_templates_or_blocks_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify bipolar path-containment guards and KeyError on unknown templates or blocks."""
        # Arrange
        catalog = TemplateCatalog((tmp_path,))

        # Act
        with pytest.raises(ValueError, match="PATH_CONTAINMENT_VIOLATION") as exc_rel:
            catalog.resolve_template_source("../secret.html")
        with pytest.raises(ValueError, match="PATH_CONTAINMENT_VIOLATION") as exc_abs:
            catalog.resolve_template_source("/etc/passwd")
        with pytest.raises(KeyError, match="Template not found") as exc_tpl:
            catalog.render("nonexistent.html")
        with pytest.raises(KeyError, match="Block 'missing' not found") as exc_blk:
            catalog.render("base.html", block_name="missing")

        # Assert
        assert exc_rel.value is not None and exc_abs.value is not None
        assert exc_tpl.value is not None and exc_blk.value is not None

    def test_plugin_shell_multi_level_inheritance_icons_and_cycle_depth_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 2-hop plugin_shell inheritance, SVG icons, and cycle/max-depth ValueError."""
        # Arrange
        tpl_dir = tmp_path / "multi"
        tpl_dir.mkdir()
        (tpl_dir / "plugin_idx.html").write_text(
            '{% extends "plugin_shell.html" %}\n'
            "{% block island %}<aside>{{ icon_cpu }} Island</aside>{% endblock %}\n",
            encoding="utf-8",
        )
        (tpl_dir / "cyc_a.html").write_text('{% extends "cyc_b.html" %}', encoding="utf-8")
        (tpl_dir / "cyc_b.html").write_text('{% extends "cyc_a.html" %}', encoding="utf-8")
        for idx in range(4):
            parent = f"lvl_{idx + 1}.html" if idx < 3 else "base.html"
            (tpl_dir / f"lvl_{idx}.html").write_text(f'{{% extends "{parent}" %}}', "utf-8")
        catalog = TemplateCatalog((tpl_dir,))

        # Act
        labelled_svg = render_icon("shield", label="Verified")
        rendered_shell = catalog.render(
            "plugin_idx.html", {"layer_id": "persona-profile", "panel_title": "Tower"}
        )
        with pytest.raises(KeyError, match="Unknown icon") as exc_icon:
            render_icon("nonexistent")
        with pytest.raises(ValueError, match="Circular template inheritance") as exc_cyc:
            catalog.render("cyc_a.html")
        with pytest.raises(ValueError, match="MAX_TEMPLATE_INHERITANCE_DEPTH") as exc_dep:
            catalog.render("lvl_0.html")

        # Assert
        assert 'aria-label="Verified"' in labelled_svg.value
        assert (
            "persona-profile — Tower" in rendered_shell.value and "Island" in rendered_shell.value
        )
        assert 'src="/static/img/logo.svg"' in rendered_shell.value
        assert exc_icon.value is not None and exc_cyc.value is not None
        assert exc_dep.value is not None

    def test_nested_blocks_and_ast_compiler_syntax_guards_expected(self, tmp_path: Path) -> None:
        """Verify nested {% block %} overrides and deterministic AST syntax error diagnostics."""
        # Arrange
        tpl_dir = tmp_path / "nested"
        tpl_dir.mkdir()
        (tpl_dir / "shell.html").write_text(
            '{% extends "base.html" %}\n'
            '{% block content %}<div class="shell">'
            "{% block sub_panel %}Default{% endblock %}</div>{% endblock %}\n",
            encoding="utf-8",
        )
        (tpl_dir / "leaf.html").write_text(
            '  {% extends "shell.html" %}\n'
            "{% block sub_panel %}<span>{{ label }}</span>{% endblock %}\n",
            encoding="utf-8",
        )
        bad_cases = {
            "unclosed_tag.html": ("Hello {{ title", "Unclosed template tag"),
            "bad_var.html": ("{{ bad-var }}", "Invalid template variable identifier"),
            "bad_stmt.html": ("{% unknown_op %}", "Unsupported or malformed template statement"),
            "late_ext.html": ('<p>x</p>{% extends "base.html" %}', "must appear once"),
            "stray_end.html": ("{% endblock %}", "Unexpected \\{% endblock %\\}"),
            "unclosed_blk.html": ("{% block content %}hi", "Unclosed template block"),
        }
        for fname, (src, _msg) in bad_cases.items():
            (tpl_dir / fname).write_text(src, encoding="utf-8")
        catalog = TemplateCatalog((tpl_dir,))

        # Act
        full_leaf = catalog.render("leaf.html", {"title": "Nested", "label": "Inner & Safe"})
        sub_only = catalog.render("leaf.html", {"label": "Sub"}, block_name="sub_panel")
        outer_blk = catalog.render("leaf.html", {"label": "Wrapped"}, block_name="content")

        # Assert
        assert '<div class="shell"><span>Inner &amp; Safe</span></div>' in full_leaf.value
        assert sub_only.value == "<span>Sub</span>"
        assert outer_blk.value == '<div class="shell"><span>Wrapped</span></div>'
        for fname, (_src, pat) in bad_cases.items():
            with pytest.raises(ValueError, match=pat):
                catalog.render(fname)

    def test_ast_if_for_include_dotted_paths_and_sanitize_url_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify {% if/else %}, {% for %}, {% include %}, dotted paths, and | safe_url."""
        # Arrange
        tpl_dir = tmp_path / "ast_ext"
        tpl_dir.mkdir()
        (tpl_dir / "item_row.html").write_text(
            "<li>{{ loop.index }}:{{ it.title }} ({{ author.name }}{{ author.note }})</li>",
            encoding="utf-8",
        )
        (tpl_dir / "view.html").write_text(
            '{% if active %}<a href="{{ link | safe_url }}">Go</a>{% else %}Off{% endif %}'
            "{% if not empty_flag %}<ul>{% for it in rows %}"
            '{% include "item_row.html" %}{% endfor %}</ul>{% endif %}'
            "{% for x in non_seq %}NEVER{% endfor %}{{ author.missing }}",
            encoding="utf-8",
        )
        (tpl_dir / "inc_self.html").write_text('{% include "inc_self.html" %}', encoding="utf-8")
        err_templates = {
            "bad_flt.html": ("{{ link | unknown }}", "Unsupported template filter"),
            "stray_else.html": ("{% else %}", "Unexpected \\{% else %\\}"),
            "dup_else.html": ("{% if a %}1{% else %}2{% else %}3{% endif %}", "Unexpected"),
            "mismatch_end.html": ("{% if a %}1{% endfor %}", "without matching"),
        }
        for fn, (src, _pat) in err_templates.items():
            (tpl_dir / fn).write_text(src, encoding="utf-8")
        cat = TemplateCatalog((tpl_dir,))

        # Act
        rendered_on = cat.render(
            "view.html",
            {
                "active": True,
                "link": "javascript:alert(1)",
                "empty_flag": False,
                "rows": [{"title": "Alpha"}, {"title": "Beta"}],
                "author": _AuthorBadge(name="Operator"),
                "non_seq": "string-not-list",
            },
        )
        rendered_off = cat.render("view.html", {"active": False, "empty_flag": True})

        # Assert
        assert '<a href="#">Go</a>' in rendered_on.value
        assert "<li>1:Alpha (Operator)</li><li>2:Beta (Operator)</li>" in rendered_on.value
        assert "NEVER" not in rendered_on.value
        assert rendered_off.value == "Off"
        assert sanitize_url("") == ""
        assert sanitize_url("http://localhost:8000/x\ny") == "#"
        assert sanitize_url("#sec") == "#sec" and sanitize_url("?p=2") == "?p=2"
        assert sanitize_url("/dashboard") == "/dashboard"
        assert sanitize_url("//evil.example/x") == "#"
        assert sanitize_url("items/2") == "items/2"
        assert sanitize_url("mailto:ops@iso.example", allow_mailto=True) == "mailto:ops@iso.example"
        assert sanitize_url("https://user@iso.example/x") == "#"
        assert sanitize_url("https://iso.example/docs") == "https://iso.example/docs"
        assert sanitize_url("http://portal.localhost:8790/a") == "http://portal.localhost:8790/a"
        assert sanitize_url("http://evil.example/a") == "#"
        with pytest.raises(ValueError, match="MAX_TEMPLATE_INCLUDE_DEPTH"):
            cat.render("inc_self.html")
        for fn, (_src, pat) in err_templates.items():
            with pytest.raises(ValueError, match=pat):
                cat.render(fn)
