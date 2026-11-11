# `scientific-methodology` (`context-stack`) — Tier 2 Formal Epistemology & Corpus Curation

> Tier 2 domain specialization extending `science-base` for formal proof/citation trace-chains, reproducible benchmarks, and sovereign knowledge repositories (`osa-*`).

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/scientific-methodology.md`](rules/scientific-methodology.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `scientific-methodology` | Domain specialization in `VALID_CONTEXT_STACK_IDS` (`constants.py`) |
| **`stack_group`** | `context-stack` | Domain Methodology & Practice Axis |
| **`tier`** | `2` (`Domain Specialization`) | Materialized into `.agents/rules/scientific-methodology.md` via `zcg sync-layer` |
| **`extends`** | `["science-base"]` | Transitively resolves `universal-base -> science-base -> scientific-methodology` |
| **`rules_file`** | [`rules/scientific-methodology.md`](rules/scientific-methodology.md) | Formal hypothesis falsifiability, `E3..E0` corpus curation, `rcap1` capsules |

---

## 2. Core Methodological & Corpus Invariants

The `scientific-methodology` specialization governs research workspaces and foundational knowledge bases (`sci-math`, `sci-physics`, `sci-compsci`, `geo-es`, `gov-iso`, `org-type`):

1. **Axiomatic & Statutory Traceability (`E3 -> E0`)**: Anchor every derived theorem, normative rule, or analytical model to a primary `E3`/`E2` source with a verifiable `citation_receipt` (`<layer>::<file>#<slug>@<digest16>:<E3..E0>`).
2. **Falsifiable Hypotheses & Dimensional Consistency**: State assumptions, domain bounds, and SI/ISO units explicitly before deriving results or executing numerical simulations.
3. **`L0..L3` Capsule Readiness (`rcap1`)**: Structure `docs/{guides,architecture,reference}/*.md` with clean `#..####` headings so `zcg-mcp` (`unfold_context_capsule`) can project lossless `L0/L1` summaries and `L3` deep citations.

---

## 3. Mounting & Cross-References

Declare `scientific-methodology` in `system/zcg-node.json` under `stack_groups.context_stack` and synchronize the node:

```bash
zcg sync-layer /path/to/knowledge-node
```

- **Parent Human Stack**: `templates/human-stack/science-base/README.md`
- **Contextual MCP Architecture**: `docs/architecture/05_contextual_mcp_and_capsules.md`
- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
