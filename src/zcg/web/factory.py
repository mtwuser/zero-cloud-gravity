"""Standalone Python 3.14 Native ASGI 3.0 web/API application factory ('create_web_app').

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import html
import inspect
import json
import secrets
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

from zcg.web.channels import (
    CHANNEL_HEADER,
    HTTP_POLL_STOP_STATUS,
    DeliveryChannel,
    SSEMessage,
    VersionedPayload,
    Zone,
    heartbeat_sse_stream,
)
from zcg.web.probes import HeartbeatJitterTracker
from zcg.web.request import (
    HTML_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    ASGIApp,
    Receive,
    Request,
    Scope,
    Send,
    WebResponse,
    read_bounded_body,
    respond_poll,
)
from zcg.web.resilience import BulkheadIsolationGuard, DeferredJobQueue
from zcg.web.router import APIRouter, RouteHandler
from zcg.web.security import (
    CSRF_COOKIE,
    DEFAULT_MAX_PAYLOAD_BYTES,
    DocsAccessMode,
    ErrorAction,
    ErrorSeverity,
    WebAppError,
    build_zone_security_headers,
    evaluate_docs_access,
    format_runtime_error_response,
    verify_csrf_request,
)
from zcg.web.static_files import FallbackStaticCatalog
from zcg.web.telemetry import RouteSignalCollector, RuntimeTelemetryScorer, TelemetryGrade
from zcg.web.templates import TemplateCatalog


@dataclass(slots=True)
class WebAppState:
    """Per-instance runtime state container (PEP 703 safe with 0 module-level globals)."""

    title: str
    version: str
    csrf_token: str
    shutdown_event: asyncio.Event
    jitter_tracker: HeartbeatJitterTracker
    telemetry_scorer: RuntimeTelemetryScorer
    signal_collector: RouteSignalCollector
    job_queue: DeferredJobQueue
    bulkhead: BulkheadIsolationGuard
    templates: TemplateCatalog
    static_catalog: FallbackStaticCatalog


async def _send_web_response(send: Send, resp: WebResponse) -> None:
    hdrs = {
        **build_zone_security_headers(resp.channel.zone),
        CHANNEL_HEADER: resp.channel.value,
        "content-type": resp.content_type,
        "content-length": str(len(resp.body)),
        **resp.headers,
    }
    raw_hdrs = [(k.encode("latin1"), v.encode("latin1")) for k, v in hdrs.items()]
    await send({"type": "http.response.start", "status": resp.status, "headers": raw_hdrs})
    await send({"type": "http.response.body", "body": resp.body, "more_body": False})


def _compose_openapi_document(state: WebAppState, root_router: APIRouter) -> dict[str, Any]:
    builtin_paths: dict[str, Any] = {
        "/healthz": {"get": {"x-delivery-channel": DeliveryChannel.STATIC_SYNC.value}},
        "/events": {"get": {"x-delivery-channel": DeliveryChannel.ISLAND_STREAM.value}},
        "/api/poll/status": {"get": {"x-delivery-channel": DeliveryChannel.SWAP_DEFERRED.value}},
        "/static/{asset_path}": {"get": {"x-delivery-channel": DeliveryChannel.STATIC_SYNC.value}},
        **root_router.build_openapi_paths(),
    }
    return {
        "openapi": "3.1.0",
        "info": {"title": state.title, "version": state.version},
        "paths": builtin_paths,
    }


def _render_openapi_docs_html(title: str, version: str, paths: Mapping[str, Any]) -> str:
    rows = "".join(
        f"<tr><td><span class='zcg-badge'>{html.escape(m.upper())}</span></td>"
        f"<td><code>{html.escape(p)}</code></td>"
        f"<td><code>{html.escape(str(op.get('x-delivery-channel', '')))}</code></td>"
        f"<td>{html.escape(str(op.get('summary', 'Built-in runtime endpoint')))}</td></tr>"
        for p, ops in paths.items()
        if isinstance(ops, Mapping)
        for m, op in ops.items()
        if isinstance(op, Mapping)
    )
    t_esc, v_esc = html.escape(title), html.escape(version)
    return (
        f"<!doctype html><html lang='en' data-zcg-surface='cockpit'><head><meta charset='utf-8'>"
        f"<title>{t_esc} — OpenAPI 3.1</title>"
        "<link rel='stylesheet' href='/static/css/design-system.css'>"
        "<link rel='stylesheet' href='/static/css/layout.css'>"
        "<link rel='stylesheet' href='/static/css/components.css'></head><body>"
        f"<header class='zcg-z1-header'><div class='zcg-card__header'><h1>{t_esc} "
        f"<span class='zcg-badge'>OpenAPI 3.1 · v{v_esc}</span></h1>"
        "<div class='zcg-tabs'><a class='zcg-tab' href='/dashboard'>Dashboard</a>"
        "<a class='zcg-tab' href='/openapi.json'>Raw /openapi.json</a></div></div></header>"
        "<main class='zcg-z3-main'><section class='zcg-card'><table class='zcg-table'>"
        "<thead><tr><th>Method</th><th>Path</th><th>DeliveryChannel</th><th>Summary</th></tr>"
        f"</thead><tbody>{rows}</tbody></table></section></main></body></html>"
    )


def create_web_app(
    *,
    title: str = "ZeroCloudGravity Web Application",
    version: str = "1.0.0",
    routers: Sequence[APIRouter] = (),
    router_factory: Callable[[WebAppState], Sequence[APIRouter]] | None = None,
    template_dirs: Sequence[Path] = (),
    static_dirs: Sequence[Path] = (),
    csrf_token: str | None = None,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    docs_access_mode: DocsAccessMode = DocsAccessMode.PUBLIC,
    docs_bearer_token: str = "",
    sse_heartbeat_sec: float = 15.0,
    sse_event_name: str = "web.snapshot",
    telemetry_grade: TelemetryGrade = TelemetryGrade.G1_OBSERVE,
    sse_snapshot_provider: Callable[[WebAppState], Mapping[str, object]] | None = None,
    healthz_extra_provider: Callable[[WebAppState], Mapping[str, object]] | None = None,
    poll_done_predicate: Callable[[Request, WebAppState], bool] | None = None,
    fallback_handler: RouteHandler | None = None,
    state_out: list[WebAppState] | None = None,
) -> ASGIApp:
    """Create a standalone Python 3.14 Native ASGI 3.0 web/API application."""
    root_router = APIRouter()
    for rtr in routers:
        root_router.include_router(rtr)
    state = WebAppState(
        title=title, version=version, csrf_token=csrf_token or secrets.token_urlsafe(24),
        shutdown_event=asyncio.Event(), jitter_tracker=HeartbeatJitterTracker(),
        telemetry_scorer=RuntimeTelemetryScorer(grade=telemetry_grade),
        signal_collector=RouteSignalCollector(), job_queue=DeferredJobQueue(),
        bulkhead=BulkheadIsolationGuard(), templates=TemplateCatalog(template_dirs),
        static_catalog=FallbackStaticCatalog(static_dirs),
    )  # fmt: skip
    if router_factory is not None:
        for dyn_rtr in router_factory(state):
            root_router.include_router(dyn_rtr)
    if state_out is not None:
        state_out.append(state)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = str(scope.get("type", ""))
        if scope_type == "lifespan":
            while True:
                mtype = str((await receive()).get("type", ""))
                if mtype == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif mtype == "lifespan.shutdown":
                    state.shutdown_event.set()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope_type != "http":
            raise WebAppError("Unsupported ASGI scope", error_code="UNSUPPORTED_SCOPE")

        t0 = time.monotonic()
        prelim_headers = {
            bytes(k).decode("latin1").lower(): bytes(v).decode("latin1")
            for k, v in scope.get("headers", [])
        }
        prelim_req = Request(scope)
        match, allowed_methods = root_router.resolve(prelim_req.method, prelim_req.path)
        active_channel = match.route.channel if match is not None else DeliveryChannel.STATIC_SYNC
        if (
            prelim_req.is_partial_swap
            and not prelim_req.is_boosted
            and match is not None
            and active_channel == DeliveryChannel.ISLAND_SYNC
        ):
            active_channel = DeliveryChannel.SWAP_SYNC

        try:
            body = await read_bounded_body(receive, prelim_headers, max_payload_bytes)
            req = Request(
                scope, body=body, path_params=match.path_params if match is not None else None
            )
            if match is not None:
                if not verify_csrf_request(
                    method=req.method,
                    zone=active_channel.zone,
                    headers=req.headers,
                    expected_token=state.csrf_token,
                ):
                    raise WebAppError(
                        "CSRF token missing or invalid",
                        error_code="CSRF_VALIDATION_FAILED",
                        http_status=int(HTTPStatus.FORBIDDEN),
                        severity=ErrorSeverity.WARNING,
                        action=ErrorAction.RETRY,
                        user_hint="Include header x-zcg-csrf-token matching your session token.",
                    )
                raw_res = match.route.handler(req)
                resp = await raw_res if inspect.isawaitable(raw_res) else raw_res
                if req.method == "GET" and "text/html" in resp.content_type:
                    ck = f"{CSRF_COOKIE}={state.csrf_token}; HttpOnly; SameSite=Strict; Path=/"
                    resp = WebResponse(
                        resp.status, resp.content_type, resp.body,
                        resp.channel, {"set-cookie": ck, **resp.headers},
                    )  # fmt: skip
                state.signal_collector.record(
                    method=req.method, route=match.route.path_template,
                    status_code=resp.status, latency_ms=(time.monotonic() - t0) * 1000.0,
                )  # fmt: skip
                await _send_web_response(send, resp)
                return

            if allowed_methods:
                allow_hdr = {"allow": ", ".join(allowed_methods)}
                err_b = json.dumps({"error": "METHOD_NOT_ALLOWED", "allow": allowed_methods})
                m_resp = WebResponse(
                    int(HTTPStatus.METHOD_NOT_ALLOWED), JSON_CONTENT_TYPE,
                    err_b.encode("utf-8"), DeliveryChannel.STATIC_SYNC, allow_hdr,
                )  # fmt: skip
                await _send_web_response(send, m_resp)
                return

            if req.path == "/events" and req.method == "GET":
                sse_h = {
                    **build_zone_security_headers(Zone.Z3),
                    CHANNEL_HEADER: DeliveryChannel.ISLAND_STREAM.value,
                    "content-type": "text/event-stream; charset=utf-8",
                    "cache-control": "no-cache", "x-accel-buffering": "no",
                }  # fmt: skip
                raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in sse_h.items()]
                await send(
                    {"type": "http.response.start", "status": int(HTTPStatus.OK), "headers": raw_h}
                )

                async def _event_gen() -> AsyncIterator[SSEMessage]:
                    j_snap = state.jitter_tracker.record_tick()
                    extra = dict(sse_snapshot_provider(state)) if sse_snapshot_provider else {}
                    snap = {"title": state.title, "jitter_status": j_snap.status.value, **extra}
                    yield VersionedPayload(data=snap).to_sse(event=sse_event_name)
                    if req.query("hold", "0") == "1":
                        await state.shutdown_event.wait()

                async for frame in heartbeat_sse_stream(
                    _event_gen(), interval=sse_heartbeat_sec, shutdown_event=state.shutdown_event
                ):
                    await send({"type": "http.response.body", "body": frame, "more_body": True})
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return

            if req.path == "/healthz" and req.method == "GET":
                j_snap = state.jitter_tracker.record_tick()
                rep = state.telemetry_scorer.evaluate(
                    state.signal_collector.derive_telemetry_input()
                )
                extra_hz = dict(healthz_extra_provider(state)) if healthz_extra_provider else {}
                hz = {
                    "status": "ok",
                    "protocol": "python314-native-asgi",
                    "title": state.title,
                    "version": state.version,
                    "delivery_channels_count": len(DeliveryChannel),
                    "zones": ["Z1", "Z2", "Z3", "Z4"],
                    "http_poll_stop_status": HTTP_POLL_STOP_STATUS,
                    "health_regime": rep.regime.value,
                    "health_score": rep.score,
                    "telemetry_grade": rep.grade.value,
                    "jitter_status": j_snap.status.value,
                    "docs_access_mode": docs_access_mode.value,
                    "routes": state.signal_collector.route_summary(),
                    **extra_hz,
                }
                await _send_web_response(
                    send,
                    WebResponse(
                        int(HTTPStatus.OK),
                        JSON_CONTENT_TYPE,
                        json.dumps(hz).encode("utf-8"),
                        DeliveryChannel.STATIC_SYNC,
                    ),
                )
                return

            if req.path == "/api/poll/status" and req.method == "GET":
                if "done" in req.query_params:
                    done = req.query("done").lower() in ("1", "true", "yes")
                elif poll_done_predicate is not None:
                    done = poll_done_predicate(req, state)
                else:
                    done = state.job_queue.active_count == 0
                lbl = "Completed" if done else "In Progress"
                frag = f'<div id="zcg-poll-status" data-done="{str(done).lower()}">{lbl}</div>'
                await _send_web_response(send, respond_poll(req, done=done, html_fragment=frag))
                return

            if req.path.startswith("/static/") and req.method == "GET":
                await _send_web_response(
                    send, state.static_catalog.serve(req, req.path.removeprefix("/static/"))
                )
                return

            if req.path in ("/docs", "/openapi.json") and req.method == "GET":
                doc_st = evaluate_docs_access(docs_access_mode, req.headers, docs_bearer_token)
                if doc_st == int(HTTPStatus.NOT_FOUND):
                    raise WebAppError(
                        "Interactive API documentation is disabled in this environment",
                        error_code="DOCS_DISABLED",
                        http_status=int(HTTPStatus.NOT_FOUND),
                        severity=ErrorSeverity.INFO,
                        user_hint="OpenAPI /docs is disabled in 'pro' for security hardening.",
                    )
                if doc_st == int(HTTPStatus.UNAUTHORIZED):
                    u_h = {"www-authenticate": 'Bearer realm="zcg-web"'}
                    u_b = b'{"error":"DOCS_UNAUTHORIZED"}'
                    u_r = WebResponse(
                        int(HTTPStatus.UNAUTHORIZED),
                        JSON_CONTENT_TYPE,
                        u_b,
                        DeliveryChannel.STATIC_SYNC,
                        u_h,
                    )
                    await _send_web_response(send, u_r)
                    return
                spec = _compose_openapi_document(state, root_router)
                is_json = req.path == "/openapi.json"
                d_ct = JSON_CONTENT_TYPE if is_json else HTML_CONTENT_TYPE
                d_txt = (
                    json.dumps(spec)
                    if is_json
                    else _render_openapi_docs_html(state.title, state.version, spec["paths"])
                )
                d_r = WebResponse(
                    int(HTTPStatus.OK), d_ct, d_txt.encode("utf-8"), DeliveryChannel.STATIC_SYNC
                )
                await _send_web_response(send, d_r)
                return

            if fallback_handler is not None:
                raw_fb = fallback_handler(req)
                fb_resp = await raw_fb if inspect.isawaitable(raw_fb) else raw_fb
                await _send_web_response(send, fb_resp)
                return

            raise WebAppError(
                f"Resource not found: {req.path}",
                error_code="NOT_FOUND",
                http_status=int(HTTPStatus.NOT_FOUND),
                severity=ErrorSeverity.WARNING,
            )
        except WebAppError as exc:
            st_c, ct, err_bytes = format_runtime_error_response(
                exc, is_partial=prelim_req.is_partial_swap
            )
            await _send_web_response(send, WebResponse(st_c, ct, err_bytes, active_channel))

    return app
