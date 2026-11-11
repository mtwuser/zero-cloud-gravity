"""Unit tests for zcg.ephemeral.lifecycle.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.ephemeral.lifecycle import (
    copy_zero_copy,
    default_ephemeral_root,
    inspect_ephemeral_forks,
    reap_ephemeral_fork,
    reap_expired_ephemeral_forks,
)


class TestEphemeralLifecycle:
    """Verify ephemeral fork root resolution, CoW hardlink/copy2 helpers, and TTL reaping."""

    def test_default_ephemeral_root_precedence_and_ro_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resolve explicit, env-override, writable repo, and read-only /tmp fallback roots."""
        # Arrange
        explicit = tmp_path / "custom"
        env_dir = tmp_path / "env_forks"

        # Act
        r_explicit = default_ephemeral_root(tmp_path, explicit)
        monkeypatch.setenv("ZCG_EPHEMERAL_ROOT", str(env_dir))
        r_env = default_ephemeral_root(tmp_path)
        monkeypatch.delenv("ZCG_EPHEMERAL_ROOT")
        r_writable = default_ephemeral_root(tmp_path / "deep/nonexistent")
        with patch("zcg.ephemeral.lifecycle.os.access", side_effect=[False, True]):
            r_tmp = default_ephemeral_root(tmp_path / "ro_repo")
        with patch("zcg.ephemeral.lifecycle.os.access", return_value=False):
            r_ro_all = default_ephemeral_root(tmp_path / "ro_all")

        # Assert
        assert r_explicit == explicit.resolve()
        assert r_env == env_dir.resolve()
        assert r_writable.name == "ephemeral_forks"
        assert r_tmp.name == "zcg_ephemeral_forks"
        assert r_ro_all.name == "ephemeral_forks"

    def test_copy_zero_copy_directory_file_and_hardlink_fallback(self, tmp_path: Path) -> None:
        """Copy directories and files via hardlink and fall back to copy2 on OSError."""
        # Arrange
        src_dir = tmp_path / "src_dir"
        (src_dir / "sub").mkdir(parents=True)
        (src_dir / "sub/a.txt").write_text("hello", encoding="utf-8")
        src_file = tmp_path / "single.txt"
        src_file.write_text("world", encoding="utf-8")
        dst_dir = tmp_path / "dst_dir"
        dst_file = tmp_path / "dst_single.txt"

        # Act
        copy_zero_copy(src_dir, dst_dir)
        with patch.object(os, "link", side_effect=OSError("cross-device")):
            copy_zero_copy(src_file, dst_file)

        # Assert
        assert (dst_dir / "sub/a.txt").read_text(encoding="utf-8") == "hello"
        assert dst_file.read_text(encoding="utf-8") == "world"

    def test_reap_inspect_and_explicit_reap_lifecycle(self, tmp_path: Path) -> None:
        """Reap missing/corrupt/expired forks, inspect active forks, and reap specific or all."""
        # Arrange
        eph_root = tmp_path / "logs/ephemeral_forks"
        assert reap_expired_ephemeral_forks(tmp_path, eph_root, now_epoch=100.0) == []
        eph_root.mkdir(parents=True)
        (eph_root / "stray.txt").write_text("x", encoding="utf-8")
        (eph_root / "eph-missing-manifest").mkdir()
        corrupt = eph_root / "eph-corrupt-json"
        (corrupt / "system").mkdir(parents=True)
        (corrupt / "system/zcg-node.json").write_text("{bad", encoding="utf-8")
        exp = eph_root / "eph-expired-1"
        (exp / "system").mkdir(parents=True)
        (exp / "system/zcg-node.json").write_text(
            json.dumps({"ephemeral_metadata": {"expires_at_epoch": 50.0}}), encoding="utf-8"
        )
        act1 = eph_root / "eph-active-1"
        (act1 / "system").mkdir(parents=True)
        (act1 / "system/zcg-node.json").write_text(
            json.dumps({"ephemeral_metadata": {"bot_role": "sec-bot", "expires_at_epoch": 200.0}}),
            encoding="utf-8",
        )
        act2 = eph_root / "eph-active-2"
        (act2 / "system").mkdir(parents=True)
        (act2 / "system/zcg-node.json").write_text(
            json.dumps({"ephemeral_metadata": {"bot_role": "qa-bot", "expires_at_epoch": 200.0}}),
            encoding="utf-8",
        )

        # Act
        inspected_all = inspect_ephemeral_forks(tmp_path, ephemeral_root=eph_root, now_epoch=100.0)
        inspected_one = inspect_ephemeral_forks(
            tmp_path, "eph-active-1", ephemeral_root=eph_root, now_epoch=100.0
        )
        dry_one = reap_ephemeral_fork(
            tmp_path, "eph-active-1", ephemeral_root=eph_root, dry_run=True
        )
        reaped_one = reap_ephemeral_fork(tmp_path, "eph-active-1", ephemeral_root=eph_root)
        dry_all = reap_ephemeral_fork(tmp_path, "all", ephemeral_root=eph_root, dry_run=True)
        (eph_root / "stray.txt").unlink()
        reaped_all = reap_ephemeral_fork(tmp_path, "all", ephemeral_root=eph_root)

        # Assert
        assert set(inspected_all["reaped_expired"]) == {
            "eph-corrupt-json",
            "eph-expired-1",
            "eph-missing-manifest",
        }
        assert inspected_all["active_count"] == 2
        assert inspected_one["active_count"] == 1
        assert dry_one["dry_run"] is True
        assert reaped_one["reaped_forks"] == ["eph-active-1"]
        assert dry_all["reaped_forks"] == ["eph-active-2"]
        assert reaped_all["reaped_forks"] == ["eph-active-2"]
        with pytest.raises(FileNotFoundError, match="not found"):
            inspect_ephemeral_forks(tmp_path, "eph-unknown", ephemeral_root=eph_root)
        exp2 = tmp_path / "exp_root/eph-gone-1"
        (exp2 / "system").mkdir(parents=True)
        (exp2 / "system/zcg-node.json").write_text(
            json.dumps({"ephemeral_metadata": {"expires_at_epoch": 10.0}}), encoding="utf-8"
        )
        with pytest.raises(FileNotFoundError, match="EPHEMERAL_FORK_EXPIRED"):
            inspect_ephemeral_forks(
                tmp_path, "eph-gone-1", ephemeral_root=exp2.parent, now_epoch=99.0
            )
        with pytest.raises(ValueError, match="Invalid resolution_reason"):
            reap_ephemeral_fork(tmp_path, "all", resolution_reason="bad")
        with pytest.raises(ValueError, match="Invalid fork_id"):
            reap_ephemeral_fork(tmp_path, "BAD_ID")
        with pytest.raises(FileNotFoundError, match="not found under"):
            reap_ephemeral_fork(tmp_path, "eph-missing-9", ephemeral_root=tmp_path / "none")
