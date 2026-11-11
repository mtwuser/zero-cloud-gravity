"""Unit tests for zcg.mcp.server.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

from zcg.capsules.constants import MCP_PAYLOAD_WARN_BYTES
from zcg.mcp.server import ZeroCloudMCPServer, main, run_self_test, run_stdio_loop


def _seed_server_repo(repo: Path) -> None:
    for d in ("system", "docs", "antigravity/.gemini/config"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (repo / "docs/README.md").write_text("# Docs\n## Core\nRule body.\n", encoding="utf-8")
    (repo / "antigravity/.gemini/config/AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo / "system/zcg-node.json").write_text(
        json.dumps(
            {
                "schema_version": "zcg-node-v1",
                "layer_id": "srv-node",
                "default_stack_templates": ["missing-tpl"],
            }
        ),
        encoding="utf-8",
    )


class TestMCPServer:
    """Verify ZeroCloudMCPServer JSON-RPC 2.0 dispatch, stdio framing, self-test, and CLI."""

    def test_handle_request_all_jsonrpc_methods_telemetry_and_errors(self, tmp_path: Path) -> None:
        """Dispatch all JSON-RPC methods, log compaction/large payloads, and handle errors."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_server_repo(repo)
        srv = ZeroCloudMCPServer(repo_dir=repo, log_dir=tmp_path / "logs")

        # Act
        notif = srv.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"})
        init_r = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        ping_r = srv.handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        r_list = srv.handle_request({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        rt_list = srv.handle_request(
            {"jsonrpc": "2.0", "id": 4, "method": "resources/templates/list"}
        )
        r_read = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "resources/read",
                "params": {"uri": "zcg://docs/index"},
            }
        )
        t_list = srv.handle_request({"jsonrpc": "2.0", "id": 6, "method": "tools/list"})
        p_list = srv.handle_request({"jsonrpc": "2.0", "id": 7, "method": "prompts/list"})
        p_get = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "prompts/get",
                "params": {"name": "orient-on-node"},
            }
        )
        ov_call = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "get_layer_overview", "arguments": {}},
            }
        )
        q_call = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "query_governance_rules",
                    "arguments": {"query": "rule body", "resolution": "L1"},
                },
            }
        )
        q_json = json.loads(q_call["result"]["content"][0]["text"])  # type: ignore[index]
        u_call = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "unfold_context_capsule",
                    "arguments": {"capsule_token": q_json["matches"][0]["capsule_token"]},
                },
            }
        )
        (repo / "docs/huge.md").write_text("x" * (MCP_PAYLOAD_WARN_BYTES + 500), encoding="utf-8")
        (repo / "docs/list.json").write_text("[1, 2, 3]\n", encoding="utf-8")
        srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {
                    "name": "read_layer_document",
                    "arguments": {"relative_path": "docs/list.json"},
                },
            }
        )
        huge_call = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "read_layer_document",
                    "arguments": {"relative_path": "docs/huge.md"},
                },
            }
        )
        cap_err = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {
                    "name": "unfold_context_capsule",
                    "arguments": {"capsule_token": "bad"},
                },
            }
        )
        val_err = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 14,
                "method": "tools/call",
                "params": {"name": "unknown_tool", "arguments": {}},
            }
        )
        not_found = srv.handle_request({"jsonrpc": "2.0", "id": 15, "method": "unknown/method"})
        with patch.object(srv, "list_prompts", side_effect=RuntimeError("boom")):
            int_err = srv.handle_request({"jsonrpc": "2.0", "id": 16, "method": "prompts/list"})

        # Assert
        assert notif is None
        assert init_r["result"]["serverInfo"]["name"] == "zcg-mcp"  # type: ignore[index]
        assert ping_r["result"] == {}  # type: ignore[index]
        assert len(r_list["result"]["resources"]) == 9  # type: ignore[index]
        assert rt_list["result"]["resourceTemplates"] == []  # type: ignore[index]
        assert "Docs" in r_read["result"]["contents"][0]["text"]  # type: ignore[index]
        assert len(t_list["result"]["tools"]) == 9  # type: ignore[index]
        assert len(p_list["result"]["prompts"]) == 3  # type: ignore[index]
        assert "messages" in p_get["result"]  # type: ignore[index]
        assert ov_call["result"]["isError"] is False  # type: ignore[index]
        assert u_call["result"]["isError"] is False  # type: ignore[index]
        assert huge_call["result"]["isError"] is False  # type: ignore[index]
        assert cap_err["error"]["code"] == -32602  # type: ignore[index]
        assert val_err["error"]["code"] == -32602  # type: ignore[index]
        assert not_found["error"]["code"] == -32601  # type: ignore[index]
        assert int_err["error"]["code"] == -32603  # type: ignore[index]

    def test_stdio_loop_self_test_and_cli_main(self, tmp_path: Path) -> None:
        """Serve line and Content-Length JSON-RPC frames, run self-test, and execute main."""
        # Arrange
        repo = tmp_path / "repo"
        _seed_server_repo(repo)
        srv = ZeroCloudMCPServer(repo_dir=repo)
        cl_body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}).encode("utf-8")
        raw_in = (
            b"\n"
            b"{invalid-json\n"
            b'{"jsonrpc":"2.0","method":"notify"}\n'
            b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
            + f"Content-Length: {len(cl_body)}\r\nX-Test: 1\r\n\r\n".encode("ascii")
            + cl_body
        )
        in_buf = io.BytesIO(raw_in)
        out_buf = io.BytesIO()

        # Act
        run_stdio_loop(srv, in_buf, out_buf)
        st = run_self_test(repo)
        rc_st = main(["--repo-dir", str(repo), "--self-test"])
        with patch("zcg.mcp.server.run_stdio_loop") as mock_loop:
            rc_stdio = main(["--repo-dir", str(repo)])

        # Assert
        out_text = out_buf.getvalue().decode("utf-8")
        assert "-32700" in out_text
        assert "Content-Length:" in out_text
        assert st["status"] == "ok"
        assert st["overview_ok"] is True
        assert rc_st == 0
        assert rc_stdio == 0
        mock_loop.assert_called_once()
