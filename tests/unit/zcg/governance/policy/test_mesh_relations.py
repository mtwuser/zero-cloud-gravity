"""Unit tests for zcg.governance.policy.mesh_relations.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from zcg.governance.policy.mesh_relations import (
    MESH_RELATIONS_CONTRACT_REV,
    VALID_MESH_TOPOLOGY_MODES,
    VALID_RELATION_ROLES,
    VALID_RELATION_VERBS,
    VALID_WORKSPACE_SCOPES,
    configure_mesh_governance_policy,
    evaluate_node_exchange_grant,
    is_airlocked_wallet_node,
    normalize_workspace_scope,
    resolve_exchange_target_dir,
    resolve_mesh_governance_policy,
    resolve_node_relation_grants,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> Path:
    (node_dir / "system").mkdir(parents=True, exist_ok=True)
    m_path = node_dir / "system/zcg-node.json"
    m_path.write_text(json.dumps(payload), encoding="utf-8")
    return m_path


class TestMeshRelations:
    """1:1 unit suite for mesh governance policies, lateral channels, and exchange grants."""

    def test_scope_normalization_and_wallet_airlock_predicates_expected(self) -> None:
        """Verify workspace scope alias normalization and airlocked wallet detection."""
        # Arrange
        cases = {
            "": "all",
            "all": "all",
            "node": "node",
            "OWN": "node",
            "network": "network",
            "parent": "network",
            "cross-node": "network",
            "corpora": "corpora",
            "corpus": "corpora",
            "unknown-x": "all",
        }

        # Act
        normalized = {k: normalize_workspace_scope(k) for k in cases}
        by_suffix = is_airlocked_wallet_node("persona-wallet")
        by_archetype = is_airlocked_wallet_node(
            "vault-x", {"view_archetype": "sovereign-wallet-cockpit"}
        )
        normal = is_airlocked_wallet_node("dept-eng", {"view_archetype": "node-work-cockpit"})
        no_manifest = is_airlocked_wallet_node("dept-eng")

        # Assert
        assert normalized == cases
        assert VALID_WORKSPACE_SCOPES == ("all", "node", "network", "corpora")
        assert "full-mesh" in VALID_MESH_TOPOLOGY_MODES
        assert "governed-peer" in VALID_RELATION_ROLES
        assert "consult_context" in VALID_RELATION_VERBS
        assert by_suffix is True and by_archetype is True
        assert normal is False and no_manifest is False

    def test_resolve_mesh_governance_policy_inheritance_and_channel_parsing_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify parent policy inheritance, entity defaults, and malformed channel filtering."""
        # Arrange
        bare = tmp_path / "bare-node"
        bare.mkdir()
        ind_root = tmp_path / "persona-profile"
        _write_manifest(
            ind_root,
            {
                "layer_id": "persona-profile",
                "layer_role": "workstation",
                "entity_kind": "individual",
            },
        )
        corp_root = tmp_path / "corp-root"
        _write_manifest(
            corp_root,
            {
                "layer_id": "corp-root",
                "layer_role": "corporate",
                "entity_kind": "enterprise",
                "capability_policy": {
                    "mesh_governance": {
                        "topology_mode": "curated-matrix",
                        "lateral_channels": [
                            "not-a-dict",
                            {"source": "BAD_ID", "target": "dept-ops"},
                            {"source": "dept-eng", "target": "dept-eng"},
                            {"source": "persona-wallet", "target": "dept-ops"},
                            {"source": "dept-eng", "target": "persona-wallet"},
                            {
                                "source": "dept-eng",
                                "target": "dept-ops",
                                "verbs": ["consult_context", "invalid_verb", "consult_context"],
                                "reciprocal": False,
                            },
                            {
                                "source_node": "dept-eng",
                                "target_node": "dept-sec",
                                "allowed_verbs": "not-a-list",
                            },
                        ],
                    }
                },
            },
        )
        child_eng = tmp_path / "dept-eng"
        _write_manifest(
            child_eng,
            {
                "layer_id": "dept-eng",
                "layer_role": "department",
                "entity_kind": "enterprise",
                "governing_root_id": "corp-root",
            },
        )
        ext_node = tmp_path / "partner-ext"
        _write_manifest(
            ext_node,
            {
                "layer_id": "partner-ext",
                "layer_role": "corporate",
                "entity_kind": "enterprise",
                "capability_policy": {
                    "mesh_governance": {"topology_mode": "bad-mode", "lateral_channels": "bad"}
                },
            },
        )

        # Act
        p_bare = resolve_mesh_governance_policy(bare)
        p_ind = resolve_mesh_governance_policy(ind_root)
        p_child = resolve_mesh_governance_policy(child_eng, parent_dir=corp_root)
        p_ext = resolve_mesh_governance_policy(ext_node, parent_dir=corp_root)

        # Assert
        assert p_bare.topology_mode == "curated-matrix" and p_bare.inherited_from_parent is False
        assert p_ind.topology_mode == "full-mesh" and p_ind.governed_by == "persona-profile"
        assert p_child.inherited_from_parent is True and p_child.governed_by == "corp-root"
        assert p_child.topology_mode == "curated-matrix"
        assert len(p_child.lateral_channels) == 2
        assert p_child.lateral_channels[0].allowed_verbs == ("consult_context",)
        assert p_child.lateral_channels[0].reciprocal is False
        assert p_child.lateral_channels[1].allowed_verbs == ("consult_context", "propose_work")
        assert p_ext.inherited_from_parent is False and p_ext.topology_mode == "curated-matrix"
        assert p_ext.lateral_channels == ()

    def test_configure_mesh_governance_policy_mutations_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify mode updates, channel upsert/removal, dry-run, and validation errors."""
        # Arrange
        missing = tmp_path / "no-manifest"
        missing.mkdir()
        ws = tmp_path / "corp-root"
        m_path = _write_manifest(
            ws,
            {
                "layer_id": "corp-root",
                "layer_role": "corporate",
                "entity_kind": "enterprise",
                "capability_policy": {"other_flag": True},
            },
        )

        # Act
        dry = configure_mesh_governance_policy(
            ws,
            topology_mode="hierarchical-only",
            add_channel={"source": "dept-eng", "target": "dept-ops"},
            dry_run=True,
        )
        added = configure_mesh_governance_policy(
            ws,
            topology_mode="curated-matrix",
            add_channel={
                "source": "dept-eng",
                "target": "dept-ops",
                "verbs": ["consult_context", "propose_work", "consult_context"],
            },
        )
        upserted = configure_mesh_governance_policy(
            ws,
            add_channel={
                "source_node": "dept-ops",
                "target_node": "dept-eng",
                "allowed_verbs": ["consult_context"],
                "reciprocal": True,
            },
        )
        kept = configure_mesh_governance_policy(
            ws,
            add_channel={"source": "dept-a", "target": "dept-b", "reciprocal": False},
        )
        after_rm = configure_mesh_governance_policy(ws, remove_channel=("dept-eng", "dept-ops"))
        after_non_recip_rm = configure_mesh_governance_policy(
            ws, remove_channel=("dept-b", "dept-a")
        )
        persisted = json.loads(m_path.read_text(encoding="utf-8"))

        # Assert
        assert dry["contract_rev"] == MESH_RELATIONS_CONTRACT_REV and dry["dry_run"] is True
        assert (
            "mesh_governance"
            not in json.loads(m_path.read_text(encoding="utf-8")).get("capability_policy", {})
            or added["channel_count"] == 1
        )
        assert upserted["topology_mode"] == "curated-matrix" and upserted["channel_count"] == 1
        assert kept["channel_count"] == 2
        assert after_rm["channel_count"] == 1
        assert after_non_recip_rm["channel_count"] == 1
        assert persisted["capability_policy"]["other_flag"] is True

        with pytest.raises(ValueError, match="MISSING_NODE_MANIFEST"):
            configure_mesh_governance_policy(missing, topology_mode="full-mesh")
        with pytest.raises(ValueError, match="INVALID_MESH_TOPOLOGY_MODE"):
            configure_mesh_governance_policy(ws, topology_mode="mesh-99")
        with pytest.raises(ValueError, match="INVALID_CHANNEL_NODE"):
            configure_mesh_governance_policy(ws, add_channel={"source": "BAD", "target": "dept-a"})
        with pytest.raises(ValueError, match="SELF_CHANNEL_FORBIDDEN"):
            configure_mesh_governance_policy(
                ws, add_channel={"source": "dept-a", "target": "dept-a"}
            )
        with pytest.raises(ValueError, match="WALLET_LATERAL_CHANNEL_BLOCKED"):
            configure_mesh_governance_policy(
                ws, add_channel={"source": "dept-a", "target": "persona-wallet"}
            )
        with pytest.raises(ValueError, match="INVALID_RELATION_VERB"):
            configure_mesh_governance_policy(
                ws, add_channel={"source": "dept-a", "target": "dept-b", "verbs": ["destroy_all"]}
            )

    def test_relation_grants_and_exchange_evaluation_across_all_topology_modes_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify grants across upward, downward, full-mesh, curated-matrix, hierarchical, links."""
        # Arrange
        bare = tmp_path / "bare"
        bare.mkdir()
        root_ws = tmp_path / "persona-profile"
        _write_manifest(
            root_ws,
            {
                "layer_id": "persona-profile",
                "layer_role": "workstation",
                "entity_kind": "individual",
                "linked_nodes": [
                    {
                        "node_id": "partner-co",
                        "layer_role": "corporate",
                        "relation": "lateral-peer",
                    },
                    {
                        "node_id": "sci-math",
                        "layer_role": "knowledge",
                        "relation": "knowledge-feed",
                    },
                    {
                        "node_id": "persona-work",
                        "layer_role": "project",
                        "relation": "lateral-peer",
                    },
                    {"node_id": "ext-wallet", "layer_role": "project", "relation": "lateral-peer"},
                ],
            },
        )
        work_ws = tmp_path / "persona-work"
        _write_manifest(
            work_ws,
            {
                "layer_id": "persona-work",
                "layer_role": "project",
                "entity_kind": "individual",
                "governing_root_id": "persona-profile",
            },
        )
        tutor_ws = tmp_path / "persona-tutor"
        _write_manifest(
            tutor_ws,
            {
                "layer_id": "persona-tutor",
                "layer_role": "project",
                "entity_kind": "individual",
                "governing_root_id": "persona-profile",
            },
        )
        wallet_ws = tmp_path / "persona-wallet"
        _write_manifest(
            wallet_ws,
            {
                "layer_id": "persona-wallet",
                "layer_role": "project",
                "entity_kind": "individual",
                "governing_root_id": "persona-profile",
            },
        )

        # Act: individual full-mesh default + airlocked wallet self
        g_bare = resolve_node_relation_grants(bare)
        g_wallet = resolve_node_relation_grants(wallet_ws, parent_dir=root_ws)
        g_root = {g.target_node: g for g in resolve_node_relation_grants(root_ws)}
        g_work_full = {
            g.target_node: g for g in resolve_node_relation_grants(work_ws, parent_dir=root_ws)
        }
        grant_ok = evaluate_node_exchange_grant(
            work_ws,
            target_node="persona-tutor",
            required_verb="consult_context",
            parent_dir=root_ws,
        )

        # Switch parent to curated-matrix and hierarchical-only
        configure_mesh_governance_policy(
            root_ws,
            topology_mode="curated-matrix",
            add_channel={
                "source": "persona-tutor",
                "target": "persona-work",
                "verbs": ["consult_context"],
                "reciprocal": True,
            },
        )
        g_work_curated = {
            g.target_node: g for g in resolve_node_relation_grants(work_ws, parent_dir=root_ws)
        }
        configure_mesh_governance_policy(
            root_ws,
            topology_mode="curated-matrix",
            remove_channel=("persona-tutor", "persona-work"),
        )
        g_work_unapproved = {
            g.target_node: g for g in resolve_node_relation_grants(work_ws, parent_dir=root_ws)
        }
        configure_mesh_governance_policy(root_ws, topology_mode="hierarchical-only")
        g_work_hier = {
            g.target_node: g for g in resolve_node_relation_grants(work_ws, parent_dir=root_ws)
        }

        # Assert
        assert g_bare == () and g_wallet == ()
        assert g_root["persona-work"].relation_role == "governor"
        assert g_root["persona-wallet"].relation_role == "airlocked"
        assert g_root["persona-wallet"].allowed_verbs == ()
        assert g_root["partner-co"].relation_role == "external-partner"
        assert "sci-math" not in g_root and "ext-wallet" not in g_root
        assert g_work_full["persona-profile"].relation_role == "governed-child"
        assert g_work_full["persona-tutor"].relation_role == "governed-peer"
        assert g_work_full["persona-wallet"].relation_role == "airlocked"
        assert grant_ok.target_node == "persona-tutor"
        assert g_work_curated["persona-tutor"].allowed_verbs == ("consult_context",)
        assert "persona-tutor" not in g_work_unapproved
        assert "persona-tutor" not in g_work_hier
        with pytest.raises(ValueError, match="MESH_RELATION_FORBIDDEN"):
            evaluate_node_exchange_grant(
                work_ws,
                target_node="persona-tutor",
                required_verb="propose_work",
                parent_dir=root_ws,
            )

    def test_resolve_exchange_target_dir_parent_child_sibling_and_links_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify local directory resolution across upward, downward, sibling, and linked nodes."""
        # Arrange
        bare = tmp_path / "bare-ws"
        bare.mkdir()
        parent_ws = tmp_path / "corp-root"
        _write_manifest(parent_ws, {"layer_id": "corp-root", "layer_role": "corporate"})
        eng_ws = parent_ws / "layers/dept-eng"
        sub_ws = eng_ws / "layers/squad-api"
        ops_ws = parent_ws / "layers/dept-ops"
        ext_abs = tmp_path / "partner-abs"
        ext_rel = tmp_path / "partner-rel"
        ext_sib = tmp_path / "partner-sib"
        standalone_ws = tmp_path / "solo-node"
        _write_manifest(sub_ws, {"layer_id": "squad-api", "layer_role": "squad"})
        _write_manifest(ops_ws, {"layer_id": "dept-ops", "layer_role": "department"})
        _write_manifest(ext_abs, {"layer_id": "partner-abs", "layer_role": "corporate"})
        _write_manifest(ext_rel, {"layer_id": "partner-rel", "layer_role": "corporate"})
        _write_manifest(ext_sib, {"layer_id": "partner-sib", "layer_role": "corporate"})
        _write_manifest(
            standalone_ws,
            {
                "layer_id": "solo-node",
                "layer_role": "project",
                "linked_nodes": [
                    {"node_id": "partner-sib", "target_ref": "https://example.invalid/repo.git"},
                ],
            },
        )
        _write_manifest(
            eng_ws,
            {
                "layer_id": "dept-eng",
                "layer_role": "department",
                "governing_root_id": "corp-root",
                "linked_nodes": [
                    "bad-entry",
                    {"node_id": "partner-abs", "target_ref": str(ext_abs)},
                    {"node_id": "partner-rel", "target_ref": "../../../partner-rel"},
                    {"node_id": "partner-missing", "target_ref": str(tmp_path / "nope")},
                ],
            },
        )

        # Act
        res_blank = resolve_exchange_target_dir(eng_ws, "  ")
        res_parent = resolve_exchange_target_dir(eng_ws, "corp-root", parent_dir=parent_ws)
        res_child = resolve_exchange_target_dir(eng_ws, "squad-api", parent_dir=parent_ws)
        res_sib = resolve_exchange_target_dir(eng_ws, "dept-ops", parent_dir=parent_ws)
        res_self = resolve_exchange_target_dir(eng_ws, "dept-eng", parent_dir=parent_ws)
        res_abs = resolve_exchange_target_dir(eng_ws, "partner-abs", parent_dir=parent_ws)
        res_rel = resolve_exchange_target_dir(eng_ws, "partner-rel", parent_dir=parent_ws)
        res_lsib = resolve_exchange_target_dir(standalone_ws, "partner-sib")
        res_miss = resolve_exchange_target_dir(eng_ws, "partner-missing", parent_dir=parent_ws)
        res_bare = resolve_exchange_target_dir(bare, "anything")

        # Assert
        assert res_blank is None and res_self is None and res_miss is None and res_bare is None
        assert res_parent == parent_ws.resolve()
        assert res_child == sub_ws.resolve()
        assert res_sib == ops_ws.resolve()
        assert res_abs == ext_abs.resolve()
        assert res_rel == ext_rel.resolve()
        assert res_lsib == ext_sib.resolve()
