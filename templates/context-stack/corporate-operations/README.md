# `corporate-operations` (`context-stack`) — Tier 2 Multi-Node Portfolio & Compliance Operations

> Tier 2 corporate specialization extending `business-base` for multi-repository program governance, RBAC stage gates, and `corporate/` policy synchronization.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/corporate-operations.md`](rules/corporate-operations.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `corporate-operations` | Domain specialization in `VALID_CONTEXT_STACK_IDS` (`constants.py`) |
| **`stack_group`** | `context-stack` | Domain Methodology & Practice Axis |
| **`tier`** | `2` (`Domain Specialization`) | Materialized into `.agents/rules/corporate-operations.md` via `zcg sync-layer` |
| **`extends`** | `["business-base"]` | Transitively resolves `universal-base -> business-base -> corporate-operations` |
| **`rules_file`** | [`rules/corporate-operations.md`](rules/corporate-operations.md) | Portfolio alignment, 1-hop delegation (`make delegate`), RBAC & audit trails |

---

## 2. Core Operational & Governance Invariants

The `corporate-operations` specialization governs enterprise hubs (`corporate_root`) and their child operational nodes:

1. **1-Hop Downward Delegation & Portfolio Traceability**: Coordinate cross-repository initiatives from `roadmaps/` $\rightarrow$ `WORKROAD.md` $\rightarrow$ `WORKTASK.md` via `zcg delegate`, maintaining deterministic parent-child linkage without hidden multi-hop mutations.
2. **RBAC Roster & Decision Ledger Integrity**: Validate operator clearance (`0..100`) and environment stage gates (`dev | pre | pro`) via `zcg roster`, `zcg decision`, and `zcg env-gate`.
3. **Statutory & Corporate Policy Parity**: Keep `corporate/**/*.md` (`< 465` lines) synchronized with mounted `gov-iso` and `org-type` reference corpora.

---

## 3. Mounting & Cross-References

Declare `corporate-operations` in `system/zcg-node.json` under `stack_groups.context_stack` and synchronize the node:

```bash
zcg sync-layer /path/to/corporate-node
```

- **Parent Human Stack**: `templates/human-stack/business-base/README.md`
- **Companion Plugin Surface**: `templates/plugin-stack/corporate-root-hub/README.md`
- **Governance Architecture**: `docs/architecture/03_governance_and_work_ledger.md`
