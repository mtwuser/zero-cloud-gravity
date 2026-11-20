# `google-cloud-iac` (`tool-stack`) — Opt-In Google Cloud & Managed Infrastructure Adapter

> Optional `tool-stack` cloud deployment adapter extending `nist-csf-security` and `software-engineering` with least-privilege IAM, declarative provisioning, resource attribution, and FinOps guardrails when a node explicitly targets Google Cloud.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/google-cloud-iac.md`](rules/google-cloud-iac.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `google-cloud-iac` | Opt-in cloud provider adapter in `CANONICAL_STARTER_TEMPLATES` (`constants.py`) |
| **`stack_group`** | `tool-stack` | Optional External Provider, Cloud, CLI & Runtime Adapter Axis |
| **`tier`** | `2` (`Provider Adapter`) | Materialized into `.agents/rules/google-cloud-iac.md` via `zcg sync-layer` |
| **`extends`** | `"nist-csf-security"` | Transitively resolves `universal-base -> science-base -> software-engineering -> nist-csf-security -> google-cloud-iac` |
| **`rules_file`** | [`rules/google-cloud-iac.md`](rules/google-cloud-iac.md) | Least-privilege IAM, declarative state parity, region pinning, FinOps labels |

---

## 2. Core Cloud & Infrastructure Invariants

The `google-cloud-iac` adapter governs nodes that opt in to Google Cloud Platform (GCP) infrastructure, data pipelines, and declarative provisioning modules:

1. **Least-Privilege IAM & Zero Long-Lived Keys**: Enforce workload identity federation and dedicated service accounts scoped to minimal resource roles; forbid exported JSON service account keys in repositories.
2. **Declarative Environment Promotion (`dev -> pre -> pro`)**: Parameterize project IDs, regions, and quotas deterministically so staging and production topologies remain structurally identical (`0` manual console drift).
3. **Resource Attribution & Cost Guardrails**: Require cost-center, environment, and owner labels plus explicit partition/cluster filters on analytical workloads.

---

## 3. Mounting & Cross-References

Declare `google-cloud-iac` in `system/zcg-node.json` under `default_stack_templates` and synchronize the node:

```bash
zcg sync-layer /path/to/cloud-node
```

- **Parent Security Methodology**: `templates/context-stack/nist-csf-security/README.md`
- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
