"""Declarative JSON-RPC 2.0 catalogs, capability rings, and bot archetypes for zcg-mcp.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

from typing import Any

from zcg.capsules.constants import (
    DEFAULT_EPHEMERAL_TTL_SECONDS,
    VALID_ARCHITECTURAL_PLANES,
    VALID_CAPSULE_LEVELS,
    VALID_EPHEMERAL_ACCESS_MODES,
    VALID_EPHEMERAL_ACTIONS,
    VALID_EPHEMERAL_SCOPES,
    VALID_GRCC_OPERATIONS,
    VALID_RESOLUTIONS,
)
from zcg.core.constants import (
    ROLE_DEFAULT_PRECEDENCE,
    VALID_AGENT_TIERS,
    VALID_EPISTEMIC_GRADES,
    VALID_ROSTER_ROLES,
)

MCP_RESOURCES_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "uri": "zcg://node/identity",
        "name": "Zero-Cloud Node Identity",
        "description": "SemVer, layer_id, layer_role, OS release, and upstream lineage.",
        "mimeType": "application/json",
    },
    {
        "uri": "zcg://system/manifests",
        "name": "Workstation System Manifests",
        "description": "Tracked APT, Snap, NPM, NVM, and GNOME workstation inventories.",
        "mimeType": "application/json",
    },
    {
        "uri": "zcg://governance/rules",
        "name": "Global Engineering Rules (AGENTS.md)",
        "description": "Universal mandates, strict typing, AAA testing, and commit governance.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "zcg://governance/hooks",
        "name": "Antigravity Lifecycle Hooks (hooks.json)",
        "description": "Deterministic PreToolUse, PostToolUse, PostInvocation, and Stop hooks.",
        "mimeType": "application/json",
    },
    {
        "uri": "zcg://governance/skills",
        "name": "Global Skills Catalog",
        "description": "Structured inventory of global Antigravity slash-command skills.",
        "mimeType": "application/json",
    },
    {
        "uri": "zcg://governance/templates",
        "name": "Declarative Stack & Plugin Templates",
        "description": "Catalog of human-stack, context-stack, framework-stack, and plugin-stack.",
        "mimeType": "application/json",
    },
    {
        "uri": "zcg://docs/index",
        "name": "Epistemic Knowledge & Spec Index (docs/README.md)",
        "description": "Navigable index of guides, 1:1:1 architecture specs, and reference docs.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "zcg://mcp/topology",
        "name": "Federated MCP Topology (system/zcg-node.json)",
        "description": "Node manifest, mounted layers, and OOP capability rings.",
        "mimeType": "application/json",
    },
    {
        "uri": "zcg://mcp/diagnostics",
        "name": "Runtime MCP Telemetry (logs/mcp_*.jsonl)",
        "description": "Live summary of MCP calls, compaction savings, and alerts.",
        "mimeType": "application/json",
    },
)

MCP_PROMPTS_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "name": "orient-on-node",
        "description": "Orient an AI agent on this Zero-Cloud Node via a 4-Channel Digest.",
        "arguments": [
            {"name": "task_description", "description": "Task summary.", "required": False}
        ],
    },
    {
        "name": "audit-container-or-node",
        "description": "Audit repository verification and workstation drift on this node.",
        "arguments": [{"name": "target_service", "description": "Target node.", "required": False}],
    },
    {
        "name": "orchestrate-federated-mcps",
        "description": "Discover federated MCPs and enforce inherited guardrails.",
        "arguments": [
            {"name": "workflow_goal", "description": "Operation goal.", "required": True},
            {"name": "environment", "description": "Target env (dev..pro).", "required": False},
            {"name": "layer", "description": "Target layer.", "required": False},
        ],
    },
)

_WS: dict[str, str] = {"type": "string", "description": "Optional target workspace directory."}
_BR: dict[str, str] = {"type": "string", "description": "Optional Git ref for zero-checkout DMCP."}
_ENV: dict[str, Any] = {"type": "string", "enum": ["dev", "tst", "pre", "pro"]}
_LYR: dict[str, str] = {"type": "string", "default": "all"}
_CAP: dict[str, Any] = {"type": "boolean", "default": True}
_RKEY: dict[str, str] = {"type": "string", "description": "Optional rcap1 resonance key."}
_STR_ARR: dict[str, Any] = {"type": "array", "items": {"type": "string"}}

MCP_TOOLS_CATALOG: tuple[dict[str, Any], ...] = (
    {"name": "get_layer_overview", "description": "Return a 4-Channel Executive Digest.",
     "inputSchema": {"type": "object", "additionalProperties": False,
         "properties": {"workspace_dir": _WS, "layer": {"type": "string"}}}},
    {"name": "audit_node_drift", "description": "Run read-only verification and drift audit.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "workspace_dir": _WS,
         "mode": {"type": "string", "enum": ["verify-repo", "system-audit", "both"],
                  "default": "verify-repo"}}}},
    {"name": "read_layer_document", "description": "Read a path-contained Markdown or JSON file.",
     "inputSchema": {"type": "object", "required": ["relative_path"], "additionalProperties": False,
         "properties": {"workspace_dir": _WS, "relative_path": {"type": "string"},
                        "layer": {"type": "string"}, "branch_ref": _BR}}},
    {"name": "query_governance_rules", "description": "Search rules/docs with rcap1 compaction.",
     "inputSchema": {"type": "object", "required": ["query"], "additionalProperties": False,
         "properties": {
             "workspace_dir": _WS, "query": {"type": "string"},
             "scope": {"type": "string", "enum": ["all", "global", "templates", "docs"],
                       "default": "all"},
             "layer": _LYR, "resolution": {"type": "string", "enum": list(VALID_RESOLUTIONS),
                                           "default": "L2"},
             "environment": _ENV, "resonance_key": _RKEY, "target_path": {"type": "string"},
             "branch_ref": _BR,
             "min_epistemic_grade": {"type": "string", "enum": list(VALID_EPISTEMIC_GRADES)},
             "include_capsules": _CAP}}},
    {"name": "unfold_context_capsule", "description": "Decrypt and unfold rcap1 L0->L1->L2->L3.",
     "inputSchema": {"type": "object", "required": ["capsule_token"], "additionalProperties": False,
         "properties": {
             "workspace_dir": _WS, "capsule_token": {"type": "string"},
             "target_level": {"type": "string", "enum": list(VALID_CAPSULE_LEVELS)},
             "agent_tier": {"type": "string", "enum": list(VALID_AGENT_TIERS),
                            "default": "inherit"},
             "environment": _ENV, "resonance_key": _RKEY}}},
    {"name": "discover_federated_mcps", "description": "Discover downstream or sibling MCPs.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "workspace_dir": _WS, "filter_role": {"type": "string"},
         "environment": _ENV, "layer": _LYR}}},
    {"name": "compare_layer_patterns", "description": "Compare project rules/skills across layers.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "workspace_dir": _WS, "project_rules": _STR_ARR,
         "project_skills": _STR_ARR, "layer": _LYR}}},
    {"name": "resolve_surface_governance", "description": "Project governance rules for a surface.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "workspace_dir": _WS, "target_path": {"type": "string"},
         "architectural_plane": {"type": "string", "enum": list(VALID_ARCHITECTURAL_PLANES)},
         "scope": {"type": "string"}, "traits": _STR_ARR, "environment": _ENV,
         "resolution_override": {"type": "string", "enum": list(VALID_RESOLUTIONS)},
         "resonance_key": _RKEY, "include_capsules": _CAP}}},
    {"name": "orchestrate_ephemeral_fork", "description": "Orchestrate TTL Department Bots.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "workspace_dir": _WS,
         "action": {"type": "string", "enum": list(VALID_EPHEMERAL_ACTIONS), "default": "evaluate"},
         "fork_id": {"type": "string"},
         "bot_role": {"type": "string", "default": "dept-specialist-bot"},
         "target_path": {"type": "string"}, "target_globs": _STR_ARR,
         "architectural_planes": _STR_ARR, "mount_templates": _STR_ARR, "mount_layers": _STR_ARR,
         "mount_project_rules_from": {"type": "string"},
         "model_tier": {"type": "string", "enum": list(VALID_AGENT_TIERS), "default": "flash"},
         "access_mode": {"type": "string", "enum": list(VALID_EPHEMERAL_ACCESS_MODES),
                         "default": "strictly-read-only"},
         "ephemeral_scope": {"type": "string", "enum": list(VALID_EPHEMERAL_SCOPES)},
         "actor_role": {"type": "string", "enum": list(VALID_ROSTER_ROLES), "default": "member"},
         "resolution": {"type": "string", "enum": list(VALID_RESOLUTIONS), "default": "L2"},
         "ttl_seconds": {"type": "integer", "default": DEFAULT_EPHEMERAL_TTL_SECONDS},
         "one_shot": {"type": "boolean", "default": True},
         "branch_ref": _BR, "task_step_id": {"type": "string"},
         "context_frame_token": {"type": "string"},
         "grcc_op": {"type": "string", "enum": list(VALID_GRCC_OPERATIONS)},
         "capsule_token": {"type": "string"}, "digest": {"type": "object"},
         "environment": {"type": "string"}, "family": {"type": "string"},
         "resonance_key": _RKEY, "remote": {"type": "string"}}}},
)  # fmt: skip

MCP_PERMISSION_RINGS: tuple[dict[str, Any], ...] = (
    {"ring_id": "R0_DISCOVERY", "crud_permissions": ["read"], "persistence_mode": "permanent",
     "tools": ["get_layer_overview", "read_layer_document", "discover_federated_mcps",
               "audit_node_drift"],
     "description": "Zero-mutation node identity, topology, and drift telemetry."},
    {"ring_id": "R1_COMPACTION", "crud_permissions": ["read", "filter"],
     "persistence_mode": "permanent",
     "tools": ["query_governance_rules", "resolve_surface_governance"],
     "description": "3D surface responsibility filtering and rcap1 L0/L1/L2 compaction."},
    {"ring_id": "R2_CRYPTO_UNFOLD", "crud_permissions": ["read", "decrypt"],
     "persistence_mode": "hybrid-symbiotic", "tools": ["unfold_context_capsule"],
     "description": "HMAC key, agent-tier, and surface-gated L1->L3 capsule decapsulation."},
    {"ring_id": "W_EPHEMERAL_SANDBOX", "crud_permissions": ["create", "read", "update", "delete"],
     "persistence_mode": "ephemeral", "tools": ["orchestrate_ephemeral_fork"],
     "description": "Scoped CoW ephemeral sandbox CRUD (spawn, evaluate, seal-return, reap)."},
    {"ring_id": "W_GOVERNANCE_PROPOSAL", "crud_permissions": ["create", "read", "update"],
     "persistence_mode": "permanent", "tools": ["compare_layer_patterns"],
     "description": "Inter-layer pattern comparison and upward/downward proposal routing."},
)  # fmt: skip

_R_RO = ["R0_DISCOVERY", "R1_COMPACTION", "R2_CRYPTO_UNFOLD"]
BOT_ARCHETYPE_CATALOG: tuple[dict[str, Any], ...] = (
    {"bot_role": "security-auditor-bot", "family": "audit-and-compliance",
     "recommended_tier": "inherit", "default_access_mode": "strictly-read-only",
     "default_encapsulation": "L2", "granted_rings": _R_RO,
     "description": "Audits security boundaries, RBAC authority, and path containment."},
    {"bot_role": "doc-coherence-bot", "family": "audit-and-compliance",
     "recommended_tier": "flash", "default_access_mode": "strictly-read-only",
     "default_encapsulation": "L1", "granted_rings": ["R0_DISCOVERY", "R1_COMPACTION"],
     "description": "Sweeps markdown links, taxonomy parity, and 3-tier doc coherence."},
    {"bot_role": "architecture-reviewer-bot", "family": "architecture-and-code",
     "recommended_tier": "pro", "default_access_mode": "strictly-read-only",
     "default_encapsulation": "L2", "granted_rings": _R_RO,
     "description": "Evaluates relational cluster mass, DAG layering, and 1:1:1 symbiosis."},
    {"bot_role": "refactoring-surgeon-bot", "family": "architecture-and-code",
     "recommended_tier": "inherit", "default_access_mode": "read-write-scoped",
     "default_encapsulation": "L2", "granted_rings": [*_R_RO, "W_EPHEMERAL_SANDBOX"],
     "description": "Executes scoped module extractions and 1:1 unit test alignment."},
    {"bot_role": "ops-ledger-bot", "family": "data-and-operations",
     "recommended_tier": "flash", "default_access_mode": "strictly-read-only",
     "default_encapsulation": "L1", "granted_rings": ["R0_DISCOVERY", "R1_COMPACTION"],
     "description": "Validates corporate-operations citations and Node Work Ledger contracts."},
    {"bot_role": "normative-analyst-bot", "family": "scientific-and-normative",
     "recommended_tier": "pro", "default_access_mode": "strictly-read-only",
     "default_encapsulation": "L2", "granted_rings": _R_RO,
     "description": "Synthesizes territorial, statutory, and scientific knowledge corpora."},
    {"bot_role": "secops-mcp-orchestrator-bot", "family": "audit-and-compliance",
     "recommended_tier": "inherit", "default_access_mode": "strictly-read-only",
     "default_encapsulation": "L2", "granted_rings": [*_R_RO, "W_GOVERNANCE_PROPOSAL"],
     "description": "Pure-bot security department orchestrator auditing fixed & ephemeral MCPs."},
)  # fmt: skip


def resolve_bot_archetype(bot_role: str) -> dict[str, Any]:
    """Resolve a canonical bot archetype from catalog or synthesize a custom role profile."""
    clean = bot_role.strip().lower() or "dept-specialist-bot"
    for entry in BOT_ARCHETYPE_CATALOG:
        if entry["bot_role"] == clean:
            has_w = any(str(r).startswith("W_") for r in entry["granted_rings"])
            aut = "actionable-gated" if has_w else "autonomous-scope-bounded"
            return {**entry, "execution_autonomy": aut, "catalog_registered": True}
    return {
        "bot_role": clean,
        "family": "custom-departmental",
        "recommended_tier": "flash",
        "default_access_mode": "strictly-read-only",
        "default_encapsulation": "L2",
        "granted_rings": list(_R_RO),
        "execution_autonomy": "autonomous-scope-bounded",
        "description": f"Custom departmental specialist bot ({clean}).",
        "catalog_registered": False,
    }


def resolve_mcp_capability_profile(
    manifest: dict[str, Any],
    *,
    environment: str = "all",
    active_ephemeral_forks: list[dict[str, Any]] | None = None,
    family_filter: str | None = None,
) -> dict[str, Any]:
    """Compute OOP capability rings, bot catalog, and Permanent <-> Ephemeral symbiosis state."""
    layer_id = str(manifest.get("layer_id", "root"))
    layer_role = str(manifest.get("layer_role", "workstation"))
    prec = int(manifest.get("precedence", ROLE_DEFAULT_PRECEDENCE.get(layer_role, 10)))
    env_clean = environment.strip().lower() or "all"
    env_cfg = manifest.get("environments", {}).get(env_clean, {})
    is_ro = env_clean == "pro" or env_cfg.get("access_mode") == "strictly-read-only"
    granted_ids = list(_R_RO) if is_ro else [r["ring_id"] for r in MCP_PERMISSION_RINGS]
    granted_rings = [dict(r) for r in MCP_PERMISSION_RINGS if r["ring_id"] in granted_ids]
    hot_leases = [
        {
            "fork_id": str(fk.get("fork_id", "")),
            "bot_role": (arch := resolve_bot_archetype(str(fk.get("bot_role", ""))))["bot_role"],
            "family": arch["family"],
            "granted_rings": arch["granted_rings"],
            "execution_autonomy": arch["execution_autonomy"],
            "remaining_ttl_seconds": float(fk.get("remaining_ttl_seconds", 0.0)),
        }
        for fk in (active_ephemeral_forks or [])
    ]
    fam_clean = (family_filter or "").strip().lower()
    catalog = [dict(b) for b in BOT_ARCHETYPE_CATALOG if not fam_clean or b["family"] == fam_clean]
    aut_l = [h["fork_id"] for h in hot_leases if h["execution_autonomy"].startswith("auton")]
    act_l = [h["fork_id"] for h in hot_leases if h["execution_autonomy"].startswith("action")]
    return {
        "layer_id": layer_id,
        "layer_role": layer_role,
        "precedence": prec,
        "environment": env_clean,
        "oop_capability_inheritance": {
            "kernel_base": "MCPNodeBase",
            "granted_ring_ids": granted_ids,
            "permission_rings": granted_rings,
        },
        "permanent_ephemeral_symbiosis": {
            "symbiotic_state": "ephemeral-augmented" if hot_leases else "basal-permanent-only",
            "zero_standing_privileges": True,
            "permanent_to_ephemeral_grants": [
                "lineage_0_to_80_inheritance",
                "surface_filtered_rcap1_capsules",
                "centralized_audit_telemetry",
            ],
            "ephemeral_to_permanent_hotplug": {
                "active_leases_count": len(hot_leases),
                "hot_plugged_leases": hot_leases,
                "ephemeral_crypto_keys_mounted": len(hot_leases),
            },
            "mcp_autonomy_matrix": {
                "autonomous_scope_bounded_rings": list(_R_RO),
                "actionable_gated_rings": ["W_EPHEMERAL_SANDBOX", "W_GOVERNANCE_PROPOSAL"],
                "active_autonomous_leases": aut_l,
                "active_actionable_leases": act_l,
            },
        },
        "bot_families": sorted({b["family"] for b in BOT_ARCHETYPE_CATALOG}),
        "bot_archetype_catalog": catalog,
    }
