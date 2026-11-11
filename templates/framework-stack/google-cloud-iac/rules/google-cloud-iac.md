---
trigger: always_on
description: "Google Cloud (Cloud Run, GKE, BigQuery, IAM/ADC) infrastructure contracts and Google Antigravity SDK agentic workload rules (google-cloud-iac)."
---

# Google Cloud & Antigravity Infrastructure Rules (`google-cloud-iac`)

> Extends `software-engineering` with sovereign Zero-Cloud deployment contracts targeting **Google Cloud (`Cloud Run`, `GKE`, `BigQuery`, `Cloud Storage`, `IAM/ADC`)**, **Google Gemini (`flash_lite`, `flash`, `pro`)**, and the **Google Antigravity SDK**.

---

## Scope & Surface Target

- **Template Pack**: `templates/framework-stack/google-cloud-iac/` (`framework-stack`, `extends: software-engineering`).
- **Applies**: Cloud infrastructure squads, data/telemetry pipelines, container services (`Dockerfile`), and multi-agent Antigravity SDK workloads governing `surfaces/infra/**`, `src/**`, and `docs/**`.

---

## Normative Invariants

1. **`GCP-IAC-01` — Workload Identity & Least-Privilege `IAM/ADC` (`Zero Static Keys`)**:
   - Authenticate exclusively via Google Cloud **Application Default Credentials (`ADC`)** and **Workload Identity Federation**. Never commit service-account JSON keys, OAuth tokens, or unmasked project secrets to Git.
2. **`GCP-IAC-02` — Non-Root Immutable `Cloud Run` & `GKE` Containers**:
   - Run every container image under an explicit unprivileged UID (`USER 10001`), bind health probes to `/healthz`, enforce `ZCG_NO_BROWSER=1` and `PYTHONDONTWRITEBYTECODE=1`, and keep container filesystems read-only outside `/tmp`.
3. **`GCP-IAC-03` — `BigQuery` Attribution, Partitioning & Parameterized Queries**:
   - Partition and cluster analytical tables deterministically, enforce parameterized queries (`0` string-interpolated SQL), and attach explicit resource attribution labels to provisioning commands.
4. **`GCP-IAC-04` — Google Antigravity SDK & Gemini Tier Routing**:
   - Align agentic sub-workflows with `VALID_AGENT_TIERS` (`flash_lite`/`flash` for high-throughput bounded telemetry, `inherit` for standard node orchestration, `pro` for `L3` synthesis and production gate audits) and seal inter-agent handoffs with `4-Channel Digest` `rcap1` capsules.

---

## Verification & Sign-Off Gates

- [ ] Zero static service-account JSON keys or hardcoded GCP credentials exist in `src/**` or `surfaces/**`.
- [ ] `Dockerfile` specifies non-root `USER`, `ZCG_NO_BROWSER=1`, and deterministic `/healthz` or `zcg-mcp --self-test` healthcheck.
- [ ] Progressive `make env-gate` (`dev -> tst -> pre -> pro`) passes prior to `Cloud Run` / `GKE` / `BigQuery` promotion.
