"""Unit tests for zcg.plugins.wallet_treasury.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from zcg.plugins.wallet_ledger import BilateralReceipt
from zcg.plugins.wallet_treasury import (
    WalletRuntimeStore,
    create_wallet_treasury_router,
    render_wallet_cockpit_html,
)
from zcg.web.http.factory import create_web_app
from zcg.web.http.request import Message, Scope

if TYPE_CHECKING:
    from pathlib import Path


async def _call_asgi(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    hdrs = {"accept": "application/json", **(headers or {})}
    if body:
        hdrs.setdefault("content-type", "application/json")
        hdrs["content-length"] = str(len(body))
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": [(k.encode("latin1"), v.encode("latin1")) for k, v in hdrs.items()],
    }
    sent: list[Message] = []
    consumed = False

    async def receive() -> Message:
        nonlocal consumed
        if not consumed:
            consumed = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg: Message) -> None:
        sent.append(msg)

    await app(scope, receive, send)
    return int(sent[0]["status"]), b"".join(bytes(m.get("body", b"")) for m in sent[1:])


class TestWalletTreasury:
    """4-quadrant AAA suite for WalletRuntimeStore, Phantom HTML renderer, and R0/R2/R3 router."""

    def test_wallet_runtime_store_ring_scoping_and_guards_expected(self, tmp_path: Path) -> None:
        """Verify SQLite WAL watch-address and receipt filtering across R0, R2, and R3."""
        # Arrange
        store = WalletRuntimeStore(tmp_path)
        evm_r0 = "0x71C7656EC7ab88b098defB751B7401B5f6d8976F"
        sol_r2 = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
        btc_r3 = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        rec_pub = BilateralReceipt(
            "r-pub",
            "public-patronage",
            "evm",
            "0xabc123",
            "peer-a",
            "zcg-org",
            "sha256:1",
            "2026-11-15",
            "Sponsor",
        )
        rec_set = BilateralReceipt(
            "r-set",
            "agreed-settlement",
            "invoice",
            "INV-99",
            "corp-a",
            "persona-work",
            "sha256:2",
            "2026-11-15",
        )

        # Act
        store.register_watch_address(
            chain_family="evm",
            chain_reference="1",
            address=evm_r0,
            label="Public Reserve",
            ring_visibility="R0",
        )
        store.register_watch_address(
            chain_family="solana", chain_reference="mainnet", address=sol_r2, ring_visibility="R2"
        )
        store.register_watch_address(
            chain_family="bitcoin", chain_reference="mainnet", address=btc_r3, ring_visibility="R3"
        )
        store.record_receipt(rec_pub)
        store.record_receipt(rec_set)
        r0_accs = store.list_watch_addresses(ring_mode="R0")
        r2_accs = store.list_watch_addresses(ring_mode="R2")
        r3_accs = store.list_watch_addresses(ring_mode="R3")
        r0_recs = store.list_receipts(ring_mode="R0")
        r3_recs = store.list_receipts(ring_mode="R3")
        empty_html = render_wallet_cockpit_html(
            surface_label="persona-wallet",
            ring_mode="R3",
            privacy_shield=True,
            watch_accounts=[],
            receipts=[],
        )
        populated_html = render_wallet_cockpit_html(
            surface_label="persona-wallet",
            ring_mode="R3",
            privacy_shield=False,
            watch_accounts=r3_accs,
            receipts=[r.to_dict() for r in r3_recs],
        )

        # Assert
        assert len(r0_accs) == 1 and len(r2_accs) == 2 and len(r3_accs) == 3
        assert [r.receipt_id for r in r0_recs] == ["r-pub"]
        assert len(r3_recs) == 2
        assert "Phantom (BTC + EVM + Solana)" in str(empty_html)
        assert "Base-100 / % Shield ON" in str(empty_html)
        assert "Local Operator Unshielded" in str(populated_html)
        with pytest.raises(ValueError, match="INVALID_WALLET_RING"):
            store.register_watch_address(
                chain_family="evm", chain_reference="1", address=evm_r0, ring_visibility="R9"
            )
        with pytest.raises(ValueError, match="INVALID_RECEIPT_KIND"):
            store.record_receipt(
                BilateralReceipt("x", "unknown", "evm", "0x1234", "a", "b", "d", "2026-11-15")
            )
        with pytest.raises(ValueError, match="INVALID_RECEIPT_METADATA"):
            store.record_receipt(
                BilateralReceipt(
                    " ", "public-patronage", "evm", "0x1234", "a", "b", " ", "2026-11-15"
                )
            )

    def test_wallet_treasury_router_endpoints_and_secret_rejection_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify GET R0/R2/R3, GET /export-r0, POST /watch-address (422), and POST /receipts."""
        # Arrange
        csrf = "tok-wallet-01"
        router = create_wallet_treasury_router(tmp_path, surface_label="zerocloudgravity")
        app = create_web_app(routers=(router,), csrf_token=csrf)
        csrf_hdr = {"x-zcg-csrf-token": csrf}
        valid_watch = json.dumps(
            {
                "chain_family": "evm",
                "chain_reference": "1",
                "address": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
                "wallet_provider": "Phantom",
                "ring_visibility": "R0",
            }
        ).encode("utf-8")
        secret_watch = json.dumps(
            {"chain_family": "evm", "chain_reference": "1", "address": "0x" + ("f" * 64)}
        ).encode("utf-8")
        valid_rec = json.dumps(
            {
                "receipt_id": "pat-01",
                "receipt_kind": "public-patronage",
                "channel": "evm",
                "reference_id": "0x99887766",
                "payer_node_id": "supporter-node",
                "payee_node_id": "zerocloudgravity",
                "proof_digest": "caip122:verified",
            }
        ).encode("utf-8")

        # Act
        st_add, _ = asyncio.run(
            _call_asgi(
                app,
                "POST",
                "/api/wallet-treasury/watch-address",
                body=valid_watch,
                headers=csrf_hdr,
            )
        )
        st_sec, b_sec = asyncio.run(
            _call_asgi(
                app,
                "POST",
                "/api/wallet-treasury/watch-address",
                body=secret_watch,
                headers=csrf_hdr,
            )
        )
        st_bad_w, _ = asyncio.run(
            _call_asgi(
                app, "POST", "/api/wallet-treasury/watch-address", body=b"[1]", headers=csrf_hdr
            )
        )
        st_rec, _ = asyncio.run(
            _call_asgi(
                app, "POST", "/api/wallet-treasury/receipts", body=valid_rec, headers=csrf_hdr
            )
        )
        st_bad_r, _ = asyncio.run(
            _call_asgi(app, "POST", "/api/wallet-treasury/receipts", body=b"[1]", headers=csrf_hdr)
        )
        st_r0, b_r0 = asyncio.run(
            _call_asgi(app, "GET", "/api/wallet-treasury", query="ring=R0&privacy_shield=0")
        )
        st_r2, b_r2 = asyncio.run(_call_asgi(app, "GET", "/api/wallet-treasury", query="ring=R2"))
        st_r3, b_r3 = asyncio.run(
            _call_asgi(app, "GET", "/api/wallet-treasury", query="ring=R3&privacy_shield=0")
        )
        st_bad_ring, _ = asyncio.run(
            _call_asgi(app, "GET", "/api/wallet-treasury", query="ring=R9")
        )
        st_exp, b_exp = asyncio.run(_call_asgi(app, "GET", "/api/wallet-treasury/export-r0"))

        # Assert
        assert st_add == 201 and st_rec == 201
        assert st_sec == 422 and json.loads(b_sec)["error"] == "PRIVATE_SECRET_REJECTED"
        assert st_bad_w == 400 and st_bad_r == 400 and st_bad_ring == 400
        assert st_r0 == 200 and "cashflow_buckets" not in json.loads(b_r0)
        assert (
            st_r2 == 200
            and "cashflow_buckets" in json.loads(b_r2)
            and "portfolio" not in json.loads(b_r2)
        )
        assert st_r3 == 200 and json.loads(b_r3)["portfolio"]["privacy_shield"] is False
        assert st_exp == 200 and len(json.loads(b_exp)["verified_public_receipts"]) == 1
