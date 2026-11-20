"""Unit tests for zcg.plugins.settlement_airlock.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from zcg.plugins.settlement_airlock import (
    PRIOR_COUNTERPARTY_BADGE,
    SETTLEMENTS_REL_PATH,
    bind_work_agreed_settlement,
    evaluate_counterparty_handshake_context,
    reconcile_wallet_airlock_pull,
)
from zcg.plugins.wallet_ledger import BilateralReceipt

if TYPE_CHECKING:
    from pathlib import Path


def _write_node(ws: Path, manifest: dict[str, object]) -> Path:
    (ws / "system").mkdir(parents=True, exist_ok=True)
    (ws / "system/zcg-node.json").write_text(json.dumps(manifest), encoding="utf-8")
    return ws


class TestSettlementAirlock:
    """4-quadrant AAA suite for <persona>-work settlement airlock and 0%-plutocracy context."""

    def test_bind_work_agreed_settlement_airlock_and_guards_expected(self, tmp_path: Path) -> None:
        """Verify wallet block, settlement_mode gate, linked peer check, and WORKVALI [x] gate."""
        # Arrange
        wallet_ws = _write_node(
            tmp_path / "persona-wallet",
            {"layer_id": "persona-wallet", "entity_kind": "individual", "layer_role": "squad"},
        )
        disabled_ws = _write_node(
            tmp_path / "persona-work-off",
            {"layer_id": "persona-work", "entity_kind": "individual", "layer_role": "department"},
        )
        work_ws = _write_node(
            tmp_path / "persona-work",
            {
                "layer_id": "persona-work",
                "entity_kind": "individual",
                "layer_role": "department",
                "settlement_mode": "manual-reference",
                "linked_nodes": [
                    "raw-ignored",
                    {"node_id": "corp-alpha", "relation": "b2b-collaboration"},
                ],
            },
        )

        # Act
        with pytest.raises(ValueError, match="WALLET_DIRECT_SETTLEMENT_BLOCKED"):
            bind_work_agreed_settlement(
                wallet_ws,
                counterparty_node_id="corp-alpha",
                deliverable_id="DELIV-01",
                channel="invoice",
                reference_id="INV-01",
                proof_digest="sha256:abc",
            )
        with pytest.raises(ValueError, match="SETTLEMENT_MODE_DISABLED"):
            bind_work_agreed_settlement(
                disabled_ws,
                counterparty_node_id="corp-alpha",
                deliverable_id="DELIV-01",
                channel="invoice",
                reference_id="INV-01",
                proof_digest="sha256:abc",
            )
        with pytest.raises(ValueError, match="INVALID_SETTLEMENT_ARGUMENTS"):
            bind_work_agreed_settlement(
                work_ws,
                counterparty_node_id="corp-alpha",
                deliverable_id="DELIV-01",
                channel="invoice",
                reference_id="INV-01",
                proof_digest="sha256:abc",
                settlement_role="escrow",
            )
        with pytest.raises(ValueError, match="UNLINKED_SETTLEMENT_COUNTERPARTY"):
            bind_work_agreed_settlement(
                work_ws,
                counterparty_node_id="corp-other",
                deliverable_id="DELIV-01",
                channel="invoice",
                reference_id="INV-01",
                proof_digest="sha256:abc",
            )
        with pytest.raises(ValueError, match="UNVERIFIED_WORKVALI_DELIVERABLE"):
            bind_work_agreed_settlement(
                work_ws,
                counterparty_node_id="corp-alpha",
                deliverable_id="DELIV-01",
                channel="invoice",
                reference_id="INV-01",
                proof_digest="sha256:abc",
            )

        (work_ws / "WORKVALI.md").write_text(
            "- [x] Verified DELIV-01 milestone\n", encoding="utf-8"
        )
        settle_file = work_ws / SETTLEMENTS_REL_PATH
        settle_file.parent.mkdir(parents=True, exist_ok=True)
        settle_file.write_text('"corrupt-non-list"', encoding="utf-8")

        res_payee = bind_work_agreed_settlement(
            work_ws,
            counterparty_node_id="corp-alpha",
            deliverable_id="DELIV-01",
            channel="invoice",
            reference_id="INV-2026-01",
            proof_digest="sha256:deliv01",
            settlement_role="payee",
        )
        res_payer = bind_work_agreed_settlement(
            work_ws,
            counterparty_node_id="corp-alpha",
            deliverable_id="DELIV-01",
            channel="solana",
            reference_id="5KtPn1abc",
            proof_digest="caip122:deliv01",
            settlement_role="payer",
        )

        # Assert
        assert res_payee["receipt"]["payer_node_id"] == "corp-alpha"
        assert res_payer["receipt"]["payer_node_id"] == "persona-work"

    def test_reconcile_wallet_airlock_pull_and_venture_radar_expected(self, tmp_path: Path) -> None:
        """Verify unidirectional localhost pull into <persona>-wallet without back-writing work."""
        # Arrange
        wallet_ws = _write_node(
            tmp_path / "persona-wallet",
            {"layer_id": "persona-wallet", "entity_kind": "individual", "layer_role": "squad"},
        )
        work_ws = _write_node(
            tmp_path / "persona-work",
            {
                "layer_id": "persona-work",
                "entity_kind": "individual",
                "layer_role": "department",
                "settlement_mode": "dedicated-settlement-endpoint",
                "linked_nodes": [{"node_id": "corp-alpha", "relation": "b2b-collaboration"}],
            },
        )
        (work_ws / "WORKVALI.md").write_text("- [x] Shipped DELIV-02\n", encoding="utf-8")
        bind_work_agreed_settlement(
            work_ws,
            counterparty_node_id="corp-alpha",
            deliverable_id="DELIV-02",
            channel="evm",
            reference_id="0x11223344",
            proof_digest="eip4361:ok",
        )
        venture_ws = _write_node(
            tmp_path / "svc-radar", {"layer_id": "svc-radar", "layer_role": "project"}
        )
        (venture_ws / "VERSION").write_text("0.4.0\n", encoding="utf-8")
        (venture_ws / "WORKTASK.md").write_text("- [x] Done\n- [ ] Next\n", encoding="utf-8")

        # Act
        pulled = reconcile_wallet_airlock_pull(
            wallet_ws, work_dir=work_ws, venture_dirs=(venture_ws,)
        )

        # Assert
        assert pulled["imported_settlement_ids"] == ["settle-deliv-02-corp-alpha"]
        assert pulled["venture_radar"] == [
            {"node_id": "svc-radar", "version": "0.4.0", "completed_count": 1, "pending_count": 1}
        ]
        assert not (work_ws / ".zcg/runtime/wallet").exists()
        with pytest.raises(ValueError, match="WALLET_PILLAR_REQUIRED"):
            reconcile_wallet_airlock_pull(work_ws, work_dir=work_ws)
        with pytest.raises(ValueError, match="WORK_AIRLOCK_SOURCE_REQUIRED"):
            reconcile_wallet_airlock_pull(wallet_ws, work_dir=venture_ws)

    def test_counterparty_handshake_context_anti_wash_trading_and_zero_plutocracy_expected(
        self,
    ) -> None:
        """Verify third-party wash trades are ignored and auto_grant_ring stays None (0%)."""
        # Arrange
        direct_rec = BilateralReceipt(
            "r-1",
            "public-patronage",
            "evm",
            "0x1111",
            "peer-alpha",
            "zcg-org",
            "caip122:ok",
            "2026-11-15",
        )
        wash_trade = {
            "receipt_id": "r-wash",
            "payer_node_id": "peer-alpha",
            "payee_node_id": "colluder-node",
            "proof_digest": "caip122:wash",
        }
        unverified_direct = {
            "receipt_id": "r-unv",
            "payer_node_id": "peer-alpha",
            "payee_node_id": "zcg-org",
            "proof_digest": "   ",
        }

        # Act
        ctx_hit = evaluate_counterparty_handshake_context(
            own_node_id="zcg-org",
            candidate_peer_id="peer-alpha",
            receipts=(direct_rec, wash_trade, unverified_direct),
        )
        ctx_miss = evaluate_counterparty_handshake_context(
            own_node_id="zcg-org",
            candidate_peer_id="peer-stranger",
            receipts=(direct_rec, wash_trade),
        )

        # Assert
        assert ctx_hit.verified_prior_counterparty is True
        assert ctx_hit.badge_label == PRIOR_COUNTERPARTY_BADGE
        assert ctx_hit.direct_receipt_count == 1
        assert ctx_hit.ignored_third_party_count == 2
        assert ctx_hit.auto_grant_ring is None
        assert ctx_hit.plutocracy_weight == 0.0
        assert ctx_hit.to_dict()["auto_grant_ring"] is None
        assert ctx_miss.verified_prior_counterparty is False and ctx_miss.badge_label is None
        with pytest.raises(ValueError, match="INVALID_HANDSHAKE_NODE_IDS"):
            evaluate_counterparty_handshake_context(
                own_node_id="zcg-org", candidate_peer_id="zcg-org", receipts=()
            )
