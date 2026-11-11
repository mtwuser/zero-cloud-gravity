"""Unit tests for zcg.capsules.grcc.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from zcg.capsules.codec import seal_single_capsule
from zcg.capsules.grcc import (
    compute_grcc_scope_fingerprint,
    discover_deep_context_index,
    list_git_branch_markdown_files,
    orchestrate_dmcp_branch_projection,
    orchestrate_grcc_capsule_ref,
    read_git_branch_document,
    resolve_git_branch_commit_sha,
)


def _init_git_repo(repo_dir: Path) -> str:
    env = {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@local",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@local",
        "HOME": str(repo_dir),
    }
    subprocess.run(["git", "init", "-b", "master", str(repo_dir)], check=True, env=env)
    (repo_dir / "README.md").write_text("# Root\n", encoding="utf-8")
    (repo_dir / "docs").mkdir()
    (repo_dir / "docs/spec.md").write_text("# Spec\n", encoding="utf-8")
    (repo_dir / "templates/t1/rules").mkdir(parents=True)
    (repo_dir / "templates/t1/rules/r1.md").write_text("# Rule\n", encoding="utf-8")
    (repo_dir / "antigravity/.gemini/config").mkdir(parents=True)
    (repo_dir / "antigravity/.gemini/config/AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo_dir / "notes.txt").write_text("ignore\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "init"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo_dir), "branch", "specialty/grid"], check=True, env=env)
    return subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


class TestCapsuleGrcc:
    """Verify zero-checkout Git branch readers, DMCP projections, GRCC refs, and deep indexing."""

    def test_resolve_and_read_git_branch_document_and_containment_guards(
        self, tmp_path: Path
    ) -> None:
        """Read allowlisted branch documents via git show while blocking unsafe refs and paths."""
        # Arrange
        repo = tmp_path / "repo"
        repo.mkdir()
        head_sha = _init_git_repo(repo)
        (repo / "docs/escape.md").symlink_to(tmp_path / "outside.md")

        # Act
        ref, sha = resolve_git_branch_commit_sha("specialty/grid", repo)
        text, doc_sha = read_git_branch_document(repo, "docs/spec.md", "specialty/grid")
        _, all_docs = list_git_branch_markdown_files(repo, "master", scope="all")
        _, targeted = list_git_branch_markdown_files(
            repo, "master", scope="docs", target_path="README.md"
        )

        # Assert
        assert (ref, sha, doc_sha) == ("specialty/grid", head_sha, head_sha)
        assert "# Spec" in text
        assert len(all_docs) == 4
        assert any(p == "README.md" for p, _ in targeted)
        with pytest.raises(ValueError, match="Invalid or unsafe branch_ref"):
            resolve_git_branch_commit_sha("../bad", repo)
        with pytest.raises(ValueError, match="DMCP_BRANCH_REF_NOT_FOUND"):
            resolve_git_branch_commit_sha("specialty/missing", repo)
        with pytest.raises(ValueError, match="Invalid relative path"):
            read_git_branch_document(repo, "../secret.md", "master")
        with pytest.raises(ValueError, match="Path escapes root"):
            read_git_branch_document(repo, "docs/escape.md", "master")
        with pytest.raises(ValueError, match="Access denied"):
            read_git_branch_document(repo, "notes.txt", "master")
        with pytest.raises(FileNotFoundError, match="not found on branch_ref"):
            read_git_branch_document(repo, "docs/absent.md", "master")

    def test_orchestrate_dmcp_branch_projection_nominal_chained_and_fallbacks(
        self, tmp_path: Path
    ) -> None:
        """Project DMCP branch context frames, chain parent hashes, and fail-closed on errors."""
        # Arrange
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        sec_val = "".join(("sec", "-1"))

        # Act
        first = orchestrate_dmcp_branch_projection(
            repo,
            "node-a",
            {"branch_ref": "specialty/grid", "target_globs": ["docs/**"]},
            default_secret=sec_val,
        )
        chained = orchestrate_dmcp_branch_projection(
            repo,
            "node-a",
            {
                "branch_ref": "specialty/grid",
                "context_frame_token": first["context_frame_token"],
                "target_path": "docs/spec.md",
            },
            default_secret=sec_val,
        )
        bad_incoming = orchestrate_dmcp_branch_projection(
            repo,
            "node-a",
            {"branch_ref": "specialty/grid", "context_frame_token": "bad.token"},
            default_secret=sec_val,
        )
        missing_branch = orchestrate_dmcp_branch_projection(
            repo, "node-a", {"branch_ref": "specialty/nope"}, default_secret=sec_val
        )
        unsafe_branch = orchestrate_dmcp_branch_projection(
            repo, "node-a", {"branch_ref": "-bad"}, default_secret=sec_val
        )

        # Assert
        assert first["verified"] is True
        assert chained["parent_frame_hash"] == first["frame_hash"]
        assert bad_incoming["fallback_activated"] is True
        assert missing_branch["fallback_activated"] is True
        assert unsafe_branch["fallback_activated"] is True

    def test_orchestrate_grcc_capsule_ref_lifecycle_and_deep_index(self, tmp_path: Path) -> None:
        """Probe, seal genesis + child, unfold, index, and prune refs/zcg/capsules/*."""
        # Arrange
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        token = seal_single_capsule({"lvl": "L1", "next": "L2"}, {"ok": True}, b"k" * 32)
        fp, ref = compute_grcc_scope_fingerprint("", "", "")

        # Act
        probe_miss = orchestrate_grcc_capsule_ref(repo, "node-a", {"grcc_op": "probe"})
        seal_1 = orchestrate_grcc_capsule_ref(
            repo, "node-a", {"grcc_op": "seal", "capsule_token": token}
        )
        seal_2 = orchestrate_grcc_capsule_ref(
            repo, "node-a", {"grcc_op": "seal", "capsule_token": token}
        )
        probe_local = orchestrate_grcc_capsule_ref(repo, "node-a", {"grcc_op": "probe"})
        probe_remote = orchestrate_grcc_capsule_ref(
            repo, "node-a", {"grcc_op": "probe", "remote": str(repo)}
        )
        unfolded = orchestrate_grcc_capsule_ref(repo, "node-a", {"grcc_op": "unfold"})
        deep_idx = discover_deep_context_index(
            repo,
            [{"name": "gov-es", "layer_role": "knowledge", "relative_path": "layers/gov-es"}],
        )
        empty_idx = discover_deep_context_index(tmp_path, [])
        pruned = orchestrate_grcc_capsule_ref(repo, "node-a", {"grcc_op": "prune"})

        # Assert
        assert ref.endswith(fp)
        assert probe_miss["exists"] is False
        assert seal_1["parent_commit_sha"] is None
        assert seal_2["parent_commit_sha"] == seal_1["commit_sha"]
        assert probe_local["exists"] is True
        assert probe_remote["exists"] is True
        assert unfolded["capsule_token"] == token
        assert "specialty/grid" in deep_idx["specialty_branches"]
        assert len(deep_idx["grcc_capsule_refs"]) == 1
        assert len(deep_idx["knowledge_nodes"]) == 1
        assert empty_idx["specialty_branches"] == []
        assert pruned["pruned"] is True
        with pytest.raises(ValueError, match="Invalid grcc_op"):
            orchestrate_grcc_capsule_ref(repo, "node-a", {"grcc_op": "invalid"})
        with pytest.raises(ValueError, match="Missing required 'capsule_token'"):
            orchestrate_grcc_capsule_ref(repo, "node-a", {"grcc_op": "seal"})
        with pytest.raises(ValueError, match="GRCC_CAPSULE_REF_NOT_FOUND"):
            orchestrate_grcc_capsule_ref(repo, "node-a", {"grcc_op": "unfold"})
