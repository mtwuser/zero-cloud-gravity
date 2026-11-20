"""Opt-in Google Cloud (Cloud Run Gen2 / GKE Agent Sandbox + IAP + Cloud DNS) provider.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import VALID_ENVIRONMENTS
from zcg.governance.policy.egress import resolve_effective_egress_policy
from zcg.topology.exposure import (
    classify_exposure_posture,
    resolve_posture_default_ring,
    resolve_surface_veracity_mode,
)

CLOUD_DEPLOY_CONTRACT_REV: Final[str] = "zcg-cloud-deploy-v1"
CLOUD_DEPLOY_REL_DIR: Final[str] = "surfaces/infra"
CLOUD_RUN_NONROOT_UID: Final[int] = 10001
DEFAULT_CLOUD_REGION: Final[str] = "europe-west1"
DEFAULT_GCP_COMPUTE_TIER: Final[str] = "cloud-run-gen2"
VALID_GCP_COMPUTE_TIERS: Final[tuple[str, ...]] = ("cloud-run-gen2", "gke-agent-sandbox")
GKE_SANDBOX_API_VERSION: Final[str] = "agents.x-k8s.io/v1alpha1"
GKE_SANDBOX_RUNTIME_CLASS: Final[str] = "gvisor"
VALID_WIF_CREDENTIAL_TYPES: Final[frozenset[str]] = frozenset(
    {"external_account", "impersonated_service_account", "authorized_user"}
)
FORBIDDEN_STATIC_KEY_FIELDS: Final[frozenset[str]] = frozenset({"private_key", "private_key_id"})


def verify_keyless_gcp_credentials(
    adc_path: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Verify Google Cloud ADC / Workload Identity Federation without static JSON keys."""
    eff_env = os.environ if env is None else env
    raw_env_p = eff_env.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    cand_path = adc_path if adc_path is not None else (Path(raw_env_p) if raw_env_p else None)
    if cand_path is None:
        return {
            "mode": "metadata-or-adc-default",
            "keyless_verified": True,
            "credential_type": "ambient-adc",
        }
    if not cand_path.is_file():
        raise ValueError(f"INVALID_GCP_ADC_JSON: credential file not found at {cand_path}")
    try:
        parsed = json.loads(cand_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("INVALID_GCP_ADC_JSON: malformed credential JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("INVALID_GCP_ADC_JSON: credential root must be a JSON object")
    cred_type = str(parsed.get("type") or "").strip()
    leaked_fields = sorted(k for k in FORBIDDEN_STATIC_KEY_FIELDS if parsed.get(k))
    if cred_type == "service_account" or leaked_fields:
        raise ValueError(
            "STATIC_GCP_KEY_FORBIDDEN: static service_account JSON keys are prohibited "
            "(use Workload Identity Federation external_account or ambient ADC)"
        )
    if cred_type not in VALID_WIF_CREDENTIAL_TYPES:
        raise ValueError(f"UNSUPPORTED_GCP_CREDENTIAL_TYPE: {cred_type!r}")
    return {"mode": "adc-file", "keyless_verified": True, "credential_type": cred_type}


def resolve_gcp_compute_tier_spec(
    cloud_cfg: Mapping[str, Any],
    *,
    service_name: str,
    def_ring: str,
    clean_env: str,
    egress_restricted: bool,
    mirror_env: Mapping[str, str],
) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """Validate Google-native compute tier (Cloud Run Gen2 vs. GKE Agent Sandbox, 0 CRDs)."""
    crd = str(cloud_cfg.get("orchestrator_crd") or "").strip().lower()
    if crd and crd != "gke-agent-sandbox":
        raise ValueError(
            f"THIRD_PARTY_AGENT_CRD_FORBIDDEN: external orchestrator CRD {crd!r} is prohibited; "
            "use native GKE Agent Sandbox (agents.x-k8s.io/v1alpha1, runtimeClassName='gvisor')"
        )
    tier = str(cloud_cfg.get("compute_tier") or DEFAULT_GCP_COMPUTE_TIER).strip().lower()
    if tier not in VALID_GCP_COMPUTE_TIERS:
        raise ValueError(
            f"UNSUPPORTED_GCP_COMPUTE_TIER: {tier!r} (expected one of {VALID_GCP_COMPUTE_TIERS})"
        )
    runtime_env = {
        "ZCG_NO_BROWSER": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ZCG_ACTIVE_ENV": clean_env,
        **mirror_env,
    }
    cloud_run_spec: dict[str, Any] = {
        "service_name": service_name,
        "execution_environment": "gen2",
        "scale_to_zero": True,
        "uid": CLOUD_RUN_NONROOT_UID,
        "read_only_root_filesystem": True,
        "healthcheck_path": "/healthz",
        "docs_access_mode": "disabled" if clean_env == "pro" else "authenticated",
        "ingress": ("all" if def_ring == "R0" else "internal-and-cloud-load-balancing"),
        "vpc_egress": "private-ranges-only" if egress_restricted else "all-traffic",
        "env": runtime_env,
    }
    if tier == "cloud-run-gen2":
        return tier, cloud_run_spec, None
    warm_pool = max(0, int(cloud_cfg.get("warm_pool_replicas") or 0))
    gke_sandbox_spec: dict[str, Any] = {
        "cluster_mode": "gke-autopilot",
        "api_version": GKE_SANDBOX_API_VERSION,
        "kind": "Sandbox",
        "runtime_class_name": GKE_SANDBOX_RUNTIME_CLASS,
        "uid": CLOUD_RUN_NONROOT_UID,
        "read_only_root_filesystem": True,
        "network_policy": "egress-restricted" if egress_restricted else "standard",
        "warm_pool_replicas": warm_pool,
        "third_party_crds": [],
        "env": runtime_env,
    }
    return tier, cloud_run_spec, gke_sandbox_spec


def materialize_cloud_deployment_manifest(
    workspace_dir: Path,
    manifest: Mapping[str, Any],
    topo: Mapping[str, Any],
    *,
    active_env: str = "dev",
    plugin_id: str = "",
    env_vars: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate keyless WIF/ADC posture and write surfaces/infra/cloud_deployment_<env>.json."""
    clean_env = active_env.strip().lower()
    if clean_env not in VALID_ENVIRONMENTS:
        raise ValueError(f"Invalid active_env {active_env!r}; must be in {VALID_ENVIRONMENTS}")
    raw_cd = manifest.get("cloud_deployment")
    cd: Mapping[str, Any] = raw_cd if isinstance(raw_cd, Mapping) else {}
    if any(cd.get(k) for k in FORBIDDEN_STATIC_KEY_FIELDS):
        raise ValueError("STATIC_GCP_KEY_FORBIDDEN: cloud_deployment contains static key fields")
    cred_check = verify_keyless_gcp_credentials(env=env_vars)

    ws = workspace_dir.resolve()
    lid = str(manifest.get("layer_id") or ws.name)
    posture = classify_exposure_posture(manifest, active_env=clean_env)["posture"]
    def_ring = resolve_posture_default_ring(posture)
    dg = topo.get("domain_governance")
    dg_map: Mapping[str, Any] = dg if isinstance(dg, Mapping) else {}
    pub_mode = str(dg_map.get("dns_publication") or "disabled-private-loopback")
    c_dom = str(dg_map.get("canonical_domain") or "").strip()
    d_dom = str(dg_map.get("developer_domain") or "").strip()
    i_zone = str(dg_map.get("intranet_zone") or "").strip()
    base_fqdn = (
        (c_dom or f"{lid}.run.app")
        if pub_mode == "public-authoritative"
        else (f"{lid}.{i_zone}" if i_zone else f"{lid}.internal")
    )
    fqdn = base_fqdn if clean_env == "pro" else f"{clean_env}.{base_fqdn}"
    dev_fqdn = (
        (d_dom if clean_env == "pro" else f"{clean_env}.{d_dom}")
        if (d_dom and pub_mode == "public-authoritative")
        else ""
    )
    eg_pol = resolve_effective_egress_policy(ws, manifest=manifest, canonical_domain=c_dom)
    comp_tier, cloud_run_spec, gke_sandbox_spec = resolve_gcp_compute_tier_spec(
        cd,
        service_name=f"{lid}-{clean_env}",
        def_ring=def_ring,
        clean_env=clean_env,
        egress_restricted=eg_pol.egress_restricted,
        mirror_env=eg_pol.artifact_mirrors.to_env_vars(),
    )
    iap_def = def_ring != "R0" and pub_mode != "disabled-private-loopback"
    iap_on = bool(cd.get("iap_enabled", iap_def))
    v_mode = resolve_surface_veracity_mode(manifest)
    attest_val = f"v=zcg1; node={lid}; env={clean_env}; ring={def_ring}; mode={v_mode}"
    dns_hosts = (fqdn, dev_fqdn) if dev_fqdn else (fqdn,)
    dns_records = (
        []
        if pub_mode == "disabled-private-loopback"
        else [
            rec
            for h in dns_hosts
            for rec in (
                {"type": "CNAME", "name": h, "target": "ghs.googlehosted.com.", "scope": pub_mode},
                {"type": "TXT", "name": f"_zcg-attest.{h}", "value": attest_val, "scope": pub_mode},
            )
        ]
    )
    doc: dict[str, Any] = {
        "schema_version": CLOUD_DEPLOY_CONTRACT_REV,
        "compute_tier": comp_tier,
        "layer_id": lid,
        "plugin_id": plugin_id or lid,
        "environment": clean_env,
        "exposure_posture": posture,
        "default_surface_ring": def_ring,
        "fqdn": fqdn,
        "developer_fqdn": dev_fqdn,
        "auth_preflight": cred_check,
        "workload_identity": {
            "project_id": str(cd.get("project_id") or "").strip(),
            "region": str(cd.get("region") or DEFAULT_CLOUD_REGION).strip(),
            "workload_identity_provider": str(cd.get("workload_identity_provider") or "").strip(),
            "service_account_email": str(cd.get("service_account_email") or "").strip(),
        },
        "cloud_run": cloud_run_spec,
        "gke_agent_sandbox": gke_sandbox_spec,
        "cloud_iap": {
            "enabled": iap_on,
            "oauth2_pkce_method": "S256",
            "required_ring": def_ring,
        },
        "cloud_dns": {"dns_publication": pub_mode, "records": dns_records},
        "egress_and_cdn": {
            "default_csp_source": eg_pol.default_csp_source,
            "egress_restricted": eg_pol.egress_restricted,
            "allowed_domains": list(eg_pol.allowed_domains),
            "cdn_origins": list(eg_pol.cdn_origins),
            "sri_hash_algorithm": "sha384",
            "artifact_mirrors": eg_pol.artifact_mirrors.to_dict(),
        },
    }
    out_file = ws / CLOUD_DEPLOY_REL_DIR / f"cloud_deployment_{clean_env}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc
