# `academic-curriculum` (`context-stack`) — Tier 2 Syllabus & Mastery Verification Specialization

> Tier 2 domain specialization extending `academic-base` for structured syllabus authoring, `M1..M4` problem sets, and automated `verify-mastery` assessment pipelines.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/academic-curriculum.md`](rules/academic-curriculum.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `academic-curriculum` | Domain specialization in `VALID_CONTEXT_STACK_IDS` (`constants.py`) |
| **`stack_group`** | `context-stack` | Domain Methodology & Practice Axis |
| **`tier`** | `2` (`Domain Specialization`) | Materialized into `.agents/rules/academic-curriculum.md` via `zcg sync-layer` |
| **`extends`** | `["academic-base"]` | Transitively resolves `universal-base -> academic-base -> academic-curriculum` |
| **`rules_file`** | [`rules/academic-curriculum.md`](rules/academic-curriculum.md) | Curriculum decomposition, Bloom/`M1..M4` rubrics, and mastery telemetry |

---

## 2. Core Curriculum & Assessment Contracts

The `academic-curriculum` specialization standardizes how educational repositories structure modules, exercises, and evaluations:

1. **Modular Syllabus Decomposition**: Partition courses into self-contained units (`< 465` lines per guide) with explicit prerequisites, learning objectives, and `M1..M4` competency checkpoints.
2. **Deterministic Mastery Gates (`verify-mastery`)**: Pair conceptual modules with executable grading suites or structured rubric verifiers so learners receive objective feedback without leaking full solutions prematurely.
3. **Spaced Retention & Error Taxonomy**: Track recurring conceptual misconceptions in study ledgers to adapt subsequent problem sets dynamically.

---

## 3. Mounting & Cross-References

Declare `academic-curriculum` in `system/zcg-node.json` under `stack_groups.context_stack` and synchronize the node:

```bash
zcg sync-layer /path/to/academic-node
```

- **Parent Human Stack**: `templates/human-stack/academic-base/README.md`
- **Companion Plugin Surface**: `templates/plugin-stack/tutor-study-cockpit/README.md`
- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
