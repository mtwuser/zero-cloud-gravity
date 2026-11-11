"""Unit tests for zcg.mcp.orchestrator.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from zcg.capsules.constants import MAX_ACTIVE_EPHEMERAL_FORKS
from zcg.mcp.orchestrator import EphemeralOrchestrationMixin


def _seed_orchestrator_repo(repo: Path) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@local",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@local",
        "HOME": str(repo),
    }
    subprocess.run(["git", "init", "-b", "master", str(repo)], check=True, env=env)
    for d in ("system", "antigravity/.gemini/config", "layers/gov-es/system"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (repo / "antigravity/.gemini/config/AGENTS.md").write_text(
        "# Global\n## Core Invariant\n**Mandate:** Zero-Cloud purity.\n", encoding="utf-8"
    )
    (repo / "system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "orch-root",
                "layer_role": "department",
            }
        ),
        encoding="utf-8",
    )
    (repo / "layers/gov-es/system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "gov-es",
                "layer_role": "knowledge",
                "upstream_layer": {"repository": "https://github.com/mtwuser/gov-es.git"},
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, env=env)


def _unpack(res: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(res["content"][0]["text"])
    return parsed


class TestMCPOrchestrator:
    """Verify orchestrate_ephemeral_fork across all 9 actions, disk/memory modes, and guards."""

    def test_spawn_inspect_evaluate_return_dmcp_grcc_catalog_and_reap(self, tmp_path: Path) -> None:
        """Execute lifecycle across spawn, evaluate, seal/verify-return, DMCP, GRCC, and reap."""
        # Arrange
        repo = tmp_path / "repo"
        repo.mkdir()
        _seed_orchestrator_repo(repo)
        node = EphemeralOrchestrationMixin(repo_dir=repo, log_dir=tmp_path / "logs")

        # Act
        spawned = _unpack(
            node.tool_orchestrate_ephemeral_fork({"action": "spawn", "bot_role": "sec-bot"})
        )
        fid = str(spawned["fork_id"])
        insp = _unpack(node.tool_orchestrate_ephemeral_fork({"action": "inspect", "fork_id": fid}))
        eval_existing = _unpack(
            node.tool_orchestrate_ephemeral_fork(
                {"action": "evaluate", "fork_id": fid, "target_path": "src/zcg/core/constants.py"}
            )
        )
        eval_oneshot = _unpack(
            node.tool_orchestrate_ephemeral_fork(
                {"action": "evaluate", "bot_role": "qa-bot", "one_shot": True}
            )
        )
        sealed = _unpack(
            node.tool_orchestrate_ephemeral_fork(
                {
                    "action": "seal-return",
                    "fork_id": fid,
                    "digest": {
                        "channel_1_domain_state": "ok",
                        "channel_2_affected_surface": [],
                        "channel_3_invariants_and_constraints": [],
                        "channel_4_actionable_delta": "none",
                    },
                }
            )
        )
        verified = _unpack(
            node.tool_orchestrate_ephemeral_fork(
                {"action": "verify-return", "capsule_token": sealed["capsule_token"]}
            )
        )
        cat = _unpack(node.tool_orchestrate_ephemeral_fork({"action": "catalog"}))
        dmcp_ok = _unpack(
            node.tool_orchestrate_ephemeral_fork(
                {"action": "project-branch", "branch_ref": "master"}
            )
        )
        dmcp_fb = _unpack(
            node.tool_orchestrate_ephemeral_fork(
                {"action": "project-branch", "branch_ref": "missing"}
            )
        )
        grcc = _unpack(
            node.tool_orchestrate_ephemeral_fork(
                {"action": "chain-capsule-ref", "grcc_op": "probe"}
            )
        )
        reaped = _unpack(node.tool_orchestrate_ephemeral_fork({"action": "reap", "fork_id": fid}))

        # Assert
        assert insp["active_count"] == 1
        assert eval_existing["auto_reaped"] is False
        assert eval_oneshot["auto_reaped"] is True
        assert verified["verified"] is True
        assert cat["layer_id"] == "orch-root"
        assert dmcp_ok["verified"] is True
        assert dmcp_fb["fallback_activated"] is True
        assert grcc["grcc_op"] == "probe"
        assert reaped["reaped_forks"] == [fid]

    def test_in_memory_fallback_expired_and_limit_error_branches(self, tmp_path: Path) -> None:
        """Handle read-only OSError in-memory forks, memory caps, and expired fork errors."""
        # Arrange
        repo = tmp_path / "repo"
        repo.mkdir()
        _seed_orchestrator_repo(repo)
        node = EphemeralOrchestrationMixin(repo_dir=repo, log_dir=tmp_path / "logs")
        real_spawn = __import__(
            "zcg.ephemeral.spawner", fromlist=["spawn_ephemeral_fork"]
        ).spawn_ephemeral_fork

        def _ro_spawn(*args: object, **kwargs: object) -> dict[str, object]:
            if not kwargs.get("dry_run"):
                raise OSError("read-only fs")
            return real_spawn(*args, **kwargs)  # type: ignore[no-any-return]

        # Act
        with patch("zcg.mcp.orchestrator.spawn_ephemeral_fork", side_effect=_ro_spawn):
            mem_sp = _unpack(
                node.tool_orchestrate_ephemeral_fork(
                    {"action": "spawn", "bot_role": "mem-bot", "mount_layers": ["gov-es"]}
                )
            )
            mem_plain = _unpack(
                node.tool_orchestrate_ephemeral_fork({"action": "spawn", "bot_role": "plain-mem"})
            )
            mem_oneshot = _unpack(
                node.tool_orchestrate_ephemeral_fork(
                    {"action": "evaluate", "bot_role": "oneshot-mem", "one_shot": True}
                )
            )
        mfid = str(mem_sp["fork_id"])
        pfid = str(mem_plain["fork_id"])
        insp_all = _unpack(node.tool_orchestrate_ephemeral_fork({"action": "inspect"}))
        insp_mem = _unpack(
            node.tool_orchestrate_ephemeral_fork({"action": "inspect", "fork_id": mfid})
        )
        eval_mem = _unpack(
            node.tool_orchestrate_ephemeral_fork(
                {"action": "evaluate", "fork_id": mfid, "target_path": "README.md"}
            )
        )
        _unpack(
            node.tool_orchestrate_ephemeral_fork(
                {"action": "evaluate", "fork_id": pfid, "target_path": "README.md"}
            )
        )
        reap_mem = _unpack(
            node.tool_orchestrate_ephemeral_fork({"action": "reap", "fork_id": mfid})
        )
        node.ephemeral_memory_store["eph-a"] = {"active": True, "expires_at_epoch": 9999999999.0}
        reap_all = _unpack(
            node.tool_orchestrate_ephemeral_fork({"action": "reap", "fork_id": "all"})
        )

        # Assert
        assert mem_oneshot["auto_reaped"] is True
        assert insp_all["active_count"] == 2
        assert insp_mem["active_count"] == 1
        assert eval_mem["fork_id"] == mfid
        assert reap_mem["reaped_forks"] == [mfid]
        assert "eph-a" in reap_all["reaped_forks"]

        with pytest.raises(ValueError, match="Invalid action"):
            node.tool_orchestrate_ephemeral_fork({"action": "explode"})
        with pytest.raises(ValueError, match="not found"):
            node.tool_orchestrate_ephemeral_fork({"action": "inspect", "fork_id": "eph-ghost"})
        with pytest.raises(ValueError, match="Invalid bot_role"):
            node.tool_orchestrate_ephemeral_fork({"action": "spawn", "bot_role": "BAD_ROLE"})
        with pytest.raises(ValueError, match="Missing required 'fork_id'"):
            node.tool_orchestrate_ephemeral_fork({"action": "reap"})
        with pytest.raises(FileNotFoundError):
            node.tool_orchestrate_ephemeral_fork({"action": "reap", "fork_id": "eph-ghost"})

        node.ephemeral_memory_store["eph-exp-1"] = {"expires_at_epoch": 1.0}
        with pytest.raises(ValueError, match="EPHEMERAL_FORK_EXPIRED"):
            node.tool_orchestrate_ephemeral_fork({"action": "inspect", "fork_id": "eph-exp-1"})

        node.ephemeral_memory_store["eph-exp-2"] = {"expires_at_epoch": 1.0}
        with pytest.raises(ValueError, match="EPHEMERAL_FORK_EXPIRED"):
            node.tool_orchestrate_ephemeral_fork({"action": "evaluate", "fork_id": "eph-exp-2"})

        for idx in range(MAX_ACTIVE_EPHEMERAL_FORKS):
            node.ephemeral_memory_store[f"eph-cap-{idx}"] = {
                "active": True,
                "expires_at_epoch": 9999999999.0,
            }
        with (
            patch("zcg.mcp.orchestrator.spawn_ephemeral_fork", side_effect=_ro_spawn),
            pytest.raises(ValueError, match="EPHEMERAL_FORK_LIMIT_REACHED"),
        ):
            node.tool_orchestrate_ephemeral_fork({"action": "spawn", "bot_role": "over-cap"})
