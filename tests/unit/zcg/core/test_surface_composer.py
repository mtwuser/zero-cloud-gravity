"""Unit tests for zcg.core.surface_composer.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import json
from pathlib import Path

from zcg.core import constants, surface_composer


class TestSurfaceComposer:
    """Verify composable node Makefiles, non-invasive .agents/zcg.mk, and skills.json filtering."""

    def test_has_active_plugin_stack_and_compose_targets_expected(self, tmp_path: Path) -> None:
        """Verify plugin-stack detection and Purpose x Role x Stack target composition."""
        # Arrange
        t_root = tmp_path / "templates"
        (t_root / "plugin-stack/custom-ui").mkdir(parents=True)
        (t_root / "context-stack/svc-pack").mkdir(parents=True)
        (t_root / "context-stack/svc-pack/template.json").write_text(
            json.dumps({"runtime_service": {"port": 8799}}), encoding="utf-8"
        )
        (t_root / "context-stack/plain-json").mkdir(parents=True)
        (t_root / "context-stack/plain-json/template.json").write_text("{}", encoding="utf-8")
        (t_root / "human-stack/academic-base").mkdir(parents=True)

        # Act
        builtin_hit = surface_composer.has_active_plugin_stack(["node-work-cockpit"], (tmp_path,))
        dir_hit = surface_composer.has_active_plugin_stack(["custom-ui"], (tmp_path,))
        svc_hit = surface_composer.has_active_plugin_stack(["svc-pack"], (tmp_path,))
        no_hit = surface_composer.has_active_plugin_stack(
            ["plain-json", "academic-base"], (tmp_path,)
        )

        ws_targets = surface_composer.compose_node_makefile_targets("workstation")
        corp_no_plugin = surface_composer.compose_node_makefile_targets(
            "corporate", active_templates=["academic-base"], search_roots=(tmp_path,)
        )
        proj_standalone = surface_composer.compose_node_makefile_targets(
            "department", purpose="standalone-project"
        )
        airlocked = surface_composer.compose_node_makefile_targets(
            "unknown-role", has_plugin_stack=False, allow_external_links=False
        )

        # Assert
        assert builtin_hit is True and dir_hit is True and svc_hit is True and no_hit is False
        assert "workstation-backup" in ws_targets and "workstation-update-agy" in ws_targets
        assert "plugin" in ws_targets and "backup-system" not in ws_targets
        assert "complete" not in corp_no_plugin and "activate-plugin" not in corp_no_plugin
        assert "mcp-test" not in proj_standalone and "activate-plugin" not in proj_standalone
        assert "promote" in proj_standalone
        assert "link" not in airlocked and "unlink" not in airlocked and "plugin" not in airlocked

    def test_render_and_is_makefile_outdated_across_roles_expected(self, tmp_path: Path) -> None:
        """Verify Makefile rendering and outdated checks for missing, custom, retired, and clean."""
        # Arrange
        eng = tmp_path / "engine"
        eng.mkdir()
        par = tmp_path / "parent"
        par.mkdir()
        ws = tmp_path / "dept-node"
        ws.mkdir()
        (ws / "templates/human-stack/academic-base").mkdir(parents=True)

        # Act
        missing_outdated = surface_composer.is_makefile_outdated(ws, "department")
        (ws / "Makefile").write_text("build:\n\techo native\n", encoding="utf-8")
        native_dept_outdated = surface_composer.is_makefile_outdated(ws, "department")
        native_proj_outdated = surface_composer.is_makefile_outdated(ws, "project")
        corp_mk = surface_composer.render_layer_makefile("corp-iso", "corporate", eng, eng)
        dept_mk = surface_composer.render_layer_makefile("dept-iso", "department", par, eng)
        (ws / "Makefile").write_text(dept_mk, encoding="utf-8")
        role_in_proj = surface_composer.is_makefile_outdated(ws, "project")
        clean_dept = surface_composer.is_makefile_outdated(ws, "department")
        (ws / "system").mkdir(parents=True)
        (ws / constants.NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"default_stack_templates": ["academic-base"]}), encoding="utf-8"
        )
        unwanted_plug = surface_composer.is_makefile_outdated(ws, "department", search_roots=(ws,))
        no_plug_mk = surface_composer.render_layer_makefile(
            "dept-iso", "department", par, eng, has_plugin_stack=False
        )
        (ws / "Makefile").write_text(no_plug_mk, encoding="utf-8")
        clean_no_plug = surface_composer.is_makefile_outdated(
            ws, "department", active_templates=["academic-base"], search_roots=(ws,)
        )
        (ws / "Makefile").write_text(no_plug_mk + "\nbackup-system:\n\techo old\n", "utf-8")
        retired_hit = surface_composer.is_makefile_outdated(
            ws, "department", active_templates=["academic-base"], search_roots=(ws,)
        )

        # Assert
        assert missing_outdated is False and native_dept_outdated is False
        assert native_proj_outdated is False
        assert "CONTRIB_REPO ?=" in corp_mk and "PARENT_DIR ?= \n" in corp_mk
        assert f"PARENT_DIR ?= {par.resolve()}\n" in dept_mk
        assert role_in_proj is True and clean_dept is False
        assert unwanted_plug is True and clean_no_plug is False and retired_hit is True

    def test_sync_workspace_makefile_preserves_native_and_custom_tails_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify non-invasive .agents/zcg.mk on projects and custom tail preservation on nodes."""
        # Arrange
        eng = tmp_path / "engine"
        eng.mkdir()
        par = tmp_path / "parent"
        par.mkdir()
        proj_native = tmp_path / "proj-native"
        proj_native.mkdir()
        (proj_native / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
        proj_fresh = tmp_path / "proj-fresh"
        proj_fresh.mkdir()
        node_dir = tmp_path / "dept-custom"
        node_dir.mkdir()
        (node_dir / "Makefile").write_text(
            f"{constants.MAKEFILE_ROLE_HEADER_PREFIX}\n"
            f"{constants.MAKEFILE_CUSTOM_TARGETS_MARKER}\nmy-local:\n\techo ok\n",
            encoding="utf-8",
        )

        # Act
        dry_proj = surface_composer.sync_workspace_makefile(
            proj_fresh,
            layer_id="proj-fresh",
            layer_role="project",
            effective_parent=eng,
            repo_dir=eng,
            dry_run=True,
        )
        dry_existed = (proj_fresh / "Makefile").exists()
        live_proj = surface_composer.sync_workspace_makefile(
            proj_fresh,
            layer_id="proj-fresh",
            layer_role="project",
            effective_parent=par,
            repo_dir=eng,
        )
        idem_proj = surface_composer.sync_workspace_makefile(
            proj_fresh,
            layer_id="proj-fresh",
            layer_role="project",
            effective_parent=par,
            repo_dir=eng,
        )
        pres_proj = surface_composer.sync_workspace_makefile(
            proj_native,
            layer_id="proj-native",
            layer_role="project",
            effective_parent=par,
            repo_dir=eng,
        )
        dry_node = surface_composer.sync_workspace_makefile(
            node_dir,
            layer_id="dept-custom",
            layer_role="department",
            effective_parent=par,
            repo_dir=eng,
            dry_run=True,
        )
        live_node = surface_composer.sync_workspace_makefile(
            node_dir,
            layer_id="dept-custom",
            layer_role="department",
            effective_parent=par,
            repo_dir=eng,
        )
        native_node = tmp_path / "node-native"
        native_node.mkdir()
        (native_node / "Makefile").write_text("all:\n\techo keep\n", encoding="utf-8")
        pres_node = surface_composer.sync_workspace_makefile(
            native_node,
            layer_id="node-native",
            layer_role="department",
            effective_parent=par,
            repo_dir=eng,
        )

        # Assert
        assert dry_proj["makefile_upgraded"] is True and dry_existed is False
        assert live_proj["makefile_upgraded"] is True and live_proj["zcg_mk_written"] is True
        assert idem_proj["makefile_upgraded"] is False
        assert "-include .agents/zcg.mk" in (proj_fresh / "Makefile").read_text("utf-8")
        assert f"ZCG_PARENT_DIR ?= {par.resolve()}" in (
            proj_fresh / constants.PROJECT_ZCG_MK_REL_PATH
        ).read_text("utf-8")
        assert pres_proj["makefile_preserved"] is True and pres_proj["makefile_upgraded"] is False
        assert (proj_native / "Makefile").read_text("utf-8") == "test:\n\tpytest\n"
        assert (proj_native / constants.PROJECT_ZCG_MK_REL_PATH).is_file()
        assert dry_node["makefile_upgraded"] is True
        assert live_node["makefile_upgraded"] is True
        assert "my-local:" in (node_dir / "Makefile").read_text("utf-8")
        assert pres_node["makefile_preserved"] is True and pres_node["makefile_upgraded"] is False

    def test_skills_manifest_and_companion_materialization_expected(self, tmp_path: Path) -> None:
        """Verify filtered zcg-skills-v1 disabled_skills and companion file materialization."""
        # Arrange
        acad_dir = tmp_path / "templates/human-stack/academic-base"
        (acad_dir / "skills/study-drill").mkdir(parents=True)
        (acad_dir / "skills/study-drill/SKILL.md").write_text("# Drill\n", encoding="utf-8")
        local_dir = tmp_path / "templates/local-pack"
        local_dir.mkdir(parents=True)
        swe_dir = tmp_path / "templates/context-stack/software-engineering"
        (swe_dir / "skills/testing").mkdir(parents=True)
        (swe_dir / "skills/testing/SKILL.md").write_text("# Testing\n", encoding="utf-8")

        proj_dir = tmp_path / "consumer-proj"
        proj_dir.mkdir()
        oss_dir = tmp_path / "oss-engine"
        (oss_dir / "system").mkdir(parents=True)
        (oss_dir / constants.NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "oss-engine", "layer_role": "workstation"}), encoding="utf-8"
        )

        # Act
        dry_doc = surface_composer.write_skills_manifest(
            proj_dir,
            active_templates=[("academic-base", acad_dir), ("local-pack", local_dir)],
            known_templates=[("software-engineering", swe_dir)],
            dry_run=True,
        )
        dry_comp = surface_composer.materialize_agent_companion_files(
            proj_dir,
            repo_dir=oss_dir,
            engine_dir=oss_dir,
            root_manifest={"entity_kind": "individual"},
            active_templates=[("academic-base", acad_dir)],
            known_templates=[("software-engineering", swe_dir)],
            copied_files=[".agents/skills/extra-skill/SKILL.md", ".agents/rules/r.md"],
            dry_run=True,
        )
        dry_skills_existed = (proj_dir / constants.SKILLS_MANIFEST_REL_PATH).exists()
        live_comp = surface_composer.materialize_agent_companion_files(
            proj_dir,
            repo_dir=oss_dir,
            engine_dir=oss_dir,
            root_manifest={"entity_kind": "individual"},
            active_templates=[("academic-base", acad_dir)],
            known_templates=[("software-engineering", swe_dir)],
            copied_files=[".agents/skills/extra-skill/SKILL.md"],
            dry_run=False,
        )
        oss_comp = surface_composer.materialize_agent_companion_files(
            oss_dir,
            repo_dir=oss_dir,
            engine_dir=oss_dir,
            root_manifest={"entity_kind": "open-source"},
            active_templates=[("software-engineering", swe_dir)],
            known_templates=[("software-engineering", swe_dir)],
            copied_files=[],
            dry_run=False,
        )

        # Assert
        assert dry_doc["schema_version"] == constants.SKILLS_MANIFEST_CONTRACT_REV
        assert dry_doc["entries"][0]["path"] == ".agents/skills"
        assert "study-drill" in dry_doc["entries"][0]["include_only"]
        assert "study-drill" in dry_doc["enabled_skills"]
        assert "testing" in dry_doc["disabled_skills"]
        assert "audit" in dry_doc["disabled_skills"]
        assert dry_skills_existed is False
        assert constants.PROJECT_ZCG_MK_REL_PATH in dry_comp
        assert live_comp == [constants.PROJECT_ZCG_MK_REL_PATH, constants.SKILLS_MANIFEST_REL_PATH]
        proj_skills = json.loads((proj_dir / constants.SKILLS_MANIFEST_REL_PATH).read_text("utf-8"))
        assert "extra-skill" in proj_skills["enabled_skills"]
        assert oss_comp == [constants.SKILLS_MANIFEST_REL_PATH]
        oss_skills = json.loads((oss_dir / constants.SKILLS_MANIFEST_REL_PATH).read_text("utf-8"))
        assert oss_skills["disabled_skills"] == []
