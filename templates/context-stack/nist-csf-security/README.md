# `nist-csf-security` (`context-stack`) — Tier 2 Cybersecurity & Cryptographic Control Methodology

> Tier 2 regulatory and security control methodology extending `software-engineering` with NIST CSF 2.0 (`GV/ID/PR/DE/RS/RC`), OWASP ASVS L2/L3, and zero-trust MCP boundary controls.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/nist-csf-security.md`](rules/nist-csf-security.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `nist-csf-security` | Cybersecurity methodology in `CANONICAL_STARTER_TEMPLATES` (`constants.py`) |
| **`stack_group`** | `context-stack` | Domain Methodology, Standards & Control Axis |
| **`tier`** | `2` (`Domain Methodology`) | Materialized into `.agents/rules/nist-csf-security.md` via `zcg sync-layer` |
| **`extends`** | `"software-engineering"` | Transitively resolves `universal-base -> science-base -> software-engineering -> nist-csf-security` |
| **`rules_file`** | [`rules/nist-csf-security.md`](rules/nist-csf-security.md) | NIST CSF 2.0 control mapping, cryptographic receipts, and containment gates |

---

## 2. Core Security & Control Invariants

The `nist-csf-security` overlay enforces defense-in-depth across sensitive workstations, corporate hubs, and secops nodes:

1. **NIST CSF 2.0 Six-Function Alignment (`GV · ID · PR · DE · RS · RC`)**: Map repository controls explicitly across Govern (`GV`), Identify (`ID`), Protect (`PR`), Detect (`DE`), Respond (`RS`), and Recover (`RC`).
2. **Zero-Trust Path & Subprocess Containment**: Require canonical `Path.resolve().is_relative_to(workspace_root)` checks (`PATH_CONTAINMENT_VIOLATION`), explicit argument lists (`shell=False`), and `strictly-read-only` sandbox boundaries.
3. **Cryptographic Integrity & Anti-Streisand Hygiene**: Verify `SHA-256` digests (`hashlib.file_digest`), HMAC-authenticated `DMCP` envelopes, and ISO-neutral identifiers (`0` plaintext secrets or private tenant tokens).

---

## 3. Mounting & Cross-References

Declare `nist-csf-security` in `system/zcg-node.json` under `default_stack_templates` and synchronize the node:

```bash
zcg sync-layer /path/to/secure-node
```

- **Parent Context Stack**: `templates/context-stack/software-engineering/README.md`
- **Companion SecOps Plugin**: `templates/plugin-stack/secops-mcp-guardian/README.md`
- **Security Reference**: `docs/reference/02_cli_mcp_and_security_reference.md`
