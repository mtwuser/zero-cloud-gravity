"""Model-Currency policy verification and orthogonal node agent guidance resolver.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

MODEL_CURRENCY_CONTRACT_REV: Final[str] = "zcg-model-currency-v1"
REQUIRED_MANDATE_12_MARKERS: Final[tuple[str, ...]] = (
    "Set-and-Forget",
    "disjoint file ownership",
    "0` worker Git commits",
    "Model-Currency",
)
REQUIRED_AUDIT_CURRENCY_MARKER: Final[str] = "Model-Currency"
CONTINUOUS_CALIBRATION_RULE: Final[str] = (
    "Recalibrate default & worker model tiers whenever upgrading stacks or running /audit "
    "(enforced by zcg lint-arch)."
)
ENTERPRISE_LAYER_ROLES: Final[frozenset[str]] = frozenset(
    {"corporate", "department", "domain-policy", "squad"}
)

_PROFILE_CATALOG: Final[dict[str, dict[str, str]]] = {
    "software-engineering": {
        "profile_id": "software-engineering",
        "profile_label": "Software Engineering & Architecture",
        "recommended_base_model": "Gemini 4 Carbon (High)",
        "velocity_alternative": "Gemini 4 Neon (High)",
        "auto_orchestration_summary": (
            "Inline execution for 1-4 coupled files; automatic Swarm pins Gemini 4 Neon (High) "
            "on disjoint-file authors (0 worker commits) and Gemini 4 Carbon (High) on a "
            "read-only verifier."
        ),
    },
    "academic-tutor": {
        "profile_id": "academic-tutor",
        "profile_label": "Academic Study & Socratic Tutor",
        "recommended_base_model": "Gemini 4 Neon (Medium)",
        "velocity_alternative": "Gemini 4 Carbon (High) for syllabus design & deep proofs",
        "auto_orchestration_summary": (
            "Fast Socratic drills inline; multi-topic study packs fan out to Neon (Medium) "
            "drafters plus a Carbon (High) pedagogical verifier."
        ),
    },
    "knowledge-science": {
        "profile_id": "knowledge-science",
        "profile_label": "Scientific & Statutory Knowledge Corpus",
        "recommended_base_model": "Gemini 4 Carbon (High)",
        "velocity_alternative": "Gemini 4 Neon (Medium) for document structuring",
        "auto_orchestration_summary": (
            "Epistemic E3..E0 & citation checks inline; multi-document corpus audits fan out "
            "to Neon (High) workers plus a Carbon (High) epistemic verifier."
        ),
    },
    "enterprise-governance": {
        "profile_id": "enterprise-governance",
        "profile_label": "Enterprise Operations & Governance",
        "recommended_base_model": "Gemini 4 Carbon (High)",
        "velocity_alternative": "Gemini 4 Neon (Medium) for routine WORK* updates",
        "auto_orchestration_summary": (
            "RBAC and SOP decisions inline; cross-department ledger & policy sweeps fan out "
            "to Neon (Medium) analysts plus a Carbon (High) auditor."
        ),
    },
    "personal-workstation": {
        "profile_id": "personal-workstation",
        "profile_label": "Personal Root 0 Workstation & Daily Flow",
        "recommended_base_model": "Gemini 4 Neon (High)",
        "velocity_alternative": "Gemini 4 Carbon (High) for cross-pillar architecture",
        "auto_orchestration_summary": (
            "Instant /sopen, /sclose & host audits inline; multi-pillar checks fan out "
            "automatically without typing /teamwork."
        ),
    },
}


def resolve_node_agent_guidance(manifest: Mapping[str, Any]) -> dict[str, str]:
    """Classify a node manifest into its orthogonal Set-and-Forget model and swarm profile."""
    raw_identity = manifest.get("entity_identity")
    identity_kind = raw_identity.get("entity_kind") if isinstance(raw_identity, Mapping) else None
    entity_kind = str(identity_kind or manifest.get("entity_kind") or "")
    layer_role = str(manifest.get("layer_role") or "")
    tpls = tuple(str(x) for x in (manifest.get("default_stack_templates") or ()))

    if "software-engineering" in tpls or layer_role == "engine":
        profile_key = "software-engineering"
    elif layer_role == "tutor" or "academic-curriculum" in tpls or "academic-base" in tpls:
        profile_key = "academic-tutor"
    elif layer_role == "knowledge" or "scientific-methodology" in tpls:
        profile_key = "knowledge-science"
    elif (
        entity_kind == "enterprise"
        or layer_role in ENTERPRISE_LAYER_ROLES
        or "corporate-operations" in tpls
    ):
        profile_key = "enterprise-governance"
    else:
        profile_key = "personal-workstation"

    return {
        "contract_rev": MODEL_CURRENCY_CONTRACT_REV,
        **_PROFILE_CATALOG[profile_key],
        "continuous_calibration_rule": CONTINUOUS_CALIBRATION_RULE,
    }


def check_model_currency_policy(root_dir: Path) -> list[tuple[str, int, str, str]]:
    """Verify Mandate #12 and Model-Currency markers in canonical engine rule and audit files."""
    agents_md = root_dir / "antigravity/.gemini/config/AGENTS.md"
    ub_md = root_dir / "templates/human-stack/universal-base/rules/universal-base.md"
    if not (agents_md.is_file() and ub_md.is_file()):
        return []

    violations: list[tuple[str, int, str, str]] = []
    for fpath in (agents_md, ub_md):
        text = fpath.read_text(encoding="utf-8")
        for marker in REQUIRED_MANDATE_12_MARKERS:
            if marker not in text:
                violations.append((str(fpath), 1, marker, "model-currency-policy-drift"))

    audit_sk = root_dir / "antigravity/.gemini/config/skills/audit/SKILL.md"
    if audit_sk.is_file() and REQUIRED_AUDIT_CURRENCY_MARKER not in audit_sk.read_text(
        encoding="utf-8"
    ):
        violations.append(
            (str(audit_sk), 1, REQUIRED_AUDIT_CURRENCY_MARKER, "model-currency-audit-missing")
        )
    return violations
