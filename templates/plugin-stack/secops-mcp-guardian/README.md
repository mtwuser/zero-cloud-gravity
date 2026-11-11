# `secops-mcp-guardian` (`plugin-stack`) — Tier 2 Zero-Trust MCP & Ephemeral Sandbox Surface

> Tier 2 runtime security plugin extending `nist-csf-security` with HMAC-authenticated `DMCP` envelopes, `strictly-read-only` ephemeral forks, and `citation_receipt` drift auditing.

---

## 1. Template Identity & Service Contract (`template.json` & `service_contract.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json), [`assets/service_contract.json`](assets/service_contract.json), and [`rules/secops-mcp-guardian.md`](rules/secops-mcp-guardian.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `secops-mcp-guardian` | Runtime surface in `CANONICAL_STARTER_TEMPLATES` (`constants.py`) |
| **`stack_group`** | `plugin-stack` | Editable Reference Dashboard & Cockpit Capability Axis |
| **`extends`** | `"nist-csf-security"` | Transitively resolves `universal-base -> science-base -> software-engineering -> nist-csf-security -> secops-mcp-guardian` |
| **`service_contract`** | [`assets/service_contract.json`](assets/service_contract.json) | Declares `enabled_modules`, `web_templates`, `web_static`, and containment audits |
| **`web_assets`** | [`web/templates/index.html`](web/templates/index.html) · [`web/static/css/plugin.css`](web/static/css/plugin.css) | Editable Two-World `/dashboard` layout and `--zcg-*` theme overrides |
| **`rules_file`** | [`rules/secops-mcp-guardian.md`](rules/secops-mcp-guardian.md) | Zero-trust MCP boundary gates, clearance (`0..100`) enforcement, and drift alerts |

---

## 2. Core SecOps & MCP Guardian Capabilities

The `secops-mcp-guardian` plugin hardens cross-node MCP federation (`zcg-mcp`) and security-critical repositories:

1. **HMAC-Authenticated `DMCP` Envelopes**: Signs and verifies federated MCP payloads (`dmcp_protocol.py`) while enforcing operator clearance (`0..100`) and environment stage (`dev | pre | pro`) boundaries.
2. **Strictly-Read-Only Ephemeral Sandboxes (`orchestrate_ephemeral_fork`)**: Creates isolated, non-mutating workspace views (`sandbox_fork.py`) so cross-layer inspections cannot alter source repositories.
3. **Cryptographic Citation & Drift Auditing**: Raises `CITATION_DRIFT_DETECTED` or `PATH_CONTAINMENT_VIOLATION` immediately when referenced digests or paths deviate from canonical contracts.

---

## 3. Mounting & Cross-References

Declare `secops-mcp-guardian` in `system/zcg-node.json` under `stack_groups.plugin_stack` and synchronize the node:

```bash
zcg sync-layer /path/to/secops-node
```

- **Parent Framework Stack**: `templates/framework-stack/nist-csf-security/README.md`
- **Contextual MCP Architecture**: `docs/architecture/05_contextual_mcp_and_capsules.md`
- **Security Reference**: `docs/reference/02_cli_mcp_and_security_reference.md`
