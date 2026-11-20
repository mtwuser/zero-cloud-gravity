"""RFC 7636 S256 PKCE challenges and RFC 7519 OIDC or identity-proxy JWT verification.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlencode

from zcg.web.auth.security import decode_b64url_bytes, decode_b64url_json

DEFAULT_JWT_CLOCK_SKEW_SEC: Final[int] = 60
MIN_PKCE_VERIFIER_LEN: Final[int] = 43
MAX_PKCE_VERIFIER_LEN: Final[int] = 128
_PKCE_UNRESERVED_CHARS: Final[frozenset[str]] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
JwtSignatureVerifier = Callable[[bytes, bytes, Mapping[str, Any]], bool]


@dataclass(frozen=True, slots=True)
class VerifiedOidcClaims:
    """Verified RFC 7519 OIDC or reverse-proxy identity and group claims."""

    subject: str
    email: str
    hosted_domain: str
    issuer: str
    audience: str
    groups: tuple[str, ...]


def compute_pkce_s256_challenge(code_verifier: str) -> str:
    """Compute RFC 7636 S256 PKCE code_challenge from a validated code_verifier."""
    v_len = len(code_verifier)
    if not (MIN_PKCE_VERIFIER_LEN <= v_len <= MAX_PKCE_VERIFIER_LEN) or not all(
        ch in _PKCE_UNRESERVED_CHARS for ch in code_verifier
    ):
        raise ValueError("Invalid RFC 7636 PKCE code_verifier length or charset")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_pkce_s256(code_verifier: str, expected_challenge: str) -> bool:
    """Verify an RFC 7636 S256 PKCE code_verifier against expected_challenge in constant time."""
    if not expected_challenge:
        return False
    try:
        computed = compute_pkce_s256_challenge(code_verifier)
    except ValueError:
        return False
    return hmac.compare_digest(computed, expected_challenge)


def build_oidc_pkce_authorize_url(
    *, authorization_endpoint: str, client_id: str, redirect_uri: str, state: str,
    code_challenge: str, domain_hint: str = "", domain_hint_param: str = "login_hint",
    scopes: Sequence[str] = ("openid", "email", "profile"),
) -> str:  # fmt: skip
    """Build a vendor-neutral RFC 7636 S256 PKCE OIDC authorization URL."""
    req_vals = (authorization_endpoint, client_id, redirect_uri, state, code_challenge)
    if not all(x.strip() for x in req_vals):
        raise ValueError("authorization_endpoint, client_id, redirect_uri, state, challenge blank")
    params: dict[str, str] = {
        "client_id": client_id.strip(), "redirect_uri": redirect_uri.strip(),
        "response_type": "code", "scope": " ".join(s.strip() for s in scopes if s.strip()),
        "state": state.strip(), "code_challenge": code_challenge.strip(),
        "code_challenge_method": "S256",
    }  # fmt: skip
    if domain_hint.strip() and domain_hint_param.strip():
        params[domain_hint_param.strip()] = domain_hint.strip().lower()
    return f"{authorization_endpoint.strip()}?{urlencode(params)}"


def verify_oidc_or_proxy_jwt(
    token: str, *, expected_audience: str, allowed_issuers: Sequence[str],
    assertion_key: str = "", signature_verifier: JwtSignatureVerifier | None = None,
    extra_groups_header: str = "", infer_domain_from_email: bool = False,
    domain_infer_issuers: Sequence[str] = (), clock_skew_sec: int = DEFAULT_JWT_CLOCK_SKEW_SEC,
    now: float | None = None,
) -> VerifiedOidcClaims | None:  # fmt: skip
    """Verify a compact RFC 7519 OIDC or identity-proxy JWT against allowed_issuers."""
    clean_aud = expected_audience.strip()
    clean_issuers = frozenset(i.strip() for i in allowed_issuers if i.strip())
    parts = token.strip().split(".")
    if len(parts) != 3 or not all(parts) or not clean_aud or not clean_issuers:
        return None
    hdr, payload = decode_b64url_json(parts[0]), decode_b64url_json(parts[1])
    sig_bytes = decode_b64url_bytes(parts[2])
    if hdr is None or payload is None or sig_bytes is None:
        return None
    signing_in = f"{parts[0]}.{parts[1]}".encode("ascii")
    if signature_verifier is not None:
        sig_ok = signature_verifier(signing_in, sig_bytes, hdr)
    elif assertion_key and hdr.get("alg") == "HS256":
        exp_sig = hmac.new(assertion_key.encode("utf-8"), signing_in, hashlib.sha256).digest()
        sig_ok = hmac.compare_digest(sig_bytes, exp_sig)
    else:
        sig_ok = False
    iss = str(payload.get("iss") or "").strip()
    if not sig_ok or iss not in clean_issuers:
        return None
    raw_aud = payload.get("aud")
    aud_ok = (isinstance(raw_aud, str) and raw_aud == clean_aud) or (
        isinstance(raw_aud, list) and clean_aud in [str(x) for x in raw_aud]
    )
    exp_v, iat_v = payload.get("exp"), payload.get("iat")
    ts = time.time() if now is None else now
    if not aud_ok or not isinstance(exp_v, (int, float)) or ts > float(exp_v) + clock_skew_sec:
        return None
    if iat_v is not None and (
        not isinstance(iat_v, (int, float)) or float(iat_v) - clock_skew_sec > ts
    ):
        return None
    raw_email = str(payload.get("email") or "").strip().lower()
    email = raw_email.rpartition(":")[2] if (":" in raw_email and "@" in raw_email) else raw_email
    if not email or payload.get("email_verified") is False:
        return None
    raw_hd = str(payload.get("hd") or payload.get("domain") or "").strip().lower()
    infer_ok = infer_domain_from_email or iss in frozenset(domain_infer_issuers)
    hd = raw_hd or (email.partition("@")[2] if infer_ok else "")
    raw_grps = payload.get("groups")
    claim_grps = [str(g).strip().lower() for g in raw_grps] if isinstance(raw_grps, list) else []
    hdr_grps = [g.strip().lower() for g in extra_groups_header.split(",") if g.strip()]
    groups = tuple(dict.fromkeys(g for g in (*claim_grps, *hdr_grps) if g))
    return VerifiedOidcClaims(str(payload.get("sub") or email), email, hd, iss, clean_aud, groups)
