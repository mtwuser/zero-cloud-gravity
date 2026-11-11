"""Unit tests for zcg.governance.bootstrap.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import MAKEFILE_CUSTOM_TARGETS_MARKER, NODE_MANIFEST_REL_PATH
from zcg.governance import bootstrap, scaffolder


class TestBootstrap:
    """Verify subtree registration, one-shot node bootstrap, and template synchronization."""

    def test_register_mounted_subtree_validation_and_registry_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify subtree name/manifest guards, public knowledge metadata, and sorting."""
        # Arrange
        ws = tmp_path / "corp-iso"
        ws.mkdir()

        # Act
        with pytest.raises(ValueError, match="Invalid layer_name"):
            bootstrap.register_mounted_subtree(ws, "BAD_NAME", "https://example.com/x.git")
        with pytest.raises(ValueError, match="Missing root manifest"):
            bootstrap.register_mounted_subtree(ws, "gov-es", "")

        scaffolder.configure_node_manifest(ws, layer_id="corp-iso", layer_role="corporate")
        dry_reg = bootstrap.register_mounted_subtree(ws, "gov-es", "", dry_run=True)
        assert dry_reg["registered_layer"]["stewardship_stage"] == "public-community"

        bootstrap.register_mounted_subtree(ws, "gov-es", "")
        res = bootstrap.register_mounted_subtree(ws, "dept-ops", "https://example.com/ops.git")
        # Assert
        assert res["total_mounted_layers"] == 2

    def test_bootstrap_node_workspace_inheritance_and_profiles_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify enterprise parent inheritance, individual & squad bootstrap, and stub README."""
        # Arrange
        home = tmp_path / "home"
        repo = tmp_path / "zcg-engine"
        scaffolder.configure_node_manifest(
            repo,
            layer_id="zero-cloud-gravity",
            layer_role="workstation",
            entity_kind="open-source",
        )
        scaffolder.scaffold_template_pack(repo, template_name="base-pack", kind="context-stack")
        scaffolder.scaffold_template_pack(repo, template_name="academic-base", kind="context-stack")
        scaffolder.scaffold_template_pack(repo, template_name="science-base", kind="context-stack")
        scaffolder.scaffold_template_pack(
            repo, template_name="software-engineering", kind="context-stack"
        )
        ext_tpl = repo / "templates/software-engineering/template.json"
        ext_d = json.loads(ext_tpl.read_text("utf-8"))
        ext_d["extends"] = "base-pack"
        ext_tpl.write_text(json.dumps(ext_d), "utf-8")
        scaffolder.scaffold_template_pack(
            repo, template_name="node-work-cockpit", kind="plugin-stack"
        )

        # Act — validation guards
        with pytest.raises(ValueError, match="Invalid layer_id"):
            bootstrap.bootstrap_node_workspace(repo, tmp_path / "x", layer_id="BAD")
        with pytest.raises(ValueError, match="Invalid layer_role"):
            bootstrap.bootstrap_node_workspace(
                repo, tmp_path / "x", layer_id="ok-id", layer_role="bad"
            )

        # 1. Enterprise corporate parent with .git remote + stub README replacement
        corp = tmp_path / "corp-iso"
        corp.mkdir()
        (corp / "README.md").write_text("# Stub\n", "utf-8")
        bootstrap.bootstrap_node_workspace(
            repo,
            corp,
            layer_id="corp-iso",
            layer_role="corporate",
            templates=["gov-es"],
            home_dir=home,
        )
        (corp / ".git").mkdir()

        # 2. Child software squad inheriting from enterprise parent (dry_run & live)
        squad = tmp_path / "squad-iso"
        git_proc = subprocess.CompletedProcess(
            ["git"], 0, stdout="https://example.com/corp.git\n", stderr=""
        )
        with patch("zcg.governance.bootstrap.subprocess.run", return_value=git_proc):
            dry_sq = bootstrap.bootstrap_node_workspace(
                repo,
                squad,
                layer_id="squad-iso",
                layer_role="squad",
                parent_dir=corp,
                templates=["software-engineering", "node-work-cockpit"],
                home_dir=home,
                dry_run=True,
            )
            assert dry_sq["dry_run"] is True

            live_sq = bootstrap.bootstrap_node_workspace(
                repo,
                squad,
                layer_id="squad-iso",
                layer_role="squad",
                parent_dir=corp,
                upstream_repo="https://example.com/explicit.git",
                templates=["software-engineering", "node-work-cockpit"],
                scaffold_own_template=False,
                home_dir=home,
            )
        assert live_sq["manifest"]["governing_root_id"] == "corp-iso"

        # 3. Unmanifested parent engine & Individual tutor lab re-run when README is full length
        bootstrap.bootstrap_node_workspace(
            tmp_path / "empty-engine",
            tmp_path / "solo-iso",
            layer_id="solo-iso",
            templates=["node-work-cockpit"],
            dry_run=True,
        )
        ind = tmp_path / "study-iso"
        bootstrap.bootstrap_node_workspace(
            repo,
            ind,
            layer_id="study-iso",
            layer_role="department",
            entity_kind="individual",
            home_dir=home,
        )
        re_ind = bootstrap.bootstrap_node_workspace(
            repo,
            ind,
            layer_id="study-iso",
            layer_role="department",
            entity_kind="individual",
            scaffold_own_template=False,
            home_dir=home,
        )
        # Assert
        assert "README.md" not in re_ind["baseline_files_created"]

    def test_sync_node_workspace_backfill_pruning_and_makefile_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify schema/root backfill, starter pruning, rule reconciliation, and Makefile sync."""
        # Arrange
        home = tmp_path / "home"
        repo = tmp_path / "zcg-engine"
        scaffolder.configure_node_manifest(
            repo,
            layer_id="zero-cloud-gravity",
            layer_role="workstation",
            entity_kind="open-source",
        )
        scaffolder.scaffold_template_pack(repo, template_name="science-base", kind="context-stack")
        scaffolder.scaffold_template_pack(
            repo, template_name="node-work-cockpit", kind="plugin-stack"
        )

        ws = tmp_path / "squad-iso"
        with pytest.raises(ValueError, match="Invalid sync strategy"):
            bootstrap.sync_node_workspace(repo, ws, strategy="invalid")
        with pytest.raises(ValueError, match="Missing target node manifest"):
            bootstrap.sync_node_workspace(repo, ws)

        bootstrap.bootstrap_node_workspace(
            repo,
            ws,
            layer_id="squad-iso",
            layer_role="squad",
            templates=["science-base", "node-work-cockpit"],
            home_dir=home,
        )

        # Simulate stale schema_version, missing governing_root_id, removed science-base,
        # newer .agents/rules/squad-iso.md, and custom Makefile section
        m_path = ws / NODE_MANIFEST_REL_PATH
        m_data = json.loads(m_path.read_text("utf-8"))
        m_data["schema_version"] = "old-rev"
        m_data.pop("governing_root_id", None)
        m_data["default_stack_templates"] = ["squad-iso", "node-work-cockpit"]
        m_path.write_text(json.dumps(m_data), "utf-8")

        ag_rule = ws / ".agents/rules/squad-iso.md"
        tpl_rule = ws / "templates/squad-iso/rules/squad-iso.md"
        ag_rule.write_text("# Updated Local Node Rule\n", "utf-8")
        os.utime(tpl_rule, (1_000_000, 1_000_000))
        os.utime(ag_rule, (2_000_000_000, 2_000_000_000))

        mk_file = ws / "Makefile"
        mk_file.write_text(
            f"{mk_file.read_text('utf-8')}\n{MAKEFILE_CUSTOM_TARGETS_MARKER}\ncustom:\n\t@true\n",
            "utf-8",
        )
        # Force makefile upgrade by trimming first recipe line while keeping header
        mk_txt = mk_file.read_text("utf-8").replace("PARENT_FLAG :=", "PARENT_FLAG ?=")
        mk_file.write_text(mk_txt, "utf-8")

        # Act
        dry_sync = bootstrap.sync_node_workspace(repo, ws, dry_run=True)
        assert dry_sync["dry_run"] is True

        live_sync = bootstrap.sync_node_workspace(repo, ws, strategy="accept-upstream")

        # Assert
        assert live_sync["makefile_upgraded"] is True
        assert not (ws / "templates/context-stack/science-base").exists()
        assert "Updated Local Node Rule" in tpl_rule.read_text("utf-8")
        assert len(live_sync["plugin_services_redeployed"]) == 1
        assert MAKEFILE_CUSTOM_TARGETS_MARKER in mk_file.read_text("utf-8")

        # Keep-local sync when governing_root_id is already backfilled
        kl_sync = bootstrap.sync_node_workspace(
            repo, ws, templates=["science-base"], strategy="keep-local"
        )
        assert kl_sync["synced_templates"] == ["science-base"]
