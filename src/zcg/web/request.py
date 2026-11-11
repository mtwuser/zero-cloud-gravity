"""Typed ASGI Request, URL-encoded & stdlib multipart UploadFile parsers, and WebResponse.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.parser import BytesFeedParser
from email.policy import HTTP
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import parse_qs, unquote

from zcg.web.channels import (
    DeliveryChannel,
    get_swap_target,
    is_boosted_request,
    is_partial_swap_request,
    poll_status_code,
)
from zcg.web.security import ErrorAction, ErrorSeverity, WebAppError

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Coroutine[Any, Any, None]]

HTML_CONTENT_TYPE: str = "text/html; charset=utf-8"
JSON_CONTENT_TYPE: str = "application/json; charset=utf-8"


@dataclass(frozen=True, slots=True)
class UploadFile:
    """Immutable in-memory uploaded file extracted from a multipart/form-data stream."""

    field_name: str
    filename: str
    content_type: str
    data: bytes

    @property
    def size(self) -> int:
        """Return payload byte length."""
        return len(self.data)


@dataclass(frozen=True, slots=True)
class MultipartFormData:
    """Parsed multipart/form-data fields and uploaded files."""

    fields: dict[str, list[str]]
    files: dict[str, list[UploadFile]]

    def get_field(self, name: str, default: str = "") -> str:
        """Return the first text value for field name, or default if absent."""
        vals = self.fields.get(name)
        return vals[0] if vals else default

    def get_file(self, name: str) -> UploadFile | None:
        """Return the first UploadFile for field name, or None if absent."""
        items = self.files.get(name)
        return items[0] if items else None


def _parse_cookies(cookie_header: str) -> dict[str, str]:
    if not cookie_header:
        return {}
    jar = SimpleCookie()
    jar.load(cookie_header)
    return {key: morsel.value for key, morsel in jar.items()}


def _raise_payload_too_large(max_bytes: int) -> NoReturn:
    raise WebAppError(
        f"Request payload exceeds {max_bytes} bytes",
        error_code="PAYLOAD_TOO_LARGE",
        http_status=int(HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
        severity=ErrorSeverity.WARNING,
        action=ErrorAction.FIX_INPUT,
    )


async def read_bounded_body(
    receive: Receive, req_headers: Mapping[str, str], max_bytes: int
) -> bytes:
    """Read ASGI http.request chunks up to max_bytes, raising 413 WebAppError on overflow."""
    cl_raw = req_headers.get("content-length")
    if cl_raw and cl_raw.isdigit() and int(cl_raw) > max_bytes:
        _raise_payload_too_large(max_bytes)
    chunks: list[bytes] = []
    total = 0
    while True:
        event = await receive()
        chunk = bytes(event.get("body", b""))
        total += len(chunk)
        if total > max_bytes:
            _raise_payload_too_large(max_bytes)
        chunks.append(chunk)
        if not event.get("more_body", False):
            return b"".join(chunks)


class Request:
    """Typed HTTP/ASGI request wrapper with JSON, URL-encoded form, and multipart parsers."""

    def __init__(
        self,
        scope: Scope,
        body: bytes = b"",
        *,
        path_params: Mapping[str, str] | None = None,
    ) -> None:
        self._method = str(scope.get("method", "GET")).upper()
        self._path = unquote(str(scope.get("path", "/")) or "/")
        self._raw_query = bytes(scope.get("query_string", b"")).decode("latin1")
        self._query_params = parse_qs(self._raw_query, keep_blank_values=True)
        self._headers = {
            bytes(k).decode("latin1").lower(): bytes(v).decode("latin1")
            for k, v in scope.get("headers", [])
        }
        self._cookies = _parse_cookies(self._headers.get("cookie", ""))
        self._path_params = dict(path_params or {})
        self._body = body

    @property
    def method(self) -> str:
        """Return uppercase HTTP method."""
        return self._method

    @property
    def path(self) -> str:
        """Return URL-decoded request path."""
        return self._path

    @property
    def raw_query(self) -> str:
        """Return raw query string without leading '?'."""
        return self._raw_query

    @property
    def query_params(self) -> dict[str, list[str]]:
        """Return parsed multi-value query string dictionary."""
        return self._query_params

    @property
    def path_params(self) -> dict[str, str]:
        """Return extracted route path parameters."""
        return self._path_params

    @property
    def headers(self) -> dict[str, str]:
        """Return lowercase HTTP request headers."""
        return self._headers

    @property
    def cookies(self) -> dict[str, str]:
        """Return parsed request cookies."""
        return self._cookies

    @property
    def body(self) -> bytes:
        """Return raw request body bytes."""
        return self._body

    @property
    def content_type(self) -> str:
        """Return raw content-type header or empty string."""
        return self._headers.get("content-type", "")

    @property
    def is_partial_swap(self) -> bool:
        """Return True when hx-request header indicates a partial DOM swap."""
        return is_partial_swap_request(self._headers)

    @property
    def is_boosted(self) -> bool:
        """Return True when hx-boosted header indicates boosted navigation."""
        return is_boosted_request(self._headers)

    @property
    def swap_target(self) -> str | None:
        """Return target DOM selector from hx-target header, if present."""
        return get_swap_target(self._headers)

    def query(self, name: str, default: str = "") -> str:
        """Return the first query parameter value for name, or default."""
        vals = self._query_params.get(name)
        return vals[0] if vals else default

    def json(self) -> Any:
        """Decode UTF-8 JSON body or raise 400 INVALID_JSON WebAppError."""
        try:
            return json.loads(self._body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebAppError(
                "Invalid JSON request payload",
                error_code="INVALID_JSON",
                http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            ) from exc

    def form_multi(self) -> dict[str, list[str]]:
        """Parse application/x-www-form-urlencoded body into multi-value lists."""
        if not self._body:
            return {}
        return parse_qs(self._body.decode("utf-8", errors="replace"), keep_blank_values=True)

    def form(self) -> dict[str, str]:
        """Parse application/x-www-form-urlencoded body into single-value strings."""
        return {k: vals[0] for k, vals in self.form_multi().items()}

    def multipart(self) -> MultipartFormData:
        """Parse multipart/form-data body using Python stdlib email.parser.BytesFeedParser."""
        ct_low = self.content_type.lower()
        if "multipart/form-data" not in ct_low or "boundary=" not in ct_low:
            raise WebAppError(
                "Expected multipart/form-data content-type with boundary",
                error_code="INVALID_MULTIPART",
                http_status=int(HTTPStatus.BAD_REQUEST),
                severity=ErrorSeverity.WARNING,
                action=ErrorAction.FIX_INPUT,
            )
        envelope = f"Content-Type: {self.content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode(
            "latin1"
        )
        parser = BytesFeedParser(EmailMessage, policy=HTTP)
        parser.feed(envelope + self._body)
        msg = parser.close()
        fields: dict[str, list[str]] = {}
        files: dict[str, list[UploadFile]] = {}
        for part in msg.iter_parts():
            raw_name = part.get_param("name", header="content-disposition")
            if not isinstance(raw_name, str) or not raw_name:
                continue
            data = bytes(part.get_payload(decode=True) or b"")
            raw_fn = part.get_filename()
            if raw_fn is not None:
                safe_fn = Path(raw_fn.replace("\\", "/")).name or "upload.bin"
                up = UploadFile(
                    field_name=raw_name,
                    filename=safe_fn,
                    content_type=part.get_content_type(),
                    data=data,
                )
                files.setdefault(raw_name, []).append(up)
            else:
                fields.setdefault(raw_name, []).append(data.decode("utf-8", errors="replace"))
        return MultipartFormData(fields=fields, files=files)


@dataclass(frozen=True, slots=True)
class WebResponse:
    """Immutable HTTP/ASGI response descriptor carrying status, body, and DeliveryChannel."""

    status: int = int(HTTPStatus.OK)
    content_type: str = JSON_CONTENT_TYPE
    body: bytes = b""
    channel: DeliveryChannel = DeliveryChannel.ISLAND_SYNC
    headers: dict[str, str] = field(default_factory=dict)


def respond(
    request: Request,
    *,
    html_fragment: str,
    data: object = None,
    full_html: str | None = None,
    status: int = int(HTTPStatus.OK),
    channel: DeliveryChannel | None = None,
    headers: Mapping[str, str] | None = None,
) -> WebResponse:
    """Return adaptive SWAP_SYNC fragment, full HTML page, or JSON API payload."""
    hdrs = dict(headers or {})
    if request.is_partial_swap and (not request.is_boosted or full_html is None):
        eff_ch = channel or DeliveryChannel.SWAP_SYNC
        return WebResponse(status, HTML_CONTENT_TYPE, html_fragment.encode("utf-8"), eff_ch, hdrs)
    if full_html is not None:
        eff_ch = channel or DeliveryChannel.ISLAND_SYNC
        return WebResponse(status, HTML_CONTENT_TYPE, full_html.encode("utf-8"), eff_ch, hdrs)
    eff_ch = channel or DeliveryChannel.ISLAND_SYNC
    payload = json.dumps(data if data is not None else {}, default=str).encode("utf-8")
    return WebResponse(status, JSON_CONTENT_TYPE, payload, eff_ch, hdrs)


def respond_poll(
    request: Request,
    *,
    done: bool,
    html_fragment: str,
    data: object = None,
    headers: Mapping[str, str] | None = None,
) -> WebResponse:
    """Return HTTP 200 while polling or HTTP 286 on completion over SWAP_DEFERRED."""
    st = poll_status_code(done=done)
    hdrs = dict(headers or {})
    if request.is_partial_swap:
        return WebResponse(
            st,
            HTML_CONTENT_TYPE,
            html_fragment.encode("utf-8"),
            DeliveryChannel.SWAP_DEFERRED,
            hdrs,
        )
    payload_obj = data if data is not None else {"done": done, "http_status": st}
    return WebResponse(
        st,
        JSON_CONTENT_TYPE,
        json.dumps(payload_obj, default=str).encode("utf-8"),
        DeliveryChannel.SWAP_DEFERRED,
        hdrs,
    )


def respond_empty(
    *,
    status: int = int(HTTPStatus.OK),
    channel: DeliveryChannel = DeliveryChannel.SWAP_SYNC,
    headers: Mapping[str, str] | None = None,
) -> WebResponse:
    """Return an empty body response (e.g. DOM element removal after DELETE)."""
    return WebResponse(status, HTML_CONTENT_TYPE, b"", channel, dict(headers or {}))
