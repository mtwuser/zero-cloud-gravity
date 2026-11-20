"""Unit tests for zcg.governance.policy.module_registry.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance.policy.module_registry import (
    reset_node_capabilities_default,
    resolve_effective_workspace_modules,
    resolve_node_capability_matrix,
    set_node_capability_enabled,
)


def _write_manifest(ws: Path, doc: dict[str, object]) -> None:
    path = ws / NODE_MANIFEST_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


class TestModuleRegistry:
    """1:1 unit suite for hierarchical capability bounds, live module resolution, and toggles."""

    def test_resolve_node_capability_matrix_lineage_bounds_and_wallet_airlock_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Parent->Node Lex Superior bounds, wallet airlock blocks, and bare dirs."""
        # Arrange
        parent_ws = tmp_path / "persona-profile"
        wallet_ws = tmp_path / "persona-wallet"
        bare_ws = tmp_path / "bare-ws"
        bare_ws.mkdir()
        _write_manifest(
            parent_ws,
            {
                "layer_id": "persona-profile",
                "layer_role": "workstation",
                "entity_kind": "individual",
                "capability_policy": {
                    "forbidden_modules": ["data_pipeline"],
                    "mandatory_modules": ["docs_reader", "portal_inbox", "data_pipeline"],
                },
            },
        )
        _write_manifest(
            wallet_ws,
            {
                "layer_id": "persona-wallet",
                "layer_role": "squad",
                "entity_kind": "individual",
                "governing_root_id": "persona-profile",
                "capability_policy": "not-a-mapping",
            },
        )
        def_mods = ("work_ledger", "vault", "portal_inbox")

        # Act
        matrix = resolve_node_capability_matrix(
            wallet_ws,
            view_archetype="sovereign-wallet-cockpit",
            default_modules=def_mods,
            parent_dir=parent_ws,
        )
        eff = resolve_effective_workspace_modules(
            wallet_ws,
            view_archetype="sovereign-wallet-cockpit",
            default_modules=def_mods,
            parent_dir=parent_ws,
        )
        bare_matrix = resolve_node_capability_matrix(
            bare_ws, default_modules=("work_ledger", "spatial_atlas")
        )

        # Assert
        by_id = {r["module_id"]: r for r in matrix}
        assert by_id["data_pipeline"]["policy_state"] == "forbidden"
        assert not by_id["data_pipeline"]["enabled"]
        assert by_id["portal_inbox"]["policy_state"] == "forbidden"
        assert "airlock" in by_id["portal_inbox"]["policy_reason"]
        assert by_id["role_projection"]["policy_state"] == "forbidden"
        assert by_id["docs_reader"]["policy_state"] == "mandatory"
        assert by_id["wallet_treasury"]["policy_state"] == "mandatory"
        assert by_id["vault"]["policy_state"] == "optional" and by_id["vault"]["enabled"]
        assert eff == ("work_ledger", "vault", "docs_reader", "wallet_treasury")
        bare_by_id = {r["module_id"]: r for r in bare_matrix}
        assert bare_by_id["work_ledger"]["enabled"] and not bare_by_id["crud"]["enabled"]

    def test_set_and_reset_node_capabilities_and_error_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify enable/disable persistence, idempotent re-enable, reset, and policy errors."""
        # Arrange
        ws = tmp_path / "dept-ops"
        uninit_ws = tmp_path / "uninit"
        uninit_ws.mkdir()
        _write_manifest(
            ws,
            {
                "layer_id": "dept-ops",
                "layer_role": "department",
                "capability_policy": {
                    "forbidden_modules": ["wallet_treasury"],
                    "mandatory_modules": ["work_ledger"],
                },
            },
        )
        defs = ("work_ledger", "docs_reader", "vault")

        # Act
        en_crud = set_node_capability_enabled(
            ws, module_id="crud", enabled=True, default_modules=defs
        )
        en_crud_again = set_node_capability_enabled(
            ws, module_id="crud", enabled=True, default_modules=defs
        )
        dis_vault = set_node_capability_enabled(
            ws, module_id="vault", enabled=False, default_modules=defs
        )
        rst = reset_node_capabilities_default(ws, default_modules=defs)

        # Assert
        assert "crud" in en_crud["enabled_modules"]
        assert en_crud_again["enabled_modules"].count("crud") == 1
        assert "vault" not in dis_vault["enabled_modules"]
        assert rst["reset"] is True and rst["enabled_modules"] == list(defs)
        assert "enabled_modules" not in json.loads(
            (ws / NODE_MANIFEST_REL_PATH).read_text(encoding="utf-8")
        )
        with pytest.raises(ValueError, match="WORKSPACE_MANIFEST_MISSING"):
            set_node_capability_enabled(uninit_ws, module_id="crud", enabled=True)
        with pytest.raises(ValueError, match="WORKSPACE_MANIFEST_MISSING"):
            reset_node_capabilities_default(uninit_ws)
        with pytest.raises(ValueError, match="UNKNOWN_CAPABILITY_MODULE"):
            set_node_capability_enabled(ws, module_id="nonexistent", enabled=True)
        with pytest.raises(ValueError, match="CAPABILITY_FORBIDDEN_BY_POLICY"):
            set_node_capability_enabled(ws, module_id="wallet_treasury", enabled=True)
        with pytest.raises(ValueError, match="CAPABILITY_MANDATORY_BY_POLICY"):
            set_node_capability_enabled(ws, module_id="work_ledger", enabled=False)
        _write_manifest(
            ws,
            {
                "layer_id": "dept-ops",
                "capability_policy": {"forbidden_modules": "not-a-list"},
            },
        )
        assert resolve_node_capability_matrix(ws)[0]["policy_state"] == "optional"
