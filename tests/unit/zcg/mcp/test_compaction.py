"""Unit tests for zcg.mcp.compaction.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from zcg.capsules.constants import L2_EXCERPT_MAX_CHARS
from zcg.mcp.compaction import CompactionMixin


def _seed_compaction_repo(repo: Path) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@local",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@local",
        "HOME": str(repo),
    }
    subprocess.run(["git", "init", "-b", "master", str(repo)], check=True, env=env)
    for d in (
        "system",
        "docs/guides",
        "antigravity/.gemini/config",
        "templates/human-stack/academic-base/rules",
        "templates/human-stack/academic-base/skills/sopen",
    ):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (repo / "README.md").write_text("# Root\nTopology overview.\n", encoding="utf-8")
    (repo / "system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "acad-node",
                "layer_role": "department",
                "human_stack": ["domain-neuro:M1", "soft-socratic-coach"],
            }
        ),
        encoding="utf-8",
    )
    (repo / "antigravity/.gemini/config/AGENTS.md").write_text(
        "# Global Rules\n## Zero-Cloud Topology Mandate\n**Mandate:** Keep strict symmetry.\n",
        encoding="utf-8",
    )
    long_body = "Zero-Cloud Topology architecture guide. " * 60
    (repo / "docs/guides/01_guide.md").write_text(
        f"# Guide\n## Zero-Cloud Topology Intro\n{long_body}\n", encoding="utf-8"
    )
    (repo / "templates/human-stack/academic-base/template.json").write_text(
        json.dumps({"name": "academic-base", "stack_group": "human-stack"}), encoding="utf-8"
    )
    (repo / "templates/human-stack/academic-base/rules/academic.md").write_text(
        "# Academic\n## Draft Proposal\nZero-Cloud Topology draft.\n", encoding="utf-8"
    )
    (repo / "templates/human-stack/academic-base/skills/sopen/SKILL.md").write_text(
        "# Skill\nZero-Cloud Topology skill.\n", encoding="utf-8"
    )
    assert len(long_body) > L2_EXCERPT_MAX_CHARS
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, env=env)


class TestMCPCompaction:
    """Verify session resonance key resolution and multi-resolution query_governance_rules."""

    def test_query_governance_rules_resolutions_grades_branch_and_viewpoints(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Query L0/L1/L2 capsules, filter E3 grades, project Git branches, and sort M1 guides."""
        # Arrange
        repo = tmp_path / "repo"
        repo.mkdir()
        _seed_compaction_repo(repo)
        node = CompactionMixin(repo_dir=repo, log_dir=tmp_path / "logs")

        # Act
        monkeypatch.setenv("ZCG_RESONANCE_KEY", "env-sec")
        assert node.resolve_resonance_secret() == b"env-sec"
        monkeypatch.delenv("ZCG_RESONANCE_KEY")
        l0 = json.loads(
            node.tool_query_governance_rules(
                {
                    "query": "zero cloud topology",
                    "resolution": "L0",
                    "target_path": "docs/guides/01_guide.md",
                }
            )["content"][0]["text"]
        )
        l1 = json.loads(
            node.tool_query_governance_rules(
                {
                    "query": "zero cloud topology",
                    "resolution": "L1",
                    "min_epistemic_grade": "E3",
                    "include_capsules": False,
                    "layer": "root",
                }
            )["content"][0]["text"]
        )
        for scoped in ("global", "templates", "docs"):
            node.tool_query_governance_rules({"query": "zero cloud topology", "scope": scoped})
        l2 = json.loads(
            node.tool_query_governance_rules(
                {
                    "query": "zero cloud topology",
                    "resolution": "L2",
                    "branch_ref": "master",
                    "resonance_key": "explicit-k",
                }
            )["content"][0]["text"]
        )

        # Assert
        assert l0["consumer_viewpoint"] == "academic-tutor-m1-m2"
        assert l0["matches"][0]["file"] == "docs/guides/01_guide.md"
        assert "surface_preview" in l0["matches"][0]
        assert all(m["epistemic_grade"] == "E3" for m in l1["matches"])
        assert l1["matches"][0]["capsule_token"] is None
        assert "axiom_skeleton" in l1["matches"][0]
        assert l2["dmcp_projection"]["zero_checkout"] is True
        assert l2["truncated"] is True

    def test_query_governance_rules_rejects_invalid_arguments(self, tmp_path: Path) -> None:
        """Raise ValueError on empty query or invalid resolution, environment, or grade."""
        # Arrange
        node = CompactionMixin(repo_dir=tmp_path)

        # Act
        with pytest.raises(ValueError, match="non-empty string"):
            node.tool_query_governance_rules({"query": "  "})
        with pytest.raises(ValueError, match="Invalid resolution"):
            node.tool_query_governance_rules({"query": "ok", "resolution": "L9"})
        with pytest.raises(ValueError, match="Invalid environment"):
            node.tool_query_governance_rules({"query": "ok", "environment": "mars"})
        # Assert
        with pytest.raises(ValueError, match="Invalid min_epistemic_grade"):
            node.tool_query_governance_rules({"query": "ok", "min_epistemic_grade": "E9"})
