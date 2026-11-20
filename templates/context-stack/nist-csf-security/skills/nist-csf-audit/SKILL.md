---
name: nist-csf-audit
description: "Author and verify NIST CSF 2.0 (GV, ID, PR, DE, RS, RC) control ledgers (corporate/ledgers/security-controls.md), security policies, and OWASP ASVS / MCP-Sec surfaces; automatically invoked by /review and /audit when nist-csf-security is active."
---
# Skill: NIST CSF 2.0 Control & Surface Playbook (`nist-csf-audit`)

> Governs `1:1:1` alignment between `corporate/ledgers/security-controls.md` (`[SEC-CTRL-YYYY-NNN]`), `corporate/policies/`, and outward `surfaces/` / `MCP-Sec` boundaries against NIST CSF 2.0 (`GV`, `ID`, `PR`, `DE`, `RS`, `RC`). Automatically executed by **`/review`** (`/review arch` / `/review 1:1:1`, `C1`) and **`/audit`** (`/audit arch` / `/audit 1:1:1`, `C2`) whenever `nist-csf-security` or `secops-mcp-guardian` is active in `.agents/rules/`, and used directly when authoring or updating `[SEC-CTRL-YYYY-NNN]` control records.

---

## 4-Step Verification & Authoring Workflow

Execute these 4 steps when authoring security controls or running a context-adaptive security audit:

1. **Control Coverage Check**: Verify every active policy in `corporate/policies/` maps to a valid NIST CSF 2.0 function (`GV`, `ID`, `PR`, `DE`, `RS`, `RC`) and cites `[SEC-CTRL-YYYY-NNN]`.
2. **Evidence Verification**: Confirm each `[SEC-CTRL-YYYY-NNN]` record specifies an automated check command or dated sign-off artifact.
3. **Zero-Trust Surface Sweep**: Scan `surfaces/**` and `.agents/proposals/**` to ensure zero internal IPs, secrets, or restricted threat-model details are exposed.
4. **Technological Application & MCP Capability Audit (`PR.AA`, `PR.DS`, `DE.CM`)**: Audit `src/**`, `scripts/**`, `Dockerfile`, and `system/zcg-node.json` (`ephemeral_fork_policy`) to verify OWASP ASVS boundary validation, non-root containers, MCP path containment (`PATH_CONTAINMENT_VIOLATION`), `citation_receipt` verification, and `strictly-read-only` subagent execution.
