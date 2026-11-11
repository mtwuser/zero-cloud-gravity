"""Nominal constants, regular expressions, and lifecycle maps for rcap1 capsules and MCP.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import re

CAPSULE_PREFIX: str = "rcap1"
CHARS_PER_TOKEN_ESTIMATE: int = 4
SHA256_BLOCK_BYTES: int = 32
ZLIB_MAX_COMPRESSION_LEVEL: int = 9
CODON_SLUG_MAX_CHARS: int = 24
CODON_MAX_SEMANTIC_TAGS: int = 5
EXON_HEADING_MAX_CHARS: int = 180
EXON_BULLET_MAX_CHARS: int = 160
EXON_MAX_BULLETS: int = 8
L1_FALLBACK_EST_TOKENS: int = 120
L2_EXCERPT_MAX_CHARS: int = 1500
L2_SECTION_MAX_CHARS: int = 8000
L3_EXCERPT_MAX_CHARS: int = 4000
MAX_UNFOLDED_L3_LINKS: int = 5
MAX_QUERY_GOVERNANCE_MATCHES: int = 10
MAX_SURFACE_SECTIONS_PER_RULE: int = 3
MAX_RECOMMENDED_MCP_FANOUT: int = 5
CAPSULE_ALERT_PREFIX_CHARS: int = 32
CAPSULE_BRIEF_PREVIEW_CHARS: int = 48
MAX_BRIEF_INVARIANTS: int = 6
FORK_ID_HASH_HEX_LEN: int = 8
EPOCH_DECIMAL_PLACES: int = 3
MIN_EPHEMERAL_TTL_SECONDS: int = 10
DEFAULT_EPHEMERAL_TTL_SECONDS: int = 300
MAX_EPHEMERAL_TTL_SECONDS: int = 3600
MAX_ACTIVE_EPHEMERAL_FORKS: int = 16
MAX_LOG_FILE_BYTES: int = 1_048_576
MCP_PAYLOAD_WARN_BYTES: int = 32_000
DIAGNOSTICS_RECENT_ALERTS_LIMIT: int = 5
DIAGNOSTICS_RECENT_EVENTS_LIMIT: int = 5
MS_PER_SECOND: float = 1000.0
HOT_CITATION_THRESHOLD: int = 5
STALE_POLICY_REVIEW_DAYS: int = 90
MIN_ROUTING_KEYWORD_LEN: int = 4
GLOB_WILDCARD_SUFFIX_LEN: int = 2
SPECIFICITY_WEIGHT_GLOB: int = 40
SPECIFICITY_WEIGHT_PLANE: int = 20
SPECIFICITY_WEIGHT_SCOPE: int = 20
SPECIFICITY_WEIGHT_TRAIT: int = 10

JSONRPC_PARSE_ERROR: int = -32700
JSONRPC_METHOD_NOT_FOUND: int = -32601
JSONRPC_INVALID_PARAMS: int = -32602
JSONRPC_INTERNAL_ERROR: int = -32603

GRCC_CAPSULE_BLOB_PATH: str = ".agents/capsule.rcap1"
CITATION_TELEMETRY_REL_PATH: str = ".agents/telemetry/citation_stats.json"
DEFAULT_SPECIALTY_BRANCH_PREFIX: str = "specialty/"

VALID_RESOLUTIONS: tuple[str, ...] = ("L0", "L1", "L2")
VALID_CAPSULE_LEVELS: tuple[str, ...] = ("L0", "L1", "L2", "L3")
NEXT_LEVEL_MAP: dict[str, str] = {"L0": "L1", "L1": "L2", "L2": "L3", "L3": "L3"}
LEVEL_INDEX: dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
LEVEL_MIN_TIER: dict[str, str] = {
    "L0": "flash_lite",
    "L1": "flash",
    "L2": "flash",
    "L3": "inherit",
}
AGENT_TIER_RANK: dict[str, int] = {"flash_lite": 0, "flash": 1, "inherit": 2, "pro": 3}
CAPSULE_ABSTRACTION_LAYERS: dict[str, str] = {
    "L0": "promoter-codon-index",
    "L1": "axiom-exon-skeleton",
    "L2": "contextual-section-body",
    "L3": "primary-substrate-verification",
}
CITATION_LIFECYCLE_QUADRANTS: dict[str, str] = {
    "Q1_HOT_CORE": "retain-and-pin-in-l1-cache",
    "Q2_HIGH_FRICTION": "clarify-or-split-ambiguous-rule",
    "Q3_EMERGING_NICHE": "monitor-usage-growth",
    "Q4_NORMATIVE_OBSOLESCENCE": "review-for-archival-never-silent-drop",
}
VALID_ARCHITECTURAL_PLANES: tuple[str, ...] = (
    "schema",
    "domain",
    "application",
    "presentation",
    "infrastructure",
    "testing",
    "governance",
)
VALID_BINDING_MODES: tuple[str, ...] = ("authoritative", "transversal")
VALID_EPHEMERAL_ACCESS_MODES: tuple[str, ...] = ("strictly-read-only", "read-write-scoped")
VALID_EPHEMERAL_SCOPES: tuple[str, ...] = ("intra-layer", "inter-layer")
VALID_EPHEMERAL_ACTIONS: tuple[str, ...] = (
    "spawn",
    "inspect",
    "evaluate",
    "reap",
    "catalog",
    "seal-return",
    "verify-return",
    "project-branch",
    "chain-capsule-ref",
)
VALID_GRCC_OPERATIONS: tuple[str, ...] = ("probe", "seal", "unfold", "prune")
DIGEST_REQUIRED_CHANNELS: tuple[str, ...] = (
    "channel_1_domain_state",
    "channel_2_affected_surface",
    "channel_3_invariants_and_constraints",
    "channel_4_actionable_delta",
)
ALLOWED_ROOT_FILES: frozenset[str] = frozenset(
    {
        "README.md",
        "VERSION",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "ACCESSIBILITY.md",
        "SYLLABUS.md",
        "WORKROAD.md",
        "WORKTASK.md",
        "WORKVALI.md",
        "BACKLOG.md",
        "ROADMAP.md",
    }
)
ALLOWED_READ_PREFIXES: tuple[str, ...] = (
    "docs/",
    "templates/",
    "antigravity/",
    "system/",
    "corporate/",
    "surfaces/",
    "roadmaps/",
    ".agents/rules/",
    ".agents/skills/",
)
CODON_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "must",
        "never",
        "all",
        "are",
        "use",
        "only",
        "into",
        "when",
        "every",
        "across",
        "via",
    }
)
PLANE_PATH_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("testing", ("tests/", "test_", "_test.")),
    ("schema", ("schema", "models", "migrations", "alembic")),
    ("presentation", ("surfaces/", "web/", ".html", ".css")),
    ("infrastructure", ("infra/", "docker", "system/", "cockpit/", "mcp/")),
    ("governance", ("corporate/", "worktask", "workroad", "workvali", ".agents/")),
    ("application", ("cli/", "commands", "services", "use_cases")),
    ("domain", ("core/", "topology/", "domain/", "entities")),
)
STRUCTURAL_PATH_SEGMENTS: frozenset[str] = frozenset(
    {"src", "tests", "unit", "imp", "e2e", "docs", "templates", "layers", "surfaces", "zcg"}
)
MD_LINK_RE: re.Pattern[str] = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BACKTICK_PATH_RE: re.Pattern[str] = re.compile(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`")
CITATION_RECEIPT_REF_RE: re.Pattern[str] = re.compile(
    r"\b([a-z0-9-]+)::([A-Za-z0-9_./-]+)#[a-z0-9-]+@[0-9a-f]{8,64}:E[0-3]\b"
)
BOLD_TERM_RE: re.Pattern[str] = re.compile(r"\*\*([^*]{3,48})\*\*")
WORD_TOKEN_RE: re.Pattern[str] = re.compile(r"[a-z0-9]{3,}")
ANSI_ESCAPE_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*m")
