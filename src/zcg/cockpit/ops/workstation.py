"""Workstation Control Tower: Antigravity IDE registrar, boot autostart, and AGENTS.md composer.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zcg.cockpit.routing.network_auth import (
    is_private_personal_node,
    resolve_default_node_environment,
)
from zcg.cockpit.views.surfaces import resolve_node_intranet_topology
from zcg.core.constants import (
    AGENTS_MD_MAX_BYTES,
    DEFAULT_INTERACTION_LANGUAGE,
    INDIVIDUAL_MIN_PRECEDENCE,
    INTERACTION_LANGUAGE_LABELS,
    NODE_MANIFEST_REL_PATH,
    REPO_DIR,
    VALID_INTERACTION_LANGUAGES,
)
from zcg.core.epistemics import PROFILE_TEMPLATE_CHAIN, VALID_GLOBAL_PROFILES
from zcg.core.manifests import (
    load_node_manifest,
    resolve_template_dir,
    strip_markdown_frontmatter,
)

WORKSTATION_UNIT_NAME: str = "zcg-workstation.service"


def _strip_frontmatter(markdown_text: str) -> str:
    return strip_markdown_frontmatter(markdown_text)


def _strip_secondary_header(markdown_text: str) -> str:
    lines, idx = _strip_frontmatter(markdown_text).splitlines(), 0
    while idx < len(lines) and (
        lines[idx].startswith(("# ", ">")) or lines[idx].strip() in ("", "---")
    ):
        idx += 1
    return "\n".join(lines[idx:]).strip()


def _backup_preexisting_home_files(target_home: Path, *, stamp: str | None = None) -> list[str]:
    """Preserve non-symlink AGENTS.md and hooks.json in <home>/.gemini/config before GNU Stow."""
    eff_stamp = stamp or datetime.now(UTC).strftime("%Y%m%d")
    cfg_dir = target_home / ".gemini/config"
    backed_up: list[str] = []
    for fname in ("AGENTS.md", "hooks.json"):
        cand = cfg_dir / fname
        if cand.is_file() and not cand.is_symlink():
            bak = cand.with_name(f"{fname}.backup.{eff_stamp}")
            cand.replace(bak)
            backed_up.append(str(bak))
    return backed_up


def _ensure_fixed_mcp_registered(
    repo_dir: Path, target_home: Path, *, workstation_dir: Path | None = None
) -> None:
    cfg_p = target_home / ".gemini/config/mcp_config.json"
    ag_p = target_home / ".gemini/antigravity/mcp_config.json"
    cfg_p.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if cfg_p.is_file():
        try:
            loaded = json.loads(cfg_p.read_text("utf-8"))
        except ValueError:
            loaded = None
        if isinstance(loaded, dict):
            data = loaded
        else:
            stamp = datetime.now(UTC).strftime("%Y%m%d")
            cfg_p.replace(cfg_p.with_name(f"mcp_config.json.backup.{stamp}"))
    if not isinstance(data.get("mcpServers"), dict):
        data["mcpServers"] = {}
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
    data["mcpServers"]["zcg-mcp"] = cmd_entry
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


def render_systemd_user_unit(
    workspace_dir: Path,
    *,
    engine_dir: Path,
    port: int,
    layer_id: str,
    docs_mode: str = "public",
) -> str:
    """Render a loopback-only user systemd service unit for a ZeroCloudGravity node."""
    ws, eng = workspace_dir.resolve(), engine_dir.resolve()
    venv_py = eng / ".venv/bin/python"
    py_bin = venv_py if venv_py.is_file() else Path(sys.executable)
    src_dir = eng / "src"
    return (
        "[Unit]\n"
        f"Description=ZeroCloudGravity Sovereign Node ({layer_id} on 127.0.0.1:{port})\n"
        "After=default.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={ws}\n"
        f'Environment="PYTHONPATH={src_dir}"\n'
        'Environment="ZCG_NO_BROWSER=1"\n'
        f"ExecStart={py_bin} -m zcg.cockpit.ops.asgi --workspace {ws} "
        f"--host 127.0.0.1 --port {port} --docs-mode {docs_mode}\n"
        "Restart=on-failure\n"
        "RestartSec=2\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def configure_node_boot_autostart(
    workspace_dir: Path,
    *,
    engine_dir: Path = REPO_DIR,
    enable: bool = True,
    home_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install or remove a user systemd login autostart unit for a sovereign node."""
    ws = workspace_dir.resolve()
    manifest = load_node_manifest(ws)
    layer_id = str(manifest.get("layer_id") or ws.name)
    ws_role = str(manifest.get("layer_role") or "")
    is_ws = ws_role == "workstation" or (
        not ws_role and int(manifest.get("precedence", 0)) == INDIVIDUAL_MIN_PRECEDENCE + 5
    )
    active_env = resolve_default_node_environment(manifest)
    topo = resolve_node_intranet_topology(
        manifest, layer_id=layer_id, active_env=active_env, workspace_dir=ws
    )
    port = int(topo["port"])
    d_mode = (
        "disabled" if (active_env == "pro" and not is_private_personal_node(manifest)) else "public"
    )
    unit_name = WORKSTATION_UNIT_NAME if is_ws else f"zcg-node-{layer_id}.service"
    eff_home = (home_dir or Path.home()).resolve()
    systemd_dir = eff_home / ".config/systemd/user"
    unit_path = systemd_dir / unit_name
    wants_link = systemd_dir / "default.target.wants" / unit_name
    systemctl_bin = shutil.which("systemctl")
    allow_systemctl = (
        bool(systemctl_bin)
        and eff_home == Path.home().resolve()
        and not os.environ.get("PYTEST_CURRENT_TEST")
        and not os.environ.get("ZCG_NO_DAEMON")
    )
    systemctl_ran = False
    if not dry_run:
        if enable:
            unit_path.parent.mkdir(parents=True, exist_ok=True)
            unit_txt = render_systemd_user_unit(
                ws, engine_dir=engine_dir, port=port, layer_id=layer_id, docs_mode=d_mode
            )
            unit_path.write_text(unit_txt, encoding="utf-8")
            wants_link.parent.mkdir(parents=True, exist_ok=True)
            if not wants_link.exists() and not wants_link.is_symlink():
                wants_link.symlink_to(unit_path)
            if allow_systemctl:
                subprocess.run(  # noqa: S603
                    [str(systemctl_bin), "--user", "daemon-reload"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(  # noqa: S603
                    [str(systemctl_bin), "--user", "enable", "--now", unit_name],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                systemctl_ran = True
        else:
            if allow_systemctl:
                subprocess.run(  # noqa: S603
                    [str(systemctl_bin), "--user", "disable", "--now", unit_name],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(  # noqa: S603
                    [str(systemctl_bin), "--user", "daemon-reload"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                systemctl_ran = True
            wants_link.unlink(missing_ok=True)
            unit_path.unlink(missing_ok=True)
    return {
        "unit_name": unit_name,
        "unit_path": str(unit_path),
        "enabled": enable,
        "port": port,
        "is_workstation": is_ws,
        "systemctl_invoked": systemctl_ran,
    }


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
    composed = raw_composed
    for existing_lbl in INTERACTION_LANGUAGE_LABELS.values():
        composed = composed.replace(
            f"Interaction Language: {existing_lbl}", f"Interaction Language: {lbl}"
        )
    composed_bytes = len(composed.encode("utf-8"))
    if composed_bytes > AGENTS_MD_MAX_BYTES:
        msg = f"Composed AGENTS.md ({composed_bytes} bytes) exceeds {AGENTS_MD_MAX_BYTES}-byte cap"
        raise ValueError(msg)
    stow_root = workstation_dir if (workstation_dir is not None and ws_data) else repo_dir
    target_agents, stow_executed = stow_root / "antigravity/.gemini/config/AGENTS.md", False
    backed_up_files: list[str] = []
    boot_autostart: dict[str, Any] | None = None
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
            backed_up_files = _backup_preexisting_home_files(target_home)
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
            ws_role = str(ws_data.get("layer_role") or "")
            is_ws_node = ws_role == "workstation" or (
                not ws_role and int(ws_data.get("precedence", 0)) == INDIVIDUAL_MIN_PRECEDENCE + 5
            )
            if workstation_dir is not None and ws_data and is_ws_node:
                boot_autostart = configure_node_boot_autostart(
                    workstation_dir,
                    engine_dir=repo_dir,
                    enable=True,
                    home_dir=target_home,
                    dry_run=False,
                )
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
        "backed_up_files": backed_up_files,
        "boot_autostart": boot_autostart,
    }
