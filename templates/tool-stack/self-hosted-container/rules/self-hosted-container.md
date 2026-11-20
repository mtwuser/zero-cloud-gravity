---
trigger: always_on
description: "Vendor-neutral OCI container, TLS 1.3 reverse-proxy, and standard RFC OIDC self-hosted deployment rules (self-hosted-container)."
---

# Sovereign Self-Hosted Container, TLS 1.3 & Standard OIDC Rules (`self-hosted-container`)

> Extends `nist-csf-security` with vendor-neutral Zero-Cloud deployment contracts targeting **OCI Containers**, **TLS 1.3 / mTLS Reverse Proxies (`Caddy`, `Nginx`, `Traefik`)**, and **RFC-Standard OpenID Connect (`OIDC`)** providers.

---

## Scope & Surface Target

- **Template Pack**: `templates/tool-stack/self-hosted-container/` (`tool-stack`, `extends: nist-csf-security`).
- **Applies**: Self-hosted bare-metal, LAN intranet, and sovereign VPS nodes governing `surfaces/infra/**`, `Dockerfile`, `src/**`, and `system/zcg-node.json`.

---

## Normative Invariants

1. **`SHC-01` — Non-Root Immutable OCI Runtime (`Zero Cloud Lock-In`)**:
   - Execute container workloads under an unprivileged UID (`USER zcg`), enforce `ZCG_NO_BROWSER=1` and `PYTHONDONTWRITEBYTECODE=1`, expose `/healthz` and `/readyz`, and persist mutable `.zcg/runtime/` state on host-owned volumes outside Git.
2. **`SHC-02` — TLS 1.3 Termination & Trusted Proxy CIDR Containment**:
   - Enforce direct OpenSSL 3 TLS 1.3 / mTLS (`--tls-certfile` / `--tls-keyfile`) or explicit CIDR-bounded `--behind-tls-proxy --trusted-proxy <CIDR>` forwarding; block unencrypted HTTP on non-loopback interfaces (`PLAINTEXT_NON_LOOPBACK_BLOCKED`).
3. **`SHC-03` — Vendor-Neutral OIDC `S256` PKCE & Zero-Literal Secrets**:
   - Bind `R1..R3` session elevation to standard OIDC discovery/token/userinfo endpoints (`Keycloak`, `Authelia`, `Pocket ID`, or enterprise OIDC) via runtime environment variables (`0` static client secrets or private emails in Git).

---

## Verification & Sign-Off Gates

- [ ] `Dockerfile` specifies non-root `USER`, `ZCG_NO_BROWSER=1`, and deterministic healthcheck without vendor-proprietary agents.
- [ ] Non-loopback bindings enforce TLS 1.3 or explicit `--trusted-proxy` CIDRs, and progressive `make env-gate` passes prior to `pro` promotion.
