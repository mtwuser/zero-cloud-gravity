"""Unit tests for zcg.core.epistemics.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import json
from pathlib import Path

from zcg.core import epistemics
from zcg.core.constants import NODE_MANIFEST_REL_PATH


class TestEpistemics:
    """Verify Human-Stack facets, language policy, and epistemic knowledge resolution."""

    def test_human_stack_and_interaction_language_precedence_expected(self, tmp_path: Path) -> None:
        """Verify Human-Stack facet parsing and 4-tier interaction_language precedence."""
        # Arrange
        ws = tmp_path / "ws"
        (ws / ".agents").mkdir(parents=True)
        parent = tmp_path / "parent"
        (parent / "system").mkdir(parents=True)
        home = tmp_path / "home"
        (home / ".gemini" / "config").mkdir(parents=True)

        # Act — default empty
        assert epistemics.resolve_effective_human_stack(ws) == {
            "facets": [],
            "scope": "default-none",
        }
        assert epistemics.resolve_effective_interaction_language(ws)["interaction_language"] == "en"

        # Manifest fallback & list input
        m_hs = epistemics.resolve_effective_human_stack(
            ws,
            {
                "human_stack": [
                    "domain-physics:M2",
                    "domain-:M1",
                    "domain-physics:M2",
                    "hat-dev",
                    "hat-*",
                    "bad",
                ]
            },
        )
        assert m_hs == {"facets": ["domain-physics:M2", "hat-dev"], "scope": "layer-manifest"}

        # SESSION.md overrides README.md
        (ws / "README.md").write_text(
            "- **Human-Stack Profile**: domain-maths:M1\n", encoding="utf-8"
        )
        assert epistemics.resolve_effective_human_stack(ws)["scope"] == "layer-blueprint"
        (ws / ".agents/SESSION.md").write_text(
            "Human-Stack: `domain-biology:M3` | soft-mentor\n", encoding="utf-8"
        )
        assert epistemics.resolve_effective_human_stack(ws)["facets"] == [
            "domain-biology:M3",
            "soft-mentor",
        ]

        # Language: home AGENTS.md -> parent -> workspace
        (home / ".gemini/config/AGENTS.md").write_text(
            "Dual-Plane (`Interaction Language: Spanish (es)`)\n", encoding="utf-8"
        )
        res_home = epistemics.resolve_effective_interaction_language(ws, home_dir=home)
        assert res_home["interaction_language"] == "es"
        assert res_home["language_scope"] == "workstation-home"

        no_match_home = tmp_path / "home2"
        no_match_home.mkdir()
        assert (
            epistemics.resolve_effective_interaction_language(ws, home_dir=no_match_home)[
                "language_scope"
            ]
            == "default-en"
        )

        (parent / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"interaction_language": "fr"}), encoding="utf-8"
        )
        res_parent = epistemics.resolve_effective_interaction_language(
            ws, parent_dir=parent, home_dir=home
        )
        assert res_parent["interaction_language"] == "fr"
        res_ws = epistemics.resolve_effective_interaction_language(
            ws, {"interaction_language": "it"}, parent_dir=parent, home_dir=home
        )
        # Assert
        assert res_ws["interaction_language"] == "it"

    def test_classify_knowledge_domain_and_resolve_mount_endpoints_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify trunk/branch/custom knowledge classification and 3-stage mount endpoints."""
        # Arrange
        local_sci = tmp_path / "layers" / "sci-formal"
        (local_sci / "system").mkdir(parents=True)
        (local_sci / NODE_MANIFEST_REL_PATH).write_text("{}", encoding="utf-8")

        # Act
        c_trunk = epistemics.classify_knowledge_domain("sci-formal", "knowledge")
        c_branch = epistemics.classify_knowledge_domain("sci-physics", "knowledge")
        c_custom_sci = epistemics.classify_knowledge_domain("sci-quantum-computing", "knowledge")
        c_gov = epistemics.classify_knowledge_domain("gov-es", "knowledge")
        c_pub = epistemics.classify_knowledge_domain("pub-alex", "knowledge")
        c_custom_know = epistemics.classify_knowledge_domain("atlas-core", "knowledge")
        c_std = epistemics.classify_knowledge_domain("dept-ops", "department")

        ep_local = epistemics.resolve_knowledge_mount_endpoints(
            {"name": "sci-formal", "private_mirror_url": "git@priv/sci.git"}, tmp_path
        )
        ep_priv = epistemics.resolve_knowledge_mount_endpoints(
            {"name": "org-secret", "private_mirror_url": "git@priv/org.git"}, tmp_path
        )
        ep_pub = epistemics.resolve_knowledge_mount_endpoints({"name": "sci-maths"}, tmp_path)
        ep_sov = epistemics.resolve_knowledge_mount_endpoints(
            {
                "name": "gov-iso",
                "stewardship_stage": "sovereign-authority",
                "canonical_authority_url": "https://gov.example/iso.git",
            },
            tmp_path,
        )
        ep_infer_pub = epistemics.resolve_knowledge_mount_endpoints(
            {"name": "sci-custom"}, tmp_path
        )

        # Assert
        assert c_trunk["granularity"] == "trunk-repository"
        assert c_branch["canonical_trunk"] == "nature"
        assert c_branch["granularity"] == "branch-repository"
        assert c_custom_sci["canonical_trunk"] == "custom-science"
        assert c_gov["knowledge_domain"] == "jurisdictional-normative"
        assert c_pub["knowledge_domain"] == "personal-sovereign-public"
        assert c_pub["default_entity_kind"] == "individual"
        assert c_pub["default_epistemic_grade"] == "E1"
        assert c_custom_know["knowledge_domain"] == "custom-knowledge"
        assert c_std["knowledge_domain"] is None and c_std["default_stack_templates"] == []
        assert ep_local["resolution_mode"] == "local-mcp-clone"
        assert ep_priv["stewardship_stage"] == "private-incubation"
        assert ep_priv["resolution_mode"] == "private-mirror-remote"
        assert ep_pub["stewardship_stage"] == "public-community"
        assert ep_sov["active_endpoint"] == "https://gov.example/iso.git"
        assert ep_infer_pub["stewardship_stage"] == "public-community"
