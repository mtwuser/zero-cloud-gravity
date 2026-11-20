"""Unit tests for zcg.providers.cloud_gcp.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcg.providers.cloud_gcp import (
    CLOUD_DEPLOY_CONTRACT_REV,
    materialize_cloud_deployment_manifest,
    verify_keyless_gcp_credentials,
)


class TestCloudGcpProvider:
    """Verify keyless Google Cloud WIF/ADC preflight and cloud_deployment_<env>.json manifests."""

    def test_verify_keyless_gcp_credentials_guards_and_wif_expected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify ambient ADC, external_account WIF, and static service_account key rejection."""
        # Arrange
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        wif_f = tmp_path / "wif.json"
        wif_f.write_text(json.dumps({"type": "external_account"}), encoding="utf-8")
        sa_f = tmp_path / "sa.json"
        sa_f.write_text(
            json.dumps({"type": "service_account", "private_key": "SECRET"}), encoding="utf-8"
        )
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{broken", encoding="utf-8")
        list_json = tmp_path / "list.json"
        list_json.write_text("[]", encoding="utf-8")
        unk_json = tmp_path / "unk.json"
        unk_json.write_text(json.dumps({"type": "custom_cred"}), encoding="utf-8")

        # Act
        amb = verify_keyless_gcp_credentials()
        wif = verify_keyless_gcp_credentials(env={"GOOGLE_APPLICATION_CREDENTIALS": str(wif_f)})
        direct = verify_keyless_gcp_credentials(wif_f, env={})

        # Assert
        assert amb["credential_type"] == "ambient-adc" and amb["keyless_verified"] is True
        assert wif["credential_type"] == "external_account"
        assert direct["mode"] == "adc-file"
        with pytest.raises(ValueError, match="INVALID_GCP_ADC_JSON"):
            verify_keyless_gcp_credentials(tmp_path / "missing.json", env={})
        with pytest.raises(ValueError, match="INVALID_GCP_ADC_JSON"):
            verify_keyless_gcp_credentials(bad_json, env={})
        with pytest.raises(ValueError, match="INVALID_GCP_ADC_JSON"):
            verify_keyless_gcp_credentials(list_json, env={})
        with pytest.raises(ValueError, match="STATIC_GCP_KEY_FORBIDDEN"):
            verify_keyless_gcp_credentials(sa_f, env={})
        with pytest.raises(ValueError, match="UNSUPPORTED_GCP_CREDENTIAL_TYPE"):
            verify_keyless_gcp_credentials(unk_json, env={})

    def test_materialize_cloud_deployment_manifest_environments_and_guards_expected(
        self, tmp_path: Path
    ) -> None:
        """Verify dev/tst/pro cloud_deployment_<env>.json generation and static key guards."""
        # Arrange
        ws = tmp_path / "org-cloud"
        ws.mkdir()
        pub_m = {
            "layer_id": "org-cloud",
            "layer_role": "organization",
            "entity_kind": "open-source",
            "visibility": "public",
            "cloud_deployment": {"project_id": "iso-gcp-01"},
            "network_egress_policy": {
                "allowed_domains": ["*.iso.org"],
                "enable_canonical_cdn": True,
            },
        }
        pub_topo = {
            "domain_governance": {
                "dns_publication": "public-authoritative",
                "canonical_domain": "iso.org",
                "developer_domain": "iso.dev",
            }
        }
        fallback_topo = {"domain_governance": {"dns_publication": "public-authoritative"}}
        priv_m = {"layer_id": "dept-ops", "layer_role": "department", "visibility": "private"}
        priv_topo = {
            "domain_governance": {
                "dns_publication": "private-split-horizon",
                "intranet_zone": "corp.net",
            }
        }

        gke_m = {
            "layer_id": "fleet-agents",
            "layer_role": "department",
            "visibility": "private",
            "cloud_deployment": {
                "project_id": "iso-gcp-01",
                "compute_tier": "gke-agent-sandbox",
                "warm_pool_replicas": 2,
            },
        }

        # Act
        dev_doc = materialize_cloud_deployment_manifest(
            ws, pub_m, pub_topo, active_env="dev", env_vars={}
        )
        pro_doc = materialize_cloud_deployment_manifest(
            ws, pub_m, pub_topo, active_env="pro", plugin_id="portal", env_vars={}
        )
        gke_doc = materialize_cloud_deployment_manifest(
            ws, gke_m, priv_topo, active_env="pre", env_vars={}
        )
        fb_doc = materialize_cloud_deployment_manifest(
            ws, {"layer_id": "fb-node"}, fallback_topo, active_env="pro", env_vars={}
        )
        priv_doc = materialize_cloud_deployment_manifest(
            ws, priv_m, priv_topo, active_env="tst", env_vars={}
        )
        loop_doc = materialize_cloud_deployment_manifest(
            ws, priv_m, {}, active_env="dev", env_vars={}
        )

        # Assert
        assert dev_doc["schema_version"] == CLOUD_DEPLOY_CONTRACT_REV
        assert dev_doc["compute_tier"] == "cloud-run-gen2"
        assert dev_doc["cloud_run"]["execution_environment"] == "gen2"
        assert dev_doc["cloud_run"]["scale_to_zero"] is True
        assert dev_doc["gke_agent_sandbox"] is None
        assert gke_doc["compute_tier"] == "gke-agent-sandbox"
        assert gke_doc["gke_agent_sandbox"]["api_version"] == "agents.x-k8s.io/v1alpha1"
        assert gke_doc["gke_agent_sandbox"]["runtime_class_name"] == "gvisor"
        assert gke_doc["gke_agent_sandbox"]["warm_pool_replicas"] == 2
        assert gke_doc["gke_agent_sandbox"]["third_party_crds"] == []
        assert dev_doc["fqdn"] == "dev.iso.org" and dev_doc["developer_fqdn"] == "dev.iso.dev"
        assert pro_doc["fqdn"] == "iso.org" and pro_doc["developer_fqdn"] == "iso.dev"
        assert pro_doc["cloud_run"]["docs_access_mode"] == "disabled"
        assert pro_doc["cloud_run"]["vpc_egress"] == "private-ranges-only"
        assert len(pro_doc["cloud_dns"]["records"]) == 4
        assert fb_doc["fqdn"] == "fb-node.run.app"
        assert priv_doc["fqdn"] == "tst.dept-ops.corp.net" and priv_doc["developer_fqdn"] == ""
        assert len(priv_doc["cloud_dns"]["records"]) == 2
        assert (
            loop_doc["fqdn"] == "dev.dept-ops.internal" and loop_doc["cloud_dns"]["records"] == []
        )
        assert (ws / "surfaces/infra/cloud_deployment_pro.json").is_file()
        with pytest.raises(ValueError, match="Invalid active_env"):
            materialize_cloud_deployment_manifest(
                ws, pub_m, pub_topo, active_env="bad", env_vars={}
            )
        with pytest.raises(ValueError, match="STATIC_GCP_KEY_FORBIDDEN"):
            materialize_cloud_deployment_manifest(
                ws, {"cloud_deployment": {"private_key": "PEM"}}, {}, active_env="dev", env_vars={}
            )
        with pytest.raises(ValueError, match="THIRD_PARTY_AGENT_CRD_FORBIDDEN"):
            materialize_cloud_deployment_manifest(
                ws,
                {"cloud_deployment": {"orchestrator_crd": "external-crd"}},
                {},
                active_env="dev",
                env_vars={},
            )
        with pytest.raises(ValueError, match="UNSUPPORTED_GCP_COMPUTE_TIER"):
            materialize_cloud_deployment_manifest(
                ws,
                {"cloud_deployment": {"compute_tier": "bare-metal-vm"}},
                {},
                active_env="dev",
                env_vars={},
            )
