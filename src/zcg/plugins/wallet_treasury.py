"""Watch-only SQLite WAL treasury store, Phantom/EIP-6963 discovery UI, and R0/R2/R3 APIRouter.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import sqlite3
from collections.abc import Iterator
from functools import lru_cache
from http import HTTPStatus
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

from zcg.core.manifests import ensure_contained_path
from zcg.plugins.wallet_ledger import (
    VALID_RECEIPT_KINDS,
    VALID_WALLET_RING_MODES,
    BilateralReceipt,
    CashflowBucketsSpec,
    PortfolioPosition,
    ThesisExposureSlice,
    assert_zero_custody_public_input,
    build_receipt_verification_url,
    compute_cashflow_buckets,
    compute_thesis_exposure_drift,
    export_r0_public_stewardship_snapshot,
    format_caip10_account_id,
    project_portfolio_positions,
)
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import JSON_CONTENT_TYPE, Request, WebResponse, respond
from zcg.web.http.router import APIRouter
from zcg.web.ui.templates import SafeHTML, TemplateCatalog

WALLET_RUNTIME_REL_DIR: Final[str] = ".zcg/runtime/wallet"
WALLET_DB_FILENAME: Final[str] = "wallet_watch.sqlite3"
SUPPORTED_WALLET_DISCOVERY_STANDARDS: Final[tuple[str, ...]] = (
    "Wallet Standard (window.navigator.wallets)",
    "EIP-6963 (eip6963:announceProvider)",
)
SUPPORTED_NON_CUSTODIAL_PROVIDERS: Final[tuple[str, ...]] = (
    "Phantom (BTC + EVM + Solana)",
    "Ledger Hardware Watch",
    "Trezor Hardware Watch",
    "Squads Multisig (Solana)",
    "Safe {Wallet} Multisig (EVM)",
)

_DEFAULT_THESIS_SLICES: Final[tuple[ThesisExposureSlice, ...]] = (
    ThesisExposureSlice("core_index", 45.0, 460.0),
    ThesisExposureSlice("direct_ecosystem_stack", 25.0, 250.0),
    ThesisExposureSlice("symbiotic_supply_chain", 20.0, 190.0),
    ThesisExposureSlice("validated_consumption", 10.0, 100.0),
)
_DEFAULT_POSITIONS: Final[tuple[PortfolioPosition, ...]] = (
    PortfolioPosition("IDX-CORE", "core_index", 4.6, 100.0),
    PortfolioPosition("STACK-INFRA", "direct_ecosystem_stack", 2.5, 100.0),
    PortfolioPosition("FAB-ENERGY", "symbiotic_supply_chain", 1.9, 100.0),
    PortfolioPosition("VERIFIED-USE", "validated_consumption", 1.0, 100.0),
)
_DEFAULT_CASHFLOW_SPEC: Final[CashflowBucketsSpec] = CashflowBucketsSpec(
    net_profit_vault_pct=20.0,
    statutory_tax_reserve_pct=25.0,
    opex_ceiling_pct=35.0,
    fixed_operator_payout_units=150.0,
)


class WalletRuntimeStore:
    """Path-contained watch-only SQLite WAL persistence under <ws>/.zcg/runtime/wallet/."""

    def __init__(self, workspace_dir: Path) -> None:
        """Initialize SQLite WAL schema inside contained .zcg/runtime/wallet/ directory."""
        ws = workspace_dir.resolve()
        rt_dir = ensure_contained_path(Path(WALLET_RUNTIME_REL_DIR), ws)
        rt_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = ensure_contained_path(Path(WALLET_RUNTIME_REL_DIR) / WALLET_DB_FILENAME, ws)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS watch_addresses ("
                "caip10_id TEXT PRIMARY KEY, chain_family TEXT NOT NULL, "
                "chain_reference TEXT NOT NULL, address TEXT NOT NULL, "
                "wallet_provider TEXT NOT NULL, label TEXT NOT NULL, "
                "ring_visibility TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS bilateral_receipts ("
                "receipt_id TEXT PRIMARY KEY, receipt_kind TEXT NOT NULL, "
                "channel TEXT NOT NULL, reference_id TEXT NOT NULL, "
                "payer_node_id TEXT NOT NULL, payee_node_id TEXT NOT NULL, "
                "proof_digest TEXT NOT NULL, recorded_at TEXT NOT NULL, public_note TEXT NOT NULL)"
            )

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.row_factory = sqlite3.Row
            with conn:
                yield conn
        finally:
            conn.close()

    def register_watch_address(
        self,
        *,
        chain_family: str,
        chain_reference: str,
        address: str,
        wallet_provider: str = "manual-watch",
        label: str = "",
        ring_visibility: str = "R3",
    ) -> dict[str, str]:
        """Validate public watch-only address and upsert into .zcg/runtime/wallet/ SQLite WAL."""
        ring = ring_visibility.strip().upper()
        if ring not in VALID_WALLET_RING_MODES:
            raise ValueError(f"INVALID_WALLET_RING: {ring_visibility!r}")
        caip10 = format_caip10_account_id(chain_family, chain_reference, address)
        clean_prov = assert_zero_custody_public_input(wallet_provider)
        clean_lbl = assert_zero_custody_public_input(label or f"{chain_family.strip()}-watch")
        now_iso = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO watch_addresses VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    caip10,
                    chain_family.strip().lower(),
                    chain_reference.strip(),
                    address.strip(),
                    clean_prov,
                    clean_lbl,
                    ring,
                    now_iso,
                ),
            )
        return {
            "caip10_id": caip10,
            "chain_family": chain_family.strip().lower(),
            "address": address.strip(),
            "wallet_provider": clean_prov,
            "label": clean_lbl,
            "ring_visibility": ring,
        }

    def list_watch_addresses(self, *, ring_mode: str = "R3") -> list[dict[str, str]]:
        """List watch-only accounts permitted by the requested R0 / R2 / R3 capability ring."""
        ring = ring_mode.strip().upper()
        allowed = {"R0"} if ring == "R0" else ({"R0", "R2"} if ring == "R2" else {"R0", "R2", "R3"})
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT caip10_id, chain_family, address, wallet_provider, label, ring_visibility "
                "FROM watch_addresses ORDER BY caip10_id"
            ).fetchall()
        return [dict(r) for r in rows if str(r["ring_visibility"]) in allowed]

    def record_receipt(self, receipt: BilateralReceipt) -> dict[str, str]:
        """Validate and persist a non-custodial bilateral receipt."""
        if receipt.receipt_kind not in VALID_RECEIPT_KINDS:
            raise ValueError(f"INVALID_RECEIPT_KIND: {receipt.receipt_kind!r}")
        if not receipt.receipt_id.strip() or not receipt.proof_digest.strip():
            raise ValueError("INVALID_RECEIPT_METADATA: receipt_id and proof_digest required")
        build_receipt_verification_url(receipt.channel, receipt.reference_id)
        if receipt.public_note:
            assert_zero_custody_public_input(receipt.public_note)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO bilateral_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    receipt.receipt_id.strip(),
                    receipt.receipt_kind,
                    receipt.channel.strip().lower(),
                    receipt.reference_id.strip(),
                    receipt.payer_node_id.strip(),
                    receipt.payee_node_id.strip(),
                    receipt.proof_digest.strip(),
                    receipt.recorded_at.strip(),
                    receipt.public_note.strip(),
                ),
            )
        return receipt.to_dict()

    def list_receipts(self, *, ring_mode: str = "R3") -> list[BilateralReceipt]:
        """List bilateral receipts scoped by ring (agreed-settlement hidden from public R0)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM bilateral_receipts ORDER BY recorded_at DESC, receipt_id ASC"
            ).fetchall()
        all_items = [
            BilateralReceipt(
                receipt_id=str(r["receipt_id"]),
                receipt_kind=str(r["receipt_kind"]),
                channel=str(r["channel"]),
                reference_id=str(r["reference_id"]),
                payer_node_id=str(r["payer_node_id"]),
                payee_node_id=str(r["payee_node_id"]),
                proof_digest=str(r["proof_digest"]),
                recorded_at=str(r["recorded_at"]),
                public_note=str(r["public_note"]),
            )
            for r in rows
        ]
        if ring_mode.strip().upper() == "R0":
            return [
                it
                for it in all_items
                if it.receipt_kind in ("public-patronage", "venture-allocation")
            ]
        return all_items


@lru_cache(maxsize=1)
def _wallet_template_catalog() -> TemplateCatalog:
    tpl_dir = Path(str(files("zcg.plugins").joinpath("templates")))
    return TemplateCatalog((tpl_dir,))


def render_wallet_cockpit_html(
    *,
    surface_label: str,
    ring_mode: str,
    privacy_shield: bool,
    watch_accounts: list[dict[str, str]],
    receipts: list[dict[str, str]],
) -> SafeHTML:
    """Render WCAG 2.2 AA zero-custody treasury HTML with Phantom / EIP-6963 discovery."""
    return _wallet_template_catalog().render(
        "wallet_cockpit.html",
        {
            "surface_label": surface_label,
            "ring_mode": ring_mode,
            "privacy_shield": privacy_shield,
            "providers_txt": " · ".join(SUPPORTED_NON_CUSTODIAL_PROVIDERS),
            "watch_accounts": watch_accounts,
            "receipts": receipts,
        },
    )


def create_wallet_treasury_router(
    workspace_dir: Path,
    *,
    default_ring_mode: str = "R3",
    surface_label: str = "sovereign-node",
    prefix: str = "/api/wallet-treasury",
) -> APIRouter:
    """Create composable multi-ring wallet & treasury APIRouter (R0 / R2 / R3)."""
    store = WalletRuntimeStore(workspace_dir)
    router = APIRouter(prefix=prefix, tags=("wallet-treasury",))

    @router.get("", summary="Inspect multi-ring watch-only treasury, buckets, and Base-100 shield")
    def inspect_treasury(request: Request) -> WebResponse:
        ring = (request.query("ring", default_ring_mode) or default_ring_mode).strip().upper()
        if ring not in VALID_WALLET_RING_MODES:
            raise WebAppError(
                f"Invalid wallet ring {ring!r}",
                error_code="INVALID_WALLET_RING",
                http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        raw_sh = (request.query("privacy_shield", "1") or "1").strip().lower()
        shield = True if ring == "R0" else raw_sh not in ("0", "false", "off")
        accounts = store.list_watch_addresses(ring_mode=ring)
        recs = [r.to_dict() for r in store.list_receipts(ring_mode=ring)]
        payload: dict[str, Any] = {
            "surface_label": surface_label,
            "ring_mode": ring,
            "discovery_standards": list(SUPPORTED_WALLET_DISCOVERY_STANDARDS),
            "supported_providers": list(SUPPORTED_NON_CUSTODIAL_PROVIDERS),
            "watch_accounts": accounts,
            "receipts": recs,
        }
        if ring in ("R2", "R3"):
            payload["cashflow_buckets"] = compute_cashflow_buckets(1000.0, _DEFAULT_CASHFLOW_SPEC)
        if ring == "R3":
            payload["portfolio"] = project_portfolio_positions(
                _DEFAULT_POSITIONS, privacy_shield=shield
            )
            payload["thesis_exposure"] = compute_thesis_exposure_drift(_DEFAULT_THESIS_SLICES)
        frag = render_wallet_cockpit_html(
            surface_label=surface_label,
            ring_mode=ring,
            privacy_shield=shield,
            watch_accounts=accounts,
            receipts=recs,
        )
        return respond(request, html_fragment=str(frag), data=payload)

    @router.get("/export-r0", summary="Export deterministic R0 public stewardship & receipts JSON")
    def export_r0(_request: Request) -> WebResponse:
        snap = export_r0_public_stewardship_snapshot(
            node_id=surface_label,
            public_watch_accounts=store.list_watch_addresses(ring_mode="R0"),
            receipts=store.list_receipts(ring_mode="R0"),
        )
        return WebResponse(
            int(HTTPStatus.OK), JSON_CONTENT_TYPE,
            json.dumps(snap).encode("utf-8"), DeliveryChannel.ISLAND_SYNC,
        )  # fmt: skip

    @router.post("/watch-address", summary="Register a validated zero-custody watch address")
    def add_watch_address(request: Request) -> WebResponse:
        body = request.json()
        data = body if isinstance(body, dict) else {}
        try:
            saved = store.register_watch_address(
                chain_family=str(data.get("chain_family") or ""),
                chain_reference=str(data.get("chain_reference") or "mainnet"),
                address=str(data.get("address") or ""),
                wallet_provider=str(data.get("wallet_provider") or "Phantom"),
                label=str(data.get("label") or ""),
                ring_visibility=str(data.get("ring_visibility") or default_ring_mode),
            )
        except ValueError as exc:
            msg = str(exc)
            is_secret = "PRIVATE_SECRET_REJECTED" in msg
            raise WebAppError(
                msg,
                error_code="PRIVATE_SECRET_REJECTED" if is_secret else "INVALID_WATCH_ADDRESS",
                http_status=int(
                    HTTPStatus.UNPROCESSABLE_ENTITY if is_secret else HTTPStatus.BAD_REQUEST
                ),
                severity=ErrorSeverity.ERROR if is_secret else ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            ) from exc
        return WebResponse(
            int(HTTPStatus.CREATED), JSON_CONTENT_TYPE,
            json.dumps(saved).encode("utf-8"), DeliveryChannel.ISLAND_SYNC,
        )  # fmt: skip

    @router.post("/receipts", summary="Record a verified non-custodial bilateral receipt")
    def add_receipt(request: Request) -> WebResponse:
        body = request.json()
        data = body if isinstance(body, dict) else {}
        rec = BilateralReceipt(
            receipt_id=str(data.get("receipt_id") or ""),
            receipt_kind=str(data.get("receipt_kind") or ""),
            channel=str(data.get("channel") or ""),
            reference_id=str(data.get("reference_id") or ""),
            payer_node_id=str(data.get("payer_node_id") or ""),
            payee_node_id=str(data.get("payee_node_id") or ""),
            proof_digest=str(data.get("proof_digest") or ""),
            recorded_at=str(data.get("recorded_at") or dt.datetime.now(dt.UTC).isoformat()),
            public_note=str(data.get("public_note") or ""),
        )
        try:
            saved = store.record_receipt(rec)
        except ValueError as exc:
            raise WebAppError(
                str(exc),
                error_code="INVALID_BILATERAL_RECEIPT",
                http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            ) from exc
        return WebResponse(
            int(HTTPStatus.CREATED), JSON_CONTENT_TYPE,
            json.dumps(saved).encode("utf-8"), DeliveryChannel.ISLAND_SYNC,
        )  # fmt: skip

    return router
