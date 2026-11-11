"""Unit tests for zcg.core.constants.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from zcg.core import constants


class TestConstants:
    """Verify nominal constants, stack purity, and Google/Antigravity nomenclature."""

    def test_starter_templates_match_canonical_four_stack_matrix_expected(self) -> None:
        """Verify starter template catalog equals the canonical 4 + 4 + 2 + 6 = 16 matrix."""
        # Arrange
        expected_matrix = (
            "universal-base",
            "academic-base",
            "science-base",
            "business-base",
            "academic-curriculum",
            "scientific-methodology",
            "software-engineering",
            "corporate-operations",
            "nist-csf-security",
            "google-cloud-iac",
            "workstation-control-tower",
            "corporate-root-hub",
            "node-work-cockpit",
            "tutor-study-cockpit",
            "secops-mcp-guardian",
            "knowledge-stewardship-portal",
        )

        # Act
        actual = constants.CANONICAL_STARTER_TEMPLATES

        # Assert
        assert actual == expected_matrix
        assert len(actual) == 16
        assert set(constants.BUILTIN_COCKPIT_PLUGINS).issubset(actual)
        assert constants.ROLE_DEFAULT_COCKPIT_PLUGIN["knowledge"] == "knowledge-stewardship-portal"

    def test_node_manifest_and_makefile_contracts_use_zcg_nomenclature_expected(self) -> None:
        """Verify node manifest path, schema revisions, and Makefile recipes use zcg."""
        # Arrange
        recipes = tuple(constants.LAYER_MAKEFILE_RECIPES.values())

        # Act
        manifest_path = constants.NODE_MANIFEST_REL_PATH

        # Assert
        assert manifest_path == "system/zcg-node.json"
        assert constants.NODE_MANIFEST_CONTRACT_REV == "zcg-node-v1"
        assert constants.TEMPLATE_MANIFEST_CONTRACT_REV == "zcg-template-v1"
        assert all("$(ZCG_BIN)" in r for r in recipes)
        assert "backup-system" in constants.LAYER_ROLE_MAKEFILE_TARGETS["workstation"]
        assert "backup-system" not in constants.LAYER_ROLE_MAKEFILE_TARGETS["corporate"]
        assert "install-antigravity" in constants.LAYER_ROLE_MAKEFILE_TARGETS["workstation"]
        assert "link" in constants.LAYER_MAKEFILE_RECIPES
        assert "unlink" in constants.LAYER_MAKEFILE_RECIPES
        assert "hr-process" in constants.VALID_NODE_LINK_RELATIONS
        assert "venture" in constants.DEFAULT_CONTEXT_BRANCH_PREFIXES
        assert "project" in constants.VALID_LAYER_ROLES
        assert "pub-" in constants.VALID_KNOWLEDGE_PREFIXES
        assert constants.KNOWLEDGE_DOMAIN_TAXONOMY["pub-"]["default_entity_kind"] == "individual"
        assert "scaffold-plugin-module" in constants.MAINTAINER_ALLOWED_OPS
