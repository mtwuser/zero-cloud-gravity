"""Sovereign CV disclosure projection, workspace-backed profile synthesis, and Root 0 hub facets.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import DEFAULT_PLUGIN_BASE_PORT
from zcg.core.manifests import load_node_manifest
from zcg.topology.exposure import is_public_portal_enabled
from zcg.web.auth.surface_access import VALID_DISCLOSURE_TIERS
from zcg.web.ui.templates import SafeHTML, TemplateCatalog

_DELEGABLE_PILLARS: Final[tuple[tuple[str, str, str, str], ...]] = (
    (
        "work",
        "Career, Ventures & CV",
        "Portfolio, advisory engagements, and ring-projected CV.",
        "b2b-collaboration",
    ),
    (
        "tutor",
        "Academic Study & Tutoring",
        "Curriculum tracks and tutoring sessions.",
        "tutoring-session",
    ),
    (
        "game",
        "Spatial Simulation & Matchmaking",
        "Deterministic simulation scenes and matches.",
        "game-match-invite",
    ),
    (
        "wallet",
        "Public R0 Stewardship",
        "Verifiable watch-only public stewardship receipts.",
        "stewardship-support",
    ),
)


@dataclass(frozen=True, slots=True)
class CVFieldEntry:
    """Single curriculum vitae entry governed by a minimum DisclosureTier ceiling."""

    field_id: str
    label: str
    value: str
    disclosure_tier: str = "core_summary"
    section: str = "summary"

    def __post_init__(self) -> None:
        if not self.field_id.strip():
            raise ValueError("CVFieldEntry.field_id must be non-blank")
        if self.disclosure_tier not in VALID_DISCLOSURE_TIERS:
            raise ValueError(f"Invalid CV disclosure_tier {self.disclosure_tier!r}")


@dataclass(frozen=True, slots=True)
class CVProfileSpec:
    """Declarative sovereign portfolio & CV specification across R0..R3 rings."""

    full_name: str
    headline: str
    public_domain: str
    public_contact: str
    entries: tuple[CVFieldEntry, ...]

    @classmethod
    def default_reference_spec(
        cls, node_id: str = "pub-persona", *, public_domain: str = "persona.example.org"
    ) -> CVProfileSpec:
        """Build an ISO-neutral 4-tier reference CV profile for sovereign twin nodes."""
        cd = public_domain.strip() or "persona.example.org"
        e1 = "Designs zero-dependency Python 3.14 ASGI engines and sovereign node meshes."
        e2 = "Python 3.14 (PEP 703/649/695), Native ASGI 3.0, SQLite WAL, TLS 1.3, GCP WIF."
        e3 = "Delivered 100-module ZeroCloudGravity platform at 100.00% isolated coverage."
        e4 = "Available for B2B architectural advisory and sovereign node deployments."
        e5 = f"https://{cd}/.well-known/zcg-attestation.json (Ring R3 Operator)"
        t0, t1, t2, t3 = VALID_DISCLOSURE_TIERS
        f = CVFieldEntry
        return cls(
            f"{node_id} Sovereign Architecture Profile",
            "Principal Distributed Systems & Zero-Cloud Security Architect",
            cd,
            f"contact@{cd}",
            (
                f("exec_summary", "Executive Summary", e1, t0, "summary"),
                f("core_stack", "Core Engineering Stack", e2, t0, "competencies"),
                f("verified_arch", "Verified Reference Systems", e3, t1, "experience"),
                f("onboarding_entity", "Contracting & Engagement Scope", e4, t2, "engagement"),
                f("bilateral_mesh", "Direct Bilateral Peer Mesh Endpoint", e5, t3, "mesh"),
            ),
        )


def resolve_entity_portal_kind(manifest: Mapping[str, Any] | None, entity_kind: str) -> str:
    """Select the canonical portal_kind across OSS, Enterprise, Personal Hub, and Personal CV."""
    ek = entity_kind.strip().lower()
    if ek == "enterprise":
        return "corporate-brand-portal"
    if ek == "individual":
        role = str((manifest or {}).get("layer_role") or "").strip().lower()
        return "personal-constellation-hub" if role == "workstation" else "personal-portfolio-cv"
    return "oss-flagship-portal"


def _extract_readme_title_and_summary(workspace_dir: Path | None) -> tuple[str, str]:
    if workspace_dir is None or not (rm := workspace_dir / "README.md").is_file():
        return "", ""
    title, summary = "", ""
    for raw in rm.read_text(encoding="utf-8").splitlines():
        ln = raw.strip()
        if not title and ln.startswith("# "):
            cand = ln.removeprefix("# ").strip()
            if "[Fill:" not in cand:
                title = cand
        elif (
            title and not summary and ln and not ln.startswith(("#", ">", "-", "|", "`", "[Fill:"))
        ):
            summary = ln
            break
    return title, summary


def resolve_workspace_cv_profile(
    workspace_dir: Path | None,
    manifest: Mapping[str, Any] | None = None,
    *,
    node_id: str = "pub-persona",
    public_domain: str = "persona.example.org",
) -> CVProfileSpec:
    """Synthesize a CVProfileSpec from declarative cv_profile or real <persona>-work metadata."""
    m = (
        dict(manifest)
        if isinstance(manifest, Mapping)
        else (load_node_manifest(workspace_dir) if workspace_dir is not None else {})
    )
    cd = public_domain.strip() or node_id
    raw_cv = m.get("cv_profile")
    if isinstance(raw_cv, Mapping):
        raw_ent = raw_cv.get("entries")
        parsed_entries = tuple(
            CVFieldEntry(
                str(e.get("field_id") or f"entry-{i}"),
                str(e.get("label") or "Entry"),
                str(e.get("value") or ""),
                str(e.get("disclosure_tier") or "core_summary"),
                str(e.get("section") or "summary"),
            )
            for i, e in enumerate(raw_ent if isinstance(raw_ent, list) else (), start=1)
            if isinstance(e, Mapping) and str(e.get("value") or "").strip()
        )
        if parsed_entries:
            return CVProfileSpec(
                full_name=str(raw_cv.get("full_name") or f"{node_id} Portfolio").strip(),
                headline=str(raw_cv.get("headline") or "Sovereign Work & Ventures Profile").strip(),
                public_domain=cd,
                public_contact=str(raw_cv.get("public_contact") or "via node inbox").strip(),
                entries=parsed_entries,
            )
    if not m or node_id.startswith("pub-"):
        return CVProfileSpec.default_reference_spec(node_id, public_domain=cd)
    rm_title, rm_sum = _extract_readme_title_and_summary(workspace_dir)
    desc = str(
        m.get("description") or rm_sum or "Sovereign career, ventures, and B2B work node."
    ).strip()
    raw_ch = m.get("public_channels")
    ch_email = str(raw_ch.get("contact_email") or "").strip() if isinstance(raw_ch, Mapping) else ""
    raw_tpls = m.get("default_stack_templates")
    tpls = (
        ", ".join(str(t) for t in raw_tpls)
        if isinstance(raw_tpls, list) and raw_tpls
        else "universal-base"
    )
    links_n = len(m["linked_nodes"]) if isinstance(m.get("linked_nodes"), list) else 0
    settle = str(m.get("settlement_mode") or "none").strip()
    t0, t1, t2, t3 = VALID_DISCLOSURE_TIERS
    return CVProfileSpec(
        full_name=rm_title or f"{node_id} — Career & Ventures Portfolio",
        headline=desc,
        public_domain=cd,
        public_contact=ch_email or "via node inbox",
        entries=(
            CVFieldEntry("exec_summary", "Work Scope", desc, t0, "summary"),
            CVFieldEntry("core_stack", "Active Stack Packs", tpls, t0, "competencies"),
            CVFieldEntry(
                "verified_links",
                "Active Collaborations",
                f"{links_n} governed peer/network link(s) configured.",
                t1,
                "experience",
            ),
            CVFieldEntry(
                "engagement_mode",
                "Engagement & Settlement Mode",
                f"Settlement mode: {settle}",
                t2,
                "engagement",
            ),
            CVFieldEntry(
                "attestation_seal",
                "Node Surface Attestation",
                f"https://{cd}/.well-known/zcg-attestation.json",
                t3,
                "mesh",
            ),
        ),
    )


def resolve_personal_hub_context(
    workspace_dir: Path | None,
    manifest: Mapping[str, Any] | None,
    *,
    node_id: str,
    canonical_domain: str,
    base_facets: Sequence[dict[str, str]] = (),
) -> dict[str, Any]:
    """Build Personal Sovereign Hub title, summary, and delegated active pillar subdomain cards."""
    m = dict(manifest) if isinstance(manifest, Mapping) else {}
    rm_title, rm_sum = _extract_readme_title_and_summary(workspace_dir)
    default_summary = (
        "Personal Root 0 domain hub coordinating purpose-scoped child pillars across subdomains."
    )
    facets = list(base_facets)
    seen = {str(f.get("pillar") or "") for f in facets}
    if workspace_dir is not None:
        ws = workspace_dir.resolve()
        prefix = node_id.removesuffix("-profile")
        is_local = not canonical_domain or canonical_domain.endswith((".localhost", ".local"))
        for p_slug, p_lbl, p_sum, p_purp in _DELEGABLE_PILLARS:
            if p_slug in seen:
                continue
            cid = f"{prefix}-{p_slug}"
            cands = (ws.parent / cid, ws.parent / "Projects" / cid, ws / "layers" / cid)
            c_dir = next((d for d in cands if (d / "system/zcg-node.json").is_file()), None)
            if c_dir is None:
                continue
            cm = load_node_manifest(c_dir)
            if not is_public_portal_enabled(cm):
                continue
            cport = int(
                cm.get("cockpit_port") or (DEFAULT_PLUGIN_BASE_PORT + int(cm.get("precedence", 85)))
            )
            sub_path = "/portal/stewardship" if p_slug == "wallet" else "/portal?format=html"
            pub_u = (
                f"http://pro.{cid}.{node_id}.localhost:{cport}{sub_path}"
                if is_local
                else f"https://{p_slug}.{canonical_domain}{sub_path}"
            )
            seen.add(p_slug)
            facets.append(
                {
                    "pillar": p_slug,
                    "label": f"{p_lbl} ({cid})",
                    "summary": str(cm.get("description") or p_sum),
                    "purpose": p_purp,
                    "public_url": pub_u,
                }
            )
    return {
        "hub_title": rm_title or f"{node_id} — Personal Sovereign Hub",
        "hub_summary": str(m.get("description") or rm_sum or default_summary),
        "public_facets": facets,
    }


def project_cv_by_disclosure_tier(
    spec: CVProfileSpec, *, effective_tier: str = "core_summary"
) -> dict[str, Any]:
    """Filter CV entries monotonically up to effective_tier and seal SHA-256 digest."""
    clean_t = effective_tier.strip()
    tiers = VALID_DISCLOSURE_TIERS
    if clean_t not in tiers:
        raise ValueError(f"Invalid effective_tier {effective_tier!r}")
    max_idx = tiers.index(clean_t)
    disclosed = [asdict(e) for e in spec.entries if tiers.index(e.disclosure_tier) <= max_idx]
    canonical = json.dumps(disclosed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "full_name": spec.full_name,
        "headline": spec.headline,
        "public_domain": spec.public_domain,
        "public_contact": spec.public_contact,
        "effective_tier": clean_t,
        "disclosed_entries": disclosed,
        "withheld_count": len(spec.entries) - len(disclosed),
        "payload_digest": hashlib.sha256(canonical).hexdigest(),
    }


def render_cv_markdown(projected: Mapping[str, Any]) -> str:
    """Render a projected CV dictionary as clean downloadable Markdown."""
    lines = [
        f"# {projected['full_name']}",
        "",
        f"**{projected['headline']}**",
        f"- **Domain**: `{projected['public_domain']}` · "
        f"**Contact**: `{projected['public_contact']}`",
        f"- **Disclosure Ceiling**: `{projected['effective_tier']}` "
        f"(Withheld higher-ring entries: `{projected['withheld_count']}`)",
        f"- **SHA-256 Digest**: `{projected['payload_digest']}`",
        "",
        "## Verified Profile Entries",
    ]
    for item in projected.get("disclosed_entries", ()):
        lines.append(
            f"- **{item['label']}** (`{item['section']}` · `{item['disclosure_tier']}`): "
            f"{item['value']}"
        )
    return "\n".join(lines) + "\n"


@lru_cache(maxsize=1)
def portal_template_catalog() -> TemplateCatalog:
    """Return cached TemplateCatalog rooted at zcg.plugins/templates."""
    tpl_dir = Path(str(files("zcg.plugins").joinpath("templates")))
    return TemplateCatalog((tpl_dir,))


def render_cv_print_a4_html(projected: Mapping[str, Any], *, prefix: str = "/portal") -> SafeHTML:
    """Render an A4 @media print HTML curriculum vitae ready for browser Save-as-PDF."""
    return portal_template_catalog().render(
        "cv_print_a4.html",
        {
            "clean_prefix": prefix.rstrip("/"),
            "full_name": str(projected["full_name"]),
            "headline": str(projected["headline"]),
            "public_domain": str(projected["public_domain"]),
            "public_contact": str(projected["public_contact"]),
            "effective_tier": str(projected["effective_tier"]),
            "withheld_count": int(projected["withheld_count"]),
            "disclosed_entries": list(projected.get("disclosed_entries", ())),
            "payload_digest": str(projected["payload_digest"]),
        },
    )
