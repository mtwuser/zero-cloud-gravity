"""Unit tests for zcg.ephemeral.briefs.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

from typing import Any

from zcg.ephemeral.briefs import build_subagent_invocation_brief, extract_ephemeral_advisories


class TestEphemeralBriefs:
    """Verify Department Bot advisory extraction and Antigravity subagent invocation briefs."""

    def test_extract_ephemeral_advisories_deduplicates_and_skips_empty(self) -> None:
        """Extract unique bot advisories from surface bindings while ignoring empty policies."""
        # Arrange
        bindings: list[dict[str, Any]] = [
            {"binding_id": "b0"},
            {
                "layer": "dept-sec",
                "binding_id": "b1",
                "ephemeral_fork_policy": {"bot_role": "sec-auditor", "mount_templates": ["sec"]},
            },
            {
                "layer": "dept-sec",
                "binding_id": "b2",
                "ephemeral_fork_policy": {"bot_role": "sec-auditor"},
            },
        ]

        # Act
        advisories = extract_ephemeral_advisories(bindings, "")

        # Assert
        assert len(advisories) == 1
        assert advisories[0]["bot_role"] == "sec-auditor"
        assert advisories[0]["recommended_mcp_call"]["arguments"]["target_path"] == "*"

    def test_build_subagent_invocation_brief_ro_and_rw_modes(self) -> None:
        """Build research (read-only) and self (read-write) subagent invocation briefs."""
        # Arrange
        ro_manifest = {
            "ephemeral_metadata": {
                "bot_role": "auditor",
                "access_mode": "strictly-read-only",
                "model_tier": "flash",
            }
        }
        rw_manifest = {
            "ephemeral_metadata": {
                "bot_role": "builder",
                "access_mode": "read-write-scoped",
                "model_tier": "inherit",
            }
        }
        projection = {"effective_invariants": ["Inv 1", "Inv 2"], "canonical_templates": ["t1.md"]}

        # Act
        ro_brief = build_subagent_invocation_brief(
            ro_manifest, "src/zcg/core/constants.py", projection, "rcap1.header.cipher.sig"
        )
        rw_brief = build_subagent_invocation_brief(rw_manifest, "", projection, None)

        # Assert
        assert ro_brief["subagent_type"] == "research"
        assert "Sealed Capsule:" in ro_brief["prompt"]
        assert rw_brief["subagent_type"] == "self"
        assert rw_brief["target_path"] == "*"
        assert "Sealed Capsule:" not in rw_brief["prompt"]
