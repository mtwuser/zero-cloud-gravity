"""Vendor-neutral isolated tool-stack runtime (.zcg/tools/<id>/) and calibrated decisions.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import TOOL_RUNTIME_REL_DIR
from zcg.core.domain import is_kebab_id
from zcg.core.manifests import ensure_contained_path, load_node_manifest
from zcg.governance.policy.egress import resolve_effective_egress_policy
from zcg.governance.runtime.skill_auditor import audit_skills_sovereign_profile
from zcg.governance.runtime.tool_catalog import (
    DEFAULT_ISOLATED_TOOL_CATALOG,
    IsolatedToolDescriptor,
)
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_governance_posture

TOOL_RUNTIME_CONTRACT_REV: Final[str] = "zcg-tool-runtime-v1"
MAX_GEMINI_DECISIONS_BATCH: Final[int] = 1000
RUBRIC_SCALE_MAX: Final[float] = 4.0
RUBRIC_PASS_THRESHOLD: Final[float] = 0.70
DEFAULT_DECISIONS_MODEL: Final[str] = "gemini-decision-1"
DEFAULT_OFFLINE_LITERT_MODEL: Final[str] = "gemma-4-26b-a4b-it"

VALID_DECISION_TASKS: Final[tuple[str, ...]] = ("yes_no", "choice", "rubric")
VALID_DECISION_USE_CASES: Final[tuple[str, ...]] = (
    "env-gate",
    "model-routing",
    "epistemic-q-score",
    "disclosure-sensitivity",
    "handoff-axis",
)

__all__ = (
    "DEFAULT_DECISIONS_MODEL",
    "DEFAULT_OFFLINE_LITERT_MODEL",
    "MAX_GEMINI_DECISIONS_BATCH",
    "RUBRIC_PASS_THRESHOLD",
    "RUBRIC_SCALE_MAX",
    "TOOL_RUNTIME_CONTRACT_REV",
    "VALID_DECISION_TASKS",
    "VALID_DECISION_USE_CASES",
    "DecisionEvaluationRequest",
    "audit_skills_sovereign_profile",
    "build_bwrap_readonly_command",
    "deprovision_isolated_tool_manifest",
    "evaluate_calibrated_decisions",
    "provision_isolated_tool_manifest",
    "resolve_tool_runtime_dir",
    "run_isolated_tool_inspection",
)


@dataclass(frozen=True, slots=True)
class DecisionEvaluationRequest:
    """Single calibrated zero-output-token evaluation item for Gemini Decisions or LiteRT."""

    item_id: str
    task_kind: str
    use_case: str
    prompt: str
    choices: tuple[str, ...] = ()
    prior_score: float = 0.5


def resolve_tool_runtime_dir(workspace_dir: Path, tool_id: str) -> Path:
    """Resolve and validate path containment for <workspace_dir>/.zcg/tools/<tool_id>."""
    clean_id = tool_id.strip()
    if not is_kebab_id(clean_id):
        raise ValueError(f"Invalid tool_id {tool_id!r}: expected kebab-case slug")
    return ensure_contained_path(Path(TOOL_RUNTIME_REL_DIR) / clean_id, workspace_dir.resolve())


def build_bwrap_readonly_command(
    workspace_dir: Path,
    tool_id: str,
    inner_argv: Sequence[str],
    *,
    allow_network: bool = False,
) -> list[str]:
    """Build deterministic Linux bubblewrap argv mounting workspace read-only."""
    cleaned_inner = [str(arg).strip() for arg in inner_argv if str(arg).strip()]
    if not cleaned_inner:
        raise ValueError("inner_argv must contain at least one executable token")
    ws = workspace_dir.resolve()
    tool_dir = resolve_tool_runtime_dir(ws, tool_id)
    net_flags = ("--share-net",) if allow_network else ()
    return [
        "bwrap", "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
        "--proc", "/proc", "--dev", "/dev", "--ro-bind", str(ws), "/workspace",
        "--bind", str(tool_dir), "/tool-state", "--unshare-all", *net_flags,
        "--die-with-parent", "--", *cleaned_inner,
    ]  # fmt: skip


def provision_isolated_tool_manifest(
    workspace_dir: Path,
    tool_id: str,
    *,
    parent_dir: Path | None = None,
    active_env: str = "dev",
    offline_override: bool = False,
    dry_run: bool = False,
    catalog: Mapping[str, IsolatedToolDescriptor] | None = None,
) -> dict[str, Any]:
    """Materialize isolated runtime configuration under .zcg/tools/<tool_id>/tool-runtime.json."""
    clean_id = tool_id.strip()
    eff_catalog = DEFAULT_ISOLATED_TOOL_CATALOG if catalog is None else catalog
    spec = eff_catalog.get(clean_id)
    if spec is None:
        raise ValueError(f"Unknown isolated tool_id {tool_id!r}")
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    posture = resolve_governance_posture(ws, manifest, parent_dir=eff_parent)
    egress = resolve_effective_egress_policy(ws, manifest=manifest, parent_dir=eff_parent)
    airgapped = (
        offline_override
        or posture.get("personal_pillar") == "wallet"
        or (egress.egress_restricted and not egress.allowed_domains)
    )
    dec_backend = (
        ("litert-gemma-4" if airgapped else "gemini-decisions-api")
        if clean_id == "gemini-decisions"
        else None
    )
    t_dir = resolve_tool_runtime_dir(ws, clean_id)
    doc: dict[str, Any] = {
        "schema_version": TOOL_RUNTIME_CONTRACT_REV,
        "tool_id": clean_id,
        "display_name": spec.display_name,
        "upstream_engine": spec.upstream_engine,
        "environment": active_env.strip().lower() or "dev",
        "runtime_dir": str(t_dir.relative_to(ws)),
        "sandbox_driver": spec.sandbox_driver,
        "network_allowed": bool(spec.requires_network and not airgapped),
        "decision_backend": dec_backend,
        "mirror_env": egress.artifact_mirrors.to_env_vars(),
    }
    if not dry_run:
        t_dir.mkdir(parents=True, exist_ok=True)
        (t_dir / "tool-runtime.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return doc


def deprovision_isolated_tool_manifest(
    workspace_dir: Path,
    tool_id: str,
    *,
    dry_run: bool = False,
    catalog: Mapping[str, IsolatedToolDescriptor] | None = None,
) -> dict[str, Any]:
    """Remove isolated runtime state under .zcg/tools/<tool_id>/ cleanly."""
    clean_id = tool_id.strip()
    eff_catalog = DEFAULT_ISOLATED_TOOL_CATALOG if catalog is None else catalog
    if clean_id not in eff_catalog:
        raise ValueError(f"Unknown isolated tool_id {tool_id!r}")
    ws = workspace_dir.resolve()
    t_dir = resolve_tool_runtime_dir(ws, clean_id)
    rt_f = t_dir / "tool-runtime.json"
    existed = rt_f.is_file()
    if not dry_run and existed:
        rt_f.unlink(missing_ok=True)
        if not any(t_dir.iterdir()):
            t_dir.rmdir()
    return {"tool_id": clean_id, "deprovisioned": existed, "dry_run": dry_run}


def run_isolated_tool_inspection(
    workspace_dir: Path,
    tool_id: str,
    *,
    parent_dir: Path | None = None,
    catalog: Mapping[str, IsolatedToolDescriptor] | None = None,
) -> dict[str, Any]:
    """Execute a live read-only diagnostic check for an isolated tool inside <workspace_dir>."""
    clean_id = tool_id.strip()
    eff_catalog = DEFAULT_ISOLATED_TOOL_CATALOG if catalog is None else catalog
    spec = eff_catalog.get(clean_id)
    if spec is None:
        raise ValueError(f"Unknown isolated tool_id {tool_id!r}")
    ws = workspace_dir.resolve()
    if clean_id == "zcg-skill-auditor":
        rep = audit_skills_sovereign_profile(ws, parent_dir=parent_dir)
        return {
            "tool_id": clean_id,
            "headline": f"Skill Trust: {rep['trust_score']}/100",
            "details": [
                f"Scanned skills: {rep['scanned_skill_count']} · Findings: {rep['finding_count']}",
                f"CLI: {spec.cli_command}",
            ],
        }
    if clean_id == "secops-guardian":
        manifest = load_node_manifest(ws)
        eff_p = resolve_default_parent_dir(ws, parent_dir)
        pos = resolve_governance_posture(ws, manifest, parent_dir=eff_p)
        eg = resolve_effective_egress_policy(ws, manifest=manifest, parent_dir=eff_p)
        argv = " ".join(build_bwrap_readonly_command(ws, clean_id, ["osv-scanner", "/workspace"]))
        head = f"Posture: {pos['governance_posture']} · Ring: {pos['default_surface_ring']}"
        return {
            "tool_id": clean_id,
            "headline": head,
            "details": [f"Egress restricted: {eg.egress_restricted}", f"Sandbox: {argv}"],
        }
    if clean_id == "gemini-decisions":
        sample = DecisionEvaluationRequest(
            "gate-check", "yes_no", "env-gate", "Are workspace gates green?", prior_score=0.92
        )
        ev = evaluate_calibrated_decisions([sample], offline_mode=True)
        r0 = ev["results"][0]
        prob_v = r0["calibrated_probability"]
        head_d = f"Offline LiteRT ({ev['model']}): {r0['decision']} (p={prob_v})"
        return {
            "tool_id": clean_id,
            "headline": head_d,
            "details": [
                "Output tokens: 0 (calibrated probability gate)",
                f"API: {spec.cli_command}",
            ],
        }
    t_dir = resolve_tool_runtime_dir(ws, clean_id)
    rt_ok = (t_dir / "tool-runtime.json").is_file()
    return {
        "tool_id": clean_id,
        "headline": f"{spec.display_name} ({'Active' if rt_ok else 'Inactive'})",
        "details": [
            f"Driver: {spec.sandbox_driver} · Engine: {spec.upstream_engine}",
            f"CLI: {spec.cli_command}",
        ],
    }


def _score_local_litert_item(req: DecisionEvaluationRequest) -> dict[str, Any]:
    prob = min(1.0, max(0.0, float(req.prior_score)))
    conf = round(abs(prob - 0.5) * 2.0, 4)
    base = {
        "item_id": req.item_id,
        "task_kind": req.task_kind,
        "use_case": req.use_case,
        "confidence": conf,
    }
    if req.task_kind == "yes_no":
        return {
            **base,
            "decision": "yes" if prob >= 0.5 else "no",
            "calibrated_probability": round(prob, 4),
        }
    if req.task_kind == "choice":
        n_c = len(req.choices)
        sel_idx = min(n_c - 1, int(prob * n_c))
        rem = round((1.0 - prob) / (n_c - 1), 4)
        dist = {
            ch: (round(prob, 4) if idx == sel_idx else rem) for idx, ch in enumerate(req.choices)
        }
        return {**base, "selected_choice": req.choices[sel_idx], "distribution": dist}
    return {
        **base,
        "rubric_score": round(prob * RUBRIC_SCALE_MAX, 2),
        "passed": prob >= RUBRIC_PASS_THRESHOLD,
    }


def evaluate_calibrated_decisions(
    requests: Sequence[DecisionEvaluationRequest],
    *,
    offline_mode: bool = False,
    transport_fn: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate 1..1,000 calibrated zero-output-token decisions via Gemini Decisions or LiteRT."""
    if not requests or len(requests) > MAX_GEMINI_DECISIONS_BATCH:
        raise ValueError(
            f"DECISIONS_BATCH_LIMIT_EXCEEDED: expected 1..{MAX_GEMINI_DECISIONS_BATCH} items"
        )
    for req in requests:
        if req.task_kind not in VALID_DECISION_TASKS:
            raise ValueError(f"Unsupported decision task_kind {req.task_kind!r}")
        if req.use_case not in VALID_DECISION_USE_CASES:
            raise ValueError(f"Unsupported decision use_case {req.use_case!r}")
        if req.task_kind == "choice" and len(req.choices) < 2:
            raise ValueError(f"Choice decision {req.item_id!r} requires at least 2 choices")

    if not offline_mode and transport_fn is not None:
        items = [
            {
                "item_id": r.item_id,
                "task_kind": r.task_kind,
                "use_case": r.use_case,
                "prompt": r.prompt,
                "choices": list(r.choices),
            }
            for r in requests
        ]
        remote = dict(transport_fn({"max_output_tokens": 0, "items": items}))
        return {
            "backend": "gemini-decisions-api",
            "model": str(remote.get("model") or DEFAULT_DECISIONS_MODEL),
            "output_tokens": 0,
            "item_count": len(requests),
            "results": list(remote.get("results") or []),
        }

    return {
        "backend": "litert-gemma-4",
        "model": DEFAULT_OFFLINE_LITERT_MODEL,
        "output_tokens": 0,
        "item_count": len(requests),
        "results": [_score_local_litert_item(r) for r in requests],
    }
