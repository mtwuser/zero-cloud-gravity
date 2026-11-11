"""Unit tests for zcg.topology.subtrees.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from zcg.core.blueprints import render_layer_makefile
from zcg.core.constants import (
    MAKEFILE_ROLE_HEADER_PREFIX,
    NODE_MANIFEST_CONTRACT_REV,
    NODE_MANIFEST_REL_PATH,
    TEMPLATE_MANIFEST_CONTRACT_REV,
)
from zcg.core.manifests import sha256_file
from zcg.topology import subtrees


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    target = node_dir / NODE_MANIFEST_REL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


class TestSubtrees:
    """Verify template freshness checks, mounted child drift detection, and parent rollup."""

    def test_is_git_historical_blob_and_is_dest_template_newer_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify template freshness checks across mtimes, reconciled sha256, and git history."""
        # Arrange — non-git fallback first
        src_no_git = tmp_path / "plain_src" / "tpl"
        dst_no_git = tmp_path / "plain_dst" / "tpl"
        assert subtrees.is_dest_template_newer(src_no_git, dst_no_git) is False
        (src_no_git / "rules").mkdir(parents=True)
        (dst_no_git / "rules").mkdir(parents=True)
        s_rf = src_no_git / "rules" / "r.md"
        d_rf = dst_no_git / "rules" / "r.md"
        s_rf.write_text("v2", encoding="utf-8")
        d_rf.write_text("v1", encoding="utf-8")
        (dst_no_git / "rules" / "local_only.md").write_text("local", encoding="utf-8")
        os.utime(s_rf, (200, 200))
        os.utime(d_rf, (100, 100))
        assert subtrees.is_dest_template_newer(src_no_git, dst_no_git) is False

        # Reconciled sha256 branch
        rec_sha = sha256_file(d_rf)
        (dst_no_git / "template.json").write_text(
            json.dumps({"reconciled_upstream_sha256": {"r.md": rec_sha}}), encoding="utf-8"
        )
        assert subtrees.is_dest_template_newer(src_no_git, dst_no_git) is False
        (dst_no_git / "template.json").write_text(
            json.dumps({"reconciled_upstream_sha256": {"r.md": "0" * 64}}), encoding="utf-8"
        )
        assert subtrees.is_dest_template_newer(src_no_git, dst_no_git) is True

        # Git historical blob check inside real temporary git repo
        git_repo = tmp_path / "git_src"
        git_tpl = git_repo / "templates" / "tpl"
        (git_tpl / "rules").mkdir(parents=True)
        g_rf = git_tpl / "rules" / "r.md"
        g_rf.write_text("upstream", encoding="utf-8")
        subprocess.run(["git", "init", str(git_repo)], check=True, capture_output=True)
        local_edit = tmp_path / "local_dst" / "tpl"
        (local_edit / "rules").mkdir(parents=True)
        l_rf = local_edit / "rules" / "r.md"
        l_rf.write_text("untracked-local-edit", encoding="utf-8")
        os.utime(g_rf, (300, 300))
        os.utime(l_rf, (100, 100))

        # Act
        assert subtrees.is_git_historical_blob(git_tpl, l_rf) is False
        # Assert
        assert subtrees.is_dest_template_newer(git_tpl, local_edit) is True

    def test_inspect_and_sync_mounted_children_into_parent_expected(self, tmp_path: Path) -> None:
        """Verify mounted child drift detection, dry_run, sync, ticket rollup, and proposals."""
        # Arrange
        parent = tmp_path / "corp-root"
        (parent / "templates" / "context-stack" / "corporate-operations" / "rules").mkdir(
            parents=True
        )
        p_rule = (
            parent / "templates/context-stack/corporate-operations/rules/corporate-operations.md"
        )
        p_rule.write_text("---\ntrigger: always_on\n---\n# Updated Parent Rule\n", encoding="utf-8")
        _write_manifest(parent, {"layer_id": "corp-root", "layer_role": "corporate"})
        (parent / "WORKTASK.md").write_text(
            "- [ ] **T1 [OPS-101]** -> `dept-ops` (stage: `delegated`)\n"
            "- [ ] **T2 [OPS-102]** local task\n",
            encoding="utf-8",
        )

        child = parent / "layers" / "dept-ops"
        _write_manifest(
            child,
            {"schema_version": "old-rev", "layer_id": "dept-ops", "layer_role": "department"},
        )
        (child / "Makefile").write_text(f"{MAKEFILE_ROLE_HEADER_PREFIX}\nall:\n", encoding="utf-8")
        c_tpl = child / "templates" / "context-stack" / "corporate-operations"
        (c_tpl / "rules").mkdir(parents=True)
        (c_tpl / "template.json").write_text(
            json.dumps(
                {
                    "schema_version": "old-tpl",
                    "kind": "context-stack",
                    "target_role": "department",
                }
            ),
            encoding="utf-8",
        )
        (c_tpl / "rules" / "corporate-operations.md").write_text("# Old\n", encoding="utf-8")
        (child / "templates" / "sovereign-child" / "rules").mkdir(parents=True)
        (child / ".agents" / "rules").mkdir(parents=True)
        (child / ".agents/rules/corporate-operations.md").write_text("# Old\n", encoding="utf-8")
        (child / "WORKTASK.md").write_text("- [x] **T1 [OPS-101]** Done\n", encoding="utf-8")
        prop = child / ".agents" / "proposals" / "new-rule.md"
        prop.parent.mkdir(parents=True)
        prop.write_text("# Proposal\n", encoding="utf-8")

        mounted = [
            {"name": "dept-ops", "layer_role": "department"},
            {"name": "missing-child", "layer_role": "department"},
            {"name": "remote-know", "repository": "https://github.com/mtwuser/sci-maths.git"},
        ]

        # Act
        drifts_before = subtrees.inspect_mounted_children_drifts(parent, mounted)
        dry_synced = subtrees.sync_mounted_children_into_parent(parent, mounted, dry_run=True)
        synced = subtrees.sync_mounted_children_into_parent(parent, mounted, dry_run=False)
        synced_again = subtrees.sync_mounted_children_into_parent(parent, mounted, dry_run=False)
        drifts_after = subtrees.inspect_mounted_children_drifts(parent, mounted)

        # Also cover already-clean child Makefile branch during sync
        (child / "Makefile").write_text(
            render_layer_makefile("dept-ops", "department", parent, parent), encoding="utf-8"
        )
        (c_tpl / "rules" / "corporate-operations.md").write_text(
            "# DriftOnlyRule\n", encoding="utf-8"
        )
        (child / ".agents/rules/corporate-operations.md").unlink()
        subtrees.sync_mounted_children_into_parent(parent, mounted, dry_run=False)

        # Assert
        assert len(drifts_before) == 1
        assert NODE_MANIFEST_REL_PATH in drifts_before[0]["drift_files"]
        assert "Makefile" in drifts_before[0]["drift_files"]
        assert dry_synced == ["dept-ops"]
        assert synced == ["dept-ops"]
        assert synced_again == []
        assert drifts_after == []
        assert (
            json.loads((child / NODE_MANIFEST_REL_PATH).read_text(encoding="utf-8"))[
                "schema_version"
            ]
            == NODE_MANIFEST_CONTRACT_REV
        )
        assert (
            json.loads((c_tpl / "template.json").read_text(encoding="utf-8"))["schema_version"]
            == TEMPLATE_MANIFEST_CONTRACT_REV
        )
        p_wt = (parent / "WORKTASK.md").read_text(encoding="utf-8")
        assert "- [x] **T1 [OPS-101]**" in p_wt and "stage: `completed (pro)`" in p_wt
        assert "from-dept-ops/new-rule.md" in p_wt
