"""Unit tests for zcg.web.server.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
from pathlib import Path
from typing import Any

from zcg.web.channels import DeliveryChannel
from zcg.web.factory import create_web_app
from zcg.web.request import JSON_CONTENT_TYPE, Receive, Request, Scope, Send, WebResponse
from zcg.web.router import APIRouter
from zcg.web.security import CSRF_HEADER
from zcg.web.server import (
    MAX_HEADER_BLOCK_BYTES,
    _serve_app_until_stopped,
    handle_http_stream,
    main,
    serve_asgi_loopback,
)


async def _raw_tcp_exchange(port: int, payload: bytes) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(payload)
    await writer.drain()
    data = await reader.read()
    writer.close()
    await writer.wait_closed()
    return data


class TestServer:
    """Verify HTTP/1.1 -> ASGI loopback bridge, HTTP 286 wire framing, and standalone CLI."""

    def test_loopback_http_bridge_edge_cases_and_286_wire_framing_expected(self) -> None:
        """Verify live TCP HTTP/1.1 requests, 286 phrase, POST body, 400/431, and custom codes."""
        # Arrange
        tok = "srv-tok-1"
        rtr = APIRouter()

        @rtr.post("/ack", channel=DeliveryChannel.SWAP_SYNC)
        def _ack(req: Request) -> WebResponse:
            return WebResponse(200, JSON_CONTENT_TYPE, req.body, DeliveryChannel.SWAP_SYNC)

        app = create_web_app(routers=(rtr,), csrf_token=tok)

        async def _custom_app(scope: Scope, receive: Receive, send: Send) -> None:
            _ = await receive()
            disc = await receive()
            assert disc["type"] == "http.disconnect"
            await send({"type": "http.response.start", "status": 299, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": True})
            await send({"type": "http.response.body", "body": b"custom", "more_body": False})
            await send({"type": "http.noop"})

        async def _run() -> int:
            server, port = await serve_asgi_loopback(app, port=0)
            async with server:
                poll_req = (
                    b"GET /api/poll/status?done=1 HTTP/1.1\r\n"
                    b"Host: localhost\r\nX-Malformed\r\n\r\n"
                )
                r_poll = await _raw_tcp_exchange(port, poll_req)
                assert b"HTTP/1.1 286 Stop Polling\r\n" in r_poll

                body_b = b'{"ok":true}'
                req_post = (
                    f"POST /ack HTTP/1.1\r\nHost: localhost\r\n"
                    f"{CSRF_HEADER}: {tok}\r\nContent-Length: {len(body_b)}\r\n\r\n"
                ).encode("latin1") + body_b
                r_post = await _raw_tcp_exchange(port, req_post)
                assert b"HTTP/1.1 200 OK\r\n" in r_post and b'{"ok":true}' in r_post

                r_bad = await _raw_tcp_exchange(port, b"INVALID\r\n\r\n")
                assert b"HTTP/1.1 400 Bad Request" in r_bad

                huge = b"GET / HTTP/1.1\r\nX-Pad: " + (b"a" * MAX_HEADER_BLOCK_BYTES) + b"\r\n\r\n"
                r_431 = await _raw_tcp_exchange(port, huge)
                assert b"HTTP/1.1 431" in r_431

                _, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(b"POST / HTTP/1.1\r\nContent-Length: 50\r\n\r\nabc")
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            c_srv = await asyncio.start_server(
                lambda r, w: handle_http_stream(_custom_app, r, w), host="127.0.0.1", port=0
            )
            c_port = int(c_srv.sockets[0].getsockname()[1])
            async with c_srv:
                r_299 = await _raw_tcp_exchange(c_port, b"GET ?q=1 HTTP/1.1\r\n\r\n")
                assert b"HTTP/1.1 299 OK" in r_299 and r_299.endswith(b"custom")
            return port

        # Act
        bound_port = asyncio.run(_run())

        # Assert
        assert bound_port > 0

    def test_cli_main_self_test_and_graceful_stop_event_expected(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        """Verify main(--self-test) JSON output and graceful shutdown via stop_event."""
        # Arrange
        ws = tmp_path / "cli-web-node"
        ws.mkdir()

        async def _signal_stop_case() -> int:
            async def _send_sig() -> None:
                await asyncio.sleep(0.015)
                os.kill(os.getpid(), signal.SIGINT)

            t = asyncio.create_task(_send_sig())
            rc = await _serve_app_until_stopped(create_web_app(), "127.0.0.1", 0, None)
            await t
            return rc

        # Act
        rc_self = main(["--workspace", str(ws), "--self-test"])
        out_txt = capsys.readouterr().out
        rc_serve = main(["--workspace", str(ws), "--port", "0"], max_runtime_sec=0.01)
        rc_sig = asyncio.run(_signal_stop_case())

        # Assert
        assert rc_self == 0
        parsed = json.loads(out_txt)
        assert parsed["lifespan_events"] == 2
        assert parsed["healthz"]["protocol"] == "python314-native-asgi"
        assert rc_serve == 0
        assert rc_sig == 0
