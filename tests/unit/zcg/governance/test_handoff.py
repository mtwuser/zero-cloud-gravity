"""Unit tests for zcg.governance.handoff.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.governance import handoff


def _write_manifest(node_dir: Path, payload: dict[str, object]) -> None:
    path = node_dir / NODE_MANIFEST_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestHandoff:
    """Verify canonical axis glossaries, symmetry rebounds, and asymmetry proposals."""

    def test_load_merged_canonical_glossary_conflicts_and_lex_superior_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify sender/receiver alias conflict detection and Parent Lex Superior resolution."""
        # Arrange
        sender = tmp_path / "dept-product"
        _write_manifest(
            sender,
            {
                "layer_id": "dept-product",
                "canonical_terms": {
                    "billing_cadence": {"monthly-cycle": ["mo", "monthly-cycle"]},
                    "": {"ignored": ["x"]},
                    "empty_axis": {"bad": "not-a-list"},
                },
                "handoff_contract": {
                    "required_sections": ["## Product Scope"],
                    "single_axis_per_item": True,
                },
            },
        )
        (sender / "templates/dept-product").mkdir(parents=True)
        (sender / "templates/dept-product/glossary.json").write_text(
            json.dumps({"delivery_channel": {"web-portal": ["portal"]}}),
            encoding="utf-8",
        )
        receiver = tmp_path / "dept-finance"
        _write_manifest(
            receiver,
            {
                "layer_id": "dept-finance",
                "canonical_terms": {"billing_cadence": {"calendar-month": ["mo"]}},
                "handoff_contract": "invalid-contract",
            },
        )
        parent = tmp_path / "corp-iso-root"
        _write_manifest(
            parent,
            {
                "layer_id": "corp-iso-root",
                "canonical_terms": {"billing_cadence": {"fiscal-month": ["mo"]}},
            },
        )

        # Act
        solo = handoff.load_merged_canonical_glossary(tmp_path / "nonexistent")
        conflict_g = handoff.load_merged_canonical_glossary(sender, receiver_dir=receiver)
        resolved_g = handoff.load_merged_canonical_glossary(
            sender, receiver_dir=receiver, parent_dir=parent
        )

        # Assert
        assert "architecture_tier" in solo["terms"]
        assert len(conflict_g["conflicts"]) == 1
        assert conflict_g["conflicts"][0]["reason_code"] == "GLOSSARY_DEFINITION_CONFLICT"
        assert "delivery_channel" in conflict_g["unstandardized_axes"]
        assert resolved_g["conflicts"] == []
        assert resolved_g["single_axis_per_item"] is True

    def test_check_handoff_symmetry_rebounds_proposals_and_aligned_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify alias rebound, multi-axis conflation, missing section, proposal, and aligned."""
        # Arrange
        sender = tmp_path / "dept-eng"
        _write_manifest(
            sender,
            {
                "layer_id": "dept-eng",
                "canonical_terms": {"observability": {"distributed-trace": ["dtrace"]}},
            },
        )
        receiver = tmp_path / "dept-ops"
        _write_manifest(
            receiver,
            {
                "layer_id": "dept-ops",
                "handoff_contract": {"required_sections": ["## Acceptance Criteria"]},
            },
        )
        aligned_peer = tmp_path / "dept-qa"
        _write_manifest(aligned_peer, {"layer_id": "dept-qa"})

        directive_file = sender / "directives/d1.md"
        directive_file.parent.mkdir(parents=True)
        directive_file.write_text(
            "# Frontend & Backend Coordination\n"
            "## Acceptance Criteria\n"
            "- Deliver Clean Telemetry Schema\n",
            encoding="utf-8",
        )

        # Act
        rebound_res = handoff.check_handoff_symmetry(
            sender,
            directive_text="- Update front, bk, and db in prod",
            receiver_dir=receiver,
            single_axis_per_item=True,
        )
        prop_unstaged = handoff.check_handoff_symmetry(
            sender,
            source_rel_path="directives/d1.md",
            receiver_dir=receiver,
            single_axis_per_item=True,
            stage_proposal=False,
        )
        prop_staged = handoff.check_handoff_symmetry(
            sender,
            source_rel_path="directives/d1.md",
            receiver_dir=receiver,
            stage_proposal=True,
            actor_email="eng@corp-iso.example",
        )
        aligned_res = handoff.check_handoff_symmetry(
            aligned_peer,
            directive_text="- Verify frontend contract in pre",
            receiver_dir=aligned_peer,
            single_axis_per_item=True,
        )

        # Assert
        with pytest.raises(ValueError, match="Missing handoff source file"):
            handoff.check_handoff_symmetry(sender, source_rel_path="directives/missing.md")
        with pytest.raises(ValueError, match="Provide non-empty directive_text"):
            handoff.check_handoff_symmetry(sender, directive_text="   ")
        assert rebound_res["passed"] is False and rebound_res["status"] == "rebound"
        assert rebound_res["normalized_text"] == "- Update frontend, backend, and database in pro"
        codes = {r["reason_code"] for r in rebound_res["rebounds"]}
        assert codes == {
            "INFORMAL_ALIAS_REBOUND",
            "MULTI_AXIS_CONFLATION_REBOUND",
            "MISSING_REQUIRED_HANDOFF_SECTION",
        }
        assert prop_unstaged["passed"] is True and prop_unstaged["status"] == "proposal"
        assert prop_unstaged["staged_proposal"] is None
        assert prop_staged["staged_proposal"] is not None
        assert Path(prop_staged["staged_proposal"]).is_file()
        assert aligned_res["passed"] is True and aligned_res["status"] == "aligned"
        assert aligned_res["rebounds"] == [] and aligned_res["proposals"] == []
