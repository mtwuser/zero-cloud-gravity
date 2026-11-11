"""Epistemic grade inference, citation receipts, Q1..Q4 obsolescence radar, and L3 claim checks.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from zcg.capsules.constants import (
    CAPSULE_ABSTRACTION_LAYERS,
    CITATION_LIFECYCLE_QUADRANTS,
    CITATION_TELEMETRY_REL_PATH,
    DIAGNOSTICS_RECENT_ALERTS_LIMIT,
    DIAGNOSTICS_RECENT_EVENTS_LIMIT,
    HOT_CITATION_THRESHOLD,
    STALE_POLICY_REVIEW_DAYS,
)
from zcg.capsules.markdown import read_non_empty_lines, slugify_codon
from zcg.core.constants import (
    CAPSULE_DIGEST_HEX_LEN,
    EPISTEMIC_GRADE_LABELS,
    EPISTEMIC_GRADE_RANK,
    VALID_EPISTEMIC_GRADES,
)


def infer_epistemic_grade(rel_file: str, section_title: str, section_body: str) -> tuple[str, str]:
    """Classify a rule or documentation section into universal epistemic grades E3..E0."""
    combined = f"{section_title}\n{section_body}"
    for explicit in VALID_EPISTEMIC_GRADES:
        if f"[{explicit}" in combined:
            return explicit, EPISTEMIC_GRADE_LABELS[explicit]
    rel_clean, title_low = rel_file.strip().lstrip("/"), section_title.lower()
    if (
        rel_clean.startswith((".agents/proposals/", "roadmaps/"))
        or rel_clean in ("BACKLOG.md", "WORKROAD.md", "WORKTASK.md")
        or any(k in title_low for k in ("proposal", "hypothesis", "draft"))
    ):
        return "E0", EPISTEMIC_GRADE_LABELS["E0"]
    if (
        rel_clean.endswith(("AGENTS.md", "SECURITY.md", "universal-base.md", "science-base.md"))
        or "**Mandate:**" in section_body
        or any(
            k in title_low for k in ("invariant", "mandate", "security", "axiom", "law", "statute")
        )
    ):
        return "E3", EPISTEMIC_GRADE_LABELS["E3"]
    if (
        rel_clean.startswith(("docs/architecture/", "docs/reference/", "corporate/", "surfaces/"))
        or "/rules/" in rel_clean
        or "Specification:" in section_body
        or any(
            k in title_low
            for k in ("contract", "specification", "schema", "1:1:1", "protocol", "standard")
        )
    ):
        return "E2", EPISTEMIC_GRADE_LABELS["E2"]
    return "E1", EPISTEMIC_GRADE_LABELS["E1"]


def build_citation_receipt(
    layer_id: str, rel_file: str, section_heading: str, digest_hex: str, epistemic_grade: str
) -> str:
    """Build a canonical citation receipt (<layer>::<file>#<slug>@<digest>:<grade>)."""
    clean_rel = rel_file.strip().lstrip("/")
    return (
        f"{layer_id}::{clean_rel}#{slugify_codon(section_heading)}@{digest_hex}:{epistemic_grade}"
    )


def evaluate_citation_telemetry_lifecycle(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify sections across the 4 Age x Empirical Usage quadrants while preserving E3..E0."""
    classified: list[dict[str, Any]] = []
    counts = dict.fromkeys(CITATION_LIFECYCLE_QUADRANTS, 0)
    for item in sections:
        grade = str(item.get("epistemic_grade") or "E1").upper()
        hits, age = int(item.get("citation_count", 0)), int(item.get("age_days", 0))
        has_fric = (
            int(item.get("stale_citation_hits", 0)) > 0
            or int(item.get("proposal_friction_count", 0)) > 0
        )
        cold_q = (
            "Q4_NORMATIVE_OBSOLESCENCE" if age > STALE_POLICY_REVIEW_DAYS else "Q3_EMERGING_NICHE"
        )
        quadrant = (
            "Q2_HIGH_FRICTION"
            if has_fric
            else ("Q1_HOT_CORE" if hits >= HOT_CITATION_THRESHOLD else cold_q)
        )
        counts[quadrant] += 1
        classified.append(
            {
                **item,
                "epistemic_grade": grade,
                "quadrant": quadrant,
                "recommended_action": CITATION_LIFECYCLE_QUADRANTS[quadrant],
            }
        )
    dynamic_index = sorted(
        classified,
        key=lambda s: (
            -EPISTEMIC_GRADE_RANK.get(str(s["epistemic_grade"]), 1),
            -int(s.get("citation_count", 0)),
            int(s.get("age_days", 0)),
        ),
    )
    return {
        "epistemic_override_allowed": False,
        "quadrant_counts": counts,
        "obsolescence_candidates": [
            s for s in classified if s["quadrant"] == "Q4_NORMATIVE_OBSOLESCENCE"
        ],
        "high_friction_targets": [s for s in classified if s["quadrant"] == "Q2_HIGH_FRICTION"],
        "dynamic_hot_index": dynamic_index,
    }


def record_citation_telemetry_event(
    repo_dir: Path,
    citation_receipt: str,
    *,
    is_stale_hit: bool = False,
    is_proposal_friction: bool = False,
    age_days: int = 0,
    count_citation: bool = True,
) -> dict[str, Any]:
    """Persist a citation usage, drift, or friction event in citation_stats.json."""
    stats_path = Path(repo_dir) / CITATION_TELEMETRY_REL_PATH
    raw = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.is_file() else {}
    sec_map: dict[str, dict[str, Any]] = dict(raw.get("sections") or {})
    sec_key = citation_receipt.split("@", 1)[0].strip()
    grade = citation_receipt.rsplit(":", 1)[1].strip() if ":" in citation_receipt else "E1"
    cur = dict(sec_map.get(sec_key) or {})
    c_inc = 1 if (count_citation and not is_stale_hit) else 0
    s_inc = 1 if is_stale_hit else 0
    f_inc = 1 if is_proposal_friction else 0
    entry = {
        "section_key": sec_key,
        "citation_receipt": citation_receipt,
        "epistemic_grade": grade.upper(),
        "citation_count": int(cur.get("citation_count", 0)) + c_inc,
        "stale_citation_hits": int(cur.get("stale_citation_hits", 0)) + s_inc,
        "proposal_friction_count": int(cur.get("proposal_friction_count", 0)) + f_inc,
        "age_days": max(int(cur.get("age_days", 0)), int(age_days)),
    }
    sec_map[sec_key] = entry
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps({"sections": sec_map}, indent=2) + "\n", encoding="utf-8")
    return entry


def load_citation_telemetry_radar(repo_dir: Path) -> dict[str, Any]:
    """Load persisted .agents/telemetry/citation_stats.json and evaluate the Q1..Q4 radar."""
    stats_path = Path(repo_dir) / CITATION_TELEMETRY_REL_PATH
    raw = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.is_file() else {}
    sec_map = raw.get("sections") if isinstance(raw, dict) else None
    sections = list(sec_map.values()) if isinstance(sec_map, dict) else []
    return {
        "telemetry_file": CITATION_TELEMETRY_REL_PATH,
        "tracked_sections_count": len(sections),
        **evaluate_citation_telemetry_lifecycle(sections),
    }


def verify_epistemic_context_claims(claims: list[dict[str, Any]], repo_dir: Path) -> dict[str, Any]:
    """Verify primary-source SHA-256 grounding, E3>E2>E1>E0 monotonicity, and cut-point bounds."""
    root_res = repo_dir.resolve()
    violations: list[dict[str, Any]] = []
    for idx, claim in enumerate(claims):
        c_id = str(claim.get("claim_id") or f"claim-{idx + 1}")
        grade = str(claim.get("epistemic_grade") or "E1").upper()
        over_grade = str(claim.get("overrides_grade") or "").upper()
        if (
            over_grade in EPISTEMIC_GRADE_RANK
            and EPISTEMIC_GRADE_RANK.get(grade, 1) < EPISTEMIC_GRADE_RANK[over_grade]
        ):
            violations.append(
                {
                    "claim_id": c_id,
                    "code": "EPISTEMIC_PRECEDENCE_VIOLATION",
                    "reason": f"Grade {grade} cannot override higher grade {over_grade}",
                }
            )
        for tgt in claim.get("l3_targets") or []:
            rel_p = str(tgt.get("path") or "").strip().lstrip("/")
            exp_sha = str(tgt.get("sha256_prefix") or "").strip()
            cand = (root_res / rel_p).resolve() if rel_p else None
            live_sha = (
                hashlib.sha256(cand.read_bytes()).hexdigest()[:CAPSULE_DIGEST_HEX_LEN]
                if cand and cand.is_file() and cand.is_relative_to(root_res)
                else ""
            )
            if not live_sha or (exp_sha and not live_sha.startswith(exp_sha)):
                violations.append(
                    {
                        "claim_id": c_id,
                        "code": "PRIMARY_SOURCE_HASH_MISMATCH",
                        "reason": f"L3 substrate {rel_p!r} missing or SHA-256 drifted",
                    }
                )
        if "cut_point" in claim and "observed_value" in claim:
            val, thr = float(claim["observed_value"]), float(claim["cut_point"])
            if val > thr:
                violations.append(
                    {
                        "claim_id": c_id,
                        "code": "CUT_POINT_BOUNDARY_VIOLATION",
                        "reason": f"Observed {val} exceeds L3 cut-point threshold {thr}",
                    }
                )
        cited = str(claim.get("citation_receipt") or "").strip()
        official_dig = str(claim.get("official_digest") or "").strip()
        is_stale = False
        if cited and official_dig and "@" in cited:
            cited_dig = cited.rsplit("@", 1)[1].split(":", 1)[0].strip()
            if not official_dig.startswith(cited_dig) and not cited_dig.startswith(official_dig):
                is_stale = True
                violations.append(
                    {
                        "claim_id": c_id,
                        "code": "CITATION_DRIFT_DETECTED",
                        "reason": (
                            f"Cited receipt digest {cited_dig!r} drifted from {official_dig!r}"
                        ),
                    }
                )
        if cited:
            record_citation_telemetry_event(
                root_res,
                cited,
                is_stale_hit=is_stale,
                is_proposal_friction=bool(claim.get("proposal_friction")),
                age_days=int(claim.get("age_days", 0)),
                count_citation=bool(claim.get("count_citation", True)),
            )
    return {
        "verified": not violations,
        "error_code": violations[0]["code"] if violations else None,
        "checked_claims_count": len(claims),
        "violations": violations,
        "abstraction_layers": dict(CAPSULE_ABSTRACTION_LAYERS),
        "citation_lifecycle_radar": load_citation_telemetry_radar(root_res),
    }


def summarize_mcp_diagnostics(log_dir: Path | None, repo_dir: Path) -> dict[str, Any]:
    """Aggregate runtime MCP events, alerts, and rcap1 compaction savings from JSONL logs."""
    ldir = log_dir or (repo_dir / "logs")
    events = [json.loads(ln) for ln in read_non_empty_lines(ldir / "mcp_events.jsonl")]
    alerts = [json.loads(ln) for ln in read_non_empty_lines(ldir / "mcp_alerts.jsonl")]
    by_code: dict[str, int] = {}
    for al in alerts:
        c = str(al.get("code", "UNKNOWN"))
        by_code[c] = by_code.get(c, 0) + 1
    q_res, u_lvl, u_tier, hops, saved = dict[str, int](), dict[str, int](), dict[str, int](), 0, 0
    for ev in events:
        if isinstance(rl := ev.get("resolution"), str):
            q_res[rl] = q_res.get(rl, 0) + 1
            saved += int(ev.get("tokens_saved", 0))
        if isinstance(ul := ev.get("unfolded_level"), str):
            u_lvl[ul] = u_lvl.get(ul, 0) + 1
            tr = str(ev.get("agent_tier", "inherit"))
            u_tier[tr] = u_tier.get(tr, 0) + 1
            hops += int(ev.get("decrypted_hops", 0))
    err_cnt = sum(1 for e in events if e.get("status") == "error")
    max_b = max((int(e.get("response_bytes", 0)) for e in events), default=0)
    cap_al = {k: v for k, v in by_code.items() if k.startswith("CAPSULE_")}
    return {
        "logging_enabled": log_dir is not None,
        "log_dir": str(log_dir) if log_dir is not None else None,
        "events_summary": {
            "total_events": len(events),
            "error_events": err_cnt,
            "max_response_bytes": max_b,
            "recent_events": events[-DIAGNOSTICS_RECENT_ALERTS_LIMIT:],
        },
        "alerts_summary": {
            "total_alerts": len(alerts),
            "by_code": by_code,
            "recent_alerts": alerts[-DIAGNOSTICS_RECENT_EVENTS_LIMIT:],
        },
        "resonance_compaction_summary": {
            "queries_by_resolution": q_res,
            "unfolds_by_target_level": u_lvl,
            "unfolds_by_agent_tier": u_tier,
            "total_decrypted_hops": hops,
            "cumulative_tokens_saved": saved,
            "capsule_alerts_by_code": cap_al,
        },
    }
