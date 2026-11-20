"""Sovereign 1-hop node update planner, upgrade notes loader, and reconciliation prompt builder.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import REPO_DIR
from zcg.core.manifests import is_oss_root_manifest, load_node_manifest
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_surface_origin

NODE_UPDATES_CONTRACT_REV: Final[str] = "zcg-node-updates-v1"
UPGRADE_NOTES_CONTRACT_REV: Final[str] = "zcg-upgrade-notes-v1"
UPGRADE_NOTES_REL_PATH: Final[str] = "system/upgrade-notes.json"
DEFAULT_FALLBACK_VERSION: Final[str] = "0.0.0"
_SEMVER_SEGMENT_COUNTS: Final[tuple[int, int]] = (2, 3)


def parse_version_tuple(raw: str | None) -> tuple[int, int, int] | None:
    """Parse a 2- or 3-segment SemVer string deterministically without regular expressions."""
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned[0] in ("v", "V"):
        cleaned = cleaned[1:]
    core = cleaned.split("-", 1)[0].split("+", 1)[0].strip()
    parts = core.split(".")
    if len(parts) not in _SEMVER_SEGMENT_COUNTS or not all(
        p.isascii() and p.isdigit() for p in parts
    ):
        return None
    nums = [int(p) for p in parts]
    return (nums[0], nums[1], nums[2] if len(nums) == 3 else 0)


def read_engine_version(engine_dir: Path = REPO_DIR) -> str:
    """Read SemVer string from <engine_dir>/VERSION, falling back to '0.0.0'."""
    ver_file = engine_dir / "VERSION"
    if ver_file.is_file():
        val = ver_file.read_text(encoding="utf-8").strip()
        if val:
            return val
    return DEFAULT_FALLBACK_VERSION


def _load_parsed_upgrade_notes(
    engine_dir: Path = REPO_DIR,
) -> list[tuple[tuple[int, int, int], dict[str, Any]]]:
    notes_file = engine_dir / UPGRADE_NOTES_REL_PATH
    if not notes_file.is_file():
        return []
    try:
        doc = json.loads(notes_file.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return []
    if (
        not isinstance(doc, dict)
        or doc.get("schema_version") != UPGRADE_NOTES_CONTRACT_REV
        or not isinstance(doc.get("releases"), list)
    ):
        return []
    parsed: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for raw_entry in doc["releases"]:
        if not isinstance(raw_entry, dict):
            continue
        ver_str = str(raw_entry.get("version") or "").strip()
        ver_tup = parse_version_tuple(ver_str)
        if ver_tup is None:
            continue
        raw_lvl = str(raw_entry.get("reconciliation_level") or "").strip().lower()
        level = "guided" if raw_lvl == "guided" else "direct"
        raw_hl = raw_entry.get("highlights")
        raw_st = raw_entry.get("reconciliation_steps")
        entry: dict[str, Any] = {
            "version": ver_str,
            "reconciliation_level": level,
            "title": str(raw_entry.get("title") or "").strip(),
            "highlights": (
                [str(x).strip() for x in raw_hl if str(x).strip()]
                if isinstance(raw_hl, list)
                else []
            ),
            "reconciliation_steps": (
                [str(x).strip() for x in raw_st if str(x).strip()]
                if isinstance(raw_st, list)
                else []
            ),
        }
        parsed.append((ver_tup, entry))
    parsed.sort(key=lambda item: item[0])
    return parsed


def load_upgrade_notes(engine_dir: Path = REPO_DIR) -> list[dict[str, Any]]:
    """Load and validate release upgrade notes from system/upgrade-notes.json."""
    return [entry for _, entry in _load_parsed_upgrade_notes(engine_dir)]


def build_reconciliation_prompt(
    *,
    layer_id: str,
    layer_role: str,
    update_source_kind: str,
    update_source_id: str,
    node_version: str | None,
    target_version: str,
    sync_cmd: str,
    release_notes: Sequence[Mapping[str, Any]],
) -> str:
    """Build a deterministic guided reconciliation prompt for 1-hop node synchronization."""
    cur_label = node_version or "unversioned"
    lines: list[str] = [
        f"# 1-Hop Sovereign Reconciliation Prompt — {layer_id} ({layer_role})",
        "",
        f"- **Current Node Engine Version**: `{cur_label}`",
        f"- **Target Version**: `{target_version}`",
        f"- **Authoritative 1-Hop Source**: `{update_source_id}` (`{update_source_kind}`)",
        f"- **Recommended Sync Command**: `{sync_cmd}`",
        "",
    ]
    if release_notes:
        lines.append("## Release Highlights & Reconciliation Steps")
        for note in release_notes:
            ver = str(note.get("version") or target_version)
            title = str(note.get("title") or "Engine upgrade").strip()
            lines.append(f"### v{ver} — {title}")
            for hl in note.get("highlights") or ():
                lines.append(f"- {hl}")
            for idx, step in enumerate(note.get("reconciliation_steps") or (), start=1):
                lines.append(f"{idx}. {step}")
            lines.append("")
    lines.extend(
        [
            "## Non-Destructive Guardrails",
            f"- Preserve local node rules under `templates/{layer_id}/rules/{layer_id}.md`.",
            "- Stage upstream rule deltas under `.agents/proposals/from-upstream/` before merging.",
            f"- Execute `{sync_cmd}`, verify `make diff` reports zero drift, and commit cleanly.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def inspect_node_update_plan(
    workspace_dir: Path,
    *,
    parent_dir: Path | None = None,
    engine_dir: Path = REPO_DIR,
) -> dict[str, Any]:
    """Inspect a node's 1-hop sovereign update plan, parent readiness, and pending release notes."""
    ws = workspace_dir.resolve()
    eng = engine_dir.resolve()
    manifest = load_node_manifest(ws)
    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    oss_ver = read_engine_version(eng)
    is_oss_self = is_oss_root_manifest(manifest)

    p_man = load_node_manifest(eff_parent) if eff_parent is not None else {}
    has_governing_parent = bool(
        eff_parent is not None
        and eff_parent.resolve() != ws
        and eff_parent.resolve() != eng
        and not is_oss_root_manifest(p_man)
    )

    if has_governing_parent and eff_parent is not None:
        eff_p_res = eff_parent.resolve()
        update_source_kind = "governing-parent"
        update_source_id = str(p_man.get("layer_id") or eff_p_res.name)
        update_source_dir = str(eff_p_res)
        parent_engine_version: str | None = str(p_man.get("engine_version") or "").strip() or None
        p_tup, o_tup = parse_version_tuple(parent_engine_version), parse_version_tuple(oss_ver)
        parent_update_required_first = bool(o_tup is not None and (p_tup is None or p_tup < o_tup))
        parent_origin = resolve_surface_origin(p_man)["canonical_origin"]
        parent_admin_url = f"{parent_origin}/admin?tab=runtime"
        target_version = parent_engine_version or oss_ver
    else:
        update_source_kind = "oss-engine"
        update_source_id = "zero-cloud-gravity"
        update_source_dir = str(eng)
        parent_engine_version = None
        parent_update_required_first = False
        parent_admin_url = ""
        target_version = oss_ver

    node_engine_version: str | None = (
        read_engine_version(ws)
        if is_oss_self and (ws / "VERSION").is_file()
        else (str(manifest.get("engine_version") or "").strip() or None)
    )
    n_tup, t_tup = parse_version_tuple(node_engine_version), parse_version_tuple(target_version)
    update_available = bool(manifest and t_tup is not None and (n_tup is None or n_tup < t_tup))

    parsed_notes = _load_parsed_upgrade_notes(eng)
    pending_notes = [
        note
        for nv, note in parsed_notes
        if t_tup is not None and nv <= t_tup and (n_tup is None or nv > n_tup)
    ]
    reference_notes = pending_notes or ([parsed_notes[-1][1]] if parsed_notes else [])
    reconciliation_level = (
        "guided"
        if any(n.get("reconciliation_level") == "guided" for n in pending_notes)
        else "direct"
    )

    layer_id = str(manifest.get("layer_id") or ws.name)
    layer_role = str(manifest.get("layer_role") or "project")
    if manifest.get("layer_role") == "workstation" and not is_oss_self:
        sync_cmd = "zcg workstation sync"
    elif (ws / "Makefile").is_file() and not is_oss_self:
        sync_cmd = f"make -C {ws} sync STRATEGY=reconcile"
    else:
        parent_flag = (
            f" --parent-dir {eff_parent.resolve()}"
            if has_governing_parent and eff_parent is not None
            else ""
        )
        sync_cmd = f"zcg sync-layer {ws}{parent_flag}"

    commands: dict[str, str] = {
        "pull_oss": f"git -C {eng} pull --ff-only" if update_source_kind == "oss-engine" else "",
        "sync_node": sync_cmd,
    }
    prompt = build_reconciliation_prompt(
        layer_id=layer_id,
        layer_role=layer_role,
        update_source_kind=update_source_kind,
        update_source_id=update_source_id,
        node_version=node_engine_version,
        target_version=target_version,
        sync_cmd=sync_cmd,
        release_notes=reference_notes,
    )
    return {
        "contract_rev": NODE_UPDATES_CONTRACT_REV,
        "layer_id": layer_id,
        "layer_role": layer_role,
        "oss_engine_version": oss_ver,
        "parent_engine_version": parent_engine_version,
        "node_engine_version": node_engine_version,
        "target_version": target_version,
        "update_source_kind": update_source_kind,
        "update_source_id": update_source_id,
        "update_source_dir": update_source_dir,
        "parent_update_required_first": parent_update_required_first,
        "parent_admin_url": parent_admin_url,
        "update_available": update_available,
        "reconciliation_level": reconciliation_level,
        "pending_releases": pending_notes,
        "commands": commands,
        "reconciliation_prompt": prompt,
    }
