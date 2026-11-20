"""Human-Stack facets, dual-plane language policy, and epistemic knowledge resolution.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from zcg.core.constants import (
    CANONICAL_SCIENCE_TRUNKS,
    DEFAULT_INTERACTION_LANGUAGE,
    DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY,
    INTERACTION_LANGUAGE_LABELS,
    KNOWLEDGE_DOMAIN_TAXONOMY,
    NODE_MANIFEST_REL_PATH,
    VALID_HUMAN_MASTERY_LEVELS,
    VALID_HUMAN_STACK_FACETS,
    VALID_INTERACTION_LANGUAGES,
    VALID_KNOWLEDGE_PREFIXES,
    VALID_KNOWLEDGE_STEWARDSHIP_STAGES,
)
from zcg.core.manifests import ensure_contained_path, load_node_manifest

_HUMAN_STACK_LABELS: tuple[str, ...] = (
    "human-stack",
    "human-stack profile",
    "human-stack (optional)",
    "human-stack profile (optional)",
)
_INTERACTION_LANG_MARKER: str = "Interaction Language:"


def _extract_human_stack_line_value(markdown_text: str) -> str:
    for raw_line in markdown_text.splitlines():
        head, sep, rhs = raw_line.partition(":")
        label = head.strip().lstrip("-*").strip().strip("*").strip().lower()
        if sep and label in _HUMAN_STACK_LABELS:
            return rhs.strip()
    return ""


def _extract_interaction_language_code(markdown_text: str) -> str:
    if _INTERACTION_LANG_MARKER not in markdown_text:
        return ""
    line_tail = markdown_text.split(_INTERACTION_LANG_MARKER, 1)[1].splitlines()[0]
    label_part, open_p, after_open = line_tail.partition("(")
    code, close_p, _ = after_open.partition(")")
    clean_lbl = label_part.strip()
    if (
        open_p
        and close_p
        and clean_lbl.isascii()
        and clean_lbl.isalpha()
        and len(code) == 2
        and code.isascii()
        and code.isalpha()
        and code.islower()
    ):
        return code
    return ""


VALID_GLOBAL_PROFILES: tuple[str, ...] = (
    "universal-base",
    "academic-base",
    "science-base",
    "business-base",
    "academic",
    "science",
    "technical",
    "business",
    "full",
)
_UB, _AB = ("universal-base", "universal-base.md"), ("academic-base", "academic-base.md")
_SB = ("science-base", "science-base.md")
_SE = ("software-engineering", "software-engineering.md")
_BB = ("business-base", "business-base.md")
PROFILE_TEMPLATE_CHAIN: dict[str, tuple[tuple[str, str], ...]] = {
    "universal-base": (_UB,),
    "academic-base": (_UB, _AB),
    "science-base": (_UB, _SB),
    "business-base": (_UB, _BB),
    "academic": (_UB, _AB),
    "science": (_UB, _SB),
    "technical": (_UB, _SB, _SE),
    "business": (_UB, _BB),
    "full": (_UB, _AB, _SB, _SE, _BB),
}


def normalize_human_stack_tokens(raw_value: Any) -> list[str]:
    """Parse and validate Human-Stack facets (domain-<area>:M1..M4, bridge-*, soft-*, hat-*)."""
    parts = (
        [str(x) for x in raw_value]
        if isinstance(raw_value, list)
        else str(raw_value or "").replace("|", ",").split(",")
    )
    valid: list[str] = []
    for p in parts:
        tok = p.strip().strip("`")
        if not tok or not tok.startswith(VALID_HUMAN_STACK_FACETS):
            continue
        if tok.startswith("domain-"):
            area, _, lvl = tok.partition(":")
            if area != "domain-" and lvl in VALID_HUMAN_MASTERY_LEVELS and tok not in valid:
                valid.append(tok)
        elif len(tok.split("-", 1)[1].strip("]*")) > 0 and tok not in valid:
            valid.append(tok)
    return valid


def resolve_effective_human_stack(
    workspace_dir: Path, manifest: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Resolve Human-Stack facets across SESSION.md -> Blueprint -> zcg-node.json."""
    ws = workspace_dir.resolve()
    m = manifest if manifest is not None else load_node_manifest(ws)
    sources = (
        ("workspace-session", ws / ".agents/SESSION.md"),
        ("layer-blueprint", ws / ".agents/LAYER_LINEAGE.md"),
        ("layer-blueprint", ws / "README.md"),
    )
    for scope_name, fpath in sources:
        if (
            fpath.is_file()
            and (raw_hs := _extract_human_stack_line_value(fpath.read_text(encoding="utf-8")))
            and (tokens := normalize_human_stack_tokens(raw_hs))
        ):
            return {"facets": tokens, "scope": scope_name}
    if m_tokens := normalize_human_stack_tokens(m.get("human_stack")):
        return {"facets": m_tokens, "scope": "layer-manifest"}
    return {"facets": [], "scope": "default-none"}


def resolve_effective_interaction_language(
    workspace_dir: Path,
    manifest: dict[str, Any] | None = None,
    *,
    parent_dir: Path | None = None,
    home_dir: Path | None = None,
) -> dict[str, str]:
    """Resolve interaction_language across Workspace -> Parent -> Workstation Home -> Default."""
    ws = workspace_dir.resolve()
    m = manifest if manifest is not None else load_node_manifest(ws)
    p_m = load_node_manifest(parent_dir.resolve()) if parent_dir else {}
    h_l = ""
    if home_dir is not None:
        eff_h = home_dir.resolve()
        hm = load_node_manifest(eff_h / "zero-cloud-gravity")
        ag_p = eff_h / ".gemini/config/AGENTS.md"
        ag_code = (
            _extract_interaction_language_code(ag_p.read_text(encoding="utf-8"))
            if ag_p.is_file()
            else ""
        )
        h_l = str(hm.get("interaction_language") or ag_code).strip()
    cands = (
        (str(m.get("interaction_language") or "").strip(), "workspace-manifest"),
        (str(p_m.get("interaction_language") or "").strip(), "parent-layer-manifest"),
        (h_l, "workstation-home"),
    )
    il, scope = next(
        ((c, s) for c, s in cands if c in VALID_INTERACTION_LANGUAGES),
        (DEFAULT_INTERACTION_LANGUAGE, "default-en"),
    )
    return {
        "artifact_language": "en", "interaction_language": il,
        "interaction_label": INTERACTION_LANGUAGE_LABELS[il], "language_scope": scope,
    }  # fmt: skip


def _resolve_science_trunk(slug: str) -> tuple[str, str]:
    if slug in CANONICAL_SCIENCE_TRUNKS:
        return slug, "trunk-repository"
    for trunk, branches in CANONICAL_SCIENCE_TRUNKS.items():
        if slug in branches:
            return trunk, "branch-repository"
    return "custom-science", "branch-repository"


def classify_knowledge_domain(layer_id: str, layer_role: str = "project") -> dict[str, Any]:
    """Classify a node identifier against canonical epistemic nomenclature and role."""
    clean_id, is_know_role = layer_id.strip().lower(), layer_role == "knowledge"
    adaptation = "M1-M2:academic-tutor-guides | M3-M4:professional-scientific-reference"
    for prefix in VALID_KNOWLEDGE_PREFIXES:
        if clean_id.startswith(prefix):
            meta = KNOWLEDGE_DOMAIN_TAXONOMY[prefix]
            slug = clean_id.removeprefix(prefix)
            trunk, gran = (
                _resolve_science_trunk(slug)
                if prefix == "sci-"
                else (meta["knowledge_domain"], "domain-repository")
            )
            return {
                "layer_id": clean_id, "is_knowledge_node": is_know_role, "prefix": prefix,
                "domain_slug": slug, "knowledge_domain": meta["knowledge_domain"],
                "canonical_trunk": trunk, "granularity": gran,
                "default_epistemic_grade": meta["default_epistemic_grade"],
                "default_entity_kind": meta["default_entity_kind"],
                "default_stack_templates": [t for t in meta["default_templates"].split(",") if t],
                "consumer_adaptation": adaptation,
            }  # fmt: skip
    def_tpls = (
        [t for t in KNOWLEDGE_DOMAIN_TAXONOMY["sci-"]["default_templates"].split(",") if t]
        if is_know_role
        else []
    )
    return {
        "layer_id": clean_id, "is_knowledge_node": is_know_role, "prefix": None,
        "domain_slug": clean_id, "knowledge_domain": "custom-knowledge" if is_know_role else None,
        "canonical_trunk": None,
        "granularity": "knowledge-repository" if is_know_role else "standard-layer",
        "default_epistemic_grade": "E2" if is_know_role else "E1",
        "default_entity_kind": "enterprise", "default_stack_templates": def_tpls,
        "consumer_adaptation": adaptation,
    }  # fmt: skip


def resolve_knowledge_mount_endpoints(
    mount_entry: dict[str, Any], repo_dir: Path
) -> dict[str, Any]:
    """Resolve a knowledge mount across local-mcp-clone, private-mirror, and public URLs."""
    name = str(mount_entry.get("name") or mount_entry.get("layer_id") or "").strip()
    m_role = str(mount_entry.get("layer_role") or "knowledge").strip()
    rel_path = str(mount_entry.get("relative_path") or f"layers/{name}").strip()
    local_dir = ensure_contained_path(Path(rel_path), repo_dir)
    has_local_mcp = (local_dir / NODE_MANIFEST_REL_PATH).is_file()
    reg = DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY.get(name, {})
    priv_url = str(mount_entry.get("private_mirror_url") or "").strip()
    pub_url = str(
        mount_entry.get("repository")
        or mount_entry.get("public_url")
        or reg.get("public_url")
        or ""
    ).strip()
    auth_url = str(
        mount_entry.get("canonical_authority_url") or reg.get("canonical_authority_url") or ""
    ).strip()
    raw_st = str(mount_entry.get("stewardship_stage") or reg.get("stewardship_stage") or "").strip()
    stage = (
        raw_st
        if raw_st in VALID_KNOWLEDGE_STEWARDSHIP_STAGES
        else (
            "sovereign-authority"
            if auth_url
            else ("private-incubation" if priv_url else "public-community")
        )
    )
    mode = (
        "local-mcp-clone"
        if has_local_mcp
        else (
            "private-mirror-remote"
            if stage == "private-incubation" and priv_url
            else "public-canonical-remote"
        )
    )
    rem_ep = (
        (priv_url or pub_url or auth_url)
        if stage == "private-incubation"
        else (
            (pub_url or priv_url or auth_url)
            if stage == "public-community"
            else (auth_url or pub_url or priv_url)
        )
    )
    return {
        **classify_knowledge_domain(name, m_role), "relative_path": rel_path,
        "local_mcp_available": has_local_mcp, "resolution_mode": mode, "stewardship_stage": stage,
        "active_endpoint": str(local_dir) if has_local_mcp else rem_ep,
        "private_mirror_url": priv_url or None, "public_url": pub_url or None,
        "canonical_authority_url": auth_url or None,
    }  # fmt: skip
