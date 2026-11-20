"""Unit tests for zcg.governance.policy.model_currency.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from zcg.governance.policy.model_currency import (
    CONTINUOUS_CALIBRATION_RULE,
    MODEL_CURRENCY_CONTRACT_REV,
    REQUIRED_AUDIT_CURRENCY_MARKER,
    REQUIRED_MANDATE_12_MARKERS,
    check_model_currency_policy,
    resolve_node_agent_guidance,
)


class TestModelCurrency:
    """Verify orthogonal node agent guidance profiles and Model-Currency drift detection."""

    def test_resolve_guidance_classifies_all_five_orthogonal_profiles_expected(self) -> None:
        """Verify all five orthogonal profiles and precedence rules resolve deterministically."""
        # Arrange
        manifests: dict[str, dict[str, Any]] = {
            "swe_tpl": {"default_stack_templates": ["universal-base", "software-engineering"]},
            "swe_role": {"layer_role": "engine"},
            "tutor_role": {"layer_role": "tutor"},
            "tutor_curr": {"default_stack_templates": ["academic-curriculum"]},
            "tutor_base": {"default_stack_templates": ["academic-base"]},
            "sci_role": {"layer_role": "knowledge"},
            "sci_tpl": {"default_stack_templates": ["scientific-methodology"]},
            "ent_nested": {"entity_identity": {"entity_kind": "enterprise"}},
            "ent_top": {"entity_kind": "enterprise"},
            "ent_role": {"layer_role": "department"},
            "ent_tpl": {"default_stack_templates": ["corporate-operations"]},
            "workstation": {
                "entity_identity": {"entity_kind": "individual"},
                "layer_role": "workstation",
                "default_stack_templates": ["universal-base"],
            },
            "empty": {"entity_identity": "invalid-non-mapping", "default_stack_templates": None},
        }

        # Act
        resolved = {key: resolve_node_agent_guidance(val) for key, val in manifests.items()}

        # Assert
        for item in resolved.values():
            assert item["contract_rev"] == MODEL_CURRENCY_CONTRACT_REV
            assert item["continuous_calibration_rule"] == CONTINUOUS_CALIBRATION_RULE

        assert resolved["swe_tpl"]["profile_id"] == "software-engineering"
        assert resolved["swe_role"]["profile_id"] == "software-engineering"
        assert resolved["swe_tpl"]["profile_label"] == "Software Engineering & Architecture"
        assert resolved["swe_tpl"]["recommended_base_model"] == "Gemini 4 Carbon (High)"
        assert resolved["swe_tpl"]["velocity_alternative"] == "Gemini 4 Neon (High)"
        assert "disjoint-file authors" in resolved["swe_tpl"]["auto_orchestration_summary"]

        assert resolved["tutor_role"]["profile_id"] == "academic-tutor"
        assert resolved["tutor_curr"]["profile_id"] == "academic-tutor"
        assert resolved["tutor_base"]["profile_id"] == "academic-tutor"
        assert resolved["tutor_role"]["recommended_base_model"] == "Gemini 4 Neon (Medium)"

        assert resolved["sci_role"]["profile_id"] == "knowledge-science"
        assert resolved["sci_tpl"]["profile_id"] == "knowledge-science"
        assert resolved["sci_role"]["profile_label"] == "Scientific & Statutory Knowledge Corpus"

        assert resolved["ent_nested"]["profile_id"] == "enterprise-governance"
        assert resolved["ent_top"]["profile_id"] == "enterprise-governance"
        assert resolved["ent_role"]["profile_id"] == "enterprise-governance"
        assert resolved["ent_tpl"]["profile_id"] == "enterprise-governance"
        assert resolved["ent_nested"]["profile_label"] == "Enterprise Operations & Governance"

        assert resolved["workstation"]["profile_id"] == "personal-workstation"
        assert resolved["empty"]["profile_id"] == "personal-workstation"
        assert resolved["workstation"]["recommended_base_model"] == "Gemini 4 Neon (High)"

    def test_check_model_currency_policy_skips_non_engine_workspaces_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify standalone workspaces missing canonical rule files return zero violations."""
        # Arrange
        empty_repo = tmp_path / "empty-repo"
        empty_repo.mkdir()
        only_agents = tmp_path / "only-agents"
        (only_agents / "antigravity/.gemini/config").mkdir(parents=True)
        (only_agents / "antigravity/.gemini/config/AGENTS.md").write_text("plain", encoding="utf-8")
        only_ub = tmp_path / "only-ub"
        (only_ub / "templates/human-stack/universal-base/rules").mkdir(parents=True)
        (only_ub / "templates/human-stack/universal-base/rules/universal-base.md").write_text(
            "plain", encoding="utf-8"
        )

        # Act
        v_empty = check_model_currency_policy(empty_repo)
        v_agents = check_model_currency_policy(only_agents)
        v_ub = check_model_currency_policy(only_ub)

        # Assert
        assert v_empty == []
        assert v_agents == []
        assert v_ub == []

    def test_check_model_currency_policy_detects_drift_and_passes_when_aligned_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Mandate #12 and audit SKILL.md Model-Currency markers are strictly enforced."""
        # Arrange
        agents_rel = Path("antigravity/.gemini/config/AGENTS.md")
        ub_rel = Path("templates/human-stack/universal-base/rules/universal-base.md")
        audit_rel = Path("antigravity/.gemini/config/skills/audit/SKILL.md")
        valid_text = " | ".join(REQUIRED_MANDATE_12_MARKERS)

        clean_no_audit = tmp_path / "clean-no-audit"
        (clean_no_audit / agents_rel.parent).mkdir(parents=True)
        (clean_no_audit / ub_rel.parent).mkdir(parents=True)
        (clean_no_audit / agents_rel).write_text(valid_text, encoding="utf-8")
        (clean_no_audit / ub_rel).write_text(valid_text, encoding="utf-8")

        clean_full = tmp_path / "clean-full"
        (clean_full / agents_rel.parent).mkdir(parents=True)
        (clean_full / ub_rel.parent).mkdir(parents=True)
        (clean_full / audit_rel.parent).mkdir(parents=True)
        (clean_full / agents_rel).write_text(valid_text, encoding="utf-8")
        (clean_full / ub_rel).write_text(valid_text, encoding="utf-8")
        (clean_full / audit_rel).write_text(
            f"# Audit\nCheck {REQUIRED_AUDIT_CURRENCY_MARKER} gate.\n", encoding="utf-8"
        )

        drifted = tmp_path / "drifted"
        (drifted / agents_rel.parent).mkdir(parents=True)
        (drifted / ub_rel.parent).mkdir(parents=True)
        (drifted / audit_rel.parent).mkdir(parents=True)
        (drifted / agents_rel).write_text("Set-and-Forget only", encoding="utf-8")
        (drifted / ub_rel).write_text("stale rules without markers", encoding="utf-8")
        (drifted / audit_rel).write_text("# Audit without currency marker\n", encoding="utf-8")

        # Act
        v_no_audit = check_model_currency_policy(clean_no_audit)
        v_full = check_model_currency_policy(clean_full)
        v_drift = check_model_currency_policy(drifted)

        # Assert
        assert v_no_audit == []
        assert v_full == []
        drift_rules = [row[3] for row in v_drift]
        drift_symbols = [row[2] for row in v_drift]
        assert drift_rules.count("model-currency-policy-drift") == 7
        assert drift_rules.count("model-currency-audit-missing") == 1
        assert REQUIRED_AUDIT_CURRENCY_MARKER in drift_symbols
        assert all(row[1] == 1 for row in v_drift)
