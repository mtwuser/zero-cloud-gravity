"""ZeroCloudMCPServer JSON-RPC 2.0 dispatcher, stdio transport loop, and CLI entrypoint.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from zcg.capsules.codec import CapsuleError
from zcg.capsules.constants import (
    CHARS_PER_TOKEN_ESTIMATE,
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    MCP_PAYLOAD_WARN_BYTES,
    MS_PER_SECOND,
)
from zcg.core.constants import MCP_JSONRPC_PROTOCOL_REV, REPO_DIR
from zcg.core.manifests import read_version
from zcg.mcp.catalogs import MCP_TOOLS_CATALOG
from zcg.mcp.orchestrator import EphemeralOrchestrationMixin


def _extract_result_json(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content")
    if isinstance(content, list) and content and isinstance(content[0], dict):
        with contextlib.suppress(ValueError, TypeError):
            parsed = json.loads(str(content[0].get("text", "")))
            if isinstance(parsed, dict):
                return parsed
    return {}


def _count_result_warnings(result: dict[str, Any]) -> int:
    data = _extract_result_json(result)
    if isinstance(warns := data.get("warnings"), list):
        return len(warns)
    ch3 = data.get("channel_3_active_invariants_and_hooks")
    return (
        len(ch3["warnings"])
        if isinstance(ch3, dict) and isinstance(ch3.get("warnings"), list)
        else 0
    )


def _extract_compaction_event_fields(target_name: str, result: dict[str, Any]) -> dict[str, Any]:
    data = _extract_result_json(result)
    if target_name in ("query_governance_rules", "resolve_surface_governance") and isinstance(
        m := data.get("token_compaction_metrics"), dict
    ):
        return {"resolution": m.get("resolution"), "tokens_saved": int(m.get("tokens_saved", 0))}
    if target_name == "unfold_context_capsule" and "unfolded_level" in data:
        return {
            "unfolded_level": data.get("unfolded_level"),
            "agent_tier": data.get("agent_tier", "inherit"),
            "decrypted_hops": int(data.get("decrypted_hops", 0)),
        }
    return {}


def _jsonrpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


class ZeroCloudMCPServer(EphemeralOrchestrationMixin):
    """Read-only MCP server exposing ZeroCloudGravity node, topology, and capsule context."""

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the catalog of MCP tools exposed by this Zero-Cloud Node."""
        return [dict(item) for item in MCP_TOOLS_CATALOG]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch an MCP tool invocation by name and return its structured JSON payload."""
        args, prev_dir = (arguments or {}), self.repo_dir
        self.repo_dir = self.resolve_workspace_override(args.get("workspace_dir"))
        try:
            dispatch = {
                "get_layer_overview": self.tool_get_layer_overview,
                "audit_node_drift": self.tool_audit_node_drift,
                "read_layer_document": self.tool_read_layer_document,
                "query_governance_rules": self.tool_query_governance_rules,
                "unfold_context_capsule": self.tool_unfold_context_capsule,
                "discover_federated_mcps": self.tool_discover_federated_mcps,
                "compare_layer_patterns": self.tool_compare_layer_patterns,
                "resolve_surface_governance": self.tool_resolve_surface_governance,
                "orchestrate_ephemeral_fork": self.tool_orchestrate_ephemeral_fork,
            }
            if name not in dispatch:
                raise ValueError(f"Unknown tool name: {name!r}")
            return dispatch[name](args)
        finally:
            self.repo_dir = prev_dir

    def handle_request(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single JSON-RPC 2.0 request message and return the response envelope."""
        method = str(message.get("method", ""))
        msg_id = message.get("id")
        params = message.get("params") or {}
        if msg_id is None:
            return None
        t0 = time.perf_counter()
        raw_args = params.get("arguments")
        tool_args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        logged_layer = str(tool_args.get("layer") or "root")
        logged_env = str(tool_args.get("environment") or "all")
        try:
            if method == "initialize":
                result: dict[str, Any] = {
                    "protocolVersion": MCP_JSONRPC_PROTOCOL_REV,
                    "capabilities": {
                        "resources": {"subscribe": False, "listChanged": False},
                        "tools": {"listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "serverInfo": {"name": "zcg-mcp", "version": read_version(self.repo_dir)},
                }
            elif method == "ping":
                result = {}
            elif method == "resources/list":
                result = {"resources": self.list_resources()}
            elif method == "resources/templates/list":
                result = {"resourceTemplates": []}
            elif method == "resources/read":
                result = {"contents": [self.read_resource(str(params.get("uri", "")))]}
            elif method == "tools/call":
                result = self.call_tool(str(params.get("name", "")), tool_args)
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "prompts/list":
                result = {"prompts": self.list_prompts()}
            elif method == "prompts/get":
                result = self.get_prompt(str(params.get("name", "")), tool_args)
            else:
                return _jsonrpc_error(
                    msg_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}"
                )
            dur = round((time.perf_counter() - t0) * MS_PER_SECOND, 2)
            resp: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "result": result}
            resp_bytes = len(json.dumps(resp).encode("utf-8"))
            warn_cnt = _count_result_warnings(result)
            if resp_bytes > MCP_PAYLOAD_WARN_BYTES:
                warn_cnt += 1
                self.emit_warning(
                    "WARN",
                    "LARGE_MCP_PAYLOAD_WARNING",
                    f"Response is {resp_bytes} bytes.",
                    {"method": method, "response_bytes": resp_bytes},
                )
            t_name = str(params.get("name") or params.get("uri") or method)
            self.write_jsonl(
                "mcp_events.jsonl",
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "method": method,
                    "target": t_name,
                    "layer": logged_layer,
                    "environment": logged_env,
                    "duration_ms": dur,
                    "status": "ok",
                    "response_bytes": resp_bytes,
                    "estimated_tokens": resp_bytes // CHARS_PER_TOKEN_ESTIMATE,
                    "warning_count": warn_cnt,
                    **_extract_compaction_event_fields(t_name, result),
                },
            )
            return resp
        except (ValueError, FileNotFoundError, KeyError) as exc:
            dur = round((time.perf_counter() - t0) * MS_PER_SECOND, 2)
            if not isinstance(exc, CapsuleError):
                self.emit_warning(
                    "WARN", "SECURITY_OR_VALIDATION_ERROR", str(exc), {"method": method}
                )
            self.write_jsonl(
                "mcp_events.jsonl",
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "method": method,
                    "target": str(params.get("name") or params.get("uri") or method),
                    "layer": logged_layer,
                    "environment": logged_env,
                    "duration_ms": dur,
                    "status": "error",
                    "warning_count": 1,
                    "error": str(exc),
                },
            )
            return _jsonrpc_error(msg_id, JSONRPC_INVALID_PARAMS, str(exc))
        except Exception as exc:
            return _jsonrpc_error(msg_id, JSONRPC_INTERNAL_ERROR, f"Internal error: {exc}")


def run_stdio_loop(
    server: ZeroCloudMCPServer,
    stdin_buf: BinaryIO | None = None,
    stdout_buf: BinaryIO | None = None,
) -> None:
    """Serve JSON-RPC 2.0 over stdio supporting line-delimited and Content-Length framing."""
    in_b, out_b = (stdin_buf or sys.stdin.buffer), (stdout_buf or sys.stdout.buffer)
    while True:
        first_line = in_b.readline()
        if not first_line:
            break
        stripped = first_line.strip()
        if not stripped:
            continue
        use_cl = stripped.lower().startswith(b"content-length:")
        if use_cl:
            length = int(stripped.split(b":", 1)[1].strip())
            while True:
                hdr = in_b.readline()
                if not hdr or hdr in (b"\r\n", b"\n"):
                    break
            raw_body = in_b.read(length)
        else:
            raw_body = stripped
        try:
            req = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            err = _jsonrpc_error(None, JSONRPC_PARSE_ERROR, f"Parse error: {exc}")
            out_b.write(json.dumps(err).encode("utf-8") + b"\n")
            out_b.flush()
            continue
        resp = server.handle_request(req)
        if resp is None:
            continue
        out_bytes = json.dumps(resp).encode("utf-8")
        if use_cl:
            out_b.write(f"Content-Length: {len(out_bytes)}\r\n\r\n".encode("ascii") + out_bytes)
        else:
            out_b.write(out_bytes + b"\n")
        out_b.flush()


def run_self_test(repo_dir: Path = REPO_DIR) -> dict[str, Any]:
    """Execute deterministic protocol self-test across resources, tools, prompts, and overview."""
    srv = ZeroCloudMCPServer(repo_dir=repo_dir)
    init_r = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) or {}
    ov_r = srv.call_tool("get_layer_overview", {})
    return {
        "status": "ok",
        "server": init_r.get("result", {}).get("serverInfo", {}),
        "resources_count": len(srv.list_resources()),
        "tools_count": len(srv.list_tools()),
        "prompts_count": len(srv.list_prompts()),
        "overview_ok": not ov_r.get("isError", True),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for zcg-mcp stdio server and --self-test diagnostics."""
    p = argparse.ArgumentParser(prog="zcg-mcp", description="ZeroCloudGravity MCP Server")
    p.add_argument("--repo-dir", type=Path, default=REPO_DIR)
    p.add_argument("--log-dir", type=Path, default=None)
    p.add_argument("--layer-id", default=None)
    p.add_argument("--layer-role", default=None)
    p.add_argument("--self-test", action="store_true")
    ns = p.parse_args(argv)
    if ns.self_test:
        sys.stdout.write(json.dumps(run_self_test(ns.repo_dir), indent=2) + "\n")
        return 0
    srv = ZeroCloudMCPServer(
        repo_dir=ns.repo_dir,
        layer_id_override=ns.layer_id,
        layer_role_override=ns.layer_role,
        log_dir=ns.log_dir,
    )
    run_stdio_loop(srv)
    return 0
