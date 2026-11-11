"""Unit tests for zcg.mcp.federation.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from zcg.mcp.federation import FederationMixin


def _seed_federation_repo(repo: Path) -> None:
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
        "docs",
        "antigravity/.gemini/config/skills/sopen",
        "layers/dept-ops/system",
    ):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (repo / "docs/README.md").write_text("# Index\n", encoding="utf-8")
    (repo / "antigravity/.gemini/config/AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo / "antigravity/.gemini/config/skills/sopen/SKILL.md").write_text(
        "---\nname: sopen\ndescription: open\n---\n", encoding="utf-8"
    )
    mcps = [
        {"mcp_id": f"mcp-{i}", "role": "analytics" if i == 0 else "ops", "environments": ["pro"]}
        for i in range(6)
    ]
    (repo / "system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "corp-root",
                "layer_role": "corporate",
                "baseline_guardrails": ["Corp Base"],
                "federated_mcps": mcps,
            }
        ),
        encoding="utf-8",
    )
    (repo / "layers/dept-ops/system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "dept-ops",
                "layer_role": "department",
                "upstream_layer": {
                    "repository": "https://github.com/mtwuser/zero-cloud-gravity.git"
                },
                "environments": {"pro": {"default_guardrails": ["Dept Pro"]}},
                "federated_mcps": [{"mcp_id": "dept-mcp", "role": "ops", "environments": ["pro"]}],
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, env=env)


class TestMCPFederation:
    """Verify node overview, drift audit, document reads, MCP discovery, and comparisons."""

    def test_overview_read_document_discover_mcps_and_compare_patterns(
        self, tmp_path: Path
    ) -> None:
        """Execute overview, disk/branch reads, federated MCP fanout/filtering, and comparisons."""
        # Arrange
        repo = tmp_path / "repo"
        repo.mkdir()
        _seed_federation_repo(repo)
        node = FederationMixin(repo_dir=repo, log_dir=tmp_path / "logs")

        # Act
        ov = json.loads(node.tool_get_layer_overview({})["content"][0]["text"])
        bare_ov = json.loads(
            FederationMixin(repo_dir=tmp_path).tool_get_layer_overview({})["content"][0]["text"]
        )
        doc_disk = node.tool_read_layer_document({"relative_path": "docs/README.md"})["content"][0][
            "text"
        ]
        doc_br = node.tool_read_layer_document(
            {"relative_path": "docs/README.md", "branch_ref": "master"}
        )["content"][0]["text"]
        fanout = json.loads(node.tool_discover_federated_mcps({})["content"][0]["text"])
        filtered = json.loads(
            node.tool_discover_federated_mcps({"filter_role": "ops", "environment": "pro"})[
                "content"
            ][0]["text"]
        )
        single_lyr = json.loads(
            node.tool_discover_federated_mcps({"layer": "dept-ops"})["content"][0]["text"]
        )
        comp_all = json.loads(
            node.tool_compare_layer_patterns(
                {"project_rules": ["novel.md"], "project_skills": ["sopen"]}
            )["content"][0]["text"]
        )
        comp_one = json.loads(
            node.tool_compare_layer_patterns({"layer": "dept-ops"})["content"][0]["text"]
        )

        # Assert
        assert ov["channel_1_node_and_system_state"]["layer_id"] == "corp-root"
        assert bare_ov["channel_4_navigable_docs_and_federated_mcps"]["documents"] == []
        assert doc_disk == "# Index\n"
        assert doc_br == "# Index\n"
        assert fanout["warnings"][0]["code"] == "MCP_FANOUT_WARNING"
        assert filtered["environment_profile"] == {"default_guardrails": ["Dept Pro"]}
        assert single_lyr["federated_mcp_count"] == 1
        assert comp_all["compared_against_layer"] == "all"
        assert comp_one["compared_against_layer"] == "dept-ops"
        with pytest.raises(ValueError, match="Invalid environment"):
            node.tool_discover_federated_mcps({"environment": "mars"})

    def test_audit_node_drift_fallback_and_script_failure(self, tmp_path: Path) -> None:
        """Run drift audit via CLI fallbacks and emit NODE_DRIFT_DETECTED on script failure."""
        # Arrange
        repo = tmp_path / "repo"
        repo.mkdir()
        _seed_federation_repo(repo)
        node = FederationMixin(repo_dir=repo, log_dir=tmp_path / "logs")

        # Act
        fallback_res = json.loads(
            node.tool_audit_node_drift({"mode": "both"})["content"][0]["text"]
        )
        node.tool_audit_node_drift({"mode": "verify-repo"})
        node.tool_audit_node_drift({"mode": "system-audit"})
        (repo / "scripts").mkdir(exist_ok=True)
        v_sh = repo / "scripts/verify-repo.sh"
        v_sh.write_text(
            "#!/usr/bin/env bash\necho -e '\\x1b[31mfail\\x1b[0m'\nexit 1\n", encoding="utf-8"
        )
        v_sh.chmod(0o755)
        a_sh = repo / "audit.sh"
        a_sh.write_text("#!/usr/bin/env bash\necho ok\nexit 0\n", encoding="utf-8")
        a_sh.chmod(0o755)
        script_res = json.loads(node.tool_audit_node_drift({"mode": "both"})["content"][0]["text"])
        ws_repo = tmp_path / "ws-node"
        (ws_repo / "system").mkdir(parents=True)
        (ws_repo / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "schema_version": "zcg-node-v1",
                    "layer_id": "iso-pc",
                    "layer_role": "workstation",
                }
            ),
            encoding="utf-8",
        )
        ws_audit = json.loads(
            FederationMixin(repo_dir=ws_repo).tool_audit_node_drift({"mode": "system-audit"})[
                "content"
            ][0]["text"]
        )

        # Assert
        assert "verify_repo" in fallback_res["checks"]
        assert script_res["healthy"] is False
        assert script_res["warnings"][0]["code"] == "NODE_DRIFT_DETECTED"
        assert "system_audit" in ws_audit["checks"]
        with pytest.raises(ValueError, match="Invalid mode"):
            node.tool_audit_node_drift({"mode": "invalid"})
