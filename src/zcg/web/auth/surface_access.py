"""Declarative R0..R3 surface capability rings, scoped external grants, and rate limits.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import hmac
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from http import HTTPStatus
from typing import Final, NoReturn

from zcg.web.auth.oidc_tokens import JwtSignatureVerifier, verify_oidc_or_proxy_jwt
from zcg.web.auth.security import (
    CSRF_HEADER,
    PROXY_GROUPS_HEADER,
    PROXY_JWT_HEADER,
    SAFE_HTTP_METHODS,
    SESSION_COOKIE,
    ErrorAction,
    ErrorSeverity,
    WebAppError,
    sign_cookie_value,
    verify_cookie_value,
)
from zcg.web.http.channels import BaseStrEnum

SURFACE_RING_HEADER: Final[str] = "x-zcg-surface-ring"
DISCLOSURE_TIER_HEADER: Final[str] = "x-zcg-disclosure-tier"
PEER_NODE_HEADER: Final[str] = "x-zcg-peer-node"
GUEST_GRANT_HEADER: Final[str] = "x-zcg-guest-grant"
DEFAULT_RATE_LIMIT_REQUESTS: Final[int] = 60
DEFAULT_RATE_LIMIT_WINDOW_SEC: Final[float] = 60.0
LOOPBACK_CLIENT_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "::1", "localhost"})
VALID_DISCLOSURE_TIERS: Final[tuple[str, ...]] = (
    "core_summary", "verified_competency", "day1_onboarding", "deep_context",
)  # fmt: skip


class SurfaceRing(BaseStrEnum):
    """Monotonic capability rings governing HTTP/ASGI web and API surfaces."""

    R0_PUBLIC = "R0"
    R1_SCOPED_EXTERNAL = "R1"
    R2_NETWORK_MEMBER = "R2"
    R3_OPERATOR = "R3"

    @property
    def ring_rank(self) -> int:
        """Return monotonic integer rank (0..3) for capability lattice comparison."""
        return _RING_RANKS[self]

    @property
    def label(self) -> str:
        """Return canonical systems-engineering ring label."""
        return _RING_LABELS[self]


class ExternalSubjectKind(BaseStrEnum):
    """Explicit subject classes permitted inside Ring R1 ('scoped-external')."""

    GUEST = "guest"
    LINKED_PEER = "linked-peer"


_RING_RANKS: Final[dict[SurfaceRing, int]] = {
    SurfaceRing.R0_PUBLIC: 0, SurfaceRing.R1_SCOPED_EXTERNAL: 1,
    SurfaceRing.R2_NETWORK_MEMBER: 2, SurfaceRing.R3_OPERATOR: 3,
}  # fmt: skip
_RING_LABELS: Final[dict[SurfaceRing, str]] = {
    SurfaceRing.R0_PUBLIC: "public", SurfaceRing.R1_SCOPED_EXTERNAL: "scoped-external",
    SurfaceRing.R2_NETWORK_MEMBER: "network-member", SurfaceRing.R3_OPERATOR: "operator",
}  # fmt: skip
RING_DEFAULT_DISCLOSURE_TIER: Final[dict[SurfaceRing, str]] = {
    SurfaceRing.R0_PUBLIC: "core_summary", SurfaceRing.R1_SCOPED_EXTERNAL: "verified_competency",
    SurfaceRing.R2_NETWORK_MEMBER: "day1_onboarding", SurfaceRing.R3_OPERATOR: "deep_context",
}  # fmt: skip


class SurfaceAccessError(WebAppError):
    """Structured surface ring authorization or rate-limit exception with HTTP headers."""

    def __init__(
        self, message: str, *, error_code: str, http_status: int,
        response_headers: Mapping[str, str] | None = None, user_hint: str | None = None,
    ) -> None:  # fmt: skip
        act = ErrorAction.RETRY if http_status == 429 else ErrorAction.NONE
        super().__init__(
            message, error_code=error_code, http_status=http_status,
            severity=ErrorSeverity.WARNING, action=act, user_hint=user_hint,
        )  # fmt: skip
        self.response_headers: dict[str, str] = dict(response_headers or {})


def _deny(msg: str, code: str, status: int, hdrs: Mapping[str, str]) -> NoReturn:
    raise SurfaceAccessError(msg, error_code=code, http_status=status, response_headers=hdrs)


class SlidingWindowRateLimiter:
    """Per-instance sliding-window rate limiter enforcing R0 public intake quotas."""

    def __init__(
        self, *, max_requests: int = DEFAULT_RATE_LIMIT_REQUESTS,
        window_sec: float = DEFAULT_RATE_LIMIT_WINDOW_SEC,
    ) -> None:  # fmt: skip
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_sec <= 0.0:
            raise ValueError("window_sec must be > 0.0")
        self._max_requests, self._window_sec = max_requests, window_sec
        self._buckets: dict[str, list[float]] = {}

    @property
    def max_requests(self) -> int:
        """Return configured maximum requests per sliding window."""
        return self._max_requests

    @property
    def window_sec(self) -> float:
        """Return sliding window duration in seconds."""
        return self._window_sec

    def check_and_record(self, bucket_key: str, *, now: float | None = None) -> tuple[bool, int]:
        """Record a request timestamp or return (False, retry_after_sec) on quota exhaustion."""
        ts = time.monotonic() if now is None else now
        retained = [t for t in self._buckets.get(bucket_key, ()) if t > ts - self._window_sec]
        if len(retained) >= self._max_requests:
            self._buckets[bucket_key] = retained
            return False, max(1, math.ceil((retained[0] + self._window_sec) - ts))
        retained.append(ts)
        self._buckets[bucket_key] = retained
        return True, 0


def issue_scoped_surface_grant(
    *, signing_key: str, subject_id: str, ring: SurfaceRing,
    external_kind: ExternalSubjectKind | None = None, allowed_routes: Sequence[str] = ("*",),
    disclosure_tier: str = "", groups: Sequence[str] = (), expires_at: float | None = None,
) -> str:  # fmt: skip
    """Issue an HMAC-SHA256 signed session or scoped R1..R3 grant token."""
    clean_sub = subject_id.strip()
    if not clean_sub:
        raise ValueError("subject_id must be non-blank")
    if ring == SurfaceRing.R0_PUBLIC:
        raise ValueError("Scoped grants require ring R1, R2, or R3 (not R0)")
    if ring == SurfaceRing.R1_SCOPED_EXTERNAL and external_kind is None:
        raise ValueError("R1 scoped grants require explicit external_kind ('guest'|'linked-peer')")
    eff_tier = disclosure_tier or RING_DEFAULT_DISCLOSURE_TIER[ring]
    if eff_tier not in VALID_DISCLOSURE_TIERS:
        raise ValueError(f"Invalid disclosure_tier {eff_tier!r}")
    clean_grps = [g.strip().lower() for g in groups if g.strip()]
    payload: dict[str, object] = {
        "sub": clean_sub, "ring": ring.value,
        "routes": [r.strip() for r in allowed_routes if r.strip()] or ["*"], "tier": eff_tier,
    }  # fmt: skip
    if clean_grps:
        payload["groups"] = clean_grps
    if external_kind is not None:
        payload["ext"] = external_kind.value
    if expires_at is not None:
        payload["exp"] = float(expires_at)
    return sign_cookie_value(payload, signing_key)


@dataclass(frozen=True, slots=True)
class RingRouteRule:
    """Declarative capability ring and minimum-disclosure binding for a route pattern."""

    path_pattern: str
    ring: SurfaceRing
    methods: tuple[str, ...] = ("*",)
    allowed_external_subjects: tuple[ExternalSubjectKind, ...] = (
        ExternalSubjectKind.GUEST, ExternalSubjectKind.LINKED_PEER,
    )  # fmt: skip
    disclosure_tier: str = ""
    required_groups: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.path_pattern.strip():
            raise ValueError("RingRouteRule.path_pattern must be non-blank")
        if self.disclosure_tier and self.disclosure_tier not in VALID_DISCLOSURE_TIERS:
            raise ValueError(f"Invalid disclosure_tier {self.disclosure_tier!r}")

    @property
    def effective_disclosure_tier(self) -> str:
        """Return explicit disclosure_tier or the ring's default ceiling."""
        return self.disclosure_tier or RING_DEFAULT_DISCLOSURE_TIER[self.ring]


@dataclass(frozen=True, slots=True)
class SurfacePrincipal:
    """Resolved request caller identity across R0..R3 capability rings."""

    ring: SurfaceRing
    subject_id: str
    external_kind: ExternalSubjectKind | None = None
    allowed_routes: tuple[str, ...] = ("*",)
    max_disclosure_tier: str = "core_summary"
    groups: tuple[str, ...] = ()


class SurfaceAccessPolicy:
    """Evaluates R0..R3 route authorization, R0 rate-limits, and DisclosureTier ceilings."""

    def __init__(
        self, *, default_ring: SurfaceRing = SurfaceRing.R2_NETWORK_MEMBER,
        rules: Sequence[RingRouteRule] = (), session_key: str = "",
        allowed_linked_peers: Mapping[str, str] | None = None,
        peer_allowed_routes: Sequence[str] = ("*",), oidc_expected_audience: str = "",
        oidc_assertion_key: str = "", oidc_allowed_issuers: Sequence[str] = (),
        proxy_jwt_headers: Sequence[str] = (PROXY_JWT_HEADER,),
        infer_domain_from_email: bool = False, domain_infer_issuers: Sequence[str] = (),
        jwt_signature_verifier: JwtSignatureVerifier | None = None,
        allowed_workspace_domains: Sequence[str] = (),
        allowed_workspace_groups: Sequence[str] = (), operator_emails: Sequence[str] = (),
        member_emails: Sequence[str] = (), scoped_external_emails: Sequence[str] = (),
        loopback_operator_bypass: bool = False,
        r0_rate_limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:  # fmt: skip
        self._default_ring, self._rules = default_ring, tuple(rules)
        self._session_key, self._peers = session_key, dict(allowed_linked_peers or {})
        self._peer_routes = tuple(peer_allowed_routes) or ("*",)
        self._oidc_aud, self._oidc_key = oidc_expected_audience, oidc_assertion_key
        self._oidc_issuers = tuple(i.strip() for i in oidc_allowed_issuers if i.strip())
        self._proxy_jwt_hdrs = tuple(h.strip().lower() for h in proxy_jwt_headers if h.strip()) or (
            PROXY_JWT_HEADER,
        )
        self._infer_dom, self._dom_infer_iss = infer_domain_from_email, tuple(domain_infer_issuers)
        self._jwt_verifier = jwt_signature_verifier
        self._domains = frozenset(d.strip().lower() for d in allowed_workspace_domains if d.strip())
        self._groups = frozenset(g.strip().lower() for g in allowed_workspace_groups if g.strip())
        self._operators = frozenset(e.strip().lower() for e in operator_emails if e.strip())
        self._members = frozenset(e.strip().lower() for e in member_emails if e.strip())
        self._externals = frozenset(e.strip().lower() for e in scoped_external_emails if e.strip())
        self._loopback_bypass, self._r0_limiter = loopback_operator_bypass, r0_rate_limiter

    def resolve_route_rule(self, method: str, path: str) -> RingRouteRule:
        """Resolve the first matching RingRouteRule or fall back to baseline R0 / default_ring."""
        up_m = method.upper()
        for rule in self._rules:
            m_ok = "*" in rule.methods or up_m in {m.upper() for m in rule.methods}
            if m_ok and fnmatchcase(path, rule.path_pattern):
                return rule
        if up_m in SAFE_HTTP_METHODS and (
            path == "/healthz" or path.startswith(("/.well-known/", "/static/"))
        ):
            return RingRouteRule(path, SurfaceRing.R0_PUBLIC)
        return RingRouteRule("*", self._default_ring)

    def authenticate_request(
        self, *, headers: Mapping[str, str], cookies: Mapping[str, str],
        client_host: str = "", now: float | None = None,
    ) -> SurfacePrincipal:  # fmt: skip
        """Resolve caller SurfacePrincipal from OIDC/proxy JWT, signed grant, peer, or loopback."""
        auth_h = headers.get("authorization", "")
        _, _, raw_bt = auth_h.partition(" ")
        bearer_tok = raw_bt.strip() if auth_h.lower().startswith("bearer ") else ""
        jwt_cand = (
            next((v for h in self._proxy_jwt_hdrs if (v := headers.get(h, "").strip())), "")
            or bearer_tok
        )
        if jwt_cand and self._oidc_aud and self._oidc_issuers:
            claims = verify_oidc_or_proxy_jwt(
                jwt_cand, expected_audience=self._oidc_aud, allowed_issuers=self._oidc_issuers,
                assertion_key=self._oidc_key, signature_verifier=self._jwt_verifier,
                extra_groups_header=headers.get(PROXY_GROUPS_HEADER, ""),
                infer_domain_from_email=self._infer_dom,
                domain_infer_issuers=self._dom_infer_iss, now=now,
            )  # fmt: skip
            if claims is not None:
                if claims.email in self._operators:
                    return SurfacePrincipal(
                        SurfaceRing.R3_OPERATOR, claims.email,
                        max_disclosure_tier="deep_context", groups=claims.groups,
                    )  # fmt: skip
                dom_ok = not self._domains or claims.hosted_domain in self._domains
                grp_ok = (not self._groups and (bool(self._domains) or not self._members)) or bool(
                    self._groups.intersection(claims.groups)
                )  # fmt: skip
                if claims.email in self._members or (dom_ok and grp_ok):
                    return SurfacePrincipal(
                        SurfaceRing.R2_NETWORK_MEMBER, claims.email,
                        max_disclosure_tier="day1_onboarding", groups=claims.groups,
                    )  # fmt: skip
                if claims.email in self._externals:
                    return SurfacePrincipal(
                        SurfaceRing.R1_SCOPED_EXTERNAL, claims.email, ExternalSubjectKind.GUEST,
                        max_disclosure_tier="verified_competency", groups=claims.groups,
                    )  # fmt: skip
        raw_grant = headers.get(GUEST_GRANT_HEADER, "") or cookies.get(SESSION_COOKIE, "")
        if raw_grant and self._session_key:
            dec = verify_cookie_value(raw_grant, self._session_key)
            ts = time.time() if now is None else now
            if dec is not None and (dec.get("exp") is None or ts <= float(dec["exp"])):
                r_map = {r.value: r for r in SurfaceRing if r != SurfaceRing.R0_PUBLIC}
                r_val = r_map.get(str(dec.get("ring") or ""))
                e_val = {k.value: k for k in ExternalSubjectKind}.get(str(dec.get("ext") or ""))
                if r_val is not None and (r_val != SurfaceRing.R1_SCOPED_EXTERNAL or e_val):
                    rts = tuple(str(x) for x in dec.get("routes", ["*"])) or ("*",)
                    raw_dg = dec.get("groups")
                    d_grps = (
                        tuple(str(g).strip().lower() for g in raw_dg if str(g).strip())
                        if isinstance(raw_dg, list) else ()
                    )  # fmt: skip
                    tr = str(dec.get("tier") or RING_DEFAULT_DISCLOSURE_TIER[r_val])
                    eff_t = tr if tr in VALID_DISCLOSURE_TIERS else "core_summary"
                    sub_s = str(dec.get("sub") or "grant")
                    return SurfacePrincipal(r_val, sub_s, e_val, rts, eff_t, d_grps)
        peer_id = headers.get(PEER_NODE_HEADER, "").strip()
        exp_peer = self._peers.get(peer_id, "") if peer_id else ""
        if exp_peer and bearer_tok and hmac.compare_digest(bearer_tok, exp_peer):
            return SurfacePrincipal(
                SurfaceRing.R1_SCOPED_EXTERNAL, peer_id,
                ExternalSubjectKind.LINKED_PEER, self._peer_routes, "verified_competency",
            )  # fmt: skip
        host_hdr = headers.get("host", "").partition(":")[0].strip().lower()
        is_loop = client_host in LOOPBACK_CLIENT_HOSTS or host_hdr.endswith(".localhost")
        if self._loopback_bypass and is_loop:
            return SurfacePrincipal(
                SurfaceRing.R3_OPERATOR, "loopback-operator", max_disclosure_tier="deep_context"
            )
        return SurfacePrincipal(SurfaceRing.R0_PUBLIC, "anonymous")

    def enforce(
        self, *, method: str, path: str, headers: Mapping[str, str],
        cookies: Mapping[str, str], client_host: str = "",
        expected_csrf: str = "", now: float | None = None,
    ) -> dict[str, str]:  # fmt: skip
        """Enforce R0..R3 ring access and return response ring + disclosure headers."""
        rule = self.resolve_route_rule(method, path)
        ring_hdr = {SURFACE_RING_HEADER: rule.ring.value}
        if rule.ring == SurfaceRing.R0_PUBLIC and method.upper() not in SAFE_HTTP_METHODS:
            if self._r0_limiter is not None:
                ok_rl, retry_s = self._r0_limiter.check_and_record(
                    f"{client_host or 'anon'}:{path}", now=now
                )
                if not ok_rl:
                    rl_hdr = {"retry-after": str(retry_s), **ring_hdr}
                    _deny("R0 rate limit exceeded", "SURFACE_RATE_LIMIT_EXCEEDED", 429, rl_hdr)
            csrf_in = headers.get(CSRF_HEADER, "")
            if expected_csrf and not (csrf_in and hmac.compare_digest(csrf_in, expected_csrf)):
                _deny("CSRF token missing or invalid", "CSRF_VALIDATION_FAILED", 403, ring_hdr)
        p = self.authenticate_request(
            headers=headers, cookies=cookies, client_host=client_host, now=now
        )
        if p.ring.ring_rank < rule.ring.ring_rank:
            if p.ring == SurfaceRing.R0_PUBLIC:
                _deny(
                    f"Authentication required for ring {rule.ring.value} ({rule.ring.label})",
                    "SURFACE_AUTH_REQUIRED", int(HTTPStatus.UNAUTHORIZED),
                    {"www-authenticate": 'Bearer realm="zcg-surface"', **ring_hdr},
                )  # fmt: skip
            _deny(
                f"Caller ring {p.ring.value} cannot access {rule.ring.value}",
                "SURFACE_RING_FORBIDDEN", int(HTTPStatus.FORBIDDEN), ring_hdr,
            )  # fmt: skip
        if rule.ring == p.ring == SurfaceRing.R1_SCOPED_EXTERNAL:
            if p.external_kind not in rule.allowed_external_subjects:
                _deny(
                    f"External subject {p.external_kind} not allowed on {path}",
                    "SURFACE_EXTERNAL_SUBJECT_FORBIDDEN", int(HTTPStatus.FORBIDDEN), ring_hdr,
                )  # fmt: skip
            if not any(fnmatchcase(path, pat) for pat in p.allowed_routes):
                _deny(
                    f"Scoped grant does not permit route {path}",
                    "SURFACE_ROUTE_SCOPE_FORBIDDEN", int(HTTPStatus.FORBIDDEN), ring_hdr,
                )  # fmt: skip
        req_grps = {g.strip().lower() for g in rule.required_groups if g.strip()}
        if req_grps and p.ring != SurfaceRing.R3_OPERATOR and not req_grps.intersection(p.groups):
            _deny(
                f"Caller lacks required departmental group for {path}",
                "SURFACE_GROUP_FORBIDDEN", int(HTTPStatus.FORBIDDEN), ring_hdr,
            )  # fmt: skip
        eff_idx = min(
            VALID_DISCLOSURE_TIERS.index(rule.effective_disclosure_tier),
            VALID_DISCLOSURE_TIERS.index(p.max_disclosure_tier),
        )
        return {**ring_hdr, DISCLOSURE_TIER_HEADER: VALID_DISCLOSURE_TIERS[eff_idx]}
