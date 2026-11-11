"""Zero-dependency asyncio HTTP/1.1 -> ASGI 3.0 loopback bridge and standalone server CLI.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import signal
import sys
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any

from zcg.core.constants import REPO_DIR
from zcg.web.channels import HTTP_POLL_STOP_STATUS
from zcg.web.factory import create_web_app
from zcg.web.request import ASGIApp, Message, Scope
from zcg.web.security import DocsAccessMode

MAX_HEADER_BLOCK_BYTES: int = 65_536
HTTP_POLL_STOP_PHRASE: str = "Stop Polling"


def _status_reason(status_code: int) -> str:
    if status_code == HTTP_POLL_STOP_STATUS:
        return HTTP_POLL_STOP_PHRASE
    with contextlib.suppress(ValueError):
        return HTTPStatus(status_code).phrase
    return "OK"


async def handle_http_stream(
    app: ASGIApp, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Bridge a single HTTP/1.1 loopback stream into an ASGI 3.0 application call."""
    try:
        try:
            raw_head = await reader.readuntil(b"\r\n\r\n")
        except asyncio.LimitOverrunError:
            writer.write(
                b"HTTP/1.1 431 Request Header Fields Too Large\r\nConnection: close\r\n\r\n"
            )
            await writer.drain()
            return
        head_lines = raw_head.decode("latin1").split("\r\n")
        parts = head_lines[0].split(" ")
        if len(parts) < 2:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return
        method, target = parts[0], parts[1]
        raw_path, _, query_str = target.partition("?")
        raw_headers: list[tuple[bytes, bytes]] = []
        content_len = 0
        for line in head_lines[1:]:
            if not line:
                continue
            hk, sep, hv = line.partition(":")
            if sep:
                clean_k, clean_v = hk.strip(), hv.strip()
                raw_headers.append((clean_k.lower().encode("latin1"), clean_v.encode("latin1")))
                if clean_k.lower() == "content-length" and clean_v.isdigit():
                    content_len = int(clean_v)
        body = await reader.readexactly(content_len) if content_len > 0 else b""
        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": raw_path or "/",
            "query_string": query_str.encode("latin1"),
            "headers": raw_headers,
        }
        body_sent = False

        async def receive() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(msg: Message) -> None:
            mtype = str(msg.get("type", ""))
            if mtype == "http.response.start":
                st = int(msg.get("status", 200))
                out_h = [f"HTTP/1.1 {st} {_status_reason(st)}"]
                for k, v in msg.get("headers", []):
                    out_h.append(f"{bytes(k).decode('latin1')}: {bytes(v).decode('latin1')}")
                out_h.append("connection: close")
                writer.write(("\r\n".join(out_h) + "\r\n\r\n").encode("latin1"))
                await writer.drain()
            elif mtype == "http.response.body":
                chunk = bytes(msg.get("body", b""))
                if chunk:
                    writer.write(chunk)
                    await writer.drain()

        await app(scope, receive, send)
    except (asyncio.IncompleteReadError, ConnectionError):
        return
    finally:
        writer.close()
        with contextlib.suppress(ConnectionError, OSError):
            await writer.wait_closed()


async def serve_asgi_loopback(
    app: ASGIApp,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[asyncio.AbstractServer, int]:
    """Start an asyncio loopback server bound to (host, port) for any ASGI 3.0 callable."""
    server = await asyncio.start_server(
        lambda r, w: handle_http_stream(app, r, w),
        host=host,
        port=port,
        limit=MAX_HEADER_BLOCK_BYTES,
    )
    bound_port = int(server.sockets[0].getsockname()[1])
    return server, bound_port


async def run_asgi_self_test(app: ASGIApp) -> dict[str, Any]:
    """Execute an in-memory ASGI lifespan + /healthz verification probe."""
    sent: list[Message] = []
    life_q = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def life_recv() -> Message:
        return life_q.pop(0)

    async def cap_send(m: Message) -> None:
        sent.append(m)

    await app({"type": "lifespan"}, life_recv, cap_send)
    http_sent: list[Message] = []

    async def http_recv() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def http_send(m: Message) -> None:
        http_sent.append(m)

    await app(
        {"type": "http", "method": "GET", "path": "/healthz", "query_string": b"", "headers": []},
        http_recv,
        http_send,
    )
    hz = json.loads(bytes(http_sent[1]["body"]).decode("utf-8"))
    return {"lifespan_events": len(sent), "healthz": hz}


async def _serve_app_until_stopped(
    app: ASGIApp,
    host: str,
    port: int,
    max_runtime_sec: float | None,
) -> int:
    stop_ev = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_ev.set)
    server, _ = await serve_asgi_loopback(app, host=host, port=port)
    async with server:
        if max_runtime_sec is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_ev.wait(), timeout=max_runtime_sec)
        else:
            await stop_ev.wait()
        getattr(server, "close_clients", server.close)()
    return 0


def _default_app_builder(workspace_dir: Path, docs_mode: DocsAccessMode) -> ASGIApp:
    return create_web_app(title=workspace_dir.resolve().name, docs_access_mode=docs_mode)


def run_server_cli(
    argv: list[str] | None = None,
    *,
    app_builder: Callable[[Path, DocsAccessMode], ASGIApp] | None = None,
    max_runtime_sec: float | None = None,
) -> int:
    """Shared CLI runner for standalone zcg.web apps and node cockpit daemons."""
    p = argparse.ArgumentParser(prog="zcg-web-asgi")
    p.add_argument("--workspace", type=Path, default=REPO_DIR)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8780)
    p.add_argument("--docs-mode", choices=DocsAccessMode.choices(), default="public")
    p.add_argument("--self-test", action="store_true")
    ns = p.parse_args(argv)
    mode = DocsAccessMode(ns.docs_mode)
    builder = app_builder or _default_app_builder
    app = builder(ns.workspace, mode)
    if ns.self_test:
        res = asyncio.run(run_asgi_self_test(app))
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        return 0
    return asyncio.run(_serve_app_until_stopped(app, ns.host, ns.port, max_runtime_sec))


def main(argv: list[str] | None = None, *, max_runtime_sec: float | None = None) -> int:
    """CLI entrypoint for standalone zcg.web Native ASGI servers."""
    return run_server_cli(argv, max_runtime_sec=max_runtime_sec)
