"""Unit tests for zcg.cockpit.routing.surface_routing.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from zcg.cockpit.routing.surface_routing import (
    build_node_oidc_and_portal_routers,
    compile_node_surface_access_policy,
    project_ring_scoped_capsule,
    resolve_deployment_target_summary,
    resolve_node_cdn_origins,
)
from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.platform.projection import DisclosureTier, PayloadFieldSegment
from zcg.web.auth.security import PROXY_JWT_HEADER, WebAppError
from zcg.web.auth.surface_access import PEER_NODE_HEADER, SURFACE_RING_HEADER


def _make_hs256_jwt(claims: dict[str, object], key: str) -> str:
    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    h_s = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    p_s = _b64(json.dumps(claims).encode("utf-8"))
    sig = _b64(
        hmac.new(key.encode("utf-8"), f"{h_s}.{p_s}".encode("ascii"), hashlib.sha256).digest()
    )
    return f"{h_s}.{p_s}.{sig}"


class TestSurfaceRouting:
    """Verify vendor-neutral node surface access compilation, OIDC/portal wiring, and targets."""

    def test_resolve_deployment_target_summary_defaults_to_local_sovereign_expected(self) -> None:
        """Verify local-sovereign default (including workstation catalogs) vs opt-in providers."""
        # Arrange
        ws_cat = {
            "layer_role": "workstation",
            "default_stack_templates": ["google-cloud-iac", "self-hosted-container"],
        }
        cont_m = {"layer_role": "department", "default_stack_templates": ["self-hosted-container"]}
        gcp_m = {"layer_role": "organization", "cloud_deployment": {"project_id": "iso-01"}}

        # Act
        local_sum = resolve_deployment_target_summary(ws_cat, active_env="dev")
        cont_dev = resolve_deployment_target_summary(cont_m, active_env="dev")
        cont_tst = resolve_deployment_target_summary(cont_m, active_env="tst")
        cont_pro = resolve_deployment_target_summary(cont_m, active_env="pro")
        gcp_dev = resolve_deployment_target_summary(gcp_m, active_env="dev")
        gcp_pre = resolve_deployment_target_summary(gcp_m, active_env="pre")
        gcp_pro = resolve_deployment_target_summary(gcp_m, active_env="pro")

        # Assert
        assert local_sum["provider"] == "local-sovereign" and local_sum["iac_manifest"] == "none"
        assert (
            cont_dev["provider"] == "self-hosted-container" and cont_dev["stage"] == "local-cockpit"
        )
        assert cont_tst["stage"] == "staging-container-edge"
        assert cont_pro["stage"] == "production-container-edge"
        assert gcp_dev["provider"] == "google-cloud-iac" and gcp_dev["stage"] == "local-cockpit"
        assert gcp_pre["stage"] == "staging-cloud-deploy"
        assert gcp_pro["stage"] == "production-cloud-run-gke"

    def test_compile_node_surface_access_policy_with_keycloak_and_env_iam_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify declarative surface_access compilation with Keycloak OIDC and runtime IAM vars."""
        # Arrange
        ws = tmp_path / "node-a"
        (ws / "system").mkdir(parents=True)
        manifest = {
            "layer_id": "node-a",
            "layer_role": "organization",
            "visibility": "public",
            "layer_authority": {"authorized_emails": ["owner@corp.net"]},
            "surface_access": {
                "oidc_provider": "keycloak",
                "oidc_issuers": ["https://sso.corp.net/realms/main"],
                "oidc_expected_audience": "zcg-web",
                "allowed_linked_peers": {"peer-b": "peer-secret"},
                "route_rules": [
                    "skip-non-dict",
                    {"path": ""},
                    {
                        "path_pattern": "/partner/feed",
                        "ring": "scoped-external",
                        "methods": ["GET"],
                        "allowed_external_subjects": ["linked-peer"],
                        "disclosure_tier": "verified_competency",
                    },
                    {"path_pattern": "/internal/ops", "ring": "r2", "required_groups": ["ops"]},
                ],
            },
        }
        (ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(manifest), encoding="utf-8")
        env_v = {
            "ZCG_OIDC_ASSERTION_KEY": "kc-key",
            "ZCG_WORKSPACE_DOMAINS": "corp.net",
            "ZCG_MEMBER_EMAILS": "member@corp.net",
        }
        kc_jwt = _make_hs256_jwt(
            {
                "iss": "https://sso.corp.net/realms/main",
                "aud": "zcg-web",
                "email": "member@corp.net",
                "groups": ["ops"],
                "exp": 900,
            },
            "kc-key",
        )

        # Act
        none_pol = compile_node_surface_access_policy(ws, {"layer_id": "x"})
        off_pol = compile_node_surface_access_policy(ws, {"surface_access": {"enabled": False}})
        no_inh_pol = compile_node_surface_access_policy(
            ws,
            {
                "layer_authority": "invalid",
                "surface_access": {
                    "inherit_layer_authority": False,
                    "protect_mutating_ops": False,
                },
            },
            env_vars={},
        )
        pol = compile_node_surface_access_policy(ws, active_env="pro", env_vars=env_v)
        tst_pol = compile_node_surface_access_policy(ws, active_env="tst", env_vars=env_v)
        assert pol is not None and tst_pol is not None
        pro_portal_h = pol.enforce(method="GET", path="/portal", headers={}, cookies={})
        tst_auth_portal_h = tst_pol.enforce(
            method="GET",
            path="/portal",
            headers={PROXY_JWT_HEADER: kc_jwt},
            cookies={},
            now=800.0,
        )
        with pytest.raises(WebAppError, match="Authentication"):
            tst_pol.enforce(method="GET", path="/portal", headers={}, cookies={})
        peer_h = pol.enforce(
            method="GET",
            path="/partner/feed",
            headers={PEER_NODE_HEADER: "peer-b", "authorization": "Bearer peer-secret"},
            cookies={},
        )
        ops_h = pol.enforce(
            method="GET",
            path="/internal/ops",
            headers={PROXY_JWT_HEADER: kc_jwt},
            cookies={},
            now=800.0,
        )

        # Assert
        assert none_pol is None and off_pol is None and no_inh_pol is not None
        assert peer_h[SURFACE_RING_HEADER] == "R1"
        assert ops_h[SURFACE_RING_HEADER] == "R2"
        assert pro_portal_h[SURFACE_RING_HEADER] == "R0"
        assert tst_auth_portal_h[SURFACE_RING_HEADER] == "R1"

    def test_oidc_portal_routers_cdn_origins_and_capsule_projection_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify OIDC/portal router instantiation, CDN origin resolution, and capsule filtering."""
        # Arrange
        ws = tmp_path / "ind-node"
        (ws / "system").mkdir(parents=True)
        ind_m = {
            "layer_id": "ind-node",
            "entity_kind": "individual",
            "visibility": "public",
            "domain_governance": {"canonical_domain": "persona.example.org"},
            "network_egress_policy": {
                "allowed_domains": ["*.persona.example.org"],
                "enable_canonical_cdn": True,
            },
            "surface_access": {"allowed_workspace_domains": ["persona.example.org"]},
        }
        (ws / NODE_MANIFEST_REL_PATH).write_text(json.dumps(ind_m), encoding="utf-8")
        segs = (
            PayloadFieldSegment("summary", DisclosureTier.CORE_SUMMARY, "Public bio"),
            PayloadFieldSegment("proposal", DisclosureTier.VERIFIED_COMPETENCY, "B2B scope"),
            PayloadFieldSegment("runbook", DisclosureTier.DAY1_ONBOARDING, "Internal ops"),
        )

        # Act
        csrf_a, csrf_b = "csrf-val-1", "csrf-val-2"
        oidc_r, portal_r = build_node_oidc_and_portal_routers(
            ws, csrf_token=csrf_a, active_env="dev", env_vars={}
        )
        oss_ws = tmp_path / "oss-node"
        (oss_ws / "system").mkdir(parents=True)
        (oss_ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps({"layer_id": "oss-node", "entity_kind": "open-source"}), encoding="utf-8"
        )
        oss_oidc, _ = build_node_oidc_and_portal_routers(oss_ws, csrf_token=csrf_b)
        empty_ws = tmp_path / "empty-node"
        empty_ws.mkdir()
        _, empty_portal = build_node_oidc_and_portal_routers(empty_ws, csrf_token=csrf_b)
        corp_ws = tmp_path / "corp-acme"
        dept_ws = tmp_path / "dept-eng"
        (corp_ws / "system").mkdir(parents=True)
        (dept_ws / "system").mkdir(parents=True)
        (corp_ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "corp-acme",
                    "layer_role": "corporate",
                    "domain_governance": {"canonical_domain": "acme.example.org"},
                }
            ),
            encoding="utf-8",
        )
        (dept_ws / NODE_MANIFEST_REL_PATH).write_text(
            json.dumps(
                {
                    "layer_id": "dept-eng",
                    "layer_role": "department",
                    "governing_root_id": "corp-acme",
                }
            ),
            encoding="utf-8",
        )
        _, dept_portal = build_node_oidc_and_portal_routers(dept_ws, csrf_token=csrf_b)
        cdn = resolve_node_cdn_origins(ws)
        cdn_no_dg = resolve_node_cdn_origins(ws, manifest={"layer_id": "plain"})
        cap_r0 = project_ring_scoped_capsule(
            resource_id="res-1",
            target_node_id="ext",
            effective_disclosure_tier="core_summary",
            segments=segs,
        )
        cap_r3 = project_ring_scoped_capsule(
            resource_id="res-1",
            target_node_id="own",
            effective_disclosure_tier="deep_context",
            segments=segs,
        )

        # Assert
        assert any(rt.path_template == "/auth/oidc/login" for rt in oidc_r.routes)
        assert any(rt.path_template == "/portal" for rt in portal_r.routes)
        assert any(rt.path_template == "/auth/session" for rt in oss_oidc.routes)
        assert any(rt.path_template == "/portal" for rt in empty_portal.routes)
        assert any(rt.path_template == "/portal" for rt in dept_portal.routes)
        assert cdn == ("https://cdn.persona.example.org",) and cdn_no_dg == ()
        assert len(cap_r0.disclosed_fields) == 1 and len(cap_r3.disclosed_fields) == 3
        with pytest.raises(ValueError, match="effective_disclosure_tier"):
            project_ring_scoped_capsule(
                resource_id="r", target_node_id="n", effective_disclosure_tier="bad", segments=segs
            )

    def test_compile_node_access_policy_merges_local_trust_circles_without_label_leak_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify local_trust_circles grant R2/R1 access with 0% circle-label wire leakage."""
        # Arrange
        ws = tmp_path / "shared-node"
        (ws / "system").mkdir(parents=True)
        manifest = {
            "layer_id": "shared-node",
            "layer_role": "department",
            "precedence": 89,
            "local_trust_circles": {
                "private-family-label": {"outward_ring": "R2", "emails": ["kin@example.org"]},
                "private-auditor-label": {"outward_ring": "R1", "emails": ["aud@example.org"]},
            },
            "surface_access": {
                "oidc_provider": "keycloak",
                "oidc_issuers": ["https://sso.shared.net/realms/main"],
                "oidc_expected_audience": "zcg-web",
                "route_rules": [
                    {"path_pattern": "/circle/r2", "ring": "r2"},
                    {"path_pattern": "/circle/r1", "ring": "r1"},
                ],
            },
        }
        kin_jwt = _make_hs256_jwt(
            {
                "iss": "https://sso.shared.net/realms/main",
                "aud": "zcg-web",
                "email": "kin@example.org",
                "exp": 900,
            },
            "circle-key",
        )
        aud_jwt = _make_hs256_jwt(
            {
                "iss": "https://sso.shared.net/realms/main",
                "aud": "zcg-web",
                "email": "aud@example.org",
                "exp": 900,
            },
            "circle-key",
        )

        # Act
        policy = compile_node_surface_access_policy(
            ws,
            manifest=manifest,
            active_env="pro",
            env_vars={"ZCG_OIDC_ASSERTION_KEY": "circle-key"},
        )
        assert policy is not None
        kin_h = policy.enforce(
            method="GET",
            path="/circle/r2",
            headers={PROXY_JWT_HEADER: kin_jwt},
            cookies={},
            now=800.0,
        )
        aud_h = policy.enforce(
            method="GET",
            path="/circle/r1",
            headers={PROXY_JWT_HEADER: aud_jwt},
            cookies={},
            now=800.0,
        )

        # Assert
        assert kin_h[SURFACE_RING_HEADER] == "R2"
        assert aud_h[SURFACE_RING_HEADER] == "R1"
        wire_dump = f"{kin_h!r} {aud_h!r} {policy!r}"
        assert "private-family-label" not in wire_dump
        assert "private-auditor-label" not in wire_dump
