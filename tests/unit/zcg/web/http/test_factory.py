"""Unit tests for zcg.web.http.factory.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from zcg.web.auth.security import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    DocsAccessMode,
    ErrorSeverity,
    WebAppError,
    compute_sri_sha384,
)
from zcg.web.auth.surface_access import (
    DISCLOSURE_TIER_HEADER,
    SURFACE_RING_HEADER,
    RingRouteRule,
    SlidingWindowRateLimiter,
    SurfaceAccessPolicy,
    SurfaceRing,
    issue_scoped_surface_grant,
)
from zcg.web.http.channels import CHANNEL_HEADER, DeliveryChannel
from zcg.web.http.factory import WebAppState, create_web_app
from zcg.web.http.middleware import CORSPolicy, NextHandler
from zcg.web.http.request import (
    HTML_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    Message,
    Request,
    Scope,
    WebResponse,
)
from zcg.web.http.router import APIRouter
from zcg.web.ops.resilience import ContextLoadSnapshot


async def _invoke(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    client: tuple[str, int] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": raw_h,
    }
    if client is not None:
        scope["client"] = client

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    sent: list[Message] = []

    async def send(msg: Message) -> None:
        sent.append(msg)

    await app(scope, receive, send)
    start = sent[0]
    resp_h = {
        bytes(k).decode("latin1"): bytes(v).decode("latin1") for k, v in start.get("headers", [])
    }
    out = b"".join(bytes(m.get("body", b"")) for m in sent[1:])
    return int(start["status"]), resp_h, out


class TestFactory:
    """Verify create_web_app routes, CSRF, 404/405, fallback, static, poll 286, SSE, and OpenAPI."""

    def test_routes_csrf_405_fallback_static_and_unsupported_scope_expected(self) -> None:
        """Verify sync/async routers, router_factory, CSRF, 405, fallback, static, and 404."""
        # Arrange
        rtr = APIRouter()

        @rtr.get("/")
        def _index(req: Request) -> WebResponse:
            return WebResponse(200, HTML_CONTENT_TYPE, b"<h1>Home</h1>")

        @rtr.post("/submit", channel=DeliveryChannel.SWAP_SYNC)
        async def _submit(req: Request) -> WebResponse:
            await asyncio.sleep(0)
            return WebResponse(201, JSON_CONTENT_TYPE, b'{"saved":true}', DeliveryChannel.SWAP_SYNC)

        def _dyn_routers(st: WebAppState) -> tuple[APIRouter, ...]:
            dyn = APIRouter(prefix="/dyn")

            @dyn.get("/ping")
            def _ping(req: Request) -> WebResponse:
                return WebResponse(200, JSON_CONTENT_TYPE, st.title.encode("utf-8"))

            return (dyn,)

        async def _async_fb(req: Request) -> WebResponse:
            await asyncio.sleep(0)
            return WebResponse(200, JSON_CONTENT_TYPE, b'{"fb":true}', DeliveryChannel.STATIC_SYNC)

        states: list[WebAppState] = []
        tok = "tok-web-01"
        app = create_web_app(
            title="Portal",
            routers=(rtr,),
            router_factory=_dyn_routers,
            csrf_token=tok,
            state_out=states,
        )
        app_nostate = create_web_app(
            title="Minimal",
            fallback_handler=lambda _req: WebResponse(200, HTML_CONTENT_TYPE, b"fb-sync"),
        )
        app_fb_async = create_web_app(fallback_handler=_async_fb)

        async def _run() -> int:
            async def _noop_recv() -> Message:
                return {"type": "websocket.disconnect"}

            async def _noop_send(msg: Message) -> None:
                return None

            with pytest.raises(WebAppError, match="Unsupported ASGI scope"):
                await app_nostate({"type": "websocket"}, _noop_recv, _noop_send)

            st_home, h_home, _ = await _invoke(app, "GET", "/")
            assert st_home == 200 and "zcg_csrf=tok-web-01" in h_home["set-cookie"]

            st_swap, h_swap, _ = await _invoke(app, "GET", "/", headers={"hx-request": "true"})
            assert st_swap == 200 and h_swap[CHANNEL_HEADER] == DeliveryChannel.ISLAND_SYNC.value

            st_boost, _, _ = await _invoke(
                app, "GET", "/", headers={"hx-request": "true", "hx-boosted": "true"}
            )
            assert st_boost == 200

            st_dyn, _, b_dyn = await _invoke(app, "GET", "/dyn/ping")
            assert st_dyn == 200 and b_dyn == b"Portal"

            st_csrf, _, b_csrf = await _invoke(
                app, "POST", "/submit", headers={"hx-request": "true"}
            )
            assert st_csrf == 403 and b"CSRF_VALIDATION_FAILED" in b_csrf

            st_post, _, _ = await _invoke(app, "POST", "/submit", headers={CSRF_HEADER: tok})
            assert st_post == 201

            st_405, h_405, _ = await _invoke(app, "DELETE", "/")
            assert st_405 == 405 and h_405["allow"] == "GET"

            st_css, _, b_css = await _invoke(app, "GET", "/static/css/design-system.css")
            assert st_css == 200 and b"--zcg-bg" in b_css

            st_404, _, b_404 = await _invoke(app, "GET", "/missing")
            assert st_404 == 404 and json.loads(b_404)["error"] == "NOT_FOUND"

            st_fbs, _, b_fbs = await _invoke(app_nostate, "GET", "/custom-static")
            st_fba, _, b_fba = await _invoke(app_fb_async, "GET", "/custom-async")
            assert st_fbs == 200 and b_fbs == b"fb-sync"
            assert st_fba == 200 and b"true" in b_fba
            return len(states[0].signal_collector.signals())

        # Act
        recorded_count = asyncio.run(_run())

        # Assert
        assert recorded_count == 5

    def test_healthz_poll_286_docs_modes_sse_and_lifespan_shutdown_expected(self) -> None:
        """Verify /healthz, /api/poll/status predicates, DocsAccessMode, and SSE hold/shutdown."""
        # Arrange
        tok = "tok-doc-77"
        app = create_web_app(
            title="LiveApp",
            docs_access_mode=DocsAccessMode.AUTHENTICATED,
            docs_bearer_token=tok,
            sse_heartbeat_sec=0.01,
            sse_event_name="custom.snapshot",
            sse_snapshot_provider=lambda st: {"custom": st.version},
            healthz_extra_provider=lambda _st: {"extra_probe": "ready"},
        )
        app_pred = create_web_app(poll_done_predicate=lambda req, st: False)
        app_dis = create_web_app(docs_access_mode=DocsAccessMode.DISABLED)

        async def _run() -> int:
            st_hz, _, b_hz = await _invoke(app, "GET", "/healthz")
            hz_doc = json.loads(b_hz)
            assert st_hz == 200 and hz_doc["delivery_channels_count"] == 16
            assert hz_doc["extra_probe"] == "ready"

            st_hz_min, _, _ = await _invoke(app_pred, "GET", "/healthz")
            assert st_hz_min == 200

            st_p_def, _, _ = await _invoke(app, "GET", "/api/poll/status")
            st_p_q, _, _ = await _invoke(app, "GET", "/api/poll/status", query="done=0")
            st_p_pred, _, _ = await _invoke(app_pred, "GET", "/api/poll/status")
            assert st_p_def == 286 and st_p_q == 200 and st_p_pred == 200

            st_dd, _, _ = await _invoke(app_dis, "GET", "/docs")
            st_401, _, _ = await _invoke(app, "GET", "/docs")
            st_oa, _, b_oa = await _invoke(
                app, "GET", "/openapi.json", headers={"authorization": f"Bearer {tok}"}
            )
            st_dc, _, b_dc = await _invoke(
                app, "GET", "/docs", headers={"authorization": f"Bearer {tok}"}
            )
            assert st_dd == 404 and st_401 == 401
            assert st_oa == 200 and json.loads(b_oa)["openapi"] == "3.1.0"
            assert st_dc == 200 and b"LiveApp" in b_dc

            st_sse, _, b_sse = await _invoke(app, "GET", "/events")
            assert st_sse == 200 and b"event: custom.snapshot" in b_sse and b"1.0.0" in b_sse

            st_sse_min, _, _ = await _invoke(app_pred, "GET", "/events")
            assert st_sse_min == 200

            life_q: asyncio.Queue[Message] = asyncio.Queue()
            life_out: list[Message] = []
            await life_q.put({"type": "lifespan.startup"})
            await life_q.put({"type": "lifespan.noop"})

            async def _life_send(msg: Message) -> None:
                life_out.append(msg)

            async def _stop_soon() -> None:
                await asyncio.sleep(0.025)
                await life_q.put({"type": "lifespan.shutdown"})

            t_life = asyncio.create_task(app({"type": "lifespan"}, life_q.get, _life_send))
            t_stop = asyncio.create_task(_stop_soon())
            _, _, b_held = await _invoke(app, "GET", "/events", query="hold=1")
            await asyncio.gather(t_life, t_stop)
            assert b": heartbeat" in b_held
            return len(life_out)

        # Act
        life_events = asyncio.run(_run())

        # Assert
        assert life_events == 2

    def test_surface_access_policy_prebody_enforcement_and_headers_expected(self) -> None:
        """Verify pre-body SurfaceAccessPolicy enforcement, ring headers, and 401/429 headers."""
        # Arrange
        sess_k, tok_c = "sess-factory-key", "csrf-factory-01"
        rtr = APIRouter()

        @rtr.get("/protected")
        def _protected(req: Request) -> WebResponse:
            return WebResponse(200, JSON_CONTENT_TYPE, b'{"ok":true}')

        @rtr.post("/open")
        def _open(req: Request) -> WebResponse:
            return WebResponse(201, JSON_CONTENT_TYPE, b'{"accepted":true}')

        policy = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R2_NETWORK_MEMBER,
            rules=(RingRouteRule("/open", SurfaceRing.R0_PUBLIC),),
            session_key=sess_k,
            r0_rate_limiter=SlidingWindowRateLimiter(max_requests=1, window_sec=60.0),
        )
        app = create_web_app(routers=(rtr,), csrf_token=tok_c, surface_access_policy=policy)
        grant_r2 = issue_scoped_surface_grant(
            signing_key=sess_k, subject_id="member-01", ring=SurfaceRing.R2_NETWORK_MEMBER
        )

        async def _run() -> tuple[
            int, dict[str, str], int, dict[str, str], int, int, dict[str, str]
        ]:
            cl, csrf_h = ("198.51.100.9", 51000), {CSRF_HEADER: tok_c}
            st_401, h_401, _ = await _invoke(app, "GET", "/protected")
            st_200, h_200, _ = await _invoke(
                app, "GET", "/protected",
                headers={"cookie": f"{SESSION_COOKIE}={grant_r2}"}, client=cl,
            )  # fmt: skip
            st_201, _, _ = await _invoke(app, "POST", "/open", headers=csrf_h, client=cl)
            st_429, h_429, _ = await _invoke(app, "POST", "/open", headers=csrf_h, client=cl)
            return st_401, h_401, st_200, h_200, st_201, st_429, h_429

        # Act
        st_401, h_401, st_200, h_200, st_201, st_429, h_429 = asyncio.run(_run())

        # Assert
        assert st_401 == 401 and "www-authenticate" in h_401
        assert h_401[SURFACE_RING_HEADER] == "R2"
        assert st_200 == 200 and h_200[SURFACE_RING_HEADER] == "R2"
        assert h_200[DISCLOSURE_TIER_HEADER] == "day1_onboarding"
        assert st_201 == 201 and st_429 == 429 and "retry-after" in h_429

    def test_allowed_cdn_origins_and_sri_policy_violation_guard_expected(self) -> None:
        """Verify CDN CSP graduation and runtime SRI_POLICY_VIOLATION block on unhashed HTML."""
        # Arrange
        cdn = "https://cdn.iso.example"
        sri = compute_sri_sha384(b"console.log(1);")
        rtr = APIRouter()

        @rtr.get("/good-cdn")
        def _good(req: Request) -> WebResponse:
            body = (
                f'<script src="{cdn}/a.js" integrity="{sri}" crossorigin="anonymous"></script>'
            ).encode()
            return WebResponse(200, HTML_CONTENT_TYPE, body, DeliveryChannel.ISLAND_SYNC)

        @rtr.get("/bad-cdn")
        def _bad(req: Request) -> WebResponse:
            body = f'<script src="{cdn}/unhashed.js"></script>'.encode()
            return WebResponse(200, HTML_CONTENT_TYPE, body, DeliveryChannel.ISLAND_SYNC)

        app = create_web_app(routers=(rtr,), allowed_cdn_origins=(cdn,))

        async def _run() -> tuple[int, dict[str, str], int, bytes]:
            st_ok, h_ok, _ = await _invoke(app, "GET", "/good-cdn")
            st_err, _, b_err = await _invoke(app, "GET", "/bad-cdn")
            return st_ok, h_ok, st_err, b_err

        # Act
        st_ok, h_ok, st_err, b_err = asyncio.run(_run())

        # Assert
        assert st_ok == 200 and cdn in h_ok["content-security-policy"]
        assert st_err == 500 and json.loads(b_err)["error"] == "SRI_POLICY_VIOLATION"

    def test_https_proxy_hsts_and_secure_cookie_vs_http_loopback_expected(self) -> None:
        """Emit HSTS and Secure cookies over trusted HTTPS while keeping loopback HTTP clean."""
        # Arrange
        rtr = APIRouter()

        @rtr.get("/portal")
        def _portal(req: Request) -> WebResponse:
            return WebResponse(200, HTML_CONTENT_TYPE, b"<h1>Portal</h1>")

        tok_https = "tok-https-01"
        app = create_web_app(routers=(rtr,), csrf_token=tok_https)

        async def _run() -> tuple[dict[str, str], dict[str, str]]:
            _, h_http, _ = await _invoke(app, "GET", "/portal", client=("127.0.0.1", 51000))
            _, h_https, _ = await _invoke(
                app,
                "GET",
                "/portal",
                headers={"x-forwarded-proto": "https"},
                client=("127.0.0.1", 51000),
            )
            return h_http, h_https

        # Act
        h_http, h_https = asyncio.run(_run())

        # Assert
        assert "strict-transport-security" not in h_http
        assert "Secure" not in h_http["set-cookie"]
        assert h_https["strict-transport-security"].startswith("max-age=63072000")
        assert h_https["set-cookie"].endswith("; Secure")

    def test_double_submit_csrf_allowed_hosts_cors_middlewares_guards_and_bulkhead_expected(
        self,
    ) -> None:
        """Verify per-client Double-Submit CSRF, Host allowlist, CORS, guards, and 503 bulkhead."""

        # Arrange
        def _require_badge(req: Request) -> None:
            if req.headers.get("x-badge") != "ok":
                raise WebAppError(
                    "Badge required",
                    error_code="BADGE_MISSING",
                    http_status=403,
                    severity=ErrorSeverity.WARNING,
                )

        async def _tag_mw(req: Request, nxt: NextHandler) -> WebResponse:
            res = await nxt(req)
            return WebResponse(
                res.status, res.content_type, res.body, res.channel, {"x-mw": "1", **res.headers}
            )

        rtr = APIRouter()

        @rtr.get("/page")
        def _page(_req: Request) -> WebResponse:
            return WebResponse(200, HTML_CONTENT_TYPE, b"<h1>Page</h1>")

        @rtr.post("/save", guards=(_require_badge,))
        def _save(_req: Request) -> WebResponse:
            return WebResponse(201, JSON_CONTENT_TYPE, b'{"ok":true}')

        saturated = [False]
        policy = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R0_PUBLIC,
            rules=(RingRouteRule("/save", SurfaceRing.R0_PUBLIC),),
        )
        states_sf: list[WebAppState] = []
        app = create_web_app(
            routers=(rtr,), surface_access_policy=policy, allowed_hosts=("portal.localhost",),
            cors_policy=CORSPolicy(allow_origins=("https://ui.example.org",)),
            middlewares=(_tag_mw,), critical_r3_safe_mode=True, state_out=states_sf,
            bulkhead_load_provider=lambda _st: ContextLoadSnapshot(
                utilization_ratio=0.95 if saturated[0] else 0.10,
                active_heavy_tasks=2 if saturated[0] else 0,
            ),
        )  # fmt: skip
        h_valid = {"host": "portal.localhost", "origin": "https://ui.example.org"}

        async def _run() -> dict[str, Any]:
            st_host, _, _ = await _invoke(app, "GET", "/page", headers={"host": "evil.example"})
            pf_h = {**h_valid, "access-control-request-method": "POST"}
            st_pf, h_pf, _ = await _invoke(app, "OPTIONS", "/save", headers=pf_h)
            _, h_g1, _ = await _invoke(
                app, "GET", "/page", headers={**h_valid, "x-zcg-peer-node": "peer-01"}
            )
            ck_val = h_g1["set-cookie"].split(";", 1)[0].partition("=")[2]
            ck_h = {**h_valid, "cookie": f"{CSRF_COOKIE}={ck_val}"}
            _, h_g2, _ = await _invoke(app, "GET", "/page", headers=ck_h)
            ck_val2 = h_g2["set-cookie"].split(";", 1)[0].partition("=")[2]
            mut_h = {**ck_h, CSRF_HEADER: ck_val}
            st_guard, _, _ = await _invoke(app, "POST", "/save", headers=mut_h)
            st_save, h_save, _ = await _invoke(
                app, "POST", "/save", headers={**mut_h, "x-badge": "ok"}
            )
            saturated[0] = True
            st_503, _, _ = await _invoke(app, "GET", "/page", headers=h_valid)
            saturated[0] = False
            for _ in range(12):
                states_sf[0].signal_collector.record(
                    method="GET", route="/err", status_code=503, latency_ms=2500.0
                )
            st_crit, _, b_crit = await _invoke(
                app, "GET", "/page", headers=h_valid, client=("198.51.100.8", 52000)
            )
            return {
                "st_host": st_host, "st_pf": st_pf, "same_ck": ck_val == ck_val2,
                "pf_aco": h_pf.get("access-control-allow-origin"), "st_guard": st_guard,
                "st_save": st_save, "mw": h_save.get("x-mw"),
                "aco": h_save.get("access-control-allow-origin"), "st_503": st_503,
                "st_crit": st_crit, "crit_err": json.loads(b_crit)["error"],
            }  # fmt: skip

        # Act
        out = asyncio.run(_run())

        # Assert
        assert out["st_host"] == 400 and out["st_pf"] == 204
        assert out["pf_aco"] == "https://ui.example.org" and out["same_ck"] is True
        assert out["st_guard"] == 403 and out["st_save"] == 201
        assert out["mw"] == "1" and out["aco"] == "https://ui.example.org"
        assert out["st_503"] == 503 and out["st_crit"] == 503
        assert out["crit_err"] == "CRITICAL_R3_SURVIVAL_SAFE_MODE"
