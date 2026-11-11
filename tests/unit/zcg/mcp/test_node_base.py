"""Unit tests for zcg.mcp.node_base.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.capsules.constants import MAX_LOG_FILE_BYTES
from zcg.core.constants import AGENTS_MD_MAX_BYTES, AGENTS_MD_WARN_BYTES
from zcg.mcp.node_base import MCPNodeBase


def _seed_node_workspace(repo: Path) -> None:
    for d in (
        "system",
        "docs",
        "antigravity/.gemini/config/skills/sopen",
        "templates/human-stack/universal-base/rules",
        "layers/.hidden",
        "layers/bare-sub",
        "layers/no-up-sub/system",
        "layers/gov-es/system",
        "layers/orphan-sub/system",
    ):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "layers/no-up-sub/system/zcg-node.json").write_text(
        json.dumps({"schema_version": "zcg-node-v1", "layer_id": "no-up-sub"}), encoding="utf-8"
    )
    (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (repo / "README.md").write_text("# Root\n", encoding="utf-8")
    (repo / "docs/README.md").write_text("# Docs Index\n", encoding="utf-8")
    (repo / "system/packages-manual.txt").write_text("git\n", encoding="utf-8")
    (repo / "system/nvm-default.txt").write_text("22\n", encoding="utf-8")
    (repo / "system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "node-root",
                "layer_role": "workstation",
                "default_stack_templates": ["universal-base", "missing-pack"],
            }
        ),
        encoding="utf-8",
    )
    (repo / "antigravity/.gemini/config/AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo / "antigravity/.gemini/config/hooks.json").write_text('{"hooks":{}}\n', encoding="utf-8")
    (repo / "antigravity/.gemini/config/skills/sopen/SKILL.md").write_text(
        "---\nname: sopen\ndescription: Open session\n---\n", encoding="utf-8"
    )
    (repo / "templates/human-stack/universal-base/template.json").write_text(
        json.dumps({"name": "universal-base", "stack_group": "human-stack"}), encoding="utf-8"
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
    (repo / "layers/orphan-sub/system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "orphan-sub",
                "upstream_layer": {},
            }
        ),
        encoding="utf-8",
    )


class TestMCPNodeBase:
    """Verify MCPNodeBase state, log rotation, warnings, containment, prompts, and resources."""

    def test_memory_reaping_jsonl_rotation_and_layer_warnings(self, tmp_path: Path) -> None:
        """Evict expired memory forks, rotate oversized JSONL logs, and emit layer alerts."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_node_workspace(repo)
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "mcp_events.jsonl").write_bytes(b"x" * MAX_LOG_FILE_BYTES)
        silent_node = MCPNodeBase(repo_dir=repo, log_dir=None)
        node = MCPNodeBase(
            repo_dir=repo,
            layer_id_override="override-id",
            layer_role_override="department",
            log_dir=log_dir,
        )
        node.ephemeral_memory_store["eph-old"] = {"expires_at_epoch": 10.0}
        node.ephemeral_memory_store["eph-live"] = {"expires_at_epoch": 500.0}

        # Act
        silent_node.write_jsonl("mcp_events.jsonl", {"noop": True})
        reaped = node.reap_expired_memory_forks(now_epoch=100.0)
        node.write_jsonl("mcp_events.jsonl", {"ok": True})
        crit_w = node.evaluate_layer_warnings(repo, AGENTS_MD_MAX_BYTES + 10)
        near_w = node.evaluate_layer_warnings(repo, AGENTS_MD_WARN_BYTES)
        child_w = node.evaluate_layer_warnings(repo / "layers/gov-es", 100)
        root_m = node.load_layer_manifest()

        # Assert
        assert reaped == ["eph-old"]
        assert "eph-live" in node.ephemeral_memory_store
        assert (log_dir / "mcp_events.jsonl.1").is_file()
        assert any(w["code"] == "TOKEN_BUDGET_EXCEEDED" for w in crit_w)
        assert any(w["code"] == "TEMPLATE_PACK_MISSING" for w in crit_w)
        assert any(w["code"] == "SUBTREE_LINEAGE_WARNING" for w in crit_w)
        assert any(w["code"] == "TOKEN_BUDGET_NEAR_LIMIT" for w in near_w)
        assert child_w == []
        assert root_m["layer_id"] == "override-id"
        assert root_m["layer_role"] == "department"

    def test_workspace_override_layer_resolution_and_path_containment(self, tmp_path: Path) -> None:
        """Resolve overrides/layers and reject bad schemas, traversal, and escaped paths."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_node_workspace(repo)
        (repo / "docs/escape.md").symlink_to(tmp_path / "outside.md")
        (repo / "secret.py").write_text("x = 1\n", encoding="utf-8")
        bad_node_dir = tmp_path / "bad_schema"
        (bad_node_dir / "system").mkdir(parents=True)
        (bad_node_dir / "system/zcg-node.json").write_text(
            json.dumps({"schema_version": "zcg-node-v0"}), encoding="utf-8"
        )
        bare_dir = tmp_path / "bare"
        bare_dir.mkdir()
        node = MCPNodeBase(repo_dir=repo)
        bare_node = MCPNodeBase(repo_dir=bare_dir)

        # Act
        same_ws = node.resolve_workspace_override("")
        explicit_ws = node.resolve_workspace_override(str(repo))
        root_lyr = node.resolve_layer_dir("self")
        child_lyr = node.resolve_layer_dir("gov-es")
        safe_doc = node.resolve_safe_path("docs/README.md")
        empty_mounted = bare_node.discover_mounted_layers()

        # Assert
        assert same_ws == repo.resolve()
        assert explicit_ws == repo.resolve()
        assert root_lyr == repo.resolve()
        assert child_lyr == (repo / "layers/gov-es").resolve()
        assert safe_doc.name == "README.md"
        assert empty_mounted == []
        with pytest.raises(ValueError, match=r"Unsupported zcg-node\.json"):
            node.load_layer_manifest(bad_node_dir)
        with pytest.raises(ValueError, match="Invalid workspace_dir"):
            node.resolve_workspace_override(str(bare_dir))
        with pytest.raises(ValueError, match="Unknown or unmounted layer"):
            node.resolve_layer_dir("unknown-layer")
        with pytest.raises(ValueError, match="Invalid relative path"):
            node.resolve_safe_path("../README.md")
        with pytest.raises(ValueError, match="Path escapes root"):
            node.resolve_safe_path("docs/escape.md")
        with pytest.raises(ValueError, match="outside readable surfaces"):
            node.resolve_safe_path("secret.py")
        with pytest.raises(FileNotFoundError, match="Document not found"):
            node.resolve_safe_path("docs/missing.md")

    def test_prompts_and_all_nine_zcg_resources(self, tmp_path: Path) -> None:
        """Render all three MCP prompts and read all nine zcg://* resources."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_node_workspace(repo)
        node = MCPNodeBase(repo_dir=repo, log_dir=tmp_path / "logs")

        # Act
        prompts = node.list_prompts()
        rendered = [node.get_prompt(p["name"], {"workflow_goal": "sync"}) for p in prompts]
        resources = node.list_resources()
        loaded_resources = [node.read_resource(r["uri"]) for r in resources]
        (repo / "system/nvm-default.txt").unlink()
        no_nvm = json.loads(node.read_resource("zcg://system/manifests")["text"])

        # Assert
        assert len(prompts) == 3
        assert len(rendered) == 3
        assert len(resources) == 9
        assert len(loaded_resources) == 9
        assert no_nvm["nvm_default"] == "none"
        with pytest.raises(ValueError, match="Unknown prompt name"):
            node.get_prompt("unknown")
        with pytest.raises(ValueError, match="Unknown resource URI"):
            node.read_resource("zcg://unknown")
