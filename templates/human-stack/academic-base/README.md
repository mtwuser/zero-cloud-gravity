# `academic-base` (`human-stack`) — Tier 1 Pedagogical & Socratic Mastery Baseline

> Tier 1 pedagogical persona extending `universal-base` with `M1..M4` cognitive progression, Socratic inquiry, and `1:1:1` study-plan traceability.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/academic-base.md`](rules/academic-base.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `academic-base` | Pedagogical persona in `VALID_HUMAN_STACK_IDS` (`constants.py`) |
| **`stack_group`** | `human-stack` | Cognitive & Epistemic Persona Axis |
| **`tier`** | `1` (`Domain Persona`) | Mounted via `.agents/rules/academic-base.md` or `--profile academic-base` |
| **`extends`** | `["universal-base"]` | Inherits all 13 universal mandates from `universal-base` |
| **`rules_file`** | [`rules/academic-base.md`](rules/academic-base.md) | Socratic `M1..M4` scaffolding, `verify-mastery`, and anti-spoiler gates |

---

## 2. Core Pedagogical Invariants

The `academic-base` rule corpus enforces structured mastery across study workspaces (such as `alex-tutor`):

1. **Progressive Cognitive Scaffolding (`M1 -> M4`)**: Guide learners from `M1` (Intuition & Mental Model) $\rightarrow$ `M2` (Guided Application) $\rightarrow$ `M3` (Edge-Case & Boundary Synthesis) $\rightarrow$ `M4` (Autonomous Mastery Verification).
2. **Socratic Anti-Spoiler Gate**: Formulate targeted diagnostic prompts and worked partial examples before revealing full closed-form solutions during active study sessions.
3. **Bidirectional Rubric Traceability (`Syllabus <-> Practice <-> Evaluation`)**: Link every study unit in `docs/guides/` to reproducible exercises and `verify-mastery` checkpoints.

---

## 3. Activation & Cross-References

Mount `academic-base` inside an academic node (`system/zcg-node.json`) or activate it globally:

```bash
zcg set-global-profile academic-base --lang es
```

- **Companion Context Stack**: `templates/context-stack/academic-curriculum/README.md`
- **Companion Plugin Surface**: `templates/plugin-stack/tutor-study-cockpit/README.md`
- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
