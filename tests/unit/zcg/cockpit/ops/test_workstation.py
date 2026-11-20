"""Unit tests for zcg.cockpit.ops.workstation.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.cockpit.ops import workstation
from zcg.core.constants import NODE_MANIFEST_REL_PATH


def _seed_profile_templates(repo_dir: Path) -> None:
    ub = repo_dir / "templates/context-stack/universal-base/rules"
    ab = repo_dir / "templates/context-stack/academic-base/rules"
    ub.mkdir(parents=True, exist_ok=True)
    ab.mkdir(parents=True, exist_ok=True)
    (ub / "universal-base.md").write_text(
        "---\ntrigger: always_on\n---\n# Universal Rules\n- Interaction Language: English (en)\n",
        encoding="utf-8",
    )
    (ab / "academic-base.md").write_text(
        "# Academic Header\n> Epistemic baseline\n---\n## Mastery Gates\n- Rigor.\n",
        encoding="utf-8",
    )


class TestWorkstation:
    """Verify global AGENTS.md composition and Antigravity workstation stow sync."""

    def test_set_global_agents_profile_composition_stow_and_budget_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify profile/lang validation, frontmatter stripping, stow, MCP link, and cap."""
        # Arrange
        repo = tmp_path / "ws-tower"
        home = tmp_path / "home"
        repo.mkdir()

        # Act — validation errors
        with pytest.raises(ValueError, match="Invalid global profile"):
            workstation.set_global_agents_profile(repo, "bad-profile")
        with pytest.raises(ValueError, match="Invalid interaction_language"):
            workstation.set_global_agents_profile(repo, "universal-base", interaction_language="xx")
        with pytest.raises(ValueError, match="Missing profile template rule file"):
            workstation.set_global_agents_profile(repo, "universal-base")

        _seed_profile_templates(repo)
        m_path = repo / NODE_MANIFEST_REL_PATH
        m_path.parent.mkdir(parents=True)
        m_path.write_text(
            json.dumps(
                {
                    "layer_id": "tower-iso",
                    "entity_kind": "individual",
                    "precedence": 90,
                    "interaction_language": "es",
                }
            ),
            encoding="utf-8",
        )

        # Dry-run & live no-stow
        dry_res = workstation.set_global_agents_profile(repo, "academic", dry_run=True)
        assert dry_res["interaction_language"] == "es"
        assert dry_res["stow_executed"] is False
        no_stow = workstation.set_global_agents_profile(repo, "universal-base", run_stow=False)
        assert no_stow["stow_executed"] is False

        # Live individual stow without .venv/bin/zcg-mcp (python3 fallback + symlink creation)
        stow_ok = subprocess.CompletedProcess(["stow"], 0, stdout="", stderr="")
        with patch("zcg.cockpit.ops.workstation.subprocess.run", return_value=stow_ok):
            live_ind = workstation.set_global_agents_profile(
                repo, "academic", run_stow=True, home_dir=home
            )
        assert live_ind["stow_executed"] is True
        agents_txt = (repo / "antigravity/.gemini/config/AGENTS.md").read_text("utf-8")
        assert "Interaction Language: Spanish (es)" in agents_txt
        assert "## Mastery Gates" in agents_txt
        assert (home / ".gemini/antigravity/mcp_config.json").is_symlink()

        # Non-individual node with .venv/bin/zcg-mcp binary present & existing symlink
        m_path.write_text(
            json.dumps({"layer_id": "oss-iso", "entity_kind": "open-source", "precedence": 10}),
            encoding="utf-8",
        )
        ws_node = tmp_path / "personal-profile"
        ws_m = ws_node / NODE_MANIFEST_REL_PATH
        ws_m.parent.mkdir(parents=True)
        ws_m.write_text(
            json.dumps(
                {
                    "layer_id": "personal-profile",
                    "entity_kind": "individual",
                    "precedence": 90,
                    "interaction_language": "es",
                }
            ),
            encoding="utf-8",
        )
        ws_rule = ws_node / "templates/personal-profile/rules/personal-profile.md"
        ws_rule.parent.mkdir(parents=True)
        ws_rule.write_text(
            "---\ntrigger: always_on\n---\n# Personal Workstation Rules\n- Keep host clean.\n",
            encoding="utf-8",
        )
        mcp_bin = repo / ".venv/bin/zcg-mcp"
        mcp_bin.parent.mkdir(parents=True)
        mcp_bin.write_text("#!/bin/sh\n", encoding="utf-8")
        # Seed antigravity assets in repo (hooks.json, scripts, skills, desktop apps)
        ag_cfg = repo / "antigravity/.gemini/config"
        ag_apps = repo / "antigravity/.local/share/applications"
        (ag_cfg / "scripts").mkdir(parents=True, exist_ok=True)
        (ag_cfg / "skills/sopen").mkdir(parents=True, exist_ok=True)
        ag_apps.mkdir(parents=True, exist_ok=True)
        (ag_cfg / "hooks.json").write_text("{}\n", encoding="utf-8")
        (ag_cfg / "scripts/pre_tool_guard.py").write_text("#!/usr/bin/env python3\n", "utf-8")
        (ag_cfg / "skills/sopen/SKILL.md").write_text("# sopen\n", encoding="utf-8")
        (ag_apps / "antigravity-ide.desktop").write_text("[Desktop Entry]\n", encoding="utf-8")
        workstation._sync_workstation_antigravity_assets(repo, repo)
        workstation._sync_workstation_antigravity_assets(tmp_path / "no-ag", ws_node)
        with patch("zcg.cockpit.ops.workstation.subprocess.run", return_value=stow_ok):
            coupled_res = workstation.set_global_agents_profile(
                repo,
                "universal-base",
                workstation_dir=ws_node,
                run_stow=True,
                home_dir=home,
            )
            # Also verify workstation_dir without personal rule file & without optional assets
            ws_rule.unlink()
            (ag_cfg / "hooks.json").unlink()
            for sub_d in (ag_cfg / "scripts", ag_cfg / "skills", ag_apps):
                for f in sub_d.rglob("*"):
                    if f.is_file():
                        f.unlink()
                for d in sorted(sub_d.rglob("*"), reverse=True):
                    if d.is_dir():
                        d.rmdir()
                sub_d.rmdir()
            workstation.set_global_agents_profile(
                repo,
                "universal-base",
                workstation_dir=ws_node,
                run_stow=False,
                home_dir=home,
            )
        assert coupled_res["workstation_dir"] == str(ws_node.resolve())
        assert any("personal-profile.md" in s for s in coupled_res["source_files"])
        assert (ws_node / "antigravity/.gemini/config/AGENTS.md").is_file()
        assert (ws_node / "antigravity/.local/share/applications/antigravity-ide.desktop").is_file()
        mcp_cfg = json.loads((home / ".gemini/config/mcp_config.json").read_text("utf-8"))
        assert mcp_cfg["mcpServers"]["zcg-mcp"]["command"] == str(mcp_bin.resolve())
        assert mcp_cfg["mcpServers"]["zcg-mcp"]["args"] == ["--repo-dir", str(ws_node.resolve())]

        # Budget cap exceeded
        # Assert
        with (
            patch("zcg.cockpit.ops.workstation.AGENTS_MD_MAX_BYTES", 10),
            pytest.raises(ValueError, match="exceeds 10-byte cap"),
        ):
            workstation.set_global_agents_profile(repo, "universal-base", dry_run=True)

    def test_home_backup_corrupt_mcp_and_systemd_boot_autostart_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify pre-Stow $HOME backups, corrupt mcp_config recovery, and boot autostart units."""
        # Arrange
        repo = tmp_path / "engine"
        home = tmp_path / "home"
        ws_node = tmp_path / "persona-profile"
        corp_node = tmp_path / "acme-corp"
        _seed_profile_templates(repo)
        (repo / ".venv/bin").mkdir(parents=True)
        (repo / ".venv/bin/python").write_text("#!/bin/sh\n", encoding="utf-8")
        (ws_node / "system").mkdir(parents=True)
        (ws_node / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "persona-profile",
                    "entity_kind": "individual",
                    "layer_role": "workstation",
                    "precedence": 90,
                }
            ),
            encoding="utf-8",
        )
        (corp_node / "system").mkdir(parents=True)
        (corp_node / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "acme-corp",
                    "entity_kind": "enterprise",
                    "layer_role": "corporate",
                    "precedence": 10,
                    "environments": {"pro": {"access_mode": "strictly-read-only-audited"}},
                }
            ),
            encoding="utf-8",
        )

        # Seed pre-existing regular AGENTS.md, hooks.json, and corrupt mcp_config.json in $HOME
        cfg_dir = home / ".gemini/config"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "AGENTS.md").write_text("user-custom-agents\n", encoding="utf-8")
        (cfg_dir / "hooks.json").write_text("user-custom-hooks\n", encoding="utf-8")
        (cfg_dir / "mcp_config.json").write_text("{corrupt-json", encoding="utf-8")

        # Act — stow with workstation_dir backs up regular files, recovers mcp_config, writes unit
        stow_ok = subprocess.CompletedProcess(["stow"], 0, stdout="", stderr="")
        with patch("zcg.cockpit.ops.workstation.subprocess.run", return_value=stow_ok):
            res_ws = workstation.set_global_agents_profile(
                repo, "universal-base", workstation_dir=ws_node, run_stow=True, home_dir=home
            )
            # Non-dict mcpServers recovery & non-workstation node stow (no auto-start by default)
            (cfg_dir / "mcp_config.json").write_text('{"mcpServers": []}\n', encoding="utf-8")
            res_corp = workstation.set_global_agents_profile(
                repo, "universal-base", workstation_dir=corp_node, run_stow=True, home_dir=home
            )

        # Assert backups & workstation unit
        assert len(res_ws["backed_up_files"]) == 2
        assert res_ws["boot_autostart"]["unit_name"] == "zcg-workstation.service"
        assert res_ws["boot_autostart"]["port"] == 8790
        assert res_corp["boot_autostart"] is None
        unit_file = home / ".config/systemd/user/zcg-workstation.service"
        wants_link = home / ".config/systemd/user/default.target.wants/zcg-workstation.service"
        assert unit_file.is_file()
        assert "--host 127.0.0.1 --port 8790" in unit_file.read_text("utf-8")
        assert wants_link.is_symlink()

        # Idempotent re-enable when wants_link already exists + dry_run + systemctl live branches
        dry_auto = workstation.configure_node_boot_autostart(
            corp_node, engine_dir=repo, enable=True, home_dir=home, dry_run=True
        )
        assert dry_auto["unit_name"] == "zcg-node-acme-corp.service"
        assert not (home / ".config/systemd/user/zcg-node-acme-corp.service").exists()

        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("ZCG_NO_DAEMON", raising=False)
        monkeypatch.setattr(Path, "home", lambda: home.resolve())
        with (
            patch("zcg.cockpit.ops.workstation.shutil.which", return_value="/usr/bin/systemctl"),
            patch("zcg.cockpit.ops.workstation.subprocess.run", return_value=stow_ok) as sys_mock,
        ):
            en_live = workstation.configure_node_boot_autostart(
                ws_node, engine_dir=tmp_path / "no-venv-eng", enable=True, home_dir=home
            )
            dis_live = workstation.configure_node_boot_autostart(
                ws_node, engine_dir=repo, enable=False, home_dir=home
            )
        assert en_live["systemctl_invoked"] is True
        assert dis_live["systemctl_invoked"] is True
        assert sys_mock.call_count == 4
        assert not unit_file.exists()
        assert not wants_link.exists()

        # Disable without systemctl available
        with patch("zcg.cockpit.ops.workstation.shutil.which", return_value=None):
            dis_offline = workstation.configure_node_boot_autostart(
                corp_node, engine_dir=repo, enable=False, home_dir=home
            )
        assert dis_offline["systemctl_invoked"] is False
