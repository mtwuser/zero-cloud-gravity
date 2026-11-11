"""Composable APIRouter with path parameter extraction, 405 detection, and OpenAPI 3.1.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from zcg.web.channels import DeliveryChannel
from zcg.web.request import Request, WebResponse

RouteHandler = Callable[[Request], WebResponse | Awaitable[WebResponse]]

_PARAM_TOKEN_RE: re.Pattern[str] = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
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


def _compile_path_template(path_template: str) -> tuple[re.Pattern[str], tuple[str, ...]]:
    parts = _PARAM_TOKEN_RE.split(path_template)
    regex_pieces: list[str] = ["^"]
    param_names: list[str] = []
    for idx, token in enumerate(parts):
        if idx % 2 == 0:
            regex_pieces.append(re.escape(token))
        else:
            if token in param_names:
                raise ValueError(f"Duplicate path parameter {token!r} in {path_template!r}")
            param_names.append(token)
            regex_pieces.append(f"(?P<{token}>[^/]+)")
    regex_pieces.append("$")
    return re.compile("".join(regex_pieces)), tuple(param_names)


@dataclass(frozen=True, slots=True)
class RouteDefinition:
    """Immutable compiled HTTP route specification."""

    method: str
    path_template: str
    pattern: re.Pattern[str]
    param_names: tuple[str, ...]
    handler: RouteHandler
    channel: DeliveryChannel
    summary: str
    tags: tuple[str, ...]


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
    ) -> None:
        self._prefix = prefix
        self._tags = tuple(tags)
        self._default_channel = default_channel
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
    ) -> RouteDefinition:
        """Compile and register a route definition."""
        clean_method = method.strip().upper()
        if clean_method not in VALID_ROUTE_METHODS:
            raise ValueError(f"Unsupported HTTP method {method!r}; expected {VALID_ROUTE_METHODS}")
        full_template = _normalize_route_path(self._prefix, path)
        pattern, param_names = _compile_path_template(full_template)
        merged_tags = tuple(dict.fromkeys([*self._tags, *tags]))
        resolved_summary = summary or (handler.__doc__ or handler.__name__).strip().splitlines()[0]
        route_def = RouteDefinition(
            method=clean_method,
            path_template=full_template,
            pattern=pattern,
            param_names=param_names,
            handler=handler,
            channel=channel or self._default_channel,
            summary=resolved_summary,
            tags=merged_tags,
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
    ) -> Callable[[RouteHandler], RouteHandler]:
        def _register(fn: RouteHandler) -> RouteHandler:
            self.add_route(method, path, fn, channel=channel, summary=summary, tags=tags)
            return fn

        return _register

    def get(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a GET route handler."""
        return self._decorator("GET", path, channel=channel, summary=summary, tags=tags)

    def post(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a POST route handler."""
        return self._decorator("POST", path, channel=channel, summary=summary, tags=tags)

    def put(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a PUT route handler."""
        return self._decorator("PUT", path, channel=channel, summary=summary, tags=tags)

    def patch(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a PATCH route handler."""
        return self._decorator("PATCH", path, channel=channel, summary=summary, tags=tags)

    def delete(
        self,
        path: str,
        *,
        channel: DeliveryChannel | None = None,
        summary: str = "",
        tags: Sequence[str] = (),
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a DELETE route handler."""
        return self._decorator("DELETE", path, channel=channel, summary=summary, tags=tags)

    def include_router(
        self,
        other: APIRouter,
        *,
        prefix: str = "",
        tags: Sequence[str] = (),
    ) -> None:
        """Mount all routes from child router under optional additional prefix and tags."""
        extra_prefix = _normalize_route_path(self._prefix, prefix) if prefix else self._prefix
        for child_route in other.routes:
            full_path = _normalize_route_path(extra_prefix, child_route.path_template)
            pattern, param_names = _compile_path_template(full_path)
            merged_tags = tuple(dict.fromkeys([*self._tags, *tags, *child_route.tags]))
            self._routes.append(
                RouteDefinition(
                    method=child_route.method,
                    path_template=full_path,
                    pattern=pattern,
                    param_names=param_names,
                    handler=child_route.handler,
                    channel=child_route.channel,
                    summary=child_route.summary,
                    tags=merged_tags,
                )
            )

    def resolve(self, method: str, path: str) -> tuple[RouteMatch | None, tuple[str, ...]]:
        """Match (method, path); return (RouteMatch, ()) or (None, allowed_methods)."""
        clean_method = method.upper()
        norm_path = "/" if path in ("", "/") else path.rstrip("/")
        allowed: list[str] = []
        for route in self._routes:
            m = route.pattern.match(norm_path)
            if m is None:
                continue
            if route.method == clean_method:
                params = {k: unquote(v) for k, v in m.groupdict().items()}
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
