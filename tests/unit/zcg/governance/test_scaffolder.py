"""Unit tests for zcg.governance.scaffolder.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance import scaffolder


class TestScaffolder:
    """Verify node manifest configuration, template pack scaffolding, and project projection."""

    def test_configure_node_manifest_validation_and_pruning_expected(self, tmp_path: Path) -> None:
        """Verify validation errors, canonical environments, federated_mcps, and pruning."""
        # Arrange
        ws = tmp_path / "node-iso"
        ws.mkdir()

        # Act — validation errors
        with pytest.raises(ValueError, match="Invalid layer_id"):
            scaffolder.configure_node_manifest(ws, layer_id="BAD_ID")
        with pytest.raises(ValueError, match="Invalid layer_role"):
            scaffolder.configure_node_manifest(ws, layer_id="node-iso", layer_role="bad")
        with pytest.raises(ValueError, match="Invalid entity_kind"):
            scaffolder.configure_node_manifest(ws, layer_id="node-iso", entity_kind="bad")
        with pytest.raises(ValueError, match="Invalid interaction_language"):
            scaffolder.configure_node_manifest(ws, layer_id="node-iso", interaction_language="xx")
        with pytest.raises(ValueError, match="Invalid precedence"):
            scaffolder.configure_node_manifest(ws, layer_id="node-iso", precedence=101)

        # Pre-seed manifest with federated_mcps missing tst and starter binding
        m_path = ws / NODE_MANIFEST_REL_PATH
        m_path.parent.mkdir(parents=True)
        m_path.write_text(
            json.dumps(
                {
                    "default_stack_templates": ["science-base", "custom-pack"],
                    "federated_mcps": [{"id": "m1", "environments": ["dev", "pre"]}],
                    "surface_bindings": [
                        {
                            "binding_id": "sci",
                            "rule_files": ["templates/context-stack/science-base/rules/r.md"],
                        },
                        {"binding_id": "keep", "rule_files": ["templates/custom-pack/rules/r.md"]},
                    ],
                }
            ),
            encoding="utf-8",
        )
        dry_m = scaffolder.configure_node_manifest(
            ws,
            layer_id="node-iso",
            layer_role="department",
            entity_kind="enterprise",
            governing_root_id="corp-iso",
            interaction_language="es",
            upstream_url="https://example.com/up.git",
            upstream_id="corp-iso",
            upstream_branch="main",
            prune_default_templates=True,
            dry_run=True,
        )
        assert dry_m["default_stack_templates"] == ["custom-pack"]
        assert "tst" in dry_m["federated_mcps"][0]["environments"]
        assert len(dry_m["surface_bindings"]) == 1

        live_m = scaffolder.configure_node_manifest(ws, layer_id="node-iso")
        # Assert
        assert set(live_m["environments"]) == {"dev", "tst", "pre", "pro"}
        scaffolder.configure_node_manifest(ws, layer_id="node-iso")

    def test_scaffold_template_pack_across_kinds_and_guards_expected(self, tmp_path: Path) -> None:
        """Verify template pack validation, plugin runtime_service, and context assets."""
        # Arrange
        ws = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(ws, layer_id="corp-iso", layer_role="corporate")

        # Act — guards
        with pytest.raises(ValueError, match="Invalid template_name"):
            scaffolder.scaffold_template_pack(ws, template_name="BAD_NAME")
        with pytest.raises(ValueError, match="Invalid template kind"):
            scaffolder.scaffold_template_pack(ws, template_name="ok-pack", kind="bad-kind")
        with pytest.raises(ValueError, match="Invalid rule_filename"):
            scaffolder.scaffold_template_pack(
                ws, template_name="ok-pack", rule_filename="../bad.txt"
            )

        dry_res = scaffolder.scaffold_template_pack(
            ws, template_name="plug-pack", kind="plugin-stack", dry_run=True
        )
        assert dry_res["dry_run"] is True

        plug_res = scaffolder.scaffold_template_pack(
            ws,
            template_name="plug-pack",
            kind="plugin-stack",
            register_binding=True,
        )
        assert plug_res["binding_registered"] is True

        ctx_res = scaffolder.scaffold_template_pack(
            ws, template_name="ctx-pack", kind="context-stack"
        )
        assert any("canonical_snippet.md" in f for f in ctx_res["files_created"])

        with pytest.raises(ValueError, match="Template directory already exists"):
            scaffolder.scaffold_template_pack(ws, template_name="ctx-pack")

        bare = tmp_path / "bare-node"
        bare_res = scaffolder.scaffold_template_pack(bare, template_name="bare-pack")
        # Assert
        assert bare_res["template_id"] == "bare-pack"

    def test_apply_templates_to_project_materialization_and_pruning_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify multi-layer materialization, lineage, root self-sync, and stale pruning."""
        # Arrange
        repo = tmp_path / "corp-iso"
        scaffolder.configure_node_manifest(repo, layer_id="corp-iso", layer_role="corporate")
        scaffolder.scaffold_template_pack(repo, template_name="pack-tech", kind="framework-stack")
        scaffolder.scaffold_template_pack(repo, template_name="pack-unused", kind="context-stack")
        (repo / "templates/pack-tech/governance/SESSION.md").write_text("# Session\n", "utf-8")
        (repo / "antigravity/.gemini/config/skills/root-sk").mkdir(parents=True)
        (repo / "antigravity/.gemini/config/skills/root-sk/SKILL.md").write_text(
            "# Root Skill\n", "utf-8"
        )
        (repo / "antigravity/.gemini/config/AGENTS.md").write_text("# Corp Rule\n", "utf-8")

        sub = repo / "layers/dept-iso"
        scaffolder.configure_node_manifest(sub, layer_id="dept-iso", layer_role="department")
        scaffolder.scaffold_template_pack(sub, template_name="dept-pack", kind="context-stack")

        proj = tmp_path / "consumer-proj"
        (proj / ".agents/rules").mkdir(parents=True)
        (proj / ".agents/skills/pack-unused-guide").mkdir(parents=True)
        (proj / ".agents/assets/pack-unused").mkdir(parents=True)
        (proj / ".agents/runtime").mkdir(parents=True)
        (proj / ".agents/rules/layer-99-stale.md").write_text("# Stale\n", "utf-8")
        (proj / ".agents/rules/policy.md").write_text("# Unused rule\n", "utf-8")
        (proj / ".agents/skills/pack-unused-guide/SKILL.md").write_text("# Old\n", "utf-8")
        (proj / ".agents/runtime/pack-unused.json").write_text("{}\n", "utf-8")

        # Act — missing template raises ValueError; builtin cockpit skipped gracefully
        with pytest.raises(ValueError, match="not found in selected layers"):
            scaffolder.apply_templates_to_project(repo, proj, template_ref="nonexistent-pack")

        # Dry-run with layer filter & unmanifested sublayer
        (repo / "layers/dept-raw").mkdir(parents=True)
        dry_proj = scaffolder.apply_templates_to_project(
            repo,
            proj,
            template_ref="dept-iso:dept-pack,node-work-cockpit",
            layers_filter=["root", "dept-iso"],
            include_layer_defaults=True,
            dry_run=True,
        )
        assert dry_proj["dry_run"] is True

        # Bare repo without layers/ dir or manifest (live creates default SESSION.md)
        bare_repo = tmp_path / "bare-repo"
        scaffolder.scaffold_template_pack(bare_repo, template_name="solo-pack")
        scaffolder.apply_templates_to_project(
            bare_repo, tmp_path / "solo-proj", template_ref="solo-pack", dry_run=False
        )

        # Live apply to external project (prunes stale layer rule & pack-unused)
        m_path = repo / NODE_MANIFEST_REL_PATH
        m_data = json.loads(m_path.read_text("utf-8"))
        m_data["default_stack_templates"] = ["universal-base", "pack-tech", "ghost-default"]
        m_path.write_text(json.dumps(m_data), "utf-8")

        scaffolder.apply_templates_to_project(repo, proj, dry_run=True)
        live_proj = scaffolder.apply_templates_to_project(repo, proj)
        assert "pack-unused" in live_proj["pruned_plugins"]
        assert not (proj / ".agents/rules/layer-99-stale.md").exists()
        assert (proj / ".agents/LAYER_LINEAGE.md").is_file()

        m_data["default_stack_templates"] = ["universal-base", "pack-tech"]
        m_path.write_text(json.dumps(m_data), "utf-8")

        # Re-apply when governance files and SESSION.md already exist + self-apply on repo root
        scaffolder.apply_templates_to_project(
            repo, proj, template_ref="dept-iso:dept-pack", include_layer_defaults=True
        )
        root_self = scaffolder.apply_templates_to_project(repo, repo, template_ref="pack-tech")
        # Assert
        assert ".agents/skills/root-sk/SKILL.md" in root_self["files_materialized"]
        scaffolder.apply_templates_to_project(repo, repo, template_ref="pack-tech", dry_run=True)
