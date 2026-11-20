"""Implementation contract suite verifying Makefile oss-* guards and installer/showcase scripts.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
from typing import TYPE_CHECKING

from zcg.core.constants import REPO_DIR

if TYPE_CHECKING:
    from pathlib import Path


class TestOssAndInstallerContracts:
    """Verify Makefile oss-* contributor target guards and offline installer/showcase stagers."""

    def test_makefile_oss_dev_targets_positive_and_bipolar_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify oss-* targets conditionally appear in help and enforce dev-<repo> guards."""
        # Arrange
        dev_repo = tmp_path / "dev-iso-engine"
        pub_repo = tmp_path / "iso-engine"
        node_doc = json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "zero-cloud-gravity-workstation",
                "layer_role": "workstation",
                "entity_kind": "open-source",
                "precedence": 10,
            }
        )
        for repo_dir in (dev_repo, pub_repo):
            (repo_dir / "system").mkdir(parents=True)
            shutil.copy2(REPO_DIR / "Makefile", repo_dir / "Makefile")
            (repo_dir / "VERSION").write_text("1.0.0\n", encoding="utf-8")
            (repo_dir / "src").symlink_to(REPO_DIR / "src", target_is_directory=True)
            (repo_dir / "system/zcg-node.json").write_text(node_doc, encoding="utf-8")
            subprocess.run(["git", "init", "-b", "master"], cwd=repo_dir, check=True)
            subprocess.run(
                ["git", "config", "user.email", "iso@example.org"], cwd=repo_dir, check=True
            )
            subprocess.run(["git", "config", "user.name", "ISO"], cwd=repo_dir, check=True)
            subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
            subprocess.run(["git", "commit", "-m", "chore: init"], cwd=repo_dir, check=True)

        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:iso-org/dev-iso-engine.git"],
            cwd=dev_repo,
            check=True,
        )
        make_cmd = ["make", f"PYTHON={sys.executable}", "DRY_RUN=1"]

        def _mk(cwd: Path, *extra: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([*make_cmd, *extra], cwd=cwd, capture_output=True, text=True)

        # Act
        pub_help = _mk(pub_repo, "help")
        pub_help_oss = _mk(pub_repo, "OSS_CONTRIB=1", "help")
        dev_help = _mk(dev_repo, "help")
        master_err = _mk(dev_repo, "oss-push-branch")
        subprocess.run(["git", "checkout", "-b", "fix/iso-guard"], cwd=dev_repo, check=True)
        push_ok = _mk(dev_repo, "oss-push-branch")
        promo_ok = _mk(dev_repo, "oss-promote-master")
        non_dev_err = _mk(pub_repo, "oss-push-branch")
        subprocess.run(
            ["git", "remote", "set-url", "origin", "git@github.com:iso-org/iso-engine.git"],
            cwd=dev_repo,
            check=True,
        )
        origin_err = _mk(dev_repo, "oss-push-branch")

        # Assert
        assert "oss-push-branch" not in pub_help.stdout
        assert "oss-push-branch" in pub_help_oss.stdout and "oss-push-branch" in dev_help.stdout
        assert push_ok.returncode == 0 and "[oss-push-branch DRY_RUN=1]" in push_ok.stdout
        assert promo_ok.returncode == 0 and "[oss-promote-master DRY_RUN=1]" in promo_ok.stdout
        assert master_err.returncode != 0 and "[OSS_BRANCH_REQUIRED]" in master_err.stderr
        assert non_dev_err.returncode != 0 and "[OSS_DEV_ONLY_BLOCKED]" in non_dev_err.stderr
        assert origin_err.returncode != 0 and "[OSS_DEV_ORIGIN_MISMATCH]" in origin_err.stderr

    def test_installer_ephemeral_archive_and_showcase_stager_contracts_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify install-antigravity --from-archive hygiene and stage-showcase dry-run."""
        # Arrange
        dl_dir = tmp_path / "Downloads"
        dl_dir.mkdir()
        dest_dir = tmp_path / "opt-ide"
        src_bundle = tmp_path / "pkg/Antigravity IDE"
        (src_bundle / "resources/app").mkdir(parents=True)
        (src_bundle / "antigravity-ide").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (src_bundle / "resources/app/package.json").write_text(
            json.dumps({"version": "2.32.1"}), encoding="utf-8"
        )
        archive_path = tmp_path / "manual-ide-2.32.1.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(src_bundle, arcname="Antigravity IDE")
        inst_env = {
            **os.environ,
            "ANTIGRAVITY_DOWNLOADS_DIR": str(dl_dir),
            "ANTIGRAVITY_IDE_DEST": str(dest_dir),
        }
        inst_sh = str(REPO_DIR / "scripts/install-antigravity.sh")
        show_sh = str(REPO_DIR / "scripts/stage-showcase.sh")
        show_dir = tmp_path / "zcg-showcase"

        # Act
        ambig_err = subprocess.run(
            [inst_sh, "--from-archive", str(archive_path)],
            env=inst_env,
            capture_output=True,
            text=True,
        )
        offline_ok = subprocess.run(
            [inst_sh, "--ide", "--from-archive", str(archive_path)],
            env=inst_env,
            capture_output=True,
            text=True,
        )
        dry_showcase = subprocess.run(
            [show_sh, "--https-demo", "--dry-run", "--dir", str(show_dir)],
            capture_output=True,
            text=True,
        )
        status_showcase = subprocess.run(
            [show_sh, "--status", "--dir", str(show_dir)], capture_output=True, text=True
        )

        # Assert
        assert ambig_err.returncode != 0
        assert offline_ok.returncode == 0
        assert list(dl_dir.iterdir()) == []
        assert archive_path.is_file()
        assert (dest_dir / ".installed-version").read_text(encoding="utf-8").strip() == "2.32.1"
        assert dry_showcase.returncode == 0 and "[CAP-01]" in dry_showcase.stdout
        assert (
            "persona-profile" in dry_showcase.stdout and ("al" + "ex-") not in dry_showcase.stdout
        )
        assert "[CAP-14]" in dry_showcase.stdout and "[TLS-13]" in dry_showcase.stdout
        assert not show_dir.exists()
        assert status_showcase.returncode == 0 and "not staged" in status_showcase.stdout.lower()
        for host_script in ("scripts/workstation-audit.sh", "scripts/workstation-restore.sh"):
            script_txt = (REPO_DIR / host_script).read_text(encoding="utf-8")
            assert "| grep -q" not in script_txt, f"SIGPIPE-prone '| grep -q' in {host_script}"
