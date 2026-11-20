"""Unit tests for zcg.providers.oidc_presets.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import pytest

from zcg.providers.oidc_presets import (
    DEFAULT_PROXY_JWT_HEADER,
    GOOGLE_IAP_ISSUER,
    GOOGLE_IAP_JWT_HEADER,
    GOOGLE_OIDC_AUTH_ENDPOINT,
    OIDC_PROVIDER_PRESETS,
    resolve_oidc_provider_endpoints,
)


class TestOidcPresets:
    """Verify RFC OIDC provider presets and manifest/env endpoint resolution."""

    def test_resolve_generic_and_self_hosted_oidc_presets_expected(self) -> None:
        """Verify default generic-oidc, keycloak auto-authorize URL, and custom labels."""
        # Arrange
        keycloak_sa = {
            "oidc_provider": "keycloak",
            "oidc_issuers": ["https://sso.corp.net/realms/main/", " "],
            "oidc_client_id": "kc-web",
            "oidc_provider_label": "Corp SSO",
            "oidc_assertion_key": "kc-secret",
        }

        # Act
        default_ep = resolve_oidc_provider_endpoints({}, {})
        kc_ep = resolve_oidc_provider_endpoints(
            keycloak_sa,
            {"ZCG_OIDC_ISSUER": "https://sso.corp.net/realms/main/ , https://backup.corp.net"},
        )
        explicit_auth = resolve_oidc_provider_endpoints(
            {"oidc_provider": "authelia"},
            {
                "ZCG_OIDC_AUTH_ENDPOINT": "https://auth.corp.net/api/oidc/authorization",
                "ZCG_OIDC_AUDIENCE": "authelia-aud",
            },
        )

        # Assert
        assert set(OIDC_PROVIDER_PRESETS) >= {
            "generic-oidc",
            "keycloak",
            "authelia",
            "pocket-id",
            "github-oidc",
            "google-workspace",
        }
        assert default_ep.provider_id == "generic-oidc"
        assert default_ep.authorization_endpoint == ""
        assert default_ep.allowed_issuers == ()
        assert default_ep.infer_domain_from_email is True
        assert default_ep.proxy_jwt_headers == (DEFAULT_PROXY_JWT_HEADER,)
        assert kc_ep.provider_id == "keycloak"
        assert kc_ep.provider_label == "Corp SSO"
        assert kc_ep.authorization_endpoint == "https://sso.corp.net/realms/main/authorize"
        assert kc_ep.expected_audience == "kc-web"
        assert kc_ep.assertion_key == "kc-secret"
        assert "https://backup.corp.net" in kc_ep.allowed_issuers
        assert explicit_auth.authorization_endpoint == (
            "https://auth.corp.net/api/oidc/authorization"
        )
        assert explicit_auth.expected_audience == "authelia-aud"

    def test_resolve_google_workspace_auto_detection_and_invalid_provider_guard_expected(
        self,
    ) -> None:
        """Verify seamless google-workspace auto-detection on IAP/Google vars and unknown guard."""
        # Arrange
        env_google = {
            "ZCG_GOOGLE_OIDC_CLIENT_ID": "12345.apps.googleusercontent.com",
            "ZCG_IAP_ASSERTION_KEY": "iap-hmac",
        }

        # Act
        goog_ep = resolve_oidc_provider_endpoints({}, env_google)

        # Assert
        assert goog_ep.provider_id == "google-workspace"
        assert goog_ep.authorization_endpoint == GOOGLE_OIDC_AUTH_ENDPOINT
        assert goog_ep.domain_hint_param == "hd"
        assert goog_ep.infer_domain_from_email is False
        assert goog_ep.domain_infer_issuers == (GOOGLE_IAP_ISSUER,)
        assert goog_ep.proxy_jwt_headers == (DEFAULT_PROXY_JWT_HEADER, GOOGLE_IAP_JWT_HEADER)
        assert goog_ep.expected_audience == "12345.apps.googleusercontent.com"
        assert goog_ep.assertion_key == "iap-hmac"
        with pytest.raises(ValueError, match="Unsupported oidc_provider"):
            resolve_oidc_provider_endpoints({"oidc_provider": "unknown-vendor"}, {})
