"""Unit tests for zcg.mcp.unfold.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.capsules.codec import CapsuleError, derive_chain_key, seal_single_capsule
from zcg.capsules.constants import L3_EXCERPT_MAX_CHARS
from zcg.capsules.surfaces import build_section_capsule
from zcg.core.constants import CAPSULE_HMAC_HEX_LEN
from zcg.mcp.unfold import UnfoldMixin


def _seed_unfold_repo(repo: Path) -> None:
    for d in ("system", "docs", "antigravity/.gemini/config"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (repo / "system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "node-u",
                "baseline_guardrails": ["Root Guard"],
                "environments": {"pro": {"default_guardrails": ["Pro Guard"]}},
            }
        ),
        encoding="utf-8",
    )
    (repo / "antigravity/.gemini/config/AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo / "docs/linked.md").write_text("x" * (L3_EXCERPT_MAX_CHARS + 50), encoding="utf-8")
    (repo / "docs/spec.md").write_text(
        "# Root\n## Core Law\nEnforce `docs/linked.md` strictly.\n", encoding="utf-8"
    )


class TestMCPUnfold:
    """Verify ephemeral issuer resolution and progressive L0->L1->L2->L3 capsule unfolding."""

    def test_resolve_ephemeral_issuer_meta_memory_disk_and_misses(self, tmp_path: Path) -> None:
        """Resolve active ephemeral issuer metadata from memory and disk or return None."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_unfold_repo(repo)
        node = UnfoldMixin(repo_dir=repo)
        node.ephemeral_memory_store["eph-mem-1"] = {
            "parent_layer_id": "node-u",
            "expires_at_epoch": 9999999999.0,
            "manifest": {
                "ephemeral_metadata": {"parent_layer_id": "node-u", "session_resonance_key": "mk"}
            },
        }
        disk_f = repo / "logs/ephemeral_forks/eph-disk-1/system"
        disk_f.mkdir(parents=True)
        (disk_f / "zcg-node.json").write_text(
            json.dumps(
                {
                    "ephemeral_metadata": {
                        "parent_layer_id": "node-u",
                        "expires_at_epoch": 9999999999.0,
                        "session_resonance_key": "dk",
                    }
                }
            ),
            encoding="utf-8",
        )

        # Act
        assert node.resolve_ephemeral_issuer_meta("other-node", "node-u") is None
        assert node.resolve_ephemeral_issuer_meta("eph-mem-1", "node-u") == {
            "parent_layer_id": "node-u",
            "session_resonance_key": "mk",
        }
        disk_meta = node.resolve_ephemeral_issuer_meta("eph-disk-1", "node-u")
        assert disk_meta is not None
        assert disk_meta["session_resonance_key"] == "dk"
        assert node.resolve_ephemeral_issuer_meta("eph-disk-1", "other-parent") is None
        # Assert
        assert node.resolve_ephemeral_issuer_meta("eph-missing", "node-u") is None

    def test_unfold_l0_to_l3_line_relocation_and_ephemeral_bridge(self, tmp_path: Path) -> None:
        """Unfold L0->L1->L2->L3, relocate line-drifted sections, and unfold bridged rules."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_unfold_repo(repo)
        node = UnfoldMixin(repo_dir=repo)
        q_res = json.loads(
            node.tool_query_governance_rules(
                {
                    "query": "core law",
                    "resolution": "L0",
                    "environment": "pro",
                    "resonance_key": "rk",
                }
            )["content"][0]["text"]
        )
        tok_l0 = q_res["matches"][0]["capsule_token"]
        (repo / "docs/spec.md").write_text(
            "# Root\n\nIntro line\n\n## Core Law\nEnforce `docs/linked.md` strictly.\n",
            encoding="utf-8",
        )

        # Act
        u_l0 = json.loads(
            node.tool_unfold_context_capsule(
                {
                    "capsule_token": tok_l0,
                    "target_level": "L0",
                    "environment": "pro",
                    "resonance_key": "rk",
                }
            )["content"][0]["text"]
        )
        u_l1 = json.loads(
            node.tool_unfold_context_capsule(
                {
                    "capsule_token": tok_l0,
                    "target_level": "L1",
                    "environment": "pro",
                    "resonance_key": "rk",
                }
            )["content"][0]["text"]
        )
        u_l2 = json.loads(
            node.tool_unfold_context_capsule(
                {
                    "capsule_token": u_l1["next_capsule_token"],
                    "target_level": "L2",
                    "environment": "pro",
                    "resonance_key": "rk",
                }
            )["content"][0]["text"]
        )
        u_l3 = json.loads(
            node.tool_unfold_context_capsule(
                {
                    "capsule_token": u_l2["next_capsule_token"],
                    "target_level": "L3",
                    "agent_tier": "pro",
                    "environment": "pro",
                    "resonance_key": "rk",
                }
            )["content"][0]["text"]
        )

        bridge_md = "# Bridge\n## Local Rule\nKeep strict.\n"
        node.ephemeral_memory_store["eph-br-1"] = {
            "parent_layer_id": "node-u",
            "expires_at_epoch": 9999999999.0,
            "manifest": {
                "ephemeral_metadata": {
                    "parent_layer_id": "node-u",
                    "session_resonance_key": "bk",
                    "bridge_layer_id": "bridge-p",
                    "bridge_agents_md": bridge_md,
                    "bridge_manifest": {
                        "baseline_guardrails": ["Bridge Guard"],
                        "federated_mcps": [],
                    },
                }
            },
        }
        _, b_tok = build_section_capsule(
            issuer_id="eph-br-1",
            resolution="L0",
            layer_name="ephemeral-project-bridge",
            rel_in_layer="antigravity/.gemini/config/AGENTS.md",
            heading="Local Rule",
            start_line=2,
            end_line=3,
            scope="all",
            l1_skeleton="## Local Rule\nKeep strict.",
            l2_excerpt="## Local Rule\nKeep strict.",
            l2_full="## Local Rule\nKeep strict.",
            l3_links=[],
            env_scope="all",
            secret=b"bk",
        )
        u_bridge = json.loads(
            node.tool_unfold_context_capsule({"capsule_token": b_tok, "target_level": "L3"})[
                "content"
            ][0]["text"]
        )

        # Assert
        assert u_l0["unfolded_level"] == "L0"
        assert u_l1["line_drift_relocated"] is True
        assert u_l2["unfolded_level"] == "L2"
        assert u_l3["unfolded_level"] == "L3"
        assert u_l3["truncated"] is True
        assert "Pro Guard" in u_l3["content"]["effective_guardrails"]
        assert "Bridge Guard" in u_bridge["content"]["effective_guardrails"]

    def test_unfold_security_and_integrity_error_branches(self, tmp_path: Path) -> None:
        """Emit structured alerts and raise CapsuleError/ValueError across all failure gates."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_unfold_repo(repo)
        node = UnfoldMixin(repo_dir=repo)
        q_res = json.loads(
            node.tool_query_governance_rules(
                {
                    "query": "core law",
                    "resolution": "L1",
                    "environment": "pro",
                    "resonance_key": "rk",
                }
            )["content"][0]["text"]
        )
        tok = q_res["matches"][0]["capsule_token"]

        # Act
        with pytest.raises(CapsuleError, match="Recovery"):
            node.tool_unfold_context_capsule({"capsule_token": "bad.token"})
        with pytest.raises(ValueError, match="Invalid target_level"):
            node.tool_unfold_context_capsule({"capsule_token": tok, "target_level": "L9"})
        with pytest.raises(ValueError, match="Invalid agent_tier"):
            node.tool_unfold_context_capsule({"capsule_token": tok, "agent_tier": "god"})
        with pytest.raises(ValueError, match="Invalid environment"):
            node.tool_unfold_context_capsule({"capsule_token": tok, "environment": "mars"})
        with pytest.raises(CapsuleError, match="bound to env"):
            node.tool_unfold_context_capsule({"capsule_token": tok, "environment": "dev"})
        with pytest.raises(CapsuleError, match="requires explicit resonance_key"):
            node.tool_unfold_context_capsule({"capsule_token": tok, "environment": "pro"})
        with pytest.raises(CapsuleError, match="signature verification failed"):
            node.tool_unfold_context_capsule(
                {"capsule_token": tok, "environment": "pro", "resonance_key": "wrong"}
            )
        with pytest.raises(ValueError, match="must be deeper"):
            node.tool_unfold_context_capsule(
                {
                    "capsule_token": tok,
                    "target_level": "L1",
                    "environment": "pro",
                    "resonance_key": "rk",
                }
            )
        with pytest.raises(CapsuleError, match="insufficient"):
            node.tool_unfold_context_capsule(
                {
                    "capsule_token": tok,
                    "target_level": "L3",
                    "agent_tier": "flash",
                    "environment": "pro",
                    "resonance_key": "rk",
                }
            )

        _, foreign_tok = build_section_capsule(
            issuer_id="foreign-node",
            resolution="L0",
            layer_name="root",
            rel_in_layer="docs/spec.md",
            heading="Core Law",
            start_line=2,
            end_line=3,
            scope="all",
            l1_skeleton="s",
            l2_excerpt="e",
            l2_full="f",
            l3_links=[],
            env_scope="all",
            secret=node.resolve_resonance_secret(),
        )
        with pytest.raises(CapsuleError, match="Cross-node mismatch"):
            node.tool_unfold_context_capsule({"capsule_token": foreign_tok})

        ck = derive_chain_key(node.resolve_resonance_secret(), "root", "L0", "ph1", "all")
        bad_ph_tok = seal_single_capsule(
            {"lvl": "L0", "next": "L1", "iss": "node-u", "lyr": "root", "env": "all", "ph": "ph1"},
            {"ph": "different"},
            ck,
        )
        with pytest.raises(CapsuleError, match="parent hash mismatch"):
            node.tool_unfold_context_capsule({"capsule_token": bad_ph_tok})

        parts = bad_ph_tok.split(".")
        import hashlib
        import hmac

        corrupt_prefix = f"{parts[0]}.{parts[1]}.YWJj"
        corrupt_sig = hmac.new(ck, corrupt_prefix.encode("ascii"), hashlib.sha256).hexdigest()[
            :CAPSULE_HMAC_HEX_LEN
        ]
        with pytest.raises(CapsuleError, match="Failed to decompress"):
            node.tool_unfold_context_capsule({"capsule_token": f"{corrupt_prefix}.{corrupt_sig}"})

        (repo / "docs/spec.md").write_text("# Root\n## Core Law\nMutated body!\n", encoding="utf-8")
        # Assert
        with pytest.raises(CapsuleError, match="section drifted"):
            node.tool_unfold_context_capsule(
                {
                    "capsule_token": tok,
                    "target_level": "L2",
                    "environment": "pro",
                    "resonance_key": "rk",
                }
            )
