---
name: audit
description: "Execute a deep, context-adaptive closed-world C2 audit of the entire repository (default) or a targeted dimension/path (/audit [path | docs | arch | 1:1:1 | layer | governance]) across the 4 canonical dimensions and active stack rules."
---

# Context-Adaptive Closed-World Audit — `/audit`

> **Purpose (`C2 — Convergent Closed-World Radius, 100% of Repo or Targeted Dimension`)**: Execute an exhaustive, zero-myopia, context-adaptive closed-world audit (`C2`) of **100% of the active repository** (default when invoked as `/audit` with no arguments) or a **closed-world sweep of a single dimension or path** (`/audit <path | docs | arch | 1:1:1 | layer | governance>`).
> **Constructive vs. Auditing Command Boundary (`0%` Overlap)**:
> - **Design (`/architecture`)**: Constructive `Spec-First` design, orthogonal taxonomy synthesis (`X × Y`), and `1:1:1` module boundary decomposition.
> - **Orchestrate (`/governance`)**: Constructive work-tier promotions (`roadmaps/ -> WORKROAD -> WORKTASK -> CHANGELOG`), 1-hop downward delegations (`make delegate`), and RBAC/stage decisions (`make roster|decision|env-gate`).
> - **Audit (`/review` `C1` $\leftrightarrow$ `/audit` `C2`)**: The **only** two auditing entrypoints in the ecosystem, sharing the exact same **4 Canonical Dimensions (`docs`, `arch`, `1:1:1`, `layer`)**, the exact same **optional selector grammar (`[path | docs | arch | 1:1:1 | layer | governance]`)**, and automatic adaptation to the workspace's active `.agents/rules/*.md` stacks.

---

## 1. Core Audit Principles

Enforce these 5 foundational audit principles across every pass:

1. **Repository & Stack Agnosticism**: Never assume rules or counts from another repository. Always discover the active repository's stack, manifests, and rule hierarchy first.
2. **4-Scope Rule Separation**:
   - **Scope 1 (`$HOME` Read-Only Workstation Base)**: Universal cognitive, session, and commit governance (`universal-base`).
   - **Scope 2 (General Foundational Pillars — `academic-base`, `science-base` & `business-base`)**: Universal Socratic `M1..M4` progression, scientific `1:1:1` traceability (`E3..E0`), and deontic layer governance (`0..100`).
   - **Scope 3 (Specialization Stack Packs — `{context,framework,plugin}-stack`)**: Domain, language, framework, and plugin conventions (`academic-curriculum`, `scientific-methodology`, `software-engineering`, `corporate-operations`, `google-cloud-iac`, `nist-csf-security`, and `plugin-stack/*`).
   - **Scope 4 (Repository-Local Specifications & Gates)**: Architecture specs (`docs/architecture/`), corporate ledgers (`corporate/`), domain invariants, and verification gates specific to the active repository.
3. **Modern Stack Currency, Zero-Backward Law, Atomic Structural Cutover & Zero Coexisting Generational Layers**: Always target the latest stable language/framework idioms declared by the project; reserve `"migration"` strictly for DB schemas (`alembic`) and execute code/rule/manifest reorganizations as **Atomic Structural Cutovers**, eliminating compatibility shims, aliases, transition maps, deprecated fallbacks, and functionally superseded mechanisms (*Coexisting Generational Layers*) even when `< 90` days old.
4. **4-Stage Responsibility Pipeline (`Review -> Audit -> Architecture -> Refactoring` & `OSS-Contribute`)**:
   - **Stage 1 — `/review` (`C1` Tactical Delta/Target Gate)**: Fast incremental audit of the active session/git delta + 1-hop coupled neighbors (or a single target selector).
   - **Stage 2 — `/audit` (This Skill — `C2` Closed-World Gap, Asymmetry, Over-Engineering & Cluster Detection)**: Audits 100% of the repository (or 100% of the selected dimension/path) across **5 Deterministic Probes (`Probe A..E`)**, separating **Sub-pass 1A (Pure Conceptual, Taxonomic & Symmetry Doc Isomorphism)** from **Sub-pass 1B (Persona Journeys)** and **Pass 2 (`Relational Cluster Mass` $M_{\text{cluster}}$ + Bidirectional Structural Evolution / Anti-Overengineering + Functional Obsolescence)** toward `Regime 0 (0 findings)`.
   - **Stage 3 — `/architecture` (Constructive Domain Taxonomy & Cluster Boundary Design)**: Activated when `/audit` flags taxonomic/command asymmetry or a `[CLUSTER_CONSOLIDATION_CANDIDATE]` ($M_{\text{cluster}} \ge 1{,}200$ across $\ge 2$ modules $\ge 385$ lines or cross-engine `_private` imports) to constructively design the target `1:1:1` module boundaries and spec tables before moving code.
   - **Stage 4 — `refactoring` (`1:1:1` Execution & Pruning) & `oss-contribute` (`C3` Substrate)**: `refactoring` executes physical module extraction, consolidation, or de-escalation with `100%` isolated unit coverage; `oss-contribute` runs post-`Regime 0` for empirical hot-path profiling, `PEP 7` C-accelerators, and external `OSS-to-OSS` PRs.
5. **Execution Block Until Approval**: Present structured findings and the Pre-Edit Scope Blueprint first; never mutate repository files before explicit user confirmation.

---

## 2. Audit Cadence Strategy (`C0 -> C3`): 1 Matrix of 4 Dimensions $\times$ 2 Radii of Action

Both `/review` and `/audit` evaluate the exact same **4 Canonical Dimensions (`1. docs`, `2. arch`, `3. 1:1:1`, `4. layer`)** with the exact same optional target selectors, separating strictly along **Radius of Action**:

| Tier & Cadence | Trigger / Moment | Command / Mechanism | Radius of Action & Analytical Focus |
| :--- | :--- | :--- | :--- |
| **`C0` — Reflexive (Per-Edit)** | Every file edit / turn end (`PostToolUse`, `PostInvocation`, `Stop`) | Lifecycle Hooks (`post_edit_format.py`, `post_invocation_lint.py`, `stop_verify_tests.py`) | **Single-File Radius (`< 1s`, `0` LLM tokens)**: Enforces `< 465` lines, `Specification:` header, AAA test markers, token budgets ($\le 18\text{ KB}$ / $80\text{ KB}$), and affected unit tests on modified files. |
| **`C1` — Tactical (Incremental / Target)** | Mid-session after completing a task, or when inspecting one path/dimension | **`/review [path \| docs \| arch \| 1:1:1 \| layer \| governance]`** | **Delta or Targeted Single-Dimension Radius (`~5–15s`)**: `/review` (no args) audits only the active session/git delta; `/review <selector>` tactically audits one path or dimension (`docs`, `arch`, `1:1:1`, `layer`/`governance`). |
| **`C2` — Convergent (Closed-World Gate)** | Milestone closure, deep dimension verification, or pre-release certification before `/release` | **`/audit [path \| docs \| arch \| 1:1:1 \| layer \| governance]`** | **100% Repository Closed-World Radius**: `/audit` (no args) runs all **5 Closed-World Deterministic Probes (`Probe A..E`)** and walks **Pass 1 (`docs`), Pass 2 (`arch`), Pass 3 (`1:1:1`), and Pass 4 (`layer` + `Spillover/Convergence`)** across 100% of the repo toward **`Regime 0 (0 findings)`**; `/audit <selector>` runs a closed-world 100% repo sweep focused on the chosen dimension or path. |
| **`C3` — Evolutionary (Post-`Regime 0`)** | Strictly **after** `Regime 0` is certified (`0` compliance gaps) | **`/enrich`** (`C -> B -> A`), **`/architecture` + `refactoring`**, **`oss-contribute`** (`Tier -1`) | **Cross-Layer & External Radius**: Upward rule promotion (`/enrich`), constructive architectural design (`/architecture`), or conscious C-substrate profiling & external `OSS-to-OSS` upstream PRs (`oss-contribute`). |

### 2.1. Symmetric Target Selector Matrix (`/review` `C1` vs. `/audit` `C2`)

Both `/review` and `/audit` accept the exact same optional target arguments so operators use one mental model across both radii:

| Optional Selector | `/review <selector>` (`C1` Tactical Delta / Quick Target) | `/audit <selector>` (`C2` Closed-World 100% Repository Sweep) |
| :--- | :--- | :--- |
| *(no args — default)* | Audits **Dimensions 1–4** strictly on files modified in the active session/branch (`git status --short`). | Audits **Dimensions 1–4** + **Probes A..E** across **100% of the repository universe** toward `Regime 0`. |
| **`docs`** | Checks **Dimension 1 (`docs`)** on touched documentation, guides, specs, and 5-link ripple targets. | Executes **Probe C + Pass 1 (`1A` Conceptual/Taxonomic Isomorphism + `1B` Persona Journeys)** across **100% of repository Markdown files**. |
| **`arch`** | Checks **Dimension 2 (`arch`)** on touched code modules (`technical`) or touched `corporate/` ledgers/policies (`business`). | Executes **Probes B & E ($M_{\text{cluster}}$) + Pass 2 (Architecture, Anti-Overengineering, Obsolescence & Stack Rules)** across **100% of code/ledgers**. |
| **`1:1:1`** | Checks **Dimension 3 (`1:1:1`)** on touched `Spec <-> Source <-> Unit Test` or `Ledger <-> Policy <-> Surface` triples. | Executes **Probes A & D + Pass 3 (`1:1:1` Symbiosis, `100%` isolated unit branch coverage & Business/NIST `1:1:1` gates)** across **100% of triples**. |
| **`layer`** *(or **`governance`***)* | Checks **Dimension 4 (`layer`)** on local `system/zcg-node.json`, `make status`, `make diff`, and 1-hop `make horizon`. | Executes a closed-world **Multi-Layer Topology, Manifest Contract, Deontic Precedence (`0..100`), RBAC Roster, Consensus & `Q1..Q4` Citation Audit** across all mounted layers and templates. |
| **`<path>`** | Audits **Dimensions 1–4** on the specified file, directory, or template pack (`~5–15s`). | Executes a closed-world **Probes A..E + Pass 1–3** audit of the specified subpackage, layer subtree, or template pack and all its `1:1:1` counterparts. |

---

## 3. Phase 0 — Closed-World Context, Stack & Deterministic Probe Discovery

// delegate: flash

To provide **human-grade certainty through closed-world elimination** (never heuristic attention-window sampling), Phase 0 MUST enumerate and probe the repository universe upfront and adapt to the active stacks:

### 3.1. Context-Adaptive Stack Audit Matrix (Automatic Specialization by Active `.agents/rules/*.md`)

During Phase 0, inspect `.agents/rules/*.md` and `system/zcg-node.json` (`default_stack_templates`) and automatically activate the domain-specific verification probes corresponding to every installed stack:

| Active Stack in `.agents/rules/*.md` | Context-Adaptive Checks Activated Automatically by `/audit` and `/review` |
| :--- | :--- |
| **`software-engineering`** & **`framework-stack/{google-cloud-iac,nist-csf-security}`** | **Technical `1:1:1` & Framework Architecture**: Runs AST Probes B & E ($M_{\text{cluster}} < 1{,}200$, `< 465` lines, `0` cross-engine `_private` imports), verifies `100.00%` single-file isolated unit branch coverage (`Test<Module>`, explicit `# Arrange / # Act / # Assert`), and enforces stack boundaries (`google-cloud-iac` Cloud Run/GKE/BigQuery/IAM least-privilege & Antigravity SDK contracts; `nist-csf-security` `R0..R2` vs `W` capability rings; WCAG 2.2 AA Zero-Cloud Node Cockpits). |
| **`corporate-operations`** (`business-base` / `context-stack`) | **Hexagonal Business `1:1:1` Ledger-to-Surface Audit (Auto-Invokes `ledger-surface-audit`)**: (1) Inventories `corporate/ledgers/` (`[DEPT]-[TYPE]-[YYYY]-[NNN]`, `ISO 4217` currencies, `SI`/`ISO` units, confidentiality tiers); (2) Verifies Business `AAA` sections (`## Scope & Surface Target`, `## Normative Invariants`, `## Verification & Sign-Off Gates`) and `> **Ledger Grounding**:` in `corporate/{policies,sops}/`; (3) Sweeps `surfaces/{web,forms,print}/` for unbacked claims, rounding drift, WCAG contrast, and print bleed/DPI; (4) Verifies the IP & Trade-Secret Firewall (`<IP-ID>` / `<TS-ID>`). |
| **`nist-csf-security`** (`framework-stack` / `secops-mcp-guardian`) | **NIST CSF 2.0 & 2-Plane Security Audit (Auto-Invokes `nist-csf-audit`)**: (1) Verifies every security policy maps to NIST CSF 2.0 (`GV`, `ID`, `PR`, `DE`, `RS`, `RC`) and cites `[SEC-CTRL-YYYY-NNN]` in `corporate/ledgers/security-controls.md`; (2) Confirms automated check or sign-off evidence per control; (3) Scans `surfaces/**` and `.agents/proposals/**` for secret/IP leaks; (4) Audits `OWASP ASVS` boundary validation, non-root `Dockerfile`, `MCP-Sec` path containment (`PATH_CONTAINMENT_VIOLATION`), and `R0..R2` (Autonomous) vs. `W` (Actionable) bot leases. |
| **`academic-curriculum`** (`academic-base` / `context-stack`) | **Socratic `M1..M4` Curriculum & Mastery Audit (`academic-tutor`)**: Verifies `ACAD-01` (`Maintainer` `E2/E3` rigor vs. `Consumer` `M1..M4` Socratic adaptation), `ACAD-02` (`M1 -> M4` delivery table), `SYLLABUS.md` / `WORKROAD.md` module progression, and `WORKVALI.md` active-recall drill sign-off gates (`verify-mastery` before `make complete`). |
| **`scientific-methodology`** (`science-base` / `knowledge` `gov-*`, `sci-*`, `geo-*`, `org-*`) | **Epistemic Credibility (`E3..E0`), Citation Receipts & `Q1..Q4` Radar**: Enforces `E3 > E2 > E1 > E0` (`0` `EPISTEMIC_PRECEDENCE_VIOLATION`), verifies cryptographic `citation_receipt` digests (`<layer_id>::<rel_file>#<slug>@<digest16>:<grade>`, `0` `CITATION_DRIFT_DETECTED`), checks `l3_targets` substrate links, and evaluates `.agents/telemetry/citation_stats.json` (`Q1..Q4`). |
| **Any Custom / Sovereign Pack in `.agents/{rules,skills}/`** ($N \to \infty$ Scale) | **Dynamic Lineage & Custom Invariant Audit**: Enumerates all projected `.agents/rules/*.md` and `.agents/skills/*/SKILL.md` on disk, traces their transitive `template.json` `"extends"` / `stack_group` lineage (`_resolve_template_lineage_chain`) to the 4 base rings, and audits every custom `## Normative Invariants` and `## Verification & Sign-Off Gates` (`- [ ]`) section without requiring hardcoded table entries. |

### 3.2. Closed-World Enumeration & The 5 Deterministic Probes (`Probe A..E`)

Execute these 3 discovery and probe steps across the target radius (`100%` of repo by default):

1. **Discover Stack, Operating State, Workspace Mode & Toolchain**:
   - Run `make status` (or `zcg status`) and inspect project manifests (`system/zcg-node.json`, `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `Makefile`, `Dockerfile`, CI workflows) to determine `operating_state` (`"oss-readonly-appliance"`, `"oss-dev"`, `"corporate-root"`, `"domain-policy"`, `"department"`, `"squad"`, or `"project"`), `workspace_mode` (`"business"`, `"technical"`, or `"hybrid"`), `command_tiers`, target language versions, linters, type-checkers, and test runners.
2. **Classify Active Rules by Scope & Enumerate 100% of the File Universe**:
   - Read `.agents/rules/*.md`, `.agents/LAYER_LINEAGE.md`, and `docs/architecture/*.md` (or `corporate/**/*.md`).
   - Enumerate all root community/governance files (`README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `ACCESSIBILITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`), `docs/**`, `templates/**`, `scripts/**`, and `tests/**` so zero files are omitted from terminology, link, or parity scans.
   - Separate **generic inherited rules** (`universal-base`, `academic-base`, `science-base`, `business-base`) from **stack-specific rules** (`context-stack/*`, `framework-stack/*`, `plugin-stack/*`) and **repository-local specs**; flag any leak where repository-local counts or single-stack literals contaminate a generic rule or skill.
3. **Execute the 5 Closed-World Deterministic Probes (`Probe A..E`)**:
   - **Probe A — Live Verification & Host Audit Suite**: Run `make verify` (or `make doctor` / `make diff`) **AND** live workstation/environment audit scripts (`NO_COLOR=1 ./audit.sh`, `./scripts/audit-global-config.sh` when applicable) from the active workspace to catch cross-clone or environment-boundary false positives immediately.
   - **Probe B — Bidirectional AST Symbol, Constant, Docstring & 3-Regime Determinism Graph**: Parse all production and test modules via AST to verify: (i) 100% explicit return annotations and 100% docstrings on public functions/methods (`not name.startswith("_") or name == "__init__"`), (ii) zero `.update(k=v)` keyword packing or raw integer slices (`> 2`), (iii) **bidirectional constant wiring** (every constant in `constants.py` / `catalogs.py` is referenced by a consumer module or test, and every policy tuple is disjoint/consistent), and (iv) **3-Regime Determinism vs. Heuristics compliance (`[P2-ARCH-DETERMINISM-VS-HEURISTIC]`)**: verify that open-ended template/skill/layer scaling ($N \to \infty$) uses transitive graph resolution (`_resolve_template_lineage_chain` over `extends` / `stack_group`) instead of hardcoded closed-set name tuples, bounded contracts (`schema_version`, `precedence`, `is_tutor`, `workspace_mode`, RBAC) use exact contract checks instead of numeric threshold/substring guesses, and heuristics remain confined to open-vocabulary search (`query_governance_rules`) and advisory promotion routing (`_route_novel_item`).
   - **Probe C — 5-Link Change-Ripple, Dual-World Command & Bidirectional Lifecycle Symmetry Matrix**:
     - **(i) 5-Link Ripple & Flag Parity**: For every CLI subcommand, Makefile target, or engine capability, verify parity across all **5 ripple links** (`1. Engine Function <-> 2. CLI Parser <-> 3. Makefile Recipe / Hook <-> 4. Normative Spec Table (docs/architecture/01..NN) <-> 5. Root/Guide Docs & Parity Tests`), including **Parameter & Optional Flag Signature Parity between Link 2 (`CLI Parser`) and Link 3 (`Makefile Recipe`)**.
     - **(ii) Dual-World Command & Taxonomy Symmetry (`1 Skill = 1 Verb` in `SKILL.md` vs. Flags in `Makefile`)**: Verify that `World 1` skills enforce **`1 Skill = 1 Verb` (`0` nested CLI subcommands in `SKILL.md`)** while parameterized flags (`VAR=val`) reside in `World 2` (`Makefile`), and verify `1:1` set equality across `BASE_SKILL_TAXONOMY`, `templates/**/template.json` (`associated_global_skills`), and disk `skills/*/SKILL.md` directories.
     - **(iii) Bidirectional Lifecycle Symmetry (`Action <-> Symmetric Inverse Prune`)**: Verify that every mutating installation, promotion, or claim operation (`make sync TEMPLATE=<plugin>`, `set-global-profile`, `make task`, or skill/rule consolidation) has a verified symmetric inverse (`Clean Uninstall / Prune` in `workspace_bootstrapper.py` and `install.sh`, `make complete` + Zero-Clutter deletion) so retired or uninstalled artifacts never linger in `.agents/` or `$HOME`.
   - **Probe D — `1:1:1` Spec Table Completeness**: Verify that every specification in `docs/architecture/01..NN` (`< 465` lines) contains an explicit `1:1:1` traceability table and that every referenced source and test file exists on disk.
   - **Probe E — Relational Cluster Mass ($M_{\text{cluster}}$) & Cross-Module Coupling Graph**: Parse the intra-package AST import graph (excluding declarative `constants.py` / `catalogs.py`) to compute each module's individual load $L(f)$, its coupled neighbor set $G$, its **Relational Cluster Mass $M_{\text{cluster}}(G) = L(f) + \sum_{g \in G} L(g)$**, and its cross-module `_private` symbol imports. Flag a **`[CLUSTER_CONSOLIDATION_CANDIDATE]`** whenever: (i) a peer `*_engine.py` module imports `_private` helpers from another `*_engine.py` module (instead of `*_helpers.py`), or (ii) $\ge 2$ coupled modules in $G$ both exceed the **Soft Compression Threshold ($L(f) \ge 385$ lines)** with $M_{\text{cluster}}(G) \ge 1{,}200$ lines, signaling a latent sub-domain that should be consolidated into a dedicated `1:1:1` module.

---

## 4. Phase 1 — Pass 1: Conceptual Coherence, Symmetry, Human Persona Journeys & 4-Perspective Lifecycle Matrix

Evaluate the repository along **two orthogonal axes**:
1. **Horizontal Technical Lifecycle Matrix (4 Perspectives)** — how every rule or component behaves across setup, runtime, testing, and federation.
2. **Vertical Human Persona Journeys (`Human <-> AI <-> Technology` Unity)** — how real human archetypes experience the repository from entry point (`README.md` / CLI) to day-2 operations.

### 4.1 Horizontal 4-Perspective Lifecycle Matrix

Verify every repository flow across four lifecycle stages from initial scaffolding to multi-layer federation:

| Perspective | Question to Verify Across Every Flow |
| :--- | :--- |
| **1. Setup / Bootstrap / Scaffolding** | Do initializers, templates, manifests, and environment setup scripts materialize files and paths in the exact locations expected at runtime? |
| **2. Runtime / Execution / Skills / Hooks** | Do runtime modules, CLI entrypoints, lifecycle hooks, and agent skills invoke the current commands, flags, and paths without compatibility fallbacks? |
| **3. Verification / Testing / Gates** | Do automated linters, parity gates, and tests actually exercise the real runtime structure (e.g., class-indented methods, multi-channel guards, isolated unit coverage)? |
| **4. Federation / Integration / Extrapolation** | Do cross-layer interactions, MCP contracts, and shared templates remain 100% extrapolable without leaking local repository assumptions? |

### 4.2 Vertical Human Persona & Use-Case Journey Matrix (`Human <-> AI <-> Technology`)

Identify the concrete human archetypes served by the repository and simulate each persona's end-to-end journey from first contact to completion:

| Human Archetype (`Persona`) | End-to-End Journey to Simulate & Validate |
| :--- | :--- |
| **P1. Individual / First-Time User** | Clones the repository, reads `README.md` Quick-Start, runs initial setup/bootstrap, and executes the health/audit command. Verify zero surprise overwrites, zero false-positive drift warnings across supported profiles, and clear next steps. |
| **P2. Organizational / Root-0 Adopter** | Forks or bootstraps the top-level organizational/domain workspace (`Root 0`), configures authority and upstream lineage, and follows the step-by-step guide in `docs/guides/`. Verify that every documented CLI command and flag in the guide executes verbatim without error. |
| **P3. Department / Operational Unit Integrator** | Inherits from `Root 0` (`--parent-dir` or subtree), scaffolds specialization packs (`context-stack`, `framework-stack`, `plugin-stack`), and uses generated `Makefile` / CLI ergonomics (`make sync`, `make diff`, `make promote`) for 1-hop upward/downward flows. |
| **P4. Consumer Project Developer & Agent** | Applies templates to a consumer project repository, works under active guardrails/hooks, runs tests, and receives actionable remediation whenever a guardrail blocks an operation. |
| **P5. Upstream Maintainer / Operator** | Runs full verification (`make verify`), inspects diagnostics, and prepares releases (`/release`) with zero cross-tier or private identifier leaks. |

### 4.3 Pass 1 Checklist

Verify all 9 conceptual, geometric, taxonomic, and symmetry invariants across the 4-level documentation cascade:

- [ ] **4-Level Top-Down Documentation Cascade (`1. Gateway & Contribution [README.md, CONTRIBUTING.md, SECURITY.md, ACCESSIBILITY.md, CODE_OF_CONDUCT.md, docs/README.md, .github/] -> 2. Human Guides [docs/guides/*] -> 3. Normative Specs & References [docs/architecture/*, docs/reference/*] -> 4. Templates & Skills [templates/**/README.md, rules/*.md, SKILL.md]`)**: Verify directory trees against disk (`find`/`ls`), descriptive non-numeric Markdown link labels (`len(clean_label) > 2 and not clean_label.isdigit()`), relative links (`test -f`), CLI flag tables, and `< 465`-line modularity across all 4 documentation levels.
- [ ] **2D Geometry, `L1` Exon Readiness & `H1..H4` Hierarchy Cap**: Confirm that every `##` / `###` / `####` section opens with a **1-line executive lead sentence** before any table, diagram, or code block (`0` empty `L1` exons via `_extract_axiom_skeleton`), uses `###` (`H3`) subsections for multi-item mechanism catalogs, enforces a strict `H1..H4` depth cap (`0` `#####` `H5+` headings), uses vertical `flowchart TD` Mermaid diagrams, and orders table columns `Left -> Right` (conceptual/invariant columns left, file/test pointers right).
- [ ] **Conceptual & Semantic Documentation Reading Pass (`Concept-to-Code, Backtick-Aware Count & Disjoint Prefix Taxonomy Isomorphism`)**: Read prose tables and conceptual explanations word-for-word against the live codebase (`constants.py`, `templates/**/template.json`, `.agents/skills/*/SKILL.md`) using backtick-aware count patterns (`` `?N`? ``) to verify: (1) zero retired taxonomy terms (`VALID_TEMPLATE_KINDS`: strictly `human-stack`, `context-stack`, `framework-stack`, `plugin-stack`), brace-factored compound naming (`{human,context,framework,plugin}-stack` over dangling `a/b/c-stack`), or stale backticked module/skill/role counts across `CONTRIBUTING.md`, `SECURITY.md`, and `docs/README.md`, (2) complete **26-Skill Matrix** across the 4 Universal Human-AI Bases (`human-stack`: `8` global universal verbs) + 3 Specialization Stack Tiers (`context-stack`: `7`, `framework-stack`: `7`, `plugin-stack`: `4`), (3) domain-neutral Level 3 descriptions (**Squad, Case, Research Study, or Operational Unit**), (4) single-surface **Antigravity 2.0 (`antigravity-agents`)** workspace execution, and (5) **strictly disjoint prefix taxonomies (`L0..L3` `rcap1` capsules, `E3..E0` epistemic credibility, `M1..M4` cognitive mastery, `V1..V5` manual UI validation, `C0..C3` command/audit tiers, `Pillar A..D`, `Level 1..4`)** plus `epistemic_grade` / `l3_targets` grounding.
- [ ] **Sibling-Pack & Subpackage Structural Symmetry (`Asymmetry Justification Gate`)**: Verify that sibling template packs within the same stack (`human-stack`, `context-stack`, `framework-stack`, `plugin-stack`) and sibling subpackages (`core/`, `capsules/`, `mcp_node/`, `governance/`) share uniform manifest schemas, directory geometry, and governance contracts unless an intentional domain asymmetry is explicitly justified in `docs/architecture/`.
- [ ] **Zero Coexisting Generational Layers (`Functional Absorption & Superseded-Mechanism Obsolescence`)**: Verify that whenever a newer rule, skill, or architectural mechanism consolidates or absorbs an earlier one, the superseded mechanism is completely removed (`[CONSOLIDATE]` + `[PRUNE]`) across `skills/`, `templates/`, `constants.py`, and `docs/` rather than left alive as a parallel "internal rulebook", redundant paragraph, or overlapping subcommand — even if `< 90` days old and still referenced by tests.
- [ ] **Verbatim Human Walkthrough Parity**: Verify that every CLI command and flag sequence shown in `README.md` and `docs/guides/` matches the actual parser options and succeeds end-to-end.
- [ ] **Modern Stack Currency**: Verify that docs, rules, templates, and code use the target modern stack version consistently (zero outdated version ranges or superseded typing syntax).
- [ ] **Zero-Backward Law & Dual Path+Content Atomic Structural Cutover Scan**: Confirm zero `@deprecated` markers, compatibility aliases (`OldName = NewName`), in-engine transition maps, heuristic schema normalizers, retired hook tool args, unrenamed post-cutover dict keys/test fixtures, retired directory paths (`find`/`rglob` across `templates/*`, `skills/*`, `.agents/*`), dual CLI flags, or dead transition branches.
- [ ] **Generic vs. Local Rule Purity & Outbound Non-Restriction Check**: Confirm that reusable base rules (`science-base`, `software-engineering`) and shared skills contain zero hardcoded counts or assumptions tied to a single repository, and that tightening a rule in Perspective A does not restrict valid outbound workflows in Perspective B.

Record all findings in a structured table using **descriptive domain-slugged IDs (`[P1-DOCS-<slug>]`, `[P1-LAYER-<slug>]`)** (never generic `[P1-01]` counters that look identical across audits) with severity, conflicting perspectives, exact `file:line` evidence, and clean-cutover remediation.

---

## 5. Phase 2 — Pass 2: Pragmatic Technical Architecture, Anti-Overengineering & Obsolescence (`technical`) OR Ledger & Topology Consolidation (`business`)

Once conceptual and normative requirements from Pass 1 are aligned, audit their implementation according to `workspace_mode`:
- **In `business` mode (`Root 0` / `Department` / `business-base` / `context-stack/*`)**: Audit (1) **Single Source of Truth (SSoT) Ledger & Corpus Consolidation** (`corporate/` tables and modular `docs/` vs. prose duplication), (2) **Full Deontic Precedence (`1..95`: Public-Admin `Root 0` & Depts `1..4` $\rightarrow$ Enterprise `Root 0` & Depts/Units `5..80` $\rightarrow$ Contextual `Human-Stack` `85..95`) & Surface Binding Coverage**, (3) **Cross-Surface Cascade (`surfaces/{web,forms,print}/`) & `< 465`-Line Modularity**, and (4) **IP Firewall & Crisis Escalation SLAs (`P0/P1/P2`)**.
- **In `technical` or `hybrid` mode (`software-engineering` / `framework-stack/*` / `plugin-stack/*`)**, audit the **code representation** following the **Pre-Edit Reading Priority (`1. Guides/Specs -> 2. Tests [E2E -> Imp -> Unit] -> 3. Source Code`)**:

1. **Floor-Version Security & Stdlib Compliance Gate**:
   - Verify the code uses modern, secure-by-default idioms of the declared language floor version (`requires-python`) and standard library primitives (`hashlib.file_digest`, `stat.S_IWUSR`, `Path.is_relative_to`) over deprecated or superseded patterns. (Keep deep hot-path profiling, optional `PEP 7` C-accelerators, and external `OSS-to-OSS` upstream PRs strictly separated in the conscious `oss-contribute` workflow.)
2. **Bidirectional Structural Evolution Ladder (`Anti-Compression Escalation <-> Anti-Overengineering De-Escalation`) & Data Symmetry**:
   - **Upward Escalation (Against Under-Engineering & Syntactic Compression)**: Prefer pure functions for stateless transformations, but escalate deterministically when code or shell scripts exhibit defensive syntactic compression (cryptic short identifiers, chained `.update()` packing, multi-statement `; then` Bash lines, or inline `python3 -c` blocks in `.sh` scripts $> 250$ lines) or structural data asymmetry (mixing `.get()` and `d["k"]` on the same internal dict, inline schema versions like `"1.2"`, or raw numeric slices like `[:24]`): extract a **Function** when an inline block repeats $\ge 2$ times; extract a **Class / `@dataclass`** when $\ge 3$ functions share $\ge 4$ context parameters (*Data Clump*); use a **Declarative Catalog (`dict`) or `Protocol` Polymorphism** when `if/elif` chains branch across $\ge 3$–$4$ variants; extract a **`1:1:1` Sub-Module** (or `cli_dispatcher.py` for `.sh` entrypoints $> 250$ lines / $> 5$ subcommands) when a file crosses `400` lines; and group into **`1:1:1` Bounded-Domain Subpackages (`3–8` modules/subpackage)** when a directory reaches $\ge 15$ modules.
   - **Downward De-Escalation (Anti-Overengineering & Speculative Generality Gate)**: Actively flag and collapse premature abstractions down the ladder whenever: (i) a `Protocol`, abstract base class, strategy catalog, or factory has only **`1` concrete consumer/implementation** and zero multi-variant branching (*Speculative Generality* $\rightarrow$ collapse into a direct function or constant), (ii) a wrapper function, middleman class, or shell shim forwards arguments `1:1` without adding validation, boundary translation, or domain logic (*Empty Pass-Through Indirection*), or (iii) multiple skills, nested subcommands, or configuration flags proliferate where `1` state-driven verb (`1 Skill = 1 Verb`) or canonical convention solves `100%` of real persona journeys.
3. **Modularity, Relational Cluster Mass ($M_{\text{cluster}}$), Directory Fan-Out (`< 15` Modules/Dir), File Size (`< 465` Lines) & Dual Obsolescence Radar (`Chronological Age + Functional Absorption`)**:
   - Evaluate individual file size ($< 465$ lines, target $\le 400$), **Directory Fan-Out ($< 15$ `.py` modules per directory $\rightarrow$ group into $3\text{--}8$-module domain subpackages mirrored `1:1:1` across `tests/unit/` and `docs/architecture/`)**, and **Probe E's Relational Cluster Mass ($M_{\text{cluster}}(G) = \sum_{f \in G} L(f)$)**: when $\ge 2$ coupled modules in a functional cluster exceed `385` lines with $M_{\text{cluster}} \ge 1{,}200$ or share `_private` helpers across peer engines (`*_engine.py`), propose consolidating the shared responsibility into a dedicated `1:1:1` module (via `architecture` $\rightarrow$ `refactoring`).
   - **Dual Obsolescence Radar**: Evaluate both **(a) Chronological Age** (`> 14d` for staged `.agents/proposals/**` via `stale_proposals` in `make status`, `> 90d` for code/tests/`docs/architecture/`, `> 180d` for `corporate/` and `templates/`, and `Q1..Q4` citation telemetry) AND **(b) Functional Absorption Obsolescence (`< 90d` & `> 0` AST refs)**: inspect recent consolidations to ensure helpers, constants, or skills whose responsibility was absorbed into a unified mechanism are not kept artificially alive solely by self-referential tests or catalog entries.
4. **Strict Typing, Public Docstrings & Forensic Intent Resolution (`[WIRE]` vs. `[CONSOLIDATE]` vs. `[PRUNE]`)**:
   - Verify explicit parameter and return types on 100% of functions/methods, 1-line docstrings on 100% of public functions/methods, specific domain exceptions/error codes, and zero linter or type-checker warnings.
   - **Never prune an unreferenced or superseded constant, helper, skill, or test by reflex**: inspect `git log -S <symbol> -p` and `docs/architecture/` first and classify it explicitly as **`[WIRE]`** (*unconnected design intent* $\rightarrow$ wire into its consumer engine and add bipolar tests), **`[CONSOLIDATE]`** (*duplicate SSoT or absorbed capability* $\rightarrow$ merge 100% of unique invariants into the canonical mechanism first), or **`[PRUNE]`** (*proven obsolete residue with zero unique invariants left* $\rightarrow$ remove cleanly along with its prune hook in `install.sh` / `make sync`).

Record all technical improvements in a structured table using **descriptive domain-slugged IDs (`[P2-ARCH-<slug>]`)** (and **`[P3-111-<slug>]`** in Pass 3) with `file:line` references, concrete refactoring actions, and a **`C2 -> C1` Self-Hardening Ratchet** (wiring any newly discovered check asymmetry into `make verify` / `test_repo_parity_gates.py` so `C1` catches it automatically on future edits).

---

## 6. Phase 3 — Pass 3: `1:1:1` Symbiosis (`Spec <-> Source <-> Test` in `technical` mode; `Policy <-> Ledger <-> Sign-Off Gate` in `business` mode)

Audit the `1:1:1` alignment between normative specifications, source modules, and test suites:

- **In `business` mode (`Root 0` / `Department`)**: Verify that every normative policy and corporate ledger (`corporate/**/*.md`, `templates/**/rules/*.md`, `docs/**/*.md`) maintains `1:1:1` alignment between (1) **Traceable Artifact & Ledger IDs (`[DEPT]-[TYPE]-[YYYY]-[NNN]`)**, (2) **Three-Part Functional Verification Structure** (`# Scope & Surface Target`, `# Normative Invariants`, `# Verification & Sign-Off Gates`), and (3) **Zero-Drift Layer Sync (`make diff` & `make horizon`)**.
- **In `technical` or `hybrid` mode**, audit the alignment between **Normative Specifications**, **Executable Source Modules**, and **Unit Test Suites** so tests serve as self-documenting executable specifications for both **Agent** and **Human**:

1. **Level 1 — Bidirectional `1:1:1` Specification Table (`docs/architecture/<spec>.md`)**:
   - Every executable source module declares `Specification: docs/architecture/<spec>.md`.
   - Every architecture spec (`< 465` lines) maintains a **Human-First `1:1:1` table** placing conceptual and functional responsibility columns on the **left** (visible without horizontal scrolling) and file pointers on the **right** (`Subpackage / Domain | Normative Section, Functional Responsibility & Key Verified Invariants | Source Module (1:1) | Unit Test Suite (1:1, Test<Module>)`).
2. **Level 2 — Single Canonical Test Container per File (`Test<Module>`)**:
   - Every `1:1` test file (`tests/unit/**/test_<module>.*` or `<module>.test.*`) encapsulates its tests inside **one** canonical class/suite (`class Test<Module>` / `describe('<Module>')`) whose docstring/header links back to the source module and specification.
3. **Level 3 — Self-Documenting Behavioral Test Names + 1-Line Invariant Docstrings**:
   - **Test Method Name (`test_<subject>_<scenario_or_condition>_<expected_outcome>`)**: Reads as a natural-language functional proposition for human scanning.
   - **1-Line Invariant Docstring**: States *why* the test exists — the normative invariant, security pole, or boundary cut-point (`N` vs `N ± 1`) proven — eliminating the need for noisy inline narrative comments.
   - **Explicit AAA, Single-File `1:1:1` Isolated Coverage & Anti-Deception Gates**: Separate `# Arrange`, `# Act`, and `# Assert` comments, `100.00%` statement and branch coverage of each `<mod>.py` when running its `1:1:1` `test_<mod>.py` in strict single-file isolation (`0` *Cross-Unit Coverage Masking*), exact `N` vs `N ± 1` boundary cut-points, bipolar guard verification (negative pole first, positive pole second), explicit error matching (`match=`), and zero blind boundary/subprocess mocks.
4. **Level 4 — Bidirectional 3-Tier Test Flow (`E2E <-> Imp <-> Unit`), `imp` Terminology & Zero-Dependency Mutation Probes**:
   - **Bidirectional Asymmetry**: Read, deduce cases, and validate **Top-Down (`E2E -> Imp -> Unit`)**; author, isolate coverage, and execute **Bottom-Up (`Unit -> Imp -> E2E`)** so `tests/unit/` achieves 100% isolated branch coverage first without higher-tier masking.
   - **`tests/e2e/`**: Human persona journeys and multi-step vertical workflows catching cross-perspective/outbound regressions.
   - **`tests/imp/` (Implementation Tests — never `int`)**: Real internal boundary implementation (CLI/stdio/IPC/DB/FS) and `Spec <-> Code <-> Doc` parity gates (named `imp` to avoid `int` keyword collisions and to distinguish internal component *implementation* from production *integration*).
   - **`tests/unit/`**: `1:1` algorithmic exhaustiveness across all 4 quadrants (*Nominal*, *Exact `N` vs `N ± 1` Numeric, Input-Cardinality (`1-token` vs. `multi-token` natural queries) & Lifecycle (`greenfield t=0` vs. `brownfield N-1 -> N` upgrade with non-ASCII UTF-8 payloads, explicit `os.utime` offsets, and post-reap/reconcile disk & tracker sterility assertions) Boundaries*, *Bipolar Guard Poles*, and *Outbound/Hostile Environment Failures*).
   - **Zero-Dependency Mutation Probe Loop (`Mutant Probe -> Outbound Survivor Check -> Test Materialization`)**: Probe critical conditions, filter sets, and default parameters with adversarial mutations (`<` $\leftrightarrow$ `<=`, omitted filter items, non-default role/flag values); whenever a mutant survives across `Unit` / `Imp` / `E2E`, materialize the missing case in its respective `Test<Module>` suite.

---

## 7. Phase 4 — Scale & Governance Spillover Gate (`WORKROAD` / `WORKTASK` / `BACKLOG`)

Before executing fixes, evaluate the total approved scope to prevent rushed execution or mid-audit context loss:

| Regime | Threshold | Mandatory Orchestration Flow |
| :--- | :--- | :--- |
| **Regime 0 — Closed-World Convergence (`0` Findings)** | All 5 Phase-0 probes and Pass 1–3 matrices return **`0` discrepancies** | 1. **Anti-Searcher-Bias Rule**: Never invent cosmetic churn, artificial refactors, or unnecessary deletions when all closed-world invariants pass.<br>2. Present the **Step-by-Step Closed-World Elimination Table (`Surface Checked -> Invariant Verified -> Status: ✅ 0 Discrepancies`)**.<br>3. Declare **`CONVERGENCE REACHED (0 findings)`** so the human operator has complete, auditable certainty that the repository is ready for commit or `/release`. |
| **Regime A — Atomic In-Session Execution** | $1\text{–}15$ cohesive findings completable within the current session with 100% verification | 1. Present the **Master Audit Plan** with a Pre-Edit Scope Blueprint (and `[WIRE]` / `[CONSOLIDATE]` / `[PRUNE]` classification for any unreferenced or superseded symbols).<br>2. Upon user approval, execute in ordered batches (`P0 Runtime/Hooks` $\rightarrow$ `P1 Rules/Skills` $\rightarrow$ `P2 Docs/Templates` $\rightarrow$ `P3 1:1:1 Tests & Gates`), walking all **5 ripple links** on every change.<br>3. Run full verification (`make verify` + Phase-0 probes) after execution to confirm **`0` residual findings** in the same turn, then close via `/continue`. |
| **Regime B — Multi-Phase Governance Spillover** | $> 15$ findings, cross-cutting architectural refactors, or multi-session scope | 1. Crystallize the full audit blueprint into `roadmaps/audit_<YYYY_MM_DD>.md`.<br>2. Register the ordered audit phases (`RA.1`, `RA.2`, ...) in `WORKROAD.md` and capture independent backlog items in `BACKLOG.md`.<br>3. Promote **only the first phase (`RA.1` $\rightarrow$ `T1`)** into `WORKTASK.md` per `/continue` (§2.6) and `/governance`.<br>4. Execute and verify `T1` atomically, then checkpoint via `/continue` so zero findings are ever left half-done across sessions. |
