"""Unit tests for zcg.web.auth.tls (TLS 1.3 / mTLS, CIDR X-Forwarded-Proto, HSTS, Secure cookies).

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import ssl
import subprocess
from pathlib import Path

import pytest

from zcg.web.auth.tls import (
    DEFAULT_HSTS_HEADER_VALUE,
    TLSTransportConfig,
    build_server_ssl_context,
    format_set_cookie_header,
    is_https_scope,
    resolve_effective_request_scheme,
    validate_listener_transport_security,
)


def _generate_pem_pair(directory: Path, prefix: str = "server") -> tuple[Path, Path]:
    cert_path = directory / f"{prefix}.crt"
    key_path = directory / f"{prefix}.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:prime256v1",
            "-nodes",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    return cert_path, key_path


class TestTLSTransport:
    """Verify native stdlib TLS 1.3/mTLS, trusted-proxy scheme detection, and cookie flags."""

    def test_tls_transport_config_has_native_tls_reflects_complete_pem_pair(
        self, tmp_path: Path
    ) -> None:
        """Return True for has_native_tls only when both certfile and keyfile are configured."""
        # Arrange
        empty_cfg = TLSTransportConfig()
        partial_cfg = TLSTransportConfig(certfile=tmp_path / "cert.pem")
        full_cfg = TLSTransportConfig(certfile=tmp_path / "cert.pem", keyfile=tmp_path / "key.pem")

        # Act
        results = (empty_cfg.has_native_tls, partial_cfg.has_native_tls, full_cfg.has_native_tls)

        # Assert
        assert results == (False, False, True)
        assert "max-age=63072000" in DEFAULT_HSTS_HEADER_VALUE

    def test_validate_listener_transport_security_allows_loopback_and_protected_non_loopback(
        self, tmp_path: Path
    ) -> None:
        """Permit loopback HTTP while requiring native TLS or behind_tls_proxy on non-loopback."""
        # Arrange
        proxy_cfg = TLSTransportConfig(behind_tls_proxy=True)
        tls_cfg = TLSTransportConfig(certfile=tmp_path / "c.pem", keyfile=tmp_path / "k.pem")

        # Act
        validate_listener_transport_security("127.0.0.1")
        validate_listener_transport_security("[::1]")
        validate_listener_transport_security("cockpit.localhost")
        validate_listener_transport_security("198.51.100.10", proxy_cfg)
        validate_listener_transport_security("198.51.100.10", tls_cfg)

        # Assert
        assert proxy_cfg.behind_tls_proxy is True
        assert tls_cfg.has_native_tls is True

    def test_validate_listener_transport_security_rejects_invalid_or_exposed_binds(
        self, tmp_path: Path
    ) -> None:
        """Raise ValueError on mismatched PEM paths, orphan client CA, or exposed plaintext HTTP."""
        # Arrange
        orphan_cert = TLSTransportConfig(certfile=tmp_path / "c.pem")
        orphan_ca = TLSTransportConfig(client_ca_file=tmp_path / "ca.pem")
        bad_cases = (
            ("127.0.0.1", orphan_cert, "INVALID_TLS_CONFIGURATION"),
            ("127.0.0.1", orphan_ca, "INVALID_TLS_CONFIGURATION"),
            ("198.51.100.10", None, "PLAINTEXT_NON_LOOPBACK_BLOCKED"),
        )

        # Act
        caught: list[str] = []
        for host, cfg, _ in bad_cases:
            with pytest.raises(ValueError) as exc_info:
                validate_listener_transport_security(host, cfg)
            caught.append(str(exc_info.value))

        # Assert
        for msg, (_, _, expected_code) in zip(caught, bad_cases, strict=True):
            assert expected_code in msg

    def test_build_server_ssl_context_handles_disabled_and_invalid_configurations(
        self, tmp_path: Path
    ) -> None:
        """Return None when TLS is disabled and raise INVALID_TLS_CONFIGURATION on missing files."""
        # Arrange
        cert_path, _ = _generate_pem_pair(tmp_path, "partial")
        missing_cert_cfg = TLSTransportConfig(
            certfile=tmp_path / "missing.crt", keyfile=tmp_path / "missing.key"
        )
        missing_key_cfg = TLSTransportConfig(certfile=cert_path, keyfile=tmp_path / "missing.key")

        # Act
        none_default = build_server_ssl_context(None)
        none_proxy = build_server_ssl_context(TLSTransportConfig(behind_tls_proxy=True))

        # Assert
        assert none_default is None
        assert none_proxy is None
        with pytest.raises(ValueError, match="INVALID_TLS_CONFIGURATION"):
            build_server_ssl_context(TLSTransportConfig(keyfile=cert_path))
        with pytest.raises(ValueError, match="INVALID_TLS_CONFIGURATION"):
            build_server_ssl_context(TLSTransportConfig(client_ca_file=cert_path))
        with pytest.raises(ValueError, match="certfile not found"):
            build_server_ssl_context(missing_cert_cfg)
        with pytest.raises(ValueError, match="keyfile not found"):
            build_server_ssl_context(missing_key_cfg)

    def test_build_server_ssl_context_builds_tls_and_mtls_contexts(self, tmp_path: Path) -> None:
        """Load server EC certificate chain and enforce CERT_REQUIRED when client_ca_file exists."""
        # Arrange
        cert_path, key_path = _generate_pem_pair(tmp_path, "srv")
        ca_cert_path, _ = _generate_pem_pair(tmp_path, "ca")
        tls_cfg = TLSTransportConfig(certfile=cert_path, keyfile=key_path)
        mtls_cfg = TLSTransportConfig(
            certfile=cert_path, keyfile=key_path, client_ca_file=ca_cert_path
        )
        missing_ca_cfg = TLSTransportConfig(
            certfile=cert_path, keyfile=key_path, client_ca_file=tmp_path / "no_ca.crt"
        )

        # Act
        tls_ctx = build_server_ssl_context(tls_cfg)
        mtls_ctx = build_server_ssl_context(mtls_cfg)

        # Assert
        assert tls_ctx is not None
        assert tls_ctx.minimum_version == ssl.TLSVersion.TLSv1_2
        assert tls_ctx.verify_mode == ssl.CERT_NONE
        assert mtls_ctx is not None
        assert mtls_ctx.verify_mode == ssl.CERT_REQUIRED
        with pytest.raises(ValueError, match="client_ca_file not found"):
            build_server_ssl_context(missing_ca_cfg)

    def test_resolve_effective_request_scheme_validates_cidrs_hostnames_and_spoofing(self) -> None:
        """Honor X-Forwarded-Proto only from trusted proxy IPs, CIDRs, or exact hostnames."""
        # Arrange
        proxies = ("", "10.0.0.0/999", "192.168.0.0/16", "10.0.0.0/8", "ingress.internal")
        https_hdr = {"x-forwarded-proto": "https, http"}
        http_hdr = {"x-forwarded-proto": "http"}

        # Act
        s_native = resolve_effective_request_scheme(
            transport_is_tls=True, peer_host="198.51.100.8", headers={}
        )
        s_cidr = resolve_effective_request_scheme(
            transport_is_tls=False, peer_host="10.4.5.6", headers=https_hdr, trusted_proxies=proxies
        )
        s_host = resolve_effective_request_scheme(
            transport_is_tls=False,
            peer_host="ingress.internal",
            headers=https_hdr,
            trusted_proxies=proxies,
        )
        s_host_miss = resolve_effective_request_scheme(
            transport_is_tls=False,
            peer_host="other.internal",
            headers=https_hdr,
            trusted_proxies=proxies,
        )
        s_trusted_plain = resolve_effective_request_scheme(
            transport_is_tls=False, peer_host="10.4.5.6", headers=http_hdr, trusted_proxies=proxies
        )
        s_spoofed = resolve_effective_request_scheme(
            transport_is_tls=False,
            peer_host="198.51.100.8",
            headers=https_hdr,
            trusted_proxies=proxies,
        )
        s_empty_peer = resolve_effective_request_scheme(
            transport_is_tls=False, peer_host="   ", headers=https_hdr, trusted_proxies=proxies
        )

        # Assert
        assert (s_native, s_cidr, s_host) == ("https", "https", "https")
        assert (s_host_miss, s_trusted_plain, s_spoofed, s_empty_peer) == (
            "http",
            "http",
            "http",
            "http",
        )

    def test_is_https_scope_and_format_set_cookie_header_cover_all_options(self) -> None:
        """Detect HTTPS ASGI scopes and toggle Max-Age, HttpOnly, and Secure cookie attributes."""
        # Arrange
        direct_https = {"scheme": "https"}
        proxied_https = {
            "scheme": "http",
            "client": ("127.0.0.1", 43100),
            "headers": [(b"x-forwarded-proto", b"https")],
        }
        plain_http = {
            "scheme": "http",
            "client": None,
            "headers": [(b"x-forwarded-proto", b"https")],
        }

        # Act
        flags = (
            is_https_scope(direct_https),
            is_https_scope(proxied_https),
            is_https_scope(plain_http),
        )
        local_cookie = format_set_cookie_header("zcg_csrf", "tok1", is_https=False)
        prod_cookie = format_set_cookie_header(
            "zcg_sess", "tok2", is_https=True, http_only=False, max_age=3600, domain=".alpha.net"
        )

        # Assert
        assert flags == (True, True, False)
        assert local_cookie == "zcg_csrf=tok1; Path=/; SameSite=Strict; HttpOnly"
        assert (
            prod_cookie
            == "zcg_sess=tok2; Path=/; Domain=alpha.net; SameSite=Strict; Max-Age=3600; Secure"
        )
        with pytest.raises(ValueError, match="INVALID_COOKIE_DOMAIN"):
            format_set_cookie_header("zcg_sess", "bad", is_https=False, domain="alpha.net:8080")
