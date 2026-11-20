"""Unit tests for zcg.providers.container_edge.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zcg.providers.container_edge import (
    CONTAINER_DEPLOY_CONTRACT_REV,
    materialize_container_deployment_manifest,
    verify_secretless_container_posture,
)


class TestContainerEdgeProvider:
    """Verify secretless OCI container posture and container_deployment_<env>.json manifests."""

    def test_verify_secretless_container_posture_and_proxy_guards_expected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify caddy/nginx/traefik/direct-tls validation and static secret rejection."""
        # Arrange
        monkeypatch.delenv("ZCG_STATIC_CONTAINER_SECRET", raising=False)

        # Act
        default_ok = verify_secretless_container_posture({})
        direct_ok = verify_secretless_container_posture({"reverse_proxy": "direct-tls"}, env={})

        # Assert
        assert default_ok["secretless_verified"] is True
        assert default_ok["reverse_proxy"] == "caddy"
        assert direct_ok["reverse_proxy"] == "direct-tls"
        with pytest.raises(ValueError, match="STATIC_CONTAINER_SECRET_FORBIDDEN"):
            verify_secretless_container_posture({"oidc_client_secret": "inline-secret"}, env={})
        with pytest.raises(ValueError, match="STATIC_CONTAINER_SECRET_FORBIDDEN"):
            verify_secretless_container_posture({}, env={"ZCG_STATIC_CONTAINER_SECRET": "leak"})
        with pytest.raises(ValueError, match="UNSUPPORTED_EDGE_PROXY"):
            verify_secretless_container_posture({"reverse_proxy": "unsupported-proxy"}, env={})

    def test_materialize_container_deployment_manifest_environments_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify OCI UID 10001, reverse-proxy vs direct-tls CLI flags, and DNS A/TXT records."""
        # Arrange
        ws = tmp_path / "selfhosted-node"
        ws.mkdir()
        pub_m = {
            "layer_id": "selfhosted-node",
            "layer_role": "organization",
            "visibility": "public",
            "container_deployment": {"reverse_proxy": "caddy", "edge_ipv4": "198.51.100.42"},
        }
        pub_topo = {
            "domain_governance": {
                "dns_publication": "public-authoritative",
                "canonical_domain": "self.example.org",
                "developer_domain": "self.example.dev",
            }
        }
        direct_m = {
            "layer_id": "edge-direct",
            "container_deployment": {"reverse_proxy": "direct-tls"},
        }
        split_topo = {
            "domain_governance": {
                "dns_publication": "private-split-horizon",
                "intranet_zone": "lan.internal",
            }
        }

        # Act
        dev_doc = materialize_container_deployment_manifest(
            ws, pub_m, pub_topo, active_env="dev", env_vars={}
        )
        pro_doc = materialize_container_deployment_manifest(
            ws, pub_m, pub_topo, active_env="pro", env_vars={}
        )
        fb_pub = materialize_container_deployment_manifest(
            ws,
            direct_m,
            {"domain_governance": {"dns_publication": "public-authoritative"}},
            active_env="pro",
            env_vars={},
        )
        split_doc = materialize_container_deployment_manifest(
            ws, direct_m, split_topo, active_env="tst", env_vars={}
        )
        loop_doc = materialize_container_deployment_manifest(
            ws, {"layer_id": "local-box"}, {}, active_env="dev", env_vars={}
        )

        # Assert
        assert dev_doc["schema_version"] == CONTAINER_DEPLOY_CONTRACT_REV
        assert dev_doc["compute_tier"] == "self-hosted-oci"
        assert dev_doc["sandbox_isolation"] == "rootless-oci+bwrap-readonly"
        assert dev_doc["fqdn"] == "dev.self.example.org"
        assert "--behind-tls-proxy" in dev_doc["oci_container"]["command"]
        assert (
            pro_doc["fqdn"] == "self.example.org"
            and pro_doc["developer_fqdn"] == "self.example.dev"
        )
        assert pro_doc["oci_container"]["uid"] == 10001
        assert pro_doc["oci_container"]["docs_access_mode"] == "disabled"
        assert len(pro_doc["rfc_dns"]["records"]) == 4
        assert fb_pub["fqdn"] == "edge-direct.selfhosted.local"
        assert "--tls-certfile" in fb_pub["oci_container"]["command"]
        assert split_doc["fqdn"] == "tst.edge-direct.lan.internal"
        assert len(split_doc["rfc_dns"]["records"]) == 2
        assert loop_doc["fqdn"] == "dev.local-box.intranet.local"
        assert loop_doc["rfc_dns"]["records"] == []
        assert (ws / "surfaces/infra/container_deployment_pro.json").is_file()
        with pytest.raises(ValueError, match="Invalid active_env"):
            materialize_container_deployment_manifest(
                ws, pub_m, pub_topo, active_env="invalid", env_vars={}
            )
