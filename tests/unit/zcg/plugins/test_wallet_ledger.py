"""Unit tests for zcg.plugins.wallet_ledger.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import pytest

from zcg.plugins.wallet_ledger import (
    BilateralReceipt,
    CashflowBucketsSpec,
    PortfolioPosition,
    ThesisExposureSlice,
    assert_zero_custody_public_input,
    build_receipt_verification_url,
    build_watch_ownership_challenge,
    compute_cashflow_buckets,
    compute_thesis_exposure_drift,
    export_r0_public_stewardship_snapshot,
    format_caip10_account_id,
    parse_caip10_account_id,
    project_portfolio_positions,
    validate_public_watch_address,
)


class TestWalletLedger:
    """4-quadrant AAA suite for zero-custody watch validators, cashflow buckets, and Base-100."""

    def test_zero_custody_guard_and_public_watch_validators_across_chains_expected(self) -> None:
        """Verify BTC/EVM/Solana public watch addresses pass and all secret formats fail."""
        # Arrange
        btc_bech32 = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        btc_xpub = "xpub" + ("6" * 96)
        evm_addr = "0x71C7656EC7ab88b098defB751B7401B5f6d8976F"
        sol_addr = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
        hex_priv = "0x" + ("a" * 64)
        bad_xprv = "xprv" + ("9" * 96)
        bad_wif = "5" + ("H" * 50)
        seed_phrase = " ".join(["abandon"] * 11 + ["about"])

        # Act
        ok_btc = validate_public_watch_address(btc_bech32, "bitcoin")
        ok_xpub = validate_public_watch_address(btc_xpub, "bitcoin")
        ok_evm = validate_public_watch_address(evm_addr, "evm")
        ok_sol = validate_public_watch_address(sol_addr, "solana")
        caip_btc = format_caip10_account_id("bitcoin", "000000000019d6689c085ae165831e93", ok_btc)
        caip_evm = format_caip10_account_id("evm", "1", ok_evm)
        caip_sol = format_caip10_account_id("solana", "mainnet", ok_sol)
        ch_btc = build_watch_ownership_challenge(
            caip10_id=caip_btc, domain="wallet.localhost", nonce="n1", issued_at="2026-11-15T00:00Z"
        )
        ch_evm = build_watch_ownership_challenge(
            caip10_id=caip_evm, domain="wallet.localhost", nonce="n2", issued_at="2026-11-15T00:00Z"
        )
        ch_sol = build_watch_ownership_challenge(
            caip10_id=caip_sol, domain="wallet.localhost", nonce="n3", issued_at="2026-11-15T00:00Z"
        )

        # Assert
        assert ok_btc == btc_bech32 and ok_xpub == btc_xpub
        assert parse_caip10_account_id(caip_evm) == ("evm", "1", evm_addr)
        assert ch_btc["standard"] == "BIP-322"
        assert ch_evm["standard"] == "EIP-4361-SIWE"
        assert ch_sol["standard"] == "CAIP-122-SIWS"
        with pytest.raises(ValueError, match="EMPTY_PUBLIC_WATCH_INPUT"):
            assert_zero_custody_public_input("   ")
        for secret in (
            hex_priv,
            bad_xprv,
            bad_wif,
            seed_phrase,
            "-----BEGIN PRIVATE KEY-----",
        ):
            with pytest.raises(ValueError, match="PRIVATE_SECRET_REJECTED"):
                assert_zero_custody_public_input(secret)
        with pytest.raises(ValueError, match="UNSUPPORTED_WATCH_CHAIN"):
            validate_public_watch_address(evm_addr, "cardano")
        with pytest.raises(ValueError, match="INVALID_PUBLIC_WATCH_ADDRESS"):
            validate_public_watch_address("0x1234", "evm")
        with pytest.raises(ValueError, match="INVALID_CAIP10_CHAIN_REFERENCE"):
            format_caip10_account_id("evm", "bad:ref", evm_addr)
        with pytest.raises(ValueError, match="INVALID_CAIP10_ACCOUNT_ID"):
            parse_caip10_account_id("unknown:1:0x1234")
        with pytest.raises(ValueError, match="INVALID_WATCH_CHALLENGE_PARAMS"):
            build_watch_ownership_challenge(
                caip10_id=caip_evm, domain=" ", nonce="n", issued_at="2026-11-15"
            )

    def test_cashflow_buckets_and_cut_points_expected(self) -> None:
        """Verify Profit-First, statutory tax, OpEx, and N vs N+1 100.0% ceiling cut-points."""
        # Arrange
        spec_nominal = CashflowBucketsSpec(20.0, 25.0, 35.0, fixed_operator_payout_units=150.0)
        spec_exact_100 = CashflowBucketsSpec(30.0, 30.0, 40.0, fixed_operator_payout_units=50.0)
        spec_over_100 = CashflowBucketsSpec(30.0, 30.01, 40.0)

        # Act
        res_nom = compute_cashflow_buckets(1000.0, spec_nominal)
        res_tight = compute_cashflow_buckets(200.0, spec_nominal)
        res_exact = compute_cashflow_buckets(500.0, spec_exact_100)

        # Assert
        assert res_nom == {
            "gross_inflow": 1000.0,
            "net_profit_vault": 200.0,
            "statutory_tax_reserve": 250.0,
            "opex_allowance": 350.0,
            "operator_payout": 150.0,
            "unallocated_surplus": 50.0,
        }
        assert res_tight["operator_payout"] == 40.0 and res_tight["unallocated_surplus"] == 0.0
        assert res_exact["operator_payout"] == 0.0
        with pytest.raises(ValueError, match="NEGATIVE_CASHFLOW_INPUT"):
            compute_cashflow_buckets(-1.0, spec_nominal)
        with pytest.raises(ValueError, match="CASHFLOW_BUCKET_PCT_EXCEEDED"):
            compute_cashflow_buckets(1000.0, spec_over_100)

    def test_thesis_exposure_drift_and_base100_privacy_shield_expected(self) -> None:
        """Verify 4-ring rebalance bands and Base-100 / % redaction vs local unshielded output."""
        # Arrange
        slices = (
            ThesisExposureSlice("core_index", 40.0, 500.0),
            ThesisExposureSlice("direct_ecosystem_stack", 30.0, 200.0),
            ThesisExposureSlice("symbiotic_supply_chain", 20.0, 200.0),
            ThesisExposureSlice("validated_consumption", 10.0, 100.0),
        )
        zero_slices = (ThesisExposureSlice("core_index", 100.0, 0.0),)
        positions = (
            PortfolioPosition("CORE", "core_index", 3.0, 100.0),
            PortfolioPosition("INFRA", "direct_ecosystem_stack", 1.0, 100.0),
        )
        empty_pos = (PortfolioPosition("CORE", "core_index", 0.0, 100.0),)

        # Act
        drift_doc = compute_thesis_exposure_drift(slices, rebalance_band_pct=5.0)
        zero_doc = compute_thesis_exposure_drift(zero_slices, rebalance_band_pct=5.0)
        shielded = project_portfolio_positions(positions, privacy_shield=True)
        unshielded = project_portfolio_positions(positions, privacy_shield=False)
        zero_proj = project_portfolio_positions(empty_pos, privacy_shield=True)

        # Assert
        actions = {r["ring_id"]: r["rebalance_action"] for r in drift_doc["slices"]}
        assert actions == {
            "core_index": "OVERWEIGHT",
            "direct_ecosystem_stack": "UNDERWEIGHT",
            "symbiotic_supply_chain": "ON_TARGET",
            "validated_consumption": "ON_TARGET",
        }
        assert zero_doc["slices"][0]["actual_pct"] == 0.0
        assert shielded["absolute_values_redacted"] is True
        assert "total_market_value" not in shielded
        assert "market_value" not in shielded["positions"][0]
        assert shielded["positions"][0]["weight_pct"] == 75.0
        assert unshielded["total_market_value"] == 400.0
        assert unshielded["positions"][0]["market_value"] == 300.0
        assert zero_proj["base_index_total"] == 0.0
        with pytest.raises(ValueError, match="INVALID_THESIS_EXPOSURE_SPEC"):
            compute_thesis_exposure_drift((), rebalance_band_pct=5.0)
        with pytest.raises(ValueError, match="INVALID_OR_DUPLICATE_THESIS_RING"):
            compute_thesis_exposure_drift((ThesisExposureSlice("bad", 100.0, 10.0),))
        with pytest.raises(ValueError, match="NEGATIVE_THESIS_SLICE_VALUE"):
            compute_thesis_exposure_drift((ThesisExposureSlice("core_index", 100.0, -1.0),))
        with pytest.raises(ValueError, match="THESIS_TARGET_SUM_MISMATCH"):
            compute_thesis_exposure_drift((ThesisExposureSlice("core_index", 80.0, 10.0),))
        with pytest.raises(ValueError, match="INVALID_PORTFOLIO_POSITION"):
            project_portfolio_positions((PortfolioPosition("X", "core_index", -1.0, 10.0),))

    def test_bilateral_receipt_urls_and_r0_stewardship_export_expected(self) -> None:
        """Verify explorer URLs across 4 channels and R0 export filtering agreed-settlements."""
        # Arrange
        r_pat = BilateralReceipt(
            "rec-1",
            "public-patronage",
            "bitcoin",
            "tx_btc_001",
            "donor-a",
            "zcg-org",
            "sha256:1",
            "2026-11-15",
        )
        r_ven = BilateralReceipt(
            "rec-2",
            "venture-allocation",
            "evm",
            "0xabc12345",
            "zcg-org",
            "sci-maths",
            "sha256:2",
            "2026-11-15",
        )
        r_set = BilateralReceipt(
            "rec-3",
            "agreed-settlement",
            "invoice",
            "INV-2026-01",
            "corp-alpha",
            "persona-work",
            "sha256:3",
            "2026-11-15",
        )
        sol_url = build_receipt_verification_url("solana", "5KtPn1abc")
        watch_in = (
            {
                "caip10_id": "eip155:1:0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
                "label": "Main Reserve",
            },
            {"caip10_id": "solana:mainnet:9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"},
        )

        # Act
        snap = export_r0_public_stewardship_snapshot(
            node_id="zerocloudgravity",
            public_watch_accounts=watch_in,
            receipts=(r_pat, r_ven, r_set),
        )

        # Assert
        assert sol_url == "https://solscan.io/tx/5KtPn1abc"
        assert r_set.to_dict()["verification_url"] == "urn:zcg:invoice:INV-2026-01"
        assert snap["schema_version"] == "zcg-stewardship-r0-v1"
        assert len(snap["public_reserve_accounts"]) == 2
        assert snap["public_reserve_accounts"][1]["label"] == "solana-reserve"
        assert [r["receipt_id"] for r in snap["verified_public_receipts"]] == ["rec-1", "rec-2"]
        with pytest.raises(ValueError, match="INVALID_RECEIPT_REFERENCE"):
            build_receipt_verification_url("wire", "INV-01")
        with pytest.raises(ValueError, match="EMPTY_STEWARDSHIP_NODE_ID"):
            export_r0_public_stewardship_snapshot(
                node_id=" ", public_watch_accounts=(), receipts=()
            )
