"""Root 0 domain/DNS governance, RFC 6761 *.localhost routing, and selective Web-Repo veracity.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from zcg.core.constants import (
    DEFAULT_PLUGIN_BASE_PORT,
    INDIVIDUAL_MIN_PRECEDENCE,
    NODE_MANIFEST_REL_PATH,
    OSS_WORKSTATION_IDS,
)
from zcg.core.manifests import load_node_manifest
from zcg.topology.identity import resolve_default_parent_dir
from zcg.web.templates import SafeHTML, render_icon

if TYPE_CHECKING:
    from collections.abc import Sequence

VALID_SURFACE_VERACITY_MODES: Final[tuple[str, ...]] = (
    "full-open-source",
    "curated-public-surface",
    "attestation-only",
)
DNS_MANIFEST_CONTRACT_REV: Final[str] = "zcg-dns-zone-v1"
SURFACE_SEAL_CONTRACT_REV: Final[str] = "zcg-surface-seal-v1"
DNS_ZONE_MANIFEST_REL_PATH: Final[str] = "surfaces/infra/dns_zone_manifest.json"
PUBLIC_SURFACE_SEAL_REL_PATH: Final[str] = "surfaces/attestation/public_surface_seal.json"
WELL_KNOWN_ATTESTATION_PATH: Final[str] = "/.well-known/zcg-attestation.json"
DEFAULT_COPYRIGHT_YEAR: Final[str] = "2026"
MAX_GOVERNANCE_HOPS: Final[int] = 3
SEAL_DIGEST_HEX_LEN: Final[int] = 16
CODE_FORGE_HOSTS: Final[tuple[str, ...]] = ("github.com", "gitlab.com", "codeberg.org")
DEFAULT_PUBLIC_SURFACE_ROUTES: Final[tuple[str, ...]] = (
    "GET /",
    f"GET {WELL_KNOWN_ATTESTATION_PATH}",
    "GET /dashboard",
    "GET /healthz",
)

_SSH_SCP_RE: Final[re.Pattern[str]] = re.compile(
    r"^git@([a-zA-Z0-9.-]+):([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+?)(?:\.git)?/?$"
)
_GIT_ORIGIN_RE: Final[re.Pattern[str]] = re.compile(
    r'\[remote\s+"origin"\][^\[]*?\burl\s*=\s*(\S+)'
)


def normalize_repo_web_url(raw_url: str) -> str:
    """Normalize SSH or HTTP(S) Git repository URLs to clean web URLs, rejecting local paths."""
    cleaned = raw_url.strip()
    if not cleaned:
        return ""
    if scp_match := _SSH_SCP_RE.match(cleaned):
        return f"https://{scp_match.group(1).lower()}/{scp_match.group(2)}"
    parsed = urlsplit(cleaned)
    if parsed.scheme in ("https", "http", "ssh") and parsed.hostname:
        clean_path = parsed.path.rstrip("/").removesuffix(".git")
        if not clean_path or clean_path == "/":
            return ""
        scheme = "http" if parsed.scheme == "http" else "https"
        port_part = f":{parsed.port}" if parsed.port and parsed.scheme != "ssh" else ""
        return f"{scheme}://{parsed.hostname.lower()}{port_part}{clean_path}"
    return ""


def _resolve_inherited_domain_governance(
    manifest: dict[str, Any], workspace_dir: Path | None, own_root: str
) -> dict[str, Any]:
    local_raw = manifest.get("domain_governance")
    local_dg: dict[str, Any] = dict(local_raw) if isinstance(local_raw, dict) else {}
    inherited_dg: dict[str, Any] = {}
    if workspace_dir is not None:
        cur = workspace_dir.resolve()
        visited: set[Path] = {cur}
        for _ in range(MAX_GOVERNANCE_HOPS):
            parent_ws = resolve_default_parent_dir(cur)
            if (
                parent_ws is None
                or parent_ws in visited
                or not (parent_ws / NODE_MANIFEST_REL_PATH).is_file()
            ):
                break
            visited.add(parent_ws)
            pm = load_node_manifest(parent_ws)
            p_lid = str(pm.get("layer_id") or parent_ws.name)
            p_root = str(pm.get("governing_root_id") or p_lid)
            if p_lid not in OSS_WORKSTATION_IDS and p_root == own_root:
                p_dg = pm.get("domain_governance")
                if isinstance(p_dg, dict):
                    inherited_dg = {**p_dg, **inherited_dg}
            cur = parent_ws
    return {**inherited_dg, **local_dg}


def resolve_domain_governance(
    manifest: dict[str, Any],
    *,
    layer_id: str,
    active_env: str = "dev",
    port: int,
    env_order: Sequence[str] = ("dev", "pro"),
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    """Resolve Root 0 domain/DNS governance and RFC 6761 *.localhost loopback URLs."""
    prec = int(manifest.get("precedence", 50))
    is_ind = manifest.get("entity_kind") == "individual" or prec >= INDIVIDUAL_MIN_PRECEDENCE
    l_role = str(manifest.get("layer_role") or "department")
    vis = str(manifest.get("visibility") or ("public" if l_role == "knowledge" else "private"))
    is_ind_priv = is_ind and vis != "public"
    root_id = str(manifest.get("governing_root_id") or layer_id)
    root_slug = root_id.removeprefix("corp-").removesuffix("-root") or layer_id
    eff_dg = _resolve_inherited_domain_governance(manifest, workspace_dir, root_id)

    raw_ldz = str(eff_dg.get("local_dev_zone") or "").strip().lower().strip(".")
    is_standalone_pub = l_role == "knowledge" and vis == "public" and root_id == layer_id
    def_ldz = f"{layer_id}.localhost" if is_standalone_pub else f"{root_slug}.localhost"
    local_dev_zone = (
        (raw_ldz if raw_ldz.endswith(".localhost") else f"{raw_ldz}.localhost")
        if raw_ldz
        else def_ldz
    )
    is_root_host = (
        layer_id == root_id
        or l_role in ("corporate", "workstation")
        or local_dev_zone.startswith(f"{layer_id}.")
    )
    node_localhost = (
        local_dev_zone
        if is_root_host
        else (
            f"{layer_id}.localhost"
            if (l_role == "knowledge" and vis == "public")
            else f"{layer_id}.{local_dev_zone}"
        )
    )
    sub_urls = {
        e: f"http://{node_localhost if e == 'pro' else f'{e}.{node_localhost}'}:{port}/?env={e}"
        for e in env_order
    }
    act_host = node_localhost if active_env == "pro" else f"{active_env}.{node_localhost}"
    canonical_dom = "" if is_ind_priv else str(eff_dg.get("canonical_domain") or "").strip().lower()
    def_intra = f"intranet.{canonical_dom}" if canonical_dom else ""
    intranet_zone = (
        "" if is_ind_priv else str(eff_dg.get("intranet_zone") or def_intra).strip().lower()
    )
    raw_auth = eff_dg.get("dns_authority")
    auth_map = raw_auth if isinstance(raw_auth, dict) else {}
    dns_pub = (
        "disabled-private-loopback"
        if is_ind_priv
        else ("public-authoritative" if vis == "public" else "private-split-horizon")
    )
    dns_auth = {
        "governed_by": str(auth_map.get("governed_by") or root_id),
        "delegated_operator_layer": str(
            auth_map.get("delegated_operator_layer") or (layer_id if is_ind_priv else root_id)
        ),
        "required_role": str(auth_map.get("required_role") or "owner"),
        "provider": "loopback-only" if is_ind_priv else str(
            auth_map.get("provider") or "google-cloud-dns"
        ),
    }  # fmt: skip
    return {
        "local_subdomain_host": act_host,
        "local_subdomain_url": f"http://{act_host}:{port}/?env={active_env}",
        "local_subdomain_dashboard_url": f"http://{act_host}:{port}/dashboard",
        "local_subdomain_urls": sub_urls,
        "domain_governance": {
            "governing_root_id": root_id, "canonical_domain": canonical_dom,
            "intranet_zone": intranet_zone, "local_dev_zone": local_dev_zone,
            "dns_publication": dns_pub, "dns_authority": dns_auth,
        },
    }  # fmt: skip


def resolve_surface_veracity_mode(manifest: dict[str, Any]) -> str:
    """Resolve selective Web-Repo veracity mode without forcing proprietary code exposure."""
    raw_mode = str(manifest.get("surface_veracity_mode") or "").strip().lower()
    if raw_mode in VALID_SURFACE_VERACITY_MODES:
        return raw_mode
    ek = str(manifest.get("entity_kind") or "").strip().lower()
    lid = str(manifest.get("layer_id") or "").strip().lower()
    lrole = str(manifest.get("layer_role") or "").strip().lower()
    vis = str(manifest.get("visibility") or ("public" if lrole == "knowledge" else "private"))
    if ek == "open-source" or (vis == "public" and lid.startswith(("gov-", "geo-", "sci-"))):
        return "full-open-source"
    if vis == "public":
        return "curated-public-surface"
    return "attestation-only"


def _read_git_origin_url(workspace_dir: Path) -> str:
    git_entry = workspace_dir / ".git"
    if git_entry.is_file():
        ptr = git_entry.read_text(encoding="utf-8", errors="ignore").partition("gitdir:")[2].strip()
        git_dir = (workspace_dir / ptr).resolve() if ptr else git_entry
    else:
        git_dir = git_entry
    cfg_path = git_dir / "config"
    if not cfg_path.is_file():
        return ""
    match = _GIT_ORIGIN_RE.search(cfg_path.read_text(encoding="utf-8", errors="ignore"))
    return match.group(1).strip() if match is not None else ""


def resolve_source_origin_metadata(
    workspace_dir: Path, manifest: dict[str, Any], *, is_public_pro: bool = False
) -> dict[str, str]:
    """Resolve copyright holder and privacy-filtered GitHub/forge Source Origin URL."""
    lid = str(manifest.get("layer_id") or workspace_dir.name)
    holder = str(manifest.get("copyright_holder") or manifest.get("display_name") or lid).strip()
    year = str(manifest.get("copyright_year") or DEFAULT_COPYRIGHT_YEAR).strip()
    repo_url = ""
    if not (is_public_pro and bool(manifest.get("hide_source_repo_in_pro"))):
        repo_url = normalize_repo_web_url(str(manifest.get("source_repo_url") or ""))
        pub_u = str(manifest.get("public_url") or "").strip()
        if not repo_url and (
            pub_u.endswith(".git") or any(h in pub_u.lower() for h in CODE_FORGE_HOSTS)
        ):
            repo_url = normalize_repo_web_url(pub_u)
        if not repo_url and (
            not is_public_pro or str(manifest.get("visibility") or "") == "public"
        ):
            repo_url = normalize_repo_web_url(_read_git_origin_url(workspace_dir))
    label = repo_url.removeprefix("https://").removeprefix("http://") if repo_url else ""
    return {
        "entity_display_name": holder, "copyright_year": year,
        "source_repo_url": repo_url, "source_repo_label": label,
    }  # fmt: skip


def materialize_dns_zone_manifest(
    workspace_dir: Path, manifest: dict[str, Any], topo: dict[str, Any]
) -> dict[str, Any]:
    """Write declarative DNS authority and _zcg-attest TXT records in surfaces/infra/."""
    ws = workspace_dir.resolve()
    lid = str(manifest.get("layer_id") or ws.name)
    dg = topo.get("domain_governance") or {}
    pub_mode = str(dg.get("dns_publication") or "disabled-private-loopback")
    c_dom = str(dg.get("canonical_domain") or "")
    i_zone = str(dg.get("intranet_zone") or "")
    v_mode = resolve_surface_veracity_mode(manifest)
    records: list[dict[str, str]] = []
    if pub_mode != "disabled-private-loopback":
        fqdn = (
            (c_dom or str(topo.get("node_host") or lid))
            if pub_mode == "public-authoritative"
            else (f"{lid}.{i_zone}" if i_zone else str(topo.get("node_host") or lid))
        )
        records = [
            {"type": "A", "name": fqdn, "target": "127.0.0.1", "scope": pub_mode},
            {"type": "TXT", "name": f"_zcg-attest.{fqdn}",
             "value": f"v=zcg1; node={lid}; mode={v_mode}", "scope": pub_mode},
        ]  # fmt: skip
    doc: dict[str, Any] = {
        "schema_version": DNS_MANIFEST_CONTRACT_REV, "layer_id": lid,
        "local_rfc6761_subdomain": str(topo.get("local_subdomain_host") or ""),
        "domain_governance": dg, "records": records,
    }  # fmt: skip
    out = ws / DNS_ZONE_MANIFEST_REL_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def build_public_surface_seal(
    workspace_dir: Path,
    manifest: dict[str, Any],
    topo: dict[str, Any],
    *,
    active_env: str = "dev",
    web_dirs: Sequence[Path] = (),
    route_signatures: Sequence[str] = (),
) -> dict[str, Any]:
    """Build SHA-256 route and asset Merkle commitments for Web <-> Repo verification."""
    ws = workspace_dir.resolve()
    lid = str(manifest.get("layer_id") or ws.name)
    gov_root = str(manifest.get("governing_root_id") or lid)
    is_pub_pro = str(topo.get("visibility") or "") == "public" and active_env == "pro"
    v_mode = resolve_surface_veracity_mode(manifest)
    origin = resolve_source_origin_metadata(ws, manifest, is_public_pro=is_pub_pro)
    eff_dirs = tuple(web_dirs) if web_dirs else (ws / "surfaces/web",)
    asset_digests: list[str] = []
    for base_d in eff_dirs:
        if not base_d.is_dir():
            continue
        for fpath in sorted(p for p in base_d.rglob("*") if p.is_file()):
            if fpath.suffix in (".py", ".pyc"):
                continue
            rel_posix = fpath.relative_to(base_d).as_posix()
            with fpath.open("rb") as fh:
                f_hex = hashlib.file_digest(fh, "sha256").hexdigest()
            asset_digests.append(f"{rel_posix}:{f_hex}")
    merkle_root = hashlib.sha256("\n".join(sorted(asset_digests)).encode("utf-8")).hexdigest()
    eff_routes = (
        sorted(set(route_signatures)) if route_signatures else list(DEFAULT_PUBLIC_SURFACE_ROUTES)
    )
    routes_digest = hashlib.sha256("\n".join(eff_routes).encode("utf-8")).hexdigest()[
        :SEAL_DIGEST_HEX_LEN
    ]
    can_dom = str(
        (topo.get("domain_governance") or {}).get("canonical_domain") or topo.get("node_host") or ""
    )
    seal_material = (
        f"{lid}|{gov_root}|{active_env}|{v_mode}|{can_dom}|"
        f"{origin['source_repo_url']}|{routes_digest}|{merkle_root}"
    )
    seal_digest = hashlib.sha256(seal_material.encode("utf-8")).hexdigest()[:SEAL_DIGEST_HEX_LEN]
    return {
        "schema_version": SURFACE_SEAL_CONTRACT_REV, "layer_id": lid,
        "governing_root_id": gov_root, "environment": active_env,
        "surface_veracity_mode": v_mode, "code_exposure_required": v_mode == "full-open-source",
        "canonical_domain": can_dom,
        "local_rfc6761_subdomain": str(topo.get("local_subdomain_host") or ""),
        "source_repo_url": origin["source_repo_url"],
        "copyright": f"© {origin['copyright_year']} {origin['entity_display_name']}",
        "public_routes_count": len(eff_routes), "public_routes_digest": routes_digest,
        "served_assets_count": len(asset_digests), "served_assets_merkle_root": merkle_root,
        "seal_digest": seal_digest, "verification_endpoint": WELL_KNOWN_ATTESTATION_PATH,
    }  # fmt: skip


def materialize_node_provenance_surfaces(
    workspace_dir: Path, manifest: dict[str, Any], topo: dict[str, Any], *, active_env: str = "dev"
) -> dict[str, Any]:
    """Materialize both DNS authority and surface attestation JSON files under surfaces/."""
    ws = workspace_dir.resolve()
    dns_doc = materialize_dns_zone_manifest(ws, manifest, topo)
    seal_doc = build_public_surface_seal(ws, manifest, topo, active_env=active_env)
    seal_out = ws / PUBLIC_SURFACE_SEAL_REL_PATH
    seal_out.parent.mkdir(parents=True, exist_ok=True)
    seal_out.write_text(json.dumps(seal_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"dns_zone": dns_doc, "surface_seal": seal_doc}


def render_provenance_footer_html(
    workspace_dir: Path, manifest: dict[str, Any], topo: dict[str, Any], *, active_env: str = "dev"
) -> SafeHTML:
    """Render SafeHTML copyright, RFC 6761/canonical domain, GitHub origin, and veracity footer."""
    is_pub_pro = str(topo.get("visibility") or "") == "public" and active_env == "pro"
    origin = resolve_source_origin_metadata(workspace_dir, manifest, is_public_pro=is_pub_pro)
    v_mode = resolve_surface_veracity_mode(manifest)
    port = int(topo.get("port") or DEFAULT_PLUGIN_BASE_PORT)
    sub_host = str(topo.get("local_subdomain_host") or f"{active_env}.localhost")
    sub_dash = str(
        topo.get("local_subdomain_dashboard_url") or f"http://{sub_host}:{port}/dashboard"
    )
    can_dom = str((topo.get("domain_governance") or {}).get("canonical_domain") or "")
    dom_lbl = can_dom if (is_pub_pro and can_dom) else f"{sub_host}:{port}"
    repo_html = (
        f"<a href='{html.escape(origin['source_repo_url'], quote=True)}' "
        f"target='_blank' rel='noopener noreferrer'>{render_icon('github')}"
        f"Source Origin: <code>{html.escape(origin['source_repo_label'])}</code></a>"
        if origin["source_repo_url"]
        else f"<span>{render_icon('lock')}Source Origin: <code>private-sovereign-repo</code></span>"
    )
    return SafeHTML(
        "<div class='zcg-provenance-footer' data-zcg-provenance='footer'>"
        f"<span>© {html.escape(origin['copyright_year'])} "
        f"<strong>{html.escape(origin['entity_display_name'])}</strong></span> · "
        f"<a href='{html.escape(sub_dash, quote=True)}' title='Active node domain'>"
        f"{render_icon('globe')}Domain: <code>{html.escape(dom_lbl)}</code></a> · "
        f"{repo_html} · "
        f"<a href='{WELL_KNOWN_ATTESTATION_PATH}'>"
        f"{render_icon('shield')}Attestation (<code>{html.escape(v_mode)}</code>)</a> · "
        f"<a href='/healthz'>{render_icon('activity')}<code>/healthz</code></a></div>"
    )
