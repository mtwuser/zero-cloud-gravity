"""Unit tests for zcg.core.blueprints.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import json
from pathlib import Path

from zcg.core import blueprints
from zcg.core.constants import NODE_MANIFEST_REL_PATH


class TestBlueprints:
    """Verify lineage resolution, cockpit selection, Makefile rendering, and setup_state."""

    def test_resolve_template_lineage_chain_and_default_cockpit_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify transitive extends/group base expansion and role-default cockpit selection."""
        # Arrange
        t_root = tmp_path / "templates"
        for grp, name, ext in (
            ("human-stack", "science-base", None),
            ("human-stack", "business-base", None),
            ("human-stack", "academic-base", None),
            ("context-stack", "software-engineering", "science-base"),
            ("context-stack", "corporate-operations", None),
            ("context-stack", "academic-curriculum", "academic-base"),
            ("plugin-stack", "secops-mcp-guardian", None),
        ):
            d = t_root / grp / name
            d.mkdir(parents=True)
            if ext is not None or grp == "plugin-stack":
                (d / "template.json").write_text(json.dumps({"extends": ext}), encoding="utf-8")

        # Act
        chain = blueprints.resolve_template_lineage_chain(
            [
                "secops-mcp-guardian",
                "corporate-operations",
                "missing-pack",
                ("explicit", t_root / "human-stack" / "science-base"),
            ],
            search_roots=(tmp_path,),
        )
        names = [n for n, _ in chain]

        # Assert
        assert "science-base" in names
        assert "software-engineering" in names
        assert "business-base" in names
        assert (
            blueprints.resolve_default_cockpit_plugin("workstation", "individual", [], (tmp_path,))
            == "workstation-control-tower"
        )
        assert (
            blueprints.resolve_default_cockpit_plugin("corporate", "enterprise", [], (tmp_path,))
            == "corporate-root-hub"
        )
        assert (
            blueprints.resolve_default_cockpit_plugin(
                "knowledge", "public-government", ["business-base"], (tmp_path,)
            )
            == "knowledge-stewardship-portal"
        )
        assert (
            blueprints.resolve_default_cockpit_plugin(
                "department", "enterprise", ["academic-curriculum"], (tmp_path,)
            )
            == "tutor-study-cockpit"
        )
        assert (
            blueprints.resolve_default_cockpit_plugin(
                "department", "individual", ["business-base"], (tmp_path,)
            )
            == "node-work-cockpit"
        )
        assert (
            blueprints.resolve_default_cockpit_plugin("department", "individual", [], (tmp_path,))
            == "tutor-study-cockpit"
        )
        assert (
            blueprints.resolve_default_cockpit_plugin("squad", "enterprise", [], (tmp_path,))
            == "node-work-cockpit"
        )

    def test_render_onboarding_readme_and_lineage_across_roles_expected(self) -> None:
        """Verify onboarding README and LAYER_LINEAGE cover academic, knowledge, root, and squad."""
        # Arrange
        # Act
        rm_acad = blueprints.render_layer_onboarding_readme(
            "tutor-lab",
            "department",
            90,
            "tutor-lab",
            ["academic-base"],
            "user-profile",
            entity_kind="individual",
            interaction_language="es",
        )
        rm_wallet = blueprints.render_layer_onboarding_readme(
            "persona-wallet",
            "squad",
            88,
            "persona-wallet",
            ["science-base"],
            "persona-profile",
            entity_kind="individual",
        )
        rm_know = blueprints.render_layer_onboarding_readme(
            "sci-maths", "knowledge", 20, "sci-maths", ["science-base"]
        )
        rm_corp = blueprints.render_layer_onboarding_readme(
            "corp-root", "corporate", 10, "corp-root", ["business-base"]
        )
        rm_squad = blueprints.render_layer_onboarding_readme(
            "squad-alpha", "squad", 50, "squad-alpha", []
        )
        rm_ws = blueprints.render_layer_onboarding_readme(
            "persona-profile",
            "workstation",
            90,
            "persona-profile",
            ["universal-base"],
            entity_kind="individual",
        )
        lin_md = blueprints.render_lineage_markdown(
            "", ["| 10 | Root | r | corporate | 1 |"], interaction_language="es"
        )

        # Assert
        assert "`direct`" in rm_acad and "Spanish (es)" in rm_acad and "SYLLABUS.md" in rm_acad
        assert "Two-Level Personal" in rm_acad and "Two-Level Personal" in rm_wallet
        assert "Sovereign Personal Pillar Rules" in rm_wallet and "SYLLABUS.md" not in rm_wallet
        assert "Epistemic Knowledge & Spec Atlas" in rm_know
        assert "Knowledge Twin" in rm_corp
        assert "Roster, Surface Bindings & Child Topology" in rm_squad and "`none`" in rm_squad
        assert "Level 0 — Personal Root 0 Workstation Hub" in rm_ws
        assert "Workstation Host Coupling" in rm_ws and "Workstation Sync, Host Audit" in rm_ws
        assert "[Customize: [Fill:" not in rm_ws and "[Customize: [Fill:" not in rm_squad
        assert "antigravity/.gemini/config/AGENTS.md and " in rm_ws
        assert "antigravity/.gemini/config/AGENTS.md" not in rm_acad
        assert "with our mission and invariants" in rm_acad
        assert "Applied Template Pack**: `none`" in lin_md and "Spanish (es)" in lin_md

    def test_resolve_workspace_setup_state_covers_u0_u1_and_u2_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify setup_state transitions across uninitialized, pending, and configured."""
        # Arrange — U0 uninitialized
        u0_dir = tmp_path / "empty-node"
        u0_dir.mkdir()
        u0 = blueprints.resolve_workspace_setup_state(u0_dir, {})

        # Arrange — U1 pending_customization (knowledge node with README Kickoff Prompt)
        u1_dir = tmp_path / "gov-draft"
        (u1_dir / "system").mkdir(parents=True)
        (u1_dir / NODE_MANIFEST_REL_PATH).write_text("{}", encoding="utf-8")
        (u1_dir / "README.md").write_text(
            blueprints.render_layer_onboarding_readme(
                "gov-draft", "knowledge", 20, "gov-draft", []
            ),
            encoding="utf-8",
        )
        (u1_dir / "WORKTASK.md").write_text(
            "- [ ] Complete `Layer Setup Blueprint` in `README.md` and run Kickoff Prompt\n",
            encoding="utf-8",
        )
        u1 = blueprints.resolve_workspace_setup_state(
            u1_dir, {"layer_id": "gov-draft", "layer_role": "knowledge"}
        )

        # Arrange — U1 unconfigured workstation clone without README prompt
        ws_clone = tmp_path / "alice-profile"
        (ws_clone / "system").mkdir(parents=True)
        (ws_clone / NODE_MANIFEST_REL_PATH).write_text("{}", encoding="utf-8")
        u1_ws = blueprints.resolve_workspace_setup_state(
            ws_clone,
            {
                "layer_id": "zero-cloud-gravity-workstation",
                "layer_role": "workstation",
                "precedence": 10,
            },
        )
        ws_engine = tmp_path / "zero-cloud-gravity"
        (ws_engine / "system").mkdir(parents=True)
        (ws_engine / NODE_MANIFEST_REL_PATH).write_text("{}", encoding="utf-8")
        u2_engine = blueprints.resolve_workspace_setup_state(
            ws_engine,
            {
                "layer_id": "zero-cloud-gravity-workstation",
                "layer_role": "workstation",
                "precedence": 10,
            },
        )

        # Arrange — U2 configured Level-4 project consumer workspace
        proj_dir = tmp_path / "service-api"
        (proj_dir / ".agents").mkdir(parents=True)
        (proj_dir / ".agents/LAYER_LINEAGE.md").write_text(
            "## Initial Chat Kickoff Prompt (4-Phase Customizable Progression)\nNo fence\n",
            encoding="utf-8",
        )
        u2 = blueprints.resolve_workspace_setup_state(proj_dir, {})
        # Act

        # Assert
        assert u0["state"] == "uninitialized" and u0["is_configured"] is False
        assert u1["state"] == "pending_customization" and u1["entity_kind"] == "public-government"
        assert "Phase A" in u1["kickoff_prompt"]
        assert u1_ws["state"] == "pending_customization" and u1_ws["entity_kind"] == "individual"
        assert "zcg init-fork" in u1_ws["kickoff_prompt"]
        assert "--precedence 90" in u1_ws["kickoff_prompt"]
        assert u2_engine["state"] == "configured" and u2_engine["kickoff_prompt"] == ""
        assert u2["state"] == "configured" and u2["is_configured"] is True
        assert u2["layer_role"] == "project" and u2["entity_kind"] == "enterprise"
