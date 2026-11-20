"""Standalone Python 3.14 Native ASGI 3.0 web/API application factory ('create_web_app').

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import inspect
import json
import secrets
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from zcg.core.domain import normalize_cdn_origins
from zcg.web.auth import security, tls
from zcg.web.auth.surface_access import SurfaceAccessError, SurfaceAccessPolicy
from zcg.web.http import channels, middleware, request, router
from zcg.web.http.channels import DeliveryChannel, SSEMessage, Zone
from zcg.web.http.middleware import CORSPolicy, HTTPMiddleware
from zcg.web.http.request import ASGIApp, Receive, Request, Scope, Send, WebResponse
from zcg.web.http.router import APIRouter, RouteHandler
from zcg.web.ops import probes, resilience, telemetry
from zcg.web.ops.resilience import ContextLoadSnapshot
from zcg.web.ops.telemetry import HealthRegime, TelemetryGrade, TrafficFlowOrigin
from zcg.web.ui.static_files import FallbackStaticCatalog
from zcg.web.ui.templates import TemplateCatalog

_LOOPBACK_HOSTS: tuple[str, ...] = ("", "127.0.0.1", "::1", "localhost")


def _classify_flow(c_host: str, headers: Mapping[str, str]) -> TrafficFlowOrigin:
    if headers.get("x-zcg-peer-node") or headers.get("x-zcg-mesh-hop"):
        return TrafficFlowOrigin.INTERNAL_MESH
    return (
        TrafficFlowOrigin.INTERNAL_HUMAN
        if c_host in _LOOPBACK_HOSTS
        else TrafficFlowOrigin.EXTERNAL_INGRESS
    )


@dataclass(slots=True)
class WebAppState:
    """Per-instance runtime state container (PEP 703 safe with 0 module-level globals)."""

    title: str
    version: str
    csrf_token: str
    csrf_secret: str
    shutdown_event: asyncio.Event
    jitter_tracker: probes.HeartbeatJitterTracker
    telemetry_scorer: telemetry.RuntimeTelemetryScorer
    signal_collector: telemetry.RouteSignalCollector
    job_queue: resilience.DeferredJobQueue
    bulkhead: resilience.BulkheadIsolationGuard
    templates: TemplateCatalog
    static_catalog: FallbackStaticCatalog


async def _send_web_response(
    send: Send, resp: WebResponse, extra_headers: Mapping[str, str] | None = None,
    cdn_origins: Sequence[str] = (), *, is_https: bool = False,
) -> None:  # fmt: skip
    if "text/html" in resp.content_type and b"://" in resp.body:
        sri_err = security.verify_sri_external_assets(
            resp.body.decode("utf-8", "ignore"), allowed_cdn_origins=cdn_origins
        )
        if sri_err:
            raise security.WebAppError(
                f"External asset SRI/CDN violation: {sri_err[0]}", error_code="SRI_POLICY_VIOLATION"
            )
    sec_h = security.build_zone_security_headers(
        resp.channel.zone, allowed_cdn_origins=cdn_origins, is_https=is_https
    )
    hdrs = {
        **sec_h, channels.CHANNEL_HEADER: resp.channel.value, "content-type": resp.content_type,
        "content-length": str(len(resp.body)), **(extra_headers or {}), **resp.headers,
    }  # fmt: skip
    raw_hdrs = [(k.encode("latin1"), v.encode("latin1")) for k, v in hdrs.items()]
    await send({"type": "http.response.start", "status": resp.status, "headers": raw_hdrs})
    await send({"type": "http.response.body", "body": resp.body, "more_body": False})


def _resolve_html_csrf_cookie(state: WebAppState, req: Request, *, pinned: bool) -> str:
    if pinned:
        return state.csrf_token
    cur_ck = req.cookies.get(security.CSRF_COOKIE, "")
    cur_sess = req.cookies.get(security.SESSION_COOKIE, "")
    if cur_ck and security.verify_double_submit_csrf(
        cur_ck, cookie_token=cur_ck, secret_key=state.csrf_secret, session_binding=cur_sess
    ):
        return cur_ck
    return security.issue_csrf_token(state.csrf_secret, session_binding=cur_sess)


def create_web_app(
    *, title: str = "ZeroCloudGravity Web Application", version: str = "1.0.0",
    routers: Sequence[APIRouter] = (),
    router_factory: Callable[[WebAppState], Sequence[APIRouter]] | None = None,
    template_dirs: Sequence[Path] = (), static_dirs: Sequence[Path] = (),
    csrf_token: str | None = None, max_payload_bytes: int = security.DEFAULT_MAX_PAYLOAD_BYTES,
    docs_access_mode: security.DocsAccessMode = security.DocsAccessMode.PUBLIC,
    docs_bearer_token: str = "", surface_access_policy: SurfaceAccessPolicy | None = None,
    allowed_cdn_origins: Sequence[str] = (), allowed_hosts: Sequence[str] = (),
    cors_policy: CORSPolicy | None = None, middlewares: Sequence[HTTPMiddleware] = (),
    bulkhead_load_provider: Callable[[WebAppState], ContextLoadSnapshot] | None = None,
    critical_r3_safe_mode: bool = False,
    trusted_proxies: Sequence[str] = tls.DEFAULT_TRUSTED_PROXIES,
    sse_heartbeat_sec: float = 15.0, sse_event_name: str = "web.snapshot",
    telemetry_grade: TelemetryGrade = TelemetryGrade.G1_OBSERVE,
    sse_snapshot_provider: Callable[[WebAppState], Mapping[str, object]] | None = None,
    healthz_extra_provider: Callable[[WebAppState], Mapping[str, object]] | None = None,
    poll_done_predicate: Callable[[Request, WebAppState], bool] | None = None,
    fallback_handler: RouteHandler | None = None, state_out: list[WebAppState] | None = None,
) -> ASGIApp:  # fmt: skip
    """Create a standalone Python 3.14 Native ASGI 3.0 web/API application."""
    cdn_t, csrf_pinned = normalize_cdn_origins(allowed_cdn_origins), csrf_token is not None
    csrf_secret = secrets.token_urlsafe(32)
    root_router = APIRouter()
    for rtr in routers:
        root_router.include_router(rtr)
    init_csrf = csrf_token if csrf_token is not None else security.issue_csrf_token(csrf_secret)
    state = WebAppState(
        title=title, version=version, csrf_token=init_csrf, csrf_secret=csrf_secret,
        shutdown_event=asyncio.Event(), jitter_tracker=probes.HeartbeatJitterTracker(),
        telemetry_scorer=telemetry.RuntimeTelemetryScorer(grade=telemetry_grade),
        signal_collector=telemetry.RouteSignalCollector(), job_queue=resilience.DeferredJobQueue(),
        bulkhead=resilience.BulkheadIsolationGuard(), templates=TemplateCatalog(template_dirs),
        static_catalog=FallbackStaticCatalog(static_dirs),
    )  # fmt: skip
    if router_factory is not None:
        for dyn_rtr in router_factory(state):
            root_router.include_router(dyn_rtr)
    if state_out is not None:
        state_out.append(state)
    eff_mws: list[HTTPMiddleware] = list(middlewares)
    if bulkhead_load_provider is not None:
        bh_mw = middleware.make_bulkhead_middleware(
            state.bulkhead, lambda: bulkhead_load_provider(state)
        )
        eff_mws.insert(0, bh_mw)

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
            raise security.WebAppError("Unsupported ASGI scope", error_code="UNSUPPORTED_SCOPE")

        t0 = time.monotonic()
        req_https = tls.is_https_scope(scope, trusted_proxies=trusted_proxies)
        prelim_req = Request(scope)
        match, allowed_methods = root_router.resolve(prelim_req.method, prelim_req.path)
        active_channel = match.route.channel if match is not None else DeliveryChannel.STATIC_SYNC
        is_swap = prelim_req.is_partial_swap and not prelim_req.is_boosted and match is not None
        if is_swap and active_channel == DeliveryChannel.ISLAND_SYNC:
            active_channel = DeliveryChannel.SWAP_SYNC
        cors_h = (
            cors_policy.resolve_origin_headers(prelim_req.headers.get("origin", ""))
            if cors_policy is not None else {}
        )  # fmt: skip

        try:
            middleware.enforce_allowed_hosts(prelim_req.headers, allowed_hosts)
            if cors_policy is not None:
                pf_resp = cors_policy.handle_preflight(prelim_req.method, prelim_req.headers)
                if pf_resp is not None:
                    await _send_web_response(send, pf_resp, cors_h, cdn_t, is_https=req_https)
                    return

            client_t = scope.get("client")
            c_host = str(client_t[0]) if isinstance(client_t, (tuple, list)) and client_t else ""
            ck_in = prelim_req.cookies.get(security.CSRF_COOKIE, "")
            hdr_in = prelim_req.headers.get(security.CSRF_HEADER, "")
            ds_ok = not csrf_pinned and bool(ck_in) and security.verify_double_submit_csrf(
                hdr_in, cookie_token=ck_in, secret_key=state.csrf_secret,
                session_binding=prelim_req.cookies.get(security.SESSION_COOKIE, ""),
            )  # fmt: skip
            ring_h = (
                surface_access_policy.enforce(
                    method=prelim_req.method, path=prelim_req.path, headers=prelim_req.headers,
                    cookies=prelim_req.cookies, client_host=c_host,
                    expected_csrf=hdr_in if ds_ok else state.csrf_token,
                )
                if surface_access_policy is not None else {}
            )  # fmt: skip
            eff_ring = ring_h.get("x-zcg-surface-ring", "R3" if c_host in _LOOPBACK_HOSTS else "R0")
            if critical_r3_safe_mode and prelim_req.path != "/healthz" and eff_ring != "R3":
                cur_in = state.signal_collector.derive_telemetry_input()
                if state.telemetry_scorer.evaluate(cur_in).regime == HealthRegime.CRITICAL:
                    raise security.WebAppError(
                        "Node in R3 survival safe mode due to CRITICAL telemetry regime",
                        error_code="CRITICAL_R3_SURVIVAL_SAFE_MODE",
                        http_status=int(HTTPStatus.SERVICE_UNAVAILABLE),
                        severity=security.ErrorSeverity.ERROR,
                    )  # fmt: skip
            extra_h = {**ring_h, **cors_h}
            body = await request.read_bounded_body(receive, prelim_req.headers, max_payload_bytes)
            m_params = match.path_params if match is not None else None
            req = Request(scope, body=body, path_params=m_params)

            if req.path == "/events" and req.method == "GET" and match is None:
                sse_h = {
                    **security.build_zone_security_headers(
                        Zone.Z3, allowed_cdn_origins=cdn_t, is_https=req_https
                    ),
                    channels.CHANNEL_HEADER: DeliveryChannel.ISLAND_STREAM.value,
                    "content-type": "text/event-stream; charset=utf-8",
                    "cache-control": "no-cache", "x-accel-buffering": "no", **extra_h,
                }  # fmt: skip
                raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in sse_h.items()]
                await send(
                    {"type": "http.response.start", "status": int(HTTPStatus.OK), "headers": raw_h}
                )

                async def _event_gen() -> AsyncIterator[SSEMessage]:
                    j_snap = state.jitter_tracker.record_tick()
                    extra = dict(sse_snapshot_provider(state)) if sse_snapshot_provider else {}
                    snap = {"title": state.title, "jitter_status": j_snap.status.value, **extra}
                    yield channels.VersionedPayload(data=snap).to_sse(event=sse_event_name)
                    if req.query("hold", "0") == "1":
                        await state.shutdown_event.wait()

                async for frame in channels.heartbeat_sse_stream(
                    _event_gen(), interval=sse_heartbeat_sec, shutdown_event=state.shutdown_event
                ):
                    await send({"type": "http.response.body", "body": frame, "more_body": True})
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return

            async def _dispatch_http(r_in: Request) -> WebResponse:
                if match is not None:
                    if not security.verify_csrf_request(
                        method=r_in.method, zone=active_channel.zone, headers=r_in.headers,
                        expected_token=state.csrf_token, cookies=r_in.cookies,
                        secret_key="" if csrf_pinned else state.csrf_secret,
                        allowed_origins=cors_policy.allow_origins if cors_policy else (),
                    ):  # fmt: skip
                        raise security.WebAppError(
                            "CSRF token missing or invalid", error_code="CSRF_VALIDATION_FAILED",
                            http_status=int(HTTPStatus.FORBIDDEN),
                            severity=security.ErrorSeverity.WARNING,
                            action=security.ErrorAction.RETRY,
                            user_hint="Include header x-zcg-csrf-token matching session token.",
                        )  # fmt: skip
                    await middleware.run_route_guards(match.route.guards, r_in)
                    raw_res = match.route.handler(r_in)
                    resp = await raw_res if inspect.isawaitable(raw_res) else raw_res
                    if r_in.method == "GET" and "text/html" in resp.content_type:
                        ck_tok = _resolve_html_csrf_cookie(state, r_in, pinned=csrf_pinned)
                        ck = tls.format_set_cookie_header(
                            security.CSRF_COOKIE, ck_tok, is_https=req_https
                        )
                        resp = WebResponse(
                            resp.status, resp.content_type, resp.body,
                            resp.channel, {"set-cookie": ck, **resp.headers},
                        )  # fmt: skip
                    state.signal_collector.record(
                        method=r_in.method, route=match.route.path_template,
                        status_code=resp.status, latency_ms=(time.monotonic() - t0) * 1000.0,
                        flow_origin=_classify_flow(c_host, r_in.headers),
                    )  # fmt: skip
                    return resp

                if allowed_methods:
                    allow_hdr = {"allow": ", ".join(allowed_methods)}
                    err_b = json.dumps({"error": "METHOD_NOT_ALLOWED", "allow": allowed_methods})
                    return WebResponse(
                        int(HTTPStatus.METHOD_NOT_ALLOWED), request.JSON_CONTENT_TYPE,
                        err_b.encode("utf-8"), DeliveryChannel.STATIC_SYNC, allow_hdr,
                    )  # fmt: skip

                if r_in.path == "/healthz" and r_in.method == "GET":
                    j_snap = state.jitter_tracker.record_tick()
                    rep = state.telemetry_scorer.evaluate(
                        state.signal_collector.derive_telemetry_input()
                    )
                    extra_hz = dict(healthz_extra_provider(state)) if healthz_extra_provider else {}
                    hz = {
                        "status": "ok", "protocol": "python314-native-asgi",
                        "title": state.title, "version": state.version,
                        "delivery_channels_count": len(DeliveryChannel),
                        "zones": ["Z1", "Z2", "Z3", "Z4"],
                        "http_poll_stop_status": channels.HTTP_POLL_STOP_STATUS,
                        "health_regime": rep.regime.value, "health_score": rep.score,
                        "telemetry_grade": rep.grade.value, "jitter_status": j_snap.status.value,
                        "docs_access_mode": docs_access_mode.value,
                        "flow_partitions": state.signal_collector.flow_partition_summary(),
                        "routes": state.signal_collector.route_summary(), **extra_hz,
                    }  # fmt: skip
                    return WebResponse(
                        int(HTTPStatus.OK), request.JSON_CONTENT_TYPE,
                        json.dumps(hz).encode("utf-8"), DeliveryChannel.STATIC_SYNC,
                    )  # fmt: skip

                if r_in.path == "/api/poll/status" and r_in.method == "GET":
                    if "done" in r_in.query_params:
                        done = r_in.query("done").lower() in ("1", "true", "yes")
                    elif poll_done_predicate is not None:
                        done = poll_done_predicate(r_in, state)
                    else:
                        done = state.job_queue.active_count == 0
                    lbl = "Completed" if done else "In Progress"
                    frag = f'<div id="zcg-poll-status" data-done="{str(done).lower()}">{lbl}</div>'
                    return request.respond_poll(r_in, done=done, html_fragment=frag)

                if r_in.path.startswith("/static/") and r_in.method == "GET":
                    return state.static_catalog.serve(r_in, r_in.path.removeprefix("/static/"))

                if r_in.path in ("/docs", "/openapi.json") and r_in.method == "GET":
                    doc_st = security.evaluate_docs_access(
                        docs_access_mode, r_in.headers, docs_bearer_token
                    )
                    if doc_st == int(HTTPStatus.NOT_FOUND):
                        raise security.WebAppError(
                            "Interactive API documentation is disabled in this environment",
                            error_code="DOCS_DISABLED", http_status=int(HTTPStatus.NOT_FOUND),
                            severity=security.ErrorSeverity.INFO,
                            user_hint="OpenAPI /docs is disabled in 'pro' for security hardening.",
                        )  # fmt: skip
                    if doc_st == int(HTTPStatus.UNAUTHORIZED):
                        u_h = {"www-authenticate": 'Bearer realm="zcg-web"'}
                        return WebResponse(
                            int(HTTPStatus.UNAUTHORIZED), request.JSON_CONTENT_TYPE,
                            b'{"error":"DOCS_UNAUTHORIZED"}', DeliveryChannel.STATIC_SYNC, u_h,
                        )  # fmt: skip
                    spec = router.compose_openapi_document(
                        title=state.title, version=state.version, root_router=root_router
                    )
                    is_json = r_in.path == "/openapi.json"
                    d_ct = request.JSON_CONTENT_TYPE if is_json else request.HTML_CONTENT_TYPE
                    d_txt = (
                        json.dumps(spec) if is_json
                        else router.render_openapi_docs_html(
                            state.title, state.version, spec["paths"]
                        )
                    )  # fmt: skip
                    return WebResponse(
                        int(HTTPStatus.OK), d_ct, d_txt.encode("utf-8"), DeliveryChannel.STATIC_SYNC
                    )

                if fallback_handler is not None:
                    raw_fb = fallback_handler(r_in)
                    return await raw_fb if inspect.isawaitable(raw_fb) else raw_fb

                raise security.WebAppError(
                    f"Resource not found: {r_in.path}", error_code="NOT_FOUND",
                    http_status=int(HTTPStatus.NOT_FOUND), severity=security.ErrorSeverity.WARNING,
                )  # fmt: skip

            pipeline = middleware.compose_http_pipeline(eff_mws, _dispatch_http)
            await _send_web_response(send, await pipeline(req), extra_h, cdn_t, is_https=req_https)
        except security.WebAppError as exc:
            if isinstance(exc, SurfaceAccessError) or (
                exc.error_code == "CRITICAL_R3_SURVIVAL_SAFE_MODE"
            ):
                state.signal_collector.record(
                    method=prelim_req.method, route=prelim_req.path, status_code=exc.http_status,
                    latency_ms=(time.monotonic() - t0) * 1000.0,
                    flow_origin=TrafficFlowOrigin.REJECTED_EXTERNAL,
                )  # fmt: skip
            st_c, ct, err_bytes = security.format_runtime_error_response(
                exc, is_partial=prelim_req.is_partial_swap
            )
            err_h = exc.response_headers if isinstance(exc, SurfaceAccessError) else {}
            err_resp = WebResponse(st_c, ct, err_bytes, active_channel, err_h)
            await _send_web_response(send, err_resp, cors_h, cdn_t, is_https=req_https)

    return app
