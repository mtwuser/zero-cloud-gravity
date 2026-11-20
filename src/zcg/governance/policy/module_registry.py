"""Hierarchical Capability Module Registry (Archetype ⊥ Capability Module ⊥ Provider/Tool).

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.core.manifests import load_node_manifest
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_governance_posture

VALID_CAPABILITY_STATES: Final[tuple[str, ...]] = ("mandatory", "optional", "forbidden")
VALID_CAPABILITY_SLOTS: Final[tuple[str, ...]] = ("admin", "workspace", "public")
_AIRLOCK_FORBIDDEN_MODULES: Final[frozenset[str]] = frozenset({"portal_inbox", "role_projection"})


@dataclass(frozen=True, slots=True)
class CapabilityModuleSpec:
    """Declarative descriptor for a toggleable sovereign node Capability Module."""

    module_id: str
    title: str
    purpose: str
    slots: tuple[str, ...]
    provider_backing: str = "native"

    def to_dict(self) -> dict[str, Any]:
        """Serialize capability descriptor metadata to a JSON-compatible dictionary."""
        return {
            "module_id": self.module_id,
            "title": self.title,
            "purpose": self.purpose,
            "slots": list(self.slots),
            "provider_backing": self.provider_backing,
        }


TOGGLEABLE_CAPABILITY_CATALOG: Final[dict[str, CapabilityModuleSpec]] = {
    "work_ledger": CapabilityModuleSpec(
        "work_ledger",
        "Work Board",
        "Kanban task board, backlog promotion, and cross-node work coordination.",
        ("admin", "workspace"),
    ),
    "docs_reader": CapabilityModuleSpec(
        "docs_reader",
        "Docs & Knowledge",
        "Structured Markdown knowledge space across node, parent network, and corpora.",
        ("admin", "workspace"),
    ),
    "crud": CapabilityModuleSpec(
        "crud",
        "Domain Records",
        "Typed domain collection records, search filters, and structured views.",
        ("admin", "workspace"),
    ),
    "vault": CapabilityModuleSpec(
        "vault",
        "Document Vault",
        "Content-addressed SHA-256 private file and evidence vault (.zcg/runtime/).",
        ("admin", "workspace"),
    ),
    "spatial_atlas": CapabilityModuleSpec(
        "spatial_atlas",
        "Network Atlas",
        "Interactive 2D/3D network topology and 5-lens relational explorer.",
        ("admin", "workspace", "public"),
    ),
    "portal_inbox": CapabilityModuleSpec(
        "portal_inbox",
        "External Mailbox",
        "Inbound contact messages and peer handshake triage from public /portal.",
        ("admin", "workspace", "public"),
    ),
    "role_projection": CapabilityModuleSpec(
        "role_projection",
        "CV & Role Projection",
        "Ring-aware R0/R1/R3 dossier, verified competency, and A4 CV projection.",
        ("admin", "workspace", "public"),
    ),
    "data_pipeline": CapabilityModuleSpec(
        "data_pipeline",
        "Data Pipeline",
        "Deterministic ingestion, lineage verification, and corpus batch pipeline.",
        ("admin", "workspace"),
    ),
    "wallet_treasury": CapabilityModuleSpec(
        "wallet_treasury",
        "Treasury & Portfolio",
        "Zero-custody R0/R2/R3 treasury, bilateral receipts, and watch-only portfolio.",
        ("admin", "workspace", "public"),
        provider_backing="wallet-standard+eip6963",
    ),
}


def _clean_mod_set(raw: object) -> set[str]:
    if not isinstance(raw, list):
        return set()
    return {s for x in raw if (s := str(x).strip()) and s in TOGGLEABLE_CAPABILITY_CATALOG}


def _collect_lineage_module_bounds(
    ws: Path, *, view_archetype: str, parent_dir: Path | None
) -> tuple[set[str], set[str], dict[str, str], dict[str, Any]]:
    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    cands = [c.resolve() for c in (eff_parent, ws) if c and (c / NODE_MANIFEST_REL_PATH).is_file()]
    chain = list(dict.fromkeys(cands))
    forbidden, mandatory = set[str](), set[str]()
    reasons: dict[str, str] = {}
    self_m: dict[str, Any] = (
        load_node_manifest(ws) if (ws / NODE_MANIFEST_REL_PATH).is_file() else {}
    )

    for node_dir in chain:
        m_doc = load_node_manifest(node_dir)
        lid = str(m_doc.get("layer_id") or node_dir.name)
        raw_cap = m_doc.get("capability_policy")
        cap: Mapping[str, Any] = raw_cap if isinstance(raw_cap, Mapping) else {}
        for f_mod in _clean_mod_set(cap.get("forbidden_modules")):
            forbidden.add(f_mod)
            reasons[f_mod] = f"Blocked by {lid} capability_policy"
        for m_mod in _clean_mod_set(cap.get("mandatory_modules")):
            if m_mod not in forbidden:
                mandatory.add(m_mod)
                reasons[m_mod] = f"Required by {lid} capability_policy"

    if self_m:
        posture = resolve_governance_posture(ws, self_m, parent_dir=eff_parent)
        if not posture["allow_external_peer_links"]:
            for air_mod in _AIRLOCK_FORBIDDEN_MODULES:
                forbidden.add(air_mod)
                mandatory.discard(air_mod)
                reasons[air_mod] = "Blocked by R3 local-only wallet airlock"
    if view_archetype == "sovereign-wallet-cockpit" and "wallet_treasury" not in forbidden:
        mandatory.add("wallet_treasury")
        reasons.setdefault("wallet_treasury", "Core ledger for sovereign-wallet-cockpit")
    mandatory -= forbidden
    return forbidden, mandatory, reasons, self_m


def resolve_node_capability_matrix(
    workspace_dir: Path,
    *,
    view_archetype: str = "",
    default_modules: Sequence[str] = (),
    parent_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Resolve the 3-state (mandatory | optional | forbidden) capability matrix for a node."""
    ws = workspace_dir.resolve()
    forbidden, mandatory, reasons, self_m = _collect_lineage_module_bounds(
        ws, view_archetype=view_archetype, parent_dir=parent_dir
    )
    raw_en = self_m.get("enabled_modules")
    has_override = isinstance(raw_en, list)
    def_set = {str(m).strip() for m in default_modules if str(m).strip()}
    base_active = _clean_mod_set(raw_en) if has_override else def_set

    rows: list[dict[str, Any]] = []
    for mod_id, spec in TOGGLEABLE_CAPABILITY_CATALOG.items():
        if mod_id in forbidden:
            p_state, is_on, toggle_ok = "forbidden", False, False
        elif mod_id in mandatory:
            p_state, is_on, toggle_ok = "mandatory", True, False
        else:
            p_state, is_on, toggle_ok = "optional", (mod_id in base_active), True
        rows.append(
            {
                **spec.to_dict(),
                "policy_state": p_state,
                "enabled": is_on,
                "can_toggle": toggle_ok,
                "default_enabled": mod_id in def_set,
                "has_custom_override": has_override,
                "policy_reason": reasons.get(mod_id, "Delegated to node operator (R3)"),
            }
        )
    return rows


def resolve_effective_workspace_modules(
    workspace_dir: Path,
    *,
    view_archetype: str = "",
    default_modules: Sequence[str] = (),
    parent_dir: Path | None = None,
) -> tuple[str, ...]:
    """Return ordered active Workspace capability module IDs honoring policy bounds."""
    ws = workspace_dir.resolve()
    matrix = resolve_node_capability_matrix(
        ws, view_archetype=view_archetype, default_modules=default_modules, parent_dir=parent_dir
    )
    active_ids = {r["module_id"] for r in matrix if r["enabled"]}
    m_doc = load_node_manifest(ws) if (ws / NODE_MANIFEST_REL_PATH).is_file() else {}
    raw_pref = m_doc.get("enabled_modules")
    pref_order = (
        [str(x).strip() for x in raw_pref]
        if isinstance(raw_pref, list)
        else [str(x).strip() for x in default_modules]
    )
    ordered = [m for m in pref_order if m in active_ids]
    extras = [r["module_id"] for r in matrix if r["enabled"] and r["module_id"] not in ordered]
    return tuple(dict.fromkeys((*ordered, *extras)))


def set_node_capability_enabled(
    workspace_dir: Path,
    *,
    module_id: str,
    enabled: bool,
    view_archetype: str = "",
    default_modules: Sequence[str] = (),
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Toggle an optional capability module ON/OFF in system/zcg-node.json."""
    ws = workspace_dir.resolve()
    m_path = ws / NODE_MANIFEST_REL_PATH
    if not m_path.is_file():
        raise ValueError("WORKSPACE_MANIFEST_MISSING: system/zcg-node.json is required")
    clean_mod = module_id.strip()
    if clean_mod not in TOGGLEABLE_CAPABILITY_CATALOG:
        raise ValueError(f"UNKNOWN_CAPABILITY_MODULE: unknown capability {module_id!r}")
    matrix = resolve_node_capability_matrix(
        ws, view_archetype=view_archetype, default_modules=default_modules, parent_dir=parent_dir
    )
    by_id = {r["module_id"]: r for r in matrix}
    target = by_id[clean_mod]
    if target["policy_state"] == "forbidden" and enabled:
        raise ValueError(f"CAPABILITY_FORBIDDEN_BY_POLICY: {target['policy_reason']}")
    if target["policy_state"] == "mandatory" and not enabled:
        raise ValueError(f"CAPABILITY_MANDATORY_BY_POLICY: {target['policy_reason']}")

    cur_active = list(
        resolve_effective_workspace_modules(
            ws,
            view_archetype=view_archetype,
            default_modules=default_modules,
            parent_dir=parent_dir,
        )
    )
    if enabled and clean_mod not in cur_active:
        cur_active.append(clean_mod)
    elif not enabled:
        cur_active = [m for m in cur_active if m != clean_mod]

    m_doc = load_node_manifest(ws)
    next_doc = {**m_doc, "enabled_modules": cur_active}
    m_path.write_text(json.dumps(next_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    updated = resolve_node_capability_matrix(
        ws, view_archetype=view_archetype, default_modules=default_modules, parent_dir=parent_dir
    )
    return {
        "module_id": clean_mod,
        "enabled": enabled,
        "enabled_modules": cur_active,
        "capabilities": updated,
    }


def reset_node_capabilities_default(
    workspace_dir: Path,
    *,
    view_archetype: str = "",
    default_modules: Sequence[str] = (),
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Remove custom enabled_modules override in system/zcg-node.json to restore defaults."""
    ws = workspace_dir.resolve()
    m_path = ws / NODE_MANIFEST_REL_PATH
    if not m_path.is_file():
        raise ValueError("WORKSPACE_MANIFEST_MISSING: system/zcg-node.json is required")
    m_doc = load_node_manifest(ws)
    cleaned = {k: v for k, v in m_doc.items() if k != "enabled_modules"}
    m_path.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    eff = list(
        resolve_effective_workspace_modules(
            ws,
            view_archetype=view_archetype,
            default_modules=default_modules,
            parent_dir=parent_dir,
        )
    )
    return {
        "reset": True,
        "enabled_modules": eff,
        "capabilities": resolve_node_capability_matrix(
            ws,
            view_archetype=view_archetype,
            default_modules=default_modules,
            parent_dir=parent_dir,
        ),
    }
