"""Unit tests for zcg.governance.consensus.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance import consensus


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    path = node_dir / NODE_MANIFEST_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestConsensus:
    """Verify surface bindings, multi-layer co-owner consensus, and env promotion gates."""

    def test_collect_and_match_authoritative_surface_bindings_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify template binding merge, deduplication, glob matching, and specificity sort."""
        # Arrange
        corp = tmp_path / "corp-iso"
        tpl_a = corp / "templates/context-stack/sec-pack"
        tpl_a.mkdir(parents=True)
        (tpl_a / "template.json").write_text(
            json.dumps(
                {
                    "recommended_surface_bindings": [
                        {
                            "binding_id": "sec-bind",
                            "mode": "authoritative",
                            "target_globs": ["surfaces/data/**", "docs/**/policy.md"],
                            "traits": ["pci", "*"],
                        },
                        {"binding_id": "sec-bind", "mode": "authoritative", "target_globs": ["x"]},
                    ]
                }
            ),
            encoding="utf-8",
        )
        tpl_bad = corp / "templates/context-stack/list-pack"
        tpl_bad.mkdir(parents=True)
        (tpl_bad / "template.json").write_text("[1, 2]", encoding="utf-8")

        corp_m: dict[str, object] = {
            "layer_id": "corp-iso",
            "precedence": 10,
            "default_stack_templates": ["sec-pack", "list-pack", "missing-pack"],
            "surface_bindings": [
                {"binding_id": "", "mode": "transversal", "target_globs": ["**"]},
                "not-a-dict",
            ],
        }
        dept = tmp_path / "dept-iso"
        dept.mkdir()
        dept_m: dict[str, object] = {
            "layer_id": "dept-iso",
            "precedence": 30,
            "surface_bindings": [
                {
                    "binding_id": "dept-data",
                    "mode": "authoritative",
                    "target_globs": ["surfaces/data/ledger.json"],
                    "traits": [],
                }
            ],
        }

        # Act
        eff = consensus.collect_layer_effective_bindings(corp, corp_m)
        hits = consensus.match_authoritative_surface_bindings(
            [("dept-iso", dept, dept_m), ("corp-iso", corp, corp_m)],
            ["", "surfaces/data/ledger.json", "docs/nested/policy.md", "unmatched.txt"],
        )

        # Assert
        assert len(eff) == 2
        assert consensus._glob_matches("any/file.py", "**") is True
        assert len(hits) == 2
        assert hits[0]["owning_layer_id"] == "corp-iso"
        assert len(hits[0]["co_owning_layers"]) == 2

    def test_evaluate_multilayer_surface_consensus_across_states_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify dev simulation, internal root override, divergence, and escalation paths."""
        # Arrange
        ws = tmp_path / "squad-iso"
        _write_manifest(
            ws,
            {
                "layer_id": "squad-iso",
                "layer_role": "squad",
                "precedence": 50,
                "governing_root_id": "corp-iso",
            },
        )
        dept = tmp_path / "dept-iso"
        _write_manifest(
            dept,
            {
                "layer_id": "dept-iso",
                "layer_role": "department",
                "precedence": 30,
                "governing_root_id": "corp-iso",
            },
        )
        gov = tmp_path / "ministry-iso"
        _write_manifest(
            gov,
            {
                "layer_id": "ministry-iso",
                "layer_role": "corporate",
                "entity_kind": "public-government",
                "precedence": 5,
            },
        )
        ext_corp = tmp_path / "ext-corp"
        _write_manifest(
            ext_corp,
            {"layer_id": "ext-corp", "layer_role": "corporate", "precedence": 10},
        )

        def _hit(lid: str, ldir: Path, prec: int, path: str) -> dict[str, object]:
            return {
                "target_path": path,
                "owning_layer_id": lid,
                "owning_layer_dir": str(ldir),
                "precedence": prec,
            }

        root_prof = {"effective_role": "owner", "precedence": 10}
        cons_prof = {"effective_role": "consumer", "precedence": 50}

        # Act — dev simulated + root_ok authorized in pro
        sim_sum, sim_g = consensus.evaluate_multilayer_surface_consensus(
            ws,
            [_hit("dept-iso", dept, 30, "surfaces/a.md")],
            clean_env="dev",
            eff_actor="x@corp.io",
            role_prof=cons_prof,
            wt_txt="",
        )
        assert sim_sum["consensus_status"] == "RECONCILED_FLOW"
        assert sim_g == []

        root_sum, _ = consensus.evaluate_multilayer_surface_consensus(
            ws,
            [_hit("dept-iso", dept, 30, "surfaces/a.md")],
            clean_env="pro",
            eff_actor="root@corp.io",
            role_prof=root_prof,
            wt_txt="",
        )
        assert root_sum["approved_layers"] == ["dept-iso"]

        # Divergent (REJECTED) + pending unauthorized -> ITERATION_REQUIRED
        div_sum, div_g = consensus.evaluate_multilayer_surface_consensus(
            ws,
            [
                _hit("dept-iso", dept, 30, "surfaces/a.md"),
                _hit("ext-corp", ext_corp, 10, "surfaces/b.md"),
            ],
            clean_env="pre",
            eff_actor="nobody@corp.io",
            role_prof=cons_prof,
            wt_txt="- [ ] GOVERNANCE DECISION: REJECTED (surfaces/a.md)",
        )
        assert div_sum["consensus_status"] == "ITERATION_REQUIRED"
        assert len(div_g) == 2

        # Internal BLOCKED -> ESCALATE_TO_ROOT
        int_blk, _ = consensus.evaluate_multilayer_surface_consensus(
            ws,
            [_hit("dept-iso", dept, 30, "surfaces/a.md")],
            clean_env="pro",
            eff_actor="x@corp.io",
            role_prof=cons_prof,
            wt_txt="- [ ] GOVERNANCE DECISION: BLOCKED (dept-iso)",
        )
        assert int_blk["consensus_status"] == "ESCALATE_TO_ROOT"

        # External public-gov & external corp BLOCKED -> ESCALATE_INTER_ENTITY_ROOTS
        ext_blk, ext_g = consensus.evaluate_multilayer_surface_consensus(
            ws,
            [
                _hit("ministry-iso", gov, 5, "surfaces/reg.md"),
                _hit("ext-corp", ext_corp, 10, "surfaces/ext.md"),
            ],
            clean_env="pro",
            eff_actor="x@corp.io",
            role_prof=cons_prof,
            wt_txt=(
                "GOVERNANCE DECISION: BLOCKED (ministry-iso)\n"
                "GOVERNANCE DECISION: BLOCKED (ext-corp)\n"
            ),
        )
        assert ext_blk["consensus_status"] == "ESCALATE_INTER_ENTITY_ROOTS"
        assert any("PUBLIC_REGULATORY_COMPLIANCE_REQUIRED" in g for g in ext_g)
        # Assert
        assert any("CROSS_ENTITY_ESCALATION_REQUIRED" in g for g in ext_g)

    def test_evaluate_environment_promotion_gates_and_semantics_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify env validation, P0/WORKVALI/RBAC/CHANGELOG gates, and dev/pro commands."""
        # Arrange
        parent = tmp_path / "corp-iso"
        _write_manifest(parent, {"layer_id": "corp-iso", "layer_role": "corporate"})
        sub_sib = parent / "layers/dept-sec"
        _write_manifest(
            sub_sib,
            {
                "layer_id": "dept-sec",
                "layer_role": "department",
                "precedence": 20,
                "surface_bindings": [
                    {
                        "binding_id": "sec",
                        "mode": "authoritative",
                        "target_globs": ["sec/**"],
                    }
                ],
            },
        )
        ws = tmp_path / "squad-iso"
        _write_manifest(
            ws,
            {
                "layer_id": "squad-iso",
                "layer_role": "squad",
                "precedence": 50,
                "layer_authority": {
                    "authorized_emails": ["owner@corp-iso.example"],
                    "validator_emails": ["val@corp-iso.example"],
                    "roster": {"members": [{"email": "mem@corp-iso.example"}]},
                },
            },
        )
        (ws / "layers/sub-unit").mkdir(parents=True)
        _write_manifest(ws / "layers/sub-unit", {"layer_id": "sub-unit", "layer_role": "project"})

        # Act — invalid env guard + clean dev technical semantics
        with pytest.raises(ValueError, match="Invalid target_env"):
            consensus.evaluate_environment_promotion(ws, target_env="staging")

        dev_ok = consensus.evaluate_environment_promotion(ws, target_env="dev")
        assert dev_ok["allowed"] is True
        assert dev_ok["phase_semantics"] == "feature-development"
        assert dev_ok["git_promotion_command"] == ""

        # Failing gates across tst, pre, and pro
        (ws / "WORKTASK.md").write_text("- [ ] [P0] Urgent blocker\n", encoding="utf-8")
        (ws / "WORKVALI.md").write_text("- [ ] Pending QA signoff\n", encoding="utf-8")

        tst_fail = consensus.evaluate_environment_promotion(
            ws, target_env="tst", actor_email="guest@corp-iso.example", dry_run=True
        )
        assert any("UNAUTHORIZED_TST_VALIDATION" in g for g in tst_fail["failed_gates"])
        assert any("OPEN_P0_WORKTASKS" in g for g in tst_fail["failed_gates"])

        pre_fail = consensus.evaluate_environment_promotion(
            ws, target_env="pre", actor_email="mem@corp-iso.example", dry_run=True
        )
        assert any("UNVERIFIED_WORKVALI_ITEMS" in g for g in pre_fail["failed_gates"])
        assert any("UNAUTHORIZED_PRE_VALIDATION" in g for g in pre_fail["failed_gates"])

        pro_fail = consensus.evaluate_environment_promotion(
            ws,
            target_env="pro",
            actor_email=None,
            parent_dir=parent,
            changed_files=["sec/policy.md"],
            dry_run=True,
        )
        assert any("MISSING_CHANGELOG" in g for g in pro_fail["failed_gates"])
        assert any("UNAUTHORIZED_PRO_RELEASE" in g for g in pro_fail["failed_gates"])

        # Business node pro pass
        (parent / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        biz_ok = consensus.evaluate_environment_promotion(parent, target_env="pro")
        assert biz_ok["allowed"] is True
        assert biz_ok["phase_semantics"] == "enacted-corporate-policy"
        # Assert
        assert biz_ok["git_promotion_command"] == "git checkout -B master"
