"""Unit tests for zcg.ephemeral.spawner.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.capsules.constants import MAX_ACTIVE_EPHEMERAL_FORKS
from zcg.ephemeral.spawner import spawn_ephemeral_fork


class TestEphemeralSpawner:
    """Verify Department Bot ephemeral fork spawning, validation guards, and project bridging."""

    def test_spawn_ephemeral_fork_nominal_templates_layers_bridge_and_dry_run(
        self, tmp_path: Path
    ) -> None:
        """Materialize a CoW ephemeral fork with templates, mounted layers, and bridge rules."""
        # Arrange
        repo = tmp_path / "repo"
        (repo / "antigravity/.gemini/config").mkdir(parents=True)
        (repo / "antigravity/.gemini/config/AGENTS.md").write_text("# Root\n", encoding="utf-8")
        (repo / "README.md").write_text("# Readme\n", encoding="utf-8")
        tpl = repo / "templates/context-stack/software-engineering"
        (tpl / "rules").mkdir(parents=True)
        (tpl / "assets").mkdir(parents=True)
        (tpl / "template.json").write_text(
            json.dumps({"name": "software-engineering"}), encoding="utf-8"
        )
        (tpl / "rules/se.md").write_text("# SE\n", encoding="utf-8")
        (tpl / "assets/blueprint.md").write_text("# Blueprint\n", encoding="utf-8")
        (repo / "layers/gov-es").mkdir(parents=True)
        (repo / "layers/gov-es/README.md").write_text("# Gov\n", encoding="utf-8")

        proj = tmp_path / "consumer_proj"
        (proj / ".agents/rules").mkdir(parents=True)
        (proj / ".agents/rules/local.md").write_text("Enforce local policy.", encoding="utf-8")

        base_manifest = {
            "schema_version": "zcg-node-v1",
            "layer_id": "node-root",
            "layer_role": "department",
            "default_stack_templates": ["software-engineering"],
        }

        # Act
        dry = spawn_ephemeral_fork(
            repo, base_manifest, bot_role="sec-bot", dry_run=True, now_epoch=1000.0
        )
        plain_spawned = spawn_ephemeral_fork(
            repo, base_manifest, bot_role="plain-bot", now_epoch=1000.5
        )
        spawned = spawn_ephemeral_fork(
            repo,
            base_manifest,
            bot_role="sec-bot",
            mount_templates=["software-engineering"],
            mount_layers=["gov-es"],
            mount_project_rules_from=proj,
            now_epoch=1001.0,
        )

        # Assert
        assert dry["dry_run"] is True
        assert not Path(dry["fork_dir"]).exists()
        assert Path(plain_spawned["fork_dir"]).is_dir()
        fork_dir = Path(spawned["fork_dir"])
        assert (fork_dir / "system/zcg-node.json").is_file()
        assert (fork_dir / "layers/gov-es/README.md").is_file()
        assert (
            fork_dir / "layers/ephemeral-project-bridge/antigravity/.gemini/config/AGENTS.md"
        ).is_file()
        assert spawned["bridged_project_files"] == [".agents/rules/local.md"]

    def test_spawn_ephemeral_fork_rejects_all_invalid_arguments_and_escapes(
        self, tmp_path: Path
    ) -> None:
        """Enforce all validation invariants, workstation RO lock, symlink guard, and fork cap."""
        # Arrange
        repo = tmp_path / "repo"
        repo.mkdir()
        base = {"layer_id": "root", "layer_role": "workstation"}

        # Act
        bad_cases: list[tuple[dict[str, object], str]] = [
            ({"bot_role": "BAD_ROLE"}, "Invalid bot_role"),
            ({"bot_role": "ok", "model_tier": "ultra"}, "Invalid model_tier"),
            ({"bot_role": "ok", "access_mode": "full-root"}, "Invalid access_mode"),
            ({"bot_role": "ok", "ephemeral_scope": "global"}, "Invalid ephemeral_scope"),
            ({"bot_role": "ok", "actor_role": "hacker"}, "Invalid actor_role"),
            ({"bot_role": "ok", "resolution_policy": "never"}, "Invalid resolution_policy"),
            (
                {
                    "bot_role": "ok",
                    "ephemeral_scope": "inter-layer",
                    "access_mode": "read-write-scoped",
                },
                "Inter-layer ephemeral forks",
            ),
            (
                {
                    "bot_role": "ok",
                    "actor_role": "validator",
                    "access_mode": "read-write-scoped",
                },
                "Validator actor_role",
            ),
            ({"bot_role": "ok", "resolution": "L9"}, "Invalid resolution"),
            ({"bot_role": "ok", "ttl_seconds": 1}, "Invalid ttl_seconds"),
            (
                {"bot_role": "ok", "architectural_planes": ["quantum"]},
                "Invalid architectural_plane",
            ),
            ({"bot_role": "ok", "mount_templates": ["BAD_TPL"]}, "Invalid mount_template"),
            ({"bot_role": "ok", "mount_layers": ["BAD_LYR"]}, "Invalid mount_layer"),
        ]
        for kwargs, expected_msg in bad_cases:
            with pytest.raises(ValueError, match=expected_msg):
                spawn_ephemeral_fork(repo, base, **kwargs)  # type: ignore[arg-type]

        (repo / ".workstation-state.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="Read-only workstation"):
            spawn_ephemeral_fork(repo, base, bot_role="ok", access_mode="read-write-scoped")

        with pytest.raises(FileNotFoundError, match="does not exist"):
            spawn_ephemeral_fork(
                repo, base, bot_role="ok", mount_project_rules_from=tmp_path / "missing_proj"
            )

        outside = tmp_path / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        bad_proj = tmp_path / "bad_proj"
        (bad_proj / ".agents/rules").mkdir(parents=True)
        (bad_proj / ".agents/rules/escape.md").symlink_to(outside)
        with pytest.raises(ValueError, match="Outbound symlink escape"):
            spawn_ephemeral_fork(repo, base, bot_role="ok", mount_project_rules_from=bad_proj)

        cap_root = tmp_path / "cap_root"
        for idx in range(MAX_ACTIVE_EPHEMERAL_FORKS):
            fdir = cap_root / f"eph-slot-{idx}"
            (fdir / "system").mkdir(parents=True)
            (fdir / "system/zcg-node.json").write_text(
                json.dumps({"ephemeral_metadata": {"expires_at_epoch": 9999999999.0}}),
                encoding="utf-8",
            )
        # Assert
        with pytest.raises(ValueError, match="EPHEMERAL_FORK_LIMIT_REACHED"):
            spawn_ephemeral_fork(repo, base, bot_role="ok", ephemeral_root=cap_root, now_epoch=10.0)
