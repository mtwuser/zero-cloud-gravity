"""Autonomous local workspace fallback and deduplication when $HOME lacks ZCG baseline.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path

from zcg.core import constants, manifests

ZCG_GLOBAL_AGENTS_MARKER: str = "ZeroCloudGravity"
ORDERED_BASE_PACK_IDS: tuple[str, ...] = (
    "universal-base",
    "academic-base",
    "business-base",
    "science-base",
)


def has_global_zcg_baseline(home_dir: Path | None = None) -> bool:
    """Return True when <home>/.gemini/config carries the ZeroCloudGravity universal baseline."""
    if (
        home_dir is None
        and os.environ.get("PYTEST_CURRENT_TEST")
        and os.environ.get("ZCG_FORCE_HOME_PROBE") != "1"
    ):
        return True
    eff_home = (home_dir or Path.home()).resolve()
    agents_file = eff_home / ".gemini/config/AGENTS.md"
    sopen_skill = eff_home / ".gemini/config/skills/sopen/SKILL.md"
    if not agents_file.is_file() or not sopen_skill.is_file():
        return False
    return ZCG_GLOBAL_AGENTS_MARKER in agents_file.read_text(encoding="utf-8", errors="ignore")


def resolve_fallback_base_skills(active_template_ids: Iterable[str]) -> tuple[str, ...]:
    """Resolve base global skills required locally when $HOME lacks ZeroCloudGravity Stow."""
    active_set = {
        "universal-base",
        *(str(t).strip() for t in active_template_ids if str(t).strip()),
    }
    return tuple(
        dict.fromkeys(
            sk
            for base_id in ORDERED_BASE_PACK_IDS
            if base_id in active_set
            for sk in constants.BASE_SKILL_TAXONOMY.get(base_id, ())
        )
    )


def reconcile_workspace_global_baseline(
    target_project_dir: Path,
    *,
    engine_dir: Path,
    active_template_ids: Iterable[str],
    already_copied: Sequence[str],
    home_dir: Path | None = None,
    dry_run: bool = False,
) -> tuple[list[str], list[str]]:
    """Materialize local fallback rules/skills when $HOME is bare, or prune duplicates when set."""
    agents_dir = target_project_dir / ".agents"
    copied_set = set(already_copied)
    materialized: list[str] = []
    pruned: list[str] = []
    ub_dir = manifests.resolve_template_dir(engine_dir, "universal-base")
    ub_src = ub_dir / "rules/universal-base.md" if ub_dir is not None else None
    ag_skills_dir = engine_dir / "antigravity/.gemini/config/skills"

    if not has_global_zcg_baseline(home_dir):
        ub_rel = ".agents/rules/universal-base.md"
        if ub_src is not None and ub_src.is_file() and ub_rel not in copied_set:
            materialized.append(ub_rel)
            if not dry_run:
                ub_dest = agents_dir / "rules/universal-base.md"
                ub_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ub_src, ub_dest)
                manifests.ensure_rule_file_frontmatter(ub_dest)
                ub_dest.chmod(ub_dest.stat().st_mode | constants.OWNER_WRITABLE_MODE_BIT)
        for sk_name in resolve_fallback_base_skills(active_template_ids):
            sk_src = ag_skills_dir / sk_name / "SKILL.md"
            sk_rel = f".agents/skills/{sk_name}/SKILL.md"
            if sk_src.is_file() and sk_rel not in copied_set:
                materialized.append(sk_rel)
                if not dry_run:
                    sk_dest = agents_dir / "skills" / sk_name / "SKILL.md"
                    sk_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(sk_src, sk_dest)
                    sk_dest.chmod(sk_dest.stat().st_mode | constants.OWNER_WRITABLE_MODE_BIT)
        return materialized, pruned

    ub_dest = agents_dir / "rules/universal-base.md"
    if (
        ".agents/rules/universal-base.md" not in copied_set
        and ub_dest.is_file()
        and ub_src is not None
        and ub_src.is_file()
    ):
        fm_bytes = manifests.ensure_rule_file_frontmatter(ub_src, sync_in_place=False).encode()
        if ub_dest.read_bytes() in (ub_src.read_bytes(), fm_bytes):
            pruned.append("universal-base")
            if not dry_run:
                ub_dest.unlink(missing_ok=True)

    all_base_skills = tuple(
        dict.fromkeys(sk for group in constants.BASE_SKILL_TAXONOMY.values() for sk in group)
    )
    for sk_name in all_base_skills:
        sk_rel = f".agents/skills/{sk_name}/SKILL.md"
        sk_dir = agents_dir / "skills" / sk_name
        sk_dest = sk_dir / "SKILL.md"
        sk_src = ag_skills_dir / sk_name / "SKILL.md"
        if (
            sk_rel not in copied_set
            and sk_dest.is_file()
            and sk_src.is_file()
            and sk_dest.read_bytes() == sk_src.read_bytes()
        ):
            pruned.append(f"skill:{sk_name}")
            if not dry_run:
                shutil.rmtree(sk_dir, ignore_errors=True)
    return materialized, pruned
