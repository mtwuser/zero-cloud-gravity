"""Ephemeral Department Bot MCP tool orchestration (orchestrate_ephemeral_fork).

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from zcg.capsules.codec import orchestrate_ephemeral_return_capsule
from zcg.capsules.constants import (
    DEFAULT_EPHEMERAL_TTL_SECONDS,
    MAX_ACTIVE_EPHEMERAL_FORKS,
    VALID_EPHEMERAL_ACTIONS,
)
from zcg.capsules.grcc import orchestrate_dmcp_branch_projection, orchestrate_grcc_capsule_ref
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.ephemeral.briefs import build_subagent_invocation_brief
from zcg.ephemeral.lifecycle import (
    default_ephemeral_root,
    inspect_ephemeral_forks,
    reap_ephemeral_fork,
)
from zcg.ephemeral.spawner import spawn_ephemeral_fork
from zcg.mcp.catalogs import resolve_bot_archetype, resolve_mcp_capability_profile
from zcg.mcp.federation import FederationMixin
from zcg.mcp.surfaces import SurfaceGovernanceMixin


def _tool_ok(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": False}


def _clean_str_list(items: Any) -> list[str]:
    return [str(x) for x in (items or []) if str(x).strip()]


class EphemeralOrchestrationMixin(FederationMixin):
    """Implements orchestrate_ephemeral_fork across all 9 symbiotic lifecycle actions."""

    def _inspect_combined_forks(self, fork_id: str | None, reaped_mem: list[str]) -> dict[str, Any]:
        if fork_id and fork_id in reaped_mem:
            raise FileNotFoundError(f"EPHEMERAL_FORK_EXPIRED: Ephemeral fork {fork_id!r} expired.")
        now = time.time()
        mem_forks = [
            {
                "fork_id": fid,
                "fork_dir": str(e.get("fork_dir", "")),
                "bot_role": str(e.get("bot_role", "")),
                "model_tier": str(e.get("model_tier", "flash")),
                "access_mode": str(e.get("access_mode", "strictly-read-only")),
                "ephemeral_scope": str(e.get("ephemeral_scope", "intra-layer")),
                "actor_role": str(e.get("actor_role", "member")),
                "remaining_ttl_seconds": max(
                    0.0, round(float(e.get("expires_at_epoch", 0.0)) - now, 1)
                ),
                "default_stack_templates": list(
                    e.get("manifest", {}).get("default_stack_templates", [])
                ),
            }
            for fid, e in sorted(self.ephemeral_memory_store.items())
            if e.get("active") and e.get("in_memory_only") and (not fork_id or fid == fork_id)
        ]
        if fork_id and mem_forks:
            return {"active_count": 1, "reaped_expired": reaped_mem, "forks": mem_forks}
        disk_res = inspect_ephemeral_forks(self.repo_dir, fork_id=fork_id)
        if fork_id is None and mem_forks:
            disk_res["forks"].extend(mem_forks)
            disk_res["active_count"] = len(disk_res["forks"])
            disk_res["reaped_expired"] = [*disk_res["reaped_expired"], *reaped_mem]
        return disk_res

    def _reap_combined_forks(self, fork_id: str) -> dict[str, Any]:
        self.reap_expired_memory_forks()
        if fork_id == "all":
            mem_ids = [
                fid for fid, e in sorted(self.ephemeral_memory_store.items()) if e.get("active")
            ]
            self.ephemeral_memory_store.clear()
            disk_reaped = reap_ephemeral_fork(self.repo_dir, fork_id="all")["reaped_forks"]
            return {"dry_run": False, "reaped_forks": list(dict.fromkeys([*disk_reaped, *mem_ids]))}
        mem_entry = self.ephemeral_memory_store.pop(fork_id, None)
        try:
            return reap_ephemeral_fork(self.repo_dir, fork_id=fork_id)
        except FileNotFoundError:
            if mem_entry is not None:
                return {"dry_run": False, "reaped_forks": [fork_id]}
            raise

    def tool_orchestrate_ephemeral_fork(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Spawn, inspect, evaluate, seal-return, or reap TTL-bounded ephemeral Department Bots."""
        action = str(arguments.get("action") or "evaluate").strip().lower()
        if action not in VALID_EPHEMERAL_ACTIONS:
            raise ValueError(f"Invalid action {action!r}: must be in {VALID_EPHEMERAL_ACTIONS}")
        fork_id = str(arguments.get("fork_id") or "").strip() or None
        bot_role = str(arguments.get("bot_role") or "dept-specialist-bot").strip()
        target_path = str(arguments.get("target_path") or "").strip()
        resolution = str(arguments.get("resolution") or "L2").strip().upper()
        one_shot = bool(arguments.get("one_shot", True))
        reaped_mem = self.reap_expired_memory_forks()

        if action == "inspect":
            try:
                return _tool_ok(self._inspect_combined_forks(fork_id, reaped_mem))
            except FileNotFoundError as exc:
                if "EPHEMERAL_FORK_EXPIRED" in str(exc):
                    self.emit_warning(
                        "WARN", "EPHEMERAL_FORK_EXPIRED", str(exc), {"fork_id": fork_id or ""}
                    )
                raise ValueError(str(exc)) from exc
        if action == "reap":
            if not fork_id:
                raise ValueError("Missing required 'fork_id' (or 'all') for action='reap'")
            return _tool_ok(self._reap_combined_forks(fork_id))

        base_manifest = self.load_layer_manifest()
        parent_id = str(base_manifest.get("layer_id", "root"))
        if action == "catalog":
            active_forks = self._inspect_combined_forks(None, reaped_mem).get("forks", [])
            return _tool_ok(
                resolve_mcp_capability_profile(
                    base_manifest,
                    environment=str(arguments.get("environment") or "all"),
                    active_ephemeral_forks=active_forks,
                    family_filter=str(arguments.get("family") or ""),
                )
            )
        if action in ("seal-return", "verify-return"):
            return _tool_ok(
                orchestrate_ephemeral_return_capsule(
                    action,
                    fork_id=fork_id,
                    parent_layer_id=parent_id,
                    meta_resolver=self.resolve_ephemeral_issuer_meta,
                    arguments=arguments,
                )
            )
        if action == "project-branch":
            def_sec = self.resolve_resonance_secret().decode("utf-8")
            dmcp_res = orchestrate_dmcp_branch_projection(
                self.repo_dir, parent_id, arguments, default_secret=def_sec
            )
            if dmcp_res.get("fallback_activated"):
                self.emit_warning(
                    "WARN", "DMCP_CONTEXT_FRAME_INVALID", str(dmcp_res.get("reason", ""))
                )
            return _tool_ok(dmcp_res)
        if action == "chain-capsule-ref":
            return _tool_ok(orchestrate_grcc_capsule_ref(self.repo_dir, parent_id, arguments))

        pb_arg = str(arguments.get("mount_project_rules_from") or "").strip()
        m_tpls = (
            _clean_str_list(arguments["mount_templates"])
            if "mount_templates" in arguments
            else None
        )
        m_lyrs = _clean_str_list(arguments["mount_layers"]) if "mount_layers" in arguments else None
        acc_m = str(arguments.get("access_mode") or "strictly-read-only").strip().lower()
        eph_sc = str(arguments.get("ephemeral_scope") or "").strip().lower() or None
        spawn_kw: dict[str, Any] = {
            "bot_role": bot_role,
            "target_globs": _clean_str_list(arguments.get("target_globs")) or None,
            "architectural_planes": _clean_str_list(arguments.get("architectural_planes")) or None,
            "mount_templates": m_tpls,
            "mount_layers": m_lyrs,
            "mount_project_rules_from": Path(pb_arg) if pb_arg else None,
            "model_tier": str(arguments.get("model_tier") or "flash").strip().lower(),
            "access_mode": acc_m,
            "ephemeral_scope": eph_sc,
            "actor_role": str(arguments.get("actor_role") or "member").strip().lower(),
            "resolution": resolution,
            "ttl_seconds": int(arguments.get("ttl_seconds") or DEFAULT_EPHEMERAL_TTL_SECONDS),
        }
        try:
            if action == "spawn" or not fork_id:
                in_mem_only = False
                try:
                    spawned = spawn_ephemeral_fork(self.repo_dir, base_manifest, **spawn_kw)
                except OSError:
                    act_mem = sum(
                        1 for v in self.ephemeral_memory_store.values() if v.get("active")
                    )
                    if act_mem >= MAX_ACTIVE_EPHEMERAL_FORKS:
                        raise ValueError(
                            f"EPHEMERAL_FORK_LIMIT_REACHED: active forks ({act_mem}) at cap."
                        ) from None
                    spawned = spawn_ephemeral_fork(
                        self.repo_dir, base_manifest, **spawn_kw, dry_run=True
                    )
                    in_mem_only = True
                self.ephemeral_memory_store[str(spawned["fork_id"])] = {
                    **spawned,
                    "parent_layer_id": parent_id,
                    "active": (action == "spawn") or (not one_shot),
                    "in_memory_only": in_mem_only,
                }
            else:
                if fork_id in reaped_mem:
                    raise FileNotFoundError(
                        f"EPHEMERAL_FORK_EXPIRED: Ephemeral fork {fork_id!r} expired."
                    )
                mem_ex = self.ephemeral_memory_store.get(fork_id)
                if mem_ex and mem_ex.get("active") and mem_ex.get("in_memory_only"):
                    spawned = dict(mem_ex)
                else:
                    inspect_ephemeral_forks(self.repo_dir, fork_id=fork_id)
                    fdir_ex = default_ephemeral_root(self.repo_dir) / fork_id
                    man_ex = json.loads(
                        (fdir_ex / NODE_MANIFEST_REL_PATH).read_text(encoding="utf-8")
                    )
                    meta_ex = man_ex.get("ephemeral_metadata", {})
                    def_ttl = DEFAULT_EPHEMERAL_TTL_SECONDS
                    spawned = {
                        "fork_id": fork_id,
                        "fork_dir": str(fdir_ex),
                        "bot_role": str(meta_ex.get("bot_role", bot_role)),
                        "model_tier": str(meta_ex.get("model_tier", "flash")),
                        "access_mode": str(meta_ex.get("access_mode", "strictly-read-only")),
                        "ephemeral_scope": str(meta_ex.get("ephemeral_scope", "intra-layer")),
                        "actor_role": str(meta_ex.get("actor_role", "member")),
                        "ttl_seconds": int(meta_ex.get("ttl_seconds", def_ttl)),
                        "expires_at_epoch": float(meta_ex.get("expires_at_epoch", 0.0)),
                        "session_resonance_key": str(meta_ex.get("session_resonance_key", "")),
                        "bridged_project_files": list(meta_ex.get("bridged_project_files", [])),
                        "reaped_expired": [],
                        "manifest": man_ex,
                    }
                    self.ephemeral_memory_store[fork_id] = {
                        **spawned,
                        "parent_layer_id": parent_id,
                        "active": True,
                        "in_memory_only": False,
                    }
        except (ValueError, FileNotFoundError) as exc:
            msg = str(exc)
            if "EPHEMERAL_FORK_LIMIT_REACHED" in msg:
                self.emit_warning(
                    "WARN", "EPHEMERAL_FORK_LIMIT_REACHED", msg, {"bot_role": bot_role}
                )
            elif "EPHEMERAL_FORK_EXPIRED" in msg:
                self.emit_warning("WARN", "EPHEMERAL_FORK_EXPIRED", msg, {"fork_id": fork_id or ""})
            raise ValueError(msg) from exc

        if action == "spawn":
            return _tool_ok(spawned)
        return self._evaluate_spawned_fork(spawned, target_path, resolution, one_shot, fork_id)

    def _evaluate_spawned_fork(
        self,
        spawned: dict[str, Any],
        target_path: str,
        resolution: str,
        one_shot: bool,
        fork_id: str | None,
    ) -> dict[str, Any]:
        eph_dir = Path(str(spawned["fork_dir"]))
        is_mat = eph_dir.is_dir()
        eph_node = SurfaceGovernanceMixin(
            repo_dir=eph_dir if is_mat else self.repo_dir, log_dir=None
        )
        if not is_mat:
            eph_meta = spawned["manifest"].get("ephemeral_metadata", {})
            allowed_layers = eph_meta.get("mount_layers_filter")
            eph_node.load_layer_manifest = lambda target_dir=None: (  # type: ignore[method-assign]
                spawned["manifest"]
                if (target_dir is None or Path(target_dir).resolve() == self.repo_dir)
                else SurfaceGovernanceMixin.load_layer_manifest(eph_node, target_dir)
            )
            if allowed_layers is not None:
                allowed_set = set(allowed_layers)
                eph_node.discover_mounted_layers = lambda: [  # type: ignore[method-assign]
                    m
                    for m in SurfaceGovernanceMixin.discover_mounted_layers(eph_node)
                    if m["name"] in allowed_set
                ]
        proj_resp = eph_node.tool_resolve_surface_governance(
            {
                "target_path": target_path or "*",
                "resolution_override": resolution,
                "resonance_key": str(spawned["session_resonance_key"]),
                "include_capsules": True,
            }
        )
        surf_proj = json.loads(proj_resp["content"][0]["text"])
        eph_caps = [
            {
                "layer": str(b.get("layer", "root")),
                "binding_id": str(b.get("binding_id", "")),
                "section": str(s.get("section", "")),
                "capsule_token": str(s["capsule_token"]),
            }
            for b in surf_proj.get("resolved_bindings", [])
            for s in b.get("sections", [])
            if s.get("capsule_token")
        ]
        first_cap = eph_caps[0]["capsule_token"] if eph_caps else None
        brief = build_subagent_invocation_brief(
            spawned["manifest"], target_path, surf_proj, first_cap
        )
        auto_reaped = False
        if one_shot and fork_id is None:
            if is_mat:
                reap_ephemeral_fork(self.repo_dir, fork_id=str(spawned["fork_id"]))
            auto_reaped = True
        return _tool_ok(
            {
                "action": "evaluate",
                "fork_id": spawned["fork_id"],
                "bot_role": spawned["bot_role"],
                "bot_archetype": resolve_bot_archetype(str(spawned["bot_role"])),
                "ephemeral_scope": spawned["ephemeral_scope"],
                "actor_role": spawned["actor_role"],
                "auto_reaped": auto_reaped,
                "session_resonance_key": spawned["session_resonance_key"],
                "bridged_project_files": spawned["bridged_project_files"],
                "subagent_invocation_brief": brief,
                "ephemeral_capsule": first_cap,
                "ephemeral_capsules": eph_caps,
                "surface_projection": surf_proj,
            }
        )
