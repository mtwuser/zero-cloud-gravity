"""Unit tests for zcg.cockpit.workstation.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.cockpit import workstation
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
    """Verify Antigravity IDE workspace registration and global AGENTS.md composition."""

    def test_register_antigravity_workspace_idempotency_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify missing-IDE fallback, dry-run, and idempotent workspace list updates."""
        # Arrange
        ws = tmp_path / "node-iso"
        ws.mkdir()
        no_ag_home = tmp_path / "no-ag-home"
        no_ag_home.mkdir()

        # Act — home_dir=None when ~/.gemini/antigravity is absent
        with patch("zcg.cockpit.workstation.Path.home", return_value=no_ag_home):
            unreg = workstation.register_antigravity_workspace(ws, home_dir=None)
        assert unreg["registered"] is False

        home = tmp_path / "home"
        dry_res = workstation.register_antigravity_workspace(ws, home_dir=home, dry_run=True)
        assert dry_res["registered"] is True
        assert not Path(dry_res["workspaces_file"]).exists()

        first = workstation.register_antigravity_workspace(ws, home_dir=home)
        second = workstation.register_antigravity_workspace(ws, home_dir=home)
        data = json.loads(Path(first["workspaces_file"]).read_text("utf-8"))
        assert second["registered"] is True
        # Assert
        assert data["workspaces"] == [str(ws.resolve())]

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
        with patch("zcg.cockpit.workstation.subprocess.run", return_value=stow_ok):
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
        ws_node = tmp_path / "personal-pc"
        ws_m = ws_node / NODE_MANIFEST_REL_PATH
        ws_m.parent.mkdir(parents=True)
        ws_m.write_text(
            json.dumps(
                {
                    "layer_id": "personal-pc",
                    "entity_kind": "individual",
                    "precedence": 90,
                    "interaction_language": "es",
                }
            ),
            encoding="utf-8",
        )
        ws_rule = ws_node / "templates/personal-pc/rules/personal-pc.md"
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
        with patch("zcg.cockpit.workstation.subprocess.run", return_value=stow_ok):
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
        assert any("personal-pc.md" in s for s in coupled_res["source_files"])
        assert (ws_node / "antigravity/.gemini/config/AGENTS.md").is_file()
        assert (ws_node / "antigravity/.local/share/applications/antigravity-ide.desktop").is_file()
        mcp_cfg = json.loads((home / ".gemini/config/mcp_config.json").read_text("utf-8"))
        assert mcp_cfg["mcpServers"]["zcg-mcp"]["command"] == str(mcp_bin.resolve())
        assert mcp_cfg["mcpServers"]["zcg-mcp"]["args"] == ["--repo-dir", str(ws_node.resolve())]

        # Budget cap exceeded
        # Assert
        with (
            patch("zcg.cockpit.workstation.AGENTS_MD_MAX_BYTES", 10),
            pytest.raises(ValueError, match="exceeds 10-byte cap"),
        ):
            workstation.set_global_agents_profile(repo, "universal-base", dry_run=True)
