"""Unit tests for zcg.cockpit.lifecycle.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zcg.cockpit import lifecycle
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance import scaffolder


class TestLifecycle:
    """Verify runtime orchestration summary, daemon PID control, and plugin lifecycle actions."""

    def test_summarize_runtime_orchestration_and_daemon_control_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify static/dynamic runtime discovery and daemon start/stop/reuse paths."""
        # Arrange
        ws = tmp_path / "node-iso"
        (ws / ".agents/runtime").mkdir(parents=True)
        (ws / "logs/ephemeral_forks/bot-1" / NODE_MANIFEST_REL_PATH).parent.mkdir(parents=True)
        (ws / "logs/ephemeral_forks/bot-1" / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "bot-1"}), "utf-8"
        )
        (ws / ".agents/runtime/s.json").write_text(
            json.dumps({"plugin_id": "s", "persistence_mode": "static", "status": "active"}),
            "utf-8",
        )
        (ws / ".agents/runtime/d.json").write_text(
            json.dumps({"plugin_id": "d", "persistence_mode": "dynamic", "status": "active"}),
            "utf-8",
        )
        m = {"layer_id": "node-iso", "federated_mcps": [{"id": "fed-1"}]}

        # Act
        summary = lifecycle.summarize_runtime_orchestration(ws, m)
        assert len(summary["static_runtime"]["mcps"]) == 2
        assert len(summary["dynamic_runtime"]["mcps"]) == 1
        assert len(summary["dynamic_runtime"]["plugins"]) == 1

        # Daemon control: stop missing, stop dead PID, reuse live PID, spawn mocked Popen
        rt_file = ws / ".agents/runtime/p.json"
        assert lifecycle.manage_plugin_daemon(ws, rt_file, 8800, start=False, dry_run=False) == {
            "daemon_active": False,
            "daemon_pid": None,
        }
        rt_file.write_text(json.dumps({"daemon_pid": 99999}), "utf-8")
        with patch("zcg.cockpit.lifecycle.os.kill", side_effect=ProcessLookupError):
            lifecycle.manage_plugin_daemon(ws, rt_file, 8800, start=False, dry_run=False)
            pytest_d = lifecycle.manage_plugin_daemon(ws, rt_file, 8800, start=True, dry_run=False)
            assert pytest_d == {"daemon_active": True, "daemon_pid": None}

        with patch("zcg.cockpit.lifecycle.os.kill", return_value=None):
            reused = lifecycle.manage_plugin_daemon(ws, rt_file, 8800, start=True, dry_run=False)
        assert reused == {"daemon_active": True, "daemon_pid": 99999}

        rt_file.unlink()
        fake_proc = MagicMock(pid=4321)
        clean_env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("PYTEST_CURRENT_TEST", "ZCG_NO_DAEMON", "PYTHONPATH")
        }
        with (
            patch.dict("zcg.cockpit.lifecycle.os.environ", clean_env, clear=True),
            patch("zcg.cockpit.lifecycle.subprocess.Popen", return_value=fake_proc) as popen_d,
        ):
            spawned = lifecycle.manage_plugin_daemon(ws, rt_file, 8800, start=True, dry_run=False)
        with (
            patch.dict(
                "zcg.cockpit.lifecycle.os.environ",
                {**clean_env, "PYTHONPATH": str(tmp_path / "custom")},
                clear=True,
            ),
            patch("zcg.cockpit.lifecycle.subprocess.Popen", return_value=fake_proc),
        ):
            lifecycle.manage_plugin_daemon(
                ws, rt_file, 8800, start=True, dry_run=False, docs_mode="disabled"
            )
        # Assert
        assert spawned == {"daemon_active": True, "daemon_pid": 4321}
        assert "zcg.cockpit.asgi" in popen_d.call_args.args[0][2]

    def test_manage_plugin_service_guards_and_full_lifecycle_expected(self, tmp_path: Path) -> None:
        """Verify validation guards, env-gates, install..uninstall, assets, and browser hook."""
        # Arrange
        ws = tmp_path / "squad-iso"
        ws.mkdir()

        # Validation guards
        with pytest.raises(ValueError, match="Invalid action"):
            lifecycle.manage_plugin_service(ws, action="bad")
        with pytest.raises(ValueError, match="Invalid target_env"):
            lifecycle.manage_plugin_service(ws, action="activate", target_env="bad")
        with pytest.raises(ValueError, match="Invalid persistence_mode"):
            lifecycle.manage_plugin_service(ws, action="activate", persistence_mode="bad")
        with pytest.raises(ValueError, match="Invalid resolution_policy"):
            lifecycle.manage_plugin_service(ws, action="activate", resolution_policy="bad")
        with pytest.raises(ValueError, match="No plugin-stack runtime_service"):
            lifecycle.manage_plugin_service(ws, action="activate", plugin_id="missing-plug")

        # Parent holds custom plugin pack with assets & file-bound surfaces (.json & .md)
        parent = tmp_path / "corp-iso"
        scaffolder.scaffold_template_pack(parent, template_name="ops-cockpit", kind="plugin-stack")
        tj_p = parent / "templates/ops-cockpit/template.json"
        tj_d = json.loads(tj_p.read_text("utf-8"))
        tj_d["runtime_service"]["bound_surfaces"] = [
            "surfaces/web/",
            "surfaces/infra/cloud.json",
            "surfaces/notes.md",
        ]
        tj_p.write_text(json.dumps(tj_d), "utf-8")
        (parent / "templates/ops-cockpit/assets").mkdir(parents=True)
        (parent / "templates/ops-cockpit/assets/icon.svg").write_text("<svg/>", "utf-8")

        scaffolder.configure_node_manifest(ws, layer_id="squad-iso", layer_role="squad")
        m_path = ws / NODE_MANIFEST_REL_PATH
        m_data = json.loads(m_path.read_text("utf-8"))
        m_data["default_stack_templates"] = ["node-work-cockpit"]
        m_data["federated_mcps"] = [{"mcp_id": "fed-mcp"}]
        m_path.write_text(json.dumps(m_data), "utf-8")

        # Env-gate block vs pass on tst
        with (
            patch(
                "zcg.cockpit.lifecycle.evaluate_environment_promotion",
                return_value={"allowed": False, "failed_gates": ["DIRTY"]},
            ),
            pytest.raises(ValueError, match="PLUGIN_ENV_GATE_BLOCKED"),
        ):
            lifecycle.manage_plugin_service(
                ws, action="activate", plugin_id="node-work-cockpit", target_env="tst"
            )

        with patch(
            "zcg.cockpit.lifecycle.evaluate_environment_promotion",
            return_value={"allowed": True, "failed_gates": []},
        ):
            dry_act = lifecycle.manage_plugin_service(
                ws,
                action="activate",
                plugin_id="node-work-cockpit",
                target_env="tst",
                persistence_mode="dynamic",
                resolution_policy="",
                dry_run=True,
            )
        assert dry_act["resolution_policy"] == "goal-resolved"

        # Install custom plugin from parent, activate (with mocked browser), switch-env,
        # healthcheck, deactivate, teardown, and uninstall
        lifecycle.manage_plugin_service(
            ws, action="install", plugin_id="ops-cockpit", parent_dir=parent
        )
        # Idempotent re-install when template dir and manifest entry already exist
        lifecycle.manage_plugin_service(
            ws, action="install", plugin_id="ops-cockpit", parent_dir=parent
        )
        assert (ws / ".agents/assets/ops-cockpit/icon.svg").is_file()
        assert (ws / "surfaces/infra/cloud.json").is_file()
        assert (ws / "surfaces/notes.md").is_file()

        with (
            patch(
                "zcg.cockpit.lifecycle.manage_plugin_daemon",
                return_value={"daemon_active": True, "daemon_pid": 111},
            ),
            patch("zcg.cockpit.lifecycle.subprocess.Popen") as popen_mock,
        ):
            act_res = lifecycle.manage_plugin_service(ws, action="activate")
        popen_mock.assert_not_called()
        assert act_res["services"][0]["status"] == "active"
        assert act_res["services"][0]["intranet_topology"][
            "local_subdomain_dashboard_url"
        ].endswith("/dashboard")

        sw_res = lifecycle.manage_plugin_service(ws, action="switch-env")
        assert sw_res["services"][0]["daemon_active"] is True
        hz_doc = json.loads((ws / "surfaces/web/healthz").read_text("utf-8"))
        assert hz_doc["http_poll_stop_status"] == 286
        assert hz_doc["zones"] == ["Z1", "Z2", "Z3", "Z4"]
        assert hz_doc["health_regime"] == "OPTIMAL"

        lifecycle.manage_plugin_service(ws, action="healthcheck")
        deact = lifecycle.manage_plugin_service(ws, action="deactivate")
        assert deact["services"][0]["status"] == "inactive"

        lifecycle.manage_plugin_service(ws, action="teardown", dry_run=True)
        # Act
        uninst = lifecycle.manage_plugin_service(ws, action="uninstall")
        # Assert
        assert uninst["services"][0]["status"] == "uninstalled"

        # Unmanifested bare workspace provision (no assets/), healthcheck + uninstall
        bare = tmp_path / "bare-ws"
        bare.mkdir()
        empty_eng = tmp_path / "empty-eng"
        lifecycle.manage_plugin_service(
            bare, action="provision", plugin_id="node-work-cockpit", engine_dir=empty_eng
        )
        lifecycle.manage_plugin_service(
            bare, action="healthcheck", plugin_id="node-work-cockpit", engine_dir=empty_eng
        )
        lifecycle.manage_plugin_service(
            bare, action="uninstall", plugin_id="node-work-cockpit", engine_dir=empty_eng
        )
