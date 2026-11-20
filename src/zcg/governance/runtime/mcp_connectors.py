"""Vendor-neutral governed external MCP connectors and Antigravity sidecar.json synthesis.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from zcg.core import constants
from zcg.core.manifests import load_node_manifest
from zcg.governance.policy.capabilities import (
    lint_skills_security,
    resolve_effective_capability_ceiling,
)
from zcg.governance.policy.egress import is_egress_host_allowed, resolve_effective_egress_policy
from zcg.governance.runtime.tool_catalog import (
    DEFAULT_EXTERNAL_MCP_CONNECTORS,
    OfficialMCPConnectorSpec,
)
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_governance_posture


def resolve_governed_mcp_connectors(
    target_dir: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
    parent_dir: Path | None = None,
    active_env: str = "dev",
    connector_catalog: Mapping[str, OfficialMCPConnectorSpec] | None = None,
) -> list[dict[str, Any]]:
    """Validate opt-in external MCP connectors against wallet airlock, allowlist, and egress."""
    ws = target_dir.resolve()
    m = dict(manifest) if manifest is not None else load_node_manifest(ws)
    raw_connectors = m.get("mcp_connectors")
    if not isinstance(raw_connectors, list) or not raw_connectors:
        return []

    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    posture = resolve_governance_posture(ws, m, parent_dir=eff_parent)
    is_wallet = posture.get("personal_pillar") == "wallet" or not bool(
        posture.get("allow_cross_workspace_1hop_read", True)
    )
    if is_wallet:
        raise ValueError(
            "WALLET_EXTERNAL_LINK_BLOCKED: R3 <persona>-wallet nodes forbid external MCP connectors"
        )

    skill_scan = lint_skills_security(ws, parent_dir=eff_parent)
    if not skill_scan["passed"]:
        raise ValueError(
            "SKILL_SECURITY_VIOLATION: workspace failed lint-skills gate prior to MCP activation"
        )

    ceiling = resolve_effective_capability_ceiling(ws, parent_dir=eff_parent)
    raw_cap = m.get("capability_policy")
    cap_map: Mapping[str, Any] = raw_cap if isinstance(raw_cap, Mapping) else {}
    allowed_override = (
        {str(x).strip() for x in cap_map["allowed_mcp_connectors"] if str(x).strip()}
        if isinstance(cap_map.get("allowed_mcp_connectors"), list)
        else set()
    )
    extra_blocked = (
        {str(x).strip().lower() for x in cap_map["blocked_operations"] if str(x).strip()}
        if isinstance(cap_map.get("blocked_operations"), list)
        else set()
    )
    blocked_ops = set(ceiling["blocked_operations"]) | extra_blocked
    egress = resolve_effective_egress_policy(ws, manifest=m, parent_dir=eff_parent)
    clean_env = active_env.strip().lower() or "dev"

    eff_catalog = (
        DEFAULT_EXTERNAL_MCP_CONNECTORS if connector_catalog is None else connector_catalog
    )
    resolved: list[dict[str, Any]] = []
    for item in raw_connectors:
        if not isinstance(item, Mapping):
            continue
        cid = str(item.get("connector_id") or "").strip()
        spec = eff_catalog.get(cid)
        if spec is None or (allowed_override and cid not in allowed_override):
            raise ValueError(f"MCP_CONNECTOR_NOT_ALLOWLISTED: connector {cid!r} is not permitted")
        if "activate" in blocked_ops:
            raise ValueError(
                f"CAPABILITY_CEILING_OPERATION_BLOCKED: MCP activation blocked for {cid!r}"
            )
        read_only = bool(item.get("read_only", True))
        if not read_only and clean_env == "pro" and not bool(item.get("allow_mutating_in_pro")):
            raise ValueError(
                f"MCP_CONNECTOR_WRITE_MODE_BLOCKED: {cid!r} requires read_only=true in pro"
            )
        endpoint_url = str(item.get("endpoint_url") or "").strip()
        if spec.transport == "streamable-http" or endpoint_url:
            parsed = urlsplit(endpoint_url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError(
                    f"UNAUTHORIZED_EGRESS_URL: invalid HTTPS endpoint {endpoint_url!r}"
                )
            if egress.egress_restricted and not is_egress_host_allowed(
                parsed.hostname, egress.allowed_domains
            ):
                raise ValueError(
                    f"UNAUTHORIZED_EGRESS_URL: endpoint host {parsed.hostname!r} blocked by egress"
                )
        resolved.append(
            {
                "connector_id": cid,
                "upstream_repo": spec.upstream_repo,
                "transport": spec.transport,
                "read_only": read_only,
                "auth_mode": "keyless-adc-or-oidc",
                "command": spec.command,
                "args": list(spec.default_args),
                "endpoint_url": endpoint_url or None,
            }
        )
    return resolved


def _discover_provisioned_tools(ws: Path) -> list[dict[str, Any]]:
    tools_root = ws / constants.TOOL_RUNTIME_REL_DIR
    if not tools_root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for rt_file in sorted(tools_root.glob("*/tool-runtime.json")):
        loaded = json.loads(rt_file.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and loaded.get("tool_id"):
            entries.append(
                {
                    "tool_id": str(loaded["tool_id"]),
                    "sandbox_driver": str(loaded.get("sandbox_driver") or "bwrap-readonly"),
                    "network_allowed": bool(loaded.get("network_allowed", False)),
                    "decision_backend": loaded.get("decision_backend"),
                }
            )
    return entries


def compile_antigravity_sidecar_manifest(
    target_dir: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
    parent_dir: Path | None = None,
    active_env: str = "dev",
    mcp_http_port: int | None = None,
    mcp_tls_enabled: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Synthesize .agents/sidecar.json supervising zcg-mcp, Cockpit ASGI, tools, and connectors."""
    ws = target_dir.resolve()
    m = dict(manifest) if manifest is not None else load_node_manifest(ws)
    lid = str(m.get("layer_id") or ws.name)
    lrole = str(m.get("layer_role") or "project")
    prec = int(m.get("precedence", constants.ROLE_DEFAULT_PRECEDENCE.get(lrole, 80)))
    c_port = int(m.get("cockpit_port") or (constants.DEFAULT_PLUGIN_BASE_PORT + prec))
    clean_env = active_env.strip().lower() or "dev"
    mcp_scheme = "https" if mcp_tls_enabled else "http"

    connectors = resolve_governed_mcp_connectors(
        ws, manifest=m, parent_dir=parent_dir, active_env=clean_env
    )
    mcp_daemon: dict[str, Any] = {
        "daemon_id": "zcg-mcp",
        "command": sys.executable,
        "args": (
            ["-m", "zcg.mcp.server", "--repo-dir", str(ws), "--http-port", str(mcp_http_port)]
            if mcp_http_port
            else ["-m", "zcg.mcp.server", "--repo-dir", str(ws)]
        ),
        "transport": "streamable-http" if mcp_http_port else "stdio",
        "endpoint": f"{mcp_scheme}://127.0.0.1:{mcp_http_port}/mcp" if mcp_http_port else None,
        "restart_policy": "on-failure",
        "graceful_stop_timeout_s": 10,
    }
    cockpit_daemon: dict[str, Any] = {
        "daemon_id": f"{lid}-cockpit",
        "transport": "http-asgi",
        "port": c_port,
        "healthcheck_url": f"http://127.0.0.1:{c_port}/healthz",
        "restart_policy": "on-failure",
        "graceful_stop_timeout_s": 10,
    }
    sidecar_doc: dict[str, Any] = {
        "schema_version": constants.SIDECAR_MANIFEST_CONTRACT_REV,
        "layer_id": lid,
        "environment": clean_env,
        "daemons": [mcp_daemon, cockpit_daemon],
        "isolated_tools": _discover_provisioned_tools(ws),
        "mcp_connectors": connectors,
    }
    if not dry_run:
        dest = ws / constants.SIDECAR_MANIFEST_REL_PATH
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(sidecar_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return sidecar_doc
