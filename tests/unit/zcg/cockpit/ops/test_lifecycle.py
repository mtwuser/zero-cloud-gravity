"""Unit tests for zcg.cockpit.ops.lifecycle.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import io
import json
import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zcg.cockpit.ops import lifecycle
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance.workspace import scaffolder
from zcg.web.ui.static_files import CURRENT_ENGINE_ASSET_DIGEST


class TestLifecycle:
    """Verify daemon PID control and plugin lifecycle actions."""

    def test_manage_plugin_daemon_control_expected(self, tmp_path: Path) -> None:
        """Verify daemon start/stop/reuse and subprocess Popen paths."""
        # Arrange
        ws = tmp_path / "node-iso"
        (ws / ".agents/runtime").mkdir(parents=True)

        # Act — Daemon control: stop missing, stop dead PID, reuse live PID, spawn mocked Popen
        rt_file = ws / ".agents/runtime/p.json"
        assert lifecycle.manage_plugin_daemon(ws, rt_file, 8800, start=False, dry_run=False) == {
            "daemon_active": False,
            "daemon_pid": None,
        }
        rt_file.write_text(json.dumps({"daemon_pid": 99999}), "utf-8")
        with patch("zcg.cockpit.ops.lifecycle.os.kill", side_effect=ProcessLookupError):
            lifecycle.manage_plugin_daemon(ws, rt_file, 8800, start=False, dry_run=False)
            pytest_d = lifecycle.manage_plugin_daemon(ws, rt_file, 8800, start=True, dry_run=False)
            assert pytest_d == {"daemon_active": True, "daemon_pid": None}

        with patch("zcg.cockpit.ops.lifecycle.os.kill", return_value=None):
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
            patch.dict("zcg.cockpit.ops.lifecycle.os.environ", clean_env, clear=True),
            patch("zcg.cockpit.ops.lifecycle.subprocess.Popen", return_value=fake_proc) as popen_d,
        ):
            spawned = lifecycle.manage_plugin_daemon(ws, rt_file, 8800, start=True, dry_run=False)
        with (
            patch.dict(
                "zcg.cockpit.ops.lifecycle.os.environ",
                {**clean_env, "PYTHONPATH": str(tmp_path / "custom")},
                clear=True,
            ),
            patch("zcg.cockpit.ops.lifecycle.subprocess.Popen", return_value=fake_proc),
        ):
            lifecycle.manage_plugin_daemon(
                ws, rt_file, 8800, start=True, dry_run=False, docs_mode="disabled"
            )
        # Assert
        assert spawned == {"daemon_active": True, "daemon_pid": 4321}
        assert "zcg.cockpit.ops.asgi" in popen_d.call_args.args[0][2]

    def test_manage_plugin_daemon_port_ownership_and_conflict_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify /healthz layer+digest reuse, stale/force SIGTERM rotation, and conflict errors."""
        # Arrange
        ws = tmp_path / "node-iso"
        (ws / ".agents/runtime").mkdir(parents=True)
        rt_file = ws / ".agents/runtime/p.json"
        rt_file.write_text(json.dumps({"daemon_pid": 7777}), "utf-8")
        cur_dig = CURRENT_ENGINE_ASSET_DIGEST

        def _fake_urlopen(payload: bytes) -> MagicMock:
            cm = MagicMock()
            cm.__enter__.return_value = io.BytesIO(payload)
            cm.__exit__.return_value = False
            return cm

        # Act
        with patch(
            "zcg.cockpit.ops.lifecycle.urlopen",
            return_value=_fake_urlopen(
                json.dumps({"layer_id": "node-iso", "engine_asset_digest": cur_dig}).encode("utf-8")
            ),
        ):
            ok_probe = lifecycle._probe_daemon_healthz(8801)
        with patch("zcg.cockpit.ops.lifecycle.urlopen", return_value=_fake_urlopen(b"[]")):
            empty_probe = lifecycle._probe_daemon_healthz(8801)
        with patch("zcg.cockpit.ops.lifecycle.urlopen", side_effect=OSError("refused")):
            err_probe = lifecycle._probe_daemon_healthz(8801)
        with patch("zcg.cockpit.ops.lifecycle.os.kill", side_effect=ProcessLookupError):
            lifecycle._wait_pid_exit(7777, timeout_sec=0.05)
        with (
            patch("zcg.cockpit.ops.lifecycle.os.kill", return_value=None),
            patch("zcg.cockpit.ops.lifecycle.time.sleep", return_value=None),
            patch("zcg.cockpit.ops.lifecycle.time.monotonic", side_effect=[0.0, 0.0, 1.0]),
        ):
            lifecycle._wait_pid_exit(7777, timeout_sec=0.5)
        with (
            patch("zcg.cockpit.ops.lifecycle.os.kill", return_value=None),
            patch(
                "zcg.cockpit.ops.lifecycle._probe_daemon_healthz",
                return_value=("node-iso", cur_dig),
            ),
        ):
            reused = lifecycle.manage_plugin_daemon(
                ws, rt_file, 8801, start=True, dry_run=False, expected_layer_id="node-iso"
            )
        kill_calls: list[tuple[int, int]] = []
        with (
            patch(
                "zcg.cockpit.ops.lifecycle.os.kill",
                side_effect=lambda pid, sig: kill_calls.append((pid, sig)),
            ),
            patch(
                "zcg.cockpit.ops.lifecycle._probe_daemon_healthz",
                return_value=("node-iso", "stale0000000"),
            ),
        ):
            rotated_stale = lifecycle.manage_plugin_daemon(
                ws, rt_file, 8802, start=True, dry_run=False, expected_layer_id="node-iso"
            )
        clean_env = {
            k: v for k, v in os.environ.items() if k not in ("PYTEST_CURRENT_TEST", "ZCG_NO_DAEMON")
        }
        fake_proc = MagicMock(pid=8888)
        with (
            patch.dict("zcg.cockpit.ops.lifecycle.os.environ", clean_env, clear=True),
            patch("zcg.cockpit.ops.lifecycle.os.kill", return_value=None),
            patch("zcg.cockpit.ops.lifecycle._wait_pid_exit") as wait_mock,
            patch(
                "zcg.cockpit.ops.lifecycle._probe_daemon_healthz",
                return_value=("node-iso", cur_dig),
            ),
            patch("zcg.cockpit.ops.lifecycle.subprocess.Popen", return_value=fake_proc),
        ):
            forced = lifecycle.manage_plugin_daemon(
                ws,
                rt_file,
                8803,
                start=True,
                dry_run=False,
                expected_layer_id="node-iso",
                force_restart=True,
            )
        rt_file.unlink()
        with (
            patch.dict("zcg.cockpit.ops.lifecycle.os.environ", clean_env, clear=True),
            patch(
                "zcg.cockpit.ops.lifecycle._probe_daemon_healthz",
                return_value=("node-iso", cur_dig),
            ),
            patch("zcg.cockpit.ops.lifecycle.subprocess.Popen", return_value=fake_proc),
        ):
            same_lid = lifecycle.manage_plugin_daemon(
                ws, rt_file, 8803, start=True, dry_run=False, expected_layer_id="node-iso"
            )
        with (
            patch.dict("zcg.cockpit.ops.lifecycle.os.environ", clean_env, clear=True),
            patch(
                "zcg.cockpit.ops.lifecycle._probe_daemon_healthz",
                return_value=("foreign-node", cur_dig),
            ),
            pytest.raises(ValueError, match="COCKPIT_PORT_CONFLICT"),
        ):
            lifecycle.manage_plugin_daemon(
                ws, rt_file, 8803, start=True, dry_run=False, expected_layer_id="node-iso"
            )

        # Assert
        assert ok_probe == ("node-iso", cur_dig)
        assert empty_probe == (None, "") and err_probe == (None, "")
        assert reused == {"daemon_active": True, "daemon_pid": 7777}
        assert (7777, signal.SIGTERM) in kill_calls
        assert rotated_stale == {"daemon_active": True, "daemon_pid": None}
        wait_mock.assert_called_once_with(7777)
        assert forced == {"daemon_active": True, "daemon_pid": 8888}
        assert same_lid == {"daemon_active": True, "daemon_pid": 8888}

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
        m_data["cloud_deployment"] = {"project_id": "iso-gcp-01"}
        m_data["container_deployment"] = {"reverse_proxy": "caddy"}
        m_path.write_text(json.dumps(m_data), "utf-8")

        # Env-gate block vs pass on tst
        with (
            patch(
                "zcg.cockpit.ops.lifecycle.evaluate_environment_promotion",
                return_value={"allowed": False, "failed_gates": ["DIRTY"]},
            ),
            pytest.raises(ValueError, match="PLUGIN_ENV_GATE_BLOCKED"),
        ):
            lifecycle.manage_plugin_service(
                ws, action="activate", plugin_id="node-work-cockpit", target_env="tst"
            )

        with patch(
            "zcg.cockpit.ops.lifecycle.evaluate_environment_promotion",
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
        bad_parent = tmp_path / "bad-corp-iso"
        scaffolder.scaffold_template_pack(
            bad_parent, template_name="bad-cockpit", kind="plugin-stack"
        )
        (bad_parent / "templates/bad-cockpit/skills/bad-sk").mkdir(parents=True)
        (bad_parent / "templates/bad-cockpit/skills/bad-sk/SKILL.md").write_text(
            "---\nname: bad-sk\ndescription: Bad\u202e\n---\n# Hazard\n", "utf-8"
        )
        with pytest.raises(ValueError, match="SKILL_SECURITY_VIOLATION"):
            lifecycle.manage_plugin_service(
                ws, action="install", plugin_id="bad-cockpit", parent_dir=bad_parent
            )
        lifecycle.manage_plugin_service(
            ws, action="install", plugin_id="ops-cockpit", parent_dir=parent
        )
        # Idempotent re-install when template dir and manifest entry already exist
        lifecycle.manage_plugin_service(
            ws, action="install", plugin_id="ops-cockpit", parent_dir=parent
        )
        assert (ws / ".agents/assets/ops-cockpit/icon.svg").is_file()
        assert (ws / "surfaces/infra/cloud.json").is_file()
        assert (ws / "surfaces/infra/cloud_deployment_dev.json").is_file()
        assert (ws / "surfaces/infra/container_deployment_dev.json").is_file()
        assert (ws / "surfaces/notes.md").is_file()

        with (
            patch(
                "zcg.cockpit.ops.lifecycle.manage_plugin_daemon",
                return_value={"daemon_active": True, "daemon_pid": 111},
            ),
            patch("zcg.cockpit.ops.lifecycle.subprocess.Popen") as popen_mock,
        ):
            act_res = lifecycle.manage_plugin_service(ws, action="activate", actor_email="")
            auto_env_res = lifecycle.manage_plugin_service(
                ws, action="provision", target_env="", actor_email=""
            )
        popen_mock.assert_not_called()
        assert auto_env_res["environment"] == "dev"
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
        auto_en = lifecycle.manage_plugin_service(ws, action="enable-autostart", dry_run=True)
        assert auto_en["services"][0]["boot_autostart"]["enabled"] is True
        auto_dis = lifecycle.manage_plugin_service(ws, action="disable-autostart", dry_run=True)
        assert auto_dis["services"][0]["boot_autostart"]["enabled"] is False
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
