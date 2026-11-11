"""Unit tests for zcg.topology.identity.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.topology import identity


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    target = node_dir / NODE_MANIFEST_REL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


class TestIdentity:
    """Verify parent/child resolution, node identity, inter-layer scope, and hierarchical RBAC."""

    def test_resolve_default_parent_and_mounted_child_dirs_expected(self, tmp_path: Path) -> None:
        """Verify parent discovery via arg, Makefile, layers/, and sibling governing_root_id."""
        # Arrange
        root_dir = tmp_path / "corp-iso-root"
        _write_manifest(root_dir, {"layer_id": "corp-iso-root", "layer_role": "corporate"})

        mounted_child = root_dir / "layers" / "mounted-dir"
        _write_manifest(
            mounted_child, {"layer_id": "dept-legal-iso", "layer_role": "domain-policy"}
        )
        direct_child = root_dir / "layers" / "dept-ops"
        _write_manifest(direct_child, {"layer_id": "dept-ops", "layer_role": "department"})
        (root_dir / "layers" / "corrupt-node" / "system").mkdir(parents=True)
        (root_dir / "layers" / "corrupt-node" / NODE_MANIFEST_REL_PATH).write_text(
            "{bad-json", encoding="utf-8"
        )
        (root_dir / "layers" / "list-node" / "system").mkdir(parents=True)
        (root_dir / "layers" / "list-node" / NODE_MANIFEST_REL_PATH).write_text(
            "[1]", encoding="utf-8"
        )

        org_group = tmp_path / "corp-iso-root-org"
        sib_dept = org_group / "dept-r-and-d"
        _write_manifest(
            sib_dept,
            {
                "layer_id": "dept-r-and-d",
                "layer_role": "department",
                "governing_root_id": "corp-iso-root",
            },
        )
        mk_child = tmp_path / "squad-a"
        _write_manifest(mk_child, {"layer_id": "squad-a", "layer_role": "squad"})
        (mk_child / "Makefile").write_text(f"PARENT_DIR ?= {sib_dept}\n", encoding="utf-8")

        standalone = tmp_path / "standalone"
        standalone.mkdir()
        (standalone / "Makefile").write_text("PARENT_DIR ?= /nonexistent/path\n", encoding="utf-8")

        # Act
        assert identity.resolve_default_parent_dir(mk_child, root_dir) == root_dir.resolve()
        assert identity.resolve_default_parent_dir(mk_child) == sib_dept.resolve()
        assert identity.resolve_default_parent_dir(mounted_child) == root_dir.resolve()
        assert identity.resolve_default_parent_dir(sib_dept) == root_dir.resolve()
        assert identity.resolve_default_parent_dir(standalone) is None
        assert identity.resolve_mounted_child_dir(root_dir, "dept-ops") == direct_child.resolve()
        assert (
            identity.resolve_mounted_child_dir(root_dir, "dept-legal-iso")
            == mounted_child.resolve()
        )
        assert identity.resolve_mounted_child_dir(root_dir, "dept-r-and-d") == sib_dept.resolve()
        assert identity.resolve_mounted_child_dir(root_dir, "absent-child") is None
        # Assert
        assert identity.resolve_mounted_child_dir(standalone, "none") is None

    def test_resolve_node_entity_identity_across_oss_enterprise_individual_and_twins_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify entity_kind, domain suffixes, twin bridge_mode, and root_0_public_approved."""
        # Arrange — OSS dev vs OSS appliance
        oss_dev = tmp_path / "dev-zero-cloud-gravity"
        oss_dev.mkdir()
        id_dev = identity.resolve_node_entity_identity(
            oss_dev, {"layer_id": "root", "layer_role": "workstation", "precedence": 10}
        )
        oss_pub = tmp_path / "zero-cloud-gravity"
        oss_pub.mkdir()
        (oss_pub / ".workstation-state.json").write_text("{}", encoding="utf-8")
        _write_manifest(
            oss_pub, {"layer_id": "root", "layer_role": "workstation", "precedence": 10}
        )
        id_oss = identity.resolve_node_entity_identity(oss_pub)

        # Arrange — Individual workstation & individual study node (.personal.local)
        ind_ws = tmp_path / "user-pc"
        _write_manifest(
            ind_ws,
            {"layer_id": "user-pc", "layer_role": "workstation", "entity_kind": "individual"},
        )
        id_ind_ws = identity.resolve_node_entity_identity(ind_ws)
        ind_study = tmp_path / "study-lab"
        id_ind_study = identity.resolve_node_entity_identity(
            ind_study,
            {"layer_id": "study-lab", "layer_role": "department", "precedence": 88},
            parent_dir=ind_ws,
        )

        # Arrange — Enterprise Root 0, Org Twin, subordinate unapproved, and prefix fallbacks
        corp = tmp_path / "corp-iso-root"
        _write_manifest(corp, {"layer_id": "corp-iso-root", "layer_role": "corporate"})
        id_twin = identity.resolve_node_entity_identity(
            tmp_path / "org-iso",
            {
                "layer_id": "org-iso",
                "layer_role": "knowledge",
                "governing_root_id": "corp-iso-root",
                "public_url": "https://github.com/example/org-iso.git",
            },
        )
        unapproved_know = identity.resolve_node_entity_identity(
            tmp_path / "org-sub",
            {
                "layer_id": "org-sub",
                "layer_role": "knowledge",
                "governing_root_id": "corp-iso-root",
                "upstream_layer": {"layer_id": "dept-marketing"},
            },
        )
        prefixed_dept = identity.resolve_node_entity_identity(
            tmp_path / "acme-dept-sales",
            {"layer_id": "acme-dept-sales", "layer_role": "department"},
            parent_dir=oss_pub,
        )
        up_prefixed = identity.resolve_node_entity_identity(
            tmp_path / "unit-x",
            {
                "layer_id": "unit-x",
                "layer_role": "squad",
                "upstream_layer": {"layer_id": "beta-dept-core"},
            },
        )
        gov_root = identity.resolve_node_entity_identity(
            tmp_path / "gov-es", {"layer_id": "gov-es", "layer_role": "knowledge", "precedence": 2}
        )
        pub_twin = identity.resolve_node_entity_identity(
            tmp_path / "pub-user",
            {
                "layer_id": "pub-user",
                "layer_role": "knowledge",
                "governing_root_id": "user-pc",
                "public_url": "https://github.com/example/pub-user.git",
            },
        )
        pub_solo = identity.resolve_node_entity_identity(
            tmp_path / "pub-solo",
            {"layer_id": "pub-solo", "layer_role": "knowledge"},
        )
        leaf_proj = identity.resolve_node_entity_identity(tmp_path / "billing-app", {})
        # Act

        # Assert
        assert id_dev["visibility_scope"] == "private:open-source:dev"
        assert id_oss["visibility_scope"] == "public-oss"
        assert id_oss["operating_state"] == "oss-readonly-appliance"
        assert id_ind_ws["operating_state"] == "individual-root"
        assert (
            id_ind_study["public_node_identity"]["canonical_domain"] == "study-lab.personal.local"
        )
        assert id_ind_study["governing_root_id"] == "user-pc"
        assert id_twin["public_node_identity"]["bridge_mode"] == "private-to-public-twin"
        assert id_twin["public_node_identity"]["recognizable_in_network"] is True
        assert unapproved_know["visibility"] == "private"
        assert unapproved_know["public_node_identity"]["root_0_public_approved"] is False
        assert prefixed_dept["governing_root_id"] == "acme-root"
        assert up_prefixed["governing_root_id"] == "beta-root"
        assert gov_root["public_node_identity"]["canonical_domain"] == "gov-es.knowledge.local"
        assert pub_twin["entity_kind"] == "individual"
        assert pub_twin["public_node_identity"]["bridge_mode"] == "private-to-public-twin"
        assert pub_twin["public_node_identity"]["canonical_domain"] == "pub-user.knowledge.local"
        assert pub_twin["public_node_identity"]["recognizable_in_network"] is True
        assert pub_solo["entity_kind"] == "individual"
        assert pub_solo["governing_root_id"] == "pub-solo"
        assert pub_solo["public_node_identity"]["bridge_mode"] == "canonical-public-knowledge"
        assert leaf_proj["visibility_scope"] == "private:enterprise:project"

    def test_classify_inter_layer_relationship_and_hierarchical_rbac_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify internal/knowledge/external MCP modes and 1-hop overarching parent RBAC."""
        # Arrange
        corp_dir = tmp_path / "corp-root"
        _write_manifest(
            corp_dir,
            {
                "layer_id": "corp-root",
                "layer_role": "corporate",
                "precedence": 10,
                "layer_authority": {"authorized_emails": ["ceo@iso.example"]},
            },
        )
        dept_dir = tmp_path / "dept-eng"
        _write_manifest(
            dept_dir,
            {
                "layer_id": "dept-eng",
                "layer_role": "department",
                "precedence": 30,
                "governing_root_id": "corp-root",
                "layer_authority": {
                    "maintainer_emails": ["lead@iso.example"],
                    "roster": {"members": [{"email": "*@dev.iso.example"}]},
                },
            },
        )
        peer_root = identity.resolve_node_entity_identity(
            tmp_path / "other-root", {"layer_id": "other-root", "layer_role": "corporate"}
        )
        oss_node = identity.resolve_node_entity_identity(
            tmp_path / "zero-cloud-gravity", {"layer_id": "root", "layer_role": "workstation"}
        )
        know_node = identity.resolve_node_entity_identity(
            tmp_path / "sci-maths", {"layer_id": "sci-maths", "layer_role": "knowledge"}
        )
        corp_id = identity.resolve_node_entity_identity(corp_dir)
        dept_id = identity.resolve_node_entity_identity(dept_dir, parent_dir=corp_dir)

        # Act
        rel_int = identity.classify_inter_layer_relationship(dept_id, corp_id)
        rel_know = identity.classify_inter_layer_relationship(dept_id, know_node)
        rel_oss = identity.classify_inter_layer_relationship(corp_id, oss_node)
        rel_peer = identity.classify_inter_layer_relationship(corp_id, peer_root)
        rel_blocked = identity.classify_inter_layer_relationship(dept_id, peer_root)

        prof_overarching = identity.resolve_hierarchical_actor_profile(
            dept_dir, actor_email="ceo@iso.example", parent_dir=corp_dir
        )
        prof_member = identity.resolve_hierarchical_actor_profile(
            dept_dir, actor_email="alice@dev.iso.example", parent_dir=corp_dir
        )
        prof_outside = identity.resolve_hierarchical_actor_profile(
            dept_dir, actor_email="stranger@other.example", parent_dir=corp_dir
        )
        prof_anon = identity.resolve_hierarchical_actor_profile(dept_dir, actor_email="")

        oss_parent = tmp_path / "oss-parent"
        _write_manifest(oss_parent, {"layer_id": "root", "layer_role": "workstation"})
        prof_oss_up = identity.resolve_hierarchical_actor_profile(
            dept_dir, actor_email="ceo@iso.example", parent_dir=oss_parent
        )

        ind_dir = tmp_path / "solo-lab"
        _write_manifest(ind_dir, {"layer_id": "solo-lab", "layer_role": "squad", "precedence": 90})
        prof_ind = identity.resolve_hierarchical_actor_profile(ind_dir, actor_email="me@local")

        # Assert
        assert rel_int["mcp_communication_mode"] == "internal-1hop-hierarchical"
        assert rel_know["mcp_communication_mode"] == "knowledge-rcap1-and-citation"
        assert rel_oss["mcp_communication_mode"] == "external-root0-to-oss-sanitized"
        assert rel_peer["mcp_communication_mode"] == "external-peer-root0-pr-and-readonly-mcp"
        assert rel_blocked["mcp_communication_mode"] == "blocked-must-route-via-governing-root0"
        assert prof_overarching["effective_role"] == "owner"
        assert prof_overarching["hierarchical_authority_granted"] is True
        assert prof_member["effective_role"] == "member"
        assert prof_outside["effective_role"] == "consumer"
        assert prof_anon["effective_role"] == "consumer"
        assert prof_oss_up["effective_role"] == "consumer"
        assert prof_ind["effective_role"] == "owner"
