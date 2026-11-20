"""Opt-in isolated tool-stack and external MCP connector catalog specifications.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class IsolatedToolDescriptor:
    """Declarative metadata for a third-party runtime isolated under .zcg/tools/<tool_id>/."""

    tool_id: str
    display_name: str
    upstream_engine: str
    sandbox_driver: str
    requires_network: bool
    optional_extra: bool
    summary: str
    cli_command: str = "zcg status ."

    def to_dict(self) -> dict[str, Any]:
        """Serialize descriptor to a JSON-compatible dictionary."""
        return asdict(self)


_CATALOG_ROWS: Final[tuple[IsolatedToolDescriptor, ...]] = (
    IsolatedToolDescriptor(
        "zcg-skill-auditor",
        "Sovereign 3-Tier Skill Auditor",
        "zcg-skill-auditor+osv-scanner",
        "bwrap-readonly",
        False,
        False,
        "3-tier SARIF 2.1.0 security, 1-Verb Jaccard deduplication, and A/B Skill Lift auditor.",
        "zcg lint-skills .",
    ),
    IsolatedToolDescriptor(
        "secops-guardian",
        "SecOps OSV & Bubblewrap Guardian",
        "osv-scanner+bubblewrap",
        "bwrap-readonly",
        True,
        False,
        "NIST CSF 2.0 compliance, OSV-Scanner CVE auditing, and bubblewrap confinement.",
        "zcg status .",
    ),
    IsolatedToolDescriptor(
        "container-edge-ops",
        "Self-Hosted OCI Runtime & TLS 1.3 Edge CLI",
        "podman+caddy-or-nginx",
        "bwrap-readonly",
        False,
        False,
        "Rootless OCI container runtime and TLS 1.3 reverse-proxy operations.",
        "zcg apply-project . --template self-hosted-container",
    ),
    IsolatedToolDescriptor(
        "google-cloud-ops",
        "Google Cloud Keyless Operations",
        "google-cloud-sdk",
        "keyless-adc",
        True,
        False,
        "Keyless Workload Identity Federation and ambient ADC operations for GCP IaC.",
        "zcg apply-project . --template google-cloud-iac",
    ),
    IsolatedToolDescriptor(
        "gemini-decisions",
        "Calibrated Gemini Decisions & Offline LiteRT",
        "gemini-decision-1/litert-gemma-4-26b-a4b-it",
        "calibrated-zero-output",
        False,
        False,
        "Zero-output-token Yes/No, Choice, and Rubric gates via gemini-decision-1 or Gemma 4.",
        "POST /api/tools/decisions/evaluate",
    ),
    IsolatedToolDescriptor(
        "duckdb-analytics",
        "DuckDB Columnar Analytics",
        "duckdb/duckdb",
        "bwrap-readonly",
        False,
        True,
        "Optional isolated in-process OLAP engine for Parquet and columnar data slices.",
        "python3 -c 'import duckdb' (inside .zcg/tools/duckdb-analytics)",
    ),
    IsolatedToolDescriptor(
        "wallet-analytics",
        "Zero-Custody Treasury & Statement Analytics",
        "duckdb+ofx-watch",
        "bwrap-readonly",
        False,
        True,
        "Offline CSV/OFX/Parquet statement mapper and CAIP-10 watch analytics under .zcg/tools/.",
        "zcg status . (R3 wallet airlock)",
    ),
)
DEFAULT_ISOLATED_TOOL_CATALOG: Final[Mapping[str, IsolatedToolDescriptor]] = {
    row.tool_id: row for row in _CATALOG_ROWS
}


def resolve_tool_node_relevance(tool_id: str, manifest: Mapping[str, Any] | None = None) -> bool:
    """Return True when tool_id is directly recommended for the active node's role or stack."""
    m = manifest if isinstance(manifest, Mapping) else {}
    lid = str(m.get("layer_id") or "").strip().lower()
    lrole = str(m.get("layer_role") or "department").strip().lower()
    raw_tpls = m.get("default_stack_templates")
    tpls = {str(t).strip() for t in raw_tpls} if isinstance(raw_tpls, list) else set()
    is_wallet = lid.endswith("-wallet") or "sovereign-wallet-cockpit" in tpls
    if tool_id in ("zcg-skill-auditor", "gemini-decisions"):
        return True
    if tool_id == "secops-guardian":
        return lrole in ("workstation", "corporate", "domain-policy") or lid.endswith("-security")
    if tool_id == "wallet-analytics":
        return is_wallet
    if tool_id == "container-edge-ops":
        return "self-hosted-container" in tpls or "container_deployment" in m
    if tool_id == "google-cloud-ops":
        return "google-cloud-iac" in tpls or "cloud_deployment" in m
    if tool_id == "duckdb-analytics":
        return is_wallet or lrole == "knowledge" or lid.endswith("-tutor")
    return False


@dataclass(frozen=True, slots=True)
class OfficialMCPConnectorSpec:
    """Curated metadata for an opt-in upstream MCP server."""

    connector_id: str
    upstream_repo: str
    transport: str
    command: str
    default_args: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    summary: str


DEFAULT_EXTERNAL_MCP_CONNECTORS: Final[Mapping[str, OfficialMCPConnectorSpec]] = {
    "remote-streamable-http": OfficialMCPConnectorSpec(
        connector_id="remote-streamable-http",
        upstream_repo="modelcontextprotocol/specification",
        transport="streamable-http",
        command="",
        default_args=(),
        allowed_domains=(),
        summary="Vendor-neutral remote Streamable HTTP (/mcp) server protected by HTTPS + OIDC.",
    ),
    "github-official": OfficialMCPConnectorSpec(
        connector_id="github-official",
        upstream_repo="github/github-mcp-server",
        transport="stdio",
        command="github-mcp-server",
        default_args=("stdio", "--read-only"),
        allowed_domains=("api.github.com", "github.com"),
        summary="Official GitHub MCP server governed under read-only default and OIDC/PAT scopes.",
    ),
    "google-cloud-gcloud": OfficialMCPConnectorSpec(
        connector_id="google-cloud-gcloud",
        upstream_repo="google/mcp",
        transport="stdio",
        command="npx",
        default_args=("-y", "@google-cloud/gcloud-mcp"),
        allowed_domains=("googleapis.com",),
        summary="Official keyless Google Cloud gcloud MCP server using ambient ADC / WIF.",
    ),
    "google-cloud-run-remote": OfficialMCPConnectorSpec(
        connector_id="google-cloud-run-remote",
        upstream_repo="google/mcp",
        transport="streamable-http",
        command="",
        default_args=(),
        allowed_domains=("run.app", "googleapis.com"),
        summary="Remote Cloud Run Streamable HTTP (/mcp) server protected by IAM / OIDC.",
    ),
}
