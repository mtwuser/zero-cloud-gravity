"""Privacy-preserving <persona>-work settlement airlock, venture radar, and 0%-plutocracy context.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from zcg.core.domain import is_kebab_id
from zcg.core.manifests import ensure_contained_path, load_node_manifest, read_version
from zcg.core.markdown_scan import contains_token_id, scan_markdown_checkboxes
from zcg.governance.work.ledger import summarize_work_orchestration_ledger
from zcg.plugins.wallet_ledger import (
    BilateralReceipt,
    assert_zero_custody_public_input,
    build_receipt_verification_url,
)
from zcg.plugins.wallet_treasury import WalletRuntimeStore
from zcg.topology.posture import resolve_governance_posture

SETTLEMENTS_REL_PATH: Final[str] = ".zcg/runtime/settlements/agreed_settlements.json"
VENTURE_RADAR_REL_PATH: Final[str] = ".zcg/runtime/wallet/venture_radar.json"
PRIOR_COUNTERPARTY_BADGE: Final[str] = "Verified Prior Counterparty Link"
PLUTOCRACY_WEIGHT_ZERO: Final[float] = 0.0
VALID_SETTLEMENT_ROLES: Final[tuple[str, ...]] = ("payee", "payer")


@dataclass(frozen=True, slots=True)
class CounterpartyHandshakeContext:
    """Human triage context for inbound link requests (0% plutocracy: auto_grant_ring is None)."""

    own_node_id: str
    candidate_peer_id: str
    verified_prior_counterparty: bool
    badge_label: str | None
    direct_receipt_count: int
    ignored_third_party_count: int
    auto_grant_ring: None = None
    plutocracy_weight: float = PLUTOCRACY_WEIGHT_ZERO

    def to_dict(self) -> dict[str, Any]:
        """Serialize handshake context to a JSON-compatible dictionary."""
        return asdict(self)


def _read_settlement_records(file_path: Path) -> list[dict[str, Any]]:
    if not file_path.is_file():
        return []
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    return [dict(it) for it in raw if isinstance(it, Mapping)] if isinstance(raw, list) else []


def _is_workvali_deliverable_verified(workspace_dir: Path, deliverable_id: str) -> bool:
    vali_path = workspace_dir / "WORKVALI.md"
    if not vali_path.is_file():
        return False
    items = scan_markdown_checkboxes(vali_path.read_text(encoding="utf-8"))
    return any(c.is_done and contains_token_id(c.body, deliverable_id) for c in items)


def bind_work_agreed_settlement(
    workspace_dir: Path,
    *,
    counterparty_node_id: str,
    deliverable_id: str,
    channel: str,
    reference_id: str,
    proof_digest: str,
    settlement_role: str = "payee",
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Bind an opt-in non-custodial agreed-settlement receipt on a linked work/enterprise node."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    posture = resolve_governance_posture(ws, manifest, parent_dir=parent_dir)
    if posture["personal_pillar"] == "wallet":
        raise ValueError(
            "WALLET_DIRECT_SETTLEMENT_BLOCKED: <persona>-wallet never connects to external "
            "counterparties; bind agreed-settlement via <persona>-work"
        )
    settlement_mode = str(manifest.get("settlement_mode") or "none").strip().lower()
    if settlement_mode not in ("manual-reference", "dedicated-settlement-endpoint"):
        raise ValueError(
            f"SETTLEMENT_MODE_DISABLED: node {posture['node_id']!r} has settlement_mode='none'"
        )
    clean_peer = counterparty_node_id.strip()
    clean_deliv = deliverable_id.strip()
    clean_digest = assert_zero_custody_public_input(proof_digest)
    clean_role = settlement_role.strip().lower()
    if not is_kebab_id(clean_peer) or not clean_deliv or clean_role not in VALID_SETTLEMENT_ROLES:
        raise ValueError("INVALID_SETTLEMENT_ARGUMENTS")
    linked_ids = {
        str(it.get("node_id") or "").strip()
        for it in manifest.get("linked_nodes", [])
        if isinstance(it, Mapping)
    }
    if clean_peer not in linked_ids:
        raise ValueError(f"UNLINKED_SETTLEMENT_COUNTERPARTY: {clean_peer!r} is not in linked_nodes")
    if not _is_workvali_deliverable_verified(ws, clean_deliv):
        raise ValueError(
            f"UNVERIFIED_WORKVALI_DELIVERABLE: {clean_deliv!r} is not checked [x] in WORKVALI.md"
        )
    build_receipt_verification_url(channel, reference_id)
    own_id = str(posture["node_id"])
    payer_id = clean_peer if clean_role == "payee" else own_id
    payee_id = own_id if clean_role == "payee" else clean_peer
    receipt = BilateralReceipt(
        receipt_id=f"settle-{clean_deliv.lower()}-{clean_peer}",
        receipt_kind="agreed-settlement",
        channel=channel.strip().lower(),
        reference_id=reference_id.strip(),
        payer_node_id=payer_id,
        payee_node_id=payee_id,
        proof_digest=clean_digest,
        recorded_at=dt.datetime.now(dt.UTC).isoformat(),
        public_note=f"Validated deliverable {clean_deliv} ({settlement_mode})",
    )
    out_file = ensure_contained_path(Path(SETTLEMENTS_REL_PATH), ws)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    existing = [
        it
        for it in _read_settlement_records(out_file)
        if it.get("receipt_id") != receipt.receipt_id
    ]
    rec_dict = receipt.to_dict()
    existing.append(rec_dict)
    out_file.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return {"settlement_mode": settlement_mode, "receipt": rec_dict}


def reconcile_wallet_airlock_pull(
    wallet_dir: Path,
    *,
    work_dir: Path,
    venture_dirs: Sequence[Path] = (),
) -> dict[str, Any]:
    """Pull agreed-settlements and venture-radar metrics unidirectionally into <persona>-wallet."""
    w_ws, wk_ws = wallet_dir.resolve(), work_dir.resolve()
    if resolve_governance_posture(w_ws)["personal_pillar"] != "wallet":
        raise ValueError("WALLET_PILLAR_REQUIRED: target workspace must be <persona>-wallet")
    if resolve_governance_posture(wk_ws)["personal_pillar"] != "work":
        raise ValueError("WORK_AIRLOCK_SOURCE_REQUIRED: source workspace must be <persona>-work")
    store = WalletRuntimeStore(w_ws)
    imported_ids: list[str] = []
    for it in _read_settlement_records(wk_ws / SETTLEMENTS_REL_PATH):
        rec = BilateralReceipt(
            receipt_id=str(it.get("receipt_id") or ""),
            receipt_kind="agreed-settlement",
            channel=str(it.get("channel") or "invoice"),
            reference_id=str(it.get("reference_id") or ""),
            payer_node_id=str(it.get("payer_node_id") or ""),
            payee_node_id=str(it.get("payee_node_id") or ""),
            proof_digest=str(it.get("proof_digest") or ""),
            recorded_at=str(it.get("recorded_at") or ""),
            public_note=str(it.get("public_note") or ""),
        )
        store.record_receipt(rec)
        imported_ids.append(rec.receipt_id)
    radar_rows: list[dict[str, Any]] = []
    for v_path in venture_dirs:
        v_ws = v_path.resolve()
        v_man = load_node_manifest(v_ws)
        ledger = summarize_work_orchestration_ledger(v_ws)["own_node_ledger"]
        radar_rows.append(
            {
                "node_id": str(v_man.get("layer_id") or v_ws.name),
                "version": read_version(v_ws),
                "completed_count": int(ledger["total_completed_items"]),
                "pending_count": int(ledger["total_open_items"])
                + int(ledger["total_in_progress_items"]),
            }
        )
    radar_file = ensure_contained_path(Path(VENTURE_RADAR_REL_PATH), w_ws)
    radar_doc = {
        "reconciled_from_work_node": str(load_node_manifest(wk_ws).get("layer_id") or wk_ws.name),
        "imported_settlement_ids": imported_ids,
        "venture_radar": radar_rows,
    }
    radar_file.write_text(json.dumps(radar_doc, indent=2) + "\n", encoding="utf-8")
    return radar_doc


def evaluate_counterparty_handshake_context(
    *,
    own_node_id: str,
    candidate_peer_id: str,
    receipts: Sequence[BilateralReceipt | Mapping[str, Any]],
) -> CounterpartyHandshakeContext:
    """Evaluate strictly direct bilateral counterparty history (immune to wash-trading)."""
    own = own_node_id.strip()
    peer = candidate_peer_id.strip()
    if not is_kebab_id(own) or not is_kebab_id(peer) or own == peer:
        raise ValueError("INVALID_HANDSHAKE_NODE_IDS: distinct kebab-case IDs required")
    expected_pair = {own, peer}
    direct_count, ignored_count = 0, 0
    for item in receipts:
        data = item.to_dict() if isinstance(item, BilateralReceipt) else dict(item)
        payer = str(data.get("payer_node_id") or "").strip()
        payee = str(data.get("payee_node_id") or "").strip()
        digest = str(data.get("proof_digest") or "").strip()
        if payer != payee and {payer, payee} == expected_pair and bool(digest):
            direct_count += 1
        else:
            ignored_count += 1
    verified = direct_count > 0
    return CounterpartyHandshakeContext(
        own_node_id=own,
        candidate_peer_id=peer,
        verified_prior_counterparty=verified,
        badge_label=PRIOR_COUNTERPARTY_BADGE if verified else None,
        direct_receipt_count=direct_count,
        ignored_third_party_count=ignored_count,
        auto_grant_ring=None,
        plutocracy_weight=PLUTOCRACY_WEIGHT_ZERO,
    )
