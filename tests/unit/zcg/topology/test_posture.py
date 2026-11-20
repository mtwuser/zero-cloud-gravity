"""Unit tests for zcg.topology.posture.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.topology import posture


class TestPosture:
    """Verify purpose archetypes, sovereign/managed posture, wallet airlocks, and origins."""

    def test_resolve_purpose_archetype_nominal_subordinate_and_guards_expected(self) -> None:
        """Verify all 7 setup purposes, subordinate managed flip, and invalid input guards."""
        # Arrange
        ind_purpose = "individual-sovereign"
        ent_purpose = "enterprise-network"

        # Act
        ind = posture.resolve_purpose_archetype(ind_purpose)
        ind_squad = posture.resolve_purpose_archetype(ind_purpose, layer_role="squad")
        acad = posture.resolve_purpose_archetype("academic-tutor")
        acad_squad = posture.resolve_purpose_archetype("academic-tutor", layer_role="squad")
        ent_root = posture.resolve_purpose_archetype(ent_purpose)
        ent_dept = posture.resolve_purpose_archetype(ent_purpose, layer_role="department")
        know = posture.resolve_purpose_archetype("knowledge-commons")

        # Assert
        assert len(posture.VALID_SETUP_PURPOSES) == 7
        assert ind["default_role"] == "workstation" and ind["default_precedence"] == 90
        assert ind["default_templates"] == ["universal-base", "workstation-control-tower"]
        assert ind["default_governance_posture"] == "sovereign"
        assert ind["personal_constellation_pillars"] == [
            "profile",
            "tutor",
            "work",
            "wallet",
            "security",
            "game",
        ]
        assert ind_squad["default_role"] == "squad" and ind_squad["default_precedence"] == 50
        assert ind_squad["default_governance_posture"] == "sovereign"
        assert ind_squad["default_templates"] == ["universal-base", "node-work-cockpit"]
        assert acad["default_role"] == "department" and acad["default_entity_kind"] == "individual"
        assert (
            acad["default_precedence"] == 86 and acad["default_governance_posture"] == "sovereign"
        )
        assert acad["default_templates"] == [
            "academic-base",
            "academic-curriculum",
            "tutor-study-cockpit",
        ]
        assert acad_squad["default_role"] == "squad" and acad_squad["default_precedence"] == 50
        assert ent_root["default_governance_posture"] == "sovereign"
        assert ent_root["personal_constellation_pillars"] == []
        assert ent_dept["default_role"] == "department"
        assert ent_dept["default_governance_posture"] == "managed"
        assert "node-work-cockpit" in ent_dept["default_templates"]
        assert know["default_entity_kind"] == "open-source"
        with pytest.raises(ValueError, match="Invalid purpose"):
            posture.resolve_purpose_archetype("unknown-purpose")
        with pytest.raises(ValueError, match="Invalid layer_role"):
            posture.resolve_purpose_archetype(ent_purpose, layer_role="invalid-role")

    def test_resolve_governance_posture_wallet_airlock_and_tree_isolation_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 4-pillar personal detection, R3 wallet airlock, and managed tree isolation."""
        # Arrange
        profile_dir = tmp_path / "persona-profile"
        (profile_dir / "system").mkdir(parents=True)
        (profile_dir / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-profile",
                    "layer_role": "workstation",
                    "entity_kind": "individual",
                    "precedence": 90,
                }
            ),
            encoding="utf-8",
        )
        wallet_dir = tmp_path / "persona-wallet"
        (wallet_dir / "system").mkdir(parents=True)
        (wallet_dir / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-wallet",
                    "layer_role": "squad",
                    "entity_kind": "individual",
                    "precedence": 88,
                    "governing_root_id": "persona-profile",
                }
            ),
            encoding="utf-8",
        )
        work_dir = tmp_path / "persona-work"
        (work_dir / "system").mkdir(parents=True)
        (work_dir / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-work",
                    "layer_role": "squad",
                    "entity_kind": "individual",
                    "precedence": 87,
                    "personal_pillar": "work",
                    "settlement_mode": "dedicated-settlement-endpoint",
                }
            ),
            encoding="utf-8",
        )
        custom_ind = tmp_path / "persona-notes"
        (custom_ind / "system").mkdir(parents=True)
        (custom_ind / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-notes",
                    "layer_role": "project",
                    "entity_kind": "individual",
                    "precedence": 89,
                    "settlement_mode": "invalid-mode",
                }
            ),
            encoding="utf-8",
        )
        corp_dept = tmp_path / "dept-platform"
        (corp_dept / "system").mkdir(parents=True)
        (corp_dept / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "dept-platform",
                    "layer_role": "department",
                    "entity_kind": "enterprise",
                    "precedence": 30,
                    "governing_root_id": "corp-nova-root",
                }
            ),
            encoding="utf-8",
        )
        exp_posture = tmp_path / "explicit-managed"
        (exp_posture / "system").mkdir(parents=True)

        # Act
        profile_res = posture.resolve_governance_posture(profile_dir)
        wal_res = posture.resolve_governance_posture(wallet_dir, parent_dir=profile_dir)
        wrk_res = posture.resolve_governance_posture(work_dir, parent_dir=profile_dir)
        notes_res = posture.resolve_governance_posture(custom_ind)
        bad_tree_res = posture.resolve_governance_posture(corp_dept, parent_dir=profile_dir)
        clean_corp_res = posture.resolve_governance_posture(corp_dept)
        exp_res = posture.resolve_governance_posture(
            exp_posture,
            manifest={
                "layer_id": "explicit-managed",
                "layer_role": "squad",
                "entity_kind": "enterprise",
                "governance_posture": "managed",
            },
        )
        sec_res = posture.resolve_governance_posture(
            tmp_path / "persona-security",
            manifest={
                "layer_id": "persona-security",
                "layer_role": "domain-policy",
                "entity_kind": "individual",
                "precedence": 85,
            },
        )
        game_res = posture.resolve_governance_posture(
            tmp_path / "persona-game",
            manifest={
                "layer_id": "persona-game",
                "layer_role": "squad",
                "entity_kind": "individual",
                "precedence": 89,
            },
        )

        # Assert
        assert (
            profile_res["personal_pillar"] == "profile"
            and profile_res["governance_posture"] == "sovereign"
        )
        assert sec_res["personal_pillar"] == "security" and sec_res["default_surface_ring"] == "R3"
        assert game_res["personal_pillar"] == "game" and game_res["allow_external_peer_links"]
        assert wal_res["personal_pillar"] == "wallet"
        assert wal_res["default_surface_ring"] == "R3"
        assert wal_res["allow_external_peer_links"] is False
        assert wal_res["allow_epistemic_knowledge_feeds"] is True
        assert wal_res["allow_cross_workspace_1hop_read"] is False
        assert wal_res["settlement_airlock_via"] == "work"
        assert wrk_res["personal_pillar"] == "work"
        assert wrk_res["settlement_mode"] == "dedicated-settlement-endpoint"
        assert notes_res["personal_pillar"] is None and notes_res["settlement_mode"] == "none"
        assert bad_tree_res["governance_posture"] == "managed"
        assert bad_tree_res["workspace_isolation_ok"] is False
        assert clean_corp_res["workspace_isolation_ok"] is True
        assert clean_corp_res["default_surface_ring"] == "R2"
        assert exp_res["governance_posture"] == "managed"

    def test_resolve_surface_origin_modes_and_header_injection_guards_expected(self) -> None:
        """Verify loopback, intranet-gateway, cloud-ephemeral, and host injection guards."""
        # Arrange
        m_doc = {
            "layer_id": "persona-profile",
            "precedence": 90,
            "base_domain": "persona-profile.personal.local",
        }

        # Act
        loop_dev = posture.resolve_surface_origin(m_doc, active_env="dev", env_vars={})
        loop_pro = posture.resolve_surface_origin(m_doc, active_env="pro", port=9790, env_vars={})
        intra_dev = posture.resolve_surface_origin(
            m_doc, active_env="dev", intranet_gateway=True, env_vars={}
        )
        intra_pro = posture.resolve_surface_origin(
            m_doc, active_env="pro", intranet_gateway=True, env_vars={}
        )
        cloud_env = posture.resolve_surface_origin(
            m_doc,
            env_vars={"ZCG_SURFACE_PUBLIC_ORIGIN": "https://persona-profile.run.app/"},
        )
        cloud_hdr = posture.resolve_surface_origin(
            m_doc,
            forwarded_proto="http",
            forwarded_host="ephemeral.iso.example:8080",
            env_vars={},
        )

        # Assert
        assert loop_dev["origin_mode"] == "loopback"
        assert loop_dev["dashboard_url"] == "http://dev.persona-profile.localhost:8790/dashboard"
        assert loop_pro["dashboard_url"] == "http://persona-profile.localhost:9790/dashboard"
        assert intra_dev["origin_mode"] == "intranet-gateway"
        assert intra_dev["canonical_origin"] == "https://dev.persona-profile.personal.local"
        assert intra_pro["canonical_origin"] == "https://persona-profile.personal.local"
        assert cloud_env["origin_mode"] == "cloud-ephemeral"
        assert cloud_env["dashboard_url"] == "https://persona-profile.run.app/dashboard"
        assert cloud_hdr["canonical_origin"] == "http://ephemeral.iso.example:8080"
        with pytest.raises(ValueError, match="Invalid active_env"):
            posture.resolve_surface_origin(m_doc, active_env="bad", env_vars={})
        with pytest.raises(ValueError, match="INVALID_SURFACE_ORIGIN_HOST"):
            posture.resolve_surface_origin(
                m_doc, env_vars={"ZCG_SURFACE_PUBLIC_ORIGIN": "ftp://bad host"}
            )
        with pytest.raises(ValueError, match="INVALID_SURFACE_ORIGIN_HOST"):
            posture.resolve_surface_origin(m_doc, forwarded_host="evil.example/path", env_vars={})

    def test_inspect_remote_node_manifest_local_remote_and_security_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify local/remote manifest inspection and option-injection/clone error guards."""
        # Arrange
        local_node = tmp_path / "custom-repo-dir"
        (local_node / "system").mkdir(parents=True)
        (local_node / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "corp-nova-root",
                    "layer_role": "corporate",
                    "entity_kind": "enterprise",
                    "precedence": 10,
                    "default_stack_templates": ["business-base", "corporate-root-hub"],
                }
            ),
            encoding="utf-8",
        )

        def _fake_clone_ok(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            dest = Path(cmd[-1])
            (dest / "system").mkdir(parents=True)
            (dest / NODE_MANIFEST_REL_PATH).write_text(
                json.dumps(
                    {
                        "layer_id": "sci-physics",
                        "layer_role": "knowledge",
                        "precedence": 20,
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, "", "")

        def _fake_clone_no_manifest(
            cmd: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            Path(cmd[-1]).mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        def _fake_clone_err(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 128, "", "repository not found")

        # Act
        with posture.open_parent_source(None) as none_src:
            opened_none = none_src
        with posture.open_parent_source(str(local_node)) as loc_src:
            opened_loc = loc_src
        loc_res = posture.inspect_remote_node_manifest(str(local_node))
        with patch("zcg.topology.posture.subprocess.run", side_effect=_fake_clone_ok):
            rem_res = posture.inspect_remote_node_manifest(
                "https://github.com/iso-org/arbitrary-repo-name.git"
            )

        # Assert
        assert opened_none is None
        assert opened_loc == (local_node.resolve(), "local-path")
        assert loc_res["source_kind"] == "local-path"
        assert loc_res["layer_id"] == "corp-nova-root"
        assert rem_res["source_kind"] == "git-remote"
        assert rem_res["layer_id"] == "sci-physics"
        with pytest.raises(ValueError, match="UNSAFE_GIT_REMOTE_REF"):
            posture.inspect_remote_node_manifest("-oProxyCommand=evil")
        with pytest.raises(ValueError, match="Invalid branch"):
            posture.inspect_remote_node_manifest(str(local_node), branch="bad..branch")
        with pytest.raises(ValueError, match="Missing remote/local node manifest"):
            posture.inspect_remote_node_manifest(str(tmp_path / "missing"))
        with (
            patch("zcg.topology.posture.subprocess.run", side_effect=_fake_clone_no_manifest),
            pytest.raises(ValueError, match=r"Missing system/zcg-node\.json"),
        ):
            posture.inspect_remote_node_manifest("https://github.com/iso-org/empty.git")
        with (
            patch("zcg.topology.posture.subprocess.run", side_effect=_fake_clone_err),
            pytest.raises(ValueError, match="REMOTE_INSPECT_FAILED"),
        ):
            posture.inspect_remote_node_manifest("https://github.com/iso-org/fail.git")
