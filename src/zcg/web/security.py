"""Zone-graded CSP, constant-time CSRF, signed cookies, DocsAccessMode, and WebAppError.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from zcg.web.channels import BaseStrEnum, Zone

CSRF_HEADER: str = "x-zcg-csrf-token"
CSRF_COOKIE: str = "zcg_csrf"
SESSION_COOKIE: str = "zcg_session"
DEFAULT_MAX_PAYLOAD_BYTES: int = 1_048_576
SAFE_HTTP_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})


class DocsAccessMode(BaseStrEnum):
    """Access policy for /docs and /openapi.json inspection endpoints."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    DISABLED = "disabled"


class ErrorSeverity(BaseStrEnum):
    """Severity classification for structured web and API runtime errors."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ErrorAction(BaseStrEnum):
    """Suggested client recovery action for structured web and API runtime errors."""

    RETRY = "RETRY"
    FIX_INPUT = "FIX_INPUT"
    CONTACT_SUPPORT = "CONTACT_SUPPORT"
    NONE = "NONE"


_ZONE_CSP_POLICIES: dict[Zone, str] = {
    Zone.Z1: (
        "default-src 'self'; script-src 'none'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; frame-ancestors 'none'"
    ),
    Zone.Z2: (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    ),
    Zone.Z3: (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    ),
    Zone.Z4: (
        "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; "
        "img-src 'self' data: blob:; worker-src 'self' blob:; frame-ancestors 'none'"
    ),
}


def build_zone_security_headers(zone: Zone) -> dict[str, str]:
    """Build Zone-graded Content-Security-Policy and baseline browser hardening headers."""
    return {
        "content-security-policy": _ZONE_CSP_POLICIES[zone],
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "same-origin",
        "cross-origin-opener-policy": "same-origin",
    }


def verify_csrf_request(
    *,
    method: str,
    zone: Zone,
    headers: Mapping[str, str],
    expected_token: str,
) -> bool:
    """Verify constant-time CSRF token presence on mutating Z1/Z2 requests."""
    if method.upper() in SAFE_HTTP_METHODS or zone not in (Zone.Z1, Zone.Z2):
        return True
    provided = headers.get(CSRF_HEADER, "")
    return bool(expected_token and provided and hmac.compare_digest(provided, expected_token))


def sign_cookie_value(payload: Mapping[str, object], secret_key: str) -> str:
    """Encode and HMAC-SHA256 sign a JSON-serializable cookie mapping."""
    if not secret_key:
        raise ValueError("secret_key must be non-empty")
    canonical = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(canonical).rstrip(b"=").decode("ascii")
    sig = hmac.new(secret_key.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_cookie_value(signed_token: str, secret_key: str) -> dict[str, Any] | None:
    """Verify an HMAC-SHA256 signed cookie token in constant time and decode its dict payload."""
    if not secret_key or "." not in signed_token:
        return None
    b64, _, provided_sig = signed_token.partition(".")
    expected_sig = hmac.new(
        secret_key.encode("utf-8"), b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        return None
    padded = b64 + "=" * (-len(b64) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def evaluate_docs_access(
    mode: DocsAccessMode,
    headers: Mapping[str, str],
    expected_bearer: str = "",
) -> int:
    """Return HTTP status (200, 401, or 404) for /docs and /openapi.json access."""
    if mode == DocsAccessMode.DISABLED:
        return int(HTTPStatus.NOT_FOUND)
    if mode == DocsAccessMode.PUBLIC:
        return int(HTTPStatus.OK)
    auth = headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if (
        scheme.lower() == "bearer"
        and expected_bearer
        and hmac.compare_digest(token.strip(), expected_bearer)
    ):
        return int(HTTPStatus.OK)
    return int(HTTPStatus.UNAUTHORIZED)


class WebAppError(Exception):
    """Structured web/API application exception adaptable to JSON envelopes or HTML alerts."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "ZCG_RUNTIME_ERROR",
        http_status: int = int(HTTPStatus.INTERNAL_SERVER_ERROR),
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        action: ErrorAction = ErrorAction.NONE,
        user_hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.http_status = http_status
        self.severity = severity
        self.action = action
        self.user_hint = user_hint


def format_runtime_error_response(exc: WebAppError, *, is_partial: bool) -> tuple[int, str, bytes]:
    """Render a WebAppError as an escaped HTML swap alert fragment or JSON error envelope."""
    if is_partial:
        sev = html.escape(exc.severity.value.lower())
        code = html.escape(exc.error_code)
        msg = html.escape(exc.message)
        hint_html = (
            f'<p class="zcg-error__hint">{html.escape(exc.user_hint)}</p>' if exc.user_hint else ""
        )
        frag = (
            f'<div class="zcg-alert zcg-alert--{sev} zcg-error zcg-error--{sev}" '
            f'data-error-code="{code}" role="alert">'
            f'<p class="zcg-error__message">{msg}</p>{hint_html}</div>'
        )
        return exc.http_status, "text/html; charset=utf-8", frag.encode("utf-8")
    body = json.dumps(
        {
            "error": exc.error_code,
            "message": exc.message,
            "severity": exc.severity.value,
            "action": exc.action.value,
            "user_hint": exc.user_hint,
        }
    ).encode("utf-8")
    return exc.http_status, "application/json; charset=utf-8", body
