---
trigger: always_on
description: "Academic curriculum, Socratic lesson design, active-recall boundary drills, and M1..M4 mastery progression rules (academic-curriculum)"
---

# Academic Curriculum & Guided Learning Context Pack (`academic-curriculum`)

> Domain specialization pack extending **`academic-base`** (`templates/human-stack/academic-base/rules/academic-base.md`) for personal study tutors (`tutor-*`), school/secondary education (`M1`), university degree coursework (`M2`), competitive examination prep, and professional upskilling (`M3 -> M4`).

---

## Curriculum Structure, `Maintainer vs. Consumer` Viewpoints & Mastery Gates

- **Description**: Dual viewpoint separation (`Maintainer` vs. `Consumer`), modular `SYLLABUS.md` design, `M1..M4` delivery protocol, active-recall boundary drills, and `WORKVALI.md` mastery verification
- **Applies**: All academic study workspaces, university course repositories, and personal tutor sub-layers (`tutor-*`)

1. **Dual Viewpoint Separation (`Maintainer` vs. `Consumer`, `ACAD-01`)**:
   - **Maintainer / Producer Viewpoint (Information Architecture)**:
     - **`sci-*` / `gov-*` / `geo-*` (`docs/reference/` — `E3/E2`)**: Maintains consolidated scientific laws, clinical evidence, and statutes by `Trunk -> Branch -> Specialty`.
     - **`org-uni-*` & Study Layers (`docs/guides/` — `E1`)**: Universities, academic institutions, and personal tutors curate degree syllabi, lab exercises, and `M1..M4` learning progressions citing `docs/reference/` via `citation_receipt`.
     - **`org-*` Enterprises (`corporate/` & `src/` — `M3/M4`)**: Post-academic professional practice applying scientific, engineering, and statutory truth to production products and services.
   - **Consumer Viewpoint (`consumer_viewpoint` Personalization Guardrails)**:
     - Inspect active `human_stack` facets (`make status` or `query_governance_rules` $\rightarrow$ `consumer_viewpoint`). Never expose an `M1` learner to uncontextualized `L3` research proofs when a foundational `docs/guides/` (`L1/E1`) progression exists.
2. **Modular `SYLLABUS.md` & Maturity-Graded Delivery Protocol (`M1 -> M4`, `ACAD-02`)**:
   - Structure every course, subject, or study program around a root `SYLLABUS.md` (`< 465` lines) partitioned into 4 progressive stages matching the learner's `.agents/SESSION.md` `Human-Stack` (`domain-<subject>:M1..M4 | soft-socratic-coach`):

| Consumer Level | Continuum Stage | Retrieval Priority (`consumer_viewpoint`) | Pedagogical & Operational Guardrails |
| :--- | :--- | :--- | :--- |
| **`M1` (*School / Year-1 Foundations*)** | **Academic Foundation** | `academic-tutor-m1-m2` (`docs/guides/` `L1` first) | Use Socratic questions, visual mental models, and zero unexplained jargon; link every concept to its `E3` axiom via `citation_receipt`. |
| **`M2` (*University / Formal Core*)** | **Academic Core** | `academic-tutor-m1-m2` (`docs/guides/` `L1 -> L2`) | Introduce canonical `E2` equations, proofs, statutory structure, and worked boundary examples (`N` vs `N ± 1`). |
| **`M3` (*Practitioner / Professional*)** | **Professional Practice** | `professional-scientific-m3-m4` (`docs/reference/` & `docs/architecture/` `E3/E2` `L2`) | Deliver production-ready engineering/clinical/legal contracts, trade-off matrices, and `AAA` verification gates directly. |
| **`M4` (*Researcher / Principal*)** | **Scientific Frontier** | `professional-scientific-m3-m4` (`docs/reference/` `E3/E2` `L3` + `E1/E0` frontier) | Unfold `L3` first-principles proofs, raw empirical datasets, and open `E0` hypotheses with zero introductory boilerplate. |

3. **Socratic Lesson Delivery & Anti-Spoiler Drill Protocol (`ACAD-03`)**:
   - Store didactic lessons in `docs/guides/<unit_slug>.md` (`< 465` lines, `E1` epistemic grade) and practice exercises in `drills/` or `WORKVALI.md`.
   - When executing `academic-tutor` (`next-lesson` or `practice-drill`), **never reveal the full solution to a drill upfront**: present the problem, formulate Socratic guiding hints when the learner is stuck, and require the learner to articulate the reasoning or boundary cut-point (`N` vs `N ± 1`) first.
4. **Closed-Loop `citation_receipt` Grounding & Verifiable Mastery Gate (`verify-mastery` in `WORKVALI.md`, `ACAD-04`)**:
   - Every didactic lesson in `docs/guides/` must cite its underlying primary reference truth (`docs/reference/` or mounted `layers/{sci,gov,geo,org}-*`) using canonical `citation_receipt` anchors (`<layer_id>::<rel_file>#<section_slug>@<h2_digest16>:<epistemic_grade>`).
   - Track each curriculum unit as a bounded task in `WORKTASK.md` (`make task`) and record mastery verification checklists in `WORKVALI.md`. A learner only graduates from `M1 -> M2 -> M3 -> M4` in `.agents/SESSION.md` (`make complete`) after passing the unit's nominal, boundary (`N ± 1`), and counter-example verification checks.
