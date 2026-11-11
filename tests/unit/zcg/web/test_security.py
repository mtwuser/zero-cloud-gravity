"""Unit tests for zcg.web.security.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from zcg.web.channels import Zone
from zcg.web.security import (
    CSRF_HEADER,
    DocsAccessMode,
    ErrorAction,
    ErrorSeverity,
    WebAppError,
    build_zone_security_headers,
    evaluate_docs_access,
    format_runtime_error_response,
    sign_cookie_value,
    verify_cookie_value,
    verify_csrf_request,
)


class TestSecurity:
    """Verify Zone CSP, CSRF, signed cookies, DocsAccessMode, and WebAppError formatting."""

    def test_zone_csp_csrf_and_docs_access_guards_expected(self) -> None:
        """Verify Z1..Z4 CSP graduation, mutating Z1/Z2 CSRF checks, and DocsAccessMode states."""
        # Arrange
        expected_tok = "tok-iso-001"
        valid_h = {CSRF_HEADER: expected_tok}
        bearer_h = {"authorization": f"Bearer {expected_tok}"}

        # Act
        z1_csp = build_zone_security_headers(Zone.Z1)["content-security-policy"]
        z4_csp = build_zone_security_headers(Zone.Z4)["content-security-policy"]
        doc_disabled = evaluate_docs_access(DocsAccessMode.DISABLED, bearer_h, expected_tok)
        doc_public = evaluate_docs_access(DocsAccessMode.PUBLIC, {}, "")
        doc_auth_ok = evaluate_docs_access(DocsAccessMode.AUTHENTICATED, bearer_h, expected_tok)
        doc_auth_bad = evaluate_docs_access(DocsAccessMode.AUTHENTICATED, {}, expected_tok)

        # Assert
        assert "script-src 'none'" in z1_csp
        assert "'wasm-unsafe-eval'" in z4_csp
        assert verify_csrf_request(
            method="GET", zone=Zone.Z2, headers={}, expected_token=expected_tok
        )
        assert verify_csrf_request(
            method="POST", zone=Zone.Z3, headers={}, expected_token=expected_tok
        )
        assert verify_csrf_request(
            method="POST", zone=Zone.Z2, headers=valid_h, expected_token=expected_tok
        )
        assert not verify_csrf_request(
            method="POST", zone=Zone.Z2, headers={}, expected_token=expected_tok
        )
        assert doc_disabled == 404
        assert doc_public == 200
        assert doc_auth_ok == 200
        assert doc_auth_bad == 401

    def test_hmac_signed_cookies_and_bipolar_verification_guards_expected(self) -> None:
        """Verify HMAC-SHA256 cookie signing, tamper rejection, and malformed payload handling."""
        # Arrange
        key_text = "iso-cookie-key-2026"
        non_json_b64 = base64.urlsafe_b64encode(b"not-json").rstrip(b"=").decode("ascii")
        non_json_sig = hmac.new(
            key_text.encode(), non_json_b64.encode("ascii"), hashlib.sha256
        ).hexdigest()
        list_b64 = base64.urlsafe_b64encode(b"[1,2]").rstrip(b"=").decode("ascii")
        list_sig = hmac.new(key_text.encode(), list_b64.encode("ascii"), hashlib.sha256).hexdigest()

        # Act
        signed = sign_cookie_value({"actor": "alex", "role": "maintainer"}, key_text)
        verified = verify_cookie_value(signed, key_text)
        empty_key = verify_cookie_value(signed, "")
        missing_dot = verify_cookie_value("malformed-token", key_text)
        tampered = verify_cookie_value(f"{signed}x", key_text)
        bad_json = verify_cookie_value(f"{non_json_b64}.{non_json_sig}", key_text)
        non_dict = verify_cookie_value(f"{list_b64}.{list_sig}", key_text)

        # Assert
        assert verified == {"actor": "alex", "role": "maintainer"}
        assert empty_key is None
        assert missing_dot is None
        assert tampered is None
        assert bad_json is None
        assert non_dict is None
        with pytest.raises(ValueError, match="secret_key must be non-empty"):
            sign_cookie_value({"actor": "alex"}, "")

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
        assert parsed["error"] == "VAL_01"
        assert parsed["action"] == "FIX_INPUT"
