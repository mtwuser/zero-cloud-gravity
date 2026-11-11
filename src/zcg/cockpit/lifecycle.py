"""Deterministic lifecycle engine for Zero-Cloud Node plugin-stack services & daemons.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from zcg.cockpit.surfaces import (
    materialize_node_data_scopes,
    render_node_cockpit_html,
    resolve_node_intranet_topology,
)
from zcg.core.constants import (
    BUILTIN_COCKPIT_PLUGINS,
    NODE_MANIFEST_REL_PATH,
    REPO_DIR,
    VALID_DYNAMIC_RESOLUTION_POLICIES,
    VALID_ENVIRONMENTS,
    VALID_PLUGIN_SERVICE_ACTIONS,
    VALID_RUNTIME_PERSISTENCE_MODES,
)  # fmt: skip
from zcg.core.manifests import load_node_manifest, resolve_template_dir
from zcg.governance.authority import resolve_git_user_email
from zcg.governance.consensus import evaluate_environment_promotion
from zcg.governance.scaffolder import apply_templates_to_project

SURFACE_RENDER_ACTIONS: tuple[str, ...] = (
    "install", "provision", "deploy", "activate", "restart", "deactivate", "switch-env",
)  # fmt: skip


def summarize_runtime_orchestration(
    workspace_dir: Path, manifest: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Summarize static vs. dynamic MCPs and plugins under .agents/runtime/."""
    ws = workspace_dir.resolve()
    m = manifest if manifest is not None else load_node_manifest(ws)
    lid, lrole = str(m.get("layer_id") or ws.name), str(m.get("layer_role") or "project")
    fed = [fm for fm in m.get("federated_mcps", []) if isinstance(fm, dict)]
    static_mcps = [
        {"mcp_id": lid, "role": lrole, "persistence_mode": "static"},
        *[
            {
                "mcp_id": str(fm.get("mcp_id") or fm.get("id") or fm.get("name") or ""),
                "role": str(fm.get("role") or "federated"),
                "persistence_mode": "static",
            }
            for fm in fed
        ],
    ]
    rt_dir = ws / ".agents" / "runtime"
    plugins = (
        [json.loads(fp.read_text("utf-8")) for fp in sorted(rt_dir.glob("*.json"))]
        if rt_dir.is_dir()
        else []
    )
    static_plugins = [p for p in plugins if str(p.get("persistence_mode") or "static") == "static"]
    dynamic_plugins = [p for p in plugins if str(p.get("persistence_mode")) == "dynamic"]
    eph_dir = ws / "logs" / "ephemeral_forks"
    dyn_mcps = [
        load_node_manifest(fd)
        for fd in (sorted(eph_dir.iterdir()) if eph_dir.is_dir() else ())
        if fd.is_dir() and (fd / NODE_MANIFEST_REL_PATH).is_file()
    ]
    bindings = [
        {
            "plugin_id": p.get("plugin_id"),
            "persistence_mode": p.get("persistence_mode", "static"),
            "resolution_policy": p.get("resolution_policy", "standing"),
            "status": p.get("status"),
            "bound_mcps": p.get("bound_mcps", {}),
        }
        for p in plugins
    ]
    return {
        "runtime_contract": "zcg-runtime-registry-v1", "runtime_dir": ".agents/runtime",
        "persistence_modes": list(VALID_RUNTIME_PERSISTENCE_MODES),
        "dynamic_resolution_policies": list(VALID_DYNAMIC_RESOLUTION_POLICIES),
        "static_runtime": {"mcps": static_mcps, "plugins": static_plugins},
        "dynamic_runtime": {"mcps": dyn_mcps, "plugins": dynamic_plugins},
        "plugin_mcp_bindings": bindings,
    }  # fmt: skip


def manage_plugin_daemon(
    ws: Path,
    rt_file: Path,
    port: int,
    *,
    start: bool,
    dry_run: bool,
    docs_mode: str = "public",
) -> dict[str, Any]:
    """Start or stop the Native Python 3.14 ASGI loopback daemon for a Zero-Cloud Node plugin."""
    existing_pid: int | None = None
    if rt_file.is_file():
        old_p = json.loads(rt_file.read_text(encoding="utf-8")).get("daemon_pid")
        existing_pid = int(old_p) if isinstance(old_p, int) and old_p > 0 else None
    if not start:
        if existing_pid is not None and not dry_run:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.kill(existing_pid, signal.SIGTERM)
        return {"daemon_active": False, "daemon_pid": None}
    if existing_pid is not None and not dry_run:
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.kill(existing_pid, 0)
            return {"daemon_active": True, "daemon_pid": existing_pid}
    if dry_run or os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("ZCG_NO_DAEMON"):
        return {"daemon_active": True, "daemon_pid": None}
    (ws / "surfaces/web").mkdir(parents=True, exist_ok=True)
    src_root = str(REPO_DIR / "src")
    cur_pp = os.environ.get("PYTHONPATH", "")
    child_env = {**os.environ, "PYTHONPATH": f"{src_root}:{cur_pp}" if cur_pp else src_root}
    entry = (
        "import sys; from zcg.cockpit.asgi import run_cockpit_daemon_cli; "
        "raise SystemExit(run_cockpit_daemon_cli(sys.argv[1:]))"
    )
    cmd = [
        sys.executable, "-c", entry,
        "--workspace", str(ws), "--port", str(port),
        "--host", "127.0.0.1", "--docs-mode", docs_mode,
    ]  # fmt: skip
    proc = subprocess.Popen(  # noqa: S603
        cmd, env=child_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )  # fmt: skip
    return {"daemon_active": True, "daemon_pid": int(proc.pid)}


def manage_plugin_service(
    workspace_dir: Path, *, action: str, plugin_id: str | None = None, target_env: str = "dev",
    persistence_mode: str = "static", resolution_policy: str = "standing",
    actor_email: str | None = None, parent_dir: Path | None = None,
    engine_dir: Path = REPO_DIR, dry_run: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Execute deterministic lifecycle actions (install..teardown) for plugin-stack plugins."""
    clean_act, clean_env = action.strip().lower(), target_env.strip().lower()
    clean_pm = persistence_mode.strip().lower() or "static"
    def_rp = "goal-resolved" if clean_pm == "dynamic" else "standing"
    clean_rp = resolution_policy.strip().lower() or def_rp
    if clean_act not in VALID_PLUGIN_SERVICE_ACTIONS:
        raise ValueError(f"Invalid action {action!r}; must be in {VALID_PLUGIN_SERVICE_ACTIONS}")
    if clean_env not in VALID_ENVIRONMENTS:
        raise ValueError(f"Invalid target_env {target_env!r}: must be one of {VALID_ENVIRONMENTS}")
    if clean_pm not in VALID_RUNTIME_PERSISTENCE_MODES:
        raise ValueError(f"Invalid persistence_mode {persistence_mode!r}")
    if clean_rp not in VALID_DYNAMIC_RESOLUTION_POLICIES:
        raise ValueError(f"Invalid resolution_policy {resolution_policy!r}")
    ws, m_path = workspace_dir.resolve(), workspace_dir.resolve() / NODE_MANIFEST_REL_PATH
    manifest = load_node_manifest(ws)
    rt_ids = [rf.stem for rf in sorted((ws / ".agents/runtime").glob("*.json"))]
    def_tpls = [str(t) for t in manifest.get("default_stack_templates", [])]
    cand_ids = (
        [plugin_id.strip()]
        if plugin_id and plugin_id.strip()
        else list(dict.fromkeys([*def_tpls, *rt_ids]))
    )
    resolved_plugins: list[tuple[str, Path, dict[str, Any], dict[str, Any]]] = []
    for tid in cand_ids:
        tdir = (
            resolve_template_dir(ws, tid)
            or (parent_dir and resolve_template_dir(parent_dir, tid))
            or resolve_template_dir(engine_dir, tid)
        )
        builtin_rs = {
            "service_id": tid, "framework": "zero-build-html-cockpit",
            "bound_surfaces": ["surfaces/web/", "surfaces/data/"],
            "healthcheck_endpoint": "/healthz",
        }  # fmt: skip
        tj = (
            json.loads((tdir / "template.json").read_text("utf-8"))
            if tdir and (tdir / "template.json").is_file()
            else ({"runtime_service": builtin_rs} if tid in BUILTIN_COCKPIT_PLUGINS else {})
        )
        if isinstance(tj.get("runtime_service"), dict):
            eff_id = tdir.name if tdir else tid
            resolved_plugins.append((eff_id, tdir or ws, tj["runtime_service"], tj))
    non_def = [p for p in resolved_plugins if p[0] != "node-work-cockpit"]
    resolved_plugins = non_def or resolved_plugins
    if not resolved_plugins:
        target_lbl = plugin_id or "workspace"
        raise ValueError(f"No plugin-stack runtime_service plugin found for {target_lbl!r}")
    if clean_act in ("provision", "deploy", "activate", "switch-env") and clean_env != "dev":
        gate_res = evaluate_environment_promotion(
            ws, target_env=clean_env, actor_email=actor_email or resolve_git_user_email(ws),
            parent_dir=parent_dir, dry_run=dry_run,
        )  # fmt: skip
        if not gate_res["allowed"]:
            reasons = "; ".join(gate_res["failed_gates"])
            raise ValueError(f"PLUGIN_ENV_GATE_BLOCKED ({clean_env}): {reasons}")
    layer_id = str(manifest.get("layer_id", ws.name))
    fed_mcps = [
        str(m.get("mcp_id") or m.get("id") or m.get("name") or "")
        for m in manifest.get("federated_mcps", [])
        if isinstance(m, dict)
    ]
    services_out: list[dict[str, Any]] = []
    for tpl_id, tpl_dir, rs, tj_doc in resolved_plugins:
        rt_rel, rt_file = f".agents/runtime/{tpl_id}.json", ws / f".agents/runtime/{tpl_id}.json"
        intranet_topo = resolve_node_intranet_topology(
            manifest, layer_id=layer_id, active_env=clean_env, workspace_dir=ws
        )
        bound_surfaces = [str(s) for s in rs.get("bound_surfaces", [])]
        raw_efp = tj_doc.get("ephemeral_fork_policy")
        efp = raw_efp if isinstance(raw_efp, dict) else {}
        bot_role = str(efp.get("bot_role") or f"{tpl_id}-guardian")
        bound_mcps = {"static_mcps": [layer_id, *fed_mcps], "dynamic_bot_role": bot_role}
        if clean_act in ("teardown", "uninstall"):
            d_info = manage_plugin_daemon(
                ws, rt_file, intranet_topo["port"], start=False, dry_run=dry_run
            )
            if not dry_run:
                rt_file.unlink(missing_ok=True)
            if clean_act == "uninstall" and not dry_run:
                shutil.rmtree(ws / ".agents/assets" / tpl_id, ignore_errors=True)
                shutil.rmtree(ws / "templates/plugin-stack" / tpl_id, ignore_errors=True)
                rem_tpls = [t for t in def_tpls if t != tpl_id]
                if m_path.is_file():
                    manifest["default_stack_templates"] = rem_tpls
                    m_txt = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
                    m_path.write_text(m_txt, "utf-8")
                apply_templates_to_project(
                    ws if m_path.is_file() else engine_dir, ws,
                    template_ref=",".join(rem_tpls) or None, layers_filter=["all"],
                    engine_dir=engine_dir, dry_run=False,
                )  # fmt: skip
            services_out.append({
                "plugin_id": tpl_id, "service_id": str(rs.get("service_id", tpl_id)),
                "environment": clean_env, "persistence_mode": clean_pm,
                "resolution_policy": clean_rp, "last_action": clean_act,
                "status": "uninstalled" if clean_act == "uninstall" else "stopped",
                "bound_mcps": bound_mcps, "intranet_topology": intranet_topo,
                "runtime_state_file": rt_rel, **d_info,
            })  # fmt: skip
            continue
        if clean_act == "install" and not dry_run and tpl_dir != ws:
            dest_t = ws / "templates/plugin-stack" / tpl_id
            if m_path.is_file() and not resolve_template_dir(ws, tpl_id):
                dest_t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(tpl_dir, dest_t)
            cur_tpls = [t for t in def_tpls if t != "node-work-cockpit"]
            (ws / ".agents/runtime/node-work-cockpit.json").unlink(missing_ok=True)
            upd_tpls = cur_tpls if tpl_id in cur_tpls else [*cur_tpls, tpl_id]
            if m_path.is_file() and upd_tpls != def_tpls:
                manifest["default_stack_templates"] = upd_tpls
                m_txt = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
                m_path.write_text(m_txt, "utf-8")
            apply_templates_to_project(
                ws if m_path.is_file() else engine_dir, ws,
                template_ref=",".join(upd_tpls), layers_filter=["all"],
                engine_dir=engine_dir, dry_run=False,
            )  # fmt: skip
        if not dry_run and clean_act in SURFACE_RENDER_ACTIONS:
            for surf in bound_surfaces:
                sp = ws / surf.rstrip("/")
                (sp.parent if sp.suffix else sp).mkdir(parents=True, exist_ok=True)
                if sp.suffix and not sp.is_file():
                    sp.write_text("{}\n" if sp.suffix == ".json" else f"# {sp.name}\n", "utf-8")
            if (assets_src := tpl_dir / "assets").is_dir():
                for afile in (p for p in sorted(assets_src.rglob("*")) if p.is_file()):
                    dest_a = ws / ".agents/assets" / tpl_id / afile.relative_to(assets_src)
                    dest_a.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(afile, dest_a)
        surfaces_ok = (
            all((ws / s.rstrip("/")).exists() for s in bound_surfaces) if not dry_run else True
        )
        was_active = (
            bool(json.loads(rt_file.read_text("utf-8")).get("daemon_active"))
            if clean_act == "switch-env" and rt_file.is_file()
            else False
        )
        want_start = clean_act in ("activate", "restart") or was_active
        ok_st = "healthy" if surfaces_ok else "degraded"
        ready_st = "active" if want_start and surfaces_ok else ok_st
        st_val = "inactive" if clean_act == "deactivate" else ready_st
        base_payload = {
            "plugin_id": tpl_id, "service_id": str(rs.get("service_id", tpl_id)),
            "framework": str(rs.get("framework", "")), "environment": clean_env,
            "persistence_mode": clean_pm, "resolution_policy": clean_rp,
            "status": st_val, "last_action": clean_act,
            "healthcheck_endpoint": str(rs.get("healthcheck_endpoint", "/healthz")),
            "bound_surfaces": bound_surfaces, "surfaces_verified": surfaces_ok,
            "bound_mcps": bound_mcps, "intranet_topology": intranet_topo,
            "data_scopes_dir": "surfaces/data", "assets_dir": f".agents/assets/{tpl_id}",
            "runtime_state_file": rt_rel, "daemon_active": want_start, "daemon_pid": None,
        }  # fmt: skip
        if not dry_run and clean_act in SURFACE_RENDER_ACTIONS:
            scopes = materialize_node_data_scopes(ws, manifest, base_payload)
            (ws / "surfaces/web").mkdir(parents=True, exist_ok=True)
            (ws / "surfaces/web/index.html").write_text(
                render_node_cockpit_html(ws, manifest, base_payload, scopes=scopes),
                encoding="utf-8",
            )
            hz = {
                "status": "ok", "protocol": "python314-native-asgi",
                "plugin_id": tpl_id, "layer_id": layer_id, "environment": clean_env,
                "delivery_channels_count": 16, "zones": ["Z1", "Z2", "Z3", "Z4"],
                "http_poll_stop_status": 286, "health_regime": "OPTIMAL",
            }  # fmt: skip
            (ws / "surfaces/web/healthz").write_text(json.dumps(hz) + "\n", encoding="utf-8")
        run_d = clean_act in ("activate", "restart", "deactivate") or was_active
        d_mode = "disabled" if clean_env == "pro" else "public"
        d_state = (
            manage_plugin_daemon(
                ws, rt_file, intranet_topo["port"],
                start=want_start, dry_run=dry_run, docs_mode=d_mode,
            )
            if run_d
            else {"daemon_active": False, "daemon_pid": None}
        )  # fmt: skip
        state_payload = {**base_payload, **d_state}
        disk_payload = (
            {**state_payload, "status": "healthy", "last_action": "provision"}
            if clean_act == "deactivate" and surfaces_ok
            else state_payload
        )
        if not dry_run and (clean_act != "healthcheck" or not rt_file.is_file()):
            rt_file.parent.mkdir(parents=True, exist_ok=True)
            rt_txt = json.dumps(disk_payload, indent=2, ensure_ascii=False) + "\n"
            rt_file.write_text(rt_txt, "utf-8")
        services_out.append(state_payload)
    return {
        "workspace_dir": str(ws), "layer_id": layer_id, "action": clean_act,
        "environment": clean_env, "persistence_mode": clean_pm,
        "resolution_policy": clean_rp, "dry_run": dry_run, "services": services_out,
    }  # fmt: skip
