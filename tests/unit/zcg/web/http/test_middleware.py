"""Unit tests for zcg.web.http.middleware.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio

import pytest

from zcg.web.auth.security import WebAppError
from zcg.web.http.middleware import (
    CORSPolicy,
    NextHandler,
    compose_http_pipeline,
    enforce_allowed_hosts,
    make_bulkhead_middleware,
    run_route_guards,
    validate_host_header,
)
from zcg.web.http.request import Request, WebResponse
from zcg.web.ops.resilience import BulkheadIsolationGuard, ContextLoadSnapshot


def _req(
    path: str = "/items", method: str = "GET", headers: dict[str, str] | None = None
) -> Request:
    raw = [(k.encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": method, "path": path, "headers": raw})


class TestMiddleware:
    """Verify HTTP middleware composition, route guards, Host allowlist, CORS, and bulkhead."""

    def test_compose_http_pipeline_and_sync_async_route_guards_order_expected(self) -> None:
        """Execute middlewares and sync/async route guards in outer-to-inner registration order."""
        # Arrange
        trace: list[str] = []

        def _sync_guard(_r: Request) -> None:
            trace.append("guard-sync")

        async def _async_guard(_r: Request) -> None:
            await asyncio.sleep(0)
            trace.append("guard-async")

        async def _mw_outer(req: Request, nxt: NextHandler) -> WebResponse:
            trace.append("mw1-in")
            res = await nxt(req)
            trace.append("mw1-out")
            return res

        async def _mw_inner(req: Request, nxt: NextHandler) -> WebResponse:
            trace.append("mw2-in")
            res = await nxt(req)
            trace.append("mw2-out")
            return res

        async def _terminal(req: Request) -> WebResponse:
            await run_route_guards((_sync_guard, _async_guard), req)
            trace.append("handler")
            return WebResponse(200, body=b"ok")

        pipeline = compose_http_pipeline((_mw_outer, _mw_inner), _terminal)

        # Act
        resp = asyncio.run(pipeline(_req()))

        # Assert
        assert resp.status == 200 and resp.body == b"ok"
        assert trace == [
            "mw1-in",
            "mw2-in",
            "guard-sync",
            "guard-async",
            "handler",
            "mw2-out",
            "mw1-out",
        ]

    def test_validate_and_enforce_allowed_hosts_patterns_ipv6_and_invalid_headers_expected(
        self,
    ) -> None:
        """Accept exact, wildcard, subdomain, and IPv6 hosts while rejecting poisoned headers."""
        # Arrange
        allow = (" ", "portal.example.org", "*.corp.local", ".mesh.internal", "[::1]")

        # Act
        enforce_allowed_hosts({}, ())
        enforce_allowed_hosts({"host": "portal.example.org:8443"}, allow)
        ok_exact = validate_host_header("PORTAL.example.org.", allow)
        ok_star_sub = validate_host_header("api.corp.local:8080", allow)
        bad_star_bare = validate_host_header("corp.local", allow)
        ok_dot_bare = validate_host_header("mesh.internal", allow)
        ok_dot_sub = validate_host_header("node1.mesh.internal", allow)
        ok_ipv6 = validate_host_header("[::1]:8000", allow)
        ok_wildcard = validate_host_header("any.domain.test", ("*",))
        bad_blank = validate_host_header("   ", ("*",))
        bad_chars = validate_host_header("evil.org/path", ("*",))
        bad_port = validate_host_header("portal.example.org:notaport", allow)
        bad_empty_host = validate_host_header(":8000", ("*",))
        bad_dot_only = validate_host_header("x.org", ("*.", ".", "other.org"))
        with pytest.raises(WebAppError, match="Invalid or untrusted HTTP Host") as exc_host:
            enforce_allowed_hosts({"host": "attacker.example"}, allow)

        # Assert
        assert ok_exact and ok_star_sub and not bad_star_bare
        assert ok_dot_bare and ok_dot_sub and ok_ipv6 and ok_wildcard
        assert not bad_blank and not bad_chars and not bad_port
        assert not bad_empty_host and not bad_dot_only
        assert exc_host.value.http_status == 400
        assert exc_host.value.error_code == "INVALID_HOST_HEADER"

    def test_cors_policy_credentials_invariant_origin_headers_and_preflight_expected(
        self,
    ) -> None:
        """Block wildcard+credentials and emit exact/wildcard CORS and preflight responses."""
        # Arrange
        cred_cors = CORSPolicy(
            allow_origins=("https://app.example.org/",),
            allow_credentials=True,
            expose_headers=("x-trace",),
        )
        open_cors = CORSPolicy(allow_origins=("*",), expose_headers=())
        nocred_cors = CORSPolicy(allow_origins=("https://pub.example.org",))

        # Act
        h_blank = cred_cors.resolve_origin_headers("  ")
        h_match = cred_cors.resolve_origin_headers("https://app.example.org")
        h_nocred = nocred_cors.resolve_origin_headers("https://pub.example.org")
        h_miss = cred_cors.resolve_origin_headers("https://evil.example.org")
        h_open = open_cors.resolve_origin_headers("https://any.example.org")
        pf_none = cred_cors.handle_preflight("GET", {"origin": "https://app.example.org"})
        pf_ok = cred_cors.handle_preflight(
            "OPTIONS",
            {"origin": "https://app.example.org", "access-control-request-method": "POST"},
        )
        pf_deny = cred_cors.handle_preflight(
            "OPTIONS",
            {"origin": "https://evil.example.org", "access-control-request-method": "POST"},
        )
        with pytest.raises(ValueError, match="must not be empty"):
            CORSPolicy(allow_origins=("   ",))
        with pytest.raises(ValueError, match="CORS_WILDCARD_CREDENTIALS_FORBIDDEN"):
            CORSPolicy(allow_origins=("*",), allow_credentials=True)
        with pytest.raises(ValueError, match="max_age_sec must be >= 0") as exc_age:
            CORSPolicy(allow_origins=("https://app.example.org",), max_age_sec=-1)

        # Assert
        assert h_blank == {} and h_miss == {}
        assert h_match["access-control-allow-origin"] == "https://app.example.org"
        assert h_match["access-control-allow-credentials"] == "true"
        assert "access-control-allow-credentials" not in h_nocred
        assert h_match["access-control-expose-headers"] == "x-trace"
        assert h_open == {"access-control-allow-origin": "*"}
        assert pf_none is None
        assert pf_ok is not None and pf_ok.status == 204
        assert "POST" in pf_ok.headers["access-control-allow-methods"]
        assert pf_deny is not None and pf_deny.status == 403
        assert exc_age.value is not None

    def test_make_bulkhead_middleware_sheds_saturated_requests_except_healthz_expected(
        self,
    ) -> None:
        """Raise 503 BULKHEAD_SHIELDED under saturation while keeping /healthz and open load OK."""
        # Arrange
        guard = BulkheadIsolationGuard(saturation_threshold=0.80)
        load_box = [ContextLoadSnapshot(utilization_ratio=0.95, active_heavy_tasks=2)]
        mw = make_bulkhead_middleware(guard, lambda: load_box[0])

        async def _ok(_r: Request) -> WebResponse:
            return WebResponse(200, body=b"ready")

        # Act
        hz_resp = asyncio.run(mw(_req("/healthz"), _ok))
        with pytest.raises(WebAppError, match="deferring to T2") as exc_503:
            asyncio.run(mw(_req("/api/items"), _ok))
        load_box[0] = ContextLoadSnapshot(utilization_ratio=0.20, active_heavy_tasks=0)
        open_resp = asyncio.run(mw(_req("/api/items"), _ok))

        # Assert
        assert hz_resp.status == 200 and open_resp.status == 200
        assert exc_503.value.http_status == 503
        assert exc_503.value.error_code == "BULKHEAD_SHIELDED"
