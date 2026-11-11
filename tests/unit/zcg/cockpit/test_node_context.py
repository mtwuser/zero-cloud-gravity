"""Unit tests for zcg.cockpit.node_context.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from zcg.cockpit import node_context


class TestNodeContext:
    """Verify Sovereign Exposure Posture, Node Passport sanitization, branches, and links."""

    def test_read_json_dict_and_exposure_postures_across_quadrants_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify missing/array/object JSON reads and all four ExposurePosture classifications."""
        # Arrange
        arr_file = tmp_path / "arr.json"
        obj_file = tmp_path / "obj.json"
        arr_file.write_text("[1, 2]\n", encoding="utf-8")
        obj_file.write_text('{"layer_id": "node-a"}\n', encoding="utf-8")

        # Act
        missing = node_context.read_json_dict(tmp_path / "missing.json")
        from_arr = node_context.read_json_dict(arr_file)
        from_obj = node_context.read_json_dict(obj_file)
        pub_live = node_context.classify_exposure_posture(
            {"layer_role": "knowledge", "visibility": "public"}, active_env="pro"
        )
        pub_prev = node_context.classify_exposure_posture(
            {"layer_role": "knowledge", "visibility": "public"}, active_env="  "
        )
        priv_ind = node_context.classify_exposure_posture(
            {"entity_kind": "individual", "precedence": 90}, active_env="pro"
        )
        priv_ent = node_context.classify_exposure_posture(
            {"entity_kind": "enterprise", "layer_role": "department", "precedence": 25},
            active_env="pro",
        )

        # Assert
        assert missing == {}
        assert from_arr == {}
        assert from_obj == {"layer_id": "node-a"}
        assert pub_live["posture"] == "public-live"
        assert pub_prev["posture"] == "public-preview"
        assert priv_ind["posture"] == "private-personal"
        assert priv_ent["posture"] == "private-intranet"

    def test_build_cockpit_passport_data_sanitizes_public_pro_vs_internal_expected(self) -> None:
        """Verify public+pro strips internal sprint tasks and private sibling fleet entries."""
        # Arrange
        scopes: dict[str, dict[str, Any]] = {
            "node": {
                "own_node_ledger": {
                    "total_open_items": 1,
                    "active_node_tasks": ["Internal roadmap task"],
                }
            },
            "network": {
                "inter_layer_exchange": {},
                "network_representation_links": {
                    "parent_home_node": {"node_id": "corp-alpha"},
                    "lateral_peers": [{"node_id": "dept-secret"}],
                },
            },
            "federation": {
                "mounted_layers": [{"layer_id": "sci-maths"}],
                "fleet_plugin_inventory": [
                    {"workspace_id": "org-alpha", "plugin_id": "portal"},
                    {"workspace_id": "dept-secret", "plugin_id": "internal"},
                ],
            },
        }
        pub_state = {
            "plugin_id": "portal",
            "environment": "pro",
            "intranet_topology": {
                "visibility": "public",
                "localhost_url": "http://127.0.0.1:8720/?env=pro",
            },
        }
        priv_state = {
            "plugin_id": "node-work-cockpit",
            "environment": "dev",
            "intranet_topology": {
                "visibility": "private",
                "localhost_url": "http://127.0.0.1:8725/?env=dev",
            },
        }

        # Act
        pub_pass = node_context.build_cockpit_passport_data(
            "org-alpha", {"layer_role": "knowledge"}, pub_state, scopes
        )
        priv_op = node_context.build_cockpit_passport_data(
            "dept-tech", {"layer_role": "department"}, priv_state, scopes
        )

        # Assert
        assert pub_pass["cockpit_posture"] == "public-passport"
        assert pub_pass["data_scopes"]["node"]["own_node_ledger"]["active_node_tasks"] == []
        assert (
            pub_pass["data_scopes"]["network"]["network_representation_links"]["lateral_peers"]
            == []
        )
        assert len(pub_pass["data_scopes"]["federation"]["fleet_plugin_inventory"]) == 1
        assert "zcg link" in " ".join(pub_pass["remote_session_commands"])
        assert priv_op["cockpit_posture"] == "internal-operator"
        assert priv_op["data_scopes"]["node"]["own_node_ledger"]["active_node_tasks"] == [
            "Internal roadmap task"
        ]
        assert len(priv_op["data_scopes"]["federation"]["fleet_plugin_inventory"]) == 2

    def test_inspect_context_branches_for_git_and_non_git_workspaces_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify git ref parsing across active/created/blueprint/extra tracks and non-git dirs."""
        # Arrange
        non_git = tmp_path / "plain"
        non_git.mkdir()
        git_ws = tmp_path / "git-ws"
        (git_ws / ".git").mkdir(parents=True)
        fake_res = MagicMock(spec=subprocess.CompletedProcess)
        fake_res.stdout = "\nmaster| \nspecialty/maths|*\nspecialty/physics| \ncustom/lab| \n"

        # Act
        plain_info = node_context.inspect_context_branches(non_git, view_archetype="unknown-role")
        with (
            patch("zcg.cockpit.node_context.shutil.which", return_value="/usr/bin/git"),
            patch("zcg.cockpit.node_context.subprocess.run", return_value=fake_res),
        ):
            git_info = node_context.inspect_context_branches(
                git_ws, view_archetype="academic-tutor-cockpit"
            )

        # Assert
        assert plain_info["active_branch"] == "master"
        assert plain_info["local_branches"] == ["master"]
        assert git_info["active_branch"] == "specialty/maths"
        by_name = {t["branch"]: t["status"] for t in git_info["tracks"]}
        assert by_name["specialty/maths"] == "active"
        assert by_name["specialty/physics"] == "created"
        assert by_name["specialty/biology"] == "blueprint"
        assert by_name["custom/lab"] == "created"

    def test_host_knowledge_and_cross_node_collectors_expected(self, tmp_path: Path) -> None:
        """Verify host Stow root detection, knowledge registry deduping, and directional links."""
        # Arrange
        empty_ws = tmp_path / "empty-ws"
        empty_ws.mkdir()
        rich_ws = tmp_path / "rich-ws"
        (rich_ws / "bash").mkdir(parents=True)
        (rich_ws / "docs").mkdir(parents=True)
        (rich_ws / "docs/guide.md").write_text("# Guide\n", encoding="utf-8")
        manifest = {
            "global_profile": "technical",
            "interaction_language": "es",
            "public_knowledge_registry": {
                "sci-maths": {"stewardship_stage": "active", "public_url": "https://m.local"},
                "sci-physics": {"stewardship_stage": "certified", "public_url": "https://p.local"},
                "invalid": "not-a-dict",
            },
            "linked_nodes": [
                {
                    "node_id": "sci-biology",
                    "relation": "knowledge-feed",
                    "layer_role": "knowledge",
                    "cockpit_url": "http://127.0.0.1:8720",
                },
                {"node_id": "sci-maths", "relation": "knowledge-feed", "layer_role": "knowledge"},
                {"node_id": "corp-a", "relation": "b2b-collaboration", "layer_role": "corporate"},
            ],
        }
        fed_sc = {
            "intranet_topology": {"localhost_url": "http://127.0.0.1:8710/?env=dev"},
            "mounted_layers": [
                {"layer_id": "sci-maths", "stewardship_stage": "mounted", "active_endpoint": "m"},
                {"layer_id": "local-pack", "stewardship_stage": "local", "active_endpoint": ""},
                "skip-non-dict",
            ],
            "fleet_plugin_inventory": [
                {
                    "workspace_id": "self-dir",
                    "workspace_path": ".",
                    "localhost_url": "http://127.0.0.1:8710/?env=dev",
                },
                {
                    "workspace_id": "dept-b",
                    "workspace_path": "dept-b",
                    "localhost_url": "http://127.0.0.1:8722/?env=dev",
                },
                {"workspace_id": "org-fleet", "localhost_url": "http://127.0.0.1:8720/?env=pro"},
                {"workspace_id": "fleet-1", "localhost_url": "http://127.0.0.1:8750/?env=dev"},
                {"workspace_id": "", "localhost_url": ""},
                "skip-str",
            ],
        }
        net_sc = {
            "network_representation_links": {
                "parent_home_node": {
                    "node_id": "root-0",
                    "layer_role": "workstation",
                    "cockpit_url": "http://127.0.0.1:8790",
                },
                "downward_child_nodes": [
                    {
                        "node_id": "proj-1",
                        "layer_role": "project",
                        "cockpit_url": "http://127.0.0.1:8780",
                    },
                    "skip",
                ],
                "lateral_peers": [
                    {
                        "node_id": "dept-b",
                        "layer_role": "department",
                        "cockpit_url": "http://127.0.0.1:8725",
                    },
                    "skip",
                ],
                "linked_nodes": [
                    {
                        "node_id": "org-pub",
                        "relation": "hr-process",
                        "layer_role": "knowledge",
                        "cockpit_url": "http://127.0.0.1:8720",
                    },
                    "skip",
                ],
            }
        }

        # Act
        h_empty = node_context.collect_workstation_host_summary(empty_ws, {})
        h_rich = node_context.collect_workstation_host_summary(rich_ws, manifest)
        kc_empty = node_context.collect_knowledge_connections(empty_ws, {}, {})
        kc_rich = node_context.collect_knowledge_connections(rich_ws, manifest, fed_sc)
        links_none = node_context.build_cross_node_links("self-id", {}, {})
        links_full = node_context.build_cross_node_links("self-id", net_sc, fed_sc)

        # Assert
        assert h_empty["governed_host_roots"] == ["system"]
        assert h_rich["governed_host_roots"] == ["bash"]
        assert kc_empty == {"mounts": [], "study_guides": []}
        assert [m["layer_id"] for m in kc_rich["mounts"]] == [
            "sci-maths",
            "local-pack",
            "sci-physics",
            "sci-biology",
        ]
        assert [m["kind"] for m in kc_rich["mounts"]] == [
            "corpus",
            "local-mount",
            "corpus",
            "live-node",
        ]
        assert kc_rich["study_guides"] == ["docs/guide.md"]
        assert links_none == []
        assert len(links_full) == 6
        scopes = {it["node_id"]: it["scope_tag"] for it in links_full}
        urls = {it["node_id"]: it["url"] for it in links_full}
        assert "self-dir" not in scopes
        assert scopes["root-0"] == "Private Local"
        assert scopes["proj-1"] == "Private Local"
        assert scopes["dept-b"] == "Private/Intranet"
        assert urls["dept-b"] == "http://dev.dept-b.self-id.localhost:8722/dashboard"
        assert scopes["org-pub"] == "Public/Corpus"
        assert scopes["org-fleet"] == "Public/Corpus"
        assert (
            json.loads(json.dumps(links_full))[0]["url"]
            == "http://dev.root-0.localhost:8790/dashboard"
        )
