"""Transport TLS 1.3 / mTLS, CIDR-gated X-Forwarded-Proto, HSTS, and Secure cookie formatting.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import ipaddress
import ssl
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from zcg.core.domain import is_safe_host

DEFAULT_HSTS_HEADER_VALUE: Final[str] = "max-age=63072000; includeSubDomains"
LOOPBACK_BIND_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "::1", "localhost"})
DEFAULT_TRUSTED_PROXIES: Final[tuple[str, ...]] = ("127.0.0.1", "::1", "localhost")


@dataclass(frozen=True, slots=True)
class TLSTransportConfig:
    """Declarative server TLS 1.3 / mTLS and trusted reverse-proxy transport policy."""

    certfile: Path | None = None
    keyfile: Path | None = None
    client_ca_file: Path | None = None
    behind_tls_proxy: bool = False
    trusted_proxy_hosts: tuple[str, ...] = DEFAULT_TRUSTED_PROXIES

    @property
    def has_native_tls(self) -> bool:
        """Return True when both server certificate and private key paths are configured."""
        return self.certfile is not None and self.keyfile is not None


def _is_loopback_bind_host(host: str) -> bool:
    cleaned = host.strip().lower().strip("[]")
    return cleaned in LOOPBACK_BIND_HOSTS or cleaned.endswith(".localhost")


def validate_listener_transport_security(
    host: str, config: TLSTransportConfig | None = None
) -> None:
    """Block incomplete PEM pairs and accidental non-loopback plaintext HTTP exposure."""
    cfg = config or TLSTransportConfig()
    if (cfg.certfile is None) != (cfg.keyfile is None):
        raise ValueError(
            "INVALID_TLS_CONFIGURATION: both certfile and keyfile must be provided together"
        )
    if cfg.client_ca_file is not None and not cfg.has_native_tls:
        raise ValueError(
            "INVALID_TLS_CONFIGURATION: client_ca_file (mTLS) requires certfile and keyfile"
        )
    if not _is_loopback_bind_host(host) and not cfg.has_native_tls and not cfg.behind_tls_proxy:
        raise ValueError(
            f"PLAINTEXT_NON_LOOPBACK_BLOCKED: refusing plaintext HTTP bind on {host!r}; "
            "pass --tls-certfile/--tls-keyfile or --behind-tls-proxy"
        )


def build_server_ssl_context(config: TLSTransportConfig | None = None) -> ssl.SSLContext | None:
    """Build a hardened OpenSSL 3 TLS 1.2+/1.3 server context (with optional mTLS)."""
    cfg = config or TLSTransportConfig()
    if (cfg.certfile is None) != (cfg.keyfile is None):
        raise ValueError(
            "INVALID_TLS_CONFIGURATION: both certfile and keyfile must be provided together"
        )
    if cfg.certfile is None or cfg.keyfile is None:
        if cfg.client_ca_file is not None:
            raise ValueError(
                "INVALID_TLS_CONFIGURATION: client_ca_file (mTLS) requires certfile and keyfile"
            )
        return None
    for label, p in (("certfile", cfg.certfile), ("keyfile", cfg.keyfile)):
        if not p.is_file():
            raise ValueError(f"INVALID_TLS_CONFIGURATION: {label} not found at {p}")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.options |= ssl.OP_NO_COMPRESSION
    ctx.load_cert_chain(certfile=str(cfg.certfile), keyfile=str(cfg.keyfile))
    if cfg.client_ca_file is not None:
        if not cfg.client_ca_file.is_file():
            raise ValueError(
                f"INVALID_TLS_CONFIGURATION: client_ca_file not found at {cfg.client_ca_file}"
            )
        ctx.load_verify_locations(cafile=str(cfg.client_ca_file))
        ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _peer_matches_trusted_proxies(peer_host: str, trusted_proxies: Sequence[str]) -> bool:
    clean_peer = peer_host.strip().lower().strip("[]")
    if not clean_peer:
        return False
    try:
        peer_ip = ipaddress.ip_address(clean_peer)
    except ValueError:
        peer_ip = None
    for raw_entry in trusted_proxies:
        entry = raw_entry.strip().lower().strip("[]")
        if not entry:
            continue
        if entry == clean_peer:
            return True
        if peer_ip is not None and "/" in entry:
            try:
                net = ipaddress.ip_network(entry, strict=False)
            except ValueError:
                continue
            if peer_ip in net:
                return True
    return False


def resolve_effective_request_scheme(
    *,
    transport_is_tls: bool,
    peer_host: str,
    headers: Mapping[str, str],
    trusted_proxies: Sequence[str] = DEFAULT_TRUSTED_PROXIES,
) -> str:
    """Resolve 'https' vs. 'http' from native TLS or CIDR-gated X-Forwarded-Proto."""
    if transport_is_tls:
        return "https"
    if _peer_matches_trusted_proxies(peer_host, trusted_proxies):
        fwd = headers.get("x-forwarded-proto", "").split(",", maxsplit=1)[0].strip().lower()
        if fwd == "https":
            return "https"
    return "http"


def is_https_scope(
    scope: Mapping[str, Any], *, trusted_proxies: Sequence[str] = DEFAULT_TRUSTED_PROXIES
) -> bool:
    """Return True when an ASGI HTTP scope arrived over native TLS or a trusted HTTPS proxy."""
    if str(scope.get("scheme", "")).lower() == "https":
        return True
    client_t = scope.get("client")
    peer = str(client_t[0]) if isinstance(client_t, (tuple, list)) and client_t else ""
    hdrs = {
        bytes(k).decode("latin1").lower(): bytes(v).decode("latin1")
        for k, v in scope.get("headers", [])
    }
    return (
        resolve_effective_request_scheme(
            transport_is_tls=False, peer_host=peer, headers=hdrs, trusted_proxies=trusted_proxies
        )
        == "https"
    )


def format_set_cookie_header(
    name: str,
    value: str,
    *,
    is_https: bool,
    same_site: str = "Strict",
    http_only: bool = True,
    path: str = "/",
    max_age: int | None = None,
    domain: str = "",
) -> str:
    """Format a Set-Cookie header with optional RFC 6265 Domain and HTTPS Secure flags."""
    parts = [f"{name}={value}", f"Path={path}"]
    clean_dom = domain.strip().lower().lstrip(".")
    if clean_dom:
        if ":" in clean_dom or not is_safe_host(clean_dom):
            raise ValueError(f"INVALID_COOKIE_DOMAIN: {domain!r}")
        parts.append(f"Domain={clean_dom}")
    parts.append(f"SameSite={same_site}")
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if http_only:
        parts.append("HttpOnly")
    if is_https:
        parts.append("Secure")
    return "; ".join(parts)
