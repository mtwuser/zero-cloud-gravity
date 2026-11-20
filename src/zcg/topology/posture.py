"""Setup purpose archetypes, sovereign/managed posture, and surface origin resolution.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import (
    DEFAULT_PLUGIN_BASE_PORT,
    NODE_MANIFEST_REL_PATH,
    ROLE_DEFAULT_PRECEDENCE,
    VALID_ENVIRONMENTS,
    VALID_LAYER_ROLES,
)
from zcg.core.domain import is_safe_git_ref, is_safe_git_remote, is_safe_host
from zcg.core.manifests import load_node_manifest
from zcg.topology.identity import resolve_default_parent_dir, resolve_node_entity_identity

VALID_SETUP_PURPOSES: Final[tuple[str, ...]] = (
    "individual-sovereign",
    "academic-tutor",
    "enterprise-network",
    "public-institution",
    "knowledge-commons",
    "standalone-project",
    "b2b-consortium",
)
VALID_GOVERNANCE_POSTURES: Final[tuple[str, ...]] = ("sovereign", "managed")
PERSONAL_CONSTELLATION_PILLARS: Final[tuple[str, ...]] = (
    "profile",
    "tutor",
    "work",
    "wallet",
    "security",
    "game",
)
VALID_SETTLEMENT_MODES: Final[tuple[str, ...]] = (
    "none",
    "manual-reference",
    "dedicated-settlement-endpoint",
)
VALID_SURFACE_ORIGIN_MODES: Final[tuple[str, ...]] = (
    "loopback",
    "intranet-gateway",
    "cloud-ephemeral",
)
DEFAULT_INSPECT_TIMEOUT_SECONDS: Final[int] = 15
_PURPOSE_MATRIX: Final[dict[str, tuple[str, str, tuple[str, ...]]]] = {
    "individual-sovereign": (
        "workstation",
        "individual",
        ("universal-base", "workstation-control-tower"),
    ),
    "academic-tutor": (
        "department",
        "individual",
        ("academic-base", "academic-curriculum", "tutor-study-cockpit"),
    ),
    "enterprise-network": (
        "corporate",
        "enterprise",
        ("business-base", "corporate-operations", "corporate-root-hub"),
    ),
    "public-institution": (
        "corporate",
        "public-government",
        ("business-base", "corporate-operations", "science-base", "corporate-root-hub"),
    ),
    "knowledge-commons": (
        "knowledge",
        "open-source",
        ("science-base", "scientific-methodology", "knowledge-stewardship-portal"),
    ),
    "standalone-project": (
        "project",
        "individual",
        ("science-base", "software-engineering", "node-work-cockpit"),
    ),
    "b2b-consortium": (
        "corporate",
        "enterprise",
        ("business-base", "corporate-operations", "nist-csf-security", "corporate-root-hub"),
    ),
}
_MANAGED_SUBORDINATE_ROLES: Final[frozenset[str]] = frozenset(
    {"department", "domain-policy", "squad", "project", "service-node", "environment-cluster"}
)


def resolve_purpose_archetype(purpose: str, *, layer_role: str | None = None) -> dict[str, Any]:
    """Resolve deterministic role, entity_kind, posture, and templates for a setup purpose."""
    clean_purpose = purpose.strip().lower()
    if clean_purpose not in VALID_SETUP_PURPOSES:
        raise ValueError(f"Invalid purpose {purpose!r}: must be one of {VALID_SETUP_PURPOSES}")
    if layer_role is not None and layer_role not in VALID_LAYER_ROLES:
        raise ValueError(f"Invalid layer_role {layer_role!r}: must be one of {VALID_LAYER_ROLES}")
    def_role, def_ek, def_tpls = _PURPOSE_MATRIX[clean_purpose]
    eff_role = layer_role or def_role
    is_managed = (
        def_ek in ("enterprise", "public-government") and eff_role in _MANAGED_SUBORDINATE_ROLES
    )
    posture = "managed" if is_managed else "sovereign"
    tpls = (
        ("business-base", "software-engineering", "node-work-cockpit")
        if is_managed
        else (
            ("universal-base", "node-work-cockpit")
            if clean_purpose == "individual-sovereign" and eff_role != "workstation"
            else def_tpls
        )
    )
    def_prec = (
        90
        if clean_purpose == "individual-sovereign" and eff_role == "workstation"
        else (
            86
            if clean_purpose == "academic-tutor" and layer_role is None
            else ROLE_DEFAULT_PRECEDENCE[eff_role]
        )
    )
    return {
        "purpose": clean_purpose,
        "default_role": eff_role,
        "default_entity_kind": def_ek,
        "default_governance_posture": posture,
        "default_precedence": def_prec,
        "default_templates": list(tpls),
        "personal_constellation_pillars": (
            list(PERSONAL_CONSTELLATION_PILLARS) if clean_purpose == "individual-sovereign" else []
        ),
    }


def _classify_personal_pillar(
    layer_id: str, layer_role: str, entity_kind: str, manifest: Mapping[str, Any]
) -> str | None:
    if entity_kind != "individual":
        return None
    exp_pillar = str(manifest.get("personal_pillar") or "").strip().lower()
    if exp_pillar in PERSONAL_CONSTELLATION_PILLARS:
        return exp_pillar
    if layer_role == "workstation":
        return "profile"
    for suffix in PERSONAL_CONSTELLATION_PILLARS:
        if suffix != "profile" and (layer_id == suffix or layer_id.endswith(f"-{suffix}")):
            return suffix
    return None


def resolve_governance_posture(
    workspace_dir: Path,
    manifest: dict[str, Any] | None = None,
    parent_dir: Path | None = None,
) -> dict[str, Any]:
    """Resolve sovereign vs. managed posture, personal pillar airlocks, and tree isolation."""
    ws = workspace_dir.resolve()
    m = manifest if manifest is not None else load_node_manifest(ws)
    ident = resolve_node_entity_identity(ws, m, parent_dir=parent_dir)
    lid = str(ident["node_id"])
    lrole = str(m.get("layer_role") or "project")
    ek = str(ident["entity_kind"])
    gov_root = ident["governing_root_id"]
    is_root = ident["visibility_scope"].endswith(":root-0") or ek == "open-source"

    raw_posture = str(m.get("governance_posture") or "").strip().lower()
    inferred_managed = (
        ek in ("enterprise", "public-government")
        and not is_root
        and bool(gov_root and gov_root != lid)
    )
    posture = (
        raw_posture
        if raw_posture in VALID_GOVERNANCE_POSTURES
        else ("managed" if inferred_managed else "sovereign")
    )
    pillar = _classify_personal_pillar(lid, lrole, ek, m)
    is_wallet = pillar == "wallet"
    raw_sm = str(m.get("settlement_mode") or "none").strip().lower()
    settlement_mode = raw_sm if raw_sm in VALID_SETTLEMENT_MODES else "none"

    eff_p = resolve_default_parent_dir(ws, parent_dir)
    p_ek = (
        str(resolve_node_entity_identity(eff_p)["entity_kind"])
        if eff_p is not None and (eff_p / NODE_MANIFEST_REL_PATH).is_file()
        else ""
    )
    isolation_ok = not (posture == "managed" and p_ek == "individual")
    return {
        "node_id": lid,
        "entity_kind": ek,
        "governance_posture": posture,
        "governing_root_id": gov_root,
        "workspace_isolation_ok": isolation_ok,
        "personal_pillar": pillar,
        "default_surface_ring": "R3" if (is_wallet or posture == "sovereign") else "R2",
        "allow_external_peer_links": not is_wallet,
        "allow_epistemic_knowledge_feeds": True,
        "allow_cross_workspace_1hop_read": not is_wallet,
        "settlement_airlock_via": "work" if is_wallet else None,
        "settlement_mode": settlement_mode if pillar == "work" else "none",
    }


def resolve_surface_origin(
    manifest: Mapping[str, Any],
    *,
    active_env: str = "dev",
    port: int | None = None,
    forwarded_proto: str = "",
    forwarded_host: str = "",
    intranet_gateway: bool = False,
    env_vars: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve canonical browser origin across loopback, intranet-gateway, and cloud-ephemeral."""
    clean_env = active_env.strip().lower()
    if clean_env not in VALID_ENVIRONMENTS:
        raise ValueError(f"Invalid active_env {active_env!r}: must be in {VALID_ENVIRONMENTS}")
    eff_env = os.environ if env_vars is None else env_vars
    pub_override = str(eff_env.get("ZCG_SURFACE_PUBLIC_ORIGIN") or "").strip().rstrip("/")
    if pub_override:
        scheme, sep, host_part = pub_override.partition("://")
        if scheme not in ("http", "https") or not sep or not is_safe_host(host_part):
            raise ValueError(f"INVALID_SURFACE_ORIGIN_HOST: {pub_override!r}")
        return {
            "origin_mode": "cloud-ephemeral",
            "canonical_origin": pub_override,
            "dashboard_url": f"{pub_override}/dashboard",
        }
    f_host = forwarded_host.strip()
    if f_host:
        if not is_safe_host(f_host):
            raise ValueError(f"INVALID_SURFACE_ORIGIN_HOST: {forwarded_host!r}")
        proto = "http" if forwarded_proto.strip().lower() == "http" else "https"
        origin = f"{proto}://{f_host}"
        return {
            "origin_mode": "cloud-ephemeral",
            "canonical_origin": origin,
            "dashboard_url": f"{origin}/dashboard",
        }
    lid = str(manifest.get("layer_id") or "node").strip()
    prec = int(manifest.get("precedence", ROLE_DEFAULT_PRECEDENCE.get("project", 80)))
    eff_port = int(port or manifest.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + prec))
    raw_pni = manifest.get("public_node_identity")
    pni = raw_pni if isinstance(raw_pni, Mapping) else {}
    c_dom = str(pni.get("canonical_domain") or manifest.get("base_domain") or f"{lid}.local")
    if intranet_gateway:
        host_lbl = c_dom if clean_env == "pro" else f"{clean_env}.{c_dom}"
        origin = f"https://{host_lbl}"
        return {
            "origin_mode": "intranet-gateway",
            "canonical_origin": origin,
            "dashboard_url": f"{origin}/dashboard",
        }
    slug = (
        c_dom.removesuffix(".intranet.local")
        .removesuffix(".personal.local")
        .removesuffix(".knowledge.local")
        .removesuffix(".local")
    )
    loop_host = f"{slug}.localhost" if clean_env == "pro" else f"{clean_env}.{slug}.localhost"
    origin = f"http://{loop_host}:{eff_port}"
    return {
        "origin_mode": "loopback",
        "canonical_origin": origin,
        "dashboard_url": f"{origin}/dashboard",
    }


@contextmanager
def _checkout_node_source(
    source_ref: str,
    *,
    branch: str = "master",
    timeout_seconds: int = DEFAULT_INSPECT_TIMEOUT_SECONDS,
) -> Iterator[tuple[Path, str]]:
    clean_ref = source_ref.strip()
    if not clean_ref or clean_ref.startswith("-"):
        raise ValueError(f"UNSAFE_GIT_REMOTE_REF: {source_ref!r}")
    if not is_safe_git_ref(branch) or ".." in branch:
        raise ValueError(f"Invalid branch {branch!r}")
    if not is_safe_git_remote(clean_ref):
        local_dir = Path(clean_ref).expanduser().resolve()
        m_file = local_dir / NODE_MANIFEST_REL_PATH
        if not m_file.is_file():
            raise ValueError(f"Missing remote/local node manifest: {m_file}")
        yield local_dir, "local-path"
        return

    git_bin = shutil.which("git") or "/usr/bin/git"
    with tempfile.TemporaryDirectory(prefix="zcg-inspect-") as tmp_str:
        clone_dir = Path(tmp_str) / "node"
        proc = subprocess.run(  # noqa: S603
            [
                git_bin,
                "clone",
                "--quiet",
                "--depth",
                "1",
                "--single-branch",
                "--branch",
                branch,
                "--",
                clean_ref,
                str(clone_dir),
            ],
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if proc.returncode != 0:
            err_msg = proc.stderr.strip() or "git clone failed"
            raise ValueError(f"REMOTE_INSPECT_FAILED ({clean_ref}): {err_msg}")
        if not (clone_dir / NODE_MANIFEST_REL_PATH).is_file():
            raise ValueError(f"Missing {NODE_MANIFEST_REL_PATH} in remote {clean_ref!r}")
        yield clone_dir, "git-remote"


@contextmanager
def open_parent_source(
    from_parent: str | None,
    *,
    branch: str = "master",
    timeout_seconds: int = DEFAULT_INSPECT_TIMEOUT_SECONDS,
) -> Iterator[tuple[Path, str] | None]:
    """Yield (resolved_dir, source_kind) for a local/remote parent node, or None."""
    if from_parent is None:
        yield None
        return
    with _checkout_node_source(
        from_parent, branch=branch, timeout_seconds=timeout_seconds
    ) as checked_out:
        yield checked_out


def inspect_remote_node_manifest(
    source_ref: str,
    *,
    branch: str = "master",
    timeout_seconds: int = DEFAULT_INSPECT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Inspect system/zcg-node.json from a local directory or shallow Git remote checkout."""
    with _checkout_node_source(source_ref, branch=branch, timeout_seconds=timeout_seconds) as (
        node_dir,
        source_kind,
    ):
        m_doc = load_node_manifest(node_dir)
        ident = resolve_node_entity_identity(node_dir, m_doc)
        return _format_inspected_manifest(source_ref.strip(), source_kind, branch, m_doc, ident)


def _format_inspected_manifest(
    source_ref: str,
    source_kind: str,
    branch: str,
    manifest: dict[str, Any],
    ident: dict[str, Any],
) -> dict[str, Any]:
    pni = ident["public_node_identity"]
    return {
        "source_ref": source_ref,
        "source_kind": source_kind,
        "branch": branch,
        "layer_id": ident["node_id"],
        "layer_role": str(manifest.get("layer_role") or "project"),
        "entity_kind": ident["entity_kind"],
        "precedence": int(manifest.get("precedence", 80)),
        "governing_root_id": ident["governing_root_id"],
        "canonical_domain": pni["canonical_domain"],
        "default_stack_templates": list(manifest.get("default_stack_templates", [])),
        "manifest": manifest,
    }
