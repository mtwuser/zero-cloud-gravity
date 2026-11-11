"""Unit tests for zcg.capsules.surfaces.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zcg.capsules.codec import parse_capsule_envelope
from zcg.capsules.surfaces import (
    binding_matches_surface,
    build_section_capsule,
    compare_project_patterns_multilayer,
    compute_binding_specificity,
    infer_plane_from_path,
    infer_scope_from_path,
)


class TestCapsuleSurfaces:
    """Verify 3D surface selectors, section capsule minting, and multi-layer pattern routing."""

    def test_infer_plane_scope_matching_and_specificity(self) -> None:
        """Infer planes/scopes, match glob/plane/scope/trait selectors, and score specificity."""
        # Arrange
        binding = {
            "target_globs": ["src/zcg/billing/**"],
            "architectural_planes": ["domain"],
            "scopes": ["payments"],
            "traits": ["pci"],
        }

        # Act
        plane_test = infer_plane_from_path("tests/unit/test_core.py")
        plane_unknown = infer_plane_from_path("Makefile")
        scope_feat = infer_scope_from_path("src/zcg/billing/service.py")
        scope_empty = infer_scope_from_path("README.md")
        matched_via_glob_seg = binding_matches_surface(
            binding, "src/zcg/billing/model.py", "domain", "billing", {"pci"}
        )
        unmatched_trait = binding_matches_surface(
            binding, "src/zcg/billing/model.py", "domain", "billing", {"public"}
        )
        spec_full = compute_binding_specificity(binding)
        spec_wild = compute_binding_specificity({})

        # Assert
        assert plane_test == "testing"
        assert plane_unknown == ""
        assert scope_feat == "billing"
        assert scope_empty == ""
        assert matched_via_glob_seg is True
        assert unmatched_trait is False
        assert spec_full == 90
        assert spec_wild == 0

    def test_build_section_capsule_minting_and_pro_tier_gate(self) -> None:
        """Mint section promoter codons and rcap1 capsules including pro-environment L3 tiering."""
        # Arrange
        l3_links = [{"path": "docs/spec.md", "estimated_tokens": 50, "sha256": "0123456789abcdef"}]

        # Act
        codon_dev, tok_dev = build_section_capsule(
            issuer_id="node-a",
            resolution="L1",
            layer_name="root",
            rel_in_layer="docs/architecture/01.md",
            heading="Core Topology",
            start_line=1,
            end_line=12,
            scope="architecture",
            l1_skeleton="## Core Topology\n- Pure DAG",
            l2_excerpt="Full excerpt",
            l2_full="Full section body",
            l3_links=l3_links,
            env_scope="dev",
            secret=b"sec-1",
            heading_depth=2,
            section_path="Root > Core Topology",
        )
        _, tok_pro = build_section_capsule(
            issuer_id="node-a",
            resolution="L2",
            layer_name="root",
            rel_in_layer="SECURITY.md",
            heading="Security Law",
            start_line=1,
            end_line=5,
            scope="security",
            l1_skeleton="## Security Law",
            l2_excerpt="Mandate",
            l2_full="Mandate",
            l3_links=[],
            env_scope="pro",
            secret=b"sec-1",
            key_required=True,
        )
        hdr_dev, _, _, _ = parse_capsule_envelope(tok_dev)
        hdr_pro, _, _, _ = parse_capsule_envelope(tok_pro)

        # Assert
        assert codon_dev["epistemic_grade"] == "E2"
        assert codon_dev["has_l3_substrate"] is True
        assert hdr_dev["lvl"] == "L1"
        assert hdr_dev["next"] == "L2"
        assert hdr_pro["cap"] == "pro"
        assert hdr_pro["kr"] is True

    def test_compare_project_patterns_multilayer_routes_child_and_root_items(
        self, tmp_path: Path
    ) -> None:
        """Compare rules and skills across root and child layers with and without templates."""
        # Arrange
        root_dir = tmp_path / "root"
        (root_dir / "antigravity/.gemini/config/skills/sopen").mkdir(parents=True)
        (root_dir / "antigravity/.gemini/config/skills/sopen/SKILL.md").write_text(
            "---\nname: sopen\ndescription: open\n---\n", encoding="utf-8"
        )
        (root_dir / "antigravity/.gemini/config/AGENTS.md").write_text("# Root\n", encoding="utf-8")
        t_root = root_dir / "templates/context-stack/software-engineering"
        (t_root / "rules").mkdir(parents=True)
        (t_root / "skills/testing").mkdir(parents=True)
        (t_root / "template.json").write_text(
            json.dumps({"name": "software-engineering"}), encoding="utf-8"
        )
        (t_root / "rules/software-engineering.md").write_text("# SE\n", encoding="utf-8")
        (t_root / "skills/testing/SKILL.md").write_text(
            "---\nname: testing\ndescription: test\n---\n", encoding="utf-8"
        )

        child_tpl = tmp_path / "child_tpl"
        (child_tpl / "templates/context-stack/payments-pack/rules").mkdir(parents=True)
        (child_tpl / "templates/context-stack/payments-pack/template.json").write_text(
            json.dumps({"name": "payments-pack"}), encoding="utf-8"
        )
        child_bare = tmp_path / "child_bare"
        child_bare.mkdir()

        target_dirs: list[tuple[str, Path, dict[str, Any]]] = [
            ("root", root_dir, {"layer_id": "root-id", "layer_role": "workstation"}),
            (
                "payments",
                child_tpl,
                {
                    "layer_id": "dept-payments",
                    "layer_role": "department",
                    "surface_bindings": [{"scopes": ["ledger"], "traits": ["pci", "*"]}],
                },
            ),
            ("telemetry", child_bare, {"layer_id": "squad-telemetry", "layer_role": "squad"}),
        ]

        # Act
        multi = compare_project_patterns_multilayer(
            root_dir,
            [{"name": "payments"}, {"name": "telemetry"}],
            project_rules=[
                "layer-20-payments-rule.md",
                "software-engineering.md",
                "ledger-guard.md",
                "telemetry-alert.md",
                "universal-novel.md",
            ],
            project_skills=["sopen", "testing", "telemetry-probe", "fresh-skill"],
            target_dirs=target_dirs,
        )
        bare_root = compare_project_patterns_multilayer(
            child_bare,
            [],
            project_rules=["bare-rule.md"],
            project_skills=[],
            target_dirs=[
                ("root", child_bare, {"layer_id": "bare-id", "layer_role": "workstation"})
            ],
        )

        # Assert
        assert multi["compared_against_layer"] == "all"
        assert multi["materialized_layer_rules"] == ["layer-20-payments-rule.md"]
        routes = {item["item"]: item for item in multi["promotion_routing"]}
        assert routes["ledger-guard.md"]["target_layer"] == "payments"
        assert "templates/payments-pack" in routes["ledger-guard.md"]["target_destination"]
        assert routes["telemetry-alert.md"]["target_layer"] == "telemetry"
        assert "AGENTS.md" in routes["telemetry-alert.md"]["target_destination"]
        assert routes["telemetry-probe"]["target_layer"] == "telemetry"
        assert routes["universal-novel.md"]["target_layer"] == "root"
        assert routes["fresh-skill"]["target_scope"] == "global-skills-root"
        assert bare_root["compared_against_layer"] == "bare-id"
        assert bare_root["promotion_routing"][0]["target_scope"] == "global-agents-root"
