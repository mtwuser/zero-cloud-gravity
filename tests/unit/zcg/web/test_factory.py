"""Unit tests for zcg.web.factory.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from zcg.web.channels import CHANNEL_HEADER, DeliveryChannel
from zcg.web.factory import WebAppState, create_web_app
from zcg.web.request import (
    HTML_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    Message,
    Request,
    Scope,
    WebResponse,
)
from zcg.web.router import APIRouter
from zcg.web.security import CSRF_HEADER, DocsAccessMode, WebAppError


async def _invoke(
    app: Any,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, str], bytes]:
    raw_h = [(k.encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": raw_h,
    }

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
