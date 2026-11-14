"""Deterministic bidirectional contract alignment and symmetry rebound engine.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.core.manifests import ensure_contained_path, load_node_manifest
from zcg.governance.authority import stage_non_destructive_proposal
from zcg.topology.identity import resolve_default_parent_dir

DEFAULT_CANONICAL_AXIS_GLOSSARY: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "architecture_tier": {
        "frontend": ("front", "fe", "ui-front"),
        "backend": ("bk", "back", "be"),
        "database": ("db", "rdbms"),
    },
    "environment": {
        "dev": ("development",),
        "tst": ("qa", "testing"),
        "pre": ("staging", "uat", "preprod"),
        "pro": ("prod", "production"),
    },
}
MIN_CONFLATED_TIERS: Final[int] = 2


def _parse_terms_mapping(raw_terms: object) -> dict[str, dict[str, tuple[str, ...]]]:
    if not isinstance(raw_terms, Mapping):
        return {}
    out: dict[str, dict[str, tuple[str, ...]]] = {}
    for raw_axis, raw_map in raw_terms.items():
        axis = str(raw_axis).strip().lower()
        if not axis or not isinstance(raw_map, Mapping):
            continue
        canon_map: dict[str, tuple[str, ...]] = {}
        for raw_canon, raw_aliases in raw_map.items():
            canon = str(raw_canon).strip().lower()
            if not canon or not isinstance(raw_aliases, (list, tuple)):
                continue
            aliases = tuple(
                str(a).strip().lower()
                for a in raw_aliases
                if str(a).strip() and str(a).strip().lower() != canon
            )
            canon_map[canon] = aliases
        if canon_map:
            out[axis] = canon_map
    return out


def _extract_node_handoff_contract(node_dir: Path | None) -> dict[str, Any]:
    if node_dir is None or not node_dir.is_dir():
        return {"terms": {}, "required_sections": (), "single_axis_per_item": False}
    manifest = load_node_manifest(node_dir) if (node_dir / NODE_MANIFEST_REL_PATH).is_file() else {}
    merged_terms = _parse_terms_mapping(manifest.get("canonical_terms"))
    tpl_root = node_dir / "templates"
    for g_file in sorted(tpl_root.rglob("glossary.json")) if tpl_root.is_dir() else ():
        doc = json.loads(g_file.read_text(encoding="utf-8"))
        for axis, cmap in _parse_terms_mapping(doc).items():
            cur_axis = merged_terms.get(axis, {})
            merged_terms[axis] = {**cur_axis, **cmap}
    raw_hc = manifest.get("handoff_contract")
    hc: Mapping[str, Any] = raw_hc if isinstance(raw_hc, Mapping) else {}
    raw_secs = hc.get("required_sections")
    secs = (
        tuple(str(s).strip() for s in raw_secs if str(s).strip())
        if isinstance(raw_secs, list)
        else ()
    )
    return {
        "terms": merged_terms,
        "required_sections": secs,
        "single_axis_per_item": bool(hc.get("single_axis_per_item", False)),
    }


def _build_alias_lookup(
    terms: Mapping[str, Mapping[str, tuple[str, ...]]],
) -> dict[tuple[str, str], str]:
    lookup: dict[tuple[str, str], str] = {}
    for axis, cmap in terms.items():
        for canon, aliases in cmap.items():
            for alias in aliases:
                lookup[(axis, alias)] = canon
    return lookup


def load_merged_canonical_glossary(
    sender_dir: Path,
    *,
    receiver_dir: Path | None = None,
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Merge canonical_terms and handoff_contract across Parent, Sender, and Receiver."""
    s_ws = sender_dir.resolve()
    r_ws = receiver_dir.resolve() if receiver_dir is not None else None
    eff_parent = resolve_default_parent_dir(s_ws, parent_dir)

    p_contract = _extract_node_handoff_contract(eff_parent)
    s_contract = _extract_node_handoff_contract(s_ws)
    r_contract = _extract_node_handoff_contract(r_ws)

    p_lookup = _build_alias_lookup(p_contract["terms"])
    s_lookup = _build_alias_lookup(s_contract["terms"])
    r_lookup = _build_alias_lookup(r_contract["terms"])

    conflicts: list[dict[str, str]] = []
    for key in sorted(set(s_lookup) & set(r_lookup)):
        if key not in p_lookup and s_lookup[key] != r_lookup[key]:
            axis, alias = key
            conflicts.append(
                {
                    "reason_code": "GLOSSARY_DEFINITION_CONFLICT",
                    "axis": axis,
                    "alias": alias,
                    "sender_canonical": s_lookup[key],
                    "receiver_canonical": r_lookup[key],
                }
            )

    effective_terms: dict[str, dict[str, tuple[str, ...]]] = {
        ax: dict(cmap) for ax, cmap in DEFAULT_CANONICAL_AXIS_GLOSSARY.items()
    }
    for layer_terms in (r_contract["terms"], s_contract["terms"], p_contract["terms"]):
        for ax, cmap in layer_terms.items():
            effective_terms[ax] = {**effective_terms.get(ax, {}), **cmap}

    base_axes = set(DEFAULT_CANONICAL_AXIS_GLOSSARY) | set(p_contract["terms"])
    unstandardized_axes = (
        sorted((set(s_contract["terms"]) ^ set(r_contract["terms"])) - base_axes)
        if r_ws is not None
        else []
    )
    p_secs = set(p_contract["required_sections"])
    unstandardized_sections = (
        sorted(
            (set(s_contract["required_sections"]) ^ set(r_contract["required_sections"])) - p_secs
        )
        if r_ws is not None
        else []
    )
    req_sections = list(
        dict.fromkeys([*p_contract["required_sections"], *r_contract["required_sections"]])
    )
    single_axis = bool(
        p_contract["single_axis_per_item"]
        or s_contract["single_axis_per_item"]
        or r_contract["single_axis_per_item"]
    )
    return {
        "terms": effective_terms,
        "conflicts": conflicts,
        "required_sections": req_sections,
        "single_axis_per_item": single_axis,
        "unstandardized_axes": unstandardized_axes,
        "unstandardized_sections": unstandardized_sections,
    }


def check_handoff_symmetry(
    sender_dir: Path,
    *,
    directive_text: str = "",
    source_rel_path: str | None = None,
    receiver_dir: Path | None = None,
    parent_dir: Path | None = None,
    single_axis_per_item: bool = False,
    stage_proposal: bool = False,
    actor_email: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Validate cross-layer directives for alias drift, axis conflation, or template asymmetry."""
    s_ws = sender_dir.resolve()
    raw_text = directive_text
    if source_rel_path is not None and source_rel_path.strip():
        src_file = ensure_contained_path(Path(source_rel_path.strip().lstrip("/")), s_ws)
        if not src_file.is_file():
            raise ValueError(f"Missing handoff source file: {source_rel_path!r}")
        raw_text = src_file.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ValueError(
            "Provide non-empty directive_text or --source <rel-path> for check-handoff"
        )

    merged = load_merged_canonical_glossary(s_ws, receiver_dir=receiver_dir, parent_dir=parent_dir)
    rebounds: list[dict[str, Any]] = [dict(c) for c in merged["conflicts"]]
    alias_rules: list[tuple[str, str, str, re.Pattern[str]]] = []
    for axis, cmap in sorted(merged["terms"].items()):
        for canon, aliases in sorted(cmap.items()):
            for alias in aliases:
                pat = re.compile(rf"(?<![./-])\b{re.escape(alias)}\b(?![./-])", re.IGNORECASE)
                alias_rules.append((axis, alias, canon, pat))

    norm_lines: list[str] = []
    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        upd = line
        for axis, alias, canon, pat in alias_rules:
            if pat.search(upd):
                rebounds.append(
                    {
                        "reason_code": "INFORMAL_ALIAS_REBOUND",
                        "axis": axis,
                        "informal_term": alias,
                        "canonical_term": canon,
                        "line": line_no,
                    }
                )
                upd = pat.sub(canon, upd)
        norm_lines.append(upd)
    normalized_text = "\n".join(norm_lines)

    eff_single = single_axis_per_item or bool(merged["single_axis_per_item"])
    tier_canons = tuple(merged["terms"].get("architecture_tier", ()))
    if eff_single and tier_canons:
        for line_no, line in enumerate(norm_lines, start=1):
            if line.lstrip().startswith("#"):
                continue
            found = [
                t
                for t in tier_canons
                if re.search(rf"(?<![./-])\b{re.escape(t)}\b(?![./-])", line, re.IGNORECASE)
            ]
            if len(found) >= MIN_CONFLATED_TIERS:
                rebounds.append(
                    {
                        "reason_code": "MULTI_AXIS_CONFLATION_REBOUND",
                        "axis": "architecture_tier",
                        "conflated_terms": found,
                        "line": line_no,
                    }
                )

    for req_sec in merged["required_sections"]:
        if req_sec not in normalized_text:
            rebounds.append(
                {
                    "reason_code": "MISSING_REQUIRED_HANDOFF_SECTION",
                    "required_section": req_sec,
                }
            )

    proposals: list[dict[str, Any]] = []
    staged_path: str | None = None
    has_asym = bool(merged["unstandardized_axes"] or merged["unstandardized_sections"])
    if not rebounds and receiver_dir is not None and has_asym:
        prop_entry = {
            "reason_code": "UNSTANDARDIZED_ASYMMETRY_PROPOSAL",
            "unstandardized_axes": merged["unstandardized_axes"],
            "unstandardized_sections": merged["unstandardized_sections"],
            "recommended_workflow": "/enrich -> make decision",
        }
        proposals.append(prop_entry)
        if stage_proposal and (s_ws / NODE_MANIFEST_REL_PATH).is_file():
            r_name = receiver_dir.resolve().name
            md_body = (
                f"# Handoff Standardization Proposal (`{s_ws.name}` <-> `{r_name}`)\n\n"
                f"- **Unstandardized Axes**: `{merged['unstandardized_axes']}`\n"
                f"- **Unstandardized Sections**: `{merged['unstandardized_sections']}`\n"
                "- **Action**: Align shared `canonical_terms` or `handoff_contract` in `/enrich`.\n"
            )
            staged_path = str(
                stage_non_destructive_proposal(
                    s_ws,
                    scope_tag="handoff-alignment",
                    file_name=f"align-{r_name}.md",
                    content=md_body,
                    operation="check-handoff",
                    actor_email=actor_email,
                    reason_code="UNSTANDARDIZED_ASYMMETRY_PROPOSAL",
                    dry_run=dry_run,
                )
            )

    status = "rebound" if rebounds else ("proposal" if proposals else "aligned")
    return {
        "sender_dir": str(s_ws),
        "receiver_dir": str(receiver_dir.resolve()) if receiver_dir is not None else None,
        "passed": status != "rebound",
        "status": status,
        "rebounds": rebounds,
        "proposals": proposals,
        "normalized_text": normalized_text,
        "staged_proposal": staged_path,
        "dry_run": dry_run,
    }
