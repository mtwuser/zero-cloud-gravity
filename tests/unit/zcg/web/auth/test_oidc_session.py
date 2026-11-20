"""Unit tests for zcg.web.auth.oidc_session.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from zcg.web.auth.oidc_session import (
    PKCE_COOKIE,
    OidcSessionConfig,
    create_oidc_session_router,
    render_identity_posture_bar_html,
    resolve_oidc_principal_from_claims,
)
from zcg.web.auth.oidc_tokens import VerifiedOidcClaims
from zcg.web.auth.security import CSRF_HEADER, SESSION_COOKIE, sign_cookie_value
from zcg.web.auth.surface_access import SurfaceAccessPolicy, SurfacePrincipal, SurfaceRing
from zcg.web.http.factory import create_web_app
from zcg.web.http.request import ASGIApp, Message

OIDC_ISS = "https://sso.zerocloudgravity.org"
OIDC_AUTH_EP = "https://sso.zerocloudgravity.org/authorize"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _make_oidc_jwt(claims: dict[str, Any], secret: str) -> str:
    h_b64 = _b64url(b'{"alg":"HS256","typ":"JWT"}')
    p_b64 = _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), f"{h_b64}.{p_b64}".encode("ascii"), hashlib.sha256)
    return f"{h_b64}.{p_b64}.{_b64url(sig.digest())}"


async def _call_app(
    app: ASGIApp,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    scheme: str = "http",
) -> tuple[int, dict[str, str], bytes]:
    raw_h = [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("latin1"),
        "headers": raw_h,
        "scheme": scheme,
        "client": ("127.0.0.1", 51000),
    }
    sent = False
    out: list[Message] = []

    async def _recv() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def _send(msg: Message) -> None:
        out.append(msg)

    await app(scope, _recv, _send)
    st = int(out[0]["status"])
    resp_h = {
        bytes(k).decode("latin1").lower(): bytes(v).decode("latin1")
        for k, v in out[0].get("headers", [])
    }
    resp_b = b"".join(bytes(m.get("body", b"")) for m in out[1:])
    return st, resp_h, resp_b


class TestOidcSession:
    """Verify RFC OIDC S256 PKCE session elevation, ring mapping, and loopback guards."""

    def test_config_validation_and_claims_to_ring_mapping_expected(self) -> None:
        """Verify monotonic R3/R2/R1/R0 principal resolution and blank signing key guard."""
        # Arrange
        cfg = OidcSessionConfig(
            session_signing_key="sess-secret-01",
            authorization_endpoint=OIDC_AUTH_EP,
            allowed_issuers=(OIDC_ISS,),
            client_id="client-01",
            allowed_workspace_domains=("corp-alpha.net",),
            allowed_workspace_groups=("dept-finance",),
            operator_emails=("admin@corp-alpha.net",),
            member_emails=("contractor@external.example",),
            scoped_external_emails=("persona@mail.example",),
        )
        c_r3 = VerifiedOidcClaims("s1", "admin@corp-alpha.net", "corp-alpha.net", OIDC_ISS, "a", ())
        c_r2_dom = VerifiedOidcClaims(
            "s2", "fin@corp-alpha.net", "corp-alpha.net", OIDC_ISS, "a", ("dept-finance",)
        )
        c_r2_mem = VerifiedOidcClaims(
            "s3", "contractor@external.example", "", OIDC_ISS, "a", ("dept-ops",)
        )
        c_r1 = VerifiedOidcClaims("s4", "persona@mail.example", "", OIDC_ISS, "a", ())
        c_r0 = VerifiedOidcClaims("s5", "visitor@mail.example", "", OIDC_ISS, "a", ())

        # Act
        p_r3 = resolve_oidc_principal_from_claims(c_r3, cfg)
        p_r2_d = resolve_oidc_principal_from_claims(c_r2_dom, cfg)
        p_r2_m = resolve_oidc_principal_from_claims(c_r2_mem, cfg)
        p_r1 = resolve_oidc_principal_from_claims(c_r1, cfg)
        p_r0 = resolve_oidc_principal_from_claims(c_r0, cfg)
        bar_https = render_identity_posture_bar_html(
            p_r2_d, login_enabled=True, dev_switch_enabled=False, is_https=True
        )

        # Assert
        assert cfg.login_enabled is True
        assert cfg.effective_audience == "client-01"
        assert p_r3.ring == SurfaceRing.R3_OPERATOR
        assert p_r2_d.ring == SurfaceRing.R2_NETWORK_MEMBER and p_r2_d.groups == ("dept-finance",)
        assert p_r2_m.ring == SurfaceRing.R2_NETWORK_MEMBER
        assert p_r1.ring == SurfaceRing.R1_SCOPED_EXTERNAL
        assert p_r0.ring == SurfaceRing.R0_PUBLIC
        assert "HTTPS / TLS 1.3 Verified" in str(bar_https)
        assert "Sign Out" in str(bar_https)
        with pytest.raises(ValueError, match="session_signing_key"):
            OidcSessionConfig(session_signing_key="   ")

    def test_pkce_login_callback_elevation_and_r0_unlisted_account_expected(self) -> None:
        """Verify S256 PKCE login redirect, callback verification, Secure cookie, and R0 reset."""
        # Arrange
        sess_k, jwt_k, csrf_t = "pkce-sess-k", "jwt-hs256-k", "csrf-tok-1"
        cfg = OidcSessionConfig(
            session_signing_key=sess_k,
            authorization_endpoint=OIDC_AUTH_EP,
            allowed_issuers=(OIDC_ISS,),
            client_id="zcg-client-id",
            redirect_uri="/auth/oidc/callback",
            domain_hint="zerocloudgravity.org",
            domain_hint_param="hd",
            jwt_assertion_key=jwt_k,
            operator_emails=("zcg@zerocloudgravity.org",),
        )
        cfg_abs = OidcSessionConfig(
            session_signing_key=sess_k,
            authorization_endpoint=OIDC_AUTH_EP,
            allowed_issuers=(OIDC_ISS,),
            client_id="zcg-client-id",
            redirect_uri="https://zerocloudgravity.org/auth/oidc/callback",
            jwt_assertion_key=jwt_k,
        )
        app = create_web_app(
            routers=(create_oidc_session_router(cfg, csrf_token=csrf_t),), csrf_token=csrf_t
        )
        app_abs = create_web_app(routers=(create_oidc_session_router(cfg_abs),), csrf_token=csrf_t)
        verifier = "v" * 48
        chal = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        now_ts = time.time()
        pkce_cookie = sign_cookie_value(
            {
                "state": "st-ok",
                "challenge": chal,
                "return_to": "/portal",
                "exp": now_ts + 300,
            },
            sess_k,
        )
        op_jwt = _make_oidc_jwt(
            {
                "iss": OIDC_ISS,
                "aud": "zcg-client-id",
                "email": "zcg@zerocloudgravity.org",
                "email_verified": True,
                "hd": "zerocloudgravity.org",
                "exp": now_ts + 300,
            },
            jwt_k,
        )
        anon_jwt = _make_oidc_jwt(
            {
                "iss": OIDC_ISS,
                "aud": "zcg-client-id",
                "email": "stranger@other.example",
                "email_verified": True,
                "exp": now_ts + 300,
            },
            jwt_k,
        )

        # Act
        st_login, h_login, _ = asyncio.run(
            _call_app(
                app,
                "GET",
                "/auth/oidc/login",
                query="return_to=//evil.example",
                headers={"host": "zerocloudgravity.org"},
                scheme="https",
            )
        )
        st_abs, h_abs, _ = asyncio.run(
            _call_app(app_abs, "GET", "/auth/oidc/login", scheme="https")
        )
        cb_q = urlencode({"state": "st-ok", "code_verifier": verifier, "id_token": op_jwt})
        st_cb, h_cb, _ = asyncio.run(
            _call_app(
                app,
                "GET",
                "/auth/oidc/callback",
                query=cb_q,
                headers={"cookie": f"{PKCE_COOKIE}={pkce_cookie}"},
                scheme="https",
            )
        )
        sess_val = h_cb["set-cookie"].split(";", 1)[0].partition("=")[2]
        st_sess, _, b_sess = asyncio.run(
            _call_app(
                app,
                "GET",
                "/auth/session",
                headers={"cookie": f"{SESSION_COOKIE}={sess_val}", "accept": "text/html"},
                scheme="https",
            )
        )
        cb_anon_q = urlencode({"state": "st-ok", "code_verifier": verifier, "id_token": anon_jwt})
        st_cb_r0, h_cb_r0, _ = asyncio.run(
            _call_app(
                app,
                "GET",
                "/auth/oidc/callback",
                query=cb_anon_q,
                headers={"cookie": f"{PKCE_COOKIE}={pkce_cookie}"},
            )
        )

        # Assert
        assert st_login == 302 and "sso.zerocloudgravity.org" in h_login["location"]
        assert "Secure" in h_login["set-cookie"]
        assert (
            st_abs == 302
            and "zerocloudgravity.org"
            in parse_qs(urlsplit(h_abs["location"]).query)["redirect_uri"][0]
        )
        assert st_cb == 302 and h_cb["location"] == "/portal"
        assert f"{SESSION_COOKIE}=" in h_cb["set-cookie"] and "Secure" in h_cb["set-cookie"]
        assert st_sess == 200 and b"<!doctype html>" in b_sess and b"R3" in b_sess
        assert f'content="{csrf_t}"'.encode() in b_sess
        assert st_cb_r0 == 302 and "Max-Age=0" in h_cb_r0["set-cookie"]

    def test_callback_errors_unconfigured_oidc_dev_elevate_and_logout_expected(self) -> None:
        """Verify 503 unconfigured login, 400/401 callback failures, dev-elevate, and logout."""
        # Arrange
        sess_k, csrf_t = "dev-sess-k", "csrf-dev"
        pol = SurfaceAccessPolicy(default_ring=SurfaceRing.R0_PUBLIC, session_key=sess_k)
        cfg_no_oidc = OidcSessionConfig(
            session_signing_key=sess_k,
            cookie_domains=("alpha.localhost",),
            allow_dev_persona_switch=True,
        )
        app = create_web_app(
            routers=(create_oidc_session_router(cfg_no_oidc, policy=pol),), csrf_token=csrf_t
        )
        verifier = "z" * 48
        chal = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        pkce_ok = sign_cookie_value(
            {"state": "s1", "challenge": chal, "return_to": "/dashboard", "exp": time.time() + 60},
            sess_k,
        )

        # Act
        st_503, _, b_503 = asyncio.run(_call_app(app, "GET", "/auth/oidc/login"))
        st_400, _, b_400 = asyncio.run(
            _call_app(app, "GET", "/auth/oidc/callback", query="state=bad")
        )
        st_401, _, b_401 = asyncio.run(
            _call_app(
                app,
                "GET",
                "/auth/oidc/callback",
                query=urlencode({"state": "s1", "code_verifier": verifier, "id_token": "bad.tok"}),
                headers={"cookie": f"{PKCE_COOKIE}={pkce_ok}"},
            )
        )
        st_403_host, _, _ = asyncio.run(
            _call_app(
                app,
                "POST",
                "/auth/dev-elevate",
                headers={"host": "zerocloudgravity.org", CSRF_HEADER: csrf_t},
                body=b'{"ring":"R3"}',
            )
        )
        st_422, _, _ = asyncio.run(
            _call_app(
                app,
                "POST",
                "/auth/dev-elevate",
                headers={
                    "host": "node.localhost:8790",
                    "content-type": "application/json",
                    CSRF_HEADER: csrf_t,
                },
                body=b'{"ring":"R9","groups":["dept-ops"]}',
            )
        )
        st_r1_form, _, b_r1 = asyncio.run(
            _call_app(
                app,
                "POST",
                "/auth/dev-elevate",
                headers={
                    "host": "127.0.0.1:8790",
                    "content-type": "application/x-www-form-urlencoded",
                    CSRF_HEADER: csrf_t,
                },
                body=b"ring=R1&groups=guests",
            )
        )
        st_r2_json, h_r2, b_r2 = asyncio.run(
            _call_app(
                app,
                "POST",
                "/auth/dev-elevate",
                headers={
                    "host": "dev.dept.alpha.localhost:8790",
                    "content-type": "application/json",
                    CSRF_HEADER: csrf_t,
                },
                body=b'{"ring":"R2","subject_id":"fin@corp.example","groups":["dept-finance"]}',
            )
        )
        st_r0_q, h_r0, _ = asyncio.run(
            _call_app(
                app,
                "POST",
                "/auth/dev-elevate",
                query="ring=R0",
                headers={"host": "localhost:8790", CSRF_HEADER: csrf_t},
            )
        )
        st_arr, _, _ = asyncio.run(
            _call_app(
                app,
                "POST",
                "/auth/dev-elevate",
                query="ring=R3",
                headers={
                    "host": "localhost:8790",
                    "content-type": "application/json",
                    CSRF_HEADER: csrf_t,
                },
                body=b"[1, 2]",
            )
        )
        st_out, h_out, b_out = asyncio.run(
            _call_app(
                app,
                "POST",
                "/auth/logout",
                headers={"host": "localhost:8790", "hx-request": "true", CSRF_HEADER: csrf_t},
            )
        )
        bar_r0 = render_identity_posture_bar_html(
            SurfacePrincipal(SurfaceRing.R0_PUBLIC, "anonymous"),
            login_enabled=False,
            dev_switch_enabled=True,
            is_https=False,
        )

        # Assert
        assert st_503 == 503 and json.loads(b_503)["error"] == "OIDC_NOT_CONFIGURED"
        assert st_400 == 400 and json.loads(b_400)["error"] == "OIDC_PKCE_VALIDATION_FAILED"
        assert st_401 == 401 and json.loads(b_401)["error"] == "OIDC_TOKEN_INVALID"
        assert st_403_host == 403 and st_422 == 422 and st_arr == 200
        assert st_r1_form == 200 and json.loads(b_r1)["ring"] == "R1"
        assert st_r2_json == 200 and json.loads(b_r2)["groups"] == ["dept-finance"]
        assert "Domain=alpha.localhost" in h_r2["set-cookie"]
        assert st_r0_q == 200 and "Max-Age=0" in h_r0["set-cookie"]
        assert st_out == 200 and "Max-Age=0" in h_out["set-cookie"] and b"Loopback QA" in b_out
        assert "Zero-Secret Mode" in str(bar_r0)
