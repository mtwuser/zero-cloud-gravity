# `science-base` (`human-stack`) — Tier 1 Scientific & Epistemic Rigor Baseline

> Tier 1 epistemic persona extending `universal-base` with `Trunk -> Branch -> Specialty` taxonomy, `1:1:1` traceability, SI/ISO precision, and `E3..E0` credibility hierarchies.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/science-base.md`](rules/science-base.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `science-base` | Scientific persona in `VALID_HUMAN_STACK_IDS` (`constants.py`) |
| **`stack_group`** | `human-stack` | Cognitive & Epistemic Persona Axis |
| **`tier`** | `1` (`Domain Persona`) | Mounted via `.agents/rules/science-base.md` or `--profile science-base` |
| **`extends`** | `["universal-base"]` | Inherits all 13 universal mandates from `universal-base` |
| **`rules_file`** | [`rules/science-base.md`](rules/science-base.md) | Epistemic hierarchy (`E3..E0`), `1:1:1` symbiosis, `N vs N ± 1` cut-points |

---

## 2. Core Epistemic & Scientific Invariants

The `science-base` rule corpus enforces formal scientific method and mathematical precision across research, knowledge (`osa-*`), and software repositories:

1. **Arboreal Taxonomy (`Trunk -> Branch -> Specialty`)**: Route rules concisely through `.agents/rules/*.md` and index domain corpora under `docs/{guides,architecture,reference}/` (`< 465` lines).
2. **Universal `1:1:1` Symbiosis (`Theory/Spec <-> Test <-> Implementation`)**: Read specifications first, verification tests second, and implementation last; declare `Specification: docs/architecture/<spec>.md` in every unit test module.
3. **Constants, SI/ISO Precision & Cut-Points (`N vs N ± 1`)**: Forbid magic numbers or raw slices; require nominal constants (`*_CONTRACT_REV`, `MAX_*`, `MIN_*`, `DEFAULT_*`, `VALID_*`) and exact boundary cut-points.
4. **Epistemic Credibility (`E3 > E2 > E1 > E0`) & Citation Receipts**: Enforce `E3` (Law/Axiom) $>$ `E2` (Standard) $>$ `E1` (Peer-Reviewed Theory) $>$ `E0` (Working Draft) and verify cryptographic `citation_receipt` digests (`<layer>::<file>#<slug>@<digest16>:<E3..E0>`).

---

## 3. Activation & Cross-References

Mount `science-base` in scientific or software nodes (`system/zcg-node.json`) or activate it globally:

```bash
zcg set-global-profile science-base --lang es
```

- **Companion Context Stacks**: `scientific-methodology` · `software-engineering`
- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
