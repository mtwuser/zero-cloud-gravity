"""Workstation Control Tower: Antigravity IDE registrar and global AGENTS.md composer.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zcg.core.constants import (
    AGENTS_MD_MAX_BYTES,
    DEFAULT_INTERACTION_LANGUAGE,
    INDIVIDUAL_MIN_PRECEDENCE,
    INTERACTION_LANGUAGE_LABELS,
    NODE_MANIFEST_REL_PATH,
    VALID_INTERACTION_LANGUAGES,
)
from zcg.core.manifests import load_node_manifest, resolve_template_dir

FRONTMATTER_OPEN_LEN: int = 4
FRONTMATTER_CLOSE_LEN: int = 5
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


def _strip_frontmatter(markdown_text: str) -> str:
    text = markdown_text.strip()
    end_idx = text.find("\n---\n", FRONTMATTER_OPEN_LEN) if text.startswith("---\n") else -1
    return text[end_idx + FRONTMATTER_CLOSE_LEN :].strip() if end_idx != -1 else text


def _strip_secondary_header(markdown_text: str) -> str:
    lines, idx = _strip_frontmatter(markdown_text).splitlines(), 0
    while idx < len(lines) and (
        lines[idx].startswith(("# ", ">")) or lines[idx].strip() in ("", "---")
    ):
        idx += 1
    return "\n".join(lines[idx:]).strip()


def register_antigravity_workspace(
    target_dir: Path, *, home_dir: Path | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Idempotently register <target_dir> inside <home>/.gemini/antigravity/workspaces.json."""
    ws_str = str(target_dir.resolve())
    eff_home = (home_dir or Path.home()).resolve()
    ag_dir = eff_home / ".gemini" / "antigravity"
    ws_file = ag_dir / "workspaces.json"
    if home_dir is None and not ag_dir.is_dir():
        return {"registered": False, "workspaces_file": str(ws_file), "workspace": ws_str}
    raw = json.loads(ws_file.read_text(encoding="utf-8")) if ws_file.is_file() else {}
    entries = list(raw.get("workspaces", [])) if isinstance(raw, dict) else []
    if ws_str not in entries:
        entries.append(ws_str)
    if not dry_run:
        ag_dir.mkdir(parents=True, exist_ok=True)
        ws_file.write_text(json.dumps({"workspaces": entries}, indent=2) + "\n", encoding="utf-8")
    return {"registered": True, "workspaces_file": str(ws_file), "workspace": ws_str}


def _ensure_fixed_mcp_registered(
    repo_dir: Path, target_home: Path, *, workstation_dir: Path | None = None
) -> None:
    cfg_p = target_home / ".gemini/config/mcp_config.json"
    ag_p = target_home / ".gemini/antigravity/mcp_config.json"
    cfg_p.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = json.loads(cfg_p.read_text("utf-8")) if cfg_p.is_file() else {}
    zcg_mcp = str((repo_dir / ".venv/bin/zcg-mcp").resolve())
    mcp_args = (
        ["--repo-dir", str(workstation_dir.resolve())]
        if workstation_dir is not None and (workstation_dir / NODE_MANIFEST_REL_PATH).is_file()
        else []
    )
    cmd_entry = (
        {"command": zcg_mcp, "args": mcp_args}
        if Path(zcg_mcp).is_file()
        else {"command": "python3", "args": ["-m", "zcg.mcp.server", *mcp_args]}
    )
    data.setdefault("mcpServers", {})["zcg-mcp"] = cmd_entry
    cfg_p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ag_p.parent.mkdir(parents=True, exist_ok=True)
    if not ag_p.exists() and not ag_p.is_symlink():
        ag_p.symlink_to(cfg_p)


def _sync_workstation_antigravity_assets(repo_dir: Path, ws_dir: Path) -> None:
    """Propagate engine hooks, scripts, skills, and desktop launchers into <ws_dir>/antigravity."""
    src_ag = repo_dir / "antigravity"
    if not src_ag.is_dir() or repo_dir.resolve() == ws_dir.resolve():
        return
    dst_ag = ws_dir / "antigravity"
    src_cfg, dst_cfg = src_ag / ".gemini/config", dst_ag / ".gemini/config"
    dst_cfg.mkdir(parents=True, exist_ok=True)
    hooks_src = src_cfg / "hooks.json"
    if hooks_src.is_file():
        shutil.copy2(hooks_src, dst_cfg / "hooks.json")
    for sub in ("scripts", "skills"):
        sub_src = src_cfg / sub
        if sub_src.is_dir():
            shutil.copytree(sub_src, dst_cfg / sub, dirs_exist_ok=True)
    apps_src = src_ag / ".local/share/applications"
    if apps_src.is_dir():
        shutil.copytree(apps_src, dst_ag / ".local/share/applications", dirs_exist_ok=True)


def set_global_agents_profile(
    repo_dir: Path,
    profile: str,
    *,
    interaction_language: str | None = None,
    workstation_dir: Path | None = None,
    run_stow: bool = False,
    home_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Compose antigravity/.gemini/config/AGENTS.md from modular base templates."""
    if profile not in VALID_GLOBAL_PROFILES:
        raise ValueError(f"Invalid global profile {profile!r}; must be in {VALID_GLOBAL_PROFILES}")
    m_path = repo_dir / NODE_MANIFEST_REL_PATH
    m_data = load_node_manifest(repo_dir)
    ws_m_path = workstation_dir / NODE_MANIFEST_REL_PATH if workstation_dir is not None else None
    ws_data = (
        load_node_manifest(workstation_dir)
        if workstation_dir is not None and ws_m_path is not None and ws_m_path.is_file()
        else {}
    )
    is_ind = (
        m_data.get("entity_kind") == "individual"
        or int(m_data.get("precedence", 10)) >= INDIVIDUAL_MIN_PRECEDENCE
    )
    def_l = (
        str(m_data.get("interaction_language", DEFAULT_INTERACTION_LANGUAGE))
        if is_ind
        else str(ws_data.get("interaction_language", DEFAULT_INTERACTION_LANGUAGE))
    )
    eff_lang = interaction_language or def_l
    if eff_lang not in VALID_INTERACTION_LANGUAGES:
        raise ValueError(
            f"Invalid interaction_language {eff_lang!r}; must be in {VALID_INTERACTION_LANGUAGES}"
        )
    sections, source_files = list[str](), list[str]()
    for idx, (tpl_id, rule_filename) in enumerate(PROFILE_TEMPLATE_CHAIN[profile]):
        tdir = resolve_template_dir(repo_dir, tpl_id) or (repo_dir / "templates" / tpl_id)
        rule_path = tdir / "rules" / rule_filename
        if not rule_path.is_file():
            rel_miss = rule_path.relative_to(repo_dir)
            raise ValueError(f"Missing profile template rule file: {rel_miss}")
        source_files.append(str(rule_path.relative_to(repo_dir)))
        raw_text = rule_path.read_text(encoding="utf-8").strip()
        sec = _strip_frontmatter(raw_text) if idx == 0 else _strip_secondary_header(raw_text)
        sections.append(sec)
    if workstation_dir is not None and ws_data:
        ws_id = str(ws_data.get("layer_id") or workstation_dir.name)
        ws_tdir = resolve_template_dir(workstation_dir, ws_id) or (
            workstation_dir / "templates" / ws_id
        )
        ws_rule = ws_tdir / "rules" / f"{ws_id}.md"
        if ws_rule.is_file():
            source_files.append(f"{workstation_dir.name}:{ws_rule.relative_to(workstation_dir)}")
            sections.append(_strip_frontmatter(ws_rule.read_text(encoding="utf-8").strip()))
    raw_composed = "\n\n---\n\n".join(sections) + "\n"
    lbl = INTERACTION_LANGUAGE_LABELS[eff_lang]
    composed = re.sub(
        r"Interaction Language:\s*[A-Za-z]+\s*\([a-z]{2}\)",
        f"Interaction Language: {lbl}",
        raw_composed,
    )
    composed_bytes = len(composed.encode("utf-8"))
    if composed_bytes > AGENTS_MD_MAX_BYTES:
        msg = f"Composed AGENTS.md ({composed_bytes} bytes) exceeds {AGENTS_MD_MAX_BYTES}-byte cap"
        raise ValueError(msg)
    stow_root = workstation_dir if (workstation_dir is not None and ws_data) else repo_dir
    target_agents, stow_executed = stow_root / "antigravity/.gemini/config/AGENTS.md", False
    if not dry_run:
        if stow_root != repo_dir:
            _sync_workstation_antigravity_assets(repo_dir, stow_root)
        target_agents.parent.mkdir(parents=True, exist_ok=True)
        target_agents.write_text(composed, encoding="utf-8")
        if is_ind and m_path.is_file():
            m_data["global_profile"], m_data["interaction_language"] = profile, eff_lang
            m_path.write_text(json.dumps(m_data, indent=2, ensure_ascii=False) + "\n", "utf-8")
        if ws_m_path is not None and ws_data:
            ws_data["global_profile"], ws_data["interaction_language"] = profile, eff_lang
            ws_m_path.write_text(json.dumps(ws_data, indent=2, ensure_ascii=False) + "\n", "utf-8")
        if run_stow:
            target_home = home_dir or Path.home()
            stow_bin = shutil.which("stow") or "/usr/bin/stow"
            subprocess.run(  # noqa: S603
                [stow_bin, "--no-folding", "-t", str(target_home), "-R", "antigravity"],
                cwd=stow_root,
                check=True,
                capture_output=True,
                text=True,
            )
            _ensure_fixed_mcp_registered(repo_dir, target_home, workstation_dir=workstation_dir)
            stow_executed = True
    return {
        "profile": profile,
        "interaction_language": eff_lang,
        "workstation_dir": str(workstation_dir.resolve()) if workstation_dir is not None else None,
        "source_files": source_files,
        "dry_run": dry_run,
        "target_file": str(target_agents.relative_to(stow_root)),
        "size_bytes": composed_bytes,
        "budget_max_bytes": AGENTS_MD_MAX_BYTES,
        "headroom_bytes": AGENTS_MD_MAX_BYTES - composed_bytes,
        "stow_executed": stow_executed,
    }
