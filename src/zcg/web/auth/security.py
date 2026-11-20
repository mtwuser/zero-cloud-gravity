"""Zone-graded CSP, SRI, CSRF, HMAC-signed cookies, DocsAccessMode, and WebAppError.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import html
import json
import secrets
from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from http import HTTPStatus
from typing import Any, Final
from urllib.parse import urlsplit

from zcg.core.domain import normalize_cdn_origins
from zcg.web.auth.tls import DEFAULT_HSTS_HEADER_VALUE
from zcg.web.http.channels import BaseStrEnum, Zone

CSRF_HEADER: str = "x-zcg-csrf-token"
CSRF_COOKIE: str = "zcg_csrf"
SESSION_COOKIE: str = "zcg_session"
PROXY_JWT_HEADER: Final[str] = "x-zcg-identity-assertion"
PROXY_GROUPS_HEADER: Final[str] = "x-zcg-workspace-groups"
DEFAULT_MAX_PAYLOAD_BYTES: int = 1_048_576
SAFE_HTTP_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})
_SRI_DIGEST_BYTE_LENGTHS: Final[dict[str, int]] = {"sha384": 48, "sha512": 64}


def _is_valid_sri_token(token: str) -> bool:
    alg, sep, b64_digest = token.partition("-")
    exp_bytes = _SRI_DIGEST_BYTE_LENGTHS.get(alg)
    if not sep or exp_bytes is None or not b64_digest:
        return False
    try:
        raw = base64.b64decode(b64_digest, validate=True)
    except binascii.Error:
        return False
    return len(raw) == exp_bytes


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


_BASE_CSP_TAIL: Final[str] = (
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"
)
_ZONE_CSP_POLICIES: dict[Zone, str] = {
    Zone.Z1: f"default-src 'self'; script-src 'none'; {_BASE_CSP_TAIL}",
    Zone.Z2: f"default-src 'self'; script-src 'self'; connect-src 'self'; {_BASE_CSP_TAIL}",
    Zone.Z3: f"default-src 'self'; script-src 'self'; connect-src 'self'; {_BASE_CSP_TAIL}",
    Zone.Z4: (
        "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; "
        "img-src 'self' data: blob:; worker-src 'self' blob:; frame-ancestors 'none'"
    ),
}


def compute_sri_sha384(content: bytes) -> str:
    """Compute canonical W3C Subresource Integrity sha384-<base64> digest."""
    return "sha384-" + base64.b64encode(hashlib.sha384(content).digest()).decode("ascii")


class _AssetTagCollector(HTMLParser):
    """HTML5 start-tag collector for external <script> and <link> SRI inspection."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "link"):
            self.tags.append((tag, {k: (v or "") for k, v in attrs}))


def verify_sri_external_assets(
    html_text: str, *, allowed_cdn_origins: Sequence[str] = ()
) -> list[str]:
    """Audit external <script> and stylesheet/preload <link> tags for CDN origin and sha384+ SRI."""
    allowed_set = frozenset(normalize_cdn_origins(allowed_cdn_origins))
    collector = _AssetTagCollector()
    collector.feed(html_text)
    issues: list[str] = []
    for tag, attrs in collector.tags:
        url = attrs.get("src", "") if tag == "script" else attrs.get("href", "")
        rels = set(attrs.get("rel", "").lower().split())
        if tag == "link" and not rels.intersection({"stylesheet", "preload", "modulepreload"}):
            continue
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in ("http", "https"):
            continue
        if f"{parts.scheme.lower()}://{parts.netloc.lower()}" not in allowed_set:
            issues.append(f"UNAUTHORIZED_CDN_ASSET_ORIGIN:{url}")
        sri_ok = any(_is_valid_sri_token(tok) for tok in attrs.get("integrity", "").split())
        cors_ok = attrs.get("crossorigin", "").strip().lower() in ("anonymous", "use-credentials")
        if not (sri_ok and cors_ok):
            issues.append(f"SRI_INTEGRITY_MISSING_OR_WEAK:{url}")
    return issues


DEFAULT_PERMISSIONS_POLICY: Final[str] = "camera=(), microphone=(), geolocation=(), payment=()"


def build_zone_security_headers(
    zone: Zone, *, allowed_cdn_origins: Sequence[str] = (), is_https: bool = False
) -> dict[str, str]:
    """Build Zone-graded Content-Security-Policy and baseline browser hardening headers."""
    cdn_t = normalize_cdn_origins(allowed_cdn_origins)
    csp = _ZONE_CSP_POLICIES[zone]
    if cdn_t:
        cdn_s = " " + " ".join(cdn_t)
        for tok in ("style-src 'self'", "img-src 'self'"):
            csp = csp.replace(tok, f"{tok}{cdn_s}")
        if zone != Zone.Z1:
            for tok in ("script-src 'self'", "connect-src 'self'"):
                csp = csp.replace(tok, f"{tok}{cdn_s}")
        csp = csp.replace(
            "; frame-ancestors 'none'", f"; font-src 'self'{cdn_s}; frame-ancestors 'none'"
        )
    if is_https:
        csp = f"{csp}; upgrade-insecure-requests"
    hsts = {"strict-transport-security": DEFAULT_HSTS_HEADER_VALUE} if is_https else {}
    return {
        "content-security-policy": csp, "x-content-type-options": "nosniff",
        "x-frame-options": "DENY", "referrer-policy": "same-origin",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",
        "permissions-policy": DEFAULT_PERMISSIONS_POLICY, **hsts,
    }  # fmt: skip


def issue_csrf_token(secret_key: str, *, session_binding: str = "", nonce: str = "") -> str:
    """Mint a per-client Double-Submit HMAC CSRF token optionally bound to session_binding."""
    if not secret_key:
        raise ValueError("secret_key must be non-empty")
    eff_nonce = nonce or secrets.token_urlsafe(18)
    msg = f"{eff_nonce}:{session_binding}".encode()
    sig = hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{eff_nonce}.{sig}"


def verify_double_submit_csrf(
    header_token: str, *, cookie_token: str, secret_key: str, session_binding: str = ""
) -> bool:
    """Verify Double-Submit HMAC equality and cryptographic signature in constant time."""
    if not (secret_key and header_token and cookie_token and "." in header_token):
        return False
    if not hmac.compare_digest(header_token, cookie_token):
        return False
    nonce, _, provided_sig = header_token.partition(".")
    expected_sig = hmac.new(
        secret_key.encode("utf-8"), f"{nonce}:{session_binding}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(provided_sig, expected_sig)


def _verify_fetch_metadata_and_origin(
    headers: Mapping[str, str], allowed_origins: frozenset[str]
) -> bool:
    raw_origin = headers.get("origin", "").strip()
    origin_key = ""
    if raw_origin:
        if raw_origin.lower() == "null":
            return False
        parts = urlsplit(raw_origin)
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
            return False
        origin_key = f"{parts.scheme.lower()}://{parts.netloc.lower()}"
        req_host = headers.get("host", "").strip().lower()
        if origin_key not in allowed_origins and req_host and parts.netloc.lower() != req_host:
            return False
    sfs = headers.get("sec-fetch-site", "").strip().lower()
    if sfs and sfs not in ("same-origin", "none"):
        return bool(origin_key and origin_key in allowed_origins)
    return True


def verify_csrf_request(
    *,
    method: str,
    zone: Zone,
    headers: Mapping[str, str],
    expected_token: str,
    cookies: Mapping[str, str] | None = None,
    secret_key: str = "",
    allowed_origins: Sequence[str] = (),
) -> bool:
    """Verify W3C Fetch Metadata, Origin, and Double-Submit/pinned CSRF across Z1..Z4."""
    if method.upper() in SAFE_HTTP_METHODS:
        return True
    allowed_set = frozenset(o.strip().lower().rstrip("/") for o in allowed_origins if o.strip())
    if not _verify_fetch_metadata_and_origin(headers, allowed_set):
        return False
    eff_cookies = cookies if cookies is not None else {}
    has_cookie = bool(eff_cookies) or bool(headers.get("cookie", "").strip())
    provided = headers.get(CSRF_HEADER, "").strip()
    requires_token = (
        zone in (Zone.Z1, Zone.Z2)
        or has_cookie
        or bool(headers.get("hx-request"))
        or bool(headers.get("sec-fetch-site"))
        or bool(provided)
    )
    if not requires_token:
        return True
    if expected_token and provided and hmac.compare_digest(provided, expected_token):
        return True
    return verify_double_submit_csrf(
        provided,
        cookie_token=eff_cookies.get(CSRF_COOKIE, ""),
        secret_key=secret_key,
        session_binding=eff_cookies.get(SESSION_COOKIE, ""),
    )


def sign_cookie_value(payload: Mapping[str, object], secret_key: str) -> str:
    """Encode and HMAC-SHA256 sign a JSON-serializable cookie mapping."""
    if not secret_key:
        raise ValueError("secret_key must be non-empty")
    canonical = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(canonical).rstrip(b"=").decode("ascii")
    sig = hmac.new(secret_key.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def decode_b64url_bytes(segment: str) -> bytes | None:
    """Decode an unpadded RFC 4648 base64url segment or return None when malformed."""
    padded = segment + "=" * (-len(segment) % 4)
    try:
        return base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
    except ValueError:
        return None


def decode_b64url_json(segment: str) -> dict[str, Any] | None:
    """Decode a base64url JSON dictionary segment or return None when malformed."""
    raw = decode_b64url_bytes(segment)
    if raw is None:
        return None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except ValueError, UnicodeDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


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
    return decode_b64url_json(b64)


def evaluate_docs_access(
    mode: DocsAccessMode, headers: Mapping[str, str], expected_bearer: str = ""
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
        self, message: str, *, error_code: str = "ZCG_RUNTIME_ERROR",
        http_status: int = int(HTTPStatus.INTERNAL_SERVER_ERROR),
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        action: ErrorAction = ErrorAction.NONE, user_hint: str | None = None,
    ) -> None:  # fmt: skip
        super().__init__(message)
        self.message, self.error_code, self.http_status = message, error_code, http_status
        self.severity, self.action, self.user_hint = severity, action, user_hint


def format_runtime_error_response(exc: WebAppError, *, is_partial: bool) -> tuple[int, str, bytes]:
    """Render a WebAppError as an escaped HTML swap alert fragment or JSON error envelope."""
    if is_partial:
        sev = html.escape(exc.severity.value.lower())
        code, msg = html.escape(exc.error_code), html.escape(exc.message)
        hint_html = (
            f'<p class="zcg-error__hint">{html.escape(exc.user_hint)}</p>' if exc.user_hint else ""
        )
        frag = (
            f'<div class="zcg-alert zcg-alert--{sev} zcg-error zcg-error--{sev}" '
            f'data-error-code="{code}" role="alert">'
            f'<p class="zcg-error__message">{msg}</p>{hint_html}</div>'
        )
        return exc.http_status, "text/html; charset=utf-8", frag.encode("utf-8")
    body = json.dumps({
        "error": exc.error_code, "message": exc.message, "severity": exc.severity.value,
        "action": exc.action.value, "user_hint": exc.user_hint,
    }).encode("utf-8")  # fmt: skip
    return exc.http_status, "application/json; charset=utf-8", body
