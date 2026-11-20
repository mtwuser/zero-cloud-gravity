"""Unit tests for zcg.core.constants.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from zcg.core import constants


class TestConstants:
    """Verify nominal constants, stack purity, and Google/Antigravity nomenclature."""

    def test_starter_templates_match_canonical_four_stack_matrix_expected(self) -> None:
        """Verify starter template catalog equals the canonical 4 + 6 + 2 + 7 = 19 matrix."""
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
            "spatial-simulation",
            "nist-csf-security",
            "self-hosted-container",
            "google-cloud-iac",
            "workstation-control-tower",
            "corporate-root-hub",
            "node-work-cockpit",
            "tutor-study-cockpit",
            "secops-mcp-guardian",
            "knowledge-stewardship-portal",
            "sovereign-wallet-cockpit",
        )

        # Act
        actual = constants.CANONICAL_STARTER_TEMPLATES

        # Assert
        assert actual == expected_matrix
        assert len(actual) == 19
        assert len(constants.BUILTIN_COCKPIT_PLUGINS) == 7
        assert "secops-mcp-guardian" in constants.BUILTIN_COCKPIT_PLUGINS
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
        assert constants.SKILLS_MANIFEST_CONTRACT_REV == "zcg-skills-v1"
        assert all("$(ZCG_BIN)" in r for r in recipes)
        assert "workstation-backup" in constants.LAYER_ROLE_MAKEFILE_TARGETS["workstation"]
        assert "workstation-backup" not in constants.LAYER_ROLE_MAKEFILE_TARGETS["corporate"]
        assert "workstation-update-agy" in constants.LAYER_ROLE_MAKEFILE_TARGETS["workstation"]
        assert "plugin" in constants.MAKEFILE_COMPOSABLE_BLOCKS["plugin_ops"]
        assert "link" in constants.LAYER_MAKEFILE_RECIPES
        assert "unlink" in constants.LAYER_MAKEFILE_RECIPES
        assert "hr-process" in constants.VALID_NODE_LINK_RELATIONS
        assert "co-sovereign-union" in constants.VALID_NODE_LINK_RELATIONS
        assert "venture" in constants.DEFAULT_CONTEXT_BRANCH_PREFIXES
        assert "project" in constants.VALID_LAYER_ROLES
        assert constants.PUBLIC_GOV_PREFIXES == ("gov-", "geo-")
        assert constants.VALID_KNOWLEDGE_PREFIXES == ("gov-", "sci-", "geo-", "org-")
        assert "pub-" not in constants.KNOWLEDGE_DOMAIN_TAXONOMY
        assert "economic" in constants.CANONICAL_SCIENCE_TRUNKS["social"]
        assert "sci-economic" in constants.DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY
        assert "lint-skills" in constants.CONSUMER_ALLOWED_OPS
        assert "check-handoff" in constants.CONSUMER_ALLOWED_OPS
        assert "scaffold-web-app" in constants.CONSUMER_ALLOWED_OPS
        assert "install-plugin" in constants.MAINTAINER_ALLOWED_OPS
        assert "scaffold-plugin-module" in constants.MAINTAINER_ALLOWED_OPS
        assert constants.TOOL_RUNTIME_REL_DIR == ".zcg/tools"
        assert constants.SIDECAR_MANIFEST_REL_PATH == ".agents/sidecar.json"
        assert constants.SIDECAR_MANIFEST_CONTRACT_REV == "zcg-sidecar-v1"
        assert "tool-stack" in constants.CANONICAL_STACK_GROUP_DIRS
        assert constants.TEMPLATE_STACK_GROUP_DIRS == constants.CANONICAL_STACK_GROUP_DIRS
        assert constants.VALID_TEMPLATE_KINDS == constants.CANONICAL_STACK_GROUP_DIRS
