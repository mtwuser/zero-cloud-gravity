---
epistemic_grade: E1
---

# Guide 02 — Sovereign Nodes, Knowledge Atlases & Federated Team Workflows

> **Human & Architect Operator Manual (Tier 2 Progressive Disclosure)**
>
> Step-by-step guide to the 4 Physical Context Pillars (`Pillar A..D`), the **`4 + 4 + 2 + 6 = 16` Template Matrix & `17`-Skill Catalog**, Scoped Antigravity Workspace Containment, the 4-Level Organizational Hierarchy (`Root 0 -> Department / Knowledge -> Squad / Tutor -> Project`), the `M1 -> M4` Personal Tutor Showcase (`specialty/*` branches), `Cases 1–7` Customizable `Phase A..D` Kickoff Prompts, the `12`-Case Level/Flow Matrix, and `gov-*/sci-*/geo-*/org-*` Knowledge Nodes. For normative engine contracts, see **[`docs/architecture/02_triadic_topology_and_twin_surfaces.md`](../architecture/02_triadic_topology_and_twin_surfaces.md)** and **[`docs/architecture/03_governance_and_work_ledger.md`](../architecture/03_governance_and_work_ledger.md)**.

---

## 1. Configuration Architecture (`Pillar A..D`) & Complete `17`-Skill Matrix

Local disk materialization follows **4 Physical Context Pillars (`Pillar A..D`)** where each pillar extends the one above it:

```text
Pillar A (Layer 1 — Shared Global)      ← ~/zero-cloud-gravity/antigravity/ (symlinked to ~/.gemini/config/)
Pillar B (Layer 2 — Templates/Subtrees) ← ~/zero-cloud-gravity/templates/ & <node>/layers/ (16 declarative packs)
Pillar C (Layer 3 — Workspace Overlay)  ← <workspace>/.agents/              (projected rules, skills, SESSION.md & LAYER_LINEAGE.md)
Pillar D (Layer 4 — Navigable Corpus)   ← <workspace>/docs/ & corporate/    (3-tier progressive disclosure & 1:1:1 specs/ledgers)
```

### 1.1. Complete `17`-Skill Matrix Across the `4` Universal Bases & `3` Specialization Stack Rings

The **17 skills** (`8` global in `antigravity/.gemini/config/skills/` + `9` stack-scoped in `templates/{context,framework,plugin}-stack/*/skills/`) enforce `1 Skill = 1 Verb` cognitive playbooks while delegating deterministic state mutations to `Makefile` targets (`make <target>`):

| Skill / Command | Source Pack (`kind`) | Target Organizational Levels | When to Use & Key Actions |
| :--- | :--- | :--- | :--- |
| `/sopen` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | Start of every session: runs `make status` (`zcg status`) in `< 0.2s` (`entity_identity`, `network_topology`, `work_orchestration`, `runtime_orchestration`, `setup_state`, `horizon`, `agent_diff`) and guides `Phase A..D` onboarding when `setup_state.state != "configured"`. |
| `/continue` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | Mid-session checkpoint & priority progression: runs the Silent Pre-Flight Probe, snapshots `.agents/SESSION.md` & `WORKTASK.md` (`[Lot k/N]`), delivers commit blocks when dirty, and advances along `#0 In-Flight -> #1 WORKTASK.md -> #2 WORKROAD.md / BACKLOG.md -> #3 roadmaps/`. |
| `/sclose` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | End of session: consolidates completed work under `## [Unreleased]` in `CHANGELOG.md`, verifies zero drift (`make diff`), and emits ready-to-run Conventional Commit blocks. |
| `/review` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | Tactical `C1` read-only audit (`/review [path\|docs\|arch\|1:1:1\|layer\|governance]`) of the active session delta or target path across the 4 canonical quality dimensions. |
| `/enrich` | Global (`universal-base`) | All (`Root 0` $\rightarrow$ `Project`) | Compares workspace `.agents/` against parent layers (`zcg diff-project`), checks `make horizon`, and promotes reusable rules 1-hop upward (`make promote`). |
| `/architecture` | Global (`science-base`) | `Root 0`, `Department`, `Squad` | Constructive `Spec-First` architectural design: orthogonal taxonomy synthesis (`X × Y`), `1:1:1` module boundary decomposition ($M_{\text{cluster}} \ge 1{,}200$), and 5-dimension specification cascade. |
| `/audit` | Global (`science-base`) | All (`Root 0` $\rightarrow$ `Project`) | Convergent `C2` closed-world repository gate (`/audit [path\|docs\|arch\|1:1:1\|layer\|governance]`) across 5 deterministic probes (`Probe A..E`) toward `Regime 0 (0 findings)`. |
| `/governance` | Global (`business-base`) | `Root 0`, `Department`, `Squad` | Constructive work-lifecycle orchestration (`roadmaps/ -> WORKROAD -> WORKTASK -> CHANGELOG`), `1-hop` downward delegation (`make delegate`), RBAC/consensus (`make roster\|decision\|env-gate`), and clean-room knowledge extraction. |
| `refactoring` | `software-engineering` (`context-stack`) | Technical `Squad`/`Project` & `make apply-template` | Safe decomposition of code files approaching the `< 385`-line source cap (`< 465` doc/test cap), relational clusters ($M_{\text{cluster}} \ge 1,200$), and `[WIRE] -> [CONSOLIDATE] -> [PRUNE]` cutovers. |
| `testing` | `software-engineering` (`context-stack`) | Technical `Squad`/`Project` & `make apply-template` | Bidirectional `Top-Down (E2E -> Imp -> Unit)` / `Bottom-Up (Unit -> Imp -> E2E)` flow, `# Arrange / # Act / # Assert` structure, and `100.00%` isolated single-file unit branch coverage. |
| `validation` | `software-engineering` (`context-stack`) | Technical `Squad`/`Project` | Exhaustive manual UI/cockpit validation procedure tracked in `WORKVALI.md`. |
| `release` | `software-engineering` (`context-stack`) | Layer Owners (`Root 0` $\rightarrow$ `Project`) | Explicit SemVer release (`vX.Y.Z`): verifies `zcg check-authority --op release`, runs agnosticism & `make verify` gates, promotes `[Unreleased]` $\rightarrow$ `[X.Y.Z]`, and outputs commit + tag + push commands. |
| `oss-contribute` | `software-engineering` (`context-stack`) | `OSS Dev` & Technical `Squad`/`Project` | Conscious `C3` workflow for empirical hot-path profiling, C-backed stdlib vectorization, optional `PEP 7` C-accelerators, and upstream OSS-to-OSS PR contributions. |
| `academic-tutor` | `academic-curriculum` (`context-stack`) | `org-uni-*`, Study Workspaces & Personal Tutors | Interactive curriculum planning (`syllabus` $\rightarrow$ `SYLLABUS.md` + `WORKROAD.md`), Socratic lessons (`next-lesson` $\rightarrow$ `make task`), active-recall drills (`practice-drill` $\rightarrow$ `WORKVALI.md`), and mastery sign-off (`verify-mastery` $\rightarrow$ `make complete`). |
| `ledger-surface-audit` | `corporate-operations` (`context-stack`) | `Root 0`, `Department`, Business `Squad` | Audits 3-ring Hexagonal Business traceability across `corporate/ledgers/` $\rightarrow$ `corporate/{policies,sops}/` $\rightarrow$ `surfaces/{web,forms,print}/` (`[DEPT]-[TYPE]-[YYYY]-[NNN]`). |
| `nist-csf-audit` | `nist-csf-security` (`framework-stack`) | Security `Department` / `Squad` | NIST CSF 2.0 (`GV/ID/PR/DE/RS/RC`), ISO/IEC 27001 controls, and `NIST-01..04` AppSec/MCP-Sec surface audits. |
| `secops-mcp-orchestration` | `secops-mcp-guardian` (`plugin-stack`) | Security `Domain-Policy` (`dept-legal-ip` / `dept-security`) | Orchestrates departmental Fixed MCPs (`R0..R2` Autonomous) vs. Ephemeral Security Bots and seals `rcap1` return digests. |

---

## 2. Scoped Workspace Execution in Google Antigravity & Multi-Tier Containment

Google Antigravity 2.0 (`antigravity-agents` and `agy` CLI) scopes agent context and file-access permissions strictly to the **Workspace Root** opened in each window:

| Workspace Root Opened in Antigravity | Active Rules Loaded into Context (`<= 20,000` tokens) | Containment Boundary & Cross-Layer Protocol |
| :--- | :--- | :--- |
| **`Corporate Root 0`** (`--role corporate`, `precedence: 10`) | Global `~/.gemini/config/AGENTS.md` + `layer-10-<root>.md` (`business-base` + `corporate-operations` + executive governance). Mounted child subtrees in `layers/<dept>/` are **never** auto-injected into always-on context; they are queried on demand via `make consult` (`rcap1`) or delegated via `make delegate`. | Enables holistic 360° executive orchestration (`corporate-root-hub` on `:8710`), cross-subtree inspection (`make status`, `make horizon`), and `1-hop` downward delegation across `layers/*`. |
| **`Department` / `Domain-Policy` / `Knowledge`** (`precedence: 5..45`) | Global `AGENTS.md` + inherited `layer-10-<root>.md` + `layer-<NN>-<dept>.md` (+ `science-base` + `software-engineering` when `make apply-template` is active). | Enforces vertical and horizontal departmental isolation; cross-department and knowledge queries use `make consult LAYER=<peer>` (`strictly-read-only`). |
| **`Level 3 Squad / Personal Tutor` & `Level 4 Project`** (`precedence: 50..89` + `85..95` `Human-Stack`) | Global `AGENTS.md` + inherited chain (`0..80`) + specialization stack (`context-stack`, `framework-stack`, or `plugin-stack`) + personal `Human-Stack` (`M1..M4`) in `.agents/SESSION.md`. | Confines execution strictly to the squad, tutor, or application repository; upward rule changes are proposed 1-hop via `make promote` (`promote-from-project --create-pr`). |

---

## 3. 4-Level Hierarchy Lifecycle & Customizable `Phase A..D` Kickoff Prompts (`Cases 1–7`)

When you initialize a node via `zcg bootstrap-workspace` (or a project via `zcg apply-project`), the CLI establishes the **Triadic `Node × Layer × Network` Topology**, activates the node's default Zero-Cloud Cockpit (`workstation-control-tower`, `corporate-root-hub`, `node-work-cockpit`, `tutor-study-cockpit`, or `secops-mcp-guardian`), and renders a **Layer Setup Blueprint** in `README.md`.

### 3.1. Concrete CLI Recipes Across the 5 Real-World Archetypes

The commands below initialize each canonical organizational and personal archetype:

```bash
# Archetype 1 — Public Government Root 0 (prec: 2) & Public Statutory Knowledge Twin (gov-es, prec: 20):
zcg bootstrap-workspace ~/Projects/gov-es-root \
  --id gov-es-root --role corporate --precedence 2 --entity-kind public-government --templates business-base,corporate-operations
zcg bootstrap-workspace ~/Projects/gov-es \
  --id gov-es --role knowledge --precedence 20 --parent-dir ~/Projects/gov-es-root --templates business-base,corporate-operations,science-base

# Archetype 2 — Scientific & Geographic Knowledge Atlases (sci-maths, sci-physics, sci-biology, sci-engineering, geo-es):
zcg bootstrap-workspace ~/Projects/sci-physics \
  --id sci-physics --role knowledge --precedence 20 --templates science-base,scientific-methodology,node-work-cockpit

# Archetype 3 — Enterprise Root 0 (prec: 10), Public Twin (org-acme, 20), Fiduciary SecOps (5) & Cloud Engineering (25):
zcg bootstrap-workspace ~/Projects/acme-root \
  --id acme-root --role corporate --precedence 10 --entity-kind enterprise --templates business-base,corporate-operations,corporate-root-hub
zcg bootstrap-workspace ~/Projects/org-acme \
  --id org-acme --role knowledge --precedence 20 --parent-dir ~/Projects/acme-root --templates business-base,corporate-operations
zcg bootstrap-workspace ~/Projects/dept-legal-ip \
  --id dept-legal-ip --role domain-policy --precedence 5 --parent-dir ~/Projects/acme-root --templates business-base,corporate-operations,nist-csf-security,secops-mcp-guardian
zcg bootstrap-workspace ~/Projects/dept-tech-eng \
  --id dept-tech-eng --role department --precedence 25 --parent-dir ~/Projects/acme-root --templates science-base,software-engineering,google-cloud-iac,node-work-cockpit

# Archetype 4 & 5 — Personal Sovereign Root 0 (~/<user>-pc, prec: 90) & Unified Personal Tutor (<user>-tutor, prec: 86):
~/zero-cloud-gravity/scripts/workstation-sync.sh --setup --profile universal-base --lang es --workstation-dir ~/alex-pc
zcg bootstrap-workspace ~/Projects/alex-tutor \
  --id alex-tutor --role department --precedence 86 --lang es \
  --parent-dir ~/alex-pc --templates academic-base,academic-curriculum,tutor-study-cockpit
```

### 3.2. Personal Tutor Showcase (`M1 -> M4`) & Parallel `specialty/*` Branches (`DMCP`)

A personal tutor node (`~/Projects/<persona>-tutor`, `precedence: 86`, `tutor-study-cockpit` on `:8786`) uses a two-plane branch architecture:
1. **`master` Branch (Universal Pedagogical DNA)**: Holds `templates/<persona>-tutor/rules/<persona>-tutor.md` defining how your tutor pairs with you across *all* disciplines (`academic-base` + `academic-curriculum`).
2. **`specialty/<track>` Branches (Pure or Combined Subject Tracks)**:
   - `specialty/maths` (mounts `layers/sci-maths`), `specialty/physics` (mounts `layers/sci-physics`), `specialty/maths-physics` (mounts both `sci-maths` and `sci-physics`), `specialty/biology` (`sci-biology`), or `specialty/software-eng` (`sci-engineering` + `software-engineering`).
   - Each `specialty/*` branch maintains its own `SYLLABUS.md` (`School M1 -> University M2 -> Professional M3 -> Research Mastery M4`), `WORKROAD.md`, `WORKTASK.md`, and `WORKVALI.md` (`verify-mastery` gates).
   - **Zero-Checkout `DMCP` Inspection**: From `master` (or any other branch), `zcg-mcp` reads `SYLLABUS.md` or rules on any `specialty/*` branch in `< 5 ms` with `zero_checkout: true` via `read_layer_document(rel_path="SYLLABUS.md", branch_ref="specialty/maths")` or `orchestrate_ephemeral_fork(action="dmcp-project", branch_ref="specialty/physics")`!

### 3.3. Complete `Cases 1–7` Customizable `Phase A..D` Kickoff Matrix

The table below provides the **4-Phase Customizable Prompt Progression (`Phase A -> Phase D`)** across all **7 Canonical Cases**:

| Canonical Case | `Phase A` (Bootstrap, Cockpit & Identity Alignment) | `Phase B` (Custom Rules, Syllabus, Corpus or Surface Tailoring) | `Phase C` (Daily Bounded-Lot Execution & Verification) | `Phase D` (Configured Transition, Enrichment & Sync) |
| :--- | :--- | :--- | :--- | :--- |
| **Case 1: `$HOME` Personal `Root 0`** (`~/<user>-pc`, `90`, `:8790`) | `/sopen` $\rightarrow$ Couple `~/zero-cloud-gravity` + `~/<user>-pc` via `workstation-sync.sh --setup --profile universal-base --lang <code\>`. | Capture manifests (`make backup-system`), isolate `.local` files, and tailor `templates/<user>-pc/rules/<user>-pc.md`. | Run `make audit-system` and `make diff` (`1` lot/turn, `/continue` checkpoints). | Run `zcg-sync` (`make workstation-sync`) and output `zcg bootstrap-workspace` commands for `~/Projects/*`. |
| **Case 2: Personal Tutor (`M1 -> M4`)** (`~/Projects/<user>-tutor`, `86`, `:8786`) | `/sopen` $\rightarrow$ Read `README.md` (`academic-base,academic-curriculum,tutor-study-cockpit`, `--lang <code\>`); tailor `<user>-tutor.md` on `master`. | Create `specialty/*` branches, mount `sci-*` corpora, author `SYLLABUS.md` (`M1..M4`), and set `domain-<topic>:M1` in `.agents/SESSION.md`. | Claim modules via `make task`, run `next-lesson` $\rightarrow$ `practice-drill` (`1` lot/turn), and gate with `verify-mastery` in `WORKVALI.md`. | Advance `M1 -> M2 -> M3 -> M4`, merge common pedagogy to `master`, and promote universal habits to `~/<user>-pc` (`make promote`). |
| **Case 3: Standalone Project Repo** (`~/Projects/<app>`, `80`) | `/sopen` $\rightarrow$ Read `.agents/LAYER_LINEAGE.md` (`software-engineering` + `google-cloud-iac` or `nist-csf-security`). | Initialize `README.md`, `docs/architecture/` (`1:1:1` specs), `WORKROAD.md`, and `WORKTASK.md` for Phase 1. | Claim via `make task`, present Pre-Edit Scope Blueprint (`1` lot/turn), and enforce `make verify` (`100%` isolated unit coverage). | Run `make sync && make diff`, validate `make env-gate ENV=tst\|pre\|pro`, and promote patterns via `/enrich` $\rightarrow$ `make promote`. |
| **Case 4: Public/Private Knowledge Atlas** (`gov-*`, `sci-*`, `geo-*`, `org-*`, `20`, `:8720`) | `/sopen` $\rightarrow$ Read `README.md` & `system/zcg-node.json` (`layer_role: "knowledge"`, `stewardship_stage`). | Structure `docs/{guides,architecture,reference}/` (`< 465` lines) with `E3..E0` grades and `citation_receipt` anchors. | Author/update corpus sections (`1` lot/turn), verify `0` empty `L1` exons and `verify_epistemic_context_claims`. | Review `Q1..Q4` citation telemetry radar (`audit_node_drift`) and publish verified snapshots to consumers. |
| **Case 5: Corporate `Root 0` + `org-*` Twin** (`<corp>-root`, `10`, `:8710`) | `/sopen` $\rightarrow$ Tailor `templates/<corp>/rules/<corp>.md` (`business-base,corporate-operations,corporate-root-hub`). | Configure `.github/CODEOWNERS` (`make roster`), `corporate/ledgers/`, `org-<corp>` twin (`20`), and child `Department` bootstrap commands. | Delegate directives (`make delegate`) or claim `Root 0` tasks (`make task`), verifying Business `AAA` gates (`1` lot/turn). | Reconcile child completions (`make sync`), arbitrate `ESCALATE_TO_ROOT`, and promote anonymized rules to OSS (`make promote`). |
| **Case 6: Functional / Cloud Department or Squad** (`dept-*` `15..45`, `squad-*` `50`, `:8715..8750`) | `/sopen` $\rightarrow$ Read `README.md` (`corporate-operations` or `software-engineering,google-cloud-iac`, `node-work-cockpit`). | Configure departmental `surface_bindings`, `corporate/{ledgers,policies,sops}/`, and mounted `layers/{gov-*,sci-*,geo-*}` subtrees. | Claim delegated tickets (`make task`), execute `1` lot/turn (`make apply-template` for in-situ code), and verify `make diff`. | Complete tasks (`make complete PARENT_SYNC=1`), validate `make env-gate`, and promote reusable rules 1-hop to `Root 0`. |
| **Case 7: Fiduciary SecOps & Legal Guardian** (`dept-legal-ip` / `dept-secops`, `5`, `:8705`) | `/sopen` $\rightarrow$ Read `README.md` (`domain-policy`, `precedence: 5`, `nist-csf-security,secops-mcp-guardian`). | Configure fiduciary `surface_bindings` (`precedence: 5` *Lex Superior*), `NIST-01..04` control ledgers, and `federated_mcps` guardrails. | Audit cross-departmental surfaces (`nist-csf-audit`, `secops-mcp-orchestration`) and spawn `strictly-read-only` Ephemeral Bots. | Record `make decision` (`approve\|reject\|blocked`) for `pre`/`pro` gates and seal `rcap1` return digests. |

---

## 4. Complete `12`-Case Level/Mode/Flow Matrix & `5` Inter-Layer Communication Modes

The table below summarizes the **12 Node Archetypes**, their `visibility_scope`, `mcp_operating_mode`, and deterministic downward/upward flows enforced by `src/zcg/topology/identity.py` and `src/zcg/governance/authority.py`:

| # | Node / Workspace Case | `visibility_scope` (`precedence`) | `mcp_operating_mode` | Allowed Downward & Intra-Tree Flows | Allowed Upward & Horizontal Flows (and Blocked Bypasses) |
| :-: | :--- | :--- | :--- | :--- | :--- |
| **1** | **Public Open-Source Engine** (`~/zero-cloud-gravity`) | `public:open-source:root-0` (`10`) | `workstation-baseline-provider` | Feeds `16` declarative template packs downward to all `Root 0`, `dev-*`, and `$HOME` installations (`zcg-sync`). | Receives clean releases from `dev-zero-cloud-gravity` and anonymized PRs (`oss-sanitized-pr`) from any `Root 0`. |
| **2** | **Private OSS Dev Clone** (`~/Projects/dev-zero-cloud-gravity`) | `private:open-source:dev` (`10`) | `self-test-and-dev-only` | Fast-forwards clean committed engine state into `~/zero-cloud-gravity` during `zcg workstation-sync`. | Runs 8-gate `make verify` (`100%` isolated coverage); blocks private tracker leaks (`_RETIRED_TOKENS_RE`). |
| **3** | **Personal Sovereign `Root 0` Hub** (`~/<user>-pc`) | `private:individual:root-0` (`90`) | `personal-root-hub` | Pulls OSS stacks downward; hosts `machine/*` & `hat/*` branches; delegates 1-hop downward to `<user>-tutor` (`86`). | Composes `<user>-pc.md` into `$HOME` `AGENTS.md`; promotes anonymized generic rules to OSS; consultable via `zcg-mcp`. |
| **4** | **Personal Tutor Sub-Layer** (`~/Projects/<user>-tutor`) | `private:individual:department` (`86..89`) | `departmental-policy-hub` | Inherits `governing_root_id: <user>-pc`; hosts `specialty/*` branches (`DMCP`) + `tutor-study-cockpit` (`:8786`). | Communicates 1-hop with `<user>-pc` (`internal-1hop-hierarchical`); direct OSS promotion blocked (`CROSS_TIER_PROMOTION_BYPASS`). |
| **5** | **Personal Study / Project** (`~/Projects/<my-app>`) | `private:individual:project` (`80..95`) | `project-consumer-only` | Consumes `<user>-pc` or `<user>-tutor` rules in `.agents/` while keeping `$HOME` on `universal-base`. | Promotes learned personal patterns 1-hop upward to `<user>-tutor` or `<user>-pc`. |
| **6** | **Public Admin `Root 0`** (`gov-es-root`) | `private:public-government:root-0` (`1..2`) | `enterprise-governance-hub` | Delegates statutory frameworks 1-hop downward to ministries (`3..4`) and publishes enacted statutes to `gov-es` (`20`). | Collaborates with peer `Root 0`s or promotes generic templates to Open Source. |
| **7** | **Public Admin Ministry** (`gov-ministry-*`) | `private:public-government:department` (`3..4`) | `departmental-policy-hub` | Enforces constitutional/statutory *Lex Superior* (`1..4 < 10`) over all enterprise and individual layers. | Promotes 1-hop upward to `gov-es-root`; cannot be overridden by a private enterprise `Root 0`. |
| **8** | **Public/Private Knowledge Atlas** (`gov-*`, `sci-*`, `geo-*`, `org-*`) | `public:knowledge:<domain>` (`20`) | `knowledge-corpus-provider` | Serves `< 465`-line `E3..E0` corpus via `rcap1` (`L0..L3`) capsules and `citation_receipt` (`node-work-cockpit` `:8720`). | Strictly isolated from sibling `public-community` repos unless mounted in `mounted_layers`; tracks `Q1..Q4` citation radar. |
| **9** | **Enterprise Fiduciary Department** (`dept-legal-ip`, `dept-secops`) | `private:enterprise:department` (`5..9`) | `departmental-policy-hub` | Exercises fiduciary veto (`precedence < 10`) over corporate/tech deliverables via `surface_bindings` (`secops-mcp-guardian`). | Internal to `governing_root_id`; deadlocks escalate via `ESCALATE_TO_ROOT` to Corporate `Root 0` (`10`). |
| **10** | **Enterprise `Root 0` Hub** (`<corp>-root`) | `private:enterprise:root-0` (`10`) | `enterprise-governance-hub` | Delegates directives (`make delegate`) to internal departments (`5..45`), governs `org-<corp>` twin (`20`), serves `:8710` hub. | Sole enterprise gateway for anonymized OSS promotion (`can_expose_to_oss: true`) and peer `Root 0` collaboration. |
| **11** | **Enterprise Functional Department / Squad** (`dept-*` `15..45`, `squad-*` `50`) | `private:enterprise:department` / `:unit` (`15..60`) | `departmental-policy-hub` / `squad-execution-hub` | Runs in business mode or overlays technical stacks (`make apply-template` / `google-cloud-iac`); serves `:8715..8750` cockpit. | Promotes 1-hop upward to parent `Department` or `Root 0`; subordinate outward OSS exposure blocked unless `root_0_public_approved`. |
| **12** | **Enterprise Application Project** (`<service-app>`) | `private:enterprise:project` (`80`) | `project-consumer-only` | Weaves inherited `0..80` rules (`zcg apply-project --layers all`) + contextual `Human-Stack` (`85..95` in `.agents/SESSION.md`). | Promotes novel rules 1-hop to governing `Squad`/`Department`; `dev -> tst -> pre -> pro` gated by `make env-gate`. |

---

## 5. Dual-World Command Customization (`1 Skill = 1 Verb` in `SKILL.md` vs. `Makefile` Flags)

In ZeroCloudGravity, **Antigravity Skills (`SKILL.md`)** and **`Makefile` Targets (`make <target>`)** form two orthogonal planes (`Mandate 1` & `Mandate 11`):
- **Skills (`SKILL.md` — Cognitive Judgment Plane)**: Govern multi-step reasoning, architectural trade-offs, Socratic coaching, and human-AI synthesis (`1 Skill = 1 Verb`: `/sopen`, `/continue`, `/sclose`, `/review`, `/audit`, `/architecture`, `/governance`, `/enrich`).
- **`Makefile` Targets (`make <target>` — Deterministic Syscall Plane)**: Execute `< 1s` deterministic state transitions, SHA-256 drift checks, RBAC checks, and cockpit daemon actions (`make status`, `make task`, `make complete`, `make sync`, `make diff`, `make consult`, `make horizon`, `make promote`, `make delegate`, `make env-gate`, `make activate-plugin`). Custom deterministic targets added below `# --- Custom Targets ---` in any node's `Makefile` are preserved automatically across `make sync`.
