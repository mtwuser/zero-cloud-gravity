"""Unit tests for zcg.governance.runtime.tool_isolation.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from zcg.governance.runtime.tool_isolation import (
    DEFAULT_DECISIONS_MODEL,
    DEFAULT_OFFLINE_LITERT_MODEL,
    DecisionEvaluationRequest,
    audit_skills_sovereign_profile,
    build_bwrap_readonly_command,
    deprovision_isolated_tool_manifest,
    evaluate_calibrated_decisions,
    provision_isolated_tool_manifest,
    resolve_tool_runtime_dir,
    run_isolated_tool_inspection,
)


class TestToolIsolation:
    """1:1 unit suite for .zcg/tools/<id>/ isolation and calibrated decisions."""

    def test_resolve_tool_dir_and_bwrap_readonly_argv_guards_expected(self, tmp_path: Path) -> None:
        """Verify kebab-case containment and read-only bubblewrap command synthesis."""
        # Arrange
        ws = tmp_path / "ws"
        ws.mkdir()

        # Act
        t_dir = resolve_tool_runtime_dir(ws, "secops-guardian")
        cmd_offline = build_bwrap_readonly_command(
            ws, "secops-guardian", ["osv-scanner", "  ", "/workspace"], allow_network=False
        )
        cmd_online = build_bwrap_readonly_command(
            ws, "secops-guardian", ["osv-scanner"], allow_network=True
        )
        with pytest.raises(ValueError, match="Invalid tool_id"):
            resolve_tool_runtime_dir(ws, "../escape")
        with pytest.raises(ValueError, match="inner_argv"):
            build_bwrap_readonly_command(ws, "secops-guardian", ["   "])

        # Assert
        assert t_dir == ws.resolve() / ".zcg/tools/secops-guardian"
        assert "--ro-bind" in cmd_offline and "--share-net" not in cmd_offline
        assert cmd_offline[-2:] == ["osv-scanner", "/workspace"]
        assert "--share-net" in cmd_online

    def test_provision_isolated_tool_manifest_online_vs_airgapped_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify Gemini Decisions online backend vs. offline LiteRT fallback on wallet/airgap."""
        # Arrange
        online_ws = tmp_path / "corp-dev"
        (online_ws / "system").mkdir(parents=True)
        (online_ws / "system/zcg-node.json").write_text(
            json.dumps({"layer_id": "corp-dev", "layer_role": "department"}), encoding="utf-8"
        )
        wallet_ws = tmp_path / "persona-wallet"
        (wallet_ws / "system").mkdir(parents=True)
        (wallet_ws / "system/zcg-node.json").write_text(
            json.dumps(
                {
                    "layer_id": "persona-wallet",
                    "entity_kind": "individual",
                    "layer_role": "squad",
                    "precedence": 88,
                }
            ),
            encoding="utf-8",
        )

        # Act
        dry_doc = provision_isolated_tool_manifest(
            online_ws, "gemini-decisions", active_env="pre", dry_run=True
        )
        sec_doc = provision_isolated_tool_manifest(online_ws, "secops-guardian")
        wal_doc = provision_isolated_tool_manifest(wallet_ws, "gemini-decisions")
        aud_rep = audit_skills_sovereign_profile(online_ws)
        with pytest.raises(ValueError, match="Unknown isolated tool_id"):
            provision_isolated_tool_manifest(online_ws, "unknown-pack")

        # Assert
        assert dry_doc["decision_backend"] == "gemini-decisions-api"
        assert dry_doc["environment"] == "pre"
        assert not (online_ws / ".zcg/tools/gemini-decisions/tool-runtime.json").exists()
        assert sec_doc["decision_backend"] is None and sec_doc["network_allowed"] is True
        assert wal_doc["decision_backend"] == "litert-gemma-4"
        assert wal_doc["network_allowed"] is False
        assert (wallet_ws / ".zcg/tools/gemini-decisions/tool-runtime.json").is_file()
        assert aud_rep["trust_score"] == 100
        i_aud = run_isolated_tool_inspection(online_ws, "zcg-skill-auditor")
        i_sec = run_isolated_tool_inspection(online_ws, "secops-guardian")
        i_dec = run_isolated_tool_inspection(wallet_ws, "gemini-decisions")
        i_gen_off = run_isolated_tool_inspection(online_ws, "duckdb-analytics")
        provision_isolated_tool_manifest(online_ws, "duckdb-analytics")
        (online_ws / ".zcg/tools/duckdb-analytics/cache.txt").write_text("keep", encoding="utf-8")
        i_gen_on = run_isolated_tool_inspection(online_ws, "duckdb-analytics")
        dep_dry = deprovision_isolated_tool_manifest(online_ws, "secops-guardian", dry_run=True)
        dep_sec = deprovision_isolated_tool_manifest(online_ws, "secops-guardian")
        dep_again = deprovision_isolated_tool_manifest(online_ws, "secops-guardian")
        dep_keep = deprovision_isolated_tool_manifest(online_ws, "duckdb-analytics")
        assert "Skill Trust:" in i_aud["headline"] and "Posture:" in i_sec["headline"]
        assert "Offline LiteRT" in i_dec["headline"]
        assert "Inactive" in i_gen_off["headline"] and "Active" in i_gen_on["headline"]
        assert dep_dry["deprovisioned"] is True and dep_sec["deprovisioned"] is True
        assert dep_again["deprovisioned"] is False and dep_keep["deprovisioned"] is True
        assert not (online_ws / ".zcg/tools/secops-guardian").exists()
        assert (online_ws / ".zcg/tools/duckdb-analytics/cache.txt").is_file()
        with pytest.raises(ValueError, match="Unknown isolated tool_id"):
            deprovision_isolated_tool_manifest(online_ws, "unknown-pack")
        with pytest.raises(ValueError, match="Unknown isolated tool_id"):
            run_isolated_tool_inspection(online_ws, "unknown-pack")

    def test_evaluate_calibrated_decisions_online_litert_and_bipolar_guards_expected(
        self,
    ) -> None:
        """Verify zero-output-token Gemini Decisions transport, offline LiteRT, and batch caps."""
        # Arrange
        items = [
            DecisionEvaluationRequest("i1", "yes_no", "env-gate", "Allow pro?", prior_score=0.82),
            DecisionEvaluationRequest("i2", "yes_no", "env-gate", "Block?", prior_score=0.15),
            DecisionEvaluationRequest(
                "i3",
                "choice",
                "model-routing",
                "Pick tier",
                choices=("flash", "inherit", "pro"),
                prior_score=0.75,
            ),
            DecisionEvaluationRequest(
                "i4", "rubric", "epistemic-q-score", "Score E3", prior_score=0.85
            ),
            DecisionEvaluationRequest(
                "i5", "rubric", "disclosure-sensitivity", "Score E0", prior_score=0.40
            ),
        ]
        captured: dict[str, Any] = {}

        def _fake_transport(payload: dict[str, Any]) -> dict[str, Any]:
            captured.update(payload)
            return {"results": [{"item_id": "i1", "decision": "yes"}]}

        # Act
        online = evaluate_calibrated_decisions(items[:1], transport_fn=_fake_transport)
        offline = evaluate_calibrated_decisions(
            items, offline_mode=True, transport_fn=_fake_transport
        )
        with pytest.raises(ValueError, match="DECISIONS_BATCH_LIMIT_EXCEEDED"):
            evaluate_calibrated_decisions([])
        with pytest.raises(ValueError, match="DECISIONS_BATCH_LIMIT_EXCEEDED"):
            evaluate_calibrated_decisions([items[0]] * 1001)
        with pytest.raises(ValueError, match="task_kind"):
            evaluate_calibrated_decisions([DecisionEvaluationRequest("x", "bad", "env-gate", "p")])
        with pytest.raises(ValueError, match="use_case"):
            evaluate_calibrated_decisions([DecisionEvaluationRequest("x", "yes_no", "bad", "p")])
        with pytest.raises(ValueError, match="at least 2 choices"):
            evaluate_calibrated_decisions(
                [DecisionEvaluationRequest("x", "choice", "handoff-axis", "p", choices=("one",))]
            )

        # Assert
        assert captured["max_output_tokens"] == 0
        assert online["backend"] == "gemini-decisions-api"
        assert online["model"] == DEFAULT_DECISIONS_MODEL and online["output_tokens"] == 0
        assert offline["backend"] == "litert-gemma-4"
        assert offline["model"] == DEFAULT_OFFLINE_LITERT_MODEL and offline["output_tokens"] == 0
        res = {r["item_id"]: r for r in offline["results"]}
        assert res["i1"]["decision"] == "yes" and res["i2"]["decision"] == "no"
        assert res["i3"]["selected_choice"] == "pro"
        assert res["i4"]["passed"] is True and res["i5"]["passed"] is False
