"""Golden-Image overlay boot quarantine and objective 0..100 Local Security Posture Meter.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from zcg.cockpit.ops.plugin_sdk import load_plugin_routers
from zcg.core.manifests import load_node_manifest
from zcg.governance.policy.capabilities import lint_skills_security
from zcg.governance.policy.egress import resolve_effective_egress_policy
from zcg.topology.exposure import classify_exposure_posture
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_governance_posture
from zcg.web.http.factory import WebAppState
from zcg.web.http.router import APIRouter
from zcg.web.ui.template_ast import compile_template_source

POSTURE_CONTRACT_REV: Final[str] = "zcg-security-posture-v1"
POINTS_PER_CHECK: Final[int] = 20
HARDENED_MIN_SCORE: Final[int] = 90
GUARDED_MIN_SCORE: Final[int] = 70

_RECOMMENDATION_MAP: Final[dict[str, str]] = {
    "gitignore_runtime_hygiene": "Add '.zcg/' to .gitignore so SQLite WAL state stays out of Git.",
    "skill_supply_chain_trust": "Resolve zcg lint-skills security violations in SKILL.md or hooks.",
    "egress_and_airgap_confinement": (
        "Declare network_egress_policy.allowed_domains on non-personal intranet/public nodes."
    ),
    "surface_ring_governance": "Declare explicit surface_access ring policy on public R0 nodes.",
    "overlay_integrity": (
        "Fix world-writable permissions or malformed HTML/router overlays under surfaces/web/."
    ),
}


def filter_safe_overlay_template_dirs(
    workspace_dir: Path, template_dirs: tuple[Path, ...]
) -> tuple[tuple[Path, ...], dict[str, Any]]:
    """Quarantine <ws>/surfaces/web/templates if any overlay HTML fails AST compilation."""
    overlay_tpl_dir = (workspace_dir.resolve() / "surfaces/web/templates").resolve()
    if overlay_tpl_dir not in template_dirs:
        return template_dirs, {"status": "CLEAN", "quarantined": False, "reason": ""}
    try:
        for html_file in sorted(overlay_tpl_dir.rglob("*.html")):
            compile_template_source(html_file.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        safe_dirs = tuple(d for d in template_dirs if d != overlay_tpl_dir)
        return (
            safe_dirs,
            {
                "status": "OVERLAY_BOOT_QUARANTINED",
                "quarantined": True,
                "reason": f"{type(exc).__name__}: {exc}",
            },
        )
    return template_dirs, {"status": "CLEAN", "quarantined": False, "reason": ""}


def load_overlay_routers_with_quarantine(
    workspace_dir: Path, *, state: WebAppState
) -> tuple[tuple[APIRouter, ...], dict[str, Any]]:
    """Load mutable <ws>/surfaces/web/routers/*.py, quarantining broken overlays on boot."""
    ws = workspace_dir.resolve()
    try:
        routers = load_plugin_routers(ws, ws / "surfaces/web", state=state)
    except (SyntaxError, ImportError, AttributeError, TypeError, ValueError, OSError) as exc:
        return (
            (),
            {
                "status": "OVERLAY_BOOT_QUARANTINED",
                "quarantined": True,
                "reason": f"{type(exc).__name__}: {exc}",
            },
        )
    return routers, {"status": "CLEAN", "quarantined": False, "reason": ""}


def _is_overlay_directory_healthy(ws: Path) -> bool:
    routers_dir = ws / "surfaces/web/routers"
    if routers_dir.is_dir():
        for r_file in sorted(routers_dir.glob("*.py")):
            if r_file.stat().st_mode & stat.S_IWOTH:
                return False
    tpl_dir = (ws / "surfaces/web/templates").resolve()
    if tpl_dir.is_dir():
        _, verdict = filter_safe_overlay_template_dirs(ws, (tpl_dir,))
        if verdict["quarantined"]:
            return False
    return True


def evaluate_local_security_posture(
    workspace_dir: Path, *, parent_dir: Path | None = None
) -> dict[str, Any]:
    """Compute an objective 0..100 Local Security Posture Score across 5 verifiable checks."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    posture = resolve_governance_posture(ws, manifest, parent_dir=eff_parent)
    egress = resolve_effective_egress_policy(ws, manifest=manifest, parent_dir=eff_parent)
    dev_exp = classify_exposure_posture(manifest, active_env="dev")["posture"]
    pro_exp = classify_exposure_posture(manifest, active_env="pro")["posture"]

    gi_path = ws / ".gitignore"
    gi_txt = gi_path.read_text(encoding="utf-8", errors="ignore") if gi_path.is_file() else ""
    checks: dict[str, bool] = {
        "gitignore_runtime_hygiene": ".zcg/" in gi_txt,
        "skill_supply_chain_trust": bool(lint_skills_security(ws, parent_dir=eff_parent)["passed"]),
        "egress_and_airgap_confinement": (
            posture.get("personal_pillar") == "wallet"
            or egress.egress_restricted
            or dev_exp == "private-personal"
        ),
        "surface_ring_governance": (
            isinstance(manifest.get("surface_access"), Mapping) or pro_exp != "public-live"
        ),
        "overlay_integrity": _is_overlay_directory_healthy(ws),
    }
    score = sum(POINTS_PER_CHECK for passed in checks.values() if passed)
    if score >= HARDENED_MIN_SCORE:
        grade = "HARDENED"
    elif score >= GUARDED_MIN_SCORE:
        grade = "GUARDED"
    else:
        grade = "ACTION_REQUIRED"
    recs = [_RECOMMENDATION_MAP[key] for key, passed in checks.items() if not passed]
    return {
        "contract_rev": POSTURE_CONTRACT_REV,
        "score": score,
        "grade": grade,
        "checks": checks,
        "recommendations": recs,
    }
