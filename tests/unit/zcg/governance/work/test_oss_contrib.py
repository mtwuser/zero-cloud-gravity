"""Unit tests for zcg.governance.work.oss_contrib.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance.work import oss_contrib


def _git_run(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_executable(script: Path, body: str = "#!/usr/bin/env bash\nexit 0\n") -> None:
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(body, encoding="utf-8")
    script.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)


def _init_engine_clone(
    repo_dir: Path, *, entity_kind: str = "open-source", version: str = "1.0.0"
) -> None:
    (repo_dir / "system").mkdir(parents=True, exist_ok=True)
    (repo_dir / NODE_MANIFEST_REL_PATH).write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "zero-cloud-gravity-workstation",
                "layer_role": "workstation",
                "entity_kind": entity_kind,
                "precedence": 10,
            }
        ),
        encoding="utf-8",
    )
    (repo_dir / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (repo_dir / "CHANGELOG.md").write_text(f"# Changelog\n\n## [{version}]\n- Ok.\n", "utf-8")
    (repo_dir / "WORKTASK.md").write_text("# Private Tracker\n", encoding="utf-8")
    (repo_dir / "BACKLOG.md").write_text("# Private Backlog\n", encoding="utf-8")
    (repo_dir / "roadmaps").mkdir(parents=True, exist_ok=True)
    (repo_dir / "roadmaps/plan.md").write_text("# Private Roadmap\n", encoding="utf-8")
    (repo_dir / ".github").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".github/dependabot.yml").write_text("version: 2\n", encoding="utf-8")
    (repo_dir / "doc-link").symlink_to("VERSION")
    _make_executable(repo_dir / "scripts/verify-repo.sh")
    _git_run(repo_dir, "init", "-b", "master")
    _git_run(repo_dir, "config", "user.email", "iso@example.org")
    _git_run(repo_dir, "config", "user.name", "ISO")
    _git_run(repo_dir, "add", ".")
    _git_run(repo_dir, "commit", "-m", "chore: initial snapshot")


class TestOssContrib:
    """Verify isolated oss-push-branch, oss-promote-master, and oss-publish workflows and guards."""

    def test_should_expose_and_push_promote_guards_and_execution_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify visibility gating, dev-clone guards, push-branch, and promote-master flows."""
        # Arrange
        dev_bare = tmp_path / "remotes/dev-iso-engine.git"
        subprocess.run(["git", "init", "--bare", "-b", "master", str(dev_bare)], check=True)
        non_dev_bare = tmp_path / "remotes/iso-engine.git"
        subprocess.run(["git", "init", "--bare", "-b", "master", str(non_dev_bare)], check=True)

        dev_ws = tmp_path / "dev-iso-engine"
        _init_engine_clone(dev_ws)
        pub_ws = tmp_path / "iso-engine"
        _init_engine_clone(pub_ws)

        # Act — visibility exposure & bipolar guard checks
        exp_pub_default = oss_contrib.should_expose_oss_targets(pub_ws)
        exp_pub_forced = oss_contrib.should_expose_oss_targets(pub_ws, env={"OSS_CONTRIB": "1"})
        exp_dev = oss_contrib.should_expose_oss_targets(dev_ws, env={})

        with pytest.raises(ValueError, match="Invalid OSS action"):
            oss_contrib.run_oss_action(dev_ws, "invalid")
        with pytest.raises(ValueError, match=r"\[OSS_DEV_ONLY_BLOCKED\]"):
            oss_contrib.run_oss_action(pub_ws, "push-branch")
        _git_run(dev_ws, "remote", "add", "origin", f"file://{non_dev_bare}")
        with pytest.raises(ValueError, match=r"\[OSS_DEV_ORIGIN_MISMATCH\]"):
            oss_contrib.run_oss_action(dev_ws, "push-branch")

        _git_run(dev_ws, "remote", "set-url", "origin", f"file://{dev_bare}")
        _git_run(dev_ws, "push", "-u", "origin", "master")
        with pytest.raises(ValueError, match=r"\[OSS_BRANCH_REQUIRED\]"):
            oss_contrib.run_oss_action(dev_ws, "push-branch")

        _git_run(dev_ws, "checkout", "-b", "feat/iso-cutover")
        (dev_ws / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
        with pytest.raises(ValueError, match="working tree is dirty"):
            oss_contrib.run_oss_action(dev_ws, "push-branch")
        (dev_ws / "dirty.txt").unlink()

        # Execute push-branch & promote-master (dry-run and live, with & without sync script)
        dry_push = oss_contrib.run_oss_action(dev_ws, "push-branch", verify=True, dry_run=True)
        (dev_ws / "NOTES.md").write_text("# Feature\n", encoding="utf-8")
        _git_run(dev_ws, "add", "NOTES.md")
        _git_run(dev_ws, "commit", "-m", "feat: add notes")
        live_push = oss_contrib.run_oss_action(dev_ws, "push-branch", verify=False, dry_run=False)
        dry_promo = oss_contrib.run_oss_action(dev_ws, "promote-master", dry_run=True)
        live_promo = oss_contrib.run_oss_action(dev_ws, "promote-master", dry_run=False)

        _git_run(dev_ws, "checkout", "-b", "fix/with-sync")
        _make_executable(dev_ws / "scripts/workstation-sync.sh")
        _git_run(dev_ws, "add", "scripts/workstation-sync.sh")
        _git_run(dev_ws, "commit", "-m", "chore: add sync script")
        promo_with_sync = oss_contrib.run_oss_action(dev_ws, "promote-master", dry_run=False)

        # Assert
        assert exp_pub_default is False and exp_pub_forced is True and exp_dev is True
        assert "[oss-push-branch DRY_RUN=1]" in dry_push["message"]
        assert "make oss-promote-master" in live_push["message"]
        assert "[oss-promote-master DRY_RUN=1]" in dry_promo["message"]
        assert live_promo["branch"] == "feat/iso-cutover"
        assert promo_with_sync["branch"] == "fix/with-sync"

    def test_publish_guards_orphan_root_pr_flow_and_tag_followup_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify oss-publish guards, tracker stripping, orphan root, PR branch, and tag release."""
        # Arrange
        pub_bare = tmp_path / "remotes/zero-cloud-gravity.git"
        subprocess.run(["git", "init", "--bare", "-b", "master", str(pub_bare)], check=True)
        pub_url = f"file://{pub_bare}"

        ws = tmp_path / "dev-iso-engine"
        _init_engine_clone(ws, version="1.0.0")
        personal_ws = tmp_path / "personal-node"
        _init_engine_clone(personal_ws, entity_kind="individual", version="1.0.0")

        # Act — bipolar publish guards
        (ws / "scratch.tmp").write_text("dirty\n", encoding="utf-8")
        with pytest.raises(ValueError, match="working tree is dirty"):
            oss_contrib.run_oss_action(ws, "publish", remote_url=pub_url, verify=True)
        (ws / "scratch.tmp").unlink()

        with pytest.raises(ValueError, match=r"\[OSS_PUBLISH_GUARD_BLOCKED\]"):
            oss_contrib.run_oss_action(ws, "publish", remote_url=pub_url, release_version="9.9.9")
        with pytest.raises(ValueError, match="Invalid CONTRIB_BRANCH"):
            oss_contrib.run_oss_action(
                ws, "publish", remote_url=pub_url, contrib_branch="bad..ref", create_pr=True
            )

        (ws / "CHANGELOG.md").write_text("## [Unreleased]\n- Pending.\n", encoding="utf-8")
        _git_run(ws, "commit", "-am", "docs: unreleased")
        with pytest.raises(ValueError, match=r"\[OSS_UNRELEASED_CHANGELOG_BLOCKED\]"):
            oss_contrib.run_oss_action(ws, "publish", remote_url=pub_url)

        (ws / "CHANGELOG.md").write_text("# Changelog\n\n## [1.0.0]\n- Cut.\n", encoding="utf-8")
        _git_run(ws, "commit", "-am", "chore: cut 1.0.0")
        with pytest.raises(ValueError, match=r"\[OSS_PERSONAL_REPO_PUBLISH_BLOCKED\]"):
            oss_contrib.run_oss_action(personal_ws, "publish", remote_url=pub_url)

        with (
            patch(
                "zcg.governance.work.oss_contrib.verify_layer_operation_authority",
                return_value={"allowed": False},
            ),
            pytest.raises(ValueError, match=r"\[UNAUTHORIZED_OSS_RELEASE\]"),
        ):
            oss_contrib.run_oss_action(ws, "publish", remote_url=pub_url)

        # Orphan root dry-run + live v1.0.0 release, then duplicate tag guard, PR flow, and v1.0.1
        with patch(
            "zcg.governance.work.oss_contrib.verify_layer_operation_authority",
            return_value={"allowed": True},
        ):
            dry_orphan = oss_contrib.run_oss_action(ws, "publish", remote_url=pub_url, dry_run=True)
            live_orphan = oss_contrib.run_oss_action(
                ws, "publish", remote_url=pub_url, dry_run=False
            )
            with pytest.raises(ValueError, match=r"\[OSS_TAG_ALREADY_PUBLISHED\]"):
                oss_contrib.run_oss_action(ws, "publish", remote_url=pub_url)

            dry_pr = oss_contrib.run_oss_action(
                ws,
                "publish",
                remote_url=pub_url,
                contrib_branch="contrib/iso-sync",
                create_pr=True,
                dry_run=True,
            )
            live_pr = oss_contrib.run_oss_action(
                ws,
                "publish",
                remote_url=pub_url,
                contrib_branch="contrib/iso-sync",
                create_pr=True,
                dry_run=False,
            )

            (ws / "CHANGELOG.md").unlink()
            (ws / "VERSION").write_text("1.0.1\n", encoding="utf-8")
            _git_run(ws, "add", "-A")
            _git_run(ws, "commit", "-m", "chore: release 1.0.1")
            live_followup = oss_contrib.run_oss_action(
                ws, "publish", remote_url=pub_url, dry_run=False
            )

        insp = tmp_path / "inspect-pub"
        _git_run(tmp_path, "clone", pub_url, str(insp))

        # Assert
        assert (
            dry_orphan["orphan_root"] is True
            and "[oss-publish DRY_RUN=1]" in (dry_orphan["message"])
        )
        assert live_orphan["orphan_root"] is True and live_orphan["commits"] == 1
        assert "[oss-publish CREATE_PR=1 DRY_RUN=1]" in dry_pr["message"]
        assert "Pushed PR branch 'contrib/iso-sync'" in live_pr["message"]
        assert live_followup["orphan_root"] is False and live_followup["release_version"] == "1.0.1"
        assert not (insp / "WORKTASK.md").exists()
        assert not (insp / "BACKLOG.md").exists()
        assert not (insp / "roadmaps").exists()
        assert not (insp / ".github/dependabot.yml").exists()
        assert (insp / "VERSION").read_text("utf-8").strip() == "1.0.1"
