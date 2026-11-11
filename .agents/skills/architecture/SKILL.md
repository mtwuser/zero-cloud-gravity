---
name: architecture
description: "Constructive spec-first architectural design, orthogonal taxonomy synthesis (X × Y), 1:1:1 module boundary decomposition (M_cluster), and 5-dimension specification cascade."
---

# Architecture — Constructive Spec-First Design, Boundary Decomposition & Taxonomy Skill (`/architecture`)

> **Purpose (`Constructive Architectural Design & Specification Playbook — 0% Audit Overlap`)**: Activate `/architecture` **exclusively to design, model, synthesize orthogonal taxonomies (`X × Y`), decompose saturated module clusters ($M_{\text{cluster}} \ge 1{,}200$), and author `1:1:1` normative specifications (`Spec-First`)** before writing or moving code.
> **Auditing vs. Designing Boundary**: Never use `/architecture` to run an audit. To **audit or verify** existing architecture, module boundaries, or `corporate/` ledgers, run **`/review arch`** (`C1` tactical delta/target) or **`/audit arch`** (`C2` closed-world `100%` repository sweep).

---

## 1. Orthogonal Intersection Design Pattern (`X × Y`)

When designing framework capabilities, domain taxonomies, or multi-layer contracts, apply this 5-step synthesis pattern to discover unifying concepts (e.g., how a unified execution policy emerges from `Surface × Authority Tier` or `World Scope × Topological Role`):

### 1.1. The 5-Step Synthesis Process

Execute these 5 steps in sequence whenever two classification axes interact:

1. **Identify orthogonal dimensions**: Search for independent classification
   pairs — two axes that describe different aspects of the same system
   (e.g., *where* something renders × *how fast* it processes).
2. **Build the complete matrix**: For each pair, construct the full combination
   table. Ask: "Does each cell have a name? Is it valid? What's the reason
   for invalid cells?"
3. **Evaluate atomicity**: If the intersection defines a unit that the
   developer needs to choose or implement $\rightarrow$ formalize it with a name
   and an enum. One cell = one atomic decision.
4. **New developer test**: Would a developer unfamiliar with the framework
   understand this combination as ONE decision or $N$ separate decisions?
   If $N > 1$, there is a simplification opportunity.
5. **Impact assessment**: Does naming this intersection reduce the number
   of independent configuration choices? If yes $\rightarrow$ formalize. If the name
   doesn't reduce complexity, it's premature abstraction.

### 1.2. When to Trigger

Trigger `/architecture` whenever any of these 5 design conditions arise:

- You need to design a new subsystem, domain policy, or `1:1:1` specification from scratch (`Spec-First`).
- Two classification systems are referenced together without a unified name or require choosing values from two independent dimensions.
- A developer asks "how do I combine X with Y?" and no single answer exists, or documentation describes the same concept under different names.
- **Symmetry-Asymmetry Friction & Dual-World Command Disambiguation (`1 Skill = 1 Verb` in `SKILL.md` vs. Parameterized Flags in `Makefile`)**: When two growing mechanisms exhibit partial symmetry alongside overlapping responsibility noise (e.g., cognitive skills `SKILL.md` vs. deterministic `Makefile` syscalls, or `universal-base` local commands vs. `business-base` inter-layer governance vs. department/plugin operations), apply the Orthogonal Intersection Design Pattern to isolate their orthogonal responsibility axes (`Cognitive Protocol Plane` enforcing **`1 Skill = 1 Verb` with zero nested CLI subcommands** vs. `Deterministic Execution/RBAC Plane` accepting parameterized `make <target> VAR=val` flags).
- **`[CLUSTER_CONSOLIDATION_CANDIDATE]` Flagged by `/audit arch` (Probe E) or `/review arch`**: When $\ge 2$ coupled modules exceed `385` lines with combined **Relational Cluster Mass $M_{\text{cluster}} \ge 1{,}200$ lines** (or share `_private` helpers across peer `*_engine.py` modules), use `/architecture` (Stage 3) to design the clean `1:1:1` module decomposition before handing off physical extraction to `refactoring` (Stage 4).

### 1.3. Anti-Pattern: Premature Intersection

Verify these 3 guards before formalizing any new intersection enum or abstraction:
- Verify that at least `60%` of matrix cells represent valid, distinct runtime or governance states (otherwise the dimensions are coupled, not orthogonal).
- Confirm that an operator or developer encounters this combination in practice (`> 1` concrete consumer).
- Check that the name captures **purpose** (what it governs or solves), not just structure.

### 1.4. 3-Regime Determinism vs. Heuristics Selection Matrix

Classify every computation or routing mechanism into one of three architectural regimes so open-ended scaling ($N \to \infty$) never relies on brittle closed lists and bounded contracts never rely on fuzzy guesses:

| Architectural Regime | Problem Domain & Scaling Profile | Required Mechanism | Forbidden Anti-Pattern (`[P2-ARCH-DETERMINISM-VS-HEURISTIC]`) |
| :--- | :--- | :--- | :--- |
| **1. Structural Graph Determinism** | Open-ended extensible topologies ($N \to \infty$ custom templates, skills, layers, or subtrees). | Transitive graph walk over declarative manifest edges (`template.json` `"extends"`, `kind` / `stack_group`, `associated_global_skills` via `_resolve_template_lineage_chain`) and self-indexing filesystem globs (`.agents/{rules,skills}/`). | Hardcoding closed-list template/skill name tuples (`if tpl in ("nist-csf-security", ...)`) that blind the engine when new packs are added. |
| **2. Bounded-Contract Determinism** | Closed invariants, state machines, schemas, cryptographic receipts, and RBAC/environment gates. | Exact constant/enum set membership (`VALID_*`, `*_CONTRACT_REV`), SHA-256 `citation_receipt` verification, and deterministic precedence (`0..100`). | Fuzzy numeric thresholds (`effective_prec >= 85`), substring guessing, or silent schema normalizers/fallbacks. |
| **3. Discovery & Ranking Heuristics** | Open-vocabulary natural-language search and advisory upward promotion target suggestion. | Token-overlap / BM25 scoring (`query_governance_rules` over `rcap1` capsules) and stem/keyword routing (`_route_novel_item` in `promotion_engine.py`), always gated by Regime 1–2 validation. | Using unvalidated heuristic scores to mutate manifests, bypass RBAC, or override `Lex Superior`. |

---

## 2. Cluster Boundary & `1:1:1` Module Decomposition Design

When designing a new subpackage or resolving a `[CLUSTER_CONSOLIDATION_CANDIDATE]` ($M_{\text{cluster}} \ge 1{,}200$ lines or directory fan-out $\ge 15$ modules), model the target boundaries before touching source files:

### 2.1. Relational Cluster Decomposition Workflow

Follow these 4 design steps to produce a zero-coupling `1:1:1` module blueprint:

1. **Map the Functional Affinity Matrix**: List the public and `_private` functions across the coupled modules and group them by cohesive domain responsibility (e.g., *Blueprint Rendering* vs. *Topology Discovery*, or *Plugin Service Lifecycle* vs. *Upward Promotion*).
2. **Assign Canonical Role Suffixes**: Partition responsibilities strictly across the 4 self-indexing module tiers so peer `*_engine.py` modules never import `_private` helpers from one another:
   - `constants.py` / `catalogs.py`: Pure declarative tuples, schemas, and constant contracts (`0` runtime I/O).
   - `<domain>_helpers.py`: Shared pure parsing, validation, and rendering helpers consumed by one or more engines.
   - `<domain>_engine.py`: Core domain state transitions and business/governance logic ($\le 400$ lines target, `< 465` hard cap).
   - `tools_<domain>.py` / `cli_dispatcher.py`: Thin MCP/CLI boundary adapters that validate inputs and delegate `1:1` to `<domain>_engine.py`.
3. **Update the `1:1:1` Normative Specification Table First (`Spec-First`)**: Add or update the row in `docs/architecture/<spec>.md` (`Subpackage / Domain | Normative Section, Functional Responsibility & Key Verified Invariants | Source Module (1:1) | Unit Test Suite (1:1, Test<Module>)`) before creating the `.py` module.
4. **Hand Off to `refactoring` & `testing`**: Execute the physical extraction via `refactoring` (`Atomic Structural Cutover` with `0` compatibility shims) and verify `100.00%` single-file isolated unit branch coverage via `testing`.

---

## 3. 5-Dimension Spec-First Authoring Cascade

Whenever an architectural design introduces or modifies terminology, module boundaries, or core mechanisms, propagate the design across these **5 surfaces in strict top-down order** before resuming code implementation:

1. **Tier 3A Normative Specifications (`docs/architecture/*.md` in `technical` mode; `corporate/**/*.md` & `templates/**/rules/*.md` in `business` mode)**: Author or update the authoritative specs first (`< 465` lines), including `1:1:1` (`Spec <-> Source <-> Unit Test`) traceability tables in `technical` mode or the Three-Part Functional Verification Structure (`## Scope & Surface Target`, `## Normative Invariants`, `## Verification & Sign-Off Gates`) and `[DEPT]-[TYPE]-[YYYY]-[NNN]` ledger IDs in `business` mode.
2. **Tier 2 Human Guides & Tier 3B Reference Docs (`docs/guides/*.md`, `docs/reference/*.md`, `docs/README.md`)**: Align step-by-step operator workflows, conceptual playbooks, and domain indexes so zero contradictions exist with normative specs.
3. **Diagrams (`docs/diagrams/*.mmd` or inline Mermaid `flowchart TD`)**: Update diagram node labels (double-quoting any label containing `()` or `[]`), edges, and filenames in 100% pure English.
4. **Tier 1 Root Gateway, Templates & Agent Rules (`README.md`, `templates/**`, `.agents/rules/`)**: Synchronize root entry points, directory trees, CLI cheat-sheets, and `always_on` agent rules.
5. **Active Governance & Roadmaps (`WORKTASK.md`, `WORKROAD.md`, `BACKLOG.md`, `roadmaps/*.md`)**: Propagate new enums, invariants, dimensions, and test paths into pending roadmap phases so future tasks build on the new design.

### 3.1. Handoff to Implementation & Context-Adaptive Verification (`/review arch` & `/audit arch`)

Once the 5-Dimension Spec-First Authoring Cascade is drafted:
- Implement the code/template changes via `refactoring` and `testing`.
- Verify the result using **`/review arch`** + **`/review docs`** (`C1` tactical verification) or **`/audit arch`** (`C2` closed-world verification) alongside `make verify`.

---

## 4. Naming Governance & Self-Indexing File Taxonomy

Enforce these 5 naming invariants across all architectural artifacts:

- **Single Canonical Meaning (`1 Term = 1 Concept`)**: Each term must have exactly ONE meaning across the entire project; if a term is overloaded across contexts, coin distinct compound names immediately.
- **Purpose Over Structure**: Names must capture **purpose** (what it DOES or governs), not internal implementation structure.
- **Disjoint Prefix Taxonomies**: Keep identifier prefixes strictly disjoint (`L0..L3` `rcap1` capsules, `E3..E0` epistemic credibility, `M1..M4` cognitive mastery, `V1..V5` manual UI validation, `C0..C3` command/audit tiers, `Pillar A..D`, `Level 1..4`).
- **Brace-Factored Compound Naming (`{a,b,c}-suffix`)**: Factor shared suffixes across enumerations (`{human,context,framework,plugin}-stack`, never dangling `a/b/c-stack`).
- **Self-Indexing File Prefix/Suffix & Extension Taxonomy (`O(1)` Glob Discovery)**: Encode architectural role and reading/precedence order in filenames (`tools_<domain>.py`, `<domain>_engine.py`, `<domain>_helpers.py`, `constants.py`, `test_<stem>.py`, `NN_<topic>.md`, `layer-<NN>-<id>.md`, `WORK*.md`) and execute renames as **Atomic Structural Cutovers** across both paths and contents (`Zero-Backward Law`).
