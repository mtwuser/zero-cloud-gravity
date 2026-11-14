"""Native Google Antigravity 2.0 plugin bundle and project-level permission synthesizer.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from zcg.core import constants
from zcg.core.manifests import (
    canonicalize_local_node_url,
    load_node_manifest,
    read_version,
    strip_markdown_frontmatter,
)
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_governance_posture

MAX_SUGGESTED_PROMPTS: Final[int] = 3


def _read_json_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _is_plugin_template(tpl_dir: Path, meta: Mapping[str, Any]) -> bool:
    return tpl_dir.parent.name == "plugin-stack" or isinstance(meta.get("runtime_service"), dict)


def build_plugin_bundle_manifest(
    plugin_id: str,
    tpl_dir: Path,
    *,
    version: str | None = None,
    disabled: bool = False,
) -> dict[str, Any]:
    """Build an official Antigravity 2.0 plugin.json manifest using strictly allowed fields."""
    meta = _read_json_mapping(tpl_dir / "template.json")
    eff_ver = (version or "").strip() or read_version()
    display_name = str(meta.get("display_name") or plugin_id.replace("-", " ").title())
    desc = str(meta.get("description") or f"Zero-Cloud plugin bundle ({plugin_id}).")
    raw_prompts = meta.get("suggested_prompts")
    custom_prompts = (
        [str(p).strip() for p in raw_prompts if str(p).strip()][:MAX_SUGGESTED_PROMPTS]
        if isinstance(raw_prompts, list)
        else []
    )
    prompts = custom_prompts or [
        f"Inspect {plugin_id} runtime status",
        f"Audit {plugin_id} surface governance",
    ]
    manifest_doc: dict[str, Any] = {
        "name": plugin_id,
        "displayName": display_name,
        "description": desc,
        "version": eff_ver,
        "suggestedPrompts": prompts,
        "disabled": bool(disabled),
    }
    if (tpl_dir / "assets/logo.svg").is_file():
        manifest_doc["logo"] = "assets/logo.svg"
    return manifest_doc


def sync_antigravity_plugins(
    target_dir: Path,
    *,
    active_templates: Sequence[tuple[str, Path]],
    known_templates: Sequence[tuple[str, Path]] = (),
    version: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Materialize .agents/plugins/<pack>/plugin.json bundles and .agents/plugins.json."""
    eff_ver = (version or "").strip() or read_version()
    plugins_root = target_dir / ".agents/plugins"
    active_packs: list[tuple[str, Path]] = []
    seen_active: set[str] = set()
    for tname, tdir in active_templates:
        meta = _read_json_mapping(tdir / "template.json")
        if _is_plugin_template(tdir, meta) and tname not in seen_active:
            seen_active.add(tname)
            active_packs.append((tname, tdir))
    known_plugin_ids: set[str] = set(seen_active)
    for kname, kdir in known_templates:
        if _is_plugin_template(kdir, _read_json_mapping(kdir / "template.json")):
            known_plugin_ids.add(kname)

    enabled_ids: set[str] = set()
    excluded_ids: set[str] = known_plugin_ids - seen_active
    emitted_files: list[str] = []

    for pid, tdir in active_packs:
        rt_doc = _read_json_mapping(target_dir / f".agents/runtime/{pid}.json")
        is_disabled = (
            bool(rt_doc.get("plugin_disabled")) or str(rt_doc.get("status") or "") == "inactive"
        )
        if is_disabled:
            excluded_ids.add(pid)
        else:
            enabled_ids.add(pid)
        p_doc = build_plugin_bundle_manifest(pid, tdir, version=eff_ver, disabled=is_disabled)
        bundle_dir = plugins_root / pid
        emitted_files.append(f".agents/plugins/{pid}/plugin.json")
        rule_files = sorted((tdir / "rules").glob("*.md")) if (tdir / "rules").is_dir() else []
        if rule_files:
            emitted_files.append(f".agents/plugins/{pid}/rules/AGENTS.md")
        skill_files = (
            sorted((tdir / "skills").glob("*/SKILL.md")) if (tdir / "skills").is_dir() else []
        )
        for sf in skill_files:
            emitted_files.append(f".agents/plugins/{pid}/skills/{sf.parent.name}/SKILL.md")
        logo_src = tdir / "assets/logo.svg"
        if logo_src.is_file():
            emitted_files.append(f".agents/plugins/{pid}/assets/logo.svg")
        if not dry_run:
            bundle_dir.mkdir(parents=True, exist_ok=True)
            (bundle_dir / "plugin.json").write_text(
                json.dumps(p_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            if rule_files:
                bodies = [strip_markdown_frontmatter(rf.read_text("utf-8")) for rf in rule_files]
                rules_txt = ("\n\n---\n\n".join(b for b in bodies if b)).strip()
                encoded = rules_txt.encode("utf-8")[: constants.AGENTS_MD_MAX_BYTES]
                (bundle_dir / "rules").mkdir(parents=True, exist_ok=True)
                (bundle_dir / "rules/AGENTS.md").write_text(
                    encoded.decode("utf-8", errors="ignore").rstrip() + "\n", encoding="utf-8"
                )
            for sf in skill_files:
                sk_dest = bundle_dir / "skills" / sf.parent.name / "SKILL.md"
                sk_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sf, sk_dest)
            if logo_src.is_file():
                logo_dest = bundle_dir / "assets/logo.svg"
                logo_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(logo_src, logo_dest)

    pruned_bundles: list[str] = []
    if plugins_root.is_dir():
        for existing_dir in sorted(plugins_root.iterdir()):
            if existing_dir.is_dir() and existing_dir.name not in seen_active:
                pruned_bundles.append(existing_dir.name)
                if not dry_run:
                    shutil.rmtree(existing_dir, ignore_errors=True)

    plugins_doc: dict[str, Any] = {
        "entries": [
            {
                "path": ".agents/plugins",
                "include_only": sorted(enabled_ids),
                "exclude": sorted(excluded_ids),
            }
        ]
    }
    emitted_files.append(constants.PLUGINS_MANIFEST_REL_PATH)
    if not dry_run:
        dest_p = target_dir / constants.PLUGINS_MANIFEST_REL_PATH
        dest_p.parent.mkdir(parents=True, exist_ok=True)
        dest_p.write_text(
            json.dumps(plugins_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return {
        "plugins_manifest": plugins_doc,
        "active_plugins": sorted(enabled_ids),
        "disabled_plugins": sorted(excluded_ids),
        "pruned_bundles": pruned_bundles,
        "files_emitted": emitted_files,
    }


def compile_antigravity_permissions(
    target_dir: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
    parent_dir: Path | None = None,
    active_env: str = "dev",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Compile project-level Antigravity permissions without touching global config.json."""
    ws = target_dir.resolve()
    m = dict(manifest) if manifest is not None else load_node_manifest(ws)
    lid = str(m.get("layer_id") or ws.name)
    lrole = str(m.get("layer_role") or "project")
    default_prec = constants.ROLE_DEFAULT_PRECEDENCE.get(lrole, 80)
    prec = int(m.get("precedence", default_prec))
    port = int(m.get("cockpit_port") or (constants.DEFAULT_PLUGIN_BASE_PORT + prec))
    clean_env = active_env.strip().lower() or "dev"
    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    p_info = resolve_governance_posture(ws, m, parent_dir=eff_parent)
    pillar = p_info.get("personal_pillar")
    purpose_arch = str(pillar or lrole)
    is_wallet = pillar == "wallet" or not bool(p_info.get("allow_cross_workspace_1hop_read", True))

    own_sub = canonicalize_local_node_url(
        f"http://127.0.0.1:{port}", node_id=lid, layer_role=lrole, active_env=clean_env
    )
    allow_urls: list[str] = [own_sub, f"http://127.0.0.1:{port}"]
    raw_egress = m.get("network_egress_policy")
    egress_map = raw_egress if isinstance(raw_egress, Mapping) else {}
    egress_hosts = [
        str(h).strip() for h in (egress_map.get("allowed_hosts") or []) if str(h).strip()
    ]
    if not is_wallet:
        for lnk in m.get("linked_nodes") or []:
            if isinstance(lnk, Mapping) and str(lnk.get("cockpit_url") or "").strip():
                c_url = canonicalize_local_node_url(
                    str(lnk["cockpit_url"]),
                    node_id=str(lnk.get("node_id") or "peer"),
                    layer_role=str(lnk.get("layer_role") or "department"),
                    active_env=clean_env,
                )
                if c_url not in allow_urls:
                    allow_urls.append(c_url)
        for host in egress_hosts:
            if host not in allow_urls:
                allow_urls.append(host)

    read_only_grants: list[str] = []
    if is_wallet:
        non_ws_policy = "deny"
        net_policy = "loopback-only"
        exec_policy = "review-driven"
    else:
        if eff_parent is not None and eff_parent.resolve() != ws:
            read_only_grants.append(str(eff_parent.resolve()))
        layers_dir = ws / "layers"
        if layers_dir.is_dir():
            for sub in sorted(layers_dir.iterdir()):
                if sub.is_dir() and not sub.name.startswith("."):
                    read_only_grants.append(str(sub.resolve()))
        non_ws_policy = "1-hop-read-only" if read_only_grants else "workspace-only"
        net_policy = "curated-allowlist" if egress_hosts else "loopback-and-vcs"
        exec_policy = "strict-review" if clean_env in ("pre", "pro") else "bounded-safe"

    perm_doc: dict[str, Any] = {
        "schema_version": constants.PERMISSIONS_MANIFEST_CONTRACT_REV,
        "layer_id": lid,
        "governance_posture": p_info["governance_posture"],
        "purpose_archetype": purpose_arch,
        "environment": clean_env,
        "global_config_mutated": False,
        "non_workspace_file_access": non_ws_policy,
        "read_only_grants": read_only_grants,
        "browser_allowlist": allow_urls,
        "internet_access_policy": net_policy,
        "auto_execution_policy": exec_policy,
    }
    if not dry_run:
        dest = ws / constants.ANTIGRAVITY_PERMISSIONS_REL_PATH
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(perm_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return perm_doc


def sync_workspace_antigravity_surfaces(
    target_dir: Path,
    *,
    active_templates: Sequence[tuple[str, Path]],
    known_templates: Sequence[tuple[str, Path]] = (),
    manifest: Mapping[str, Any] | None = None,
    parent_dir: Path | None = None,
    active_env: str = "dev",
    dry_run: bool = False,
) -> list[str]:
    """Synchronize Antigravity 2.0 plugin bundles, plugins.json, and project permissions."""
    plug_res = sync_antigravity_plugins(
        target_dir,
        active_templates=active_templates,
        known_templates=known_templates,
        dry_run=dry_run,
    )
    compile_antigravity_permissions(
        target_dir,
        manifest=manifest,
        parent_dir=parent_dir,
        active_env=active_env,
        dry_run=dry_run,
    )
    return [*plug_res["files_emitted"], constants.ANTIGRAVITY_PERMISSIONS_REL_PATH]
