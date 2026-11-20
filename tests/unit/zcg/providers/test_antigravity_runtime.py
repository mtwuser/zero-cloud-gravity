"""Unit tests for zcg.providers.antigravity_runtime.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import io
import json
import stat
import struct
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.providers import antigravity_runtime as agy_rt


def _build_asar(asar_path: Path, pkg_payload: dict[str, Any]) -> None:
    """Write a minimal valid Electron ASAR binary containing package.json."""
    pkg_bytes = json.dumps(pkg_payload).encode("utf-8")
    header_json = json.dumps(
        {"files": {"package.json": {"size": len(pkg_bytes), "offset": "0"}}}
    ).encode("utf-8")
    pad_len = (4 - (len(header_json) % 4)) % 4
    header_size = 8 + len(header_json) + pad_len
    prefix = struct.pack("<IIII", 4, header_size, header_size - 4, len(header_json))
    asar_path.parent.mkdir(parents=True, exist_ok=True)
    asar_path.write_bytes(prefix + header_json + (b"\x00" * pad_len) + pkg_bytes)


class TestAntigravityRuntime:
    """Verify deterministic SemVer parsing, bundle/CLI probing, and Wallet-airlocked checks."""

    def test_parse_semver_tuple_valid_and_invalid_inputs_expected(self) -> None:
        """Verify 2-segment, 3-segment, v-prefixed, prerelease, and malformed version strings."""
        # Arrange
        valid_cases = [
            ("2.33", (2, 33, 0)),
            ("2.32.1", (2, 32, 1)),
            ("v1.22.4", (1, 22, 4)),
            ("V3.4-beta.1+sha", (3, 4, 0)),
            (" 0.9.10+build.5 ", (0, 9, 10)),
        ]
        invalid_cases: list[str | None] = [None, "", "   ", "1", "1.2.3.4", "1.a.3", "v"]

        # Act
        parsed_valid = [agy_rt.parse_semver_tuple(raw) for raw, _ in valid_cases]
        parsed_invalid = [agy_rt.parse_semver_tuple(bad) for bad in invalid_cases]

        # Assert
        assert parsed_valid == [exp for _, exp in valid_cases]
        assert all(item is None for item in parsed_invalid)

    def test_read_installed_bundle_version_precedence_and_asar_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify marker, product/package JSON, and app.asar precedence plus corrupt guards."""
        # Arrange
        b_dir = tmp_path / "bundle"
        b_dir.mkdir()

        # Act — empty bundle
        assert agy_rt.read_installed_bundle_version(b_dir) is None

        # 1. Corrupt & truncated app.asar return None
        asar = b_dir / "resources/app.asar"
        asar.parent.mkdir(parents=True)
        asar.write_bytes(b"short")
        assert agy_rt.read_installed_bundle_version(b_dir) is None
        asar.write_bytes(struct.pack("<IIII", 4, 20, 16, 10) + b"not-json!!")
        assert agy_rt.read_installed_bundle_version(b_dir) is None

        # 2. Valid ASAR with empty version -> None, then valid version -> parsed
        _build_asar(asar, {"version": ""})
        assert agy_rt.read_installed_bundle_version(b_dir) is None
        _build_asar(asar, {"version": "2.32.1"})
        assert agy_rt.read_installed_bundle_version(b_dir) == "2.32.1"

        # 3. package.json takes precedence over app.asar (and handles invalid JSON / non-dict)
        pkg = b_dir / "resources/app/package.json"
        pkg.parent.mkdir(parents=True)
        pkg.write_text("{bad-json", encoding="utf-8")
        assert agy_rt.read_installed_bundle_version(b_dir) == "2.32.1"
        pkg.write_text("[]", encoding="utf-8")
        assert agy_rt.read_installed_bundle_version(b_dir) == "2.32.1"
        pkg.write_text(json.dumps({"version": "2.33.0"}), encoding="utf-8")
        assert agy_rt.read_installed_bundle_version(b_dir) == "2.33.0"

        # 4. product.json takes precedence over package.json
        prod = b_dir / "resources/app/product.json"
        prod.write_text(json.dumps({"ideVersion": "1.22.5"}), encoding="utf-8")
        assert agy_rt.read_installed_bundle_version(b_dir) == "1.22.5"

        # 5. .installed-version takes precedence (blank or OSError falls through)
        marker = b_dir / ".installed-version"
        marker.write_text("   \n", encoding="utf-8")
        assert agy_rt.read_installed_bundle_version(b_dir) == "1.22.5"
        with patch.object(
            Path, "read_text", side_effect=[OSError("perm"), '{"ideVersion":"1.22.5"}']
        ):
            assert agy_rt.read_installed_bundle_version(b_dir) == "1.22.5"
        marker.write_text("2.34.0\n", encoding="utf-8")

        # Assert
        assert agy_rt.read_installed_bundle_version(b_dir) == "2.34.0"

    def test_inspect_local_antigravity_runtime_workstation_wallet_and_cli_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify local inspection across workstation, bare, wallet, and CLI failure modes."""
        # Arrange
        home = tmp_path / "home"
        (home / ".gemini/config/skills/sopen").mkdir(parents=True)
        (home / ".gemini/config/AGENTS.md").write_text("# ZeroCloudGravity\n", encoding="utf-8")
        (home / ".gemini/config/skills/sopen/SKILL.md").write_text("# sopen\n", encoding="utf-8")

        eng = tmp_path / "engine"
        eng.mkdir()
        agents = tmp_path / "agents"
        (agents / ".installed-version").parent.mkdir(parents=True)
        (agents / ".installed-version").write_text("2.32.1\n", encoding="utf-8")
        ide = tmp_path / "ide"
        ide.mkdir()
        cli = home / ".local/bin/agy"
        cli.parent.mkdir(parents=True)
        cli.write_text("#!/bin/sh\necho '2.33.0 build'\n", encoding="utf-8")
        cli.chmod(cli.stat().st_mode | stat.S_IXUSR)

        ws = tmp_path / "persona-profile"
        (ws / NODE_MANIFEST_REL_PATH).parent.mkdir(parents=True)
        (ws / NODE_MANIFEST_REL_PATH).write_text(
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
        (ws / "Makefile").write_text("workstation-update-agy:\n\t@true\n", encoding="utf-8")
        (ws / ".agents/rules").mkdir(parents=True)
        (ws / ".agents/rules/r1.md").write_text("# R1\n", encoding="utf-8")
        (ws / ".agents/skills/sk1").mkdir(parents=True)
        (ws / ".agents/skills/sk1/SKILL.md").write_text("# SK1\n", encoding="utf-8")
        (ws / ".agents/skills.json").write_text(
            json.dumps({"enabled_skills": ["sopen", "sclose"]}), encoding="utf-8"
        )
        (ws / ".agents/sidecar.json").write_text("{}\n", encoding="utf-8")
        (ws / ".zcg/runtime").mkdir(parents=True)
        (ws / ".zcg/runtime/session_pin.json").write_text("{}\n", encoding="utf-8")

        # Act
        rt = agy_rt.inspect_local_antigravity_runtime(
            ws, agents_dir=agents, ide_dir=ide, home_dir=home, engine_dir=eng
        )

        # Assert — workstation with Stow, agents + cli installed
        assert rt["contract_rev"] == agy_rt.ANTIGRAVITY_RUNTIME_CONTRACT_REV
        assert rt["any_installed"] is True
        assert rt["online_checks_allowed"] is True
        assert rt["home_stow_coupled"] is True
        assert rt["components"]["agents"]["version"] == "2.32.1"
        assert rt["components"]["cli"]["version"] == "2.33.0"
        assert rt["components"]["ide"]["installed"] is False
        assert rt["workspace_projection"] == {
            "rules_count": 1,
            "skills_count": 3,
            "has_session_pin": True,
            "has_sidecar": True,
        }
        (ws / ".agents/skills.json").write_text("{corrupt", encoding="utf-8")
        rt_corrupt_sk = agy_rt.inspect_local_antigravity_runtime(
            ws, agents_dir=agents, ide_dir=ide, home_dir=home, engine_dir=eng
        )
        assert rt_corrupt_sk["workspace_projection"]["skills_count"] == 1
        assert rt["commands"]["update_agents"] == "make workstation-update-agy"
        assert rt["commands"]["workspace_path"] == str(ws.resolve())
        assert rt["commands"]["open_workspace"] == f"cd {ws.resolve()} && agy"

        # Act — Wallet airlock workspace + CLI failure modes (non-zero, empty stdout, OSError)
        wallet = tmp_path / "persona-wallet"
        (wallet / NODE_MANIFEST_REL_PATH).parent.mkdir(parents=True)
        (wallet / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-wallet",
                    "layer_role": "squad",
                    "entity_kind": "individual",
                    "precedence": 88,
                    "personal_pillar": "wallet",
                }
            ),
            encoding="utf-8",
        )
        with patch(
            "zcg.providers.antigravity_runtime.subprocess.run",
            side_effect=OSError("exec fail"),
        ):
            w_rt = agy_rt.inspect_local_antigravity_runtime(
                wallet,
                agents_dir=tmp_path / "missing-a",
                ide_dir=tmp_path / "missing-i",
                cli_bin=cli,
                home_dir=tmp_path / "bare-home",
                engine_dir=eng,
            )
        assert w_rt["online_checks_allowed"] is False
        assert w_rt["any_installed"] is False
        assert w_rt["home_stow_coupled"] is False
        assert w_rt["commands"]["update_agents"].endswith("scripts/install-antigravity.sh --agents")

        bad_rc = subprocess.CompletedProcess([str(cli), "--version"], 1, stdout="", stderr="err")
        empty_ok = subprocess.CompletedProcess(
            [str(cli), "--version"], 0, stdout="   \n", stderr=""
        )
        with patch(
            "zcg.providers.antigravity_runtime.subprocess.run", side_effect=[bad_rc, empty_ok]
        ):
            assert agy_rt._read_cli_version(cli) is None
            assert agy_rt._read_cli_version(cli) is None
        assert agy_rt._read_cli_version(tmp_path / "nonexistent-cli") is None

    def test_check_antigravity_online_releases_airlock_statuses_and_https_guard_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Wallet airlock block, all 4 component statuses, and HTTPS-only default fetcher."""
        # Arrange
        ws = tmp_path / "node-iso"
        ws.mkdir()

        # Act — 1. Wallet airlock blocks online checks
        blocked = agy_rt.check_antigravity_online_releases(
            ws, local_runtime={"online_checks_allowed": False}
        )
        assert blocked == {
            "checked": False,
            "reason": "WALLET_AIRLOCK_OFFLINE",
            "updates_available": False,
            "components": {},
        }

        # 2. All statuses: update-available, up-to-date, not-installed
        local_rt = {
            "online_checks_allowed": True,
            "components": {
                "agents": {"version": "2.31.0"},
                "cli": {"version": "2.33.0"},
                "ide": {"version": None},
            },
        }

        def _fake_fetch(url: str, _timeout: float) -> Any:
            if url == agy_rt.HUB_RELEASES_URL:
                return [{"version": "2.32.1"}]
            if url == agy_rt.CLI_MANIFEST_URL:
                return {"version": "2.33.0"}
            return [{"version": "1.22.0"}]

        res = agy_rt.check_antigravity_online_releases(
            ws, local_runtime=local_rt, fetch_json=_fake_fetch
        )
        assert res["checked"] is True
        assert res["reason"] == "OK"
        assert res["updates_available"] is True
        assert res["components"]["agents"]["status"] == "update-available"
        assert res["components"]["agents"]["update_available"] is True
        assert res["components"]["cli"]["status"] == "up-to-date"
        assert res["components"]["ide"]["status"] == "not-installed"

        # 3. Unreachable / malformed payloads and non-mapping local_runtime components
        def _bad_fetch(url: str, _timeout: float) -> Any:
            if url == agy_rt.HUB_RELEASES_URL:
                raise OSError("offline")
            if url == agy_rt.CLI_MANIFEST_URL:
                return {"version": 123}
            return []

        unreach = agy_rt.check_antigravity_online_releases(
            ws,
            local_runtime={"online_checks_allowed": True, "components": "invalid"},
            fetch_json=_bad_fetch,
        )
        assert unreach["updates_available"] is False
        assert all(c["status"] == "unreachable" for c in unreach["components"].values())

        # 4. Default HTTPS fetcher guard & urlopen path + local_runtime=None probe
        with pytest.raises(ValueError, match="Only HTTPS"):
            agy_rt._default_fetch_json("http://example.invalid/releases", 1.0)

        def _fake_urlopen(url: str, timeout: float = 3.0) -> io.BytesIO:
            _ = timeout
            if url == agy_rt.CLI_MANIFEST_URL:
                return io.BytesIO(b'{"version": "2.33.0"}')
            return io.BytesIO(b'[{"version": "2.32.1"}]')

        with (
            patch(
                "zcg.providers.antigravity_runtime.inspect_local_antigravity_runtime",
                return_value={
                    "online_checks_allowed": True,
                    "components": {"agents": "bad-entry"},
                },
            ),
            patch(
                "zcg.providers.antigravity_runtime.urllib.request.urlopen",
                side_effect=_fake_urlopen,
            ),
        ):
            via_default = agy_rt.check_antigravity_online_releases(ws)

        # Assert
        assert via_default["checked"] is True
        assert via_default["components"]["agents"]["status"] == "not-installed"
        assert via_default["components"]["cli"]["latest_version"] == "2.33.0"
