---
trigger: always_on
description: "Pure-Bot Transversal Security Department rules: Fixed vs. Ephemeral MCP orchestration and Autonomous (R0..R2) vs. Actionable (W) capability bounding (secops-mcp-guardian)."
---

# Pure-Bot Security Department & MCP Orchestration Rules (`secops-mcp-guardian`)

> Extends `science-base.md`, `business-base.md`, `software-engineering.md`, and `nist-csf-security.md` with the **`plugin-stack` Pure-Bot Security Department** contract: a transversal bot department (`dept-security`, `precedence: 7`) that orchestrates the Fixed MCPs of all other departments and spawns scoped Ephemeral MCPs.

---

## 1. Fixed vs. Ephemeral & Autonomous vs. Actionable MCP Dichotomy

Every MCP interaction governed by `secops-mcp-guardian` is classified across two orthogonal axes:

1. **Fixed MCP vs. Ephemeral MCP (`persistence_mode`)**:
   - **Fixed Departmental MCPs (`permanent`)**: Persistent per-layer nodes holding static `system/zcg-node.json` topology, local departmental views, and `.agents/telemetry/citation_stats.json` (`Q1..Q4` radar).
   - **Ephemeral Security MCPs (`ephemeral` / `hybrid-symbiotic`)**: Short-lived leases (`orchestrate_ephemeral_fork`, `DMCP` zero-checkout `git show` projection, `GRCC` `refs/capsules/*`) spawned on boundary changes and reaped with crypto-shredded `rcap1` 4-Channel Digests.
2. **Autonomous MCP (Scope-Bounded) vs. Actionable MCP (Rule/Human-Gated)**:
   - **Autonomous MCP (`R0_DISCOVERY`, `R1_COMPACTION`, `R2_CRYPTO_UNFOLD`)**: Strictly scope-bounded (`strictly-read-only`) continuous auditing of departmental reach, `citation_receipt` digests, and `NIST-01..04` invariants without human intervention.
   - **Actionable MCP (`W_EPHEMERAL_SANDBOX`, `W_GOVERNANCE_PROPOSAL`)**: Controlled operations that stage cross-departmental PR proposals (`.agents/proposals/`), inject `[GOVERNANCE DECISION]` gates into `WORKTASK.md`, or trigger `runtime_service` healthcheck rollbacks.

---

## 2. Single-Framework (`1-Framework`) & Multi-Framework Orchestration

1. **Independent Niche Auditing (`Single-Node`)**: Validate each departmental node in its dedicated role—`corporate-root-hub` for Holding `Root 0`, `node-work-cockpit` for departmental/squad ledgers, `tutor-study-cockpit` for academic labs, and `google-cloud-iac` for Cloud Run / BigQuery workloads.
2. **Cross-Departmental Composition (`Multi-Node`)**: When a workflow spans multiple nodes (`corporate-root-hub` $\leftrightarrow$ `node-work-cockpit` $\leftrightarrow$ `google-cloud-iac`), `secops-mcp-guardian` verifies that each node's surface reach remains strictly bounded to its authorized globs and `R0..R2` capability rings.
