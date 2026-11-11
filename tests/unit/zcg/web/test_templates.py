"""Unit tests for zcg.web.templates.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zcg.web.channels import DeliveryChannel
from zcg.web.request import Request
from zcg.web.templates import SafeHTML, TemplateCatalog, escape_html, render_icon


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

        # Assert
        assert safe_out == "<strong>Verified</strong>"
        assert str_repr == "<strong>Verified</strong>"
        assert "&lt;script&gt;" in escaped_out and "&quot;xss&quot;" in escaped_out

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
            "plugin_idx.html", {"layer_id": "alex-pc", "panel_title": "Tower"}
        )
        with pytest.raises(KeyError, match="Unknown icon") as exc_icon:
            render_icon("nonexistent")
        with pytest.raises(ValueError, match="Circular template inheritance") as exc_cyc:
            catalog.render("cyc_a.html")
        with pytest.raises(ValueError, match="MAX_TEMPLATE_INHERITANCE_DEPTH") as exc_dep:
            catalog.render("lvl_0.html")

        # Assert
        assert 'aria-label="Verified"' in labelled_svg.value
        assert "alex-pc — Tower" in rendered_shell.value and "Island" in rendered_shell.value
        assert exc_icon.value is not None and exc_cyc.value is not None
        assert exc_dep.value is not None
