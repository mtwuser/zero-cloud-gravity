"""Unit tests for zcg.governance.workspace.surface_mutations.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH, SKILLS_MANIFEST_REL_PATH
from zcg.governance.workspace.surface_mutations import (
    commit_scoped_workspace_paths,
    delete_node_skill,
    inspect_workspace_skills_studio,
    is_workspace_path_dirty,
    save_node_skill_verified,
    switch_workspace_context_branch,
)


def _init_git_ws(ws: Path, *, layer_id: str = "tutor-iso") -> None:
    ws.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "master", str(ws)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(ws), "config", "user.name", "ISO"], check=True)
    subprocess.run(["git", "-C", str(ws), "config", "user.email", "iso@example.org"], check=True)
    (ws / "system").mkdir(parents=True, exist_ok=True)
    (ws / NODE_MANIFEST_REL_PATH).write_text(
        json.dumps({"layer_id": layer_id, "layer_role": "department", "entity_kind": "individual"}),
        encoding="utf-8",
    )
    (ws / "WORKTASK.md").write_text("# Tasks\n- [ ] **T1**: Initial drill\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ws), "add", "."], check=True)
    subprocess.run(["git", "-C", str(ws), "commit", "-m", "chore: init"], check=True)


class TestSurfaceMutations:
    """Verify safe branch switching, Two-World skill authoring, and path-scoped Git commits."""

    def test_switch_workspace_context_branch_guards_and_sync_expected(self, tmp_path: Path) -> None:
        """Verify invalid ref, missing git, dirty worktree, create+existing switch, and sync."""
        # Arrange
        non_git = tmp_path / "plain"
        non_git.mkdir()
        ws = tmp_path / "tutor-iso"
        _init_git_ws(ws)
        (ws / ".agents").mkdir(exist_ok=True)
        (ws / ".agents/local.txt").write_text("ignored runtime", encoding="utf-8")
        plain_git = tmp_path / "bare-git"
        plain_git.mkdir()
        subprocess.run(
            ["git", "init", "-b", "master", str(plain_git)], check=True, capture_output=True
        )
        subprocess.run(["git", "-C", str(plain_git), "config", "user.name", "ISO"], check=True)
        subprocess.run(
            ["git", "-C", str(plain_git), "config", "user.email", "iso@example.org"], check=True
        )
        (plain_git / "README.md").write_text("# Bare\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(plain_git), "add", "."], check=True)
        subprocess.run(["git", "-C", str(plain_git), "commit", "-m", "chore: init"], check=True)

        # Act
        with patch("zcg.governance.workspace.surface_mutations.sync_node_workspace") as sync_mock:
            created_res = switch_workspace_context_branch(ws, branch="specialty/maths")
            existing_res = switch_workspace_context_branch(ws, branch="master")
        unsynced_res = switch_workspace_context_branch(plain_git, branch="hat/focus")
        (ws / "WORKTASK.md").write_text("# Dirty\n", encoding="utf-8")

        # Assert
        assert sync_mock.call_count == 2
        assert created_res == {"branch": "specialty/maths", "created": True, "synced": True}
        assert existing_res == {"branch": "master", "created": False, "synced": True}
        assert unsynced_res == {"branch": "hat/focus", "created": True, "synced": False}
        with pytest.raises(ValueError, match="INVALID_CONTEXT_BRANCH"):
            switch_workspace_context_branch(ws, branch="bad..ref")
        with pytest.raises(ValueError, match="GIT_REPO_REQUIRED"):
            switch_workspace_context_branch(non_git, branch="specialty/maths")
        with pytest.raises(ValueError, match="WORKTREE_DIRTY"):
            switch_workspace_context_branch(ws, branch="specialty/maths")
        subprocess.run(["git", "-C", str(ws), "checkout", "--", "WORKTASK.md"], check=True)
        with pytest.raises(ValueError, match="BRANCH_NOT_FOUND"):
            switch_workspace_context_branch(ws, branch="specialty/uncreated", allow_create=False)
        with (
            patch(
                "zcg.governance.workspace.surface_mutations._run_git",
                side_effect=[
                    subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                    subprocess.CompletedProcess([], 0, stdout="master\n", stderr=""),
                    subprocess.CompletedProcess([], 1, stdout="", stderr="lock error"),
                ],
            ),
            pytest.raises(ValueError, match="GIT_SWITCH_FAILED"),
        ):
            switch_workspace_context_branch(ws, branch="specialty/physics")

    def test_skills_studio_inspect_save_optimistic_lock_and_auditor_gate_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify inherited vs node-owned skills, SHA-256 lock, auditor gate, and 0-drift save."""
        # Arrange
        ws = tmp_path / "tutor-iso"
        _init_git_ws(ws)
        (ws / ".agents/skills/sopen").mkdir(parents=True)
        (ws / ".agents/skills/sopen/SKILL.md").write_text(
            "---\nname: sopen\ndescription: Open session state cleanly.\n---\n# Open\n",
            encoding="utf-8",
        )
        (ws / SKILLS_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "skills": [{"name": "sopen", "source": "root:universal-base"}],
                    "enabled_skills": ["sclose"],
                }
            ),
            encoding="utf-8",
        )
        valid_sk = (
            "---\nname: solve-ode\n"
            "description: Solve ordinary differential equation drills step by step.\n---\n"
            "# Solve ODE\n"
        )

        # Act
        saved = save_node_skill_verified(ws, skill_slug="solve-ode", content=valid_sk)
        updated = save_node_skill_verified(
            ws,
            skill_slug="solve-ode",
            content=valid_sk + "\nVerify boundary values.\n",
            expected_sha256=saved["sha256"],
        )
        studio = inspect_workspace_skills_studio(ws, skill_slug="solve-ode")
        (ws / SKILLS_MANIFEST_REL_PATH).write_text('{"skills": "bad"}', encoding="utf-8")
        studio_bad_map = inspect_workspace_skills_studio(ws)
        studio_no_manifest = inspect_workspace_skills_studio(tmp_path / "empty-dir")

        # Assert
        assert studio_no_manifest["skills"] == []
        assert saved["trust_score"] == 100
        assert updated["sha256"] != saved["sha256"]
        assert (ws / ".agents/skills/solve-ode/SKILL.md").is_file()
        assert studio["selected_skill"]["ownership"] == "node-owned"
        assert any(s["ownership"] == "inherited" for s in studio["skills"])
        assert len(studio_bad_map["skills"]) == 2
        with pytest.raises(ValueError, match="INVALID_SKILL_SLUG"):
            save_node_skill_verified(ws, skill_slug="BAD_SLUG", content=valid_sk)
        with pytest.raises(ValueError, match="STALE_SKILL_REVISION"):
            save_node_skill_verified(
                ws, skill_slug="solve-ode", content=valid_sk, expected_sha256="deadbeef"
            )
        with pytest.raises(ValueError, match="exceeds 464-line"):
            save_node_skill_verified(ws, skill_slug="solve-ode", content="line\n" * 470)
        with pytest.raises(ValueError, match="YAML frontmatter"):
            save_node_skill_verified(ws, skill_slug="solve-ode", content="# Missing FM\n")
        with pytest.raises(ValueError, match="SKILL_AUDIT_REJECTED"):
            save_node_skill_verified(
                ws,
                skill_slug="solve-ode",
                content="---\nname: solve-ode\ndescription: Bad\u202e\n---\n# Bad\n",
            )
        bad_lid = tmp_path / "BAD_DIR"
        bad_lid.mkdir()
        with pytest.raises(ValueError, match="INVALID_LAYER_ID"):
            save_node_skill_verified(bad_lid, skill_slug="solve-ode", content=valid_sk)
        (ws / ".agents/skills/corp-sop").mkdir(parents=True)
        (ws / ".agents/skills/corp-sop/SKILL.md").write_text(
            "---\nname: corp-sop\ndescription: Parent layer procedure.\n---\n# SOP\n",
            encoding="utf-8",
        )
        tiers = {s["slug"]: s["origin_tier"] for s in inspect_workspace_skills_studio(ws)["skills"]}
        assert tiers == {"corp-sop": "parent", "solve-ode": "node", "sopen": "engine"}
        del_res = delete_node_skill(ws, skill_slug="solve-ode")
        assert del_res["deleted"] is True
        assert not (ws / ".agents/skills/solve-ode").exists()
        save_node_skill_verified(
            ws,
            skill_slug="sopen",
            content="---\nname: sopen\ndescription: Custom node sopen.\n---\n# Sopen\n",
        )
        delete_node_skill(ws, skill_slug="sopen")
        assert (ws / ".agents/skills/sopen/SKILL.md").is_file()
        with pytest.raises(ValueError, match="INVALID_SKILL_SLUG"):
            delete_node_skill(ws, skill_slug="BAD_SLUG")
        with pytest.raises(ValueError, match="INVALID_LAYER_ID"):
            delete_node_skill(bad_lid, skill_slug="solve-ode")
        with pytest.raises(ValueError, match="SKILL_NOT_NODE_OWNED"):
            delete_node_skill(ws, skill_slug="corp-sop")

    def test_commit_scoped_workspace_paths_guards_and_clean_commit_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Conventional Commit, path whitelist, staged-index guard, and scoped commit."""
        # Arrange
        ws = tmp_path / "tutor-iso"
        _init_git_ws(ws)
        valid_sk = (
            "---\nname: solve-ode\n"
            "description: Solve ordinary differential equation drills step by step.\n---\n# ODE\n"
        )
        saved = save_node_skill_verified(ws, skill_slug="solve-ode", content=valid_sk)
        (ws / "WORKTASK.md").write_text("# Tasks\n- [x] **T1**: Initial drill\n", encoding="utf-8")
        (ws / "untracked_other.txt").write_text("stay untracked", encoding="utf-8")

        # Act
        commit_res = commit_scoped_workspace_paths(
            ws,
            rel_paths=[saved["canonical_rel_path"], saved["canonical_rel_path"], "WORKTASK.md"],
            commit_message="feat(skills): add solve-ode skill and update tracker",
        )

        # Assert
        assert len(commit_res["commit_sha"]) >= 7
        assert commit_res["committed_paths"] == [saved["canonical_rel_path"], "WORKTASK.md"]
        assert (ws / "untracked_other.txt").is_file()
        with pytest.raises(ValueError, match="NOTHING_TO_COMMIT"):
            commit_scoped_workspace_paths(
                ws, rel_paths=["WORKTASK.md"], commit_message="docs(ledger): repeat"
            )
        with pytest.raises(ValueError, match="INVALID_COMMIT_MESSAGE"):
            commit_scoped_workspace_paths(
                ws, rel_paths=["WORKTASK.md"], commit_message="bad message"
            )
        with pytest.raises(ValueError, match="at least one target path"):
            commit_scoped_workspace_paths(ws, rel_paths=[], commit_message="docs: x")
        brand_p = ws / "surfaces/web/static/brand/logo.svg"
        brand_p.parent.mkdir(parents=True, exist_ok=True)
        brand_p.write_text("<svg></svg>", encoding="utf-8")
        doc_p = ws / "docs/guides/sop.md"
        doc_p.parent.mkdir(parents=True, exist_ok=True)
        doc_p.write_text("# SOP\n", encoding="utf-8")
        brand_commit = commit_scoped_workspace_paths(
            ws,
            rel_paths=["surfaces/web/static/brand/logo.svg", "docs/guides/sop.md"],
            commit_message="chore(brand): add brand emblem and sop",
        )
        assert brand_commit["committed_paths"] == [
            "surfaces/web/static/brand/logo.svg",
            "docs/guides/sop.md",
        ]
        (ws / "src_secret.py").write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="UNSAFE_COMMIT_PATH"):
            commit_scoped_workspace_paths(
                ws, rel_paths=["src_secret.py"], commit_message="chore: nope"
            )
        subprocess.run(["git", "-C", str(ws), "add", "untracked_other.txt"], check=True)
        with pytest.raises(ValueError, match="INDEX_HAS_STAGED_FILES"):
            commit_scoped_workspace_paths(
                ws, rel_paths=["WORKTASK.md"], commit_message="docs: blocked"
            )
        subprocess.run(["git", "-C", str(ws), "reset", "HEAD", "untracked_other.txt"], check=True)
        (ws / "WORKTASK.md").write_text("# Next\n", encoding="utf-8")
        with (
            patch(
                "zcg.governance.workspace.surface_mutations._run_git",
                side_effect=[
                    subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                    subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                    subprocess.CompletedProcess([], 1, stdout="", stderr=""),
                    subprocess.CompletedProcess([], 1, stdout="", stderr="hook denied"),
                ],
            ),
            pytest.raises(ValueError, match="GIT_COMMIT_FAILED"),
        ):
            commit_scoped_workspace_paths(
                ws, rel_paths=["WORKTASK.md"], commit_message="docs: fail"
            )

    def test_is_workspace_path_dirty_clean_dirty_non_git_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify is_workspace_path_dirty across clean, modified, untracked, non-git, and escape."""
        # Arrange
        non_git = tmp_path / "plain"
        non_git.mkdir()
        (non_git / "README.md").write_text("# Plain\n", encoding="utf-8")
        ws = tmp_path / "tutor-iso"
        _init_git_ws(ws)

        # Act
        empty_res = is_workspace_path_dirty(ws, "   ")
        non_git_res = is_workspace_path_dirty(non_git, "README.md")
        clean_res = is_workspace_path_dirty(ws, "WORKTASK.md")
        (ws / "WORKTASK.md").write_text("# Modified\n", encoding="utf-8")
        dirty_res = is_workspace_path_dirty(ws, "WORKTASK.md")
        (ws / "docs").mkdir(exist_ok=True)
        (ws / "docs/new.md").write_text("# New\n", encoding="utf-8")
        untracked_res = is_workspace_path_dirty(ws, "docs\\new.md")
        with patch("zcg.governance.workspace.surface_mutations.shutil.which", return_value=None):
            no_git_bin_res = is_workspace_path_dirty(ws, "WORKTASK.md")
        with patch(
            "zcg.governance.workspace.surface_mutations._run_git",
            return_value=subprocess.CompletedProcess([], 1, stdout="M WORKTASK.md\n", stderr="err"),
        ):
            failed_git_res = is_workspace_path_dirty(ws, "WORKTASK.md")

        # Assert
        assert empty_res is False
        assert non_git_res is False
        assert clean_res is False
        assert dirty_res is True
        assert untracked_res is True
        assert no_git_bin_res is False
        assert failed_git_res is False
        with pytest.raises(ValueError, match="PATH_CONTAINMENT_VIOLATION"):
            is_workspace_path_dirty(ws, "../outside.md")
