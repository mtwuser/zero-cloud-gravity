"""Unit tests for zcg.governance.workspace.antigravity_sync.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from zcg.core import constants
from zcg.governance.workspace import antigravity_sync


class TestAntigravitySync:
    """1:1 unit suite for Antigravity 2.0 plugin bundles and project permissions."""

    def test_build_plugin_bundle_manifest_custom_and_fallback_fields_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify plugin.json enforces official Antigravity 2.0 fields, prompt cap, and logo."""
        # Arrange
        rich_tpl = tmp_path / "plugin-stack/pack-rich"
        (rich_tpl / "assets").mkdir(parents=True)
        (rich_tpl / "assets/logo.svg").write_text("<svg/>", encoding="utf-8")
        (rich_tpl / "template.json").write_text(
            json.dumps(
                {
                    "display_name": "Rich Pack",
                    "description": "Custom sovereign cockpit.",
                    "suggested_prompts": ["p1", " ", "p2", "p3", "p4"],
                }
            ),
            encoding="utf-8",
        )
        bare_tpl = tmp_path / "plugin-stack/pack-bare"
        bare_tpl.mkdir(parents=True)
        (bare_tpl / "template.json").write_text("[1, 2]", encoding="utf-8")

        # Act
        rich_doc = antigravity_sync.build_plugin_bundle_manifest(
            "pack-rich", rich_tpl, version="1.2.3", disabled=False
        )
        bare_doc = antigravity_sync.build_plugin_bundle_manifest(
            "pack-bare", bare_tpl, disabled=True
        )

        # Assert
        assert rich_doc == {
            "name": "pack-rich",
            "displayName": "Rich Pack",
            "description": "Custom sovereign cockpit.",
            "version": "1.2.3",
            "suggestedPrompts": ["p1", "p2", "p3"],
            "disabled": False,
            "logo": "assets/logo.svg",
        }
        assert bare_doc["displayName"] == "Pack Bare"
        assert len(bare_doc["suggestedPrompts"]) == 2
        assert bare_doc["disabled"] is True
        assert "logo" not in bare_doc

    def test_sync_antigravity_plugins_bundles_frontmatter_and_pruning_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify plugin bundle materialization, AGENTS.md frontmatter stripping, and pruning."""
        # Arrange
        non_plug = tmp_path / "tpls/human-stack/science-base"
        non_plug.mkdir(parents=True)
        plug_a = tmp_path / "tpls/plugin-stack/pack-a"
        (plug_a / "rules").mkdir(parents=True)
        (plug_a / "rules/01.md").write_text("---\ntrigger: always_on\n---\n# Rule A\n", "utf-8")
        (plug_a / "rules/02_empty.md").write_text("---\ntrigger: always_on\n---\n", "utf-8")
        (plug_a / "skills/sk-a").mkdir(parents=True)
        (plug_a / "skills/sk-a/SKILL.md").write_text("# Skill A\n", "utf-8")
        (plug_a / "agents").mkdir(parents=True)
        (plug_a / "agents/auditor.md").write_text("# Agent A\n", "utf-8")
        (plug_a / "assets").mkdir(parents=True)
        (plug_a / "assets/logo.svg").write_text("<svg/>", "utf-8")
        plug_b = tmp_path / "tpls/custom/pack-b"
        plug_b.mkdir(parents=True)
        (plug_b / "template.json").write_text(json.dumps({"runtime_service": {}}), "utf-8")
        plug_c = tmp_path / "tpls/plugin-stack/pack-c"
        plug_c.mkdir(parents=True)

        ws = tmp_path / "ws"
        (ws / ".agents/runtime").mkdir(parents=True)
        (ws / ".agents/runtime/pack-b.json").write_text(
            json.dumps({"plugin_disabled": True, "status": "healthy"}), "utf-8"
        )
        active_list = [
            ("science-base", non_plug),
            ("pack-a", plug_a),
            ("pack-a", plug_a),
            ("pack-b", plug_b),
        ]
        known_list = [("science-base", non_plug), ("pack-c", plug_c)]

        # Act
        dry_clean = antigravity_sync.sync_antigravity_plugins(
            ws, active_templates=active_list, known_templates=known_list, dry_run=True
        )
        stale_dir = ws / ".agents/plugins/stale-pack"
        stale_dir.mkdir(parents=True)
        (ws / ".agents/plugins/note.txt").write_text("keep", "utf-8")
        dry_with_stale = antigravity_sync.sync_antigravity_plugins(
            ws, active_templates=active_list, known_templates=known_list, dry_run=True
        )
        live_res = antigravity_sync.sync_antigravity_plugins(
            ws, active_templates=active_list, known_templates=known_list, version="1.0.1"
        )

        # Assert
        assert dry_clean["pruned_bundles"] == []
        assert dry_with_stale["pruned_bundles"] == ["stale-pack"]
        assert stale_dir.is_dir() is False
        assert live_res["active_plugins"] == ["pack-a"]
        assert live_res["disabled_plugins"] == ["pack-b", "pack-c"]
        agents_txt = (ws / ".agents/plugins/pack-a/rules/AGENTS.md").read_text("utf-8")
        assert "trigger:" not in agents_txt and "# Rule A" in agents_txt
        assert (ws / ".agents/plugins/pack-a/skills/sk-a/SKILL.md").is_file()
        assert (ws / ".agents/plugins/pack-a/agents/auditor.md").is_file()
        assert (ws / ".agents/plugins/pack-a/assets/logo.svg").is_file()
        p_json = json.loads((ws / constants.PLUGINS_MANIFEST_REL_PATH).read_text("utf-8"))
        assert p_json["entries"][0]["include_only"] == ["pack-a"]
        assert p_json["entries"][0]["exclude"] == ["pack-b", "pack-c"]

    def test_compile_antigravity_permissions_wallet_airlock_and_hierarchy_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify R3 wallet airlock vs. 1-hop read-only grants and curated egress allowlists."""
        # Arrange
        parent_ws = tmp_path / "persona-profile"
        parent_ws.mkdir()
        wallet_ws = tmp_path / "persona-wallet"
        wallet_ws.mkdir()
        wallet_manifest = {
            "layer_id": "persona-wallet",
            "entity_kind": "individual",
            "layer_role": "squad",
            "precedence": 88,
            "linked_nodes": [{"node_id": "sci-economic", "cockpit_url": "http://127.0.0.1:8720"}],
            "network_egress_policy": {"allowed_hosts": ["https://api.example.org"]},
        }
        corp_ws = tmp_path / "corp-dept"
        (corp_ws / "system").mkdir(parents=True)
        (corp_ws / "layers/sub-a").mkdir(parents=True)
        (corp_ws / "layers/.hidden").mkdir(parents=True)
        (corp_ws / "layers/readme.txt").write_text("x", "utf-8")
        (corp_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "corp-dept",
                    "entity_kind": "enterprise",
                    "layer_role": "department",
                    "precedence": 30,
                    "linked_nodes": [
                        "skip",
                        {"node_id": "empty", "cockpit_url": ""},
                        {"node_id": "peer-a", "cockpit_url": "http://127.0.0.1:8725"},
                        {"node_id": "peer-a", "cockpit_url": "http://127.0.0.1:8725"},
                    ],
                    "domain_governance": {"canonical_domain": "iso.example"},
                    "network_egress_policy": {
                        "allowed_hosts": [
                            "https://api.github.com",
                            "",
                            "https://api.github.com",
                            "https://cdn.iso.example",
                        ],
                        "enable_canonical_cdn": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        leaf_ws = tmp_path / "leaf-app"
        leaf_ws.mkdir()

        # Act
        w_perm = antigravity_sync.compile_antigravity_permissions(
            wallet_ws, manifest=wallet_manifest, parent_dir=parent_ws
        )
        c_perm = antigravity_sync.compile_antigravity_permissions(
            corp_ws, parent_dir=parent_ws, active_env="pro"
        )
        l_perm = antigravity_sync.sync_workspace_antigravity_surfaces(
            leaf_ws,
            active_templates=(),
            manifest={"layer_id": "leaf-app", "network_egress_policy": "invalid"},
            parent_dir=leaf_ws,
            dry_run=True,
        )
        pers_ws = tmp_path / "pers-sync"
        (pers_ws / ".agents/runtime").mkdir(parents=True)
        (pers_ws / ".agents/runtime/empty.json").write_text('{"environment": ""}', "utf-8")
        antigravity_sync.sync_workspace_antigravity_surfaces(
            pers_ws,
            active_templates=(),
            manifest={"layer_id": "pers-sync", "entity_kind": "individual", "precedence": 90},
        )
        (pers_ws / ".agents/runtime/active.json").write_text('{"environment": "dev"}', "utf-8")
        antigravity_sync.sync_workspace_antigravity_surfaces(
            pers_ws,
            active_templates=(),
            manifest={"layer_id": "pers-sync", "entity_kind": "individual", "precedence": 90},
        )
        antigravity_sync.sync_workspace_antigravity_surfaces(
            pers_ws,
            active_templates=(),
            manifest={"layer_id": "pers-sync", "entity_kind": "individual", "precedence": 90},
            active_env="pro",
        )

        # Assert
        assert w_perm["purpose_archetype"] == "wallet"
        assert w_perm["non_workspace_file_access"] == "deny"
        assert w_perm["internet_access_policy"] == "loopback-only"
        assert w_perm["auto_execution_policy"] == "review-driven"
        assert w_perm["read_only_grants"] == []
        assert w_perm["global_config_mutated"] is False
        assert c_perm["non_workspace_file_access"] == "1-hop-read-only"
        assert len(c_perm["read_only_grants"]) == 2
        assert c_perm["internet_access_policy"] == "curated-allowlist"
        assert c_perm["auto_execution_policy"] == "strict-review"
        assert "https://api.github.com" in c_perm["browser_allowlist"]
        assert c_perm["cdn_origins"] == ["https://cdn.iso.example"]
        assert "cdn.iso.example" in c_perm["allowed_egress_domains"]
        assert (corp_ws / constants.ANTIGRAVITY_PERMISSIONS_REL_PATH).is_file()
        assert l_perm == [
            constants.PLUGINS_MANIFEST_REL_PATH,
            constants.ANTIGRAVITY_PERMISSIONS_REL_PATH,
            constants.SIDECAR_MANIFEST_REL_PATH,
        ]
        assert not (leaf_ws / constants.ANTIGRAVITY_PERMISSIONS_REL_PATH).exists()
        assert not (leaf_ws / constants.SIDECAR_MANIFEST_REL_PATH).exists()
        pers_perm = json.loads(
            (pers_ws / constants.ANTIGRAVITY_PERMISSIONS_REL_PATH).read_text("utf-8")
        )
        assert pers_perm["environment"] == "pro"

    def test_register_antigravity_workspace_and_runtime_summary_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify missing-IDE fallback, idempotent workspaces.json, and runtime summary."""
        # Arrange
        ws = tmp_path / "node-iso"
        (ws / ".agents/runtime").mkdir(parents=True)
        (ws / "logs/ephemeral_forks/bot-1" / constants.NODE_MANIFEST_REL_PATH).parent.mkdir(
            parents=True
        )
        (ws / "logs/ephemeral_forks/bot-1" / constants.NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "bot-1"}), "utf-8"
        )
        (ws / ".agents/runtime/s.json").write_text(
            json.dumps(
                {
                    "plugin_id": "s",
                    "persistence_mode": "static",
                    "status": "active",
                    "daemon_active": True,
                    "daemon_pid": 999999,
                }
            ),
            "utf-8",
        )
        (ws / ".agents/runtime/p.json").write_text(
            json.dumps(
                {
                    "plugin_id": "p",
                    "persistence_mode": "static",
                    "status": "active",
                    "daemon_active": True,
                    "daemon_pid": 888888,
                }
            ),
            "utf-8",
        )
        (ws / ".agents/runtime/a.json").write_text(
            json.dumps(
                {
                    "plugin_id": "a",
                    "persistence_mode": "static",
                    "status": "active",
                    "daemon_active": True,
                    "daemon_pid": 777777,
                }
            ),
            "utf-8",
        )
        (ws / ".agents/runtime/d.json").write_text(
            json.dumps({"plugin_id": "d", "persistence_mode": "dynamic", "status": "active"}),
            "utf-8",
        )
        no_ag_home = tmp_path / "no-ag-home"
        no_ag_home.mkdir()
        dry_home = tmp_path / "dry-home"
        home = tmp_path / "home"

        def _fake_kill(pid: int, _sig: int) -> None:
            if pid == 999999:
                raise ProcessLookupError
            if pid == 888888:
                raise PermissionError

        # Act
        with patch("zcg.governance.workspace.antigravity_sync.Path.home", return_value=no_ag_home):
            unreg = antigravity_sync.register_antigravity_workspace(ws, home_dir=None)
        dry_res = antigravity_sync.register_antigravity_workspace(
            ws, home_dir=dry_home, dry_run=True
        )
        first = antigravity_sync.register_antigravity_workspace(ws, home_dir=home)
        second = antigravity_sync.register_antigravity_workspace(ws, home_dir=home)
        with patch("zcg.governance.workspace.antigravity_sync.os.kill", side_effect=_fake_kill):
            summary = antigravity_sync.summarize_runtime_orchestration(
                ws, {"layer_id": "node-iso", "federated_mcps": [{"id": "fed-1"}]}
            )
        fallback_sum = antigravity_sync.summarize_runtime_orchestration(tmp_path / "empty-ws")

        # Assert
        assert unreg["registered"] is False
        assert dry_res["registered"] is True and not Path(dry_res["workspaces_file"]).exists()
        assert second["registered"] is True
        assert json.loads(Path(first["workspaces_file"]).read_text("utf-8"))["workspaces"] == [
            str(ws.resolve())
        ]
        by_id = {p["plugin_id"]: p for p in summary["static_runtime"]["plugins"]}
        assert by_id["s"]["daemon_active"] is False and by_id["s"]["daemon_pid"] is None
        assert by_id["p"]["daemon_active"] is True and by_id["p"]["daemon_pid"] == 888888
        assert by_id["a"]["daemon_active"] is True and by_id["a"]["daemon_pid"] == 777777
        assert len(summary["static_runtime"]["mcps"]) == 2
        assert len(summary["dynamic_runtime"]["mcps"]) == 1
        assert len(summary["dynamic_runtime"]["plugins"]) == 1
        assert fallback_sum["static_runtime"]["plugins"] == []
