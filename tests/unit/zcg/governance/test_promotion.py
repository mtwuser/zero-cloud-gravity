"""Unit tests for zcg.governance.promotion.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import AGENTS_MD_MAX_BYTES, NODE_MANIFEST_REL_PATH
from zcg.governance import promotion


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    path = node_dir / NODE_MANIFEST_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestPromotion:
    """Verify read-only 4-channel consultation and upward asset promotion PR workflows."""

    def test_consult_layer_ephemeral_across_targets_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify validation guards, self/parent/template resolution, and rcap1 receipts."""
        # Arrange
        repo = tmp_path / "zcg-root"
        _write_manifest(repo, {"layer_id": "zcg-root", "layer_role": "workstation"})
        (repo / "templates/context-stack/sci-pack/rules").mkdir(parents=True)
        (repo / "templates/context-stack/sci-pack/rules/r.md").write_text(
            "# Axiom Alpha\nEnforce E3 precision.\n", "utf-8"
        )

        parent = tmp_path / "dept-iso"
        _write_manifest(parent, {"layer_id": "dept-iso", "layer_role": "department"})
        (parent / "corporate").mkdir()
        (parent / "corporate/policy.md").write_text("# SLA Policy\nStrict uptime.\n", "utf-8")

        ws = tmp_path / "squad-iso"
        _write_manifest(ws, {"layer_id": "squad-iso", "layer_role": "squad"})
        (ws / "docs").mkdir()
        (ws / "docs/spec.md").write_text("Intro text\n# Telemetry Spec\n X \n", "utf-8")

        # Act — guards
        with pytest.raises(ValueError, match="Invalid target_layer"):
            promotion.consult_layer_ephemeral(repo, ws, target_layer="BAD_ID", query="x")
        with pytest.raises(ValueError, match="query must be a non-empty"):
            promotion.consult_layer_ephemeral(repo, ws, target_layer="self", query=" ")
        with pytest.raises(ValueError, match="Invalid model_tier"):
            promotion.consult_layer_ephemeral(
                repo, ws, target_layer="self", query="x", model_tier="ultra"
            )
        with pytest.raises(ValueError, match="Target layer or template not found"):
            promotion.consult_layer_ephemeral(repo, ws, target_layer="missing-node", query="x")

        # Self, parent, and template-only consultations
        res_self = promotion.consult_layer_ephemeral(
            repo, ws, target_layer="self", query="x", model_tier="", target_path=""
        )
        assert res_self["four_channel_digest"]["channel_4_actionable_delta"]["match_count"] >= 1

        res_parent = promotion.consult_layer_ephemeral(
            repo, ws, target_layer="parent", query="uptime", parent_dir=parent
        )
        assert res_parent["capsule_matches"][0]["section"] == "SLA Policy"

        res_tpl = promotion.consult_layer_ephemeral(
            repo, ws, target_layer="sci-pack", query="axiom"
        )
        linked_peer = tmp_path / "isolated-folder/alex-tutor"
        _write_manifest(linked_peer, {"layer_id": "alex-tutor", "layer_role": "department"})
        (linked_peer / "docs").mkdir()
        (linked_peer / "docs/mastery.md").write_text(
            "# Mastery Gate\nVerified E2 skill.\n", "utf-8"
        )
        _write_manifest(
            ws,
            {
                "layer_id": "squad-iso",
                "layer_role": "squad",
                "linked_nodes": [
                    {
                        "node_id": "alex-tutor",
                        "relation": "lateral-peer",
                        "target_ref": str(linked_peer),
                    }
                ],
            },
        )
        res_linked = promotion.consult_layer_ephemeral(
            repo, ws, target_layer="alex-tutor", query="mastery"
        )
        # Assert
        assert res_tpl["capsule_matches"][0]["epistemic_grade"] == "E3"
        assert res_linked["capsule_matches"][0]["section"] == "Mastery Gate"

    def test_promote_project_asset_oss_and_inter_root_guards_expected(self, tmp_path: Path) -> None:
        """Verify source/target validation, OSS surface blocks, and Peer Root 0 PR staging."""
        # Arrange
        oss_root = tmp_path / "zcg-oss"
        _write_manifest(
            oss_root,
            {
                "layer_id": "zero-cloud-gravity",
                "layer_role": "workstation",
                "entity_kind": "open-source",
            },
        )
        corp_a = tmp_path / "corp-a"
        _write_manifest(corp_a, {"layer_id": "corp-a", "layer_role": "corporate", "precedence": 10})
        corp_b = tmp_path / "corp-b"
        _write_manifest(
            corp_b,
            {
                "layer_id": "corp-b",
                "layer_role": "corporate",
                "precedence": 10,
                "layer_authority": {"authorized_emails": ["b-owner@corp-b.example"]},
            },
        )
        (corp_a / "WORKTASK.md").write_text("- [ ] Private task\n", "utf-8")
        (corp_a / "corporate").mkdir()
        (corp_a / "corporate/charter.md").write_text("# Charter\n", "utf-8")
        (corp_a / ".agents/rules").mkdir(parents=True)
        (corp_a / ".agents/rules/clean.md").write_text("# Clean Universal Rule\n", "utf-8")

        # Act — missing source / missing target layer
        with pytest.raises(ValueError, match="Invalid or missing project source file"):
            promotion.promote_project_asset_to_layer(corp_b, corp_a, source_rel_path="nope.md")
        with pytest.raises(ValueError, match="Target layer directory not found"):
            promotion.promote_project_asset_to_layer(
                corp_b, corp_a, source_rel_path="WORKTASK.md", target_layer="ghost-layer"
            )

        # OSS private surface block & OSS anonymized PR promotion
        with pytest.raises(ValueError, match="OSS_PRIVATE_SURFACE_BLOCKED"):
            promotion.promote_project_asset_to_layer(
                oss_root, corp_a, source_rel_path="WORKTASK.md", upstream_dir=oss_root
            )
        with patch("zcg.governance.promotion.resolve_git_user_email", return_value=""):
            oss_res = promotion.promote_project_asset_to_layer(
                oss_root,
                corp_a,
                source_rel_path=".agents/rules/clean.md",
                target_template="science-base",
                upstream_dir=oss_root,
                dry_run=True,
            )
        assert oss_res["collaboration_mode"] == "oss-sanitized-pr"
        assert oss_res["promotion_pr_plan"]["oss_anonymized"] is True

        # Inter-Root Peer blocks private corporate/ and stages clean rule non-destructively
        with pytest.raises(ValueError, match="INTER_ROOT_PRIVATE_SURFACE_BLOCKED"):
            promotion.promote_project_asset_to_layer(
                corp_b, corp_a, source_rel_path="corporate/charter.md", upstream_dir=corp_b
            )
        peer_res = promotion.promote_project_asset_to_layer(
            corp_b,
            corp_a,
            source_rel_path=".agents/rules/clean.md",
            target_template="sec-pack",
            upstream_dir=corp_b,
            actor_email="a-owner@corp-a.example",
        )
        assert peer_res["collaboration_mode"] == "inter-root-peer-pr"
        # Assert
        assert peer_res["staged_proposal"] is not None

    def test_promote_assets_skills_agents_trackers_and_staging_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify template routing, SKILL.md & AGENTS.md gates, tracker append, and staging."""
        # Arrange
        repo = tmp_path / "dept-iso"
        _write_manifest(
            repo,
            {
                "layer_id": "dept-iso",
                "layer_role": "department",
                "layer_authority": {"authorized_emails": ["owner@corp-iso.example"]},
            },
        )
        (repo / "templates/context-stack/dept-iso/rules").mkdir(parents=True)
        (repo / "layers/sub-iso").mkdir(parents=True)
        _write_manifest(repo / "layers/sub-iso", {"layer_id": "sub-iso", "layer_role": "squad"})

        proj = tmp_path / "squad-iso"
        _write_manifest(proj, {"layer_id": "squad-iso", "layer_role": "squad"})
        (proj / ".agents/rules").mkdir(parents=True)
        (proj / ".agents/assets/dept-iso").mkdir(parents=True)
        (proj / ".agents/skills/good-skill").mkdir(parents=True)
        (proj / ".agents/skills/bad-fm").mkdir(parents=True)
        (proj / ".agents/skills/bad-name").mkdir(parents=True)

        (proj / ".agents/rules/auto.md").write_text("# Auto rule\n", "utf-8")
        (proj / ".agents/assets/dept-iso/card.md").write_text("Asset\n", "utf-8")
        (proj / ".agents/skills/bad-fm/SKILL.md").write_text("# No FM\n", "utf-8")
        (proj / ".agents/skills/bad-name/SKILL.md").write_text(
            '---\nname: BAD_NAME\ndescription: ""\n---\n# Bad\n', "utf-8"
        )
        (proj / ".agents/skills/good-skill/SKILL.md").write_text(
            '---\nname: good-skill\ndescription: "Valid skill"\n---\n# Good\n', "utf-8"
        )
        (proj / "AGENTS.md").write_text("# Root Agents\n", "utf-8")
        (proj / "big.md").write_text("x" * (AGENTS_MD_MAX_BYTES + 10), "utf-8")
        (proj / "WORKTASK.md").write_text("- [ ] Escalate item\n", "utf-8")

        # Act — invalid template & SKILL.md validation errors
        with pytest.raises(ValueError, match="Invalid target_template"):
            promotion.promote_project_asset_to_layer(
                repo,
                proj,
                source_rel_path=".agents/rules/auto.md",
                target_template="BAD_TPL",
                actor_email="owner@corp-iso.example",
            )
        with pytest.raises(ValueError, match="YAML frontmatter"):
            promotion.promote_project_asset_to_layer(
                repo,
                proj,
                source_rel_path=".agents/skills/bad-fm/SKILL.md",
                actor_email="owner@corp-iso.example",
            )
        with pytest.raises(ValueError, match="kebab-case name and description"):
            promotion.promote_project_asset_to_layer(
                repo,
                proj,
                source_rel_path=".agents/skills/bad-name/SKILL.md",
                actor_email="owner@corp-iso.example",
            )

        # Auto-routed rule, asset, skill (layer config & template), AGENTS.md, and tracker
        r_res = promotion.promote_project_asset_to_layer(
            repo,
            proj,
            source_rel_path=".agents/rules/auto.md",
            actor_email="owner@corp-iso.example",
        )
        assert r_res["target_template"] == "dept-iso"

        # Unauthorized actor stages proposal cleanly
        stg_res = promotion.promote_project_asset_to_layer(
            repo,
            proj,
            source_rel_path=".agents/assets/dept-iso/card.md",
            actor_email="guest@corp-iso.example",
        )
        assert stg_res["staged_proposal"] is not None

        # Force overwrite asset & promote skills
        promotion.promote_project_asset_to_layer(
            repo,
            proj,
            source_rel_path=".agents/assets/dept-iso/card.md",
            force_overwrite=True,
            actor_email="owner@corp-iso.example",
        )
        promotion.promote_project_asset_to_layer(
            repo,
            proj,
            source_rel_path=".agents/skills/good-skill/SKILL.md",
            actor_email="owner@corp-iso.example",
        )
        promotion.promote_project_asset_to_layer(
            repo,
            proj,
            source_rel_path=".agents/skills/good-skill/SKILL.md",
            target_template="dept-iso",
            actor_email="owner@corp-iso.example",
        )

        # AGENTS.md write, overwrite protection, and byte-cap guard
        with pytest.raises(ValueError, match="exceeds"):
            promotion.promote_project_asset_to_layer(
                repo, proj, source_rel_path="big.md", actor_email="owner@corp-iso.example"
            )
        promotion.promote_project_asset_to_layer(
            repo, proj, source_rel_path="AGENTS.md", actor_email="owner@corp-iso.example"
        )
        (proj / "other.md").write_text("# Other\n", "utf-8")
        with pytest.raises(ValueError, match=r"Refusing to overwrite AGENTS\.md"):
            promotion.promote_project_asset_to_layer(
                repo, proj, source_rel_path="other.md", actor_email="owner@corp-iso.example"
            )

        # Tracker promotion into mounted sub-layer (creates subtree_push_command)
        trk_res = promotion.promote_project_asset_to_layer(
            repo,
            proj,
            source_rel_path="WORKTASK.md",
            target_layer="sub-iso",
            actor_email="owner@corp-iso.example",
        )
        # Assert
        assert trk_res["subtree_push_command"] == "zcg subtree-push sub-iso feat/promote-WORKTASK"
