---
name: academic-tutor
description: "Execute interactive curriculum planning (syllabus), Socratic lesson delivery (next-lesson), active-recall boundary drills (practice-drill), and mastery verification (verify-mastery) in academic-curriculum and personal tutor workspaces."
---
# Skill: Academic Curriculum & Mastery Action Playbook (`academic-tutor`)

> Procedural workspace action playbook for [`templates/context-stack/academic-curriculum`](../../README.md) (`extends: "academic-base"`). Continuous cognitive and pedagogical invariants (`Maintainer vs. Consumer` viewpoint separation, `M1 -> M4` delivery guardrails, and Socratic anti-spoiler rules) are governed by `always_on` rules in `academic-base.md` and `academic-curriculum.md`; this skill executes the 4 deterministic curriculum lifecycle actions (`syllabus`, `next-lesson`, `practice-drill`, `verify-mastery`).

---

## 1. Interactive Tutor Playbooks & Dual-World Command Mapping (`SKILL.md` $\leftrightarrow$ `Makefile`)

In a Personal Tutor layer (`tutor-*`, `precedence: 85..89`) or study workspace (`apply-project --template academic-base,academic-curriculum`), pedagogical actions map isomorphically onto the standard trackers (`SYLLABUS.md`, `WORKROAD.md`, `WORKTASK.md`, `WORKVALI.md`) and deterministic `Makefile` syscalls:

| Tutor Action / Mode | What the Learner Asks in Chat | Cognitive Playbook Action (`academic-tutor`) | Deterministic `Makefile` & Tracker Syscall |
| :--- | :--- | :--- | :--- |
| **1. `syllabus` (*Plan Curriculum*)** | *"Build or review my study plan for `<subject>` at level `M1 -> M3`."* | Queries mounted libraries (`sci-*`, `gov-*`, `org-uni-*`) via `query_governance_rules` (`L1`) and structures progressive modules (`M1` foundations $\rightarrow$ `M4` frontier) in `SYLLABUS.md`. | Records module milestones in **`WORKROAD.md`** and populates current module lessons as `- [ ]` items in **`WORKTASK.md`**. |
| **2. `next-lesson` (*Advance Lesson*)** | *"Start the next lesson"* or *"Explain Lesson `<id>`."* | Reads the active `Human-Stack` (`domain-<subject>:M1..M4` in `.agents/SESSION.md`), retrieves primary axioms via `citation_receipt`, and teaches the concept Socratically (`M1/M2`) or analytically (`M3/M4`). | Runs **`make task TASK="<lesson-id>"`** (marks `[/]` in `WORKTASK.md`) and **`make consult LAYER=<lib> QUERY="<topic>"`**. |
| **3. `practice-drill` (*Request Exercises*)** | *"Give me practice exercises / boundary problems on this lesson."* | Generates `AAA` problem sets (`Nominal`, `N vs N ± 1` boundary cut-points, and counter-examples) tailored to `M1..M4` **without revealing solutions upfront**. | Appends verifiable exercise checkpoints (`- [ ]`) in **`WORKVALI.md`** (or `WORKTASK.md`). |
| **4. `verify-mastery` (*Grade & Consolidate*)** | *"Check my solutions and close the lesson."* | Evaluates the learner's answers against `E3/E2` primary laws, explains any misconceptions, distills study notes into `docs/guides/<topic>.md` (`< 465` lines), and recommends upgrading `domain-<subject>:M1 -> M2` in `.agents/SESSION.md` when ready. | Marks exercises `[x]` in **`WORKVALI.md`**, runs **`make complete TASK="<lesson-id>"`**, and logs mastery progress under `## [Unreleased]` in **`CHANGELOG.md`**. |

---

## 2. Customizing Your Personal Tutor & Enriching the Open-Source Community (`/enrich` $\rightarrow$ `make promote`)

Follow these 3 rules to keep your workstation clean while evolving your study workspaces and contributing reusable pedagogical patterns upstream:

1. **Keep `$HOME` Universal for Parallel Workspaces**: Keep `~/.gemini/config/AGENTS.md` on the default universal profile (`universal-base`) so parallel Antigravity windows (work, study, personal projects) never contaminate one another; scope curriculum rules and `/academic-tutor` strictly to your `tutor-*` layer or study workspace (`.agents/`).
2. **Customize Without Losing Upstream Open-Source Updates**:
   - Add personal study rules in `templates/<tutor-id>/rules/<tutor-id>.md` or custom sections (`## My Mnemonics & Worked Proofs`) inside inherited rules, and run `make sync STRATEGY=merge` (or `make upstream-diff`) to pull new Open-Source improvements while preserving `100%` of your local sections.
3. **Share Reusable Learning Patterns with the Community**: When you craft a high-value pedagogical rule, Socratic checklist, or `sci-*`/`gov-*` study template that benefits any learner, run **`/enrich`** and **`make promote`** (`promote-from-project --create-pr`) to propose a sanitized, zero-leak PR back to the upstream Open-Source repository.
