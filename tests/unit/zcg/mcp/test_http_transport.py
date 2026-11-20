"""Unit tests for zcg.mcp.http_transport.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from zcg.mcp.http_transport import (
    MCP_SESSION_HEADER_LOWER,
    MCPSessionRegistry,
    _prefers_sse,
    create_mcp_asgi_app,
    run_mcp_http_server,
    verify_mcp_http_origin,
)
from zcg.mcp.server import ZeroCloudMCPServer
from zcg.web.auth.security import DocsAccessMode, WebAppError
from zcg.web.auth.tls import TLSTransportConfig
from zcg.web.http.request import Message, Scope


def _seed_mcp_repo(repo: Path) -> None:
    for d in ("system", "docs", "antigravity/.gemini/config"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "VERSION").write_text("1.1.0\n", encoding="utf-8")
    (repo / "docs/README.md").write_text("# Docs\n## Core\nBody.\n", encoding="utf-8")
    (repo / "antigravity/.gemini/config/AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo / "system/zcg-node.json").write_text(
        json.dumps({"schema_version": "zcg-node-v1", "layer_id": "mcp-http-node"}),
        encoding="utf-8",
    )


async def _mcp_req(
    app: Any,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, str], bytes]:
    raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": raw_h,
    }
    sent: list[Message] = []
    consumed = False

    async def receive() -> Message:
        nonlocal consumed
        chunk = b"" if consumed else body
        consumed = True
        return {"type": "http.request", "body": chunk, "more_body": False}

    async def send(msg: Message) -> None:
        sent.append(msg)

    await app(scope, receive, send)
    out_h = {
        bytes(k).decode("latin1").lower(): bytes(v).decode("latin1")
        for k, v in sent[0].get("headers", [])
    }
    out_b = b"".join(bytes(m.get("body", b"")) for m in sent[1:])
    return int(sent[0]["status"]), out_h, out_b


class TestMCPHttpTransport:
    """1:1 unit suite for MCP Streamable HTTP (/mcp) JSON-RPC 2.0, SSE, and Origin guards."""

    def test_verify_origin_and_session_registry_lifecycle_expected(self) -> None:
        """Verify DNS-rebinding Origin checks, SSE header preference, and FIFO session eviction."""
        # Arrange
        reg = MCPSessionRegistry(max_sessions=2)

        # Act
        verify_mcp_http_origin("")
        verify_mcp_http_origin("http://127.0.0.1:8799")
        verify_mcp_http_origin("http://portal.localhost:8799")
        verify_mcp_http_origin(
            "https://mcp.iso.example", allowed_origins=("https://mcp.iso.example", "not-a-url")
        )
        with pytest.raises(WebAppError) as exc_bad_host:
            verify_mcp_http_origin(
                "https://attacker.example", allowed_origins=("https://mcp.iso.example",)
            )
        with pytest.raises(WebAppError):
            verify_mcp_http_origin("ftp://invalid-scheme.example")

        s1 = reg.create_session()
        s2 = reg.create_session()
        s3 = reg.create_session()
        enq_miss = reg.enqueue_event(s1, {"method": "gone"})
        enq_hit = reg.enqueue_event(s2, {"jsonrpc": "2.0", "method": "notifications/progress"})
        drained_miss = reg.drain_events(s1)
        drained_hit = reg.drain_events(s2)
        term_miss = reg.terminate_session(s1)
        term_hit = reg.terminate_session(s3)

        # Assert
        assert exc_bad_host.value.error_code == "MCP_HTTP_ORIGIN_DENIED"
        assert reg.has_session(s1) is False and reg.has_session(s2) is True
        assert reg.active_count == 1
        assert enq_miss is False and enq_hit is True
        assert drained_miss == [] and len(drained_hit) == 1
        assert term_miss is False and term_hit is True
        assert _prefers_sse("application/json") is False
        assert _prefers_sse("text/event-stream") is True
        assert _prefers_sse("text/event-stream, application/json") is True
        assert _prefers_sse("application/json, text/event-stream") is False

    def test_streamable_http_post_get_delete_and_server_runner_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify POST/GET/DELETE /mcp across single, batch, SSE, session, and error paths."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_mcp_repo(repo)
        srv = ZeroCloudMCPServer(repo_dir=repo)
        reg = MCPSessionRegistry()
        app_stateless = create_mcp_asgi_app(srv)
        app_strict = create_mcp_asgi_app(srv, session_registry=reg, require_session=True)

        # Act
        async def _run_matrix() -> dict[str, tuple[int, dict[str, str], bytes]]:
            results: dict[str, tuple[int, dict[str, str], bytes]] = {}
            results["bad_json"] = await _mcp_req(app_strict, "POST", "/mcp", body=b"{bad")
            results["empty_batch"] = await _mcp_req(app_strict, "POST", "/mcp", body=b"[]")
            results["missing_sid_post"] = await _mcp_req(
                app_strict, "POST", "/mcp", body=b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
            )
            results["unknown_sid_post"] = await _mcp_req(
                app_strict,
                "POST",
                "/mcp",
                headers={MCP_SESSION_HEADER_LOWER: "unknown"},
                body=b'{"jsonrpc":"2.0","id":1,"method":"ping"}',
            )
            results["stateless_ping"] = await _mcp_req(
                app_stateless, "POST", "/mcp", body=b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
            )
            results["stateless_get"] = await _mcp_req(
                app_stateless, "GET", "/mcp", headers={"accept": "text/event-stream"}
            )
            init_res = await _mcp_req(
                app_strict, "POST", "/mcp", body=b'{"jsonrpc":"2.0","id":1,"method":"initialize"}'
            )
            results["init"] = init_res
            sid = init_res[1][MCP_SESSION_HEADER_LOWER]
            results["reinit_same_sid"] = await _mcp_req(
                app_strict,
                "POST",
                "/mcp",
                headers={MCP_SESSION_HEADER_LOWER: sid},
                body=b'{"jsonrpc":"2.0","id":2,"method":"initialize"}',
            )
            results["notif_202"] = await _mcp_req(
                app_strict,
                "POST",
                "/mcp",
                headers={MCP_SESSION_HEADER_LOWER: sid},
                body=b'{"jsonrpc":"2.0","method":"notifications/initialized"}',
            )
            batch_body = json.dumps(
                [
                    7,
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 3, "method": "ping"},
                ]
            ).encode("utf-8")
            results["batch"] = await _mcp_req(
                app_strict,
                "POST",
                "/mcp",
                headers={MCP_SESSION_HEADER_LOWER: sid},
                body=batch_body,
            )
            results["post_sse"] = await _mcp_req(
                app_strict,
                "POST",
                "/mcp",
                headers={MCP_SESSION_HEADER_LOWER: sid, "accept": "text/event-stream"},
                body=b'{"jsonrpc":"2.0","id":4,"method":"ping"}',
            )
            results["get_406"] = await _mcp_req(app_strict, "GET", "/mcp")
            results["get_missing_sid"] = await _mcp_req(
                app_strict, "GET", "/mcp", headers={"accept": "text/event-stream"}
            )
            results["get_unknown_sid"] = await _mcp_req(
                app_strict,
                "GET",
                "/mcp",
                headers={"accept": "text/event-stream", MCP_SESSION_HEADER_LOWER: "ghost"},
            )
            reg.enqueue_event(sid, {"jsonrpc": "2.0", "method": "notifications/message"})
            results["get_sse"] = await _mcp_req(
                app_strict,
                "GET",
                "/mcp",
                headers={"accept": "text/event-stream", MCP_SESSION_HEADER_LOWER: sid},
            )
            results["del_missing"] = await _mcp_req(app_strict, "DELETE", "/mcp")
            results["del_unknown"] = await _mcp_req(
                app_strict, "DELETE", "/mcp", headers={MCP_SESSION_HEADER_LOWER: "ghost"}
            )
            results["del_ok"] = await _mcp_req(
                app_strict, "DELETE", "/mcp", headers={MCP_SESSION_HEADER_LOWER: sid}
            )
            return results

        out = asyncio.run(_run_matrix())

        captured_argvs: list[list[str]] = []

        def _fake_cli(argv: list[str], *, app_builder: Any, max_runtime_sec: float | None) -> int:
            captured_argvs.append(list(argv))
            built = app_builder(repo, DocsAccessMode.PUBLIC)
            assert callable(built) and "--port" in argv and max_runtime_sec == 0.1
            return 0

        full_tls = TLSTransportConfig(
            certfile=repo / "c.pem",
            keyfile=repo / "k.pem",
            client_ca_file=repo / "ca.pem",
            behind_tls_proxy=True,
        )
        with patch("zcg.mcp.http_transport.run_server_cli", side_effect=_fake_cli):
            rc_srv = run_mcp_http_server(srv, port=8799, max_runtime_sec=0.1)
            rc_empty_tls = run_mcp_http_server(
                srv, port=8799, tls_config=TLSTransportConfig(), max_runtime_sec=0.1
            )
            rc_full_tls = run_mcp_http_server(
                srv, port=8799, tls_config=full_tls, max_runtime_sec=0.1
            )

        # Assert
        assert out["bad_json"][0] == 400 and out["empty_batch"][0] == 400
        assert out["missing_sid_post"][0] == 400 and out["unknown_sid_post"][0] == 404
        assert out["stateless_ping"][0] == 200
        assert MCP_SESSION_HEADER_LOWER not in out["stateless_ping"][1]
        assert out["stateless_get"][0] == 200
        assert out["init"][0] == 200 and out["reinit_same_sid"][0] == 200
        assert out["notif_202"][0] == 202 and out["notif_202"][2] == b""
        batch_parsed = json.loads(out["batch"][2])
        assert len(batch_parsed) == 2 and "error" in batch_parsed[0]
        assert out["post_sse"][0] == 200 and b"event: message" in out["post_sse"][2]
        assert out["get_406"][0] == 406
        assert out["get_missing_sid"][0] == 400 and out["get_unknown_sid"][0] == 404
        assert out["get_sse"][0] == 200 and b"notifications/message" in out["get_sse"][2]
        assert out["del_missing"][0] == 400 and out["del_unknown"][0] == 404
        assert out["del_ok"][0] == 204
        assert (rc_srv, rc_empty_tls, rc_full_tls) == (0, 0, 0)
        assert "--tls-certfile" in captured_argvs[2] and "--tls-client-ca" in captured_argvs[2]
        assert "--behind-tls-proxy" in captured_argvs[2]
