"""Unit tests for zcg.governance.horizon.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH, REPO_DIR
from zcg.governance import horizon


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    path = node_dir / NODE_MANIFEST_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestHorizon:
    """Verify project digest diffing, template sync reconciliation, and 1-hop horizon radar."""

    def test_diff_project_against_layers_and_symlink_containment_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify in_sync, modified, novel, materialized rule, and symlink escape checks."""
        # Arrange
        repo = tmp_path / "corp-iso"
        _write_manifest(repo, {"layer_id": "corp-iso", "layer_role": "corporate"})
        (repo / "antigravity/.gemini/config/skills/s1").mkdir(parents=True)
        (repo / "antigravity/.gemini/config/skills/s1/SKILL.md").write_text("# S1\n", "utf-8")
        (repo / "antigravity/.gemini/config/AGENTS.md").write_text("# Root Agents\n", "utf-8")

        tpl = repo / "templates/context-stack/pack-a"
        (tpl / "rules").mkdir(parents=True)
        (tpl / "skills/sk-a").mkdir(parents=True)
        (tpl / "assets").mkdir(parents=True)
        (tpl / "rules/r1.md").write_text("# Rule 1\n", "utf-8")
        (tpl / "rules/r2.md").write_text("# Rule 2\n", "utf-8")
        (tpl / "skills/sk-a/SKILL.md").write_text("---\nname: sk-a\n---\n# Sk\n", "utf-8")
        (tpl / "assets/snip.md").write_text("asset-v1\n", "utf-8")

        sub = repo / "layers/dept-iso"
        _write_manifest(sub, {"layer_id": "dept-iso", "layer_role": "department"})

        proj = tmp_path / "proj-iso"
        (proj / ".agents/rules").mkdir(parents=True)
        (proj / ".agents/skills/s1").mkdir(parents=True)
        (proj / ".agents/assets/pack-a").mkdir(parents=True)
        (proj / ".agents/rules/r1.md").write_text("# Rule 1\n", "utf-8")
        (proj / ".agents/rules/r2.md").write_text("# Rule 2 edited\n", "utf-8")
        (proj / ".agents/rules/layer-10-root.md").write_text("# Root Agents\n", "utf-8")
        (proj / ".agents/rules/layer-99-ghost.md").write_text("# Missing sub\n", "utf-8")
        (proj / ".agents/skills/s1/SKILL.md").write_text("# S1\n", "utf-8")
        (proj / ".agents/assets/pack-a/snip.md").write_text("asset-v1\n", "utf-8")

        # Act
        diff_ext = horizon.diff_project_against_layers(repo, proj)
        (repo / ".agents/skills/s1").mkdir(parents=True)
        (repo / ".agents/skills/s1/SKILL.md").write_text("# S1\n", "utf-8")
        diff_self = horizon.diff_project_against_layers(repo, repo)

        # Assert
        assert len(diff_ext["in_sync"]) == 4
        assert len(diff_ext["modified_in_project"]) == 1
        assert diff_ext["novel_in_project"] == ["rules/layer-99-ghost.md"]
        assert len(diff_self["in_sync"]) == 1

        # Symlink escape check
        outside = tmp_path / "secret.md"
        outside.write_text("# Secret\n", "utf-8")
        (proj / ".agents/rules/escape.md").symlink_to(outside)
        with pytest.raises(ValueError, match="Outbound symlink escape denied"):
            horizon.diff_project_against_layers(repo, proj)

    def test_reconcile_template_pack_sync_strategies_expected(self, tmp_path: Path) -> None:
        """Verify keep-local, reconcile conflict staging, and merge heading preservation."""
        # Arrange
        src_tpl = tmp_path / "upstream/templates/context-stack/pack-a"
        (src_tpl / "rules").mkdir(parents=True)
        (src_tpl / "rules/policy.md").write_text("# Upstream\nBody v2\n", "utf-8")
        (src_tpl / "rules/same.md").write_text("# Shared\nIdentical\n", "utf-8")
        (src_tpl / "template.json").write_text('{"template_id": "pack-a"}\n', "utf-8")

        ws = tmp_path / "ws"
        dest_tpl = ws / "templates/context-stack/pack-a"
        (dest_tpl / "rules").mkdir(parents=True)
        (dest_tpl / "rules/policy.md").write_text(
            "# Upstream\nBody v1\n\n# Local Extension\nCustom\n", "utf-8"
        )
        (dest_tpl / "rules/same.md").write_text("# Shared\nIdentical\n", "utf-8")
        prop_dir = ws / ".agents/proposals/from-upstream"
        prop_dir.mkdir(parents=True)
        (prop_dir / "pack-a-policy.md").write_text("# Old prop\n", "utf-8")
        (ws / "WORKTASK.md").write_text(
            "# Tasks\n- [ ] Review `.agents/proposals/from-upstream/pack-a-policy.md`\n",
            "utf-8",
        )
        (ws / ".agents/SESSION.md").write_text(
            "# Session\n\n## Governance Alerts & Pending Decisions\n"
            "- `.agents/proposals/from-upstream/pack-a-policy.md`\n",
            "utf-8",
        )

        # Act — 1. keep-local dry_run & live
        copied_dry, _ = horizon.reconcile_template_pack_sync(
            ws, "pack-a", src_tpl, dest_tpl, strategy="keep-local", dry_run=True
        )
        assert copied_dry is False
        copied_kl, _ = horizon.reconcile_template_pack_sync(
            ws, "pack-a", src_tpl, dest_tpl, strategy="keep-local"
        )
        assert copied_kl is False
        assert not (prop_dir / "pack-a-policy.md").exists()

        # 2. reconcile when already recorded in reconciled_upstream_sha256 -> 0 conflicts
        _, no_conf = horizon.reconcile_template_pack_sync(
            ws, "pack-a", src_tpl, dest_tpl, strategy="reconcile", is_local_newer=True
        )
        assert no_conf == []

        # Update upstream rule -> stages conflict
        (src_tpl / "rules/policy.md").write_text("# Upstream\nBody v3\n", "utf-8")
        did_copy, conflicts = horizon.reconcile_template_pack_sync(
            ws, "pack-a", src_tpl, dest_tpl, strategy="reconcile", is_local_newer=True
        )
        assert did_copy is False
        assert len(conflicts) == 1

        # 3. merge dry_run & live preserves # Local Extension
        horizon.reconcile_template_pack_sync(
            ws, "pack-a", src_tpl, dest_tpl, strategy="merge", dry_run=True
        )
        merged_ok, _ = horizon.reconcile_template_pack_sync(
            ws, "pack-a", src_tpl, dest_tpl, strategy="merge"
        )
        assert merged_ok is True
        merged_txt = (dest_tpl / "rules/policy.md").read_text("utf-8")
        assert "Body v3" in merged_txt and "# Local Extension" in merged_txt

        # 4. accept-upstream when trackers have no stale proposal token
        acc_ok, _ = horizon.reconcile_template_pack_sync(
            ws, "pack-a", src_tpl, dest_tpl, strategy="accept-upstream"
        )
        # Assert
        assert acc_ok is True

    def test_compare_upstream_templates_and_inspect_horizon_expected(self, tmp_path: Path) -> None:
        """Verify section-level comparisons, safe apply, and 1-hop OSS/private horizon radar."""
        # Arrange
        up = tmp_path / "oss-up"
        _write_manifest(
            up,
            {
                "layer_id": "zero-cloud-gravity",
                "layer_role": "workstation",
                "entity_kind": "open-source",
            },
        )
        (up / "VERSION").write_text("1.0.0\n", "utf-8")
        up_tpl = up / "templates/context-stack/pack-a"
        (up_tpl / "rules").mkdir(parents=True)
        (up_tpl / "skills/sk-new").mkdir(parents=True)
        (up_tpl / "skills/sk-new/SKILL.md").write_text("# Skill\n", "utf-8")
        (up_tpl / "rules/up_only.md").write_text(
            "---\ntrigger: always_on\n---\nPreamble\n# S1\nA\n", "utf-8"
        )
        (up_tpl / "rules/same.md").write_text("# S1\nSame\n", "utf-8")
        (up_tpl / "rules/add.md").write_text("# S1\nSame\n\n# S2\nAdded\n", "utf-8")
        (up_tpl / "rules/div.md").write_text("# S1\nUpstream line\n", "utf-8")

        ws = tmp_path / "corp-ws"
        _write_manifest(
            ws,
            {
                "layer_id": "acmevault-corp",
                "layer_role": "corporate",
                "default_stack_templates": ["pack-a", "missing-pack"],
                "mounted_layers": [{"name": "dept-a", "repository": "https://example.com/a.git"}],
            },
        )
        ws_tpl = ws / "templates/context-stack/pack-a"
        (ws_tpl / "rules").mkdir(parents=True)
        (ws_tpl / "rules/loc_only.md").write_text("# Local\nacmevault private\n", "utf-8")
        (ws_tpl / "rules/same.md").write_text("# S1\nSame\n", "utf-8")
        (ws_tpl / "rules/add.md").write_text("# S1\nSame\n", "utf-8")
        (ws_tpl / "rules/div.md").write_text("# S1\nLocal line\n", "utf-8")
        os.utime(up_tpl / "rules/div.md", (2_000_000_000, 2_000_000_000))
        os.utime(ws_tpl / "rules/div.md", (1_900_000_000, 1_900_000_000))

        # Act — compare read-only, dry_run, filtered, and live apply_upstream_only
        cmp_ro = horizon.compare_upstream_templates(up, ws, apply_upstream_only=False)
        assert cmp_ro["safe_applied_files"] == []
        cmp_dry = horizon.compare_upstream_templates(
            up, ws, template_filter="pack-a", apply_upstream_only=True, dry_run=True
        )
        assert cmp_dry["summary"]["files_compared"] == 5
        assert len(cmp_dry["safe_applied_files"]) == 2
        assert not (ws_tpl / "rules/up_only.md").exists()

        horizon.compare_upstream_templates(up, ws, apply_upstream_only=True, dry_run=False)
        assert (ws_tpl / "rules/up_only.md").is_file()
        assert "# S2" in (ws_tpl / "rules/add.md").read_text("utf-8")

        # Horizon against OSS root vs private parent (with novel .agents file & child drift)
        (ws / ".agents/rules").mkdir(parents=True)
        (ws / ".agents/rules/novel.md").write_text("# Novel\n", "utf-8")
        with patch("zcg.governance.horizon.authority.resolve_git_user_email", return_value=""):
            h_oss = horizon.inspect_layer_horizon(up, ws)
        assert h_oss["is_oss_community_horizon"] is True
        assert h_oss["downward_sync_needed"] is True

        priv_up = tmp_path / "priv-parent"
        _write_manifest(priv_up, {"layer_id": "priv-parent", "layer_role": "corporate"})
        (priv_up / "templates/context-stack/pack-a/rules").mkdir(parents=True)
        (priv_up / "templates/context-stack/pack-a/rules/loc_only.md").write_text(
            "# Old\n", "utf-8"
        )
        os.utime(priv_up / "templates/context-stack/pack-a/rules/loc_only.md", (1_000, 1_000))
        with patch(
            "zcg.governance.horizon.inspect_mounted_children_drifts",
            return_value=[{"layer_id": "unregistered-child"}],
        ):
            h_priv = horizon.inspect_layer_horizon(
                REPO_DIR, ws, parent_dir=priv_up, actor_email="lead@corp.io"
            )
        assert h_priv["is_oss_community_horizon"] is False
        assert h_priv["child_sync_needed"] is True
        # Assert
        assert any("novel.md" in str(s) for s in h_priv["upward_promotion_suggestions"])
