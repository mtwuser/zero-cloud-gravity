"""Opt-in self-hosted OCI container and TLS 1.3 reverse-proxy deployment provider.

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

CONTAINER_DEPLOY_CONTRACT_REV: Final[str] = "zcg-container-deploy-v1"
CONTAINER_DEPLOY_REL_DIR: Final[str] = "surfaces/infra"
CONTAINER_NONROOT_UID: Final[int] = 10001
COMPUTE_TIER_SELF_HOSTED_OCI: Final[str] = "self-hosted-oci"
VALID_EDGE_PROXIES: Final[frozenset[str]] = frozenset({"caddy", "nginx", "traefik", "direct-tls"})
FORBIDDEN_CONTAINER_SECRET_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "private_key",
        "tls_private_key_pem",
        "oidc_client_secret",
        "database_password",
        "api_secret",
    }
)


def verify_secretless_container_posture(
    container_cfg: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Verify container deployment config omits inline static secrets and uses runtime mounts."""
    eff_env = os.environ if env is None else env
    leaked_fields = sorted(k for k in FORBIDDEN_CONTAINER_SECRET_FIELDS if container_cfg.get(k))
    if leaked_fields or eff_env.get("ZCG_STATIC_CONTAINER_SECRET", "").strip():
        raise ValueError(
            "STATIC_CONTAINER_SECRET_FORBIDDEN: inline container secrets are prohibited "
            "(inject secrets via /run/secrets/* or runtime environment variables)"
        )
    proxy_kind = str(container_cfg.get("reverse_proxy") or "caddy").strip().lower()
    if proxy_kind not in VALID_EDGE_PROXIES:
        raise ValueError(
            f"UNSUPPORTED_EDGE_PROXY: {proxy_kind!r} (expected one of {sorted(VALID_EDGE_PROXIES)})"
        )
    return {
        "secretless_verified": True,
        "secret_mount_dir": "/run/secrets",
        "reverse_proxy": proxy_kind,
    }


def materialize_container_deployment_manifest(
    workspace_dir: Path,
    manifest: Mapping[str, Any],
    topo: Mapping[str, Any],
    *,
    active_env: str = "dev",
    plugin_id: str = "",
    env_vars: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate secretless OCI posture and write surfaces/infra/container_deployment_<env>.json."""
    clean_env = active_env.strip().lower()
    if clean_env not in VALID_ENVIRONMENTS:
        raise ValueError(f"Invalid active_env {active_env!r}; must be in {VALID_ENVIRONMENTS}")
    raw_cd = manifest.get("container_deployment")
    cd: Mapping[str, Any] = raw_cd if isinstance(raw_cd, Mapping) else {}
    preflight = verify_secretless_container_posture(cd, env=env_vars)

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
        (c_dom or f"{lid}.selfhosted.local")
        if pub_mode == "public-authoritative"
        else (f"{lid}.{i_zone}" if i_zone else f"{lid}.intranet.local")
    )
    fqdn = base_fqdn if clean_env == "pro" else f"{clean_env}.{base_fqdn}"
    dev_fqdn = (
        (d_dom if clean_env == "pro" else f"{clean_env}.{d_dom}")
        if (d_dom and pub_mode == "public-authoritative")
        else ""
    )
    eg_pol = resolve_effective_egress_policy(ws, manifest=manifest, canonical_domain=c_dom)
    proxy_kind = str(preflight["reverse_proxy"])
    entrypoint_args = (
        [
            "python3",
            "-m",
            "zcg.cockpit.ops.asgi",
            "--tls-certfile",
            "/run/secrets/tls.crt",
            "--tls-keyfile",
            "/run/secrets/tls.key",
        ]
        if proxy_kind == "direct-tls"
        else ["python3", "-m", "zcg.cockpit.ops.asgi", "--behind-tls-proxy"]
    )
    edge_ip = str(cd.get("edge_ipv4") or "203.0.113.10").strip()
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
                {"type": "A", "name": h, "target": edge_ip, "scope": pub_mode},
                {"type": "TXT", "name": f"_zcg-attest.{h}", "value": attest_val, "scope": pub_mode},
            )
        ]
    )
    doc: dict[str, Any] = {
        "schema_version": CONTAINER_DEPLOY_CONTRACT_REV,
        "compute_tier": COMPUTE_TIER_SELF_HOSTED_OCI,
        "sandbox_isolation": "rootless-oci+bwrap-readonly",
        "layer_id": lid,
        "plugin_id": plugin_id or lid,
        "environment": clean_env,
        "exposure_posture": posture,
        "default_surface_ring": def_ring,
        "fqdn": fqdn,
        "developer_fqdn": dev_fqdn,
        "auth_preflight": preflight,
        "oci_container": {
            "service_name": f"{lid}-{clean_env}",
            "runtime_engine": str(cd.get("runtime_engine") or "podman-or-docker").strip(),
            "uid": CONTAINER_NONROOT_UID,
            "read_only_root_filesystem": True,
            "runtime_wal_volume": "/var/lib/zcg/runtime",
            "healthcheck_path": "/healthz",
            "docs_access_mode": "disabled" if clean_env == "pro" else "authenticated",
            "command": entrypoint_args,
            "env": {
                "ZCG_NO_BROWSER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "ZCG_ACTIVE_ENV": clean_env,
                **eg_pol.artifact_mirrors.to_env_vars(),
            },
        },
        "edge_tls_proxy": {
            "provider": proxy_kind,
            "tls_min_version": "TLSv1.3",
            "hsts_enabled": True,
            "oauth2_pkce_method": "S256",
            "required_ring": def_ring,
        },
        "rfc_dns": {"dns_publication": pub_mode, "records": dns_records},
        "egress_and_cdn": {
            "default_csp_source": eg_pol.default_csp_source,
            "egress_restricted": eg_pol.egress_restricted,
            "allowed_domains": list(eg_pol.allowed_domains),
            "cdn_origins": list(eg_pol.cdn_origins),
            "sri_hash_algorithm": "sha384",
            "artifact_mirrors": eg_pol.artifact_mirrors.to_dict(),
        },
    }
    out_file = ws / CONTAINER_DEPLOY_REL_DIR / f"container_deployment_{clean_env}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc
