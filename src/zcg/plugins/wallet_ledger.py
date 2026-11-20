"""Pure multi-ring treasury & portfolio ledger math, CAIP-10 validators, and Base-100 shield.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

VALID_WALLET_RING_MODES: Final[tuple[str, ...]] = ("R0", "R2", "R3")
VALID_WATCH_CHAIN_FAMILIES: Final[tuple[str, ...]] = ("bitcoin", "evm", "solana")
VALID_RECEIPT_CHANNELS: Final[tuple[str, ...]] = ("bitcoin", "evm", "solana", "invoice")
VALID_RECEIPT_KINDS: Final[tuple[str, ...]] = (
    "public-patronage",
    "agreed-settlement",
    "venture-allocation",
)
VALID_THESIS_RINGS: Final[tuple[str, ...]] = (
    "core_index",
    "direct_ecosystem_stack",
    "symbiotic_supply_chain",
    "validated_consumption",
)
BASE_100_INDEX_SCALE: Final[float] = 100.0
MAX_ALLOCATION_PCT: Final[float] = 100.0
DEFAULT_REBALANCE_BAND_PCT: Final[float] = 5.0
ALLOCATION_TOLERANCE_PCT: Final[float] = 0.05

_CHAIN_TO_CAIP_NS: Final[dict[str, str]] = {
    "bitcoin": "bip122",
    "evm": "eip155",
    "solana": "solana",
}
_CAIP_NS_TO_CHAIN: Final[dict[str, str]] = {v: k for k, v in _CHAIN_TO_CAIP_NS.items()}
_HEX_CHARS: Final[frozenset[str]] = frozenset("0123456789abcdefABCDEF")
_BASE58_CHARS: Final[frozenset[str]] = frozenset(
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
)
_BECH32_CHARS: Final[frozenset[str]] = frozenset("qpzry9x8gf2tvdw0s3jn54khce6mua7l")
_SAFE_REF_CHARS: Final[frozenset[str]] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
)


def _has_charset_len(value: str, charset: frozenset[str], min_len: int, max_len: int) -> bool:
    return min_len <= len(value) <= max_len and all(ch in charset for ch in value)


def _is_secret_material(clean: str) -> bool:
    words = clean.lower().split()
    is_mnemonic = 12 <= len(words) <= 24 and all(
        3 <= len(w) <= 10 and w.isascii() and w.isalpha() for w in words
    )
    return (
        (clean.startswith(("0x", "0X")) and _has_charset_len(clean[2:], _HEX_CHARS, 64, 64))
        or (
            clean[:4] in ("xprv", "yprv", "zprv")
            and _has_charset_len(clean[4:], _BASE58_CHARS, 80, 120)
        )
        or (clean[0] in ("5", "K", "L") and _has_charset_len(clean[1:], _BASE58_CHARS, 50, 51))
        or "PRIVATE KEY" in " ".join(clean.upper().split())
        or is_mnemonic
    )


@dataclass(frozen=True, slots=True)
class CashflowBucketsSpec:
    """Profit-First, statutory tax vault, OpEx ceiling, and fixed operator payout targets."""

    net_profit_vault_pct: float
    statutory_tax_reserve_pct: float
    opex_ceiling_pct: float
    fixed_operator_payout_units: float = 0.0


@dataclass(frozen=True, slots=True)
class ThesisExposureSlice:
    """Single thesis ring allocation target (%) versus observed market valuation."""

    ring_id: str
    target_pct: float
    current_value: float


@dataclass(frozen=True, slots=True)
class PortfolioPosition:
    """Single asset holding input prior to Base-100 / % Privacy Shield projection."""

    asset_code: str
    thesis_ring: str
    quantity: float
    unit_price: float


@dataclass(frozen=True, slots=True)
class BilateralReceipt:
    """Non-custodial bilateral receipt bound via on-chain memo, CAIP-122 proof, or invoice ref."""

    receipt_id: str
    receipt_kind: str
    channel: str
    reference_id: str
    payer_node_id: str
    payee_node_id: str
    proof_digest: str
    recorded_at: str
    public_note: str = ""

    def to_dict(self) -> dict[str, str]:
        """Serialize bilateral receipt with its deterministic verification URL."""
        return {
            "receipt_id": self.receipt_id,
            "receipt_kind": self.receipt_kind,
            "channel": self.channel,
            "reference_id": self.reference_id,
            "payer_node_id": self.payer_node_id,
            "payee_node_id": self.payee_node_id,
            "proof_digest": self.proof_digest,
            "recorded_at": self.recorded_at,
            "public_note": self.public_note,
            "verification_url": build_receipt_verification_url(self.channel, self.reference_id),
        }


def assert_zero_custody_public_input(raw_value: str) -> str:
    """Reject private keys, WIF secrets, extended xprv keys, PEM blocks, or seed mnemonics."""
    clean = raw_value.strip()
    if not clean:
        raise ValueError("EMPTY_PUBLIC_WATCH_INPUT: value must be non-empty")
    if _is_secret_material(clean):
        raise ValueError("PRIVATE_SECRET_REJECTED: zero-custody watch surfaces reject secrets")
    return clean


def validate_public_watch_address(address: str, chain_family: str) -> str:
    """Validate a public watch-only address (BIP-173/xpub, EIP-55 0x20B, or Solana Base58)."""
    clean_addr = assert_zero_custody_public_input(address)
    clean_chain = chain_family.strip().lower()
    if clean_chain not in VALID_WATCH_CHAIN_FAMILIES:
        raise ValueError(f"UNSUPPORTED_WATCH_CHAIN: {chain_family!r}")
    valid = (
        (
            (
                clean_addr[:3] in ("bc1", "tb1")
                and _has_charset_len(clean_addr[3:], _BECH32_CHARS, 25, 87)
            )
            or (
                clean_addr[:4] in ("xpub", "ypub", "zpub")
                and _has_charset_len(clean_addr[4:], _BASE58_CHARS, 80, 120)
            )
        )
        if clean_chain == "bitcoin"
        else (
            (clean_addr.startswith("0x") and _has_charset_len(clean_addr[2:], _HEX_CHARS, 40, 40))
            if clean_chain == "evm"
            else _has_charset_len(clean_addr, _BASE58_CHARS, 32, 44)
        )
    )
    if not valid:
        raise ValueError(f"INVALID_PUBLIC_WATCH_ADDRESS: {clean_addr!r} for {clean_chain}")
    return clean_addr


def format_caip10_account_id(chain_family: str, chain_reference: str, address: str) -> str:
    """Format a validated CAIP-10 account identifier (<namespace>:<reference>:<address>)."""
    clean_chain = chain_family.strip().lower()
    clean_addr = validate_public_watch_address(address, clean_chain)
    clean_ref = chain_reference.strip()
    if not clean_ref or ":" in clean_ref or " " in clean_ref:
        raise ValueError(f"INVALID_CAIP10_CHAIN_REFERENCE: {chain_reference!r}")
    return f"{_CHAIN_TO_CAIP_NS[clean_chain]}:{clean_ref}:{clean_addr}"


def parse_caip10_account_id(caip10_id: str) -> tuple[str, str, str]:
    """Parse and validate a CAIP-10 identifier into (chain_family, chain_reference, address)."""
    clean = assert_zero_custody_public_input(caip10_id)
    parts = clean.split(":")
    if len(parts) != 3 or parts[0] not in _CAIP_NS_TO_CHAIN or not parts[1]:
        raise ValueError(f"INVALID_CAIP10_ACCOUNT_ID: {caip10_id!r}")
    chain_family = _CAIP_NS_TO_CHAIN[parts[0]]
    addr = validate_public_watch_address(parts[2], chain_family)
    return chain_family, parts[1], addr


def build_watch_ownership_challenge(
    *, caip10_id: str, domain: str, nonce: str, issued_at: str
) -> dict[str, str]:
    """Construct a read-only BIP-322 / EIP-4361 SIWE / CAIP-122 SIWS watch challenge."""
    chain_family, chain_ref, address = parse_caip10_account_id(caip10_id)
    clean_dom, clean_nonce, clean_ts = domain.strip(), nonce.strip(), issued_at.strip()
    if not clean_dom or not clean_nonce or not clean_ts:
        raise ValueError("INVALID_WATCH_CHALLENGE_PARAMS: domain, nonce, and issued_at required")
    standard = (
        "BIP-322"
        if chain_family == "bitcoin"
        else ("EIP-4361-SIWE" if chain_family == "evm" else "CAIP-122-SIWS")
    )
    msg = (
        f"{clean_dom} requests read-only watch verification for {address}\n"
        f"CAIP-10: {caip10_id.strip()}\nChain-Ref: {chain_ref}\n"
        f"Statement: Zero-custody watch-address verification only; 0 spending permissions.\n"
        f"Nonce: {clean_nonce}\nIssued At: {clean_ts}"
    )
    return {
        "standard": standard,
        "chain_family": chain_family,
        "caip10_id": caip10_id,
        "message": msg,
    }


def compute_cashflow_buckets(gross_inflow: float, spec: CashflowBucketsSpec) -> dict[str, float]:
    """Compute Profit-First net profit, statutory tax reserve, OpEx, and operator payout buckets."""
    if (
        gross_inflow < 0.0
        or spec.net_profit_vault_pct < 0.0
        or spec.statutory_tax_reserve_pct < 0.0
        or spec.opex_ceiling_pct < 0.0
        or spec.fixed_operator_payout_units < 0.0
    ):
        raise ValueError("NEGATIVE_CASHFLOW_INPUT: inflow and bucket parameters must be >= 0")
    pct_sum = spec.net_profit_vault_pct + spec.statutory_tax_reserve_pct + spec.opex_ceiling_pct
    if pct_sum > MAX_ALLOCATION_PCT:
        raise ValueError(f"CASHFLOW_BUCKET_PCT_EXCEEDED: {pct_sum:.2f}% > 100.00%")
    profit = round(gross_inflow * (spec.net_profit_vault_pct / MAX_ALLOCATION_PCT), 4)
    tax = round(gross_inflow * (spec.statutory_tax_reserve_pct / MAX_ALLOCATION_PCT), 4)
    opex = round(gross_inflow * (spec.opex_ceiling_pct / MAX_ALLOCATION_PCT), 4)
    rem = max(0.0, round(gross_inflow - profit - tax - opex, 4))
    payout = round(min(spec.fixed_operator_payout_units, rem), 4)
    return {
        "gross_inflow": round(gross_inflow, 4),
        "net_profit_vault": profit,
        "statutory_tax_reserve": tax,
        "opex_allowance": opex,
        "operator_payout": payout,
        "unallocated_surplus": round(rem - payout, 4),
    }


def compute_thesis_exposure_drift(
    slices: Sequence[ThesisExposureSlice], *, rebalance_band_pct: float = DEFAULT_REBALANCE_BAND_PCT
) -> dict[str, Any]:
    """Evaluate 4-ring thesis exposure weights against target percentages and rebalance bands."""
    if not slices or rebalance_band_pct <= 0.0:
        raise ValueError("INVALID_THESIS_EXPOSURE_SPEC: non-empty slices and band > 0 required")
    seen: set[str] = set()
    for sl in slices:
        if sl.ring_id not in VALID_THESIS_RINGS or sl.ring_id in seen:
            raise ValueError(f"INVALID_OR_DUPLICATE_THESIS_RING: {sl.ring_id!r}")
        if sl.target_pct < 0.0 or sl.current_value < 0.0:
            raise ValueError("NEGATIVE_THESIS_SLICE_VALUE")
        seen.add(sl.ring_id)
    target_sum = sum(sl.target_pct for sl in slices)
    if abs(target_sum - MAX_ALLOCATION_PCT) > ALLOCATION_TOLERANCE_PCT:
        raise ValueError(f"THESIS_TARGET_SUM_MISMATCH: expected 100.0%, got {target_sum:.2f}%")
    total_val = sum(sl.current_value for sl in slices)
    rows: list[dict[str, Any]] = []
    for sl in slices:
        actual = (sl.current_value / total_val * MAX_ALLOCATION_PCT) if total_val > 0.0 else 0.0
        drift = round(actual - sl.target_pct, 4)
        action = (
            "OVERWEIGHT"
            if drift > rebalance_band_pct
            else ("UNDERWEIGHT" if drift < -rebalance_band_pct else "ON_TARGET")
        )
        rows.append(
            {
                "ring_id": sl.ring_id,
                "target_pct": round(sl.target_pct, 2),
                "actual_pct": round(actual, 2),
                "drift_pct": round(drift, 2),
                "rebalance_action": action,
            }
        )
    return {"rebalance_band_pct": rebalance_band_pct, "slices": rows}


def project_portfolio_positions(
    positions: Sequence[PortfolioPosition], *, privacy_shield: bool = True
) -> dict[str, Any]:
    """Project holdings into Base-100 / % relative weights when privacy_shield is enabled."""
    vals: list[tuple[PortfolioPosition, float]] = []
    for pos in positions:
        if pos.thesis_ring not in VALID_THESIS_RINGS or pos.quantity < 0.0 or pos.unit_price < 0.0:
            raise ValueError(f"INVALID_PORTFOLIO_POSITION: {pos.asset_code!r}")
        vals.append((pos, pos.quantity * pos.unit_price))
    total_val = sum(v for _, v in vals)
    items: list[dict[str, Any]] = []
    for pos, m_val in vals:
        w_pct = (m_val / total_val * BASE_100_INDEX_SCALE) if total_val > 0.0 else 0.0
        row: dict[str, Any] = {
            "asset_code": pos.asset_code,
            "thesis_ring": pos.thesis_ring,
            "weight_pct": round(w_pct, 2),
            "base_100_index": round(w_pct, 2),
        }
        if not privacy_shield:
            row["quantity"] = round(pos.quantity, 6)
            row["market_value"] = round(m_val, 2)
        items.append(row)
    out: dict[str, Any] = {
        "privacy_shield": privacy_shield,
        "absolute_values_redacted": privacy_shield,
        "base_index_total": BASE_100_INDEX_SCALE if total_val > 0.0 else 0.0,
        "positions": items,
    }
    if not privacy_shield:
        out["total_market_value"] = round(total_val, 2)
    return out


def build_receipt_verification_url(channel: str, reference_id: str) -> str:
    """Build deterministic block-explorer or invoice URN verification URL for a receipt."""
    clean_ch = channel.strip().lower()
    clean_ref = assert_zero_custody_public_input(reference_id)
    if clean_ch not in VALID_RECEIPT_CHANNELS or not _has_charset_len(
        clean_ref, _SAFE_REF_CHARS, 4, 128
    ):
        raise ValueError(f"INVALID_RECEIPT_REFERENCE: {channel!r} / {reference_id!r}")
    if clean_ch == "bitcoin":
        return f"https://mempool.space/tx/{clean_ref}"
    if clean_ch == "evm":
        return f"https://etherscan.io/tx/{clean_ref}"
    if clean_ch == "solana":
        return f"https://solscan.io/tx/{clean_ref}"
    return f"urn:zcg:invoice:{clean_ref}"


def export_r0_public_stewardship_snapshot(
    *,
    node_id: str,
    public_watch_accounts: Sequence[Mapping[str, str]],
    receipts: Sequence[BilateralReceipt],
) -> dict[str, Any]:
    """Export sanitized R0 public reserve watch accounts and public patronage/venture receipts."""
    clean_node = node_id.strip()
    if not clean_node:
        raise ValueError("EMPTY_STEWARDSHIP_NODE_ID")
    sanitized_accounts: list[dict[str, str]] = []
    for acc in public_watch_accounts:
        chain, ref, addr = parse_caip10_account_id(str(acc.get("caip10_id") or ""))
        sanitized_accounts.append(
            {
                "caip10_id": f"{_CHAIN_TO_CAIP_NS[chain]}:{ref}:{addr}",
                "chain_family": chain,
                "address": addr,
                "label": str(acc.get("label") or f"{chain}-reserve"),
            }
        )
    pub_receipts = [
        r.to_dict()
        for r in receipts
        if r.receipt_kind in ("public-patronage", "venture-allocation")
    ]
    return {
        "schema_version": "zcg-stewardship-r0-v1",
        "node_id": clean_node,
        "ring": "R0",
        "absolute_private_balances_exposed": False,
        "public_reserve_accounts": sanitized_accounts,
        "verified_public_receipts": pub_receipts,
    }
