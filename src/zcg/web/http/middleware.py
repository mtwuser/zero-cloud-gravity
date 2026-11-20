"""Composable ASGI HTTP middleware, route guards, Host allowlist, CORS, and bulkhead shield.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Final
from urllib.parse import urlsplit

from zcg.web.auth.security import ErrorAction, ErrorSeverity, WebAppError
from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import JSON_CONTENT_TYPE, Request, WebResponse
from zcg.web.http.router import RouteGuard
from zcg.web.ops.resilience import BulkheadIsolationGuard, BulkheadStatus, ContextLoadSnapshot

NextHandler = Callable[[Request], Coroutine[Any, Any, WebResponse]]
HTTPMiddleware = Callable[[Request, NextHandler], Coroutine[Any, Any, WebResponse]]

DEFAULT_CORS_METHODS: Final[tuple[str, ...]] = (
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
)
DEFAULT_CORS_HEADERS: Final[tuple[str, ...]] = (
    "content-type",
    "authorization",
    "x-zcg-csrf-token",
    "hx-request",
    "hx-target",
)
DEFAULT_CORS_EXPOSE_HEADERS: Final[tuple[str, ...]] = ("x-delivery-channel",)
DEFAULT_CORS_MAX_AGE_SEC: Final[int] = 600
_FORBIDDEN_HOST_CHARS: Final[frozenset[str]] = frozenset("/\\?#@,")


async def run_route_guards(guards: Sequence[RouteGuard], req: Request) -> None:
    """Execute synchronous or asynchronous route guards in outer-to-inner registration order."""
    for guard in guards:
        outcome = guard(req)
        if inspect.isawaitable(outcome):
            await outcome


def compose_http_pipeline(
    middlewares: Sequence[HTTPMiddleware], terminal: NextHandler
) -> NextHandler:
    """Compose HTTP middlewares around a terminal async handler in outer-to-inner order."""
    handler = terminal
    for mw in reversed(middlewares):
        prev = handler

        async def _layer(
            req: Request, _mw: HTTPMiddleware = mw, _next: NextHandler = prev
        ) -> WebResponse:
            return await _mw(req, _next)

        handler = _layer
    return handler


def validate_host_header(host_header: str, allowed_hosts: Sequence[str]) -> bool:
    """Validate an incoming HTTP Host header against exact, IPv6, or subdomain patterns."""
    clean = host_header.strip()
    if not clean or any(ord(c) <= 32 or ord(c) == 127 or c in _FORBIDDEN_HOST_CHARS for c in clean):
        return False
    parts = urlsplit(f"//{clean}")
    try:
        _ = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        return False
    for raw_pat in allowed_hosts:
        pat = raw_pat.strip().lower()
        if not pat:
            continue
        if pat == "*":
            return True
        pat_host = (
            pat.removeprefix("[").removesuffix("]")
            if pat.startswith("[") and pat.endswith("]")
            else pat.rstrip(".")
        )
        if pat_host.startswith("*."):
            suffix = pat_host.removeprefix("*")
            if len(suffix) > 1 and host.endswith(suffix):
                return True
        elif pat_host.startswith("."):
            bare = pat_host.removeprefix(".")
            if bare and (host == bare or host.endswith(pat_host)):
                return True
        elif host == pat_host:
            return True
    return False


def enforce_allowed_hosts(headers: Mapping[str, str], allowed_hosts: Sequence[str]) -> None:
    """Raise 400 INVALID_HOST_HEADER when allowed_hosts is configured and Host fails validation."""
    if not allowed_hosts:
        return
    if not validate_host_header(headers.get("host", ""), allowed_hosts):
        raise WebAppError(
            "Invalid or untrusted HTTP Host header",
            error_code="INVALID_HOST_HEADER",
            http_status=int(HTTPStatus.BAD_REQUEST),
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
        )


@dataclass(frozen=True, slots=True)
class CORSPolicy:
    """Opt-in Cross-Origin Resource Sharing policy blocking wildcard-with-credentials."""

    allow_origins: tuple[str, ...]
    allow_methods: tuple[str, ...] = DEFAULT_CORS_METHODS
    allow_headers: tuple[str, ...] = DEFAULT_CORS_HEADERS
    expose_headers: tuple[str, ...] = DEFAULT_CORS_EXPOSE_HEADERS
    allow_credentials: bool = False
    max_age_sec: int = DEFAULT_CORS_MAX_AGE_SEC

    def __post_init__(self) -> None:
        norm = tuple(
            "*" if o.strip() == "*" else o.strip().rstrip("/")
            for o in self.allow_origins
            if o.strip()
        )
        if not norm:
            raise ValueError("CORSPolicy.allow_origins must not be empty")
        if "*" in norm and self.allow_credentials:
            raise ValueError("CORS_WILDCARD_CREDENTIALS_FORBIDDEN")
        if self.max_age_sec < 0:
            raise ValueError("CORSPolicy.max_age_sec must be >= 0")
        object.__setattr__(self, "allow_origins", norm)

    def resolve_origin_headers(self, origin: str) -> dict[str, str]:
        """Compute CORS response headers for an incoming Origin header value."""
        orig = origin.strip().rstrip("/")
        if not orig:
            return {}
        if "*" in self.allow_origins:
            hdrs: dict[str, str] = {"access-control-allow-origin": "*"}
        elif orig in self.allow_origins:
            hdrs = {"access-control-allow-origin": orig, "vary": "Origin"}
            if self.allow_credentials:
                hdrs["access-control-allow-credentials"] = "true"
        else:
            return {}
        if self.expose_headers:
            hdrs["access-control-expose-headers"] = ", ".join(self.expose_headers)
        return hdrs

    def handle_preflight(self, method: str, headers: Mapping[str, str]) -> WebResponse | None:
        """Return 204 or 403 WebResponse for OPTIONS CORS preflight requests, else None."""
        if method.upper() != "OPTIONS" or "access-control-request-method" not in headers:
            return None
        base_h = self.resolve_origin_headers(headers.get("origin", ""))
        if not base_h:
            return WebResponse(
                int(HTTPStatus.FORBIDDEN),
                JSON_CONTENT_TYPE,
                b'{"error":"CORS_ORIGIN_DENIED"}',
                DeliveryChannel.STATIC_SYNC,
            )
        pf_h = {
            **base_h,
            "access-control-allow-methods": ", ".join(self.allow_methods),
            "access-control-allow-headers": ", ".join(self.allow_headers),
            "access-control-max-age": str(self.max_age_sec),
        }
        return WebResponse(
            int(HTTPStatus.NO_CONTENT),
            "text/plain; charset=utf-8",
            b"",
            DeliveryChannel.STATIC_SYNC,
            pf_h,
        )


def make_bulkhead_middleware(
    bulkhead: BulkheadIsolationGuard,
    load_provider: Callable[[], ContextLoadSnapshot],
) -> HTTPMiddleware:
    """Create an HTTP middleware shedding saturated load with 503 BULKHEAD_SHIELDED."""

    async def _shield(req: Request, call_next: NextHandler) -> WebResponse:
        if req.path != "/healthz":
            decision = bulkhead.evaluate(load_provider())
            if decision.status == BulkheadStatus.SHIELDED:
                raise WebAppError(
                    decision.reason,
                    error_code="BULKHEAD_SHIELDED",
                    http_status=int(HTTPStatus.SERVICE_UNAVAILABLE),
                    severity=ErrorSeverity.WARNING,
                    action=ErrorAction.RETRY,
                )
        return await call_next(req)

    return _shield
