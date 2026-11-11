---
name: review
description: "Tactical C1 read-only context-adaptive audit of the active session delta (default) or a targeted path/dimension (/review [path | docs | arch | 1:1:1 | layer | governance]) across the 4 canonical quality dimensions."
---

# Tactical & Context-Adaptive Review — `/review`

> **Purpose (`C1 — Tactical Incremental Radius, ~5–15s`)**: Quickly audit the **files modified in the current task/branch** (default when invoked as `/review` with no arguments) or a **specific target path / single dimension** (`/review <path | docs | arch | 1:1:1 | layer | governance>`) before `/continue` or commit.
> **Constructive vs. Auditing Command Boundary (`0%` Overlap)**:
> - **Design (`/architecture`)**: Constructive `Spec-First` design, orthogonal taxonomy synthesis (`X × Y`), and `1:1:1` module boundary decomposition.
> - **Orchestrate (`/governance`)**: Constructive work-tier promotions (`roadmaps/ -> WORKROAD -> WORKTASK -> CHANGELOG`), 1-hop downward delegations (`make delegate`), and RBAC/stage decisions (`make roster|decision|env-gate`).
> - **Audit (`/review` `C1` $\leftrightarrow$ `/audit` `C2`)**: Shares the exact same **4 Canonical Dimensions** and **optional selector grammar** as `/audit`, differing only in its **Radius of Action**: `/review` inspects a targeted delta or single dimension in seconds (`C1`), whereas `/audit` certifies `100%` of the repository (or `100%` of a selected dimension) in closed-world mode (`C2`).

---

## 1. Radius of Action & Invocation Modes

Check `operating_state`, `workspace_mode` (`"technical"`, `"business"`, or `"hybrid"`), and active `.agents/rules/*.md` stacks from `make status`:

| Invocation | Target Radius Inspected | When to Use |
| :--- | :--- | :--- |
| **`/review`** *(no args — default)* | **Active Session / Git Delta (`git status --short` / modified files)** | Default mid-session check before `/continue`: evaluates Dimensions 1–4 **only on files touched in the current task**. |
| **`/review <path>`** | **Specific Module, Directory, or Template Pack** | After editing a specific module (`src/zcg/capsules/codec.py`), directory (`corporate/`), or template pack (`templates/framework-stack/google-cloud-iac/`). |
| **`/review docs`** | **Dimension 1 Only (`3-Tier Docs & 5-Link Ripple`)** | After updating CLI flags, `Makefile` targets, architecture specs, or user guides. |
| **`/review arch`** | **Dimension 2 Only (`Technical Code` or `Business Ledgers`)** | After refactoring code (`technical`) or updating policies, ledgers, and `surfaces/` (`business`). |
| **`/review 1:1:1`** | **Dimension 3 Only (`Spec <-> Source <-> Test` or `Ledger <-> Policy <-> Surface`)** | After adding/modifying functions, unit tests (`Test<Module>`), security controls (`[SEC-CTRL-YYYY-NNN]`), or normative policy checklists. |
| **`/review layer`** *(or **`/review governance`***)* | **Dimension 4 Only (`Layer Manifest, RBAC, Precedence & 1-Hop Horizon`)** | When validating or aligning a `Root 0`, `domain-policy`, `department`, `squad`, `knowledge`, or `project` workspace (`governance` is accepted as a natural alias for `layer`). |

### 1.1. Context-Adaptive Stack Audit Matrix (Automatic Specialization by Active `.agents/rules/*.md`)

`/review` automatically adapts Dimensions 2 (`arch`) and 3 (`1:1:1`) to the specialization stacks projected in `.agents/rules/*.md`:

| Active Stack in `.agents/rules/*.md` | Context-Adaptive Checks Activated Automatically on the Target Radius |
| :--- | :--- |
| **`software-engineering`** & **`framework-stack/{google-cloud-iac,nist-csf-security}`** | Enforces `< 465` lines ($\le 400$ target), $M_{\text{cluster}} < 1{,}200$, `100.00%` isolated single-file unit branch coverage (`Test<Module>`), `google-cloud-iac` Cloud Run/GKE/BigQuery/IAM least-privilege contracts, `nist-csf-security` `R0..R2` capability rings, and WCAG 2.2 AA Zero-Cloud Node Cockpits. |
| **`corporate-operations`** (`business-base` / `context-stack`) | Automatically runs the 4-Step Business `1:1:1` Ledger-to-Surface verification (`ledger-surface-audit`): `corporate/ledgers/` (`[DEPT]-[TYPE]-[YYYY]-[NNN]`) $\leftrightarrow$ Business `AAA` sections in `corporate/{policies,sops}/` $\leftrightarrow$ `surfaces/{web,forms,print}/` claim/unit parity & IP/Trade-Secret Firewall. |
| **`nist-csf-security`** (`framework-stack` / `secops-mcp-guardian`) | Automatically runs the 4-Step NIST CSF 2.0 (`GV`, `ID`, `PR`, `DE`, `RS`, `RC`) control & surface verification (`nist-csf-audit`): `corporate/ledgers/security-controls.md` (`[SEC-CTRL-YYYY-NNN]`) $\leftrightarrow$ policies $\leftrightarrow$ `OWASP ASVS` / `MCP-Sec` (`PATH_CONTAINMENT_VIOLATION`) / `R0..R2` vs. `W` bot autonomy. |
| **`academic-curriculum`** (`academic-base` / `context-stack`) | Verifies `ACAD-01` (`Maintainer` vs. `Consumer` separation), `ACAD-02` (`M1..M4` Socratic progression), `SYLLABUS.md` alignment, and `WORKVALI.md` active-recall drill gates (`academic-tutor`). |
| **`scientific-methodology`** (`science-base` / `knowledge` `gov-*`, `sci-*`, `geo-*`, `org-*`) | Verifies `E3 > E2 > E1 > E0` epistemic precedence, `citation_receipt` SHA-256 digests (`0` `CITATION_DRIFT_DETECTED`), `l3_targets` links, and `.agents/telemetry/citation_stats.json` (`Q1..Q4`). |
| **Any Custom / Sovereign Pack in `.agents/{rules,skills}/`** ($N \to \infty$ Scale) | Dynamically enumerates all projected `.agents/rules/*.md` and `.agents/skills/*/SKILL.md`, resolves their transitive `template.json` `"extends"` / `stack_group` lineage (`_resolve_template_lineage_chain`), and enforces every custom `## Normative Invariants` and `## Verification & Sign-Off Gates` (`- [ ]`) checklist item. |

---

## 2. Deterministic Fast Probes (Run First on Target Radius)

Execute these deterministic probes first to establish a fast baseline on the target radius before reading prose or source files:

// delegate: flash

```bash
# 1. Workspace & layer drift digest (< 0.2s):
make status && make diff

# 2. Isolated unit branch coverage on touched module(s) (technical/hybrid mode):
venv/bin/pytest <test_file> --cov=<module_import_path> --cov-branch --cov-report=term-missing -q

# 3. Zero-residue & anti-duplication scan on touched files:
grep -rn "DEPRECATED\|@deprecated\|BACKWARD COMPAT\|# shim\|# transitional" <target_paths>
grep -rn "class.*Expanded\|class.*100Coverage\|class.*Extended\|class.*Additional\|class.*Coverage" <target_test_paths>

# 4. Unpushed commit triangulation & cross-layer version/escape sweep (when HEAD is ahead of origin/<branch>):
git diff origin/$(git branch --show-current) --stat
grep -rn "\\\\u[0-9a-fA-F]\\{4\\}" system/ templates/ layers/ 2>/dev/null || true
```

---

## 3. The 4 Canonical Audit Dimensions (Applied to Target Radius)

// delegate: flash

Evaluate only the dimensions relevant to the selected target radius and `workspace_mode`:

### 3.1 Dimension 1 — `docs`: 4-Level Documentation Cascade, 2D Geometry, `L1` Exon Readiness & 5-Link Change-Ripple
- [ ] **4-Level Top-Down Cascade (`Gateway/Contribution [README.md, CONTRIBUTING.md, SECURITY.md, docs/README.md] -> Guides -> Specs/Refs -> Templates/Skills`) & `< 465`-Line Gate**: Touched `README.md` ($\le 400$ target), root contribution/security docs, `docs/guides/*.md`, `docs/architecture/*.md`, and `docs/reference/*.md` stay strictly `< 465` lines and match actual disk trees (`find` / `ls`).
- [ ] **2D Geometry, `L1` Exon Readiness & `H1..H4` Hierarchy Cap**: Every `##` / `###` / `####` section opens with a **1-line executive lead sentence** before any table, diagram, or code block (`0` empty `L1` exons in `_extract_axiom_skeleton`), uses `###` (`H3`) subsections for multi-item mechanism catalogs, enforces a strict `H1..H4` depth cap (`0` `#####` `H5+` headings), and orders table columns `Left -> Right` (conceptual/invariant columns left, file/test pointers right).
- [ ] **Conceptual, Backtick-Aware Count, Disjoint Prefix Taxonomy & Zero Coexisting Generational Layers**: Read touched documentation tables and prose word-for-word against `constants.py` and `templates/**/template.json` (checking backticked counts `` `?N`? ``) to ensure zero retired taxonomy terms (`human-stack`, `context-stack`, `framework-stack`, `plugin-stack` only) or stale module/skill/role counts, brace-factored compound naming (`{human,context,framework,plugin}-stack`, never dangling `a/b/c-stack`), complete skill/template inventories, **`1 Skill = 1 Verb` (`0` nested CLI subcommands in `SKILL.md`)**, **zero coexisting generational layers** (superseded skills, rules, or prose removed via `[CONSOLIDATE]` + `[PRUNE]`), domain-neutral Level 3 (**Squad, Case, or Operational Unit**) framing, single-surface `antigravity-agents` guidance, and **strictly disjoint prefix taxonomies (`L0..L3` `rcap1` capsules, `E3..E0` epistemic credibility, `M1..M4` cognitive mastery, `V1..V5` manual UI validation, `C0..C3` command/audit tiers, `Pillar A..D`, `Level 1..4`)**.
- [ ] **5-Link Change-Ripple, Dual-World Command & Bidirectional Lifecycle Symmetry**: Any modified capability is synchronized across all 5 links (`1. Engine/Service Function <-> 2. CLI/Router Parser <-> 3. Makefile Recipe / Hook <-> 4. Spec Table (docs/architecture/) <-> 5. Root/Guide Docs & Parity Tests`), verifying that Link 3 (`Makefile` recipes) forwards all optional CLI flags exposed by Link 2, and that any install/claim/rename operation has its symmetric uninstall/prune inverse wired in `make sync` / `install.sh`.
- [ ] **Descriptive Link Labels, Mermaid (`flowchart TD`) & Language Purity**: 100% of relative Markdown links resolve on disk and use descriptive non-numeric labels (`len(clean_label) > 2 and not clean_label.isdigit()`, never bare `[01]` or `[§4]`), Mermaid diagrams use vertical `flowchart TD` with double-quoted node labels containing `()` or `[]`, and repository artifacts remain in 100% pure technical English.

### 3.2 Dimension 2 — `arch`: Pragmatic Code Architecture (`technical`) OR SSoT Ledgers (`business`)
- **In `technical` / `hybrid` mode**:
  - [ ] **Single-Owner Boundaries, Import Direction & Specific Exceptions**: Entrypoints/routers/CLI stay thin and delegate to domain engines/services; upstream never imports from downstream (except runtime-safe `TYPE_CHECKING` blocks); raise specific domain exceptions/error codes (never generic `Exception`); keep consumer `src/**/__init__.py` and `tests/**/__init__.py` at `0 bytes`.
  - [ ] **Bidirectional 6-Stage Structural Evolution (`Anti-Compression Escalation <-> Anti-Overengineering De-Escalation`), Shell-Wrapper Thin-Delegation (`.sh < 250` Lines $\rightarrow$ `cli_dispatcher.py`), Relational Cluster Mass ($M_{\text{cluster}}$) & `< 465`-Line Gate**: Escalate upward against defensive syntactic compression (cryptic short names, chained `.update()` packing, multi-statement `; then` shell lines, inline `python3 -c` blocks in `.sh` scripts $> 250$ lines, repeated inline blocks $\ge 2 \rightarrow$ Function, data clumps $\ge 3$ functions sharing $\ge 4$ params $\rightarrow$ Class/`@dataclass`, multi-branch `if/elif` chains $\ge 3\text{–}4 \rightarrow$ Catalog/`Protocol`, modules $> 400$ lines, flat directories $\ge 15$ modules $\rightarrow$ Stage 6 `1:1:1` Domain Subpackages, or **Relational Cluster Saturation** where $\ge 2$ coupled sibling modules $\ge 385$ lines reach $M_{\text{cluster}} \ge 1{,}200$ lines or import cross-engine `_private` helpers); **de-escalate downward against over-engineering** whenever a `Protocol`/class/catalog has only `1` concrete consumer (*Speculative Generality*), a wrapper forwards arguments `1:1` without logic (*Empty Indirection*), or multiple skills/subcommands/flags proliferate where `1` state-driven verb suffices.
  - [ ] **Data & Sibling Symmetry, 3-Regime Determinism vs. Heuristics, Bidirectional Constants, Dual Path+Content Cutover & Zero-Residue Forensics**: Enforce the **3-Regime Determinism vs. Heuristics Law** (`[P2-ARCH-DETERMINISM-VS-HEURISTIC]`: use **Structural Graph Determinism** via `_resolve_template_lineage_chain` / `extends` / `kind` / filesystem globs rather than closed-list name tuples for $N \to \infty$ template/skill scaling; use **Bounded-Contract Determinism** with `0` fuzzy numeric thresholds or substring guesses on schemas/states/authority; restrict **Discovery Heuristics** to `query_governance_rules` and `_route_novel_item`), purpose-named constants (`*_CONTRACT_REV`, `DEFAULT_*`, `MAX_*` with nominal wire strings like `"zcg-node-v1"`, never SemVer schema strings like `"1.2"` or raw slices `[:24]`), `{...}` literals, `.get()` at external boundaries vs. `d["k"]` internally, structural symmetry across sibling template packs/subpackages, 100% public docstrings & return types, zero compatibility shims/aliases/transition maps/heuristic schema normalizers or unrenamed cutover prefixes across **both directory/file paths (`find` / `rglob`) and file contents (`grep`, including test fixtures)**, and explicit **`[WIRE]` / `[CONSOLIDATE]` / `[PRUNE]`** forensics (`git log -S` + `docs/architecture/`) before removing any unreferenced or functionally superseded symbol. Capture out-of-scope smells in `BACKLOG.md` (`[BKL-NNN]`).
  - [ ] **Dual Obsolescence Radar (`Chronological Age 14d/90d/180d + Functional Absorption`) & `Q1..Q4` Citation Lifecycle**: Check `stale_proposals` (`> 14d`), modules/specs (`> 90d`), policies/templates (`> 180d`), **functional absorption obsolescence** (mechanisms `< 90d` kept alive only by self-referential tests/constants after consolidation), and `citation_lifecycle_radar` (`Q1_HOT_CORE`, `Q2_HIGH_FRICTION`, `Q3_EMERGING_NICHE`, `Q4_NORMATIVE_OBSOLESCENCE` in `.agents/telemetry/citation_stats.json`): classify aligned hot artifacts (`Q1`) for `L0/L1` hot-cache promotion, high-friction aging canons (`Q2`) for modernization, and unreferenced aging rules (`Q4`) for consolidation/repeal (`epistemic_override_allowed: false`).
- **In `business` / `hybrid` mode (`business-base` / `context-stack/*`)**:
  - [ ] **Lex Superior (`0..100`), Deontic Precedence (`1..95`), Epistemic Credibility (`E3 > E2 > E1 > E0`) & Citation Receipts**: Lower-tier packs never weaken higher-authority invariants (`Public Admin Root 0 1..2 > Public Admin Dept [Justice/Tax/Territorial] 3..4 > Enterprise Fiduciary Dept [Legal/IP] 5..9 > Corporate Root 0 10 > Functional Dept [Finance/Ops/Tech/Brand/Mkt] 15..40 > Sub-Dept/Unit/Squad 40..60 > Project 80 > Contextual Human-Stack 85..95`) or higher epistemic grades (`E3` Axiom/Law $>$ `E2` Contract/Standard $>$ `E1` Guideline $>$ `E0` Hypothesis/Draft), and external library claims verify `citation_receipt` (`<layer_id>::<rel_file>#<section_slug>@<h2_digest16>:<epistemic_grade>`) with `0` `CITATION_DRIFT_DETECTED` mismatches.
  - [ ] **Single Source of Truth (SSoT) Ledgers & IP Firewall**: Financial, pricing, and SLA figures live in one canonical table under `corporate/` or `docs/` with ISO 4217 / SI units; zero restricted formulas or internal codenames leak to external surfaces; crisis playbooks define `P0/P1/P2` SLAs.
  - [ ] **Cross-Surface Cascade (`< 465` Lines)**: Changes in `corporate/` cascade across `surfaces/{web,forms,print}/` with `0` drift.

### 3.3 Dimension 3 — `1:1:1`: Executable Test Symbiosis (`technical`) OR Normative Sign-Off (`business`)
- **In `technical` / `hybrid` mode**:
  - [ ] **Bidirectional `1:1:1` Mapping, 3-Tier Flow (`Unit -> Imp -> E2E`) & Scope**: Every executable module declares `Specification: docs/architecture/<spec>.md` and maps `1:1` to `tests/unit/**/test_<module>.*` (`1` canonical `class Test<Module>`, `0` loose top-level `test_*` functions, `0` banned `*Expanded`/`*Coverage` class suffixes, `0` duplicate method names, and `0` artificial unit test files for purely declarative DTOs/models/catalogs). Verify no real DB/subprocess/network I/O in `tests/unit/` (move to `tests/imp/`) and no mocked boundaries in `tests/imp/`.
  - [ ] **Constructor Injection, Patch-at-Consumption, Single-File `1:1:1` Isolation & Anti-Deception Gates**: Inject spec-constrained mocks in constructors; patch at the consumer lookup seam (`@patch('consumer.Dep')`, never `@patch('external.Dep')`); enforce 1-line invariant docstrings on every `test_<subject>_<scenario>_<expected>`, separated `# Arrange` / `# Act` / `# Assert` comments, `match=` on `pytest.raises`, zero blind `subprocess.run` lambdas, and `100%` single-file isolated unit branch coverage (`0` *Cross-Unit Coverage Masking*) across all 4 quadrants (*Nominal*, *`N` vs `N ± 1` Numeric, Input-Cardinality (`1-token` vs `multi-token`) & Lifecycle (`greenfield t=0` vs `brownfield N-1 -> N`) Boundaries*, *Negative-First Bipolar Guards*, *Outbound Failures*).
- **In `business` / `hybrid` mode**:
  - [ ] **Traceable IDs & Three-Part Verification**: Every normative artifact carries `[DEPT]-[TYPE]-[YYYY]-[NNN]` and contains `# Scope & Surface Target`, `# Normative Invariants`, and `# Verification & Sign-Off Gates` (`- [ ]`).

### 3.4 Dimension 4 — `layer`: Multi-Layer Topology, Manifest & 1-Hop Horizon
- [ ] **Manifest, Epistemic Grounding, Federated Libraries (`gov-*`, `sci-*`, `geo-*`, `org-*`) & Surface Binding Contracts (`zcg-node-v1` & `zcg-template-v1`)**: `system/zcg-node.json` and `templates/**/template.json` declare valid contracts, existing `rule_files` / `canonical_templates`, explicit `epistemic_grade` (`E3..E0`) / `l3_targets` pointers on `context_capsules`, and valid `local-mcp-clone -> private-mirror-remote -> public-canonical-remote` endpoints for mounted knowledge libraries.
- [ ] **Horizon, Upgrade Reconciliation, Dual-World Command Taxonomy & Projection Sync (`make status`, `make horizon`, `make diff`)**: Verify `makefile_outdated: false`, `manifest_contracts_outdated: false`, `downward_sync_needed: false`, `modified_in_project: []`, `.agents/LAYER_LINEAGE.md` parity, and `command_taxonomy` alignment (`skill_rings` across `universal-base`/`academic-base`/`business-base`/`science-base` + `workspace_layer_skills` vs. `makefile_domains` across `universal_base_local`, `business_inter_layer`, `layer_hierarchy_governance`, and `technical_and_plugin_ops`).
- [ ] **Authority, Entity Lineage (`Internal` vs `External`) & $N$-Layer Consensus Gates (`make authority`, `make env-gate`)**: Verify `layer_authority` (`authorized_emails`, `maintainer_emails`, `validator_emails`), `entity_identity` (`entity_kind`, `governing_root_id` — ensuring `UPSTREAM_HIERARCHICAL_AUTHORITY` only applies when `relationship_scope == "internal"`), `co_owning_layers` surface consensus (`RECONCILED_FLOW`, `ITERATION_REQUIRED`, `ESCALATE_TO_ROOT`, `ESCALATE_INTER_ENTITY_ROOTS`), and `git_governance` (`protected_branches`, `.github/CODEOWNERS`).

---

## 4. Output Format & Read-Only Rules

1. **Re-Read Active Rules First & Stay Read-Only**: Read `.agents/rules/*.md` before auditing; report findings without mutating files (capture non-trivial deferred items in `BACKLOG.md`).
2. **Structured Prioritized Table**: Report `Dimension (docs|arch|1:1:1|layer) | Severity (❌ Critical / ⚠️ Warning / 💡 Suggestion) | File:Line Evidence | Clean-Cutover Recommendation`.
