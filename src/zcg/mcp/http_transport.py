"""Native MCP Streamable HTTP (/mcp) JSON-RPC 2.0 and SSE transport over zcg.web.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from zcg.capsules.constants import JSONRPC_PARSE_ERROR
from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.auth.tls import TLSTransportConfig
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.factory import create_web_app
from zcg.web.http.request import JSON_CONTENT_TYPE, ASGIApp, Request, WebResponse
from zcg.web.http.router import APIRouter
from zcg.web.http.server import run_server_cli

if TYPE_CHECKING:
    from zcg.mcp.server import ZeroCloudMCPServer

SSE_CONTENT_TYPE: Final[str] = "text/event-stream; charset=utf-8"
MCP_SESSION_HEADER_LOWER: Final[str] = "mcp-session-id"
MCP_SESSION_HEADER_CANONICAL: Final[str] = "Mcp-Session-Id"
MAX_ACTIVE_MCP_SESSIONS: Final[int] = 256
JSONRPC_INVALID_REQUEST: Final[int] = -32600
SESSION_TOKEN_BYTES: Final[int] = 24
LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})


def _normalize_origin(raw: str) -> str:
    parsed = urlsplit(raw.strip())
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc.lower()}"
    return ""


def verify_mcp_http_origin(origin_header: str, *, allowed_origins: Sequence[str] = ()) -> None:
    """Enforce DNS-rebinding protection on MCP Streamable HTTP requests."""
    cleaned = origin_header.strip()
    if not cleaned:
        return
    parsed = urlsplit(cleaned)
    host = (parsed.hostname or "").lower()
    is_loopback = parsed.scheme in ("http", "https") and (
        host in LOOPBACK_HOSTS or host.endswith(".localhost")
    )
    if is_loopback:
        return
    norm_cand = _normalize_origin(cleaned)
    allowed_set = {_normalize_origin(o) for o in allowed_origins if _normalize_origin(o)}
    if norm_cand and norm_cand in allowed_set:
        return
    raise WebAppError(
        f"Untrusted MCP HTTP Origin {cleaned!r}",
        error_code="MCP_HTTP_ORIGIN_DENIED",
        http_status=int(HTTPStatus.FORBIDDEN),
        severity=ErrorSeverity.WARNING,
        action=ErrorAction.FIX_INPUT,
    )


class MCPSessionRegistry:
    """Bounded in-memory session and server-event queue registry for Streamable HTTP."""

    def __init__(self, *, max_sessions: int = MAX_ACTIVE_MCP_SESSIONS) -> None:
        self._max_sessions = max(1, max_sessions)
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    @property
    def active_count(self) -> int:
        """Return number of currently active MCP HTTP sessions."""
        return len(self._sessions)

    def create_session(self) -> str:
        """Mint a new cryptographic Mcp-Session-Id, evicting oldest if at capacity."""
        if len(self._sessions) >= self._max_sessions:
            oldest = next(iter(self._sessions))
            del self._sessions[oldest]
        sid = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        self._sessions[sid] = []
        return sid

    def has_session(self, session_id: str) -> bool:
        """Return True when session_id is active."""
        return session_id in self._sessions

    def enqueue_event(self, session_id: str, payload: Mapping[str, Any]) -> bool:
        """Queue an outbound JSON-RPC notification or message for GET /mcp SSE delivery."""
        queue = self._sessions.get(session_id)
        if queue is None:
            return False
        queue.append(dict(payload))
        return True

    def drain_events(self, session_id: str) -> list[dict[str, Any]]:
        """Pop and return all queued SSE events for session_id."""
        queue = self._sessions.get(session_id)
        if queue is None:
            return []
        drained = list(queue)
        queue.clear()
        return drained

    def terminate_session(self, session_id: str) -> bool:
        """Remove session_id from registry, returning True if it was active."""
        return self._sessions.pop(session_id, None) is not None


def _prefers_sse(accept_header: str) -> bool:
    low = accept_header.lower()
    if "text/event-stream" not in low:
        return False
    if "application/json" not in low:
        return True
    return low.index("text/event-stream") < low.index("application/json")


def _format_sse_messages(items: Sequence[Mapping[str, Any]]) -> bytes:
    frames = [f"event: message\ndata: {json.dumps(item)}\n\n" for item in items]
    return "".join(frames).encode("utf-8")


def _json_error_response(status: int, code: int, message: str) -> WebResponse:
    err = {"jsonrpc": "2.0", "id": None, "error": {"code": code, "message": message}}
    return WebResponse(
        status, JSON_CONTENT_TYPE, json.dumps(err).encode("utf-8"), DeliveryChannel.ISLAND_SYNC
    )


def create_mcp_http_router(
    server: ZeroCloudMCPServer,
    *,
    allowed_origins: Sequence[str] = (),
    session_registry: MCPSessionRegistry | None = None,
    require_session: bool = False,
) -> APIRouter:
    """Create MCP Streamable HTTP router exposing POST, GET, and DELETE on /mcp."""
    reg = session_registry if session_registry is not None else MCPSessionRegistry()
    router = APIRouter(tags=("mcp-streamable-http",))

    def _handle_post(request: Request) -> WebResponse:
        verify_mcp_http_origin(request.headers.get("origin", ""), allowed_origins=allowed_origins)
        try:
            decoded = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _json_error_response(
                int(HTTPStatus.BAD_REQUEST), JSONRPC_PARSE_ERROR, f"Parse error: {exc}"
            )
        is_batch = isinstance(decoded, list)
        if not isinstance(decoded, (dict, list)) or (is_batch and not decoded):
            return _json_error_response(
                int(HTTPStatus.BAD_REQUEST),
                JSONRPC_INVALID_REQUEST,
                "Expected JSON-RPC object or non-empty batch array",
            )
        batch_items: list[Any] = decoded if isinstance(decoded, list) else [decoded]
        has_init = any(
            isinstance(it, dict) and it.get("method") == "initialize" for it in batch_items
        )
        sid = request.headers.get(MCP_SESSION_HEADER_LOWER, "").strip()
        if sid and not reg.has_session(sid):
            return _json_error_response(
                int(HTTPStatus.NOT_FOUND), JSONRPC_INVALID_REQUEST, "Unknown Mcp-Session-Id"
            )
        if not sid and require_session and not has_init:
            return _json_error_response(
                int(HTTPStatus.BAD_REQUEST), JSONRPC_INVALID_REQUEST, "Missing Mcp-Session-Id"
            )

        responses: list[dict[str, Any]] = []
        for item in batch_items:
            if not isinstance(item, dict):
                responses.append(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": JSONRPC_INVALID_REQUEST, "message": "Invalid item"},
                    }
                )
                continue
            out = server.handle_request(item)
            if out is not None:
                responses.append(out)

        eff_sid = reg.create_session() if (has_init and not sid) else sid
        resp_hdrs = {MCP_SESSION_HEADER_CANONICAL: eff_sid} if eff_sid else {}
        if not responses:
            return WebResponse(
                int(HTTPStatus.ACCEPTED),
                JSON_CONTENT_TYPE,
                b"",
                DeliveryChannel.ISLAND_SYNC,
                resp_hdrs,
            )
        if _prefers_sse(request.headers.get("accept", "")):
            return WebResponse(
                int(HTTPStatus.OK),
                SSE_CONTENT_TYPE,
                _format_sse_messages(responses),
                DeliveryChannel.ISLAND_STREAM,
                {"cache-control": "no-cache", **resp_hdrs},
            )
        out_payload: Any = responses if is_batch else responses[0]
        return WebResponse(
            int(HTTPStatus.OK),
            JSON_CONTENT_TYPE,
            json.dumps(out_payload).encode("utf-8"),
            DeliveryChannel.ISLAND_SYNC,
            resp_hdrs,
        )

    def _handle_get(request: Request) -> WebResponse:
        verify_mcp_http_origin(request.headers.get("origin", ""), allowed_origins=allowed_origins)
        if "text/event-stream" not in request.headers.get("accept", "").lower():
            return _json_error_response(
                int(HTTPStatus.NOT_ACCEPTABLE),
                JSONRPC_INVALID_REQUEST,
                "GET /mcp requires Accept: text/event-stream",
            )
        sid = request.headers.get(MCP_SESSION_HEADER_LOWER, "").strip()
        if sid and not reg.has_session(sid):
            return _json_error_response(
                int(HTTPStatus.NOT_FOUND), JSONRPC_INVALID_REQUEST, "Unknown Mcp-Session-Id"
            )
        if not sid and require_session:
            return _json_error_response(
                int(HTTPStatus.BAD_REQUEST), JSONRPC_INVALID_REQUEST, "Missing Mcp-Session-Id"
            )
        queued = reg.drain_events(sid) if sid else []
        endpoint_evt = 'event: endpoint\ndata: {"transport":"streamable-http","path":"/mcp"}\n\n'
        raw_sse = endpoint_evt.encode("utf-8") + _format_sse_messages(queued)
        hdrs = {"cache-control": "no-cache"}
        if sid:
            hdrs[MCP_SESSION_HEADER_CANONICAL] = sid
        return WebResponse(
            int(HTTPStatus.OK), SSE_CONTENT_TYPE, raw_sse, DeliveryChannel.ISLAND_STREAM, hdrs
        )

    def _handle_delete(request: Request) -> WebResponse:
        verify_mcp_http_origin(request.headers.get("origin", ""), allowed_origins=allowed_origins)
        sid = request.headers.get(MCP_SESSION_HEADER_LOWER, "").strip()
        if not sid:
            return _json_error_response(
                int(HTTPStatus.BAD_REQUEST), JSONRPC_INVALID_REQUEST, "Missing Mcp-Session-Id"
            )
        if not reg.terminate_session(sid):
            return _json_error_response(
                int(HTTPStatus.NOT_FOUND), JSONRPC_INVALID_REQUEST, "Unknown Mcp-Session-Id"
            )
        return WebResponse(
            int(HTTPStatus.NO_CONTENT), JSON_CONTENT_TYPE, b"", DeliveryChannel.ISLAND_SYNC
        )

    router.add_route(
        "POST", "/mcp", _handle_post, channel=DeliveryChannel.ISLAND_SYNC,
        summary="Dispatch MCP JSON-RPC 2.0 single or batch request over Streamable HTTP",
    )  # fmt: skip
    router.add_route(
        "GET", "/mcp", _handle_get, channel=DeliveryChannel.ISLAND_STREAM,
        summary="Open MCP Server-Sent Events (SSE) stream",
    )  # fmt: skip
    router.add_route(
        "DELETE", "/mcp", _handle_delete, channel=DeliveryChannel.ISLAND_SYNC,
        summary="Terminate active Mcp-Session-Id",
    )  # fmt: skip
    return router


def create_mcp_asgi_app(
    server: ZeroCloudMCPServer,
    *,
    allowed_origins: Sequence[str] = (),
    session_registry: MCPSessionRegistry | None = None,
    require_session: bool = False,
) -> ASGIApp:
    """Build standalone Native ASGI application serving MCP Streamable HTTP at /mcp."""
    mcp_router = create_mcp_http_router(
        server,
        allowed_origins=allowed_origins,
        session_registry=session_registry,
        require_session=require_session,
    )
    return create_web_app(title="ZeroCloudGravity MCP Server", routers=(mcp_router,))


def run_mcp_http_server(
    server: ZeroCloudMCPServer,
    *,
    host: str = "127.0.0.1",
    port: int = 8799,
    allowed_origins: Sequence[str] = (),
    tls_config: TLSTransportConfig | None = None,
    max_runtime_sec: float | None = None,
) -> int:
    """Run ZeroCloudMCPServer over Streamable HTTP/HTTPS (/mcp) using Native ASGI."""
    app = create_mcp_asgi_app(server, allowed_origins=allowed_origins)
    cli_args = ["--host", host, "--port", str(port)]
    if tls_config is not None:
        if tls_config.certfile is not None and tls_config.keyfile is not None:
            cli_args.extend(
                [
                    "--tls-certfile",
                    str(tls_config.certfile),
                    "--tls-keyfile",
                    str(tls_config.keyfile),
                ]
            )
        if tls_config.client_ca_file is not None:
            cli_args.extend(["--tls-client-ca", str(tls_config.client_ca_file)])
        if tls_config.behind_tls_proxy:
            cli_args.append("--behind-tls-proxy")
    return run_server_cli(
        cli_args,
        app_builder=lambda _ws, _mode: app,
        max_runtime_sec=max_runtime_sec,
    )
