"""Unit tests for zcg.web.auth.security.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from zcg.web.auth.security import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    DocsAccessMode,
    ErrorAction,
    ErrorSeverity,
    WebAppError,
    build_zone_security_headers,
    compute_sri_sha384,
    evaluate_docs_access,
    format_runtime_error_response,
    issue_csrf_token,
    sign_cookie_value,
    verify_cookie_value,
    verify_csrf_request,
    verify_double_submit_csrf,
    verify_sri_external_assets,
)
from zcg.web.http.channels import Zone


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class TestSecurity:
    """Verify Zone CSP, SRI, CSRF, HMAC-signed cookies, DocsAccessMode, and WebAppError."""

    def test_zone_csp_csrf_and_docs_access_guards_expected(self) -> None:
        """Verify Z1..Z4 CSP graduation, mutating Z1/Z2 CSRF checks, and DocsAccessMode states."""
        # Arrange
        expected_tok = "tok-iso-001"
        valid_h = {CSRF_HEADER: expected_tok}
        bearer_h = {"authorization": f"Bearer {expected_tok}"}

        # Act
        z1_hdrs = build_zone_security_headers(Zone.Z1)
        z1_csp = z1_hdrs["content-security-policy"]
        z4_csp = build_zone_security_headers(Zone.Z4)["content-security-policy"]
        z2_https = build_zone_security_headers(Zone.Z2, is_https=True)
        doc_disabled = evaluate_docs_access(DocsAccessMode.DISABLED, bearer_h, expected_tok)
        doc_public = evaluate_docs_access(DocsAccessMode.PUBLIC, {}, "")
        doc_auth_ok = evaluate_docs_access(DocsAccessMode.AUTHENTICATED, bearer_h, expected_tok)
        doc_auth_bad = evaluate_docs_access(DocsAccessMode.AUTHENTICATED, {}, expected_tok)

        # Assert
        assert "script-src 'none'" in z1_csp
        assert "script-src 'self' 'wasm-unsafe-eval';" in z4_csp
        assert "strict-transport-security" not in z1_hdrs
        assert z1_hdrs["cross-origin-resource-policy"] == "same-origin"
        assert "camera=()" in z1_hdrs["permissions-policy"]
        assert z2_https["strict-transport-security"].startswith("max-age=63072000")
        assert "upgrade-insecure-requests" in z2_https["content-security-policy"]
        assert verify_csrf_request(
            method="GET", zone=Zone.Z2, headers={}, expected_token=expected_tok
        )
        assert verify_csrf_request(
            method="POST", zone=Zone.Z3, headers={}, expected_token=expected_tok
        )
        assert not verify_csrf_request(
            method="POST",
            zone=Zone.Z3,
            headers={"cookie": "zcg_session=s1"},
            expected_token=expected_tok,
        )
        assert not verify_csrf_request(
            method="POST",
            zone=Zone.Z4,
            headers={"sec-fetch-site": "cross-site"},
            expected_token=expected_tok,
        )
        assert not verify_csrf_request(
            method="POST",
            zone=Zone.Z3,
            headers={"origin": "null"},
            expected_token=expected_tok,
        )
        assert not verify_csrf_request(
            method="POST",
            zone=Zone.Z3,
            headers={"origin": "ftp://bad.example"},
            expected_token=expected_tok,
        )
        assert not verify_csrf_request(
            method="POST",
            zone=Zone.Z3,
            headers={"origin": "https://evil.example", "host": "portal.localhost"},
            expected_token=expected_tok,
        )
        assert verify_csrf_request(
            method="POST",
            zone=Zone.Z3,
            headers={
                "origin": "https://app.iso.example",
                "host": "api.iso.example",
                "sec-fetch-site": "same-site",
                CSRF_HEADER: expected_tok,
            },
            expected_token=expected_tok,
            allowed_origins=("https://app.iso.example",),
        )
        assert verify_csrf_request(
            method="POST",
            zone=Zone.Z3,
            headers={"origin": "https://portal.localhost", "host": "portal.localhost"},
            expected_token=expected_tok,
        )
        assert verify_csrf_request(
            method="POST", zone=Zone.Z2, headers=valid_h, expected_token=expected_tok
        )
        assert not verify_csrf_request(
            method="POST", zone=Zone.Z2, headers={}, expected_token=expected_tok
        )
        assert (doc_disabled, doc_public, doc_auth_ok, doc_auth_bad) == (404, 200, 200, 401)

    def test_double_submit_hmac_csrf_token_and_session_binding_expected(self) -> None:
        """Verify per-client Double-Submit HMAC CSRF token issuance and session binding."""
        # Arrange
        sec_key = "csrf-hmac-key-2026"
        other_tok = "unmatched-static"
        ds_tok = issue_csrf_token(sec_key, session_binding="sess-99")

        # Act
        ok_ds = verify_csrf_request(
            method="POST",
            zone=Zone.Z4,
            headers={CSRF_HEADER: ds_tok},
            expected_token=other_tok,
            cookies={CSRF_COOKIE: ds_tok, SESSION_COOKIE: "sess-99"},
            secret_key=sec_key,
        )
        bad_sess = verify_double_submit_csrf(
            ds_tok, cookie_token=ds_tok, secret_key=sec_key, session_binding="other-sess"
        )
        bad_mismatch = verify_double_submit_csrf(
            ds_tok, cookie_token=f"{ds_tok}x", secret_key=sec_key, session_binding="sess-99"
        )
        bad_empty = verify_double_submit_csrf("", cookie_token="", secret_key=sec_key)

        # Assert
        assert ok_ds is True
        assert bad_sess is False and bad_mismatch is False and bad_empty is False
        with pytest.raises(ValueError, match="secret_key must be non-empty"):
            issue_csrf_token("")

    def test_hmac_signed_cookies_and_bipolar_verification_guards_expected(self) -> None:
        """Verify HMAC-SHA256 cookie signing, tamper rejection, and malformed payload handling."""
        # Arrange
        key_text = "iso-cookie-key-2026"
        non_b64 = "%%%." + hmac.new(key_text.encode(), b"%%%", hashlib.sha256).hexdigest()
        non_json_b64 = _b64url(b"not-json")
        non_json_sig = hmac.new(
            key_text.encode(), non_json_b64.encode(), hashlib.sha256
        ).hexdigest()
        list_b64 = _b64url(b"[1,2]")
        list_sig = hmac.new(key_text.encode(), list_b64.encode(), hashlib.sha256).hexdigest()

        # Act
        signed = sign_cookie_value({"actor": "persona", "role": "maintainer"}, key_text)
        verified = verify_cookie_value(signed, key_text)

        # Assert
        assert verified == {"actor": "persona", "role": "maintainer"}
        assert verify_cookie_value(signed, "") is None
        assert verify_cookie_value("malformed-token", key_text) is None
        assert verify_cookie_value(f"{signed}x", key_text) is None
        assert verify_cookie_value(non_b64, key_text) is None
        assert verify_cookie_value(f"{non_json_b64}.{non_json_sig}", key_text) is None
        assert verify_cookie_value(f"{list_b64}.{list_sig}", key_text) is None
        with pytest.raises(ValueError, match="secret_key must be non-empty"):
            sign_cookie_value({"actor": "persona"}, "")

    def test_web_app_error_json_and_partial_html_formatting_expected(self) -> None:
        """Verify WebAppError renders escaped HTML swap alert fragments or JSON envelopes."""
        # Arrange
        err_hint = WebAppError(
            "Invalid <input>",
            error_code="VAL_01",
            http_status=422,
            severity=ErrorSeverity.WARNING,
            action=ErrorAction.FIX_INPUT,
            user_hint="Check <field>",
        )
        err_plain = WebAppError("Failure")

        # Act
        st_h, ct_h, body_h = format_runtime_error_response(err_hint, is_partial=True)
        st_p, _, body_p = format_runtime_error_response(err_plain, is_partial=True)
        st_j, ct_j, body_j = format_runtime_error_response(err_hint, is_partial=False)

        # Assert
        assert st_h == 422 and "text/html" in ct_h
        assert b"&lt;input&gt;" in body_h and b"zcg-error__hint" in body_h
        assert st_p == 500 and b"zcg-error__hint" not in body_p
        assert st_j == 422 and "application/json" in ct_j
        parsed = json.loads(body_j.decode("utf-8"))
        assert parsed["error"] == "VAL_01" and parsed["action"] == "FIX_INPUT"

    def test_cdn_csp_graduation_and_sha384_sri_verification_expected(self) -> None:
        """Verify 'self' default CSP, Zone Z1 vs Z3 CDN graduation, and sha384 SRI checks."""
        # Arrange
        js_bytes = b"export const ready = true;"
        sri = compute_sri_sha384(js_bytes)
        cdn = "https://cdn.iso.example"
        valid_html = (
            '<div data-expr="a > b">ok</div>'
            "<link rel='icon' href='https://other.example/favicon.ico'>"
            "<script src='/static/js/zcg-swap.js'></script>"
            f"<link rel=stylesheet media='(width > 600px)' href='{cdn}/app.css' "
            f"integrity='{sri}' crossorigin='anonymous'>"
            f'<script src="{cdn}/app.js" integrity="{sri}" crossorigin="use-credentials"></script>'
        )
        invalid_html = (
            '<script src="https://evil.example/x.js"></script>'
            '<link rel="stylesheet" media="(width > 600px)" href="https://evil.example/q.css">'
            f'<link rel="stylesheet" href="{cdn}/weak.css" '
            'integrity="sha256-AAAA sha384-bad! sha384-AAAA">'
        )

        # Act
        z1_cdn = build_zone_security_headers(Zone.Z1, allowed_cdn_origins=(cdn,))
        z3_cdn = build_zone_security_headers(Zone.Z3, allowed_cdn_origins=(cdn,))
        ok_issues = verify_sri_external_assets(valid_html, allowed_cdn_origins=(cdn,))
        bad_issues = verify_sri_external_assets(invalid_html, allowed_cdn_origins=(cdn,))

        # Assert
        assert sri.startswith("sha384-")
        assert "script-src 'none'" in z1_cdn["content-security-policy"]
        assert f"style-src 'self' {cdn}" in z1_cdn["content-security-policy"]
        assert f"script-src 'self' {cdn};" in z3_cdn["content-security-policy"]
        assert f"connect-src 'self' {cdn}" in z3_cdn["content-security-policy"]
        assert f"font-src 'self' {cdn}" in z3_cdn["content-security-policy"]
        assert ok_issues == []
        assert any(i.startswith("UNAUTHORIZED_CDN_ASSET_ORIGIN:") for i in bad_issues)
        assert sum(i.startswith("SRI_INTEGRITY_MISSING_OR_WEAK:") for i in bad_issues) == 3
