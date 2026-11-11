"""Base Zero-Cloud MCP node state, path containment, prompts, and zcg://* resources.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import contextlib
import json
import platform
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zcg.capsules.citations import summarize_mcp_diagnostics
from zcg.capsules.constants import (
    ALLOWED_READ_PREFIXES,
    ALLOWED_ROOT_FILES,
    MAX_LOG_FILE_BYTES,
)
from zcg.capsules.markdown import read_non_empty_lines
from zcg.core.constants import (
    AGENTS_MD_MAX_BYTES,
    AGENTS_MD_WARN_BYTES,
    NODE_MANIFEST_CONTRACT_REV,
    NODE_MANIFEST_REL_PATH,
    REPO_DIR,
    ROLE_DEFAULT_PRECEDENCE,
    VALID_KNOWLEDGE_PREFIXES,
)
from zcg.core.manifests import (
    discover_layer_template_names,
    discover_templates_catalog,
    is_running_in_container,
    parse_skill_frontmatter,
    read_git_commit,
    read_os_pretty_name,
    read_version,
    resolve_template_dir,
)
from zcg.ephemeral.lifecycle import inspect_ephemeral_forks
from zcg.mcp.catalogs import (
    MCP_PROMPTS_CATALOG,
    MCP_RESOURCES_CATALOG,
    resolve_mcp_capability_profile,
)


def _prompt_envelope(description: str, text: str) -> dict[str, Any]:
    return {
        "description": description,
        "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
    }


def _json_res(uri: str, payload: Any) -> dict[str, Any]:
    return {"uri": uri, "mimeType": "application/json", "text": json.dumps(payload, indent=2)}


class MCPNodeBase:
    """Core Zero-Cloud Node state, path-containment guard, prompt, and resource provider."""

    def __init__(
        self,
        repo_dir: Path = REPO_DIR,
        layer_id_override: str | None = None,
        layer_role_override: str | None = None,
        log_dir: Path | None = None,
    ) -> None:
        """Initialize the MCP node base with repository path, overrides, and ephemeral store."""
        self.repo_dir = repo_dir.resolve()
        self.layer_id_override = layer_id_override
        self.layer_role_override = layer_role_override
        self.log_dir = log_dir.resolve() if log_dir is not None else None
        self.ephemeral_memory_store: dict[str, dict[str, Any]] = {}

    def reap_expired_memory_forks(self, now_epoch: float | None = None) -> list[str]:
        """Evict expired in-memory ephemeral fork entries and return their fork IDs."""
        now = now_epoch if now_epoch is not None else datetime.now(UTC).timestamp()
        reaped: list[str] = []
        for fid in list(self.ephemeral_memory_store):
            if now >= float(self.ephemeral_memory_store[fid].get("expires_at_epoch", 0.0)):
                self.ephemeral_memory_store.pop(fid, None)
                reaped.append(fid)
        return reaped

    def write_jsonl(self, filename: str, record: dict[str, Any]) -> None:
        """Append a JSONL telemetry record to log_dir/<filename> with size-bounded rotation."""
        if self.log_dir is None:
            return
        with contextlib.suppress(OSError):
            self.log_dir.mkdir(parents=True, exist_ok=True)
            target = self.log_dir / filename
            if target.is_file() and target.stat().st_size >= MAX_LOG_FILE_BYTES:
                target.replace(self.log_dir / f"{filename}.1")
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")

    def emit_warning(
        self, severity: str, code: str, message: str, details: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Record and return a structured alert in mcp_alerts.jsonl."""
        alert = {
            "ts": datetime.now(UTC).isoformat(),
            "severity": severity,
            "code": code,
            "message": message,
            "details": details or {},
        }
        self.write_jsonl("mcp_alerts.jsonl", alert)
        return alert

    def evaluate_layer_warnings(self, target_dir: Path, agents_bytes: int) -> list[dict[str, Any]]:
        """Evaluate AGENTS.md token budget, missing templates, and subtree lineage warnings."""
        warnings: list[dict[str, Any]] = []
        cap_meta = {"agents_md_bytes": agents_bytes, "cap_bytes": AGENTS_MD_MAX_BYTES}
        if agents_bytes > AGENTS_MD_MAX_BYTES:
            msg = f"AGENTS.md is {agents_bytes} bytes (exceeds {AGENTS_MD_MAX_BYTES}-byte cap)."
            warnings.append(self.emit_warning("CRITICAL", "TOKEN_BUDGET_EXCEEDED", msg, cap_meta))
        elif agents_bytes >= AGENTS_MD_WARN_BYTES:
            msg = f"AGENTS.md is {agents_bytes} bytes (>= {AGENTS_MD_WARN_BYTES}-byte warn cap)."
            warnings.append(self.emit_warning("WARN", "TOKEN_BUDGET_NEAR_LIMIT", msg, cap_meta))
        for tpl_name in self.load_layer_manifest(target_dir).get("default_stack_templates", []):
            if resolve_template_dir(target_dir, str(tpl_name)) is None:
                msg = f"Configured default_stack_templates entry {tpl_name!r} not found."
                warnings.append(
                    self.emit_warning("WARN", "TEMPLATE_PACK_MISSING", msg, {"template": tpl_name})
                )
        if target_dir == self.repo_dir:
            for entry in self.discover_mounted_layers():
                if not entry["has_upstream"]:
                    msg = f"Mounted subtree {entry['relative_path']!r} lacks upstream_layer."
                    meta = {"layer": entry["name"]}
                    warnings.append(self.emit_warning("WARN", "SUBTREE_LINEAGE_WARNING", msg, meta))
        return warnings

    def load_layer_manifest(self, target_dir: Path | None = None) -> dict[str, Any]:
        """Load and validate <target_dir>/system/zcg-node.json with workstation defaults."""
        base_dir = (target_dir or self.repo_dir).resolve()
        manifest_path = base_dir / NODE_MANIFEST_REL_PATH
        is_root = base_dir == self.repo_dir
        def_prec = ROLE_DEFAULT_PRECEDENCE["workstation" if is_root else "service-node"]
        def_role = (
            "knowledge"
            if (not is_root and base_dir.name.startswith(VALID_KNOWLEDGE_PREFIXES))
            else "workstation"
        )
        defaults: dict[str, Any] = {
            "schema_version": NODE_MANIFEST_CONTRACT_REV,
            "layer_id": "zero-cloud-gravity-workstation" if is_root else base_dir.name,
            "layer_role": def_role,
            "precedence": def_prec,
            "description": "Zero-Cloud Antigravity Sovereign Node",
            "upstream_layer": {
                "layer_id": "mtwuser/zero-cloud-gravity",
                "repository": "https://github.com/mtwuser/zero-cloud-gravity.git",
                "branch": "master",
            },
            "mounted_layers_dir": "layers",
            "mounted_layers": [],
            "default_stack_templates": discover_layer_template_names(base_dir),
            "baseline_guardrails": [],
            "surface_bindings": [],
            "environments": {},
            "federated_mcps": [],
        }
        loaded = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        )
        data: dict[str, Any] = {**defaults, **(loaded if isinstance(loaded, dict) else {})}
        if str(data.get("schema_version")) != NODE_MANIFEST_CONTRACT_REV:
            raise ValueError(
                f"Unsupported zcg-node.json schema_version {data.get('schema_version')!r}"
            )
        if is_root:
            if self.layer_id_override:
                data["layer_id"] = self.layer_id_override
            if self.layer_role_override:
                data["layer_role"] = self.layer_role_override
        return data

    def discover_mounted_layers(self) -> list[dict[str, Any]]:
        """Discover mounted subtrees under repo_dir/layers sorted by precedence."""
        layers_dir = self.repo_dir / "layers"
        if not layers_dir.is_dir():
            return []
        discovered: list[dict[str, Any]] = []
        for sub in sorted(layers_dir.iterdir()):
            if not sub.is_dir() or sub.name.startswith("."):
                continue
            raw_m, has_upstream = sub / NODE_MANIFEST_REL_PATH, True
            if raw_m.is_file():
                raw_d = json.loads(raw_m.read_text(encoding="utf-8"))
                if isinstance(raw_d, dict) and "upstream_layer" in raw_d:
                    up = raw_d.get("upstream_layer")
                    has_upstream = bool(isinstance(up, dict) and up.get("repository"))
            sub_m = self.load_layer_manifest(sub)
            def_sp = ROLE_DEFAULT_PRECEDENCE["service-node"]
            discovered.append(
                {
                    "name": sub.name,
                    "relative_path": f"layers/{sub.name}",
                    "layer_id": sub_m.get("layer_id", sub.name),
                    "layer_role": sub_m.get("layer_role", "service-node"),
                    "precedence": int(sub_m.get("precedence", def_sp)),
                    "surface_binding_count": len(sub_m.get("surface_bindings", [])),
                    "version": read_version(sub),
                    "has_docs": (sub / "docs").is_dir(),
                    "has_rules": (sub / "antigravity/.gemini/config/AGENTS.md").is_file(),
                    "has_templates": (sub / "templates").is_dir(),
                    "has_upstream": has_upstream,
                    "federated_mcp_count": len(sub_m.get("federated_mcps", [])),
                }
            )
        discovered.sort(key=lambda item: (int(item["precedence"]), str(item["name"])))
        return discovered

    def resolve_workspace_override(self, workspace_dir: object) -> Path:
        """Resolve an optional per-call workspace_dir override to an existing node/git root."""
        raw = str(workspace_dir or "").strip()
        if not raw:
            return self.repo_dir
        cand = Path(raw).expanduser().resolve()
        has_marker = (
            (cand / NODE_MANIFEST_REL_PATH).is_file()
            or (cand / ".agents").is_dir()
            or (cand / ".git").exists()
        )
        if not cand.is_dir() or not has_marker:
            raise ValueError(f"Invalid workspace_dir {raw!r}: must be a Zero-Cloud workspace.")
        return cand

    def resolve_layer_dir(self, layer: str | None = None) -> Path:
        """Resolve 'root', 'self', root layer_id, or a mounted subtree name to its Path."""
        clean = (layer or "").strip()
        root_id = str(self.load_layer_manifest().get("layer_id", ""))
        if not clean or clean in ("root", "self", root_id):
            return self.repo_dir
        for entry in self.discover_mounted_layers():
            if clean in (entry["name"], entry["layer_id"]):
                return (self.repo_dir / str(entry["relative_path"])).resolve()
        raise ValueError(f"Unknown or unmounted layer: {layer!r}")

    def validate_safe_rel_path(
        self, relative_path: str, base_dir: Path | None = None
    ) -> tuple[Path, Path, str]:
        """Enforce workspace path containment and readable prefix allowlist."""
        target_base = (base_dir or self.repo_dir).resolve()
        clean_rel = relative_path.strip().lstrip("/")
        if not clean_rel or ".." in Path(clean_rel).parts:
            raise ValueError(f"PATH_CONTAINMENT_VIOLATION: Invalid relative path {relative_path!r}")
        cand = (target_base / clean_rel).resolve()
        if not cand.is_relative_to(target_base):
            raise ValueError(f"PATH_CONTAINMENT_VIOLATION: Path escapes root: {relative_path!r}")
        rel_str = str(cand.relative_to(target_base)).replace("\\", "/")
        if rel_str not in ALLOWED_ROOT_FILES and not any(
            rel_str.startswith(p) for p in ALLOWED_READ_PREFIXES
        ):
            raise ValueError(f"Access denied for {relative_path!r}: outside readable surfaces.")
        return target_base, cand, rel_str

    def resolve_safe_path(self, relative_path: str, base_dir: Path | None = None) -> Path:
        """Resolve a safe relative file path and raise FileNotFoundError when absent."""
        _, cand, rel_str = self.validate_safe_rel_path(relative_path, base_dir)
        if not cand.is_file():
            raise FileNotFoundError(f"Document not found: {rel_str}")
        return cand

    def list_prompts(self) -> list[dict[str, Any]]:
        """Return the catalog of MCP prompts exposed by this Zero-Cloud Node."""
        return [dict(item) for item in MCP_PROMPTS_CATALOG]

    def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render a structured MCP prompt message sequence for the requested prompt name."""
        args = arguments or {}
        if name == "orient-on-node":
            task = args.get("task_description", "general architectural exploration")
            return _prompt_envelope(
                f"Orientation for: {task}",
                f"Task: {task}\n1. Call `get_layer_overview`.\n2. Read `zcg://docs/index`.",
            )
        if name == "audit-container-or-node":
            svc = args.get("target_service", "current node")
            return _prompt_envelope(
                f"Drift audit for {svc}",
                f"Audit `{svc}` via `audit_node_drift(mode='both')` and `zcg://node/identity`.",
            )
        if name == "orchestrate-federated-mcps":
            goal = args.get("workflow_goal", "multi-service operation")
            env_s, lyr_s = args.get("environment", "pre"), args.get("layer", "all")
            body = f"Goal: {goal}\nCall `discover_federated_mcps` ({lyr_s!r}, {env_s!r})."
            return _prompt_envelope(f"MCP orchestration: {goal}", body)
        raise ValueError(f"Unknown prompt name: {name!r}")

    def list_resources(self) -> list[dict[str, Any]]:
        """Return the catalog of read-only zcg://* MCP resources exposed by this node."""
        return [dict(item) for item in MCP_RESOURCES_CATALOG]

    def read_resource(self, uri: str) -> dict[str, Any]:
        """Read and serialize the requested zcg://* resource URI."""
        if uri == "zcg://node/identity":
            m = self.load_layer_manifest()
            return _json_res(
                uri,
                {
                    "version": read_version(self.repo_dir),
                    "layer_id": m.get("layer_id"),
                    "layer_role": m.get("layer_role"),
                    "description": m.get("description", ""),
                    "hostname": socket.gethostname(),
                    "in_container": is_running_in_container(),
                    "os_pretty_name": read_os_pretty_name(),
                    "python_version": platform.python_version(),
                    "git_commit": read_git_commit(self.repo_dir),
                    "repo_path": str(self.repo_dir),
                    "upstream_layer": m.get("upstream_layer", {}),
                },
            )
        if uri == "zcg://system/manifests":
            sdir = self.repo_dir / "system"
            apt = read_non_empty_lines(sdir / "packages-manual.txt")
            snaps = read_non_empty_lines(sdir / "snaps.txt")
            npm = read_non_empty_lines(sdir / "npm-globals.txt")
            nvm = read_non_empty_lines(sdir / "nvm-default.txt")
            ext = read_non_empty_lines(sdir / "external.txt")
            gnome = read_non_empty_lines(sdir / "gnome-extensions.txt")
            return _json_res(
                uri,
                {
                    "counts": {
                        "apt_manual_packages": len(apt),
                        "snaps": len(snaps),
                        "npm_globals": len(npm),
                        "enabled_external_recipes": len(ext),
                        "gnome_extensions": len(gnome),
                    },
                    "nvm_default": nvm[0] if nvm else "none",
                    "apt_manual_packages": apt,
                    "snaps": snaps,
                    "npm_globals": npm,
                    "enabled_external_recipes": ext,
                    "gnome_extensions": gnome,
                },
            )
        if uri == "zcg://governance/rules":
            p = self.repo_dir / "antigravity/.gemini/config/AGENTS.md"
            return {"uri": uri, "mimeType": "text/markdown", "text": p.read_text(encoding="utf-8")}
        if uri == "zcg://governance/hooks":
            p = self.repo_dir / "antigravity/.gemini/config/hooks.json"
            return {
                "uri": uri,
                "mimeType": "application/json",
                "text": p.read_text(encoding="utf-8"),
            }
        if uri == "zcg://governance/skills":
            s_glob = (self.repo_dir / "antigravity/.gemini/config/skills").glob("*/SKILL.md")
            skills = [parse_skill_frontmatter(sf, self.repo_dir) for sf in sorted(s_glob)]
            return _json_res(uri, {"count": len(skills), "skills": skills})
        if uri == "zcg://governance/templates":
            cat = discover_templates_catalog(self.repo_dir, self.discover_mounted_layers())
            return _json_res(uri, {"count": len(cat), "templates": cat})
        if uri == "zcg://docs/index":
            p = self.repo_dir / "docs/README.md"
            return {"uri": uri, "mimeType": "text/markdown", "text": p.read_text(encoding="utf-8")}
        if uri == "zcg://mcp/topology":
            m = self.load_layer_manifest()
            m["discovered_mounted_layers"] = self.discover_mounted_layers()
            m["capability_profile"] = resolve_mcp_capability_profile(
                m, active_ephemeral_forks=inspect_ephemeral_forks(self.repo_dir)["forks"]
            )
            return _json_res(uri, m)
        if uri == "zcg://mcp/diagnostics":
            return _json_res(uri, summarize_mcp_diagnostics(self.log_dir, self.repo_dir))
        raise ValueError(f"Unknown resource URI: {uri!r}")
