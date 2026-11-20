# `self-hosted-container` (`tool-stack`) — Vendor-Neutral OCI Container, TLS 1.3 & Standard OIDC Adapter

> Sovereign zero-cloud deployment adapter extending `nist-csf-security` and `software-engineering` for bare-metal, LAN, VPS, or private intranet nodes running OCI containers behind TLS 1.3 reverse proxies and RFC-standard OIDC identity providers.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/self-hosted-container.md`](rules/self-hosted-container.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `self-hosted-container` | Sovereign deployment adapter in `CANONICAL_STARTER_TEMPLATES` (`constants.py`) |
| **`stack_group`** | `tool-stack` | Optional External Provider, Cloud, CLI & Runtime Adapter Axis |
| **`tier`** | `2` (`Provider Adapter`) | Materialized into `.agents/rules/self-hosted-container.md` via `zcg sync-layer` |
| **`extends`** | `"nist-csf-security"` | Transitively resolves `universal-base -> science-base -> software-engineering -> nist-csf-security -> self-hosted-container` |
| **`rules_file`** | [`rules/self-hosted-container.md`](rules/self-hosted-container.md) | Non-root OCI containers, TLS 1.3 / CIDR-trusted proxy headers, RFC OIDC |

---

## 2. Core Self-Hosted & Edge Invariants

The `self-hosted-container` adapter governs sovereign deployments without cloud-provider lock-in:

1. **Immutable Non-Root OCI Containers**: Run containers under unprivileged UIDs (`USER zcg`), mount read-only root filesystems, keep `.zcg/runtime/` SQLite WAL volumes outside the image, and verify `/healthz` + `/readyz` probes.
2. **End-to-End TLS 1.3 & CIDR-Gated Reverse Proxies**: Terminate TLS 1.3 (or mTLS) natively via `zcg.web.auth.tls` or behind an explicit CIDR-trusted reverse proxy (`Caddy`, `Nginx`, `Traefik`), rejecting plaintext binds on non-loopback interfaces (`PLAINTEXT_NON_LOOPBACK_BLOCKED`).
3. **Standard RFC OIDC Identity Federation**: Authenticate `R1/R2/R3` web rings against any standards-compliant OpenID Connect / OAuth 2.1 `S256` PKCE provider (`Keycloak`, `Authelia`, `Pocket ID`, custom Proton/enterprise IdP) using runtime environment secrets (`0` credentials in Git).

---

## 3. Mounting & Cross-References

Declare `self-hosted-container` in `system/zcg-node.json` under `default_stack_templates` and synchronize the node:

```bash
zcg sync-layer /path/to/sovereign-node
```

- **Parent Security Methodology**: `templates/context-stack/nist-csf-security/README.md`
- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
