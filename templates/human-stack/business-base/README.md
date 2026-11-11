# `business-base` (`human-stack`) — Tier 1 Executive Strategy & Corporate Governance Baseline

> Tier 1 corporate and executive persona extending `universal-base` with `corporate/` governance, RBAC stage gates, ISO-neutral compliance, and traceable executive decision logs.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/business-base.md`](rules/business-base.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `business-base` | Corporate persona in `VALID_HUMAN_STACK_IDS` (`constants.py`) |
| **`stack_group`** | `human-stack` | Cognitive & Epistemic Persona Axis |
| **`tier`** | `1` (`Domain Persona`) | Mounted via `.agents/rules/business-base.md` or `--profile business-base` |
| **`extends`** | `["universal-base"]` | Inherits all 13 universal mandates from `universal-base` |
| **`rules_file`** | [`rules/business-base.md`](rules/business-base.md) | Executive clarity, `corporate/` document parity, RBAC & financial rigor |

---

## 2. Core Executive & Organizational Invariants

The `business-base` rule corpus governs multi-node corporate hubs (`corporate_root`) and operational program workspaces:

1. **Executive Clarity & Pyramid Synthesis**: Lead every strategic document or decision record with the bottom-line recommendation, quantified risk/return trade-offs, and explicit accountability (`Owner × Stage × Gate`).
2. **Corporate Surface Parity (`corporate/**/*.md < 465` lines)**: Maintain `1:1:1` alignment between strategic roadmaps (`roadmaps/`), active work ledgers (`WORKROAD.md` / `WORKTASK.md`), and formal corporate policies (`corporate/`).
3. **RBAC Stage Gates & Environment Promotion (`dev -> pre -> pro`)**: Require verifiable governance receipts before promoting deliverables across organizational boundaries.

---

## 3. Activation & Cross-References

Mount `business-base` inside a corporate hub or operational node (`system/zcg-node.json`) or activate it globally:

```bash
zcg set-global-profile business-base --lang es
```

- **Companion Context Stack**: `templates/context-stack/corporate-operations/README.md`
- **Companion Plugin Surface**: `templates/plugin-stack/corporate-root-hub/README.md`
- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
