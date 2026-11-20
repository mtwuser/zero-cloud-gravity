"""Unit tests for zcg.cockpit.views.spatial_bridge.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path

from zcg.cockpit.views.spatial_bridge import (
    CODEBASE_AST_PRESET_KEY,
    LIVE_TOPOLOGY_PRESET_KEY,
    build_codebase_ast_spatial_preset,
    build_live_node_spatial_presets,
    render_live_node_atlas_fragment,
)
from zcg.core.constants import DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY


class TestSpatialBridge:
    """Verify live workspace topology projection into Zone.Z4 2D/3D Spatial Atlas presets."""

    def test_build_live_node_spatial_presets_from_materialized_scopes_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify materialized node, network, and federation scopes project connected + halo."""
        # Arrange
        ws = tmp_path / "corp-alpha"
        (ws / "system").mkdir(parents=True)
        (ws / "surfaces/data").mkdir(parents=True)
        reg_keys = tuple(DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY)
        (ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "corp-alpha",
                    "layer_role": "corporate",
                    "entity_kind": "enterprise",
                    "precedence": 80,
                    "visibility": "private",
                }
            ),
            encoding="utf-8",
        )
        (ws / "surfaces/data/node_scope.json").write_text(
            json.dumps(
                {
                    "layer_id": "corp-alpha",
                    "representation_context": {
                        "active_templates": ["universal-base", "business-base"]
                    },
                }
            ),
            encoding="utf-8",
        )
        (ws / "surfaces/data/network_scope.json").write_text(
            json.dumps(
                {
                    "network_representation_links": {
                        "parent_home_node": {
                            "node_id": "holding-root",
                            "layer_role": "workstation",
                            "precedence": 95,
                        },
                        "downward_child_nodes": [
                            {"node_id": "dept-ops", "layer_role": "department"},
                            {"node_id": "pub-portal", "layer_role": "knowledge"},
                            "skip-invalid",
                            {},
                        ],
                        "lateral_peers": [
                            {"node_id": "dept-hr", "layer_role": "department"},
                            "skip-peer",
                            {"node_id": ""},
                        ],
                        "linked_nodes": [
                            {
                                "node_id": "pub-standards",
                                "layer_role": "knowledge",
                                "relation": "knowledge-feed",
                                "shared_packs": ["business-base"],
                            },
                            {
                                "node_id": "partner-b2b",
                                "layer_role": "department",
                                "relation": "linked-peer",
                                "shared_packs": "not-a-list",
                            },
                            {
                                "node_id": "co-sov-peer",
                                "layer_role": "workstation",
                                "relation": "co-sovereign-union",
                                "shared_packs": ["universal-base"],
                            },
                            {"node_id": "partner-b2b", "layer_role": "department"},
                            {"node_id": "corp-alpha", "layer_role": "corporate"},
                            "skip-link",
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        (ws / "surfaces/data/federation_scope.json").write_text(
            json.dumps(
                {
                    "visibility": "private",
                    "fleet_plugin_inventory": [
                        {"workspace_id": "corp-alpha"},
                        {"workspace_id": "dept-ops"},
                        {
                            "workspace_id": "sci-econ",
                            "plugin_id": "knowledge-stewardship-portal",
                        },
                        {
                            "workspace_id": "dept-fin",
                            "plugin_id": "sovereign-wallet-cockpit",
                        },
                        "skip-fleet",
                        {},
                    ],
                    "mounted_layers": [
                        {"layer_id": reg_keys[0]},
                        "org-custom-corpus",
                        "",
                        "corp-alpha",
                    ],
                }
            ),
            encoding="utf-8",
        )

        # Act
        presets = build_live_node_spatial_presets(ws)
        nodes, edges = presets[LIVE_TOPOLOGY_PRESET_KEY]
        by_id = {n.node_id: n for n in nodes}

        # Assert
        assert next(iter(presets)) == LIVE_TOPOLOGY_PRESET_KEY
        assert "constellation-4-pillar" in presets
        assert by_id["corp-alpha"].parent_id == "holding-root"
        assert by_id["corp-alpha"].surface_ring == "R2"
        assert by_id["corp-alpha"].posture == "managed"
        assert by_id["sci-econ"].surface_ring == "R0"
        assert by_id["dept-fin"].surface_ring == "R2"
        assert by_id["partner-b2b"].surface_ring == "R1"
        assert by_id["co-sov-peer"].surface_ring == "R2"
        assert by_id["co-sov-peer"].posture == "sovereign"
        assert by_id["co-sov-peer"].parent_id is None
        assert by_id[reg_keys[0]].is_connected is True
        disconnected = [n for n in nodes if not n.is_connected]
        assert len(disconnected) == 2
        assert any(e.relation_kind == "knowledge-feed" for e in edges)
        assert any(e.relation_kind == "linked-peer" for e in edges)

    def test_build_live_node_spatial_presets_fallback_manifest_and_bare_dir_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify live topology fallback when scopes are corrupt, unmaterialized, or absent."""
        # Arrange
        ws_man = tmp_path / "solo-workstation"
        (ws_man / "system").mkdir(parents=True)
        (ws_man / "surfaces/data").mkdir(parents=True)
        (ws_man / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "solo-workstation",
                    "layer_role": "workstation",
                    "entity_kind": "individual",
                    "active_templates": ["  "],
                    "mounted_layers": list(DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY),
                }
            ),
            encoding="utf-8",
        )
        (ws_man / "surfaces/data/node_scope.json").write_text("{corrupt", encoding="utf-8")
        (ws_man / "surfaces/data/network_scope.json").write_text("[1, 2]", encoding="utf-8")
        ws_bare = tmp_path / "bare-node"
        ws_bare.mkdir()

        # Act
        presets_man = build_live_node_spatial_presets(ws_man)
        presets_bare = build_live_node_spatial_presets(ws_bare)
        nodes_man, _ = presets_man[LIVE_TOPOLOGY_PRESET_KEY]
        nodes_bare, edges_bare = presets_bare[LIVE_TOPOLOGY_PRESET_KEY]

        # Assert
        by_man = {n.node_id: n for n in nodes_man}
        assert by_man["solo-workstation"].surface_ring == "R3"
        assert by_man["solo-workstation"].posture == "sovereign"
        assert by_man["solo-workstation"].capability_tags == (
            "universal-base",
            "software-engineering",
        )
        assert all(n.is_connected for n in nodes_man)
        assert any(n.node_id == "bare-node" for n in nodes_bare)
        assert edges_bare == ()

    def test_build_codebase_ast_spatial_preset_projects_packages_and_imports_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify local src/ Python packages and AST imports project into codebase-ast-topology."""
        # Arrange
        ws = tmp_path / "code-node"
        (ws / "src/pkg_core").mkdir(parents=True)
        (ws / "src/pkg_api").mkdir(parents=True)
        (ws / "src/pkg_core/mod.py").write_text("import pkg_core.mod\nX = 1\n", encoding="utf-8")
        (ws / "src/pkg_api/svc.py").write_text("import pkg_core.mod\n", encoding="utf-8")
        (ws / "src/pkg_core/back.py").write_text("import pkg_api.svc\n", encoding="utf-8")

        # Act
        presets = build_live_node_spatial_presets(ws)
        ast_nodes, ast_edges = build_codebase_ast_spatial_preset(ws)
        atlas_frag = render_live_node_atlas_fragment(ws)

        # Assert
        assert CODEBASE_AST_PRESET_KEY in presets
        by_id = {n.node_id: n for n in ast_nodes}
        assert "code-node" in by_id and "pkg_core" in by_id and "pkg_api" in by_id
        peer_edges = [e for e in ast_edges if e.relation_kind == "linked-peer"]
        assert len(peer_edges) == 1
        assert 'data-island="spatial-atlas"' in atlas_frag
        assert 'data-api-prefix="/api/modules/spatial-atlas"' in atlas_frag
        assert LIVE_TOPOLOGY_PRESET_KEY in atlas_frag
        assert "<h3>2D/3D Network Atlas</h3>" not in atlas_frag
