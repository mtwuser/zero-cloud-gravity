"""Sovereign 3-tier skill auditor (SARIF 2.1.0 security, 1-Verb Jaccard, and A/B Skill Lift).

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from zcg.core.domain import is_kebab_id
from zcg.core.manifests import parse_skill_frontmatter
from zcg.governance.policy.capabilities import lint_skills_security

SKILL_AUDITOR_CONTRACT_REV: Final[str] = "zcg-skill-auditor-v1"
SARIF_SCHEMA_URL: Final[str] = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION: Final[str] = "2.1.0"
SKILL_AUDITOR_DRIVER_NAME: Final[str] = "zcg-skill-auditor"
SKILL_AUDITOR_INFO_URI: Final[str] = (
    "https://zerocloudgravity.org/docs/architecture/03_governance_and_work_ledger"
)
MAX_TRUST_SCORE: Final[int] = 100
MIN_TRUST_SCORE: Final[int] = 0
JACCARD_OVERLAP_WARN_THRESHOLD: Final[float] = 0.65
MIN_TOKEN_LEN_FOR_JACCARD: Final[int] = 3

SEVERITY_TRUST_PENALTIES: Final[dict[str, int]] = {
    "critical": 40,
    "high": 25,
    "medium": 10,
    "low": 5,
}
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "use",
        "when",
        "this",
        "skill",
        "from",
        "into",
        "that",
        "are",
        "all",
        "via",
        "across",
    }
)


@dataclass(frozen=True, slots=True)
class SkillLiftBenchmarkCase:
    """Deterministic sandboxed A/B evaluation slice measuring net skill pass-rate lift."""

    skill_name: str
    case_id: str
    baseline_pass_rate: float
    with_skill_pass_rate: float
    baseline_tokens: int = 0
    with_skill_tokens: int = 0


def _tokenize_description(text: str) -> frozenset[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return frozenset(
        tok
        for tok in cleaned.split()
        if len(tok) >= MIN_TOKEN_LEN_FOR_JACCARD and tok not in _STOPWORDS
    )


def _discover_node_skill_files(scan_root: Path, *, explicit_target: bool) -> list[Path]:
    if explicit_target:
        return sorted(scan_root.rglob("SKILL.md"))
    t_dir = scan_root / "templates"
    tpl_skills = t_dir.rglob("SKILL.md") if t_dir.is_dir() else ()
    return sorted(
        {
            *scan_root.glob(".agents/skills/*/SKILL.md"),
            *scan_root.glob("antigravity/.gemini/config/skills/*/SKILL.md"),
            *tpl_skills,
        }
    )


def audit_skill_taxonomy_and_overlap(
    workspace_dir: Path,
    *,
    target_dir: Path | None = None,
    jaccard_threshold: float = JACCARD_OVERLAP_WARN_THRESHOLD,
) -> dict[str, Any]:
    """Evaluate Tier 2 1-Skill-1-Verb frontmatter hygiene and pairwise Jaccard overlap."""
    ws = workspace_dir.resolve()
    scan_root = target_dir.resolve() if target_dir is not None else ws
    skill_files = _discover_node_skill_files(scan_root, explicit_target=target_dir is not None)
    findings: list[dict[str, str]] = []
    unique_by_name: dict[str, tuple[str, frozenset[str]]] = {}

    for sk_file in skill_files:
        fm = parse_skill_frontmatter(sk_file, scan_root)
        name = str(fm["name"]).strip()
        desc = str(fm["description"]).strip()
        rel = Path(str(fm["path"])).as_posix()
        if not desc:
            findings.append(
                {
                    "rule_id": "SKILL_MISSING_DESCRIPTION",
                    "severity": "medium",
                    "taxonomy": "ZCG-TAXONOMY",
                    "file": rel,
                    "message": f"Skill {name!r} is missing a YAML frontmatter description.",
                }
            )
        if not is_kebab_id(name) or name != sk_file.parent.name:
            findings.append(
                {
                    "rule_id": "SKILL_ID_MISMATCH",
                    "severity": "medium",
                    "taxonomy": "ZCG-TAXONOMY",
                    "file": rel,
                    "message": (
                        f"Skill frontmatter name {name!r} must be kebab-case matching "
                        f"folder {sk_file.parent.name!r}."
                    ),
                }
            )
        if name not in unique_by_name:
            unique_by_name[name] = (rel, _tokenize_description(desc))

    names = sorted(unique_by_name)
    overlap_pairs: list[dict[str, Any]] = []
    for idx, name_a in enumerate(names):
        toks_a = unique_by_name[name_a][1]
        for name_b in names[idx + 1 :]:
            toks_b = unique_by_name[name_b][1]
            union_n = len(toks_a | toks_b)
            sim = round(len(toks_a & toks_b) / union_n, 4) if union_n else 0.0
            if sim >= jaccard_threshold:
                overlap_pairs.append({"skill_a": name_a, "skill_b": name_b, "jaccard": sim})
                findings.append(
                    {
                        "rule_id": "SKILL_TAXONOMY_JACCARD_OVERLAP",
                        "severity": "low",
                        "taxonomy": "ZCG-TAXONOMY",
                        "file": unique_by_name[name_b][0],
                        "message": (
                            f"Skills {name_a!r} and {name_b!r} overlap "
                            f"(Jaccard={sim:.2f} >= {jaccard_threshold:.2f})."
                        ),
                    }
                )
    return {
        "unique_skill_count": len(unique_by_name),
        "overlap_pairs": overlap_pairs,
        "findings": findings,
    }


def evaluate_skill_lift_cases(cases: Sequence[SkillLiftBenchmarkCase]) -> dict[str, Any]:
    """Evaluate Tier 3 sandboxed A/B Skill Lift benchmark slices and flag regressions."""
    evaluated: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    lifts: list[float] = []
    for case in cases:
        if (
            not (0.0 <= case.baseline_pass_rate <= 1.0)
            or not (0.0 <= case.with_skill_pass_rate <= 1.0)
            or case.baseline_tokens < 0
            or case.with_skill_tokens < 0
        ):
            raise ValueError(
                "INVALID_SKILL_LIFT_BOUNDS: pass rates must be in 0.0..1.0 and tokens >= 0"
            )
        net_lift = round(case.with_skill_pass_rate - case.baseline_pass_rate, 4)
        token_delta = case.with_skill_tokens - case.baseline_tokens
        lifts.append(net_lift)
        evaluated.append(
            {
                "skill_name": case.skill_name,
                "case_id": case.case_id,
                "net_lift": net_lift,
                "token_delta": token_delta,
                "regressed": net_lift < 0.0,
            }
        )
        if net_lift < 0.0:
            findings.append(
                {
                    "rule_id": "SKILL_LIFT_REGRESSION",
                    "severity": "medium",
                    "taxonomy": "ZCG-SKILL-LIFT",
                    "file": f".agents/skills/{case.skill_name}/SKILL.md",
                    "message": (
                        f"Skill {case.skill_name!r} regressed on {case.case_id!r} "
                        f"(net_lift={net_lift:+.2f})."
                    ),
                }
            )
    mean_lift = round(sum(lifts) / len(lifts), 4) if lifts else 0.0
    return {
        "evaluated_case_count": len(cases),
        "mean_net_lift": mean_lift,
        "cases": evaluated,
        "findings": findings,
    }


def audit_skills_sovereign_profile(
    workspace_dir: Path,
    *,
    target_dir: Path | None = None,
    parent_dir: Path | None = None,
    external_findings: Sequence[Mapping[str, Any]] = (),
    lift_cases: Sequence[SkillLiftBenchmarkCase] = (),
    jaccard_threshold: float = JACCARD_OVERLAP_WARN_THRESHOLD,
) -> dict[str, Any]:
    """Compute a 0..100 sovereign skill trust score and SARIF 2.1.0 report across 3 tiers."""
    ws = workspace_dir.resolve()
    base_scan = lint_skills_security(ws, target_dir=target_dir, parent_dir=parent_dir)
    tier1_findings: list[dict[str, str]] = [
        {
            "rule_id": str(f.get("rule") or "SKILL_SECURITY_VIOLATION"),
            "severity": "high",
            "taxonomy": "ZCG-STATIC",
            "file": str(f.get("file") or "SKILL.md"),
            "message": str(f.get("message") or "Static skill security violation."),
        }
        for f in base_scan["violations"]
    ]
    for ext in external_findings:
        sev = str(ext.get("severity") or "medium").strip().lower()
        tier1_findings.append(
            {
                "rule_id": str(ext.get("rule_id") or "ZCG-AUDIT-RULE"),
                "severity": sev if sev in SEVERITY_TRUST_PENALTIES else "medium",
                "taxonomy": str(ext.get("taxonomy") or "OWASP-LLM"),
                "file": str(ext.get("file") or "SKILL.md"),
                "message": str(ext.get("message") or "External sovereign skill audit finding."),
            }
        )
    tier2 = audit_skill_taxonomy_and_overlap(
        ws, target_dir=target_dir, jaccard_threshold=jaccard_threshold
    )
    tier3 = evaluate_skill_lift_cases(lift_cases)
    merged = [*tier1_findings, *tier2["findings"], *tier3["findings"]]
    penalty = sum(SEVERITY_TRUST_PENALTIES[item["severity"]] for item in merged)
    trust_score = max(MIN_TRUST_SCORE, MAX_TRUST_SCORE - penalty)
    sarif_results = [
        {
            "ruleId": item["rule_id"],
            "level": "error" if item["severity"] in ("critical", "high") else "warning",
            "message": {"text": f"[{item['taxonomy']}] {item['message']}"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": item["file"]}}}],
        }
        for item in merged
    ]
    driver = {"name": SKILL_AUDITOR_DRIVER_NAME, "informationUri": SKILL_AUDITOR_INFO_URI}
    return {
        "contract_rev": SKILL_AUDITOR_CONTRACT_REV,
        "passed": len(merged) == 0,
        "trust_score": trust_score,
        "finding_count": len(merged),
        "scanned_skill_count": base_scan["scanned_skill_count"],
        "tiers": {
            "tier1_security_finding_count": len(tier1_findings),
            "tier2_unique_skill_count": tier2["unique_skill_count"],
            "tier2_overlap_pairs": tier2["overlap_pairs"],
            "tier3_evaluated_case_count": tier3["evaluated_case_count"],
            "tier3_mean_net_lift": tier3["mean_net_lift"],
        },
        "sarif": {
            "$schema": SARIF_SCHEMA_URL,
            "version": SARIF_VERSION,
            "runs": [{"tool": {"driver": driver}, "results": sarif_results}],
        },
    }
