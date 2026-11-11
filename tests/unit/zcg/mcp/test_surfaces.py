"""Unit tests for zcg.mcp.surfaces.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.capsules.constants import L2_EXCERPT_MAX_CHARS
from zcg.mcp.surfaces import SurfaceGovernanceMixin


def _seed_surfaces_repo(repo: Path) -> None:
    for d in (
        "system",
        "docs",
        "antigravity/.gemini/config",
        "layers/dept-sec/system",
        "layers/dept-sec/antigravity/.gemini/config",
        "layers/pruned-layer/system",
        "layers/ephemeral-project-bridge/system",
        "layers/ephemeral-project-bridge/antigravity/.gemini/config",
    ):
        (repo / d).mkdir(parents=True, exist_ok=True)
    long_sec = "Strict security law. " * 90
    assert len(long_sec) > L2_EXCERPT_MAX_CHARS
    (repo / "antigravity/.gemini/config/AGENTS.md").write_text(
        f"# Root\n## Sec 1\n{long_sec}\n## Sec 2\nB\n## Sec 3\nC\n## Sec 4\nD\n",
        encoding="utf-8",
    )
    (repo / "docs/template.md").write_text("# Canonical\n", encoding="utf-8")
    (repo / "system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "root-node",
                "layer_role": "corporate",
                "precedence": 20,
                "baseline_guardrails": ["Root Baseline"],
                "environments": {"pro": {"default_guardrails": ["Root Pro"]}},
                "surface_bindings": [
                    {
                        "binding_id": "root-sec",
                        "precedence": 20,
                        "mode": "authoritative",
                        "target_globs": ["src/zcg/**"],
                        "rule_files": ["antigravity/.gemini/config/AGENTS.md", "docs/missing.md"],
                        "canonical_templates": ["docs/template.md", "docs/absent_tpl.md"],
                        "invariants": ["Root Inv"],
                        "ephemeral_fork_policy": {"bot_role": "security-auditor-bot"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (repo / "layers/dept-sec/antigravity/.gemini/config/AGENTS.md").write_text(
        "# Dept\n## Dept Rule\nEnforce RBAC.\n", encoding="utf-8"
    )
    (repo / "layers/dept-sec/system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "dept-sec",
                "layer_role": "department",
                "precedence": 20,
                "surface_bindings": [
                    {
                        "binding_id": "dept-sec-auth",
                        "precedence": 20,
                        "mode": "authoritative",
                        "target_globs": ["src/zcg/**"],
                        "rule_files": ["antigravity/.gemini/config/AGENTS.md"],
                        "invariants": ["Dept Inv"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (repo / "layers/pruned-layer/system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "pruned-layer",
                "layer_role": "squad",
                "precedence": 50,
                "surface_bindings": [{"binding_id": "other", "target_globs": ["surfaces/web/**"]}],
            }
        ),
        encoding="utf-8",
    )
    (repo / "layers/ephemeral-project-bridge/antigravity/.gemini/config/AGENTS.md").write_text(
        "# Bridge\n## Local\nBridge body.\n", encoding="utf-8"
    )
    (repo / "layers/ephemeral-project-bridge/system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "bridge-local",
                "layer_role": "squad",
                "precedence": 60,
            }
        ),
        encoding="utf-8",
    )


class TestMCPSurfaces:
    """Verify 3D surface governance projection, precedence collision alerts, and validations."""

    def test_resolve_surface_governance_weaving_resolutions_and_warnings(
        self, tmp_path: Path
    ) -> None:
        """Weave multi-layer bindings across L0/L1/L2, prune unmatched, and emit warnings."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_surfaces_repo(repo)
        node = SurfaceGovernanceMixin(repo_dir=repo, log_dir=tmp_path / "logs")

        # Act
        adaptive = json.loads(
            node.tool_resolve_surface_governance(
                {"target_path": "src/zcg/core/constants.py", "environment": "pro"}
            )["content"][0]["text"]
        )
        l0 = json.loads(
            node.tool_resolve_surface_governance(
                {
                    "target_path": "src/zcg/core/constants.py",
                    "resolution_override": "L0",
                    "include_capsules": False,
                }
            )["content"][0]["text"]
        )
        l1 = json.loads(
            node.tool_resolve_surface_governance(
                {
                    "architectural_plane": "domain",
                    "resolution_override": "L1",
                    "resonance_key": "k1",
                }
            )["content"][0]["text"]
        )
        short_repo = tmp_path / "short_repo"
        for d in ("system", "antigravity/.gemini/config"):
            (short_repo / d).mkdir(parents=True)
        (short_repo / "antigravity/.gemini/config/AGENTS.md").write_text(
            "# Short\n## Rule\nOk.\n", encoding="utf-8"
        )
        short_res = json.loads(
            SurfaceGovernanceMixin(repo_dir=short_repo).tool_resolve_surface_governance(
                {"scope": "core"}
            )["content"][0]["text"]
        )

        # Assert
        assert short_res["truncated"] is False
        assert adaptive["participating_layers_count"] == 3
        assert adaptive["pruned_layers_count"] == 1
        assert adaptive["truncated"] is True
        assert len(adaptive["ephemeral_delegation_advisories"]) == 1
        codes = {w["code"] for w in adaptive["warnings"]}
        assert "SURFACE_PRECEDENCE_COLLISION" in codes
        assert "SURFACE_ASSET_MISSING" in codes
        assert "RESPONSE_TRUNCATED" in codes
        assert "surface_preview" in l0["resolved_bindings"][0]["sections"][0]
        assert "axiom_skeleton" in l1["resolved_bindings"][0]["sections"][0]

    def test_resolve_surface_governance_rejects_invalid_inputs_and_manifests(
        self, tmp_path: Path
    ) -> None:
        """Reject invalid selectors, environments, resolutions, precedences, and binding modes."""
        # Arrange
        repo = tmp_path / "repo"
        (repo / "system").mkdir(parents=True)
        node = SurfaceGovernanceMixin(repo_dir=repo)

        # Act
        with pytest.raises(ValueError, match="Invalid architectural_plane"):
            node.tool_resolve_surface_governance({"architectural_plane": "bad"})
        with pytest.raises(ValueError, match="At least one surface selector"):
            node.tool_resolve_surface_governance({})
        with pytest.raises(ValueError, match="Invalid environment"):
            node.tool_resolve_surface_governance({"scope": "core", "environment": "bad"})
        with pytest.raises(ValueError, match="Invalid resolution_override"):
            node.tool_resolve_surface_governance({"scope": "core", "resolution_override": "L9"})

        (repo / "system/zcg-node.json").write_text(
            json.dumps({"schema_version": "zcg-node-v1", "precedence": 150}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="Invalid layer precedence"):
            node.tool_resolve_surface_governance({"scope": "core"})

        (repo / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "schema_version": "zcg-node-v1",
                    "precedence": 10,
                    "surface_bindings": [{"precedence": -5}],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Invalid binding precedence"):
            node.tool_resolve_surface_governance({"scope": "core"})

        (repo / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "schema_version": "zcg-node-v1",
                    "precedence": 10,
                    "surface_bindings": [{"mode": "chaos"}],
                }
            ),
            encoding="utf-8",
        )
        # Assert
        with pytest.raises(ValueError, match="Invalid surface_binding mode"):
            node.tool_resolve_surface_governance({"scope": "core"})
