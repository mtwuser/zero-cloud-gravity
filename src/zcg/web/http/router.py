"""Composable APIRouter with path parameter extraction, 405 detection, and OpenAPI 3.1.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import html
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import unquote

from zcg.web.http.channels import DeliveryChannel
from zcg.web.http.request import Request, WebResponse

RouteHandler = Callable[[Request], WebResponse | Awaitable[WebResponse]]
RouteGuard = Callable[[Request], Awaitable[None] | None]
type RouteSegment = tuple[bool, str]

VALID_ROUTE_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


def _normalize_route_path(prefix: str, path: str) -> str:
    clean_prefix = prefix.strip().rstrip("/")
    clean_path = path.strip()
    if clean_prefix and not clean_prefix.startswith("/"):
        clean_prefix = f"/{clean_prefix}"
    if clean_path and not clean_path.startswith("/"):
        clean_path = f"/{clean_path}"
    combined = f"{clean_prefix}{clean_path}" or "/"
    return combined if combined == "/" else combined.rstrip("/")


@lru_cache(maxsize=256)
def _compile_path_template(
    path_template: str,
) -> tuple[tuple[RouteSegment, ...], tuple[str, ...]]:
    if path_template == "/":
        return (), ()
    segments: list[RouteSegment] = []
    param_names: list[str] = []
    for raw_seg in path_template.lstrip("/").split("/"):
        if raw_seg.startswith("{") and raw_seg.endswith("}"):
            token = raw_seg[1:-1]
            if not (token.isascii() and token.isidentifier()):
                raise ValueError(f"Invalid path parameter {raw_seg!r} in {path_template!r}")
            if token in param_names:
                raise ValueError(f"Duplicate path parameter {token!r} in {path_template!r}")
            param_names.append(token)
            segments.append((True, token))
        elif "{" in raw_seg or "}" in raw_seg:
            raise ValueError(f"Malformed path parameter {raw_seg!r} in {path_template!r}")
        else:
            segments.append((False, raw_seg))
    return tuple(segments), tuple(param_names)


def _match_route_segments(
    route_segments: tuple[RouteSegment, ...], req_segments: tuple[str, ...]
) -> dict[str, str] | None:
    if len(route_segments) != len(req_segments):
        return None
    params: dict[str, str] = {}
    for (is_param, token), actual in zip(route_segments, req_segments, strict=True):
        if is_param:
            if not actual:
                return None
            params[token] = unquote(actual)
        elif actual != token:
            return None
    return params


@dataclass(frozen=True, slots=True)
class RouteDefinition:
    """Immutable compiled HTTP route specification."""

    method: str
    path_template: str
    segments: tuple[RouteSegment, ...]
    param_names: tuple[str, ...]
    handler: RouteHandler
    channel: DeliveryChannel
    summary: str
    tags: tuple[str, ...]
    guards: tuple[RouteGuard, ...] = ()


@dataclass(frozen=True, slots=True)
class RouteMatch:
    """Resolved route definition paired with extracted URL-decoded path parameters."""

    route: RouteDefinition
    path_params: dict[str, str]


class APIRouter:
    """Composable HTTP/ASGI router supporting nested prefixes, path params, and OpenAPI 3.1."""

    def __init__(
        self,
        *,
        prefix: str = "",
        tags: Sequence[str] = (),
        default_channel: DeliveryChannel = DeliveryChannel.ISLAND_SYNC,
        guards: Sequence[RouteGuard] = (),
    ) -> None:
        self._prefix = prefix
        self._tags = tuple(tags)
        self._default_channel = default_channel
        self._guards = tuple(guards)
        self._routes: list[RouteDefinition] = []

    @property
    def prefix(self) -> str:
        """Return configured router path prefix."""
        return self._prefix

    @property
    def routes(self) -> tuple[RouteDefinition, ...]:
        """Return all registered route definitions in registration order."""
        return tuple(self._routes)

    def add_route(
        self,
        method: str,
        path: str,
        handler: RouteHandler,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
        guards: Sequence[RouteGuard] = (),
    ) -> RouteDefinition:
        """Compile and register a route definition."""
        clean_method = method.strip().upper()
        if clean_method not in VALID_ROUTE_METHODS:
            raise ValueError(f"Unsupported HTTP method {method!r}; expected {VALID_ROUTE_METHODS}")
        full_template = _normalize_route_path(self._prefix, path)
        segments, param_names = _compile_path_template(full_template)
        merged_tags = tuple(dict.fromkeys([*self._tags, *tags]))
        resolved_summary = summary or (handler.__doc__ or handler.__name__).strip().splitlines()[0]
        route_def = RouteDefinition(
            method=clean_method,
            path_template=full_template,
            segments=segments,
            param_names=param_names,
            handler=handler,
            channel=channel or self._default_channel,
            summary=resolved_summary,
            tags=merged_tags,
            guards=(*self._guards, *guards),
        )
        self._routes.append(route_def)
        return route_def

    def _decorator(
        self,
        method: str,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
        guards: Sequence[RouteGuard] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        def _register(fn: RouteHandler) -> RouteHandler:
            self.add_route(
                method, path, fn, channel=channel, summary=summary, tags=tags, guards=guards
            )
            return fn

        return _register

    def get(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
        guards: Sequence[RouteGuard] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a GET route handler."""
        return self._decorator(
            "GET", path, channel=channel, summary=summary, tags=tags, guards=guards
        )

    def post(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
        guards: Sequence[RouteGuard] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a POST route handler."""
        return self._decorator(
            "POST", path, channel=channel, summary=summary, tags=tags, guards=guards
        )

    def put(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
        guards: Sequence[RouteGuard] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a PUT route handler."""
        return self._decorator(
            "PUT", path, channel=channel, summary=summary, tags=tags, guards=guards
        )

    def patch(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
        guards: Sequence[RouteGuard] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a PATCH route handler."""
        return self._decorator(
            "PATCH", path, channel=channel, summary=summary, tags=tags, guards=guards
        )

    def delete(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
        guards: Sequence[RouteGuard] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a DELETE route handler."""
        return self._decorator(
            "DELETE", path, channel=channel, summary=summary, tags=tags, guards=guards
        )

    def include_router(
        self,
        other: APIRouter,
        *,
        prefix: str = "",
        tags: Sequence[str] = (),
        guards: Sequence[RouteGuard] = (),
    ) -> None:
        """Mount all routes from child router under optional additional prefix, tags, and guards."""
        extra_prefix = _normalize_route_path(self._prefix, prefix) if prefix else self._prefix
        for child_route in other.routes:
            full_path = _normalize_route_path(extra_prefix, child_route.path_template)
            segments, param_names = _compile_path_template(full_path)
            merged_tags = tuple(dict.fromkeys([*self._tags, *tags, *child_route.tags]))
            merged_guards = (*self._guards, *guards, *child_route.guards)
            self._routes.append(
                RouteDefinition(
                    method=child_route.method,
                    path_template=full_path,
                    segments=segments,
                    param_names=param_names,
                    handler=child_route.handler,
                    channel=child_route.channel,
                    summary=child_route.summary,
                    tags=merged_tags,
                    guards=merged_guards,
                )
            )

    def resolve(self, method: str, path: str) -> tuple[RouteMatch | None, tuple[str, ...]]:
        """Match (method, path); return (RouteMatch, ()) or (None, allowed_methods)."""
        clean_method = method.upper()
        norm_path = "/" if path in ("", "/") else path.rstrip("/")
        req_segments = () if norm_path == "/" else tuple(norm_path.lstrip("/").split("/"))
        allowed: list[str] = []
        for route in self._routes:
            params = _match_route_segments(route.segments, req_segments)
            if params is None:
                continue
            if route.method == clean_method:
                return RouteMatch(route=route, path_params=params), ()
            if route.method not in allowed:
                allowed.append(route.method)
        return None, tuple(allowed)

    def build_openapi_paths(self) -> dict[str, dict[str, Any]]:
        """Generate OpenAPI 3.1 path operation items for all registered routes."""
        paths: dict[str, dict[str, Any]] = {}
        for route in self._routes:
            op: dict[str, Any] = {
                "summary": route.summary,
                "x-delivery-channel": route.channel.value,
                "responses": {"200": {"description": "Successful response"}},
            }
            if route.tags:
                op["tags"] = list(route.tags)
            if route.param_names:
                op["parameters"] = [
                    {
                        "name": pname,
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                    for pname in route.param_names
                ]
            paths.setdefault(route.path_template, {})[route.method.lower()] = op
        return paths


def compose_openapi_document(*, title: str, version: str, root_router: APIRouter) -> dict[str, Any]:
    """Compose a complete OpenAPI 3.1 document merging built-in and router operations."""
    paths: dict[str, Any] = {
        "/healthz": {"get": {"x-delivery-channel": DeliveryChannel.STATIC_SYNC.value}},
        "/events": {"get": {"x-delivery-channel": DeliveryChannel.ISLAND_STREAM.value}},
        "/api/poll/status": {"get": {"x-delivery-channel": DeliveryChannel.SWAP_DEFERRED.value}},
        "/static/{asset_path}": {"get": {"x-delivery-channel": DeliveryChannel.STATIC_SYNC.value}},
        **root_router.build_openapi_paths(),
    }
    return {"openapi": "3.1.0", "info": {"title": title, "version": version}, "paths": paths}


def render_openapi_docs_html(title: str, version: str, paths: Mapping[str, Any]) -> str:
    """Render zero-build HTML documentation page for an OpenAPI 3.1 paths mapping."""
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
