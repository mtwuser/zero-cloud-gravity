"""Unit tests for zcg.mcp.catalogs.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

from zcg.mcp.catalogs import (
    MCP_PROMPTS_CATALOG,
    MCP_RESOURCES_CATALOG,
    MCP_TOOLS_CATALOG,
    resolve_bot_archetype,
    resolve_mcp_capability_profile,
)


class TestMCPCatalogs:
    """Verify MCP resource/prompt/tool catalogs, bot archetypes, and OOP capability profiles."""

    def test_catalogs_and_resolve_bot_archetype_registered_and_custom(self) -> None:
        """Verify catalog counts and resolve autonomous, actionable, and custom bot archetypes."""
        # Arrange
        # Act
        auto_bot = resolve_bot_archetype("security-auditor-bot")
        act_bot = resolve_bot_archetype("refactoring-surgeon-bot")
        custom_bot = resolve_bot_archetype("custom-telemetry-bot")

        # Assert
        assert len(MCP_RESOURCES_CATALOG) == 9
        assert len(MCP_PROMPTS_CATALOG) == 3
        assert len(MCP_TOOLS_CATALOG) == 9
        assert auto_bot["catalog_registered"] is True
        assert auto_bot["execution_autonomy"] == "autonomous-scope-bounded"
        assert act_bot["execution_autonomy"] == "actionable-gated"
        assert custom_bot["catalog_registered"] is False
        assert custom_bot["family"] == "custom-departmental"

    def test_resolve_mcp_capability_profile_all_pro_and_active_leases(self) -> None:
        """Compute capability rings for dev/pro environments and hot-plugged ephemeral leases."""
        # Arrange
        manifest = {
            "layer_id": "dept-sec",
            "layer_role": "department",
            "environments": {"pre": {"access_mode": "strictly-read-only"}},
        }
        leases = [
            {
                "fork_id": "eph-sec-1",
                "bot_role": "security-auditor-bot",
                "remaining_ttl_seconds": 90,
            },
            {
                "fork_id": "eph-ref-2",
                "bot_role": "refactoring-surgeon-bot",
                "remaining_ttl_seconds": 60,
            },
        ]

        # Act
        dev_prof = resolve_mcp_capability_profile(
            manifest,
            environment="dev",
            active_ephemeral_forks=leases,
            family_filter="audit-and-compliance",
        )
        pro_prof = resolve_mcp_capability_profile(manifest, environment="pro")
        pre_prof = resolve_mcp_capability_profile(manifest, environment="pre")

        # Assert
        assert len(dev_prof["oop_capability_inheritance"]["granted_ring_ids"]) == 5
        assert dev_prof["permanent_ephemeral_symbiosis"]["symbiotic_state"] == "ephemeral-augmented"
        assert dev_prof["permanent_ephemeral_symbiosis"]["mcp_autonomy_matrix"][
            "active_autonomous_leases"
        ] == ["eph-sec-1"]
        assert dev_prof["permanent_ephemeral_symbiosis"]["mcp_autonomy_matrix"][
            "active_actionable_leases"
        ] == ["eph-ref-2"]
        assert all(b["family"] == "audit-and-compliance" for b in dev_prof["bot_archetype_catalog"])
        assert len(pro_prof["oop_capability_inheritance"]["granted_ring_ids"]) == 3
        assert len(pre_prof["oop_capability_inheritance"]["granted_ring_ids"]) == 3
