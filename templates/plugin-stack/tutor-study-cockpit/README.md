# `tutor-study-cockpit` (`plugin-stack`) — Tier 2 Pedagogical & Mastery Progression Surface

> Tier 2 runtime surface plugin extending `academic-curriculum` for academic workspaces (`alex-tutor`), interactive `M1..M4` study dashboards, and `verify-mastery` checkpoints.

---

## 1. Template Identity & Service Contract (`template.json` & `service_contract.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json), [`assets/service_contract.json`](assets/service_contract.json), and [`rules/tutor-study-cockpit.md`](rules/tutor-study-cockpit.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `tutor-study-cockpit` | Runtime surface in `CANONICAL_STARTER_TEMPLATES` (`constants.py`) |
| **`stack_group`** | `plugin-stack` | Editable Reference Dashboard & Cockpit Capability Axis |
| **`extends`** | `"academic-curriculum"` | Transitively resolves `universal-base -> academic-base -> academic-curriculum -> tutor-study-cockpit` |
| **`service_contract`** | [`assets/service_contract.json`](assets/service_contract.json) | Declares `enabled_modules`, `web_templates`, `web_static`, and `M1..M4` gates |
| **`web_assets`** | [`web/templates/index.html`](web/templates/index.html) · [`web/static/css/plugin.css`](web/static/css/plugin.css) | Editable Two-World `/dashboard` layout and `--zcg-*` theme overrides |
| **`rules_file`** | [`rules/tutor-study-cockpit.md`](rules/tutor-study-cockpit.md) | Study session cadence, anti-spoiler cockpit rendering, and rubric telemetry |

---

## 2. Core Study Cockpit Capabilities

The `tutor-study-cockpit` plugin powers dedicated learning and tutoring workspaces (`alex-tutor`):

1. **`M1..M4` Mastery Telemetry**: Visualizes learner progression across syllabus units (`M1` Intuition $\rightarrow$ `M2` Guided Practice $\rightarrow$ `M3` Boundary Analysis $\rightarrow$ `M4` Autonomous Verification).
2. **Socratic Session Continuity**: Connects `.agents/SESSION.md` and `WORKTASK.md` study lots so tutoring sessions resume at the exact conceptual checkpoint without losing prior diagnostic context.
3. **Automated Rubric Verification (`verify-mastery`)**: Integrates practice exercise runners with the node's `Makefile` verification targets.

---

## 3. Mounting & Cross-References

Declare `tutor-study-cockpit` in `system/zcg-node.json` under `stack_groups.plugin_stack` and synchronize the academic node:

```bash
zcg sync-layer /path/to/academic-node
```

- **Parent Context Stack**: `templates/context-stack/academic-curriculum/README.md`
- **Parent Human Stack**: `templates/human-stack/academic-base/README.md`
- **Cockpit Architecture**: `docs/architecture/04_cockpit_and_intranet_surfaces.md`
