"""Hierarchical Lex Superior network_egress_policy, CDN origins, and private artifact mirrors.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from zcg.core.constants import NODE_MANIFEST_REL_PATH
from zcg.core.domain import normalize_cdn_origins
from zcg.core.manifests import load_node_manifest
from zcg.topology.identity import resolve_default_parent_dir
from zcg.topology.posture import resolve_governance_posture

LOOPBACK_EGRESS_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_CSP_SOURCE: Final[str] = "'self'"
_LOCAL_DOMAIN_SUFFIXES: Final[tuple[str, ...]] = (".local", ".internal", ".localhost")
_URL_TERMINATORS: Final[frozenset[str]] = frozenset(
    {" ", "\t", "\r", "\n", '"', "'", "<", ">", "`", ")", "]"}
)


def is_egress_host_allowed(host: str, allowed_domains: Sequence[str]) -> bool:
    """Return True when host is loopback or matches any fnmatch pattern in allowed_domains."""
    clean_h = host.strip().lower().rstrip(".")
    if clean_h in LOOPBACK_EGRESS_HOSTS or clean_h.endswith(".localhost"):
        return True
    return any(fnmatchcase(clean_h, pat.strip().lower()) for pat in allowed_domains if pat.strip())


def extract_http_url_spans(text: str) -> list[str]:
    """Extract raw http:// and https:// URL spans terminated by whitespace or delimiters."""
    low = text.lower()
    n = len(text)
    spans: list[str] = []
    pos = 0
    while pos < n:
        candidates = [
            idx for idx in (low.find("http://", pos), low.find("https://", pos)) if idx != -1
        ]
        if not candidates:
            break
        start = min(candidates)
        end = start
        while end < n and text[end] not in _URL_TERMINATORS:
            end += 1
        spans.append(text[start:end])
        pos = end
    return spans


def find_unauthorized_egress_hosts(text: str, allowed_domains: Sequence[str]) -> list[str]:
    """Return labels for HTTP(S) URLs in text violating allowed_domains or RFC 3986 userinfo."""
    blocked: list[str] = []
    for span in extract_http_url_spans(text):
        raw_url = span.rstrip(".,;:")
        parts = urlsplit(raw_url)
        host = (parts.hostname or "").lower()
        has_userinfo = "@" in parts.netloc
        if has_userinfo or not host or not is_egress_host_allowed(host, allowed_domains):
            blocked.append(parts.netloc if has_userinfo else (host or raw_url))
    return blocked


def _extract_domain_and_url(raw_entry: str) -> tuple[str, str]:
    clean = raw_entry.strip().rstrip("/")
    if not clean:
        return "", ""
    if "://" in clean:
        parts = urlsplit(clean)
        host = (parts.hostname or "").lower()
        b_url = (
            f"{parts.scheme.lower()}://{parts.netloc.lower()}" if host and "*" not in host else ""
        )
        return host, b_url
    host = clean.lower().split("/", maxsplit=1)[0]
    b_url = f"https://{host}" if host and "*" not in host else ""
    return host, b_url


def _validate_mirror_endpoint(
    raw_value: str,
    *,
    allow_registry_host_path: bool,
    egress_restricted: bool,
    allowed_domains: Sequence[str],
) -> str:
    clean = raw_value.strip().rstrip("/")
    if not clean:
        return ""
    candidate = f"https://{clean}" if allow_registry_host_path and "://" not in clean else clean
    parts = urlsplit(candidate)
    host = (parts.hostname or "").lower()
    if (
        parts.scheme.lower() != "https"
        or not host
        or parts.username is not None
        or parts.password is not None
        or " " in clean
    ):
        raise ValueError(f"UNAUTHORIZED_ARTIFACT_MIRROR: invalid HTTPS endpoint {raw_value!r}")
    if egress_restricted and not is_egress_host_allowed(host, allowed_domains):
        raise ValueError(
            f"UNAUTHORIZED_ARTIFACT_MIRROR: {host!r} outside network_egress_policy.allowed_domains"
        )
    return clean if allow_registry_host_path and "://" not in clean else candidate


@dataclass(frozen=True, slots=True)
class ArtifactMirrorConfig:
    """Governed private Artifact Registry, PyPI, and APT mirror configuration."""

    container_registry: str = ""
    pypi_index_url: str = ""
    apt_mirror_url: str = ""
    require_private_mirrors: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize mirror configuration to a JSON-compatible dictionary."""
        return {
            "container_registry": self.container_registry,
            "pypi_index_url": self.pypi_index_url,
            "apt_mirror_url": self.apt_mirror_url,
            "require_private_mirrors": self.require_private_mirrors,
        }

    def to_env_vars(self) -> dict[str, str]:
        """Project configured private mirrors onto deterministic container/toolchain env vars."""
        env: dict[str, str] = {}
        if self.container_registry:
            env["ZCG_CONTAINER_REGISTRY"] = self.container_registry
        if self.pypi_index_url:
            env["PIP_INDEX_URL"] = self.pypi_index_url
            env["UV_DEFAULT_INDEX"] = self.pypi_index_url
        elif self.require_private_mirrors:
            env["PIP_NO_INDEX"] = "1"
        if self.apt_mirror_url:
            env["ZCG_APT_MIRROR_URL"] = self.apt_mirror_url
        return env


@dataclass(frozen=True, slots=True)
class EffectiveEgressPolicy:
    """Resolved Lex Superior network_egress_policy, CDN origins, and private mirrors."""

    layer_id: str
    lineage_layers: tuple[str, ...]
    default_csp_source: str
    egress_restricted: bool
    is_loopback_isolated: bool
    allowed_domains: tuple[str, ...]
    browser_allowlist_urls: tuple[str, ...]
    cdn_origins: tuple[str, ...]
    artifact_mirrors: ArtifactMirrorConfig

    def to_dict(self) -> dict[str, Any]:
        """Serialize effective egress policy to a JSON-compatible dictionary."""
        return {
            "layer_id": self.layer_id,
            "lineage_layers": list(self.lineage_layers),
            "default_csp_source": self.default_csp_source,
            "egress_restricted": self.egress_restricted,
            "is_loopback_isolated": self.is_loopback_isolated,
            "allowed_domains": list(self.allowed_domains),
            "browser_allowlist_urls": list(self.browser_allowlist_urls),
            "cdn_origins": list(self.cdn_origins),
            "artifact_mirrors": self.artifact_mirrors.to_dict(),
        }


def resolve_effective_egress_policy(
    workspace_dir: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
    parent_dir: Path | None = None,
    canonical_domain: str = "",
) -> EffectiveEgressPolicy:
    """Resolve inherited Lex Superior egress domains, CDN origins, and private artifact mirrors."""
    ws = workspace_dir.resolve()
    ws_m = dict(manifest) if manifest is not None else load_node_manifest(ws)
    lid = str(ws_m.get("layer_id") or ws.name)
    eff_parent = resolve_default_parent_dir(ws, parent_dir)
    p_info = resolve_governance_posture(ws, ws_m, parent_dir=eff_parent)
    is_wallet = p_info.get("personal_pillar") == "wallet" or not bool(
        p_info.get("allow_cross_workspace_1hop_read", True)
    )
    chain: list[tuple[str, Mapping[str, Any]]] = []
    if (
        eff_parent is not None
        and eff_parent.resolve() != ws
        and (eff_parent / NODE_MANIFEST_REL_PATH).is_file()
    ):
        pm = load_node_manifest(eff_parent.resolve())
        chain.append((str(pm.get("layer_id") or eff_parent.name), pm))
    chain.append((lid, ws_m))
    lineage = tuple(item[0] for item in chain)

    if is_wallet:
        return EffectiveEgressPolicy(
            layer_id=lid,
            lineage_layers=lineage,
            default_csp_source=DEFAULT_CSP_SOURCE,
            egress_restricted=True,
            is_loopback_isolated=True,
            allowed_domains=(),
            browser_allowlist_urls=(),
            cdn_origins=(),
            artifact_mirrors=ArtifactMirrorConfig(require_private_mirrors=True),
        )

    allowed_set: set[str] | None = None
    url_map: dict[str, str] = {}
    raw_cdns: list[str] = []
    enable_canon_cdn = False
    mirrors_locked = False
    c_reg, pypi_u, apt_u, req_priv = "", "", "", False

    for _, m_doc in chain:
        raw_eg = m_doc.get("network_egress_policy")
        eg: Mapping[str, Any] = raw_eg if isinstance(raw_eg, Mapping) else {}
        has_dom_list = isinstance(eg.get("allowed_domains"), list) or isinstance(
            eg.get("allowed_hosts"), list
        )
        if has_dom_list:
            layer_doms: set[str] = set()
            for field in ("allowed_domains", "allowed_hosts"):
                raw_items = eg.get(field)
                if isinstance(raw_items, list):
                    for entry in raw_items:
                        dom, b_url = _extract_domain_and_url(str(entry))
                        if dom:
                            layer_doms.add(dom)
                        if dom and b_url:
                            url_map[dom] = b_url
            allowed_set = layer_doms if allowed_set is None else (allowed_set & layer_doms)

        if isinstance(eg.get("cdn_origins"), list):
            raw_cdns.extend(str(x) for x in eg["cdn_origins"])
        if bool(eg.get("enable_canonical_cdn", False)):
            enable_canon_cdn = True

        raw_mir = eg.get("artifact_mirrors")
        mir: Mapping[str, Any] = raw_mir if isinstance(raw_mir, Mapping) else {}
        req_priv = req_priv or bool(mir.get("require_private_mirrors", False))
        if not mirrors_locked:
            if str(mir.get("container_registry") or "").strip():
                c_reg = str(mir["container_registry"]).strip()
            if str(mir.get("pypi_index_url") or "").strip():
                pypi_u = str(mir["pypi_index_url"]).strip()
            if str(mir.get("apt_mirror_url") or "").strip():
                apt_u = str(mir["apt_mirror_url"]).strip()
            mirrors_locked = bool(mir.get("lock_mirrors", False))

    clean_c_dom = canonical_domain.strip().lower().rstrip(".")
    if enable_canon_cdn and clean_c_dom and not clean_c_dom.endswith(_LOCAL_DOMAIN_SUFFIXES):
        raw_cdns.append(f"https://cdn.{clean_c_dom}")

    egress_restricted = allowed_set is not None
    eff_domains = tuple(sorted(allowed_set or ()))
    norm_cdns = normalize_cdn_origins(raw_cdns)
    for cdn_url in norm_cdns:
        cdn_host = (urlsplit(cdn_url).hostname or "").lower()
        if egress_restricted and not is_egress_host_allowed(cdn_host, eff_domains):
            raise ValueError(f"UNAUTHORIZED_CDN_EGRESS_ORIGIN: {cdn_url!r} outside allowed_domains")

    val_mirrors = ArtifactMirrorConfig(
        container_registry=_validate_mirror_endpoint(
            c_reg,
            allow_registry_host_path=True,
            egress_restricted=egress_restricted,
            allowed_domains=eff_domains,
        ),
        pypi_index_url=_validate_mirror_endpoint(
            pypi_u,
            allow_registry_host_path=False,
            egress_restricted=egress_restricted,
            allowed_domains=eff_domains,
        ),
        apt_mirror_url=_validate_mirror_endpoint(
            apt_u,
            allow_registry_host_path=False,
            egress_restricted=egress_restricted,
            allowed_domains=eff_domains,
        ),
        require_private_mirrors=req_priv,
    )

    browser_urls = tuple(
        dict.fromkeys([*(url_map[d] for d in eff_domains if d in url_map), *norm_cdns])
    )

    return EffectiveEgressPolicy(
        layer_id=lid,
        lineage_layers=lineage,
        default_csp_source=DEFAULT_CSP_SOURCE,
        egress_restricted=egress_restricted,
        is_loopback_isolated=False,
        allowed_domains=eff_domains,
        browser_allowlist_urls=browser_urls,
        cdn_origins=norm_cdns,
        artifact_mirrors=val_mirrors,
    )
