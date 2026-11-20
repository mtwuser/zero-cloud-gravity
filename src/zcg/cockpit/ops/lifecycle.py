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
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from zcg.cockpit.ops.workstation import configure_node_boot_autostart
from zcg.cockpit.routing.network_auth import (
    is_private_personal_node,
    resolve_default_node_environment,
)
from zcg.cockpit.views.surfaces import (
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
)
from zcg.core.manifests import iter_layer_template_dirs, load_node_manifest, resolve_template_dir
from zcg.governance.policy.authority import resolve_git_user_email
from zcg.governance.policy.capabilities import enforce_capability_gate, lint_skills_security
from zcg.governance.work.consensus import evaluate_environment_promotion
from zcg.governance.workspace.antigravity_sync import sync_workspace_antigravity_surfaces
from zcg.governance.workspace.scaffolder import apply_templates_to_project
from zcg.providers.cloud_gcp import materialize_cloud_deployment_manifest
from zcg.providers.container_edge import materialize_container_deployment_manifest
from zcg.web.ui.static_files import CURRENT_ENGINE_ASSET_DIGEST

SURFACE_RENDER_ACTIONS: tuple[str, ...] = (
    "install", "provision", "deploy", "activate", "restart", "deactivate", "switch-env",
)  # fmt: skip
CAPABILITY_GATED_PLUGIN_ACTIONS: tuple[str, ...] = (
    "install", "uninstall", "activate", "deactivate", "deploy",
)  # fmt: skip
HEALTHZ_PROBE_TIMEOUT_SEC: float = 0.35
DAEMON_STOP_TIMEOUT_SEC: float = 1.5
DAEMON_STOP_POLL_SEC: float = 0.025


def _probe_daemon_healthz(
    port: int, *, timeout_sec: float = HEALTHZ_PROBE_TIMEOUT_SEC
) -> tuple[str | None, str]:
    with contextlib.suppress(OSError, ValueError):
        with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=timeout_sec) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        if isinstance(doc, dict) and (lid := str(doc.get("layer_id") or "").strip()):
            return lid, str(doc.get("engine_asset_digest") or "").strip()
    return None, ""


def _wait_pid_exit(pid: int, *, timeout_sec: float = DAEMON_STOP_TIMEOUT_SEC) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError, PermissionError, OSError:
            return
        time.sleep(DAEMON_STOP_POLL_SEC)


def manage_plugin_daemon(
    ws: Path, rt_file: Path, port: int, *, start: bool, dry_run: bool,
    docs_mode: str = "public", expected_layer_id: str = "", force_restart: bool = False,
) -> dict[str, Any]:  # fmt: skip
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
    rotated_pid: int | None = None
    if existing_pid is not None and not dry_run:
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.kill(existing_pid, 0)
            if not force_restart:
                if not expected_layer_id:
                    return {"daemon_active": True, "daemon_pid": existing_pid}
                occ_lid, occ_dig = _probe_daemon_healthz(port)
                if occ_lid == expected_layer_id and occ_dig == CURRENT_ENGINE_ASSET_DIGEST:
                    return {"daemon_active": True, "daemon_pid": existing_pid}
            os.kill(existing_pid, signal.SIGTERM)
            rotated_pid = existing_pid
    if dry_run or os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("ZCG_NO_DAEMON"):
        return {"daemon_active": True, "daemon_pid": None}
    if rotated_pid is not None:
        _wait_pid_exit(rotated_pid)
    if expected_layer_id:
        occ_lid, _ = _probe_daemon_healthz(port)
        if occ_lid is not None and occ_lid != expected_layer_id:
            raise ValueError(
                f"COCKPIT_PORT_CONFLICT ({port}): port owned by {occ_lid!r}, "
                f"expected {expected_layer_id!r}"
            )
    (ws / "surfaces/web").mkdir(parents=True, exist_ok=True)
    src_root = str(REPO_DIR / "src")
    cur_pp = os.environ.get("PYTHONPATH", "")
    child_env = {**os.environ, "PYTHONPATH": f"{src_root}:{cur_pp}" if cur_pp else src_root}
    entry = (
        "import sys; from zcg.cockpit.ops.asgi import run_cockpit_daemon_cli; "
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
    ws, m_path = workspace_dir.resolve(), workspace_dir.resolve() / NODE_MANIFEST_REL_PATH
    manifest = load_node_manifest(ws)
    rt_files = sorted((ws / ".agents/runtime").glob("*.json"))
    rt_ids = [rf.stem for rf in rt_files]
    clean_act, raw_env = action.strip().lower(), target_env.strip().lower()
    rt0 = json.loads(rt_files[0].read_text("utf-8")) if rt_files else {}
    if not raw_env and (clean_act != "activate" or bool(rt0.get("explicit_env"))):
        raw_env = str(rt0.get("environment") or "").lower()
    clean_env = raw_env or resolve_default_node_environment(manifest)
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
    is_priv_ind = is_private_personal_node(manifest)
    if (
        clean_act in ("provision", "deploy", "activate", "switch-env")
        and clean_env != "dev"
        and not (is_priv_ind and clean_env == "pro")
    ):
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
        for m in manifest.get("federated_mcps", []) if isinstance(m, dict)
    ]  # fmt: skip
    services_out: list[dict[str, Any]] = []
    for tpl_id, tpl_dir, rs, tj_doc in resolved_plugins:
        if clean_act in CAPABILITY_GATED_PLUGIN_ACTIONS:
            enforce_capability_gate(
                ws, operation=clean_act, actor_email=actor_email, parent_dir=parent_dir,
                plugin_id=tpl_id, plugin_dir=tpl_dir if tpl_dir != ws else None, dry_run=dry_run,
            )  # fmt: skip
        if clean_act == "install" and tpl_dir != ws:
            sec_res = lint_skills_security(ws, target_dir=tpl_dir, parent_dir=parent_dir)
            if not sec_res["passed"]:
                msg = f"SKILL_SECURITY_VIOLATION ({tpl_id}): {sec_res['violations'][0]['rule']}"
                raise ValueError(msg)
        rt_rel, rt_file = f".agents/runtime/{tpl_id}.json", ws / f".agents/runtime/{tpl_id}.json"
        intranet_topo = resolve_node_intranet_topology(manifest, layer_id=layer_id, active_env=clean_env, workspace_dir=ws)  # noqa: E501  # fmt: skip
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
        prev_rt = json.loads(rt_file.read_text("utf-8")) if rt_file.is_file() else {}
        prev_active = bool(prev_rt.get("daemon_active"))
        was_active = prev_active if clean_act == "switch-env" else False
        want_start = clean_act in ("activate", "restart") or was_active
        run_d = clean_act in ("activate", "restart", "deactivate") or was_active
        keep_active = prev_active and not run_d
        ok_st = "healthy" if surfaces_ok else "degraded"
        ready_st = "active" if (want_start or keep_active) and surfaces_ok else ok_st
        st_val = "inactive" if clean_act == "deactivate" else ready_st
        exp_env = bool(target_env.strip()) or (
            clean_act != "activate" and bool(prev_rt.get("explicit_env"))
        )
        base_payload = {
            "plugin_id": tpl_id, "service_id": str(rs.get("service_id", tpl_id)),
            "framework": str(rs.get("framework", "")), "environment": clean_env,
            "persistence_mode": clean_pm, "resolution_policy": clean_rp,
            "status": st_val, "last_action": clean_act,
            "healthcheck_endpoint": str(rs.get("healthcheck_endpoint", "/healthz")),
            "bound_surfaces": bound_surfaces, "surfaces_verified": surfaces_ok,
            "bound_mcps": bound_mcps, "intranet_topology": intranet_topo,
            "data_scopes_dir": "surfaces/data", "assets_dir": f".agents/assets/{tpl_id}",
            "runtime_state_file": rt_rel, "daemon_active": want_start or keep_active,
            "explicit_env": exp_env, "daemon_pid": None,
        }  # fmt: skip
        if not dry_run and clean_act in SURFACE_RENDER_ACTIONS:
            scopes = materialize_node_data_scopes(ws, manifest, base_payload)
            is_ws_cat = str(manifest.get("layer_role") or "") == "workstation"
            if "cloud_deployment" in manifest or (not is_ws_cat and "google-cloud-iac" in def_tpls):
                materialize_cloud_deployment_manifest(
                    ws, manifest, intranet_topo, active_env=clean_env, plugin_id=tpl_id
                )
            if "container_deployment" in manifest or (
                not is_ws_cat and "self-hosted-container" in def_tpls
            ):
                materialize_container_deployment_manifest(
                    ws, manifest, intranet_topo, active_env=clean_env, plugin_id=tpl_id
                )
            (ws / "surfaces/web").mkdir(parents=True, exist_ok=True)
            (ws / "surfaces/web/index.html").write_text(
                render_node_cockpit_html(ws, manifest, base_payload, scopes=scopes), "utf-8"
            )
            hz = {
                "status": "ok", "protocol": "python314-native-asgi",
                "plugin_id": tpl_id, "layer_id": layer_id, "environment": clean_env,
                "delivery_channels_count": 16, "zones": ["Z1", "Z2", "Z3", "Z4"],
                "http_poll_stop_status": 286, "health_regime": "OPTIMAL",
            }  # fmt: skip
            (ws / "surfaces/web/healthz").write_text(json.dumps(hz) + "\n", encoding="utf-8")
        d_mode = "disabled" if (clean_env == "pro" and not is_priv_ind) else "public"
        d_state = (
            manage_plugin_daemon(
                ws, rt_file, intranet_topo["port"], start=want_start, dry_run=dry_run,
                docs_mode=d_mode, expected_layer_id=layer_id, force_restart=clean_act == "restart",
            )
            if run_d
            else {"daemon_active": keep_active, "daemon_pid": prev_rt.get("daemon_pid") if keep_active else None}  # noqa: E501
        )  # fmt: skip
        auto_meta = (
            {"boot_autostart": configure_node_boot_autostart(ws, engine_dir=engine_dir, enable=clean_act == "enable-autostart", dry_run=dry_run)}  # noqa: E501
            if clean_act in ("enable-autostart", "disable-autostart") else {}
        )  # fmt: skip
        state_payload = {**base_payload, **d_state, **auto_meta}
        disk_payload = (
            {**state_payload, "status": "healthy", "last_action": "provision", "plugin_disabled": True}  # noqa: E501
            if clean_act == "deactivate" and surfaces_ok
            else {**state_payload, "plugin_disabled": clean_act == "deactivate"}
        )  # fmt: skip
        if not dry_run and (clean_act != "healthcheck" or not rt_file.is_file()):
            rt_file.parent.mkdir(parents=True, exist_ok=True)
            rt_txt = json.dumps(disk_payload, indent=2, ensure_ascii=False) + "\n"
            rt_file.write_text(rt_txt, "utf-8")
        services_out.append(state_payload)
    if not dry_run and clean_act in ("activate", "deactivate", "switch-env") and m_path.is_file():
        cur_m = load_node_manifest(ws)
        act_t = [
            (d.name, d)
            for t in cur_m.get("default_stack_templates", [])
            if (d := resolve_template_dir(ws, str(t)) or resolve_template_dir(engine_dir, str(t)))
        ]
        known_d = {
            **dict(iter_layer_template_dirs(engine_dir)), **dict(iter_layer_template_dirs(ws))
        }  # fmt: skip
        sync_workspace_antigravity_surfaces(
            ws, active_templates=act_t, known_templates=list(known_d.items()),
            manifest=cur_m, parent_dir=parent_dir, active_env=clean_env, dry_run=False,
        )  # fmt: skip
    return {
        "workspace_dir": str(ws), "layer_id": layer_id, "action": clean_act,
        "environment": clean_env, "persistence_mode": clean_pm,
        "resolution_policy": clean_rp, "dry_run": dry_run, "services": services_out,
    }  # fmt: skip
