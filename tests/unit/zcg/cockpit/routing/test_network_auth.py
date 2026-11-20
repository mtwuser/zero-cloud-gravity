"""Unit tests for zcg.cockpit.routing.network_auth.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from zcg.cockpit.routing.network_auth import (
    ENGINE_VERSION,
    ENV_SEMANTIC_META,
    NETWORK_SESSION_KEY_REL_PATH,
    PRIVATE_KEY_FILE_MODE,
    is_private_personal_node,
    resolve_default_node_environment,
    resolve_engine_version,
    resolve_governing_root_workspace,
    resolve_inherited_network_access,
    resolve_network_session_material,
)
from zcg.core.constants import NODE_MANIFEST_REL_PATH


class TestNetworkAuth:
    """Verify Root 0 membership inheritance, shared network session keys, and env defaults."""

    def test_version_and_default_environment_by_entity_kind_and_override_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify VERSION reading, private-personal 'pro' default, and explicit overrides."""
        # Arrange
        ver_file = tmp_path / "VERSION"
        ver_file.write_text("1.3.0\n", encoding="utf-8")
        blank_ver = tmp_path / "BLANK_VERSION"
        blank_ver.write_text("   \n", encoding="utf-8")
        ind_priv = {"entity_kind": "individual", "precedence": 90}
        ind_pub = {"entity_kind": "individual", "layer_role": "knowledge", "visibility": "public"}
        ind_override = {"entity_kind": "individual", "default_active_env": "dev"}
        corp_m = {"entity_kind": "enterprise", "layer_role": "corporate", "precedence": 10}

        # Act
        v_ok = resolve_engine_version(ver_file)
        v_blank = resolve_engine_version(blank_ver)
        v_missing = resolve_engine_version(tmp_path / "NO_VERSION")

        # Assert
        assert ENGINE_VERSION and v_ok == "1.3.0"
        assert v_blank == "1.2.0" and v_missing == "1.2.0"
        assert set(ENV_SEMANTIC_META) == {"dev", "tst", "pre", "pro"}
        assert is_private_personal_node(ind_priv) is True
        assert is_private_personal_node(ind_pub) is False
        assert resolve_default_node_environment(ind_priv) == "pro"
        assert resolve_default_node_environment(ind_pub) == "dev"
        assert resolve_default_node_environment(ind_override) == "dev"
        assert resolve_default_node_environment(corp_m) == "dev"

    def test_root_0_membership_inheritance_and_shared_session_material_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify 3-hop Root 0 inheritance, disabled overrides, and shared 0600 session key."""
        # Arrange
        root_ws = tmp_path / "corp-alpha"
        dept_ws = tmp_path / "dept-fin"
        squad_ws = tmp_path / "squad-ledger"
        foreign_ws = tmp_path / "foreign-root"
        bare_ws = tmp_path / "bare-node"
        for d in (root_ws, dept_ws, squad_ws, foreign_ws):
            (d / "system").mkdir(parents=True)
        bare_ws.mkdir()

        root_m = {
            "layer_id": "corp-alpha",
            "layer_role": "corporate",
            "governing_root_id": "corp-alpha",
            "layer_authority": {"authorized_emails": ["ceo@alpha.net"]},
            "surface_access": {
                "oidc_provider": "google-workspace",
                "allowed_workspace_domains": ["alpha.net"],
                "allowed_workspace_groups": ["all-staff"],
                "operator_emails": ["sec@alpha.net"],
                "member_emails": ["emp@alpha.net"],
                "scoped_external_emails": ["auditor@ext.org"],
                "allowed_linked_peers": {"peer-a": "sec-a"},
                "route_rules": [{"path_pattern": "/intra*", "ring": "r2"}],
            },
        }
        dept_m = {
            "layer_id": "dept-fin",
            "layer_role": "department",
            "governing_root_id": "corp-alpha",
            "upstream_layer": {"layer_id": "corp-alpha"},
            "layer_authority": {"authorized_emails": ["cfo@alpha.net"]},
            "surface_access": {
                "allowed_workspace_groups": ["dept-finance"],
                "route_rules": [
                    {
                        "path_pattern": "/api/modules/wallet-treasury*",
                        "ring": "r2",
                        "required_groups": ["dept-finance"],
                    }
                ],
                "allowed_linked_peers": {"peer-b": "sec-b"},
            },
        }
        foreign_m = {
            "layer_id": "foreign-root",
            "governing_root_id": "other-org",
            "layer_authority": "invalid",
            "surface_access": {"operator_emails": ["leak@other.org"]},
        }
        squad_m = {
            "layer_id": "squad-ledger",
            "layer_role": "squad",
            "governing_root_id": "corp-alpha",
            "upstream_layer": {"layer_id": "dept-fin"},
        }
        (root_ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(root_m), encoding="utf-8")
        (dept_ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(dept_m), encoding="utf-8")
        (squad_ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(squad_m), encoding="utf-8")
        (foreign_ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(foreign_m), encoding="utf-8")

        def _parent_lookup(cur: Path, *_a: object, **_k: object) -> Path | None:
            if cur == squad_ws.resolve():
                return dept_ws.resolve()
            if cur == dept_ws.resolve():
                return root_ws.resolve()
            if cur == root_ws.resolve():
                return foreign_ws.resolve()
            return None

        # Act
        with patch(
            "zcg.cockpit.routing.network_auth.resolve_default_parent_dir",
            side_effect=_parent_lookup,
        ):
            gov_dir = resolve_governing_root_workspace(squad_ws, squad_m)
            inh = resolve_inherited_network_access(squad_ws, squad_m)
            k_root, doms_root = resolve_network_session_material(
                root_ws,
                root_m,
                intranet_zone=".intranet.alpha.net",
                local_dev_zone="alpha.localhost",
                env_vars={},
            )
            k_dept, doms_dept = resolve_network_session_material(
                dept_ws, dept_m, local_dev_zone="alpha.localhost", env_vars={}
            )
            dis_inh = resolve_inherited_network_access(
                dept_ws, {**dept_m, "surface_access": {"enabled": False}}
            )
            no_la_inh = resolve_inherited_network_access(
                dept_ws, {**dept_m, "surface_access": {"inherit_layer_authority": False}}
            )

        none_inh = resolve_inherited_network_access(
            bare_ws, {"layer_id": "bare", "layer_authority": "not-a-map"}
        )
        k_env, _ = resolve_network_session_material(
            bare_ws, {"layer_id": "bare"}, env_vars={"ZCG_SURFACE_SESSION_KEY": "env-key-99"}
        )
        k_bare, doms_bare = resolve_network_session_material(
            bare_ws, {"layer_id": "bare"}, env_vars={}, fallback_key="fb-key"
        )

        # Assert
        assert gov_dir == root_ws.resolve()
        assert inh["has_surface_access"] is True
        assert inh["authorized_emails"] == ["ceo@alpha.net", "cfo@alpha.net"]
        sa = inh["surface_access"]
        assert sa["oidc_provider"] == "google-workspace"
        assert sa["allowed_workspace_domains"] == ["alpha.net"]
        assert sa["allowed_workspace_groups"] == ["all-staff", "dept-finance"]
        assert "leak@other.org" not in sa["operator_emails"]
        assert len(sa["route_rules"]) == 2
        assert sa["allowed_linked_peers"] == {"peer-a": "sec-a", "peer-b": "sec-b"}
        assert k_root == k_dept and len(k_root) >= 16
        key_file = root_ws / NETWORK_SESSION_KEY_REL_PATH
        assert (key_file.stat().st_mode & 0o777) == PRIVATE_KEY_FILE_MODE
        assert doms_root == ("intranet.alpha.net", "alpha.localhost")
        assert doms_dept == ("alpha.localhost",)
        assert dis_inh["has_surface_access"] is False
        assert no_la_inh["authorized_emails"] == []
        assert none_inh["has_surface_access"] is False
        assert k_env == "env-key-99"
        assert k_bare == "fb-key" and doms_bare == ()
