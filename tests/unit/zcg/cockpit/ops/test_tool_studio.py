"""Unit tests for zcg.cockpit.ops.tool_studio.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from typing import Any

from zcg.cockpit.ops.tool_studio import render_commit_skill_form, render_tools_and_skills_html


class TestToolStudio:
    """1:1 unit suite for 3-origin Skills Studio and Tool-Stack sandbox HTML presenters."""

    def test_render_commit_skill_form_and_modes_expected(self) -> None:
        """Verify commit form escaping and skills/tools/combined mode selection."""
        # Arrange
        studio_empty: dict[str, Any] = {
            "layer_id": "workstation-iso",
            "trust_score": 100,
            "skills": [],
            "selected_skill": None,
        }
        tools = [
            {
                "tool_id": "zcg-skill-auditor",
                "display_name": "Skill Auditor",
                "summary": "SARIF auditor",
                "cli_command": "zcg lint-skills .",
                "provisioned": True,
                "recommended": True,
            },
            {
                "tool_id": "wallet-analytics",
                "display_name": "Wallet Analytics",
                "summary": "OFX watch",
                "cli_command": "",
                "provisioned": False,
                "recommended": False,
            },
        ]

        # Act
        form_html = render_commit_skill_form("drill-check")
        skills_only = render_tools_and_skills_html(
            studio_empty, tools, mode="skills", banner_html="<div class='zcg-alert'>OK</div>"
        )
        tools_only = render_tools_and_skills_html(studio_empty, tools, mode="tools")
        tools_none = render_tools_and_skills_html(studio_empty, [], mode="tools")
        both_html = render_tools_and_skills_html(studio_empty, tools)

        # Assert
        assert "feat(skills): update drill-check" in form_html
        assert "0 node-owned skills yet" in skills_only
        assert "0 core or stack skills projected" in skills_only
        assert "Isolated Tool-Stack Runtimes" not in skills_only
        assert "OK" in skills_only
        assert "Recommended for This Node (1)" in tools_only
        assert "Optional &amp; Specialized (1)" in tools_only
        assert "Run Check / Inspect" in tools_only and "Disable" in tools_only
        assert "Enable" in tools_only and "zcg status ." in tools_only
        assert "Node Skills &amp; Inherited Capabilities" not in tools_only
        assert "Recommended for This Node" not in tools_none
        assert "Optional &amp; Specialized" not in tools_none
        assert "Node Skills &amp; Inherited Capabilities" in both_html
        assert "Isolated Tool-Stack Runtimes" in both_html

    def test_render_skill_origins_and_detail_states_expected(self) -> None:
        """Verify node, parent, and engine badges plus view, duplicate, edit, and new states."""
        # Arrange
        node_sk = {
            "slug": "solve-ode",
            "editable": True,
            "origin_tier": "node",
            "source": "layer:tutor-iso",
            "sha256": "abc123",
            "content": "---\nname: solve-ode\ndescription: ODE.\n---\n",
        }
        parent_sk = {
            "slug": "corp-sop",
            "editable": False,
            "origin_tier": "parent",
            "source": "parent:corp-iso",
            "sha256": "def456",
            "content": "---\nname: corp-sop\ndescription: SOP.\n---\n",
        }
        eng_sk = {
            "slug": "sopen",
            "editable": False,
            "source": "core:universal-baseline",
            "sha256": "789ghi",
            "content": "---\nname: sopen\ndescription: Open.\n---\n",
        }
        base_studio = {
            "layer_id": "tutor-iso",
            "trust_score": 98,
            "skills": [node_sk, parent_sk, eng_sk],
        }

        # Act
        view_html = render_tools_and_skills_html(
            {**base_studio, "selected_skill": parent_sk}, [], action="view", mode="skills"
        )
        dup_html = render_tools_and_skills_html(
            {**base_studio, "selected_skill": eng_sk}, [], action="duplicate", mode="skills"
        )
        edit_clean = render_tools_and_skills_html(
            {**base_studio, "selected_skill": node_sk}, [], action="edit"
        )
        edit_dirty_draft = render_tools_and_skills_html(
            {
                **base_studio,
                "selected_skill": {**node_sk, "is_dirty": True},
                "draft": {
                    "has_draft": True,
                    "content": "---\nname: solve-ode\ndescription: Draft ODE.\n---\n",
                    "updated_at": "2026-11-19T12:00:00+00:00",
                },
            },
            [],
            action="edit",
        )
        new_html = render_tools_and_skills_html(
            {**base_studio, "selected_skill": None}, [], action="new", mode="skills"
        )

        # Assert
        assert "Inherited from Parent Layer (1)" in view_html
        assert "🏛️ Parent Layer" in view_html
        assert "✏️ Node-Owned" in view_html and "Delete" in view_html
        assert "⚙️ Core / Stack" in view_html
        assert "Viewing Read-Only Skill" in view_html and "<textarea" not in view_html
        assert "Duplicate as Node Skill" in dup_html and "tutor-iso-sopen" in dup_html
        assert "Commit Saved Skill" not in dup_html
        assert "Editing Node Skill" in edit_clean and "Commit Saved Skill" not in edit_clean
        assert "data-island='draft-studio'" in edit_clean and "commit_now" in edit_clean
        assert "zcg-dirty-banner" in edit_dirty_draft and "Commit Saved Skill" in edit_dirty_draft
        assert "Unapplied draft restored" in edit_dirty_draft and "Draft ODE." in edit_dirty_draft
        assert "Discard Draft" in edit_dirty_draft
        assert "+ Create New Node Skill" in new_html and "custom-node-skill" in new_html

    def test_render_agent_guidance_present_omitted_and_escaped_expected(self) -> None:
        """Verify agent guidance card renders in skills/combined modes and hides on tools."""
        # Arrange
        guidance = {
            "profile_label": "Software & <Arch>",
            "recommended_base_model": "Gemini 4 Carbon (High)",
            "velocity_alternative": "Gemini 4 Neon (High)",
            "auto_orchestration_summary": "Auto Swarm with disjoint files.",
            "continuous_calibration_rule": "Recalibrate via /audit.",
        }
        base_studio: dict[str, Any] = {
            "layer_id": "engine-iso",
            "trust_score": 100,
            "skills": [],
            "selected_skill": None,
        }

        # Act
        with_skills = render_tools_and_skills_html(
            {**base_studio, "agent_guidance": guidance}, [], mode="skills"
        )
        with_both = render_tools_and_skills_html({**base_studio, "agent_guidance": guidance}, [])
        with_tools = render_tools_and_skills_html(
            {**base_studio, "agent_guidance": guidance}, [], mode="tools"
        )
        omitted = render_tools_and_skills_html(base_studio, [], mode="skills")
        empty_map = render_tools_and_skills_html(
            {**base_studio, "agent_guidance": {}}, [], mode="skills"
        )
        non_map = render_tools_and_skills_html(
            {**base_studio, "agent_guidance": "invalid"}, [], mode="skills"
        )

        # Assert
        assert "data-zcg-agent-guidance" in with_skills
        assert "Set-and-Forget Agent &amp; Automatic Swarm Policy" in with_skills
        assert "Software &amp; &lt;Arch&gt;" in with_skills
        assert "<code>Gemini 4 Carbon (High)</code>" in with_skills
        assert "Gemini 4 Neon (High)" in with_skills
        assert "Auto Swarm with disjoint files." in with_skills
        assert "Recalibrate via /audit." in with_skills
        assert with_skills.index("data-zcg-agent-guidance") < with_skills.index(
            "Node Skills &amp; Inherited Capabilities"
        )
        assert "data-zcg-agent-guidance" in with_both
        assert "data-zcg-agent-guidance" not in with_tools
        assert "data-zcg-agent-guidance" not in omitted
        assert "data-zcg-agent-guidance" not in empty_map
        assert "data-zcg-agent-guidance" not in non_map
