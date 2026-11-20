"""Unit tests for zcg.web.auth.oidc_tokens.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from zcg.web.auth.oidc_tokens import (
    MAX_PKCE_VERIFIER_LEN,
    MIN_PKCE_VERIFIER_LEN,
    build_oidc_pkce_authorize_url,
    compute_pkce_s256_challenge,
    verify_oidc_or_proxy_jwt,
    verify_pkce_s256,
)

PROXY_ISS = "https://proxy.idp.example"
OIDC_ISS = "https://sso.idp.example"
AUTH_EP = "https://sso.idp.example/authorize"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_hs256_jwt(header: dict[str, object], payload: dict[str, object], key_val: str) -> str:
    h_seg = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_seg = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(key_val.encode("utf-8"), f"{h_seg}.{p_seg}".encode("ascii"), hashlib.sha256)
    return f"{h_seg}.{p_seg}.{_b64url(sig.digest())}"


class TestOidcTokens:
    """Verify RFC 7636 S256 PKCE cutpoints, OIDC authorize URLs, and RFC 7519 JWT claims."""

    def test_pkce_s256_and_oidc_proxy_jwt_verification_cutpoints_expected(self) -> None:
        """Verify RFC 7636 PKCE S256 bounds, RFC OIDC URL builder, and OIDC/proxy JWT checks."""
        # Arrange
        min_v, max_v = "a" * MIN_PKCE_VERIFIER_LEN, "Z" * MAX_PKCE_VERIFIER_LEN
        key_val, aud = "proxy-key-iso-01", "https://node.example.org"
        issuers = (PROXY_ISS, OIDC_ISS)
        claims: dict[str, object] = {
            "iss": PROXY_ISS,
            "aud": [aud, "alt"],
            "sub": "idp:99",
            "email": "idp:Dev@Example.org",
            "exp": 1000,
            "iat": 900,
            "groups": ["eng@example.org"],
        }
        tok = _make_hs256_jwt({"alg": "HS256"}, claims, key_val)
        es_payload = _b64url(
            json.dumps({**claims, "iss": OIDC_ISS, "aud": aud, "hd": "org.io"}).encode()
        )
        es_tok = f"{_b64url(b'{"alg":"ES256"}')}.{es_payload}.{_b64url(b'sig-ok')}"

        # Act
        ch_min, ch_max = compute_pkce_s256_challenge(min_v), compute_pkce_s256_challenge(max_v)
        url_hd = build_oidc_pkce_authorize_url(
            authorization_endpoint=AUTH_EP,
            client_id="cid",
            redirect_uri="https://n.io/cb",
            state="s1",
            code_challenge=ch_min,
            domain_hint="org.io",
            domain_hint_param="hd",
        )
        url_no_hd = build_oidc_pkce_authorize_url(
            authorization_endpoint=AUTH_EP,
            client_id="cid",
            redirect_uri="https://n.io/cb",
            state="s1",
            code_challenge=ch_min,
        )
        ok_proxy = verify_oidc_or_proxy_jwt(
            tok,
            expected_audience=aud,
            allowed_issuers=issuers,
            assertion_key=key_val,
            extra_groups_header="ops@example.org",
            domain_infer_issuers=(PROXY_ISS,),
            now=1060.0,
        )
        ok_es = verify_oidc_or_proxy_jwt(
            es_tok,
            expected_audience=aud,
            allowed_issuers=issuers,
            signature_verifier=lambda _m, raw_s, hdr: (
                hdr.get("alg") == "ES256" and raw_s == b"sig-ok"
            ),
            now=950.0,
        )

        # Assert
        assert verify_pkce_s256(min_v, ch_min) and verify_pkce_s256(max_v, ch_max)
        assert not verify_pkce_s256(min_v, "") and not verify_pkce_s256("a" * 42, ch_min)
        assert not verify_pkce_s256("a" * 129, ch_min) and not verify_pkce_s256(
            "bad space!" + min_v, ch_min
        )
        assert "hd=org.io" in url_hd and "hd=" not in url_no_hd
        assert ok_proxy is not None and ok_proxy.email == "dev@example.org"
        assert ok_proxy.hosted_domain == "example.org"
        assert ok_proxy.groups == ("eng@example.org", "ops@example.org")
        assert ok_es is not None and ok_es.hosted_domain == "org.io"
        assert (
            verify_oidc_or_proxy_jwt(
                tok, expected_audience=aud, allowed_issuers=issuers, assertion_key=key_val, now=1061
            )
            is None
        )
        assert (
            verify_oidc_or_proxy_jwt(
                tok, expected_audience=aud, allowed_issuers=issuers, assertion_key=key_val, now=839
            )
            is None
        )
        assert (
            verify_oidc_or_proxy_jwt(
                "bad.tok", expected_audience=aud, allowed_issuers=issuers, assertion_key=key_val
            )
            is None
        )
        assert (
            verify_oidc_or_proxy_jwt(
                tok, expected_audience=aud, allowed_issuers=(), assertion_key=key_val, now=950.0
            )
            is None
        )
        assert (
            verify_oidc_or_proxy_jwt(
                tok.rsplit(".", 1)[0] + ".%",
                expected_audience=aud,
                allowed_issuers=issuers,
                assertion_key=key_val,
            )
            is None
        )
        assert verify_oidc_or_proxy_jwt(tok, expected_audience=aud, allowed_issuers=issuers) is None
        bad_iss = _make_hs256_jwt({"alg": "HS256"}, {**claims, "iss": "https://bad.io"}, key_val)
        bad_aud = _make_hs256_jwt({"alg": "HS256"}, {**claims, "aud": "wrong"}, key_val)
        no_email = _make_hs256_jwt({"alg": "HS256"}, {**claims, "email": ""}, key_val)
        unver_email = _make_hs256_jwt(
            {"alg": "HS256"}, {**claims, "email_verified": False}, key_val
        )
        oidc_no_hd = _make_hs256_jwt(
            {"alg": "HS256"},
            {
                "iss": OIDC_ISS,
                "aud": aud,
                "email": "persona@mail.example",
                "email_verified": True,
                "exp": 1000,
            },
            key_val,
        )
        ok_no_hd = verify_oidc_or_proxy_jwt(
            oidc_no_hd,
            expected_audience=aud,
            allowed_issuers=issuers,
            assertion_key=key_val,
            domain_infer_issuers=(PROXY_ISS,),
            now=950.0,
        )
        ok_inferred = verify_oidc_or_proxy_jwt(
            oidc_no_hd,
            expected_audience=aud,
            allowed_issuers=issuers,
            assertion_key=key_val,
            infer_domain_from_email=True,
            now=950.0,
        )
        assert ok_no_hd is not None and ok_no_hd.hosted_domain == ""
        assert ok_inferred is not None and ok_inferred.hosted_domain == "mail.example"
        for bad_t in (unver_email, bad_iss, bad_aud, no_email):
            assert (
                verify_oidc_or_proxy_jwt(
                    bad_t,
                    expected_audience=aud,
                    allowed_issuers=issuers,
                    assertion_key=key_val,
                    now=950.0,
                )
                is None
            )
        with pytest.raises(ValueError, match="code_verifier"):
            compute_pkce_s256_challenge("short")
        with pytest.raises(ValueError, match="client_id"):
            build_oidc_pkce_authorize_url(
                authorization_endpoint=AUTH_EP,
                client_id="",
                redirect_uri="https://n.io/cb",
                state="s1",
                code_challenge=ch_min,
            )
