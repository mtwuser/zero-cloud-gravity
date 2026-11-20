"""Opt-in RFC 6749 / OpenID Connect provider presets and runtime endpoint resolution.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

GOOGLE_IAP_ISSUER: Final[str] = "https://cloud.google.com/iap"
GOOGLE_IAP_JWT_HEADER: Final[str] = "x-goog-iap-jwt-assertion"
GOOGLE_OIDC_ISSUERS: Final[tuple[str, ...]] = (
    "https://accounts.google.com",
    "accounts.google.com",
)
GOOGLE_OIDC_AUTH_ENDPOINT: Final[str] = "https://accounts.google.com/o/oauth2/v2/auth"
GITHUB_OIDC_ISSUER: Final[str] = "https://token.actions.githubusercontent.com"
GITHUB_OAUTH_AUTH_ENDPOINT: Final[str] = "https://github.com/login/oauth/authorize"
DEFAULT_PROXY_JWT_HEADER: Final[str] = "x-zcg-identity-assertion"


@dataclass(frozen=True, slots=True)
class OidcProviderPreset:
    """Declarative OIDC / identity-proxy preset decoupling zcg.web from vendor constants."""

    provider_id: str
    provider_label: str
    authorization_endpoint: str
    allowed_issuers: tuple[str, ...]
    domain_hint_param: str = "login_hint"
    infer_domain_from_email: bool = False
    domain_infer_issuers: tuple[str, ...] = ()
    proxy_jwt_headers: tuple[str, ...] = (DEFAULT_PROXY_JWT_HEADER,)


OIDC_PROVIDER_PRESETS: Final[Mapping[str, OidcProviderPreset]] = {
    "generic-oidc": OidcProviderPreset(
        provider_id="generic-oidc",
        provider_label="OIDC Identity",
        authorization_endpoint="",
        allowed_issuers=(),
        domain_hint_param="login_hint",
        infer_domain_from_email=True,
    ),
    "keycloak": OidcProviderPreset(
        provider_id="keycloak",
        provider_label="Keycloak OIDC",
        authorization_endpoint="",
        allowed_issuers=(),
        domain_hint_param="login_hint",
        infer_domain_from_email=True,
    ),
    "authelia": OidcProviderPreset(
        provider_id="authelia",
        provider_label="Authelia OIDC",
        authorization_endpoint="",
        allowed_issuers=(),
        domain_hint_param="login_hint",
        infer_domain_from_email=True,
    ),
    "pocket-id": OidcProviderPreset(
        provider_id="pocket-id",
        provider_label="Pocket ID Passkey",
        authorization_endpoint="",
        allowed_issuers=(),
        domain_hint_param="login_hint",
        infer_domain_from_email=True,
    ),
    "github-oidc": OidcProviderPreset(
        provider_id="github-oidc",
        provider_label="GitHub Identity",
        authorization_endpoint=GITHUB_OAUTH_AUTH_ENDPOINT,
        allowed_issuers=(GITHUB_OIDC_ISSUER,),
        domain_hint_param="login",
        infer_domain_from_email=True,
    ),
    "google-workspace": OidcProviderPreset(
        provider_id="google-workspace",
        provider_label="Google Identity",
        authorization_endpoint=GOOGLE_OIDC_AUTH_ENDPOINT,
        allowed_issuers=(GOOGLE_IAP_ISSUER, *GOOGLE_OIDC_ISSUERS),
        domain_hint_param="hd",
        infer_domain_from_email=False,
        domain_infer_issuers=(GOOGLE_IAP_ISSUER,),
        proxy_jwt_headers=(DEFAULT_PROXY_JWT_HEADER, GOOGLE_IAP_JWT_HEADER),
    ),
}


@dataclass(frozen=True, slots=True)
class ResolvedOidcEndpoints:
    """Resolved OIDC provider configuration compiled from node manifest and runtime env vars."""

    provider_id: str
    provider_label: str
    authorization_endpoint: str
    allowed_issuers: tuple[str, ...]
    client_id: str
    expected_audience: str
    assertion_key: str
    domain_hint_param: str
    infer_domain_from_email: bool
    domain_infer_issuers: tuple[str, ...]
    proxy_jwt_headers: tuple[str, ...] = (DEFAULT_PROXY_JWT_HEADER,)


def _split_csv_values(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def resolve_oidc_provider_endpoints(
    raw_surface_access: Mapping[str, Any],
    env_vars: Mapping[str, str],
) -> ResolvedOidcEndpoints:
    """Resolve RFC OIDC endpoints and audiences from manifest + ZCG_OIDC_* / ZCG_IAP_* env vars."""
    explicit_id = (
        env_vars.get("ZCG_OIDC_PROVIDER", "").strip()
        or str(raw_surface_access.get("oidc_provider") or "").strip()
    )
    if explicit_id:
        provider_id = explicit_id
    elif (
        env_vars.get("ZCG_GOOGLE_OIDC_CLIENT_ID", "").strip()
        or env_vars.get("ZCG_IAP_AUDIENCE", "").strip()
        or str(raw_surface_access.get("iap_expected_audience") or "").strip()
        or str(raw_surface_access.get("iap_assertion_key") or "").strip()
        or str(raw_surface_access.get("iap_assertion_key_env") or "").strip()
    ):
        provider_id = "google-workspace"
    else:
        provider_id = "generic-oidc"

    preset = OIDC_PROVIDER_PRESETS.get(provider_id)
    if preset is None:
        raise ValueError(
            f"Unsupported oidc_provider '{provider_id}' "
            f"(expected one of {sorted(OIDC_PROVIDER_PRESETS)})"
        )

    raw_iss_list = raw_surface_access.get("oidc_issuers")
    manifest_issuers = (
        tuple(str(x).strip() for x in raw_iss_list if str(x).strip())
        if isinstance(raw_iss_list, list)
        else ()
    )
    env_issuers = _split_csv_values(env_vars.get("ZCG_OIDC_ISSUER"))
    merged_issuers = tuple(
        dict.fromkeys((*env_issuers, *manifest_issuers, *preset.allowed_issuers))
    )

    auth_ep = (
        env_vars.get("ZCG_OIDC_AUTH_ENDPOINT", "").strip()
        or str(raw_surface_access.get("oidc_authorization_endpoint") or "").strip()
        or preset.authorization_endpoint
    )
    if not auth_ep and merged_issuers:
        auth_ep = f"{merged_issuers[0].rstrip('/')}/authorize"

    client_id = (
        env_vars.get("ZCG_OIDC_CLIENT_ID", "").strip()
        or env_vars.get("ZCG_GOOGLE_OIDC_CLIENT_ID", "").strip()
        or str(raw_surface_access.get("oidc_client_id") or "").strip()
    )

    oidc_key_env = str(
        raw_surface_access.get("oidc_assertion_key_env")
        or raw_surface_access.get("iap_assertion_key_env")
        or "ZCG_OIDC_ASSERTION_KEY"
    ).strip()
    assertion_key = (
        env_vars.get(oidc_key_env, "").strip()
        or env_vars.get("ZCG_IAP_ASSERTION_KEY", "").strip()
        or str(
            raw_surface_access.get("oidc_assertion_key")
            or raw_surface_access.get("iap_assertion_key")
            or ""
        ).strip()
    )

    expected_aud = (
        str(raw_surface_access.get("oidc_expected_audience") or "").strip()
        or env_vars.get("ZCG_OIDC_AUDIENCE", "").strip()
        or str(raw_surface_access.get("iap_expected_audience") or "").strip()
        or env_vars.get("ZCG_IAP_AUDIENCE", "").strip()
        or client_id
    )

    label = (
        str(raw_surface_access.get("oidc_provider_label") or "").strip() or preset.provider_label
    )
    return ResolvedOidcEndpoints(
        provider_id=preset.provider_id,
        provider_label=label,
        authorization_endpoint=auth_ep,
        allowed_issuers=merged_issuers,
        client_id=client_id,
        expected_audience=expected_aud,
        assertion_key=assertion_key,
        domain_hint_param=preset.domain_hint_param,
        infer_domain_from_email=preset.infer_domain_from_email,
        domain_infer_issuers=preset.domain_infer_issuers,
        proxy_jwt_headers=preset.proxy_jwt_headers,
    )
