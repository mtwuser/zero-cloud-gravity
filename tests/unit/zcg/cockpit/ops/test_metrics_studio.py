"""Unit tests for zcg.cockpit.ops.metrics_studio.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from zcg.cockpit.ops.metrics_studio import (
    render_cli_transparency_hint,
    render_metrics_view_html,
)


class TestMetricsStudio:
    """Verify collapsible CLI transparency hint and 3-scope Workspace Metrics Studio HTML."""

    def test_render_cli_transparency_hint_covers_empty_partial_and_escaped_inputs_expected(
        self,
    ) -> None:
        """Verify CLI hint returns empty on blank inputs and escapes tracked files and commands."""
        # Arrange
        files = ("WORKTASK.md", "docs/<spec>.md", " ")
        cmds = ("zcg status .", "make task TASK=<id>")

        # Act
        empty_html = render_cli_transparency_hint((), ("  ",))
        files_only = render_cli_transparency_hint(("WORKTASK.md",), ())
        cmds_only = render_cli_transparency_hint((), ("make diff",))
        full_html = render_cli_transparency_hint(files, cmds, summary_label="CLI <Hint>")

        # Assert
        assert empty_html == ""
        assert "Tracked files:" in files_only and "Manual CLI:" not in files_only
        assert "Manual CLI:" in cmds_only and "Tracked files:" not in cmds_only
        assert "data-zcg-cli-hint" in full_html and "<script" not in full_html.lower()
        assert "CLI &lt;Hint&gt;" in full_html
        assert "docs/&lt;spec&gt;.md" in full_html
        assert "data-zcg-copy='make task TASK=&lt;id&gt;'" in full_html

    def test_render_metrics_view_html_covers_scopes_progress_bars_tables_and_units_expected(
        self,
    ) -> None:
        """Verify 4 cards, byte formatting (B/KB/MB), scope switchers, and node/empty tables."""
        # Arrange
        base_node = {
            "node_id": "corp-iso",
            "layer_role": "corporate",
            "work": {"completion_pct": 75, "backlog_open_count": 2},
            "knowledge": {"total_docs": 4},
            "vault": {"vault_files": 2},
        }
        node_report = {
            "scope": "node",
            "work": {
                "completion_pct": 75,
                "done_count": 3,
                "in_progress_count": 1,
                "todo_count": 0,
                "backlog_open_count": 2,
                "roadmap_done_count": 1,
                "roadmap_total_count": 2,
                "validation_verified_count": 2,
                "validation_total_count": 2,
                "inbox_pending_count": 1,
            },
            "knowledge": {"total_docs": 4, "r3_count": 1, "r2_count": 2, "r0_count": 1},
            "vault": {"vault_files": 2, "vault_bytes": 2048},
            "git_sync": {"git_dirty_count": 1, "git_ahead": 0, "git_behind": 0},
            "nodes": [base_node],
        }
        network_report = {
            **node_report,
            "scope": "network",
            "vault": {"vault_files": 3, "vault_bytes": 2 * 1024 * 1024},
            "nodes": [
                base_node,
                {
                    "node_id": "squad-iso",
                    "layer_role": "squad",
                    "work": {"completion_pct": 50, "backlog_open_count": 1},
                    "knowledge": {"total_docs": 2},
                    "vault": {"vault_files": 1},
                },
                {"node_id": "minimal-iso"},
            ],
        }
        empty_corpora = {"scope": "corpora", "nodes": []}
        empty_network = {"scope": "network", "nodes": []}
        all_report = {**node_report, "scope": "all"}

        # Act
        node_html = render_metrics_view_html(
            node_report, posture_score=95, skill_trust_score=90, health_state="ATTENTION"
        )
        ws_html = render_metrics_view_html(all_report, layer_role="workstation")
        net_html = render_metrics_view_html(network_report)
        corp_html = render_metrics_view_html(empty_corpora)
        net_empty_html = render_metrics_view_html(empty_network)
        minimal_html = render_metrics_view_html({})

        # Assert
        assert "data-zcg-metrics-view" in node_html and "<script" not in node_html.lower()
        assert "metrics_scope=" not in node_html and "role='tablist'" not in node_html
        assert "zcg workstation-audit" not in node_html
        assert "make workstation-audit" not in node_html
        assert "make workstation-audit" in ws_html and "zcg status ." in ws_html
        assert "Work &amp; Delivery Velocity" in node_html and "75% Done" in node_html
        assert (
            "Knowledge &amp; Visibility Footprint" in node_html and "🔒 Internal (R3)" in node_html
        )
        assert "2.0 KB" in node_html and "Security Posture: <strong>95/100</strong>" in node_html
        assert "Skill Trust: <strong>90/100</strong>" in node_html
        assert "Node Health: <strong>ATTENTION</strong>" in node_html
        assert "<table class='zcg-table'>" not in node_html
        assert "data-zcg-cli-hint" in node_html
        assert "<table class='zcg-table'>" in net_html and "squad-iso" in net_html
        assert "minimal-iso" in net_html and "2.0 MB" in net_html
        assert "0 connected corpora discovered in this scope." in corp_html
        assert "0 B" in corp_html and "0% Done" in minimal_html
        assert "0 nodes discovered in this scope." in net_empty_html
