"""Unit tests for zcg.web.auth.surface_access.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from zcg.web.auth.security import (
    CSRF_HEADER,
    PROXY_GROUPS_HEADER,
    PROXY_JWT_HEADER,
    SESSION_COOKIE,
)
from zcg.web.auth.surface_access import (
    DISCLOSURE_TIER_HEADER,
    GUEST_GRANT_HEADER,
    PEER_NODE_HEADER,
    SURFACE_RING_HEADER,
    ExternalSubjectKind,
    RingRouteRule,
    SlidingWindowRateLimiter,
    SurfaceAccessError,
    SurfaceAccessPolicy,
    SurfaceRing,
    issue_scoped_surface_grant,
)

PROXY_ISS = "https://proxy.idp.example"
OIDC_ISS = "https://sso.idp.example"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_jwt(payload: dict[str, object], key_val: str) -> str:
    h_seg = _b64url(b'{"alg":"HS256"}')
    p_seg = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(key_val.encode("utf-8"), f"{h_seg}.{p_seg}".encode("ascii"), hashlib.sha256)
    return f"{h_seg}.{p_seg}.{_b64url(sig.digest())}"


class TestSurfaceAccess:
    """Verify R0..R3 capability rings, scoped external grants, IAP/OIDC mapping, and rate limits."""

    def test_surface_ring_ranks_labels_and_sliding_rate_limiter_cutpoints_expected(self) -> None:
        """Verify SurfaceRing ranks/labels and SlidingWindowRateLimiter N vs N+1 cut-points."""
        # Arrange
        limiter = SlidingWindowRateLimiter(max_requests=2, window_sec=10.0)

        # Act
        ok_1, r_1 = limiter.check_and_record("client-a", now=100.0)
        ok_2, r_2 = limiter.check_and_record("client-a", now=104.0)
        blocked_3, r_3 = limiter.check_and_record("client-a", now=104.2)
        ok_4, r_4 = limiter.check_and_record("client-a", now=110.1)

        # Assert
        assert SurfaceRing.R0_PUBLIC.ring_rank == 0 and SurfaceRing.R0_PUBLIC.label == "public"
        assert (
            SurfaceRing.R3_OPERATOR.ring_rank == 3 and SurfaceRing.R3_OPERATOR.label == "operator"
        )
        assert limiter.max_requests == 2 and limiter.window_sec == 10.0
        assert (ok_1, r_1, ok_2, r_2) == (True, 0, True, 0)
        assert (blocked_3, r_3, ok_4, r_4) == (False, 6, True, 0)
        with pytest.raises(ValueError, match="max_requests"):
            SlidingWindowRateLimiter(max_requests=0)
        with pytest.raises(ValueError, match="window_sec"):
            SlidingWindowRateLimiter(window_sec=0.0)

    def test_r0_to_r3_policy_enforcement_and_disclosure_ceilings_expected(self) -> None:
        """Verify R0..R3 route rules, guest/linked-peer R1 scoping, R2 IAP/OIDC, and R3 operator."""
        # Arrange
        sess_k, iap_k, csrf_v = "sess-iso-key", "iap-iso-key", "csrf-iso-01"
        aud = "/projects/1/apps/node"
        policy = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R2_NETWORK_MEMBER,
            rules=(
                RingRouteRule("/public/*", SurfaceRing.R0_PUBLIC),
                RingRouteRule(
                    "/partner/*",
                    SurfaceRing.R1_SCOPED_EXTERNAL,
                    allowed_external_subjects=(ExternalSubjectKind.LINKED_PEER,),
                ),
                RingRouteRule(
                    "/guest/*",
                    SurfaceRing.R1_SCOPED_EXTERNAL,
                    allowed_external_subjects=(ExternalSubjectKind.GUEST,),
                ),
                RingRouteRule("/admin/*", SurfaceRing.R3_OPERATOR),
            ),
            session_key=sess_k,
            allowed_linked_peers={"peer-alpha": "peer-tok-01"},
            peer_allowed_routes=("/partner/*",),
            oidc_expected_audience=aud,
            oidc_assertion_key=iap_k,
            oidc_allowed_issuers=(PROXY_ISS, OIDC_ISS),
            domain_infer_issuers=(PROXY_ISS,),
            allowed_workspace_domains=("example.org",),
            allowed_workspace_groups=("squad@example.org",),
            operator_emails=("root@example.org",),
            member_emails=("direct@example.org",),
            r0_rate_limiter=SlidingWindowRateLimiter(max_requests=1, window_sec=30.0),
        )
        guest_g = issue_scoped_surface_grant(
            signing_key=sess_k,
            subject_id="guest-01",
            ring=SurfaceRing.R1_SCOPED_EXTERNAL,
            external_kind=ExternalSubjectKind.GUEST,
            allowed_routes=("/guest/brief",),
            disclosure_tier="core_summary",
            expires_at=500.0,
        )
        exp_g = issue_scoped_surface_grant(
            signing_key=sess_k,
            subject_id="guest-exp",
            ring=SurfaceRing.R1_SCOPED_EXTERNAL,
            external_kind=ExternalSubjectKind.GUEST,
            expires_at=400.0,
        )
        op_ck = issue_scoped_surface_grant(
            signing_key=sess_k, subject_id="op-sess", ring=SurfaceRing.R3_OPERATOR
        )
        mem_j = _make_jwt(
            {"iss": PROXY_ISS, "aud": aud, "email": "dev@example.org", "exp": 600}, iap_k
        )
        dir_j = _make_jwt(
            {"iss": PROXY_ISS, "aud": aud, "email": "direct@example.org", "exp": 600}, iap_k
        )
        op_j = _make_jwt(
            {"iss": PROXY_ISS, "aud": aud, "email": "root@example.org", "exp": 600}, iap_k
        )
        out_j = _make_jwt(
            {"iss": PROXY_ISS, "aud": aud, "email": "ext@other.org", "exp": 600}, iap_k
        )

        # Act
        r0_hz = policy.enforce(method="GET", path="/healthz", headers={}, cookies={}, now=450.0)
        r0_in = policy.enforce(
            method="POST",
            path="/public/intake",
            headers={CSRF_HEADER: csrf_v},
            cookies={},
            client_host="198.51.100.10",
            expected_csrf=csrf_v,
            now=450.0,
        )
        r1_gu = policy.enforce(
            method="GET",
            path="/guest/brief",
            headers={GUEST_GRANT_HEADER: guest_g},
            cookies={},
            now=500.0,
        )
        r1_pr = policy.enforce(
            method="GET",
            path="/partner/spec",
            headers={PEER_NODE_HEADER: "peer-alpha", "authorization": "Bearer peer-tok-01"},
            cookies={},
            now=450.0,
        )
        r2_gp = policy.enforce(
            method="GET",
            path="/dashboard",
            headers={PROXY_JWT_HEADER: mem_j, PROXY_GROUPS_HEADER: "squad@example.org"},
            cookies={},
            now=500.0,
        )
        r2_dr = policy.enforce(
            method="GET",
            path="/dashboard",
            headers={"authorization": f"Bearer {dir_j}"},
            cookies={},
            now=500.0,
        )
        r3_jw = policy.enforce(
            method="GET", path="/admin/cfg", headers={PROXY_JWT_HEADER: op_j}, cookies={}, now=500.0
        )
        r3_ck = policy.enforce(
            method="GET", path="/admin/cfg", headers={}, cookies={SESSION_COOKIE: op_ck}, now=500.0
        )

        # Assert
        assert r0_hz == {SURFACE_RING_HEADER: "R0", DISCLOSURE_TIER_HEADER: "core_summary"}
        assert r0_in[SURFACE_RING_HEADER] == "R0"
        assert r1_gu == {SURFACE_RING_HEADER: "R1", DISCLOSURE_TIER_HEADER: "core_summary"}
        assert r1_pr == {SURFACE_RING_HEADER: "R1", DISCLOSURE_TIER_HEADER: "verified_competency"}
        assert r2_gp == {SURFACE_RING_HEADER: "R2", DISCLOSURE_TIER_HEADER: "day1_onboarding"}
        assert r2_dr[SURFACE_RING_HEADER] == "R2"
        assert r3_jw == {SURFACE_RING_HEADER: "R3", DISCLOSURE_TIER_HEADER: "deep_context"}
        assert r3_ck[SURFACE_RING_HEADER] == "R3"

        with pytest.raises(SurfaceAccessError) as rl_err:
            policy.enforce(
                method="POST",
                path="/public/intake",
                headers={CSRF_HEADER: csrf_v},
                cookies={},
                client_host="198.51.100.10",
                expected_csrf=csrf_v,
                now=455.0,
            )
        assert rl_err.value.http_status == 429 and "retry-after" in rl_err.value.response_headers
        for bad_call, exp_code in (
            (
                {
                    "method": "POST",
                    "path": "/public/x",
                    "headers": {},
                    "cookies": {},
                    "expected_csrf": csrf_v,
                    "now": 450.0,
                },
                "CSRF_VALIDATION_FAILED",
            ),
            (
                {
                    "method": "GET",
                    "path": "/dashboard",
                    "headers": {GUEST_GRANT_HEADER: exp_g},
                    "cookies": {},
                    "now": 450.0,
                },
                "SURFACE_AUTH_REQUIRED",
            ),
            (
                {
                    "method": "GET",
                    "path": "/dashboard",
                    "headers": {PROXY_JWT_HEADER: out_j},
                    "cookies": {},
                    "now": 500.0,
                },
                "SURFACE_AUTH_REQUIRED",
            ),
            (
                {
                    "method": "GET",
                    "path": "/dashboard",
                    "headers": {PROXY_JWT_HEADER: mem_j},
                    "cookies": {},
                    "now": 500.0,
                },
                "SURFACE_AUTH_REQUIRED",
            ),
            (
                {
                    "method": "GET",
                    "path": "/admin/cfg",
                    "headers": {GUEST_GRANT_HEADER: guest_g},
                    "cookies": {},
                    "now": 450.0,
                },
                "SURFACE_RING_FORBIDDEN",
            ),
            (
                {
                    "method": "GET",
                    "path": "/partner/spec",
                    "headers": {GUEST_GRANT_HEADER: guest_g},
                    "cookies": {},
                    "now": 450.0,
                },
                "SURFACE_EXTERNAL_SUBJECT_FORBIDDEN",
            ),
            (
                {
                    "method": "GET",
                    "path": "/guest/other",
                    "headers": {GUEST_GRANT_HEADER: guest_g},
                    "cookies": {},
                    "now": 450.0,
                },
                "SURFACE_ROUTE_SCOPE_FORBIDDEN",
            ),
        ):
            with pytest.raises(SurfaceAccessError) as exc_info:
                policy.enforce(**bad_call)  # type: ignore[arg-type]
            assert exc_info.value.error_code == exp_code

    def test_scoped_external_emails_grant_groups_and_required_groups_expected(self) -> None:
        """Verify scoped_external_emails R1 JWTs, grant groups, and required_groups 403/200."""
        # Arrange
        sess_k, iap_k, aud = "grp-sess", "grp-iap", "zcg-aud"
        pol = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R2_NETWORK_MEMBER,
            rules=(
                RingRouteRule(
                    "/fin/ledger", SurfaceRing.R2_NETWORK_MEMBER, required_groups=("dept-finance",)
                ),
                RingRouteRule("/cv/private", SurfaceRing.R1_SCOPED_EXTERNAL),
            ),
            session_key=sess_k,
            oidc_expected_audience=aud,
            oidc_assertion_key=iap_k,
            oidc_allowed_issuers=(OIDC_ISS,),
            allowed_workspace_domains=("corp-alpha.net",),
            scoped_external_emails=("persona@mail.example",),
        )
        ext_jwt = _make_jwt(
            {
                "iss": OIDC_ISS,
                "aud": aud,
                "email": "persona@mail.example",
                "email_verified": True,
                "exp": 600,
            },
            iap_k,
        )
        fin_ck = issue_scoped_surface_grant(
            signing_key=sess_k,
            subject_id="fin@corp-alpha.net",
            ring=SurfaceRing.R2_NETWORK_MEMBER,
            groups=("dept-finance",),
        )
        ops_ck = issue_scoped_surface_grant(
            signing_key=sess_k,
            subject_id="ops@corp-alpha.net",
            ring=SurfaceRing.R2_NETWORK_MEMBER,
            groups=("dept-ops",),
        )

        # Act
        r1_ok = pol.enforce(
            method="GET",
            path="/cv/private",
            headers={PROXY_JWT_HEADER: ext_jwt},
            cookies={},
            now=500.0,
        )
        r2_fin = pol.enforce(
            method="GET",
            path="/fin/ledger",
            headers={},
            cookies={SESSION_COOKIE: fin_ck},
            now=500.0,
        )

        # Assert
        assert r1_ok[SURFACE_RING_HEADER] == "R1"
        assert r2_fin[SURFACE_RING_HEADER] == "R2"
        with pytest.raises(SurfaceAccessError) as grp_err:
            pol.enforce(
                method="GET",
                path="/fin/ledger",
                headers={},
                cookies={SESSION_COOKIE: ops_ck},
                now=500.0,
            )
        assert grp_err.value.error_code == "SURFACE_GROUP_FORBIDDEN"

    def test_loopback_bypass_and_rule_grant_validation_errors_expected(self) -> None:
        """Verify loopback operator mode, grant fallbacks, and invalid rule/grant guards."""
        # Arrange
        sess_k, open_k = "loop-key", "open-key"
        bad_r1 = _b64url(b'{"ring":"R1","sub":"x"}')
        bad_r1_sig = hmac.new(sess_k.encode(), bad_r1.encode(), hashlib.sha256).hexdigest()
        bad_t = _b64url(b'{"ring":"R2","sub":"x","tier":"unknown"}')
        bad_t_sig = hmac.new(sess_k.encode(), bad_t.encode(), hashlib.sha256).hexdigest()
        loop_policy = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R3_OPERATOR,
            rules=(RingRouteRule("/only-post", SurfaceRing.R0_PUBLIC, methods=("POST",)),),
            session_key=sess_k,
            allowed_linked_peers={"peer-a": "tok-a"},
            oidc_expected_audience="/projects/1/apps/open",
            oidc_assertion_key=open_k,
            oidc_allowed_issuers=(PROXY_ISS,),
            domain_infer_issuers=(PROXY_ISS,),
            loopback_operator_bypass=True,
        )
        no_rl_policy = SurfaceAccessPolicy(
            default_ring=SurfaceRing.R0_PUBLIC,
            rules=(RingRouteRule("/open-post", SurfaceRing.R0_PUBLIC),),
        )
        open_j = _make_jwt(
            {
                "iss": PROXY_ISS,
                "aud": "/projects/1/apps/open",
                "email": "any@org.io",
                "exp": 900,
            },
            open_k,
        )

        # Act
        by_ip = loop_policy.enforce(
            method="GET", path="/only-post", headers={}, cookies={}, client_host="127.0.0.1"
        )
        by_sub = loop_policy.enforce(
            method="GET",
            path="/admin",
            headers={"host": "dev.node.localhost:8710", PROXY_JWT_HEADER: "invalid.jwt.tok"},
            cookies={},
        )
        by_bad_tier = loop_policy.authenticate_request(
            headers={GUEST_GRANT_HEADER: f"{bad_t}.{bad_t_sig}"}, cookies={}
        )
        by_invalid = loop_policy.authenticate_request(
            headers={
                GUEST_GRANT_HEADER: f"{bad_r1}.{bad_r1_sig}",
                PEER_NODE_HEADER: "peer-a",
                "authorization": "Bearer wrong",
            },
            cookies={},
        )
        by_open_iap = loop_policy.authenticate_request(
            headers={PROXY_JWT_HEADER: open_j}, cookies={}, now=850.0
        )
        no_rl_post = no_rl_policy.enforce(method="POST", path="/open-post", headers={}, cookies={})

        # Assert
        assert by_ip[SURFACE_RING_HEADER] == "R3" and by_sub[SURFACE_RING_HEADER] == "R3"
        assert by_bad_tier.max_disclosure_tier == "core_summary"
        assert by_invalid.ring == SurfaceRing.R0_PUBLIC
        assert by_open_iap.ring == SurfaceRing.R2_NETWORK_MEMBER
        assert no_rl_post[SURFACE_RING_HEADER] == "R0"
        with pytest.raises(ValueError, match="path_pattern"):
            RingRouteRule(" ", SurfaceRing.R0_PUBLIC)
        with pytest.raises(ValueError, match="disclosure_tier"):
            RingRouteRule("/ok", SurfaceRing.R0_PUBLIC, disclosure_tier="invalid")
        with pytest.raises(ValueError, match="subject_id"):
            issue_scoped_surface_grant(
                signing_key=sess_k, subject_id=" ", ring=SurfaceRing.R2_NETWORK_MEMBER
            )
        with pytest.raises(ValueError, match="R0"):
            issue_scoped_surface_grant(
                signing_key=sess_k, subject_id="u", ring=SurfaceRing.R0_PUBLIC
            )
        with pytest.raises(ValueError, match="external_kind"):
            issue_scoped_surface_grant(
                signing_key=sess_k, subject_id="u", ring=SurfaceRing.R1_SCOPED_EXTERNAL
            )
        with pytest.raises(ValueError, match="disclosure_tier"):
            issue_scoped_surface_grant(
                signing_key=sess_k,
                subject_id="u",
                ring=SurfaceRing.R2_NETWORK_MEMBER,
                disclosure_tier="bad",
            )
