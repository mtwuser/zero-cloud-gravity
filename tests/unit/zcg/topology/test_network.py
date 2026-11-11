"""Unit tests for zcg.topology.network.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.topology import network


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    target = node_dir / NODE_MANIFEST_REL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


class TestNetwork:
    """Verify composite topology discovery, public-seed sibling isolation, and sync DAG."""

    def test_discover_network_topology_isolates_public_seeds_from_foreign_org_twins_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify foreign org-* siblings never leak into public-community knowledge registries."""
        # Arrange
        know_hub = tmp_path / "osa-knowledge"
        sci_maths = know_hub / "sci-maths"
        _write_manifest(
            sci_maths,
            {
                "layer_id": "sci-maths",
                "layer_role": "knowledge",
                "visibility": "public",
                "public_url": "https://github.com/mtwuser/sci-maths.git",
            },
        )
        foreign_org = know_hub / "org-enterprise-iso"
        _write_manifest(
            foreign_org,
            {
                "layer_id": "org-enterprise-iso",
                "layer_role": "knowledge",
                "visibility": "public",
                "governing_root_id": "corp-enterprise-root",
                "public_url": "https://github.com/example/org-enterprise-iso.git",
            },
        )
        corp_root = tmp_path / "corp-enterprise-root"
        _write_manifest(
            corp_root,
            {
                "layer_id": "corp-enterprise-root",
                "layer_role": "corporate",
                "precedence": 10,
                "mounted_layers": [
                    {"name": "sci-maths", "layer_role": "knowledge"},
                    {"name": "", "layer_role": "department"},
                ],
            },
        )
        dept_a = tmp_path / "corp-enterprise-root-org" / "dept-alpha"
        _write_manifest(
            dept_a,
            {
                "layer_id": "dept-alpha",
                "layer_role": "department",
                "precedence": 30,
                "governing_root_id": "corp-enterprise-root",
            },
        )
        dept_b = tmp_path / "corp-enterprise-root-org" / "dept-beta"
        _write_manifest(
            dept_b,
            {
                "layer_id": "dept-beta",
                "layer_role": "domain-policy",
                "precedence": 5,
                "governing_root_id": "corp-enterprise-root",
            },
        )
        squad_a = dept_a / "layers" / "squad-one"
        _write_manifest(
            squad_a,
            {
                "layer_id": "squad-one",
                "layer_role": "squad",
                "precedence": 50,
                "governing_root_id": "corp-enterprise-root",
            },
        )

        # Act
        sci_topo = network.discover_network_topology(sci_maths)
        corp_topo = network.discover_network_topology(corp_root)
        dept_topo = network.discover_network_topology(dept_a, parent_dir=corp_root)
        squad_topo = network.discover_network_topology(squad_a, parent_dir=dept_a)
        ws_dir = tmp_path / "user-pc"
        _write_manifest(
            ws_dir,
            {
                "layer_id": "user-pc",
                "layer_role": "workstation",
                "entity_kind": "individual",
                "linked_nodes": [
                    {
                        "node_id": "org-alpha",
                        "relation": "hr-process",
                        "layer_role": "knowledge",
                        "precedence": 20,
                        "shared_packs": ["corporate-operations"],
                    },
                    {"node_id": "user-pc", "relation": "lateral-peer"},
                    {"node_id": "peer-lab", "relation": "invalid-fallback"},
                ],
            },
        )
        ws_topo = network.discover_network_topology(ws_dir)
        oss_pub = tmp_path / "zero-cloud-gravity"
        _write_manifest(oss_pub, {"layer_id": "root", "layer_role": "workstation"})
        oss_topo = network.discover_network_topology(oss_pub)
        proj_dir = tmp_path / "leaf-app"
        proj_topo = network.discover_network_topology(proj_dir, {})

        # Assert — sci-maths does NOT contain org-enterprise-iso, while corp-enterprise-root DOES
        assert "org-enterprise-iso" not in sci_topo["network_topology"]["public_knowledge_registry"]
        assert "sci-maths" in sci_topo["network_topology"]["public_knowledge_registry"]
        assert "org-enterprise-iso" in corp_topo["network_topology"]["public_knowledge_registry"]
        assert corp_topo["sync_topology"]["subtree_aggregation_command"] == "zcg subtree pull-all"
        assert corp_topo["sync_topology"]["outbound_knowledge_command"] is not None
        assert len(dept_topo["node_connection_summary"]["lateral_peers"]) == 1
        assert len(dept_topo["node_connection_summary"]["downward_governed_nodes"]) == 1
        assert len(ws_topo["node_connection_summary"]["linked_nodes"]) == 2
        assert ws_topo["node_connection_summary"]["linked_nodes"][1]["relation"] == "lateral-peer"
        assert squad_topo["network_topology"]["network_scope"] == "unit-subnetwork"
        assert ws_topo["sync_topology"]["inbound_sync_command"] == "zcg workstation sync"
        assert oss_topo["network_topology"]["inward_boundary"] == "open-source-curated"
        assert proj_topo["network_topology"]["network_scope"] == "leaf-execution-node"
