---
epistemic_grade: E1
---

# Guide 07 — Act IV (Weaving Networks): Inter-Node HR/B2B Links, `19`-Pack / `17`-Skill Matrix & Federated Workflows

> **Cross-Network Architect & Operator Playbook — Compositional Journey Step 7 of 8 (Tier 2 Progressive Disclosure)**
>
> With your **Personal Constellation** (**[`Guides 01–03`](01_personal_workstation_and_day0_setup.md)**), **Public Knowledge Corpora** (**[`Guide 04`](04_scientific_and_public_knowledge_corpora.md)**), and **Enterprise Hierarchy** (**[`Guides 05–06`](05_enterprise_root_and_organizational_scales.md)**) all running cleanly on your workstation, connect `<persona>-work (:8787)` and `corp-alpha-root (:8710)` via **minimal-disclosure HR/B2B links**, and reference the complete **`Pillar A..D` context architecture, `17`-skill catalog, `Cases 1–7` progression, and `12`-case flow matrix**. Final synthesis: **[`Guide 08` Network of Networks & Distributed Isomorphism](08_network_of_networks_and_distributed_topology.md)**.

---

## 1. Linking Personal (`<persona>-work`) & Enterprise (`corp-alpha-*`) Nodes Without Merging Repos

Instead of copying repositories or over-disclosing personal data when applying for roles or delivering B2B engagements, `<persona>-work` uses declarative **`zcg link` / `zcg unlink`** (`system/zcg-node.json -> linked_nodes`) paired with **`RolePayloadProjector`** ([`src/zcg/platform/projection.py`](../../src/zcg/platform/projection.py)):

| Exchange Stage (`ExchangeStage`) | Declarative Link Relation | Allowed Fields Crossed | Blocked Private Fields (`0` Over-Disclosure) |
| :--- | :--- | :--- | :--- |
| **`CANDIDATE_SELECTION`** | `hr-process` $\rightarrow$ `org-alpha` (`:8720`) | `candidate_handle`, `target_role`, `verified_skills`, `portfolio_links`, `availability_window` | Government ID, tax/SSN numbers, bank IBAN, home address, private salary floor, medical data |
| **`DAY_ONE_ONBOARDING`** | `hr-process` $\rightarrow$ `corp-alpha-root` (`:8710`) | Selection fields + `legal_full_name`, `tax_identifier`, `payroll_iban`, `emergency_contact` | Unrelated `venture/*` IP branches, other `opportunity/*` applications, personal `~/<persona>-profile` configs |
| **`B2B_ENGAGEMENT`** | `b2b-collaboration` $\rightarrow$ `corp-alpha-root` | `provider_entity`, `StatementOfWork` deliverables, `shared_packs` (`software-engineering`), SLA metrics | Personal payroll records, private academic `<persona>-tutor` notes, and `<persona>-wallet` airlock |

```bash
# Link <persona>-work (:8787) with org-alpha (:8720) & corp-alpha-root (:8710) and consult in < 20 ms:
zcg link ~/Projects/<persona>-work --target org-alpha --url http://org-alpha.localhost:8720/ --relation hr-process
zcg link ~/Projects/<persona>-work --target corp-alpha-root --ref ~/Work/corp-alpha/corp-alpha-root \
  --relation b2b-collaboration --packs software-engineering,corporate-operations
zcg consult-layer ~/Projects/<persona>-work --layer org-alpha --query "engineering role competencies"
```

### 1.1. `Root 0` Mesh Role Governance, Inheritable Grants & Global Workspace Scope

`Root 0` governs internal node-to-node communication declaratively via `capability_policy.mesh_governance` in `system/zcg-node.json` (`Node Admin > Network & Links`, `POST /api/modules/node-mesh/policy`), inheriting deterministic `NodeRelationGrant` rules downward while keeping every node ready for `v2.0.0` cryptographic signing ([`Architecture 03`](../architecture/03_governance_and_work_ledger.md), [`Architecture 04`](../architecture/04_cockpit_and_intranet_surfaces.md)):

| Governance Mode (`mesh_governance.topology_mode`) | Default Archetype & Topology Behavior | Authorized `NodeRelationGrant` Verbs (`4` Inheritable Capabilities) | Airlock & Isolation Guard |
| :--- | :--- | :--- | :--- |
| **`full-mesh`** | Default for personal constellations (`<persona>-profile`): `Root 0`, children, and sibling pillars communicate freely without manual bilateral wiring. | `consult_context`, `propose_work`, `delegate_work` (`Root 0` $\rightarrow$ child), and `validate_gate` (`domain-policy` / governor). | Automatically excludes `R3` `<persona>-wallet` nodes (`is_airlocked_wallet_node`) from lateral mesh exchange. |
| **`hierarchical-only`** | Strict vertical chain (`Parent <-> Child` only): blocks all unapproved lateral sibling traffic while preserving `1-hop` governance. | `consult_context`, `propose_work` (`Child -> Parent`), `delegate_work` (`Parent -> Child`), and `validate_gate` along vertical edges. | Sibling departments and peer pillars remain isolated (`0` cross-sibling inbox or doc leakage). |
| **`curated-matrix`** | Enterprise department governance: combines vertical `1-hop` authority with explicit `lateral_channels` (`LateralChannelRule` source/target/verbs). | Grants only the exact capability subset declared per department pair (`consult_context \| propose_work \| delegate_work \| validate_gate`). | Unlisted lateral pairs are denied by default; every grant record carries a structured contract ready for `v2.0.0` `Ed25519` attestation. |

Across `Workspace (/)`, the persistent **Workspace Scope Lens** (`.zcg-ws-scope` in `.zcg-stage-head`, persisted via `?ws_scope=all|node|network|corpora`) synchronizes `Dashboard`, `Backlog`, `Docs & Knowledge`, and `Metrics` around four consistent perspectives (`All`, `This Node`, `1-Hop`, and `Corpora`), while Quick-Add `exchange_target` lets operators route new tasks directly to any authorized parent, child, or governed sibling node.

---

## 2. Physical Context Architecture (`Pillar A..D`), Scoped Containment & `17`-Skill Matrix

Local disk materialization follows **4 Physical Context Pillars (`Pillar A..D`)** while Google Antigravity confines file-access and `<= 20,000`-token inline rule budgets strictly to the active **Workspace Root**:

```text
Pillar A (Layer 1 — Shared Global)      ← ~/zero-cloud-gravity/antigravity/ (symlinked to ~/.gemini/config/)
Pillar B (Layer 2 — Templates/Subtrees) ← ~/zero-cloud-gravity/templates/ & <node>/layers/ (19 declarative packs + isolated .zcg/tools/<id>/ tool-stack)
Pillar C (Layer 3 — Workspace Overlay)  ← <workspace>/.agents/              (projected rules, skills, SESSION.md & LAYER_LINEAGE.md)
Pillar D (Layer 4 — Navigable Corpus)   ← <workspace>/docs/ & corporate/    (3-tier progressive disclosure & 1:1:1 specs/ledgers)
```

### 2.1. Complete `17`-Skill Matrix (`8` Global `human-stack` + `9` Specialization Skills)

Every `SKILL.md` enforces **`1 Skill = 1 Verb`** cognitive judgment while delegating `< 1s` deterministic mutations to `Makefile` targets (`make status|task|complete|sync|diff|consult|horizon|promote|delegate|env-gate|activate-plugin`):

| Skill / Command | Source Pack (`kind`) | Target Levels | When to Use & Key Actions |
| :--- | :--- | :--- | :--- |
| `/sopen` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | Session start: runs `make status` (`< 0.2s`) and executes the Day-0 Kickoff Prompt when `setup_state != "configured"`. |
| `/continue` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | Mid-session checkpoint: Silent Pre-Flight Probe, snapshots `.agents/SESSION.md` & `WORKTASK.md` (`[Lot k/N]`), advances priorities. |
| `/sclose` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | Session close: updates `## [Unreleased]` in `CHANGELOG.md`, verifies `make diff` (`0` drift), emits Conventional Commit blocks. |
| `/review` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | Tactical `C1` read-only delta audit (`/review [path\|docs\|arch\|1:1:1\|layer\|governance]`). |
| `/enrich` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | Compares `.agents/` against parent layers (`zcg diff-project`) and promotes reusable rules `1-hop` upward (`make promote`). |
| `/architecture` | Global (`science-base`) | `Root 0`, `Department`, `Squad` | `Spec-First` design: orthogonal taxonomy (`X × Y`), `1:1:1` decomposition ($M_{\text{cluster}} \ge 1{,}200$), 5-surface cascade. |
| `/audit` | Global (`science-base`) | All (`Root 0` $\rightarrow$ `Project`) | Convergent `C2` closed-world repository gate across `Probe A..E` toward `Regime 0 (0 findings)`. |
| `/governance` | Global (`business-base`) | `Root 0`, `Department`, `Squad` | Work-lifecycle orchestration, `1-hop` delegation (`make delegate`), RBAC (`make roster\|decision\|env-gate`). |
| `refactoring` | `software-engineering` | Technical `Squad` / `Project` | Safe decomposition (`<= 384` source / `<= 464` doc-test caps) via `[WIRE] -> [CONSOLIDATE] -> [PRUNE]`. |
| `testing` | `software-engineering` | Technical `Squad` / `Project` | Bidirectional `E2E <-> Imp <-> Unit` `AAA` flow at `100.00%` isolated unit statement + branch coverage. |
| `validation` | `software-engineering` | Technical `Squad` / `Project` | Structured `V1..V5` interactive UI/cockpit validation tracked in `WORKVALI.md`. |
| `release` | `software-engineering` | Layer Owners | SemVer release (`vX.Y.Z`): `check-authority`, agnosticism + `make verify`, `[Unreleased] -> [X.Y.Z]`, commit/tag block. |
| `oss-contribute` | `software-engineering` | `OSS Dev` & `Squad` / `Project` | Empirical hot-path profiling, stdlib vectorization, and sanitized upstream OSS-to-OSS PRs. |
| `academic-tutor` | `academic-curriculum` | `tutor` & `org-uni-*` | Socratic `syllabus` $\rightarrow$ `next-lesson` $\rightarrow$ `practice-drill` $\rightarrow$ `verify-mastery` (`WORKVALI.md`). |
| `ledger-surface-audit` | `corporate-operations` | `Root 0` & `Department` | `1:1:1` business audit across `corporate/ledgers/` $\leftrightarrow$ `policies/sops/` $\leftrightarrow$ `surfaces/`. |
| `nist-csf-audit` | `nist-csf-security` | Security `Department` / Pillar | NIST CSF 2.0 (`GV/ID/PR/DE/RS/RC`), ISO 27001, and `NIST-01..04` AppSec/MCP-Sec surface checks. |
| `secops-mcp-orchestration` | `secops-mcp-guardian` | `domain-policy` (`dept-secops`) | Orchestrates Fixed MCPs (`R0..R2`) vs. `strictly-read-only` Ephemeral Security Bots + `rcap1` digests. |

### 2.2. Set-and-Forget Base Model, Thinking-Budget & Automatic Swarm Matrix (Mandate #12)

Pick **one** Set-and-Forget default base model per workspace profile from Day 1 (avoiding global `Orchestrator` pinning) and speak naturally without typing `/teamwork` — ZeroCloudGravity automatically deduces inline execution, single subagent delegation, or a disjoint-file Swarm (`0` worker Git commits) and recalibrates model tiers continuously during `/audit` (`zcg lint-arch`):

| Workspace Profile | Set-and-Forget Default Model (Day 1) | Velocity / Depth Alternative | Automatic Swarm & Multi-Agent Deduction (`0` `/teamwork` Needed) | Contract Reference |
| :--- | :--- | :--- | :--- | :--- |
| **1. Personal Workstation** (`Root 0` & Daily Flow) | **`Gemini 4 Neon (High)`** | `Gemini 4 Carbon (High)` for cross-pillar architecture | Instant `/sopen`, `/sclose`, and host audits run inline; multi-pillar sweeps fan out automatically without typing `/teamwork`. | [`model_currency.py`](../../src/zcg/governance/policy/model_currency.py) |
| **2. Academic Tutor** (`M1..M4` Socratic Study) | **`Gemini 4 Neon (Medium)`** | `Gemini 4 Carbon (High)` for syllabus design & deep proofs | Fast Socratic drills run inline; multi-topic study packs fan out to `Neon (Medium)` drafters plus a `Carbon (High)` pedagogical verifier. | [`Guide 02`](02_personal_tutor_and_academic_progression.md) |
| **3. Enterprise & Governance** (`Root 0` / Dept / SOP) | **`Gemini 4 Carbon (High)`** | `Gemini 4 Neon (Medium)` for routine `WORK*` updates | RBAC and SOP decisions run inline; cross-department ledger and policy sweeps fan out to `Neon (Medium)` analysts plus a `Carbon (High)` auditor. | [`Guide 05`](05_enterprise_root_and_organizational_scales.md) |
| **4. Science & Knowledge** (`E3..E0` Corpora) | **`Gemini 4 Carbon (High)`** | `Gemini 4 Neon (Medium)` for document structuring | Epistemic `E3..E0` and citation checks run inline; multi-document corpus audits fan out to `Neon (High)` workers plus a `Carbon (High)` epistemic verifier. | [`Guide 04`](04_scientific_and_public_knowledge_corpora.md) |
| **5. Software Engineering** (`1:1:1` Architecture) | **`Gemini 4 Carbon (High)`** | `Gemini 4 Neon (High)` for high-velocity bounded lots | Coupled `1–4` file edits run inline; `>= 2` independent slices auto-spawn `Neon (High)` disjoint-file authors (`workspace: "inherit"`, `0` worker Git commits) + `1` read-only `Carbon (High)` verifier. | [`Architecture 03`](../architecture/03_governance_and_work_ledger.md) |

#### 2.2.1. Thinking Budgets (`Low | Medium | High | XHigh`) & Continuous `Model-Currency` Calibration

Thinking budgets govern reasoning depth per turn while Mandate `#12` keeps model tiers current across stack upgrades without memorizing routing flags:

| Thinking Budget / Gate | Reasoning Behavior & Automatic Trigger | Primary Execution Role & Verification Rule |
| :--- | :--- | :--- |
| **`Low`** | Minimal deliberation for immediate lookups, formatting, and mechanical one-liners. | Reserved for `flash` browser/read-only subagents and rapid triage queries. |
| **`Medium`** | Balanced latency and accuracy for structured prose, docs, and routine updates. | Default for `Academic Tutor`, pure-doc Swarm authors (`gemini-4-neon-medium`), and `WORK*` updates. |
| **`High`** | Deep multi-file invariant synthesis, architectural design, and strict verification. | Set-and-Forget default for `Carbon (High)` / `Neon (High)` engineering, science, enterprise, and read-only `verifier` audits. |
| **`XHigh`** | Extended frontier reasoning for hard algorithmic or branch-coverage puzzles, novel proofs, and complex root-cause forensics. | Available on `Gemini 4 Neon` and `Hydrogen` (`gemini-4-neon-xhigh`) selectively without changing your daily default, while `Gemini 4 Carbon` caps at `High`. |
| **Continuous `Model-Currency` Gate** | Recalibrates default base models, thinking budgets (`Low..XHigh`), and worker/verifier pins on every stack/platform upgrade and `/audit` pass (`0` deprecated model shims). | Enforced deterministically by `check_model_currency_policy` (`zcg lint-arch`), `/review`, and `/audit` across `AGENTS.md`, `universal-base.md`, and `Node Admin > Skills`. |

---

## 3. Reference Summary: `Cases 1–7` `Phase A..D` Matrix & `12`-Case Topology Governance

Every archetype pre-loads its tailored `Phase A..D` prompt automatically inside its **Pending-Setup Web Studio (`GET /`)**:

| Canonical Case | `Phase A` (Identity & Authority) | `Phase B` (Rules, Tracks or Corpus) | `Phase C` (Bounded-Lot Execution) | `Phase D` (`[x]` Unlock & Sync) |
| :--- | :--- | :--- | :--- | :--- |
| **1. Personal `Root 0`** (`~/<user>-profile` `:8790`) | Couple engine + `<user>-profile` (`universal-base`). | `make workstation-backup`, `machine/*` & `.local` isolation. | `make workstation-audit` & `make diff`. | Mark `[x]` in `WORKTASK.md`, unlock `:8790` Workspace. |
| **2. Personal Tutor** (`<user>-tutor` `:8786`) | Tailor `<user>-tutor.md` on `master` (`academic-base`). | `specialty/*` branches, `sci-*` feeds, `SYLLABUS.md`. | `make task` $\rightarrow$ `practice-drill` $\rightarrow$ `verify-mastery`. | Merge shared habits to `master`, promote to `<user>-profile`. |
| **3. Application Project** (`<app>` `:8080/8780`) | Read `.agents/LAYER_LINEAGE.md` (`software-engineering`). | Initialize `docs/architecture/` (`1:1:1`) & `WORKTASK.md`. | `make task`, `Pre-Blueprint` (`1` lot/turn), `make verify`. | `make env-gate ENV=tst\|pre\|pro`, `/enrich` $\rightarrow$ `promote`. |
| **4. Knowledge Corpus** (`gov/sci/geo/org-*` `:8720`) | Configure `layer_role: "knowledge"` & `stewardship_stage`. | Author `< 465`-line `E3..E0` docs + `citation_receipt`. | Verify `0` empty `L1` exons & epistemic monotonicity. | Audit `Q1..Q4` citation radar & publish verified snapshot. |
| **5. Corporate `Root 0`** (`<corp>-root` `:8710`) | Tailor `<corp>.md` (`corporate-root-hub`). | `make roster`, `capability_policy`, `domain_governance`. | `make delegate` / `Work Inbox` & Business `AAA` gates. | Reconcile children (`make sync`) & arbitrate escalations. |
| **6. Functional Dept / Squad** (`dept-*` `:8715..8750`) | Inherit `Root 0` policy (`node-work-cockpit`). | Configure `surface_bindings`, SOPs, and `layers/*` mounts. | Claim tickets on Kanban `Work Board`, `make diff`. | `make complete`, `make env-gate`, promote `1-hop` upward. |
| **7. Fiduciary SecOps** (`dept-secops` `:8705`) | Configure `domain-policy` (`precedence: 5` *Lex Superior*). | Bind `NIST-01..04` gates & Ephemeral Bot guardrails. | Run `nist-csf-audit` & read-only bot inspections. | Record `make decision` (`approve\|reject\|blocked`) for `pro`. |

### 3.1. Complete `12`-Case Visibility & Flow Enforcement Matrix

The visibility lattice below governs every intra-tree, upward, and horizontal boundary across all `12` canonical workspace cases:

| # | Node / Workspace Case | `visibility_scope` (`prec`) | Allowed Downward & Intra-Tree Flows | Allowed Upward / Horizontal Flows & Guards |
| :-: | :--- | :--- | :--- | :--- |
| **1–2** | **OSS Engine (`~/zero-cloud-gravity`) & Dev Clone (`dev-*`)** | `open-source` (`10`) | Feeds `19` packs downward (`zcg-sync`); `dev-*` fast-forwards clean commits. | Receives sanitized PRs (`oss-sanitized-pr`); `_RETIRED_TOKENS` purity gate. |
| **3–5** | **Personal `Root 0` (`90`), Pillars (`85..89`) & Personal Projects (`80`)** | `private:individual:*` | `<user>-profile` governs `tutor`, `work`, `security`, `wallet`, `game`; `wallet` blocks peer links. | `1-hop` promotion to `<user>-profile`; `CROSS_TIER_PROMOTION_BYPASS` blocks tier-skipping. |
| **6–8** | **Public Gov `Root 0` (`1..2`), Ministry (`3..4`) & `Knowledge` (`20`)** | `public-government` / `knowledge` | Enforces statutory *Lex Superior* (`1..4 < 10`) & serves `rcap1` (`L0..L3`) corpora (`:8720`). | Sibling `public-community` repos stay isolated unless mounted; `Q1..Q4` radar. |
| **9–12** | **Fiduciary Dept (`5..9`), Enterprise `Root 0` (`10`), Dept/Squad (`15..60`) & Project (`80`)** | `private:enterprise:*` | Fiduciary veto (`5 < 10`), `make delegate` / `Work Inbox`, `0..80` rule cascade. | Subordinate OSS leaks blocked (`can_expose_to_oss: false`) unless `root_0_public_approved`. |
