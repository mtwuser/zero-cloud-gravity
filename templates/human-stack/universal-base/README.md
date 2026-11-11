# `universal-base` (`human-stack`) — Tier 0 Global Cognitive & Governance Baseline

> Foundational Tier 0 cognitive, organizational, and `ZeroCloudGravity` orchestration baseline mounted globally across `$HOME` (`~/.gemini/config/AGENTS.md`) and inherited by all Tier 1 profiles.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/universal-base.md`](rules/universal-base.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `universal-base` | Root identity in `VALID_HUMAN_STACK_IDS` (`constants.py`) |
| **`stack_group`** | `human-stack` | Cognitive & Epistemic Persona Axis |
| **`tier`** | `0` (`Global Foundation`) | Always active at the top of `~/.gemini/config/AGENTS.md` |
| **`extends`** | `[]` (`Root`) | Base of the DAG (`academic-base`, `science-base`, `business-base` extend it) |
| **`rules_file`** | [`rules/universal-base.md`](rules/universal-base.md) | 13 behavioral mandates + universal commit & priority-chain governance |

---

## 2. Core Mandates & Operational Invariants

The `universal-base` rule corpus establishes the 13 non-negotiable operational laws across every workspace:

1. **Reusability First & Orthogonal Taxonomy (`X × Y`)**: Compose orthogonal dimensions (`entity_kind × layer_role × stack_groups`) with `0` flat case heuristics and `1 Skill = 1 Verb`.
2. **Professional Robustness & Modularity**: Keep source modules (`<= 385` target), tests, root `README.md` (`<= 400`), and documentation files `< 465` lines.
3. **Verification & Quality Integrity**: Require `ZCG_NO_BROWSER=1 make verify`, `zcg diff-project`, and `audit_node_drift` to pass with zero warnings before task completion.
4. **Atomic Deliverable & `1:1:1` Verification Inclusion**: Pair every change with active-layer verification (`Spec <-> Verification <-> Deliverable`).
5. **Bounded Lots & 4-Line Compass (`Human <-> AI`)**: Execute `1` bounded lot per turn (`3–5` files) and close every turn with the 4-line compass (`✅ Done · 📍 Position · 👤 Action · ⏭️ Next`).
6. **Dual-Plane Language Purity & Zero-Backward Cutover**: Respond in the configured `--lang <es|en|it|fr|de|pt>` while keeping repository artifacts 100% in English (`[WIRE] -> [CONSOLIDATE] -> [PRUNE]`).
7. **Universal Commit Discipline**: Never run mutating Git commands automatically; emit one Conventional Commit block per independent repository only at full stop.

---

## 3. Activation & Cross-References

Activate `universal-base` as the global workstation profile or inspect its full specification in the reference catalog:

```bash
zcg set-global-profile universal-base --lang es --workstation-dir "$HOME/alex-pc"
```

- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
- **Workstation Guide**: `docs/guides/01_workstation_and_global_profiles.md`
