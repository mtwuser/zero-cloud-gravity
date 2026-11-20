"""Unit tests for zcg.core.ast_graph.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zcg.core.ast_graph import (
    AST_GRAPH_CONTRACT_REV,
    CLUSTER_MODULE_MIN_LINES,
    M_CLUSTER_WARN_LINES,
    build_codebase_ast_graph,
)


class TestAstGraph:
    """Verify zero-LLM stdlib AST module graph, 1:1:1 citations, and M_cluster detection."""

    def test_build_codebase_ast_graph_full_metadata_citations_and_m_clusters_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify AST classes/functions, relative/absolute imports, CITED links, and M_cluster."""
        # Arrange
        ws = tmp_path / "sample-repo"
        (ws / "src/pkg").mkdir(parents=True)
        (ws / "tests/unit/pkg").mkdir(parents=True)
        (ws / "src/pkg/__init__.py").write_text("", encoding="utf-8")
        (ws / "src/root_mod.py").write_text(
            "CONST = 1\n\ndef root_helper() -> int:\n    return CONST\n",
            encoding="utf-8",
        )
        (ws / "src/pkg/alpha.py").write_text(
            '"""Alpha module.\n\n'
            'Specification: docs/architecture/01_core_and_node_manifest.md\n"""\n'
            "import json\n"
            "import pkg.alpha\n"
            "import pkg.light\n"
            "from external_pkg import missing\n"
            "from . import alpha, light\n"
            "from .light import light_fn\n"
            "from .. import root_mod\n"
            "from ..root_mod import root_helper\n\n"
            "class PublicEntity:\n    pass\n\n"
            "class _PrivateEntity:\n    pass\n\n"
            "def public_action() -> None:\n    pass\n\n"
            "async def async_action() -> None:\n    pass\n\n"
            "def _private_helper() -> None:\n    pass\n",
            encoding="utf-8",
        )
        (ws / "tests/unit/pkg/test_alpha.py").write_text("# unit\n", encoding="utf-8")
        (ws / "src/pkg/light.py").write_text(
            "def light_fn() -> int:\n    return 1\n", encoding="utf-8"
        )
        (ws / "src/pkg/broken.py").write_text("def broken(:\n", encoding="utf-8")

        pad = "\n" * (CLUSTER_MODULE_MIN_LINES + 25)
        (ws / "src/pkg/heavy_iso.py").write_text(
            f"import pkg.light\n{pad}def iso() -> int:\n    return 0\n",
            encoding="utf-8",
        )
        (ws / "src/pkg/heavy_a.py").write_text(
            f"import pkg.heavy_b\nimport pkg.heavy_c\n{pad}def fa() -> int:\n    return 1\n",
            encoding="utf-8",
        )
        (ws / "src/pkg/heavy_b.py").write_text(
            f"import pkg.heavy_c\n{pad}def fb() -> int:\n    return 2\n",
            encoding="utf-8",
        )
        (ws / "src/pkg/heavy_c.py").write_text(
            f"import pkg.heavy_a\n{pad}def fc() -> int:\n    return 3\n",
            encoding="utf-8",
        )

        # Act
        graph = build_codebase_ast_graph(ws)
        by_mod = {m["module_id"]: m for m in graph["modules"]}

        # Assert
        assert graph["contract_rev"] == AST_GRAPH_CONTRACT_REV
        assert graph["has_cycle"] is False
        assert "root_mod" in graph["topological_order"]
        assert by_mod["pkg.alpha"]["classes"] == ["PublicEntity"]
        assert by_mod["pkg.alpha"]["functions"] == ["async_action", "public_action"]
        assert by_mod["pkg.alpha"]["imports"] == ["pkg.light", "root_mod"]
        assert (
            by_mod["pkg.alpha"]["spec_target"] == "docs/architecture/01_core_and_node_manifest.md"
        )
        assert by_mod["pkg.alpha"]["unit_test_path"] == "tests/unit/pkg/test_alpha.py"
        assert by_mod["pkg.broken"]["parse_ok"] is False
        assert any(e["kind"] == "CITED" and e["relation"] == "spec-link" for e in graph["edges"])
        assert any(
            e["kind"] == "CITED" and e["relation"] == "unit-test-link" for e in graph["edges"]
        )
        assert len(graph["m_clusters"]) == 1
        cluster = graph["m_clusters"][0]
        assert cluster["modules"] == ["pkg.heavy_a", "pkg.heavy_b", "pkg.heavy_c"]
        assert cluster["total_lines"] >= M_CLUSTER_WARN_LINES
        assert cluster["warn_exceeded"] is True

    def test_build_codebase_ast_graph_empty_cycle_and_containment_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify missing src dir returns empty graph, cycles report has_cycle, and escape fails."""
        # Arrange
        empty_ws = tmp_path / "empty-ws"
        empty_ws.mkdir()
        cyc_ws = tmp_path / "cycle-ws"
        (cyc_ws / "src/pkg_a").mkdir(parents=True)
        (cyc_ws / "src/pkg_b").mkdir(parents=True)
        (cyc_ws / "src/pkg_a/one.py").write_text("import pkg_b.two\n", encoding="utf-8")
        (cyc_ws / "src/pkg_b/two.py").write_text("import pkg_a.one\n", encoding="utf-8")

        # Act
        empty_graph = build_codebase_ast_graph(empty_ws)
        cyc_graph = build_codebase_ast_graph(cyc_ws)

        # Assert
        assert empty_graph["module_count"] == 0 and empty_graph["packages"] == []
        assert cyc_graph["has_cycle"] is True
        assert cyc_graph["topological_order"] == []
        assert len(cyc_graph["cycle_nodes"]) >= 2
        with pytest.raises(ValueError, match="PATH_CONTAINMENT_VIOLATION"):
            build_codebase_ast_graph(empty_ws, src_rel_dir="../cycle-ws")
