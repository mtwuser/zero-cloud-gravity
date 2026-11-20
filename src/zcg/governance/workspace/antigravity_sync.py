"""Native Google Antigravity 2.0 plugin bundle and project-level permission synthesizer.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import os
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
from zcg.governance.policy.egress import resolve_effective_egress_policy
from zcg.governance.runtime.mcp_connectors import compile_antigravity_sidecar_manifest
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
        agent_files = sorted((tdir / "agents").glob("*.md")) if (tdir / "agents").is_dir() else []
        for af in agent_files:
            emitted_files.append(f".agents/plugins/{pid}/agents/{af.name}")
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
            for af in agent_files:
                ag_dest = bundle_dir / "agents" / af.name
                ag_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(af, ag_dest)
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
        "plugins_manifest": plugins_doc, "active_plugins": sorted(enabled_ids),
        "disabled_plugins": sorted(excluded_ids), "pruned_bundles": pruned_bundles,
        "files_emitted": emitted_files,
    }  # fmt: skip


def compile_antigravity_permissions(
    target_dir: Path, *, manifest: Mapping[str, Any] | None = None,
    parent_dir: Path | None = None, active_env: str = "dev", dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
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
    raw_dg = m.get("domain_governance")
    c_dom = str(raw_dg.get("canonical_domain") or "").strip() if isinstance(raw_dg, Mapping) else ""
    eg_pol = resolve_effective_egress_policy(
        ws, manifest=m, parent_dir=eff_parent, canonical_domain=c_dom
    )
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
        allow_urls = list(dict.fromkeys([*allow_urls, *eg_pol.browser_allowlist_urls]))

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
        net_policy = "curated-allowlist" if eg_pol.egress_restricted else "loopback-and-vcs"
        exec_policy = "strict-review" if clean_env in ("pre", "pro") else "bounded-safe"

    perm_doc: dict[str, Any] = {
        "schema_version": constants.PERMISSIONS_MANIFEST_CONTRACT_REV, "layer_id": lid,
        "governance_posture": p_info["governance_posture"], "purpose_archetype": purpose_arch,
        "environment": clean_env, "global_config_mutated": False,
        "non_workspace_file_access": non_ws_policy, "read_only_grants": read_only_grants,
        "browser_allowlist": allow_urls, "allowed_egress_domains": list(eg_pol.allowed_domains),
        "cdn_origins": list(eg_pol.cdn_origins),
        "artifact_mirrors": eg_pol.artifact_mirrors.to_dict(),
        "internet_access_policy": net_policy, "auto_execution_policy": exec_policy,
    }  # fmt: skip
    if not dry_run:
        dest = ws / constants.ANTIGRAVITY_PERMISSIONS_REL_PATH
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(perm_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return perm_doc


def _resolve_sync_environment(ws: Path, manifest: Mapping[str, Any] | None, raw_env: str) -> str:
    if raw_env.strip():
        return raw_env.strip().lower()
    rt_dir = ws / ".agents" / "runtime"
    if rt_dir.is_dir():
        for fp in sorted(rt_dir.glob("*.json")):
            rt_env = str(_read_json_mapping(fp).get("environment") or "").strip().lower()
            if rt_env in constants.VALID_ENVIRONMENTS:
                return rt_env
    m = dict(manifest) if manifest is not None else load_node_manifest(ws)
    prec = int(m.get("precedence", 50))
    is_ind = m.get("entity_kind") == "individual" or prec >= constants.INDIVIDUAL_MIN_PRECEDENCE
    vis = str(
        m.get("visibility") or ("public" if m.get("layer_role") == "knowledge" else "private")
    )
    return "pro" if (is_ind and vis != "public") else "dev"


def sync_workspace_antigravity_surfaces(
    target_dir: Path, *, active_templates: Sequence[tuple[str, Path]],
    known_templates: Sequence[tuple[str, Path]] = (), manifest: Mapping[str, Any] | None = None,
    parent_dir: Path | None = None, active_env: str = "", dry_run: bool = False,
) -> list[str]:  # fmt: skip
    """Synchronize Antigravity 2.0 plugin bundles, plugins.json, and project permissions."""
    eff_env = _resolve_sync_environment(target_dir.resolve(), manifest, active_env)
    plug_res = sync_antigravity_plugins(
        target_dir, active_templates=active_templates, known_templates=known_templates,
        dry_run=dry_run,
    )  # fmt: skip
    kw: dict[str, Any] = {
        "manifest": manifest, "parent_dir": parent_dir, "active_env": eff_env, "dry_run": dry_run
    }  # fmt: skip
    compile_antigravity_permissions(target_dir, **kw)
    compile_antigravity_sidecar_manifest(target_dir, **kw)
    return [
        *plug_res["files_emitted"], constants.ANTIGRAVITY_PERMISSIONS_REL_PATH,
        constants.SIDECAR_MANIFEST_REL_PATH,
    ]  # fmt: skip


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


def _normalize_plugin_liveness(raw: dict[str, Any]) -> dict[str, Any]:
    pid = raw.get("daemon_pid")
    is_pos_int = isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
    if not raw.get("daemon_active") or not is_pos_int:
        return raw
    try:
        os.kill(pid, 0)  # type: ignore[arg-type]
    except PermissionError:
        return raw
    except OSError:
        return {**raw, "daemon_active": False, "daemon_pid": None}
    return raw


def summarize_runtime_orchestration(
    workspace_dir: Path, manifest: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Summarize static vs. dynamic MCPs and plugins under .agents/runtime/."""
    ws = workspace_dir.resolve()
    m = dict(manifest) if manifest is not None else load_node_manifest(ws)
    lid, lrole = str(m.get("layer_id") or ws.name), str(m.get("layer_role") or "project")
    fed = [fm for fm in m.get("federated_mcps", []) if isinstance(fm, dict)]
    static_mcps = [
        {"mcp_id": lid, "role": lrole, "persistence_mode": "static"},
        *[
            {"mcp_id": str(fm.get("mcp_id") or fm.get("id") or fm.get("name") or ""),
             "role": str(fm.get("role") or "federated"), "persistence_mode": "static"}
            for fm in fed
        ],
    ]  # fmt: skip
    rt_dir = ws / ".agents" / "runtime"
    plugins = (
        [_normalize_plugin_liveness(json.loads(fp.read_text("utf-8")))
         for fp in sorted(rt_dir.glob("*.json"))]
        if rt_dir.is_dir() else []
    )  # fmt: skip
    static_plugins = [p for p in plugins if str(p.get("persistence_mode") or "static") == "static"]
    dynamic_plugins = [p for p in plugins if str(p.get("persistence_mode")) == "dynamic"]
    eph_dir = ws / "logs" / "ephemeral_forks"
    dyn_mcps = [
        load_node_manifest(fd)
        for fd in (sorted(eph_dir.iterdir()) if eph_dir.is_dir() else ())
        if fd.is_dir() and (fd / constants.NODE_MANIFEST_REL_PATH).is_file()
    ]
    bindings = [
        {"plugin_id": p.get("plugin_id"), "persistence_mode": p.get("persistence_mode", "static"),
         "resolution_policy": p.get("resolution_policy", "standing"),
         "status": p.get("status"), "bound_mcps": p.get("bound_mcps", {})}
        for p in plugins
    ]  # fmt: skip
    return {
        "runtime_contract": "zcg-runtime-registry-v1", "runtime_dir": ".agents/runtime",
        "persistence_modes": list(constants.VALID_RUNTIME_PERSISTENCE_MODES),
        "dynamic_resolution_policies": list(constants.VALID_DYNAMIC_RESOLUTION_POLICIES),
        "static_runtime": {"mcps": static_mcps, "plugins": static_plugins},
        "dynamic_runtime": {"mcps": dyn_mcps, "plugins": dynamic_plugins},
        "plugin_mcp_bindings": bindings,
    }  # fmt: skip
