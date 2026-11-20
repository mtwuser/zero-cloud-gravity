"""Unit tests for zcg.governance.runtime.tool_catalog.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from zcg.governance.runtime.tool_catalog import (
    DEFAULT_EXTERNAL_MCP_CONNECTORS,
    DEFAULT_ISOLATED_TOOL_CATALOG,
    resolve_tool_node_relevance,
)


class TestToolCatalog:
    """Verify opt-in isolated tool descriptors and external MCP connector specifications."""

    def test_isolated_tool_and_mcp_connector_catalogs_expected(self) -> None:
        """Verify sovereign zcg-skill-auditor, gemini-decisions, and connector catalog entries."""
        # Arrange
        expected_tools = {
            "zcg-skill-auditor",
            "secops-guardian",
            "container-edge-ops",
            "google-cloud-ops",
            "gemini-decisions",
            "duckdb-analytics",
            "wallet-analytics",
        }
        expected_connectors = {
            "remote-streamable-http",
            "github-official",
            "google-cloud-gcloud",
            "google-cloud-run-remote",
        }

        # Act
        serialized = {k: v.to_dict() for k, v in DEFAULT_ISOLATED_TOOL_CATALOG.items()}

        # Assert
        assert set(serialized) == expected_tools
        assert serialized["zcg-skill-auditor"]["upstream_engine"] == "zcg-skill-auditor+osv-scanner"
        assert serialized["gemini-decisions"]["upstream_engine"] == (
            "gemini-decision-1/litert-gemma-4-26b-a4b-it"
        )
        assert serialized["container-edge-ops"]["sandbox_driver"] == "bwrap-readonly"
        assert serialized["container-edge-ops"]["requires_network"] is False
        assert set(DEFAULT_EXTERNAL_MCP_CONNECTORS) == expected_connectors
        assert DEFAULT_EXTERNAL_MCP_CONNECTORS["remote-streamable-http"].transport == (
            "streamable-http"
        )
        assert resolve_tool_node_relevance("zcg-skill-auditor", None) is True
        assert resolve_tool_node_relevance("secops-guardian", {"layer_role": "workstation"}) is True
        assert resolve_tool_node_relevance("secops-guardian", {"layer_role": "squad"}) is False
        assert resolve_tool_node_relevance("wallet-analytics", {"layer_id": "iso-wallet"}) is True
        assert (
            resolve_tool_node_relevance(
                "container-edge-ops", {"default_stack_templates": ["self-hosted-container"]}
            )
            is True
        )
        assert (
            resolve_tool_node_relevance(
                "google-cloud-ops", {"default_stack_templates": ["google-cloud-iac"]}
            )
            is True
        )
        assert resolve_tool_node_relevance("duckdb-analytics", {"layer_role": "knowledge"}) is True
        assert resolve_tool_node_relevance("unknown-tool", {}) is False
