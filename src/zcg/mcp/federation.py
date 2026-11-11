"""Node overview, drift audit, document reading, and federated MCP discovery tools.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from typing import Any

from zcg.capsules.citations import load_citation_telemetry_radar
from zcg.capsules.constants import (
    ANSI_ESCAPE_RE,
    CHARS_PER_TOKEN_ESTIMATE,
    MAX_RECOMMENDED_MCP_FANOUT,
)
from zcg.capsules.grcc import discover_deep_context_index, read_git_branch_document
from zcg.capsules.markdown import merge_unique_strings, read_non_empty_lines
from zcg.capsules.surfaces import compare_project_patterns_multilayer
from zcg.cockpit.lifecycle import summarize_runtime_orchestration
from zcg.core.constants import AGENTS_MD_MAX_BYTES, REPO_DIR, VALID_ENVIRONMENTS
from zcg.core.epistemics import resolve_effective_human_stack
from zcg.core.manifests import (
    discover_layer_template_names,
    is_running_in_container,
    parse_skill_frontmatter,
    read_git_commit,
    read_os_pretty_name,
    read_version,
)
from zcg.ephemeral.lifecycle import inspect_ephemeral_forks
from zcg.mcp.catalogs import resolve_mcp_capability_profile
from zcg.mcp.surfaces import SurfaceGovernanceMixin
from zcg.topology.identity import resolve_node_entity_identity
from zcg.topology.network import discover_network_topology

AUDIT_CMD_TIMEOUT_SECONDS: int = 30


class FederationMixin(SurfaceGovernanceMixin):
    """Implements node overview, drift audit, document reading, and federation MCP tools."""

    def tool_get_layer_overview(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return a 4-Channel Executive Digest of this Zero-Cloud Node or subtree."""
        tdir = self.resolve_layer_dir(args.get("layer"))
        manifest, sdir = self.load_layer_manifest(tdir), tdir / "system"
        apt = read_non_empty_lines(sdir / "packages-manual.txt")
        snaps = read_non_empty_lines(sdir / "snaps.txt")
        npm = read_non_empty_lines(sdir / "npm-globals.txt")
        ext = read_non_empty_lines(sdir / "external.txt")
        gnome = read_non_empty_lines(sdir / "gnome-extensions.txt")
        skills = [
            parse_skill_frontmatter(sf, tdir)["name"]
            for sf in sorted((tdir / "antigravity/.gemini/config/skills").glob("*/SKILL.md"))
        ]
        docs_files = (
            [str(p.relative_to(tdir)) for p in sorted((tdir / "docs").rglob("*.md"))]
            if (tdir / "docs").is_dir()
            else []
        )
        ag_file = tdir / "antigravity/.gemini/config/AGENTS.md"
        ag_bytes = ag_file.stat().st_size if ag_file.is_file() else 0
        warnings = self.evaluate_layer_warnings(tdir, ag_bytes)
        ent_id = resolve_node_entity_identity(tdir, manifest)
        net_topo = discover_network_topology(tdir, manifest)
        cap_prof = resolve_mcp_capability_profile(
            manifest, active_ephemeral_forks=inspect_ephemeral_forks(tdir)["forks"]
        )
        mounted = self.discover_mounted_layers()
        digest = {
            "channel_1_node_and_system_state": {
                "version": read_version(tdir),
                "layer_id": manifest.get("layer_id"),
                "layer_role": str(manifest.get("layer_role") or "project"),
                "entity_identity": ent_id,
                "network_topology": net_topo["network_topology"],
                "node_connection_summary": net_topo["node_connection_summary"],
                "sync_topology": net_topo["sync_topology"],
                "runtime_orchestration": summarize_runtime_orchestration(tdir, manifest),
                "operating_state": ent_id["operating_state"],
                "mcp_operating_mode": ent_id["mcp_operating_mode"],
                "hostname": socket.gethostname(),
                "in_container": is_running_in_container(),
                "os_pretty_name": read_os_pretty_name(),
                "git_commit": read_git_commit(tdir),
                "manifest_counts": {
                    "apt_manual_packages": len(apt),
                    "snaps": len(snaps),
                    "npm_globals": len(npm),
                    "enabled_external_recipes": len(ext),
                    "gnome_extensions": len(gnome),
                },
            },
            "channel_2_governance_and_stack_contracts": {
                "global_profile": str(manifest.get("global_profile", "universal-base")),
                "human_stack": resolve_effective_human_stack(tdir, manifest),
                "global_skills_count": len(skills),
                "global_skills": skills,
                "stack_templates": discover_layer_template_names(tdir),
                "baseline_guardrails": manifest.get("baseline_guardrails", []),
            },
            "channel_3_active_invariants_and_hooks": {
                "agents_md_bytes": ag_bytes,
                "agents_md_estimated_tokens": ag_bytes // CHARS_PER_TOKEN_ESTIMATE,
                "agents_md_budget_cap_bytes": AGENTS_MD_MAX_BYTES,
                "agents_md_budget_utilization_pct": round(
                    (ag_bytes / AGENTS_MD_MAX_BYTES) * 100, 1
                ),
                "active_lifecycle_hooks": [
                    "PreToolUse (pre_tool_guard.py)",
                    "PostToolUse (post_edit_format.py)",
                    "PostInvocation (post_invocation_lint.py)",
                    "Stop (stop_verify_tests.py)",
                ],
                "mcp_security_mode": "strictly-read-only-path-contained",
                "context_compaction_protocol": "rcap1 (L0->L1->L2->L3 zlib+HMAC-SHA256)",
                "log_dir": str(self.log_dir) if self.log_dir else None,
                "warnings": warnings,
            },
            "channel_4_navigable_docs_and_federated_mcps": {
                "docs_index": "docs/README.md",
                "documents": docs_files,
                "mounted_layers": mounted,
                "deep_context_index": discover_deep_context_index(tdir, mounted),
                "supported_environments": list(manifest.get("environments", {}).keys()),
                "federated_mcps": manifest.get("federated_mcps", []),
                "oop_capability_inheritance": cap_prof["oop_capability_inheritance"],
                "permanent_ephemeral_symbiosis": cap_prof["permanent_ephemeral_symbiosis"],
            },
        }
        return {
            "content": [{"type": "text", "text": json.dumps(digest, indent=2)}],
            "isError": False,
        }

    def tool_audit_node_drift(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run deterministic read-only verification and/or system drift audit."""
        mode = str(args.get("mode", "verify-repo"))
        if mode not in ("verify-repo", "system-audit", "both"):
            raise ValueError(f"Invalid mode {mode!r}")
        env = {
            **os.environ,
            "NO_COLOR": "1",
            "LC_ALL": "C",
            "ZCG_NO_BROWSER": "1",
            "PYTHONPATH": str(REPO_DIR / "src"),
        }
        results: dict[str, Any] = {"mode": mode, "healthy": True, "checks": {}}
        cmds: list[tuple[str, list[str]]] = []
        if mode in ("verify-repo", "both"):
            v_sh = self.repo_dir / "scripts/verify-repo.sh"
            fb = [sys.executable, "-m", "zcg.cli.dispatcher", "diff-project", str(self.repo_dir)]
            cmds.append(("verify_repo", [str(v_sh)] if v_sh.is_file() else fb))
        if mode in ("system-audit", "both"):
            a_sh = self.repo_dir / "audit.sh"
            ws_sh = REPO_DIR / "scripts/workstation-audit.sh"
            is_ws = self.load_layer_manifest().get("layer_role") == "workstation"
            fb_a = [sys.executable, "-m", "zcg.cli.dispatcher", "status", str(self.repo_dir)]
            sys_cmd = (
                [str(a_sh)]
                if a_sh.is_file()
                else ([str(ws_sh), str(self.repo_dir)] if is_ws and ws_sh.is_file() else fb_a)
            )
            cmds.append(("system_audit", sys_cmd))
        for key, cmd in cmds:
            proc = subprocess.run(  # noqa: S603
                cmd,
                cwd=self.repo_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=AUDIT_CMD_TIMEOUT_SECONDS,
                check=False,
            )
            ok = proc.returncode == 0
            if not ok:
                results["healthy"] = False
            results["checks"][key] = {
                "exit_code": proc.returncode,
                "passed": ok,
                "output": ANSI_ESCAPE_RE.sub("", proc.stdout + proc.stderr).strip(),
            }
        results["warnings"] = (
            []
            if results["healthy"]
            else [
                self.emit_warning(
                    "WARN", "NODE_DRIFT_DETECTED", "Drift audit reported issues.", {"mode": mode}
                )
            ]
        )
        results["citation_lifecycle_radar"] = load_citation_telemetry_radar(self.repo_dir)
        return {
            "content": [{"type": "text", "text": json.dumps(results, indent=2)}],
            "isError": False,
        }

    def tool_read_layer_document(self, args: dict[str, Any]) -> dict[str, Any]:
        """Read a path-contained Markdown spec, rule, skill, or manifest file."""
        rel_p = str(args.get("relative_path", ""))
        tdir = self.resolve_layer_dir(args.get("layer"))
        br = str(args.get("branch_ref") or "").strip()
        content = (
            read_git_branch_document(tdir, rel_p, br)[0]
            if br
            else self.resolve_safe_path(rel_p, tdir).read_text(encoding="utf-8")
        )
        return {"content": [{"type": "text", "text": content}], "isError": False}

    def tool_discover_federated_mcps(self, args: dict[str, Any]) -> dict[str, Any]:
        """Discover downstream or sibling MCP servers and inherited guardrails."""
        root_m = self.load_layer_manifest()
        f_role = str(args.get("filter_role", "")).strip().lower()
        env_arg = str(args.get("environment", "")).strip().lower()
        if env_arg and env_arg not in VALID_ENVIRONMENTS:
            raise ValueError(f"Invalid environment {env_arg!r}")
        l_arg = str(args.get("layer", "all")).strip() or "all"
        tdirs = (
            [
                self.repo_dir,
                *(self.repo_dir / str(m["relative_path"]) for m in self.discover_mounted_layers()),
            ]
            if l_arg == "all"
            else [self.resolve_layer_dir(l_arg)]
        )
        act_prof = root_m.get("environments", {}).get(env_arg) if env_arg else None
        r_env_g = act_prof.get("default_guardrails", []) if isinstance(act_prof, dict) else []
        r_base, mcps = root_m.get("baseline_guardrails", []), list[dict[str, Any]]()
        for td in tdirs:
            tm = self.load_layer_manifest(td)
            lp = tm.get("environments", {}).get(env_arg) if env_arg else None
            if act_prof is None and isinstance(lp, dict):
                act_prof = lp
            l_eg = lp.get("default_guardrails", []) if isinstance(lp, dict) else []
            for rm in tm.get("federated_mcps", []):
                mc = {
                    "source_layer": tm.get("layer_id", td.name),
                    "activation_policy": "on-demand",
                    "when_to_invoke": "Invoke on demand when task requires this service.",
                    "avoid_when": "Avoid invoking when local repository files suffice.",
                    **dict(rm),
                }
                mc["effective_guardrails"] = merge_unique_strings(
                    r_base,
                    tm.get("baseline_guardrails", []),
                    r_env_g,
                    l_eg,
                    mc.get("required_guardrails", []),
                )
                mcps.append(mc)
        if f_role:
            mcps = [
                m
                for m in mcps
                if any(f_role in str(m.get(k, "")).lower() for k in ("role", "layer", "mcp_id"))
            ]
        if env_arg:
            mcps = [m for m in mcps if env_arg in m.get("environments", list(VALID_ENVIRONMENTS))]
        warns = (
            [
                self.emit_warning(
                    "WARN",
                    "MCP_FANOUT_WARNING",
                    f"Unfiltered discovery returned {len(mcps)} MCPs.",
                    {"returned_mcp_count": len(mcps)},
                )
            ]
            if (len(mcps) > MAX_RECOMMENDED_MCP_FANOUT and not f_role and not env_arg)
            else []
        )
        payload = {
            "layer_id": root_m.get("layer_id"),
            "layer_role": root_m.get("layer_role"),
            "upstream_layer": root_m.get("upstream_layer"),
            "queried_layer": l_arg,
            "active_environment": env_arg or "all",
            "environment_profile": act_prof,
            "mounted_layers": self.discover_mounted_layers(),
            "federated_mcp_count": len(mcps),
            "warnings": warns,
            "federated_mcps": mcps,
        }
        return {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "isError": False,
        }

    def tool_compare_layer_patterns(self, args: dict[str, Any]) -> dict[str, Any]:
        """Compare project rules/skills against layers for upward promotion or sync."""
        l_arg = str(args.get("layer", "all")).strip() or "all"
        mounted = self.discover_mounted_layers()
        if l_arg == "all":
            tdirs = [
                ("root", self.repo_dir, self.load_layer_manifest()),
                *(
                    (
                        str(m["name"]),
                        self.repo_dir / str(m["relative_path"]),
                        self.load_layer_manifest(self.repo_dir / str(m["relative_path"])),
                    )
                    for m in mounted
                ),
            ]
        else:
            td = self.resolve_layer_dir(l_arg)
            tdirs = [("root" if td == self.repo_dir else td.name, td, self.load_layer_manifest(td))]
        comp = compare_project_patterns_multilayer(
            self.repo_dir,
            mounted,
            project_rules=[str(r).strip() for r in args.get("project_rules", [])],
            project_skills=[str(s).strip() for s in args.get("project_skills", [])],
            target_dirs=tdirs,
        )
        return {"content": [{"type": "text", "text": json.dumps(comp, indent=2)}], "isError": False}
