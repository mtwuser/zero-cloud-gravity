"""Unit tests for zcg.capsules.citations.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from zcg.capsules.citations import (
    build_citation_receipt,
    evaluate_citation_telemetry_lifecycle,
    infer_epistemic_grade,
    load_citation_telemetry_radar,
    record_citation_telemetry_event,
    summarize_mcp_diagnostics,
    verify_epistemic_context_claims,
)


class TestCapsuleCitations:
    """Verify epistemic grade inference, Q1..Q4 telemetry, L3 claim checks, and MCP diagnostics."""

    def test_infer_epistemic_grade_and_build_citation_receipt(self) -> None:
        """Infer explicit and heuristic E3..E0 grades and format canonical citation receipts."""
        # Arrange
        explicit = infer_epistemic_grade("docs/guide.md", "Rule [E2]", "Body")
        e0 = infer_epistemic_grade("BACKLOG.md", "Future Item", "Body")
        e3 = infer_epistemic_grade("SECURITY.md", "Core Policy", "Body")
        e2 = infer_epistemic_grade("docs/architecture/01.md", "Overview", "Body")
        e1 = infer_epistemic_grade("docs/guides/01.md", "Quickstart", "Body")

        # Act
        receipt = build_citation_receipt(
            "root", "/docs/spec.md", "1. Law", "0123456789abcdef", "E3"
        )

        # Assert
        assert explicit[0] == "E2"
        assert e0[0] == "E0"
        assert e3[0] == "E3"
        assert e2[0] == "E2"
        assert e1[0] == "E1"
        assert receipt == "root::docs/spec.md#1-law@0123456789abcdef:E3"

    def test_evaluate_and_record_citation_telemetry_lifecycle(self, tmp_path: Path) -> None:
        """Classify sections into Q1..Q4 quadrants and persist citation_stats.json events."""
        # Arrange
        sections = [
            {"epistemic_grade": "E3", "citation_count": 7, "age_days": 10},
            {"epistemic_grade": "E2", "citation_count": 2, "stale_citation_hits": 1},
            {"epistemic_grade": "E1", "citation_count": 1, "age_days": 5},
            {"epistemic_grade": "E3", "citation_count": 0, "age_days": 120},
        ]

        # Act
        lifecycle = evaluate_citation_telemetry_lifecycle(sections)
        empty_radar = load_citation_telemetry_radar(tmp_path)
        record_citation_telemetry_event(
            tmp_path,
            "root::docs/spec.md#sec@0123456789abcdef:E2",
            is_proposal_friction=True,
            age_days=15,
        )
        record_citation_telemetry_event(
            tmp_path, "root::docs/plain.md#sec@0123456789abcdef", is_stale_hit=True
        )
        live_radar = load_citation_telemetry_radar(tmp_path)

        # Assert
        assert lifecycle["epistemic_override_allowed"] is False
        assert lifecycle["quadrant_counts"] == {
            "Q1_HOT_CORE": 1,
            "Q2_HIGH_FRICTION": 1,
            "Q3_EMERGING_NICHE": 1,
            "Q4_NORMATIVE_OBSOLESCENCE": 1,
        }
        assert empty_radar["tracked_sections_count"] == 0
        assert live_radar["tracked_sections_count"] == 2
        assert len(live_radar["high_friction_targets"]) == 2

    def test_verify_epistemic_context_claims_clean_and_all_four_violations(
        self, tmp_path: Path
    ) -> None:
        """Verify clean L3 claims and detect precedence, hash, cut-point, and drift violations."""
        # Arrange
        doc = tmp_path / "docs/spec.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("# Spec\n", encoding="utf-8")
        sha16 = hashlib.sha256(doc.read_bytes()).hexdigest()[:16]
        clean_claims: list[dict[str, Any]] = [
            {
                "claim_id": "ok-1",
                "epistemic_grade": "E3",
                "overrides_grade": "E2",
                "l3_targets": [{"path": "docs/spec.md", "sha256_prefix": sha16}],
                "cut_point": 10.0,
                "observed_value": 5.0,
                "citation_receipt": f"root::docs/spec.md#spec@{sha16}:E3",
                "official_digest": sha16,
            },
            {"claim_id": "minimal"},
        ]
        bad_claims = [
            {
                "epistemic_grade": "E0",
                "overrides_grade": "E3",
                "l3_targets": [{"path": "docs/missing.md", "sha256_prefix": "deadbeef"}],
                "cut_point": 1.0,
                "observed_value": 2.5,
                "citation_receipt": "root::docs/spec.md#spec@ffffffffffffffff:E0",
                "official_digest": sha16,
            }
        ]

        # Act
        ok_res = verify_epistemic_context_claims(clean_claims, tmp_path)
        bad_res = verify_epistemic_context_claims(bad_claims, tmp_path)

        # Assert
        assert ok_res["verified"] is True
        assert ok_res["error_code"] is None
        assert bad_res["verified"] is False
        codes = [v["code"] for v in bad_res["violations"]]
        assert codes == [
            "EPISTEMIC_PRECEDENCE_VIOLATION",
            "PRIMARY_SOURCE_HASH_MISMATCH",
            "CUT_POINT_BOUNDARY_VIOLATION",
            "CITATION_DRIFT_DETECTED",
        ]

    def test_summarize_mcp_diagnostics_empty_and_populated(self, tmp_path: Path) -> None:
        """Summarize JSONL MCP events, alerts, and resonance compaction metrics."""
        # Arrange
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "mcp_events.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "status": "ok",
                            "resolution": "L1",
                            "tokens_saved": 120,
                            "response_bytes": 512,
                        }
                    ),
                    json.dumps(
                        {
                            "status": "error",
                            "unfolded_level": "L2",
                            "agent_tier": "pro",
                            "decrypted_hops": 2,
                            "response_bytes": 1024,
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (log_dir / "mcp_alerts.jsonl").write_text(
            "\n".join(
                [
                    json.dumps({"code": "CAPSULE_SIGNATURE_INVALID"}),
                    json.dumps({"code": "TOKEN_BUDGET_NEAR_LIMIT"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        # Act
        empty_diag = summarize_mcp_diagnostics(None, tmp_path / "empty_repo")
        full_diag = summarize_mcp_diagnostics(log_dir, tmp_path)

        # Assert
        assert empty_diag["logging_enabled"] is False
        assert empty_diag["events_summary"]["total_events"] == 0
        assert full_diag["logging_enabled"] is True
        assert full_diag["events_summary"]["error_events"] == 1
        assert full_diag["events_summary"]["max_response_bytes"] == 1024
        assert full_diag["resonance_compaction_summary"]["cumulative_tokens_saved"] == 120
        assert full_diag["resonance_compaction_summary"]["total_decrypted_hops"] == 2
        assert full_diag["resonance_compaction_summary"]["capsule_alerts_by_code"] == {
            "CAPSULE_SIGNATURE_INVALID": 1
        }
