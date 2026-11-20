# ZeroCloudGravity (`zcg` · `v1.2.0`)

<!-- mcp-name: io.github.mtwuser/zero-cloud-gravity -->

[![CI](https://github.com/mtwuser/zero-cloud-gravity/actions/workflows/ci.yml/badge.svg)](https://github.com/mtwuser/zero-cloud-gravity/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](VERSION)
[![Coverage](https://img.shields.io/badge/coverage-100%25%20(unit%20%2B%20branch)-brightgreen.svg)](scripts/verify-repo.sh)
[![Python](https://img.shields.io/badge/python-3.14%20(zero--deps)-3776AB.svg)](pyproject.toml)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-26.04%20LTS-E95420.svg)](https://ubuntu.com/)
[![Antigravity](https://img.shields.io/badge/Google%20Antigravity-2.0-8E44AD.svg)](https://antigravity.google/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Sovereign Zero-Cloud Human-AI Governance ("pAIr programming"), Physical Workstation Control Tower, and Epistemic Knowledge Mesh for **Ubuntu 26.04 LTS ("Resolute Raccoon")** and **Google Antigravity 2.0 / Gemini** *(100% Python 3.14 Standard Library, `0` external runtime dependencies, `100.00%` isolated `1:1` statement and branch coverage)*.

This platform is built on **one unified fractal pattern** (*every governed directory combines a declarative node manifest `system/zcg-node.json`, Markdown rules/skills, task ledgers, and zero-build `.local` cockpits across `Public Gov (1..4) -> Corporate Root 0 (10) -> Domain-Policy (5..9) / Knowledge (20) / Department (15..45) -> Squad (50) -> Project (80)` and `Individual Sovereign Root 0 (90) -> Personal Pillar (86..89)`, powered by the **`4 + 6 + 2 + 7 = 19` Declarative Template Matrix** across `human-stack`, `context-stack`, `tool-stack`, and `plugin-stack`*):
1. **Ubuntu 26.04 Workstation Backup, Audit, Restore & Dual-Repo `$HOME` Sync ([`scripts/workstation-sync.sh`](scripts/workstation-sync.sh), [`scripts/workstation-backup.sh`](scripts/workstation-backup.sh), [`scripts/workstation-audit.sh`](scripts/workstation-audit.sh), [`scripts/workstation-restore.sh`](scripts/workstation-restore.sh), [`scripts/install-antigravity.sh`](scripts/install-antigravity.sh))** — snapshot APT packages, Snaps, NPM globals, external recipes, and GNOME settings into plain-text `system/*` manifests, manage `~/.bashrc`, `~/.profile`, and `~/.gitconfig` via [GNU Stow](https://www.gnu.org/software/stow/), and couple the passive `$HOME/zero-cloud-gravity` engine appliance with your personal `Root 0` node (`~/<persona>-profile`) via `zcg workstation-sync` (`zcg-sync`).
2. **Local Google Antigravity 2.0 Governance (`antigravity/`, `templates/`)** — composable frontmatter-free `AGENTS.md` baselines (`<= 18,000` bytes across `universal-base`, `academic-base`, `science-base`, `business-base` + personal workstation rules), 5 deterministic Python 3.14 lifecycle hooks (`SessionStart`, `PreToolUse`, `PostToolUse`, `PostInvocation`, `Stop` with `continuationActive` guard), native `.agents/plugins/<pack>/plugin.json` + `.agents/plugins.json` + `.agents/antigravity-permissions.json` synthesis, 17 reusable skills (`8` global `human-stack` + `8` `context-stack` + `1` `plugin-stack`), and `19` declarative `zcg-template-v1` template packs.
3. **Zero-Cloud Intranet & Personal Cockpits (`src/zcg/cockpit/`)** — Python 3.14 Native ASGI `DeliveryChannel` (`Zone Z1..Z4 × Tier T1..T5`, `--zcg-*` design tokens, `data-zcg-surface="cockpit"`, `HTTP 286` poll control, `runtime_telemetry` bridged to `.agents/telemetry/`) with deterministic localhost port mapping (`8700 + precedence`), `.intranet.local` / `.personal.local` / `.knowledge.local` routing, `3-Scope` JSON feeds, declarative `dual_world_contract` overlays, and `7` editable WCAG 2.2 AA `plugin-stack` Reference Dashboards (`workstation-control-tower`, `corporate-root-hub`, `node-work-cockpit`, `tutor-study-cockpit`, `secops-mcp-guardian`, `knowledge-stewardship-portal`, `sovereign-wallet-cockpit`).
4. **Multi-Layer CLI (`zcg`) & Contextual MCP Server (`zcg-mcp`)** — 39-subcommand tiered CLI (`C1` Discovery + `inspect-remote` + `lint-arch` + `lint-skills` + `check-handoff`, `C2` Lifecycle + `--purpose` / `--from-parent` + `scaffold-plugin-module` + `scaffold-web-app`, `C3` Sovereign Governance, `Subtree`, `OSS` Engine contribution isolation `zcg oss`, and `Workstation` + `stage-showcase` with real-time TTY progress streaming and `--json` automation mode) plus a read-only JSON-RPC 2.0 `stdio` MCP server sealing `rcap1` (`L0 -> L1 -> L2 -> L3`) `zlib + HMAC-SHA256` Merkle context capsules, `citation_receipt` provenance (`E3..E0`), zero-checkout Git `DMCP`/`GRCC` branch projection, and `strictly-read-only` Ephemeral Department Bots.

The table below summarizes the four progressive adoption modes of ZeroCloudGravity:

| Progressive Adoption Mode | Who It Is For | What Executes on Disk (`0` External Servers Required) |
| :--- | :--- | :--- |
| **Mode 1 — Individual Workstation + Personal `Root 0`** | Solo engineer, researcher, or executive on Ubuntu 26.04 | `./install.sh --stow` + `zcg workstation-sync` couples `~/zero-cloud-gravity` (engine) with `~/<persona>-profile` (personal `Root 0` identity, host manifests & `bash`/`git` Stow links). |
| **Mode 2 — Standalone Project + Stack** | Any software, cloud, or research repository | `zcg apply-project <dir> --template <stack>` projects `.agents/rules/`, `.agents/skills/`, `.agents/skills.json`, and non-invasive `.agents/zcg.mk` (`zcg-*`) with `SHA-256` drift tracking. |
| **Mode 3 — Multi-Layer Organization & Knowledge Mesh** | `Root 0 -> Department / Knowledge -> Squad -> Project` | `zcg bootstrap-workspace` + `layers/<child>/` (`zcg subtree`) + `make delegate` / `make complete` / `make consult` (`rcap1` capsules & `.intranet.local` cockpits). |
| **Mode 4 — Engine Contributor (`oss-dev`)** | Maintaining or extending `zero-cloud-gravity` | `make verify` runs the 8-stage deterministic verification gate (`100.00%` isolated `1:1` unit statement & branch coverage across `143` modules). |

> [!IMPORTANT]
> **Objective Engineering Virtues & Live Empirical Benchmarks (`100%` Python 3.14 Stdlib · `0` External Dependencies)**:
> - **Deterministic $O(N)$ Structural Compaction (`rcap1` `L0/L1` + 2D Geometry)**: Enforcing `< 465` lines/file, `H1..H4` hierarchy, 1-line lead sentences, and `> *"...*"` mandate quotes turns Markdown specs into pre-indexed ASTs — achieving **`88.7%` (`L0`, `522` vs. `4,622` tok)** and **`67.0%` (`L1`, `1,523` vs. `4,622` tok)** compaction across `130k+` tokens in **`~16 ms`** (`0` LLM summarization calls, `0` vector DBs, and **`-76.3%` single-envelope `zlib`-first capsule size** at `518–577` chars/capsule). See **[`docs/architecture/05_contextual_mcp_and_capsules.md`](docs/architecture/05_contextual_mcp_and_capsules.md)**.
> - **Content-Addressable Merkle Provenance (`citation_receipt`)**: Every section is pinned by `<layer>::<file>#<slug>@<sha256_16>:<E3..E0>`, enabling $O(1)$ cryptographic drift detection (`CITATION_DRIFT_DETECTED`), `E3 > E2 > E1 > E0` monotonicity proofs (`verify_epistemic_context_claims`), and `Q1..Q4` lifecycle telemetry.
> - **Zero-Checkout C-Backed Git Plumbing (`DMCP` & `GRCC`)**: Multi-branch context projection reads `git ls-tree` / `git cat-file` directly from `.git/objects` (`zero_checkout: true`, `0` working-tree mutations) and chains encrypted capsules under `refs/zcg/capsules/*` without polluting `refs/heads/*`.
> - **Mathematically Verified `1:1:1` Architecture**: `143` production modules (`<= 384` lines/module in `src/zcg/`, `<= 10` modules/package dir, `0` cross-package cycles enforced via `graphlib.TopologicalSorter`) $\leftrightarrow$ `143` `1:1` isolated unit test suites (**`100.00%` isolated unit statement and branch coverage**, `< 2s`) $\leftrightarrow$ `6` normative `E3` architecture specifications (`< 465` lines/file).

---

## 1. Navigation & Progressive Disclosure (`docs/`)

The documentation corpus is organized into 3 progressive-disclosure tiers so humans and AI agents locate exact specifications in $O(1)$:

| Tier | What You Will Find | Guide / Specification |
| :--- | :--- | :--- |
| **Tier 1 (Gateway & Systems Whitepaper)** | Quick-Start paths, 4 role-based entry journeys, Blueprint SVG architecture, `v1.2.0 -> v2.0.0` cryptographic bridge, repository tree, and CLI cheat-sheet. | **[`README.md`](README.md)** *(this file)* · **[`docs/WHITEPAPER.md`](docs/WHITEPAPER.md)** · **[`docs/README.md`](docs/README.md)** |
| **Tier 2 (Act I · Guides 01–03 — Personal Sovereign Constellation)** | Build your isolated personal mesh step-by-step on one machine: **`01` Personal `Root 0` (`~/<persona>-profile` `:8790` + Browser-First Day-0 Setup)** $\rightarrow$ **`02` Personal Tutor (`:8786`, `M1..M4` & `specialty/*` `DMCP`)** $\rightarrow$ **`03` Career (`work` `:8787` + `spinout-project`), Security (`:8785`) & `R3` Treasury Airlock (`wallet` `:8788`)**. | **[`01: Workstation & Day-0`](docs/guides/01_personal_workstation_and_day0_setup.md)** · **[`02: Personal Tutor`](docs/guides/02_personal_tutor_and_academic_progression.md)** · **[`03: Work, Security & Airlock`](docs/guides/03_personal_work_security_and_airlock_pillars.md)** |
| **Tier 2 (Act II · Guide 04 — Scientific & Public Knowledge)** | Scientific Research (`M2..M4`, 4-quadrant `AAA`) and read-only `E3..E0` Public Knowledge Corpora (`gov-*`, `geo-*`, `sci-*` `:8720`, `93.3%–97.0%` `rcap1:L1` + `SQLite FTS5`). | **[`04: Science & Public Knowledge`](docs/guides/04_scientific_and_public_knowledge_corpora.md)** |
| **Tier 2 (Act III & IV · Guides 05–08 — Enterprise Hierarchy & Network of Networks)** | **`05` Enterprise `Root 0` (`:8710`) & Scales (`Startup -> Scaleup -> Regulated`)** $\rightarrow$ **`06` Departments (`:8725`), Company Projects & Public `pro` Portals** $\rightarrow$ **`07` HR/B2B Links & `19`-Pack / `17`-Skill Matrix** $\rightarrow$ **`08` Network of Networks & `1 Machine <-> Distributed Fleet` Isomorphism**. | **[`05: Enterprise Root & Scales`](docs/guides/05_enterprise_root_and_organizational_scales.md)** · **[`06: Depts, Projects & Portals`](docs/guides/06_enterprise_departments_projects_and_portals.md)** · **[`07: Federated Workflows & Links`](docs/guides/07_federated_workflows_and_inter_node_links.md)** · **[`08: Network of Networks`](docs/guides/08_network_of_networks_and_distributed_topology.md)** |
| **Tier 3A (`E3` Normative Architecture Specs)** | `1:1:1` source-test-spec contracts (`Specification:`) across all `143` modules in `src/zcg/`. | **[`01: Core & Manifest`](docs/architecture/01_core_and_node_manifest.md)** · **[`02: Topology & Twins`](docs/architecture/02_triadic_topology_and_twin_surfaces.md)** · **[`03: Governance & CLI`](docs/architecture/03_governance_and_work_ledger.md)** · **[`04: Cockpits & Intranet`](docs/architecture/04_cockpit_and_intranet_surfaces.md)** · **[`05: MCP, Capsules & Bots`](docs/architecture/05_contextual_mcp_and_capsules.md)** · **[`06: Web & API Engine`](docs/architecture/06_web_and_api_application_engine.md)** |
| **Tier 3B (`E2` Reference Playbooks)** | 7-Axis Multidimensional Taxonomy, Cross-Departmental Contextual Algebra (`0..80`), `Human-Stack` Matrix (`85..95`), `19`-pack catalog, `zcg` CLI & `zcg-mcp` JSON-RPC 2.0 schemas, Container/SSH MCP mesh, and Maintainer Extension Guide. | **[`01: Stack, Plugin & Human-Stack Matrix`](docs/reference/01_stack_and_plugin_matrix.md)** · **[`02: CLI, MCP & Security Reference`](docs/reference/02_cli_mcp_and_security_reference.md)** |

### 1.1. Orthogonal Blueprint & 4 Role-Based Entry Journeys (`[CAP-01..CAP-10]`)

Blueprint 01 illustrates how the 4 composable stack groups combine across the `0..100` *Lex Superior* `Node × Layer × Network` lattice:

![Blueprint 01 — Orthogonal 4-Stack Matrix and Triadic Node-Layer-Network Topology](docs/assets/diagrams/01_four_stack_triadic_architecture.svg)

Select the entry journey matching your primary role to reach a running local or remote surface in minutes:

| Operator Role & Perspective | Recommended 5-Minute Entry Command | Live Web & Cockpit Surface Unlocked | Primary Playbook |
| :--- | :--- | :--- | :--- |
| **1. Solo Engineer, Student or Portfolio Owner** | `./install.sh --stow && zcg bootstrap-workspace ~/<persona>-profile --id <persona>-profile --purpose individual-sovereign` | `http://<persona>-profile.localhost:8790/` (Day-0 Setup Studio $\rightarrow$ `profile :8790`, `tutor :8786`, `work :8787`, `security :8785`, `R3` `wallet :8788` + CV `/portal`). | [`Guide 01`](docs/guides/01_personal_workstation_and_day0_setup.md) · [`Guide 02`](docs/guides/02_personal_tutor_and_academic_progression.md) · [`Guide 03`](docs/guides/03_personal_work_security_and_airlock_pillars.md) |
| **2. Scientific Researcher or Corpus Steward** | `zcg bootstrap-workspace ~/Projects/sci-lab --id sci-lab --role knowledge --templates science-base,scientific-methodology,spatial-simulation,knowledge-stewardship-portal` | `http://sci-lab.localhost:8720/` (`93%–97%` `rcap1:L1` compaction, `SQLite FTS5` search, `citation_receipt` provenance, and 2D/3D `Network Atlas`). | [`Guide 04`](docs/guides/04_scientific_and_public_knowledge_corpora.md) · [`Whitepaper`](docs/WHITEPAPER.md) |
| **3. Enterprise Architect, FinOps or SecOps Lead** | `zcg bootstrap-workspace ~/Work/corp-alpha --id corp-alpha-root --role corporate --templates business-base,software-engineering,corporate-root-hub` | `http://alpha.localhost:8710/` (`Workspace /`, `Node Admin /admin` capability policy, `corporate-brand-portal` `.com`, and `.net` `R2` OIDC groups). | [`Guide 05`](docs/guides/05_enterprise_root_and_organizational_scales.md) · [`Guide 06`](docs/guides/06_enterprise_departments_projects_and_portals.md) |
| **4. Open-Source Contributor or Platform Maintainer** | `make setup-dev && make verify && ./scripts/stage-showcase.sh --https-demo` | `13` live showcase nodes (`9700..9790`) + TLS 1.3 `/portal`, `/mcp` `Streamable HTTP`, and keyless Cloud Run CD ([`.github/workflows/cd-environments.yml`](.github/workflows/cd-environments.yml)). | [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`Guide 08`](docs/guides/08_network_of_networks_and_distributed_topology.md) |

Every adoption scale runs over the exact same zero-dependency Python 3.14 Native ASGI engine (`*.localhost` subdomains, `.zcg-compass` spatial orientation, and `rcap1` Merkle capsules) — explore all **`10` real 3-Pane Antigravity captures** across **[`Guide 08 §3`](docs/guides/08_network_of_networks_and_distributed_topology.md)**:

![CAP-08 — Panoramic Synthesis of the Sovereign Network of Networks (:8790 · :8786 · :8720 · :8710)](docs/assets/screenshots/cap_08_network_of_networks_panoramic_synthesis.png)

![CAP-10 — Departmental Plugin SDK (:8725) & Verified Public Corporate Portal (:8720 pro)](docs/assets/screenshots/cap_10_departmental_plugin_and_public_pro_portal.png)

---

## 2. Quick Start: 3 Main Ways to Use ZeroCloudGravity

Choose one of the three adoption paths below depending on whether you need standalone Antigravity governance, full Ubuntu 26.04 workstation management, or multi-layer organizational orchestration.

### 2.1. Path 1: Standalone Google Antigravity 2.0 Setup & Usage

Install global rules (`~/.gemini/config/AGENTS.md`), 5 lifecycle hooks (`hooks.json` + `scripts/`), 8 universal global skills (`~/.gemini/config/skills/`), and the `zcg-mcp` server in `$HOME`:

```bash
git clone https://github.com/mtwuser/zero-cloud-gravity.git ~/zero-cloud-gravity
cd ~/zero-cloud-gravity
./install.sh --profile universal-base --lang en --stow

# Optional: install/upgrade Google Antigravity Agents + agy CLI (or --ide / --all):
./scripts/install-antigravity.sh --agents

# Any time in terminal: synchronize engine runtime, profile & Stow links:
./scripts/workstation-sync.sh --status
```

### 2.2. Path 2: Dual-Repo Ubuntu 26.04 Workstation (`~/zero-cloud-gravity` + `~/<persona>-profile`)

Keep `~/zero-cloud-gravity` as the clean Open-Source engine runtime while managing your personal `Root 0` identity rules, Ubuntu 26.04 packages (`system/*`), and host shell/Git files (`bash/`, `git/`) inside your sovereign repository `~/<persona>-profile` (or couple an enterprise `Root 0` / `Department` node on managed corporate hardware):

```bash
# Phase A — Couple ~/zero-cloud-gravity (engine) with ~/<persona>-profile (personal Root 0):
~/zero-cloud-gravity/scripts/workstation-sync.sh --setup \
  --profile universal-base --lang es --workstation-dir ~/<persona>-profile --auto-sync boot

# Phase B — Capture, audit, or restore your physical Ubuntu 26.04 workstation:
cd ~/<persona>-profile
make workstation-backup    # Captures APT, Snap, NPM, external recipes & GNOME settings into system/*
make workstation-audit     # Verifies 0 drift across Stow symlinks, packages, GNOME, and Git status
make workstation-restore   # Interactive or --all / --packages / --external / --nvm / --gnome / --stow
```

📖 Full details on Browser-First Day-0 Setup, GNU Stow tree unfolding, `.audit-ignore`, Dual-Repo `$HOME` auto-sync (`zcg-sync`), and `machine/<hostname>` branches: **[`docs/guides/01_personal_workstation_and_day0_setup.md`](docs/guides/01_personal_workstation_and_day0_setup.md)**.

### 2.3. Path 3: Multi-Layer Enterprise, Public Admin & Knowledge Mesh

Orchestrate Human-AI governance across **Open Source (`zero-cloud-gravity`) $\leftrightarrow$ `Root 0` (`Public Admin 1..2` \| `Company 10` \| `Individual 90`) $\leftrightarrow$ `Department / Domain-Policy / Knowledge` (`3..45`) $\leftrightarrow$ `Squad / Unit` (`40..60` \| `86..89`) $\leftrightarrow$ `Project / Case` (`80`)**:

```mermaid
flowchart TD
    SUB["Intrinsic Runtime Substrate\n(C-Backed Python 3.14 Stdlib · Ubuntu 26.04 Core)"]
    OSS["Open-Source Engine & Contributor Clone\n(zero-cloud-gravity · ZCG_DEV_REPO_DIR)"]
    APP["$HOME Engine Appliance + Personal Root 0\n(~/zero-cloud-gravity + ~/<persona>-profile · :8790)"]
    CORP["Level 1: Root 0 (Public Admin 1..2 | Enterprise 10 | Individual 90)\n(corporate-root-hub :8710 | workstation-control-tower :8790)"]
    DEPT["Level 2: Statutory, Functional & Knowledge Nodes\n(domain-policy [5..9] | knowledge [20] | department [15..45])"]
    SQUAD["Level 3: Operational Units, Tutors & Delivery Squads\n(squad [40..60] | personal tutor [86..89] · node-work-cockpit / tutor-study-cockpit)"]
    PROJ["Level 4: Application, Case & Cloud Service Projects\n(project [80] · Contextual Human-Stack M1..M4 [85..95])"]

    SUB <-->|"C-Backed Primitives &\nOSS-to-OSS Contributions"| OSS
    OSS -->|"workstation-sync.sh\n(Coupled $HOME Runtime)"| APP
    OSS <-->|"Downward: make sync\nUpward: Anonymized PR (/enrich)"| CORP
    CORP <-->|"Downward: make delegate & make sync\nUpward: make complete & make promote"| DEPT
    DEPT <-->|"Downward: make delegate & make sync\nHorizontal: make consult (rcap1)"| SQUAD
    SQUAD <-->|"Downward: apply-project & make task\nUpward: make complete & /enrich"| PROJ
```

#### 2.3.1. Summary of the 6 Orthogonal Stack & Layer Composition Patterns (`entity_kind × layer_role × stack_groups`)

Every workspace composes inherited `{human,context,tool,plugin}-stack` packs (`templates/*-stack/<pack>/`) with its own sovereign node rules (`templates/<layer-id>/rules/<layer-id>.md`) along the `0..100` *Lex Superior* spectrum:

| Organizational / Epistemic Need | Who Owns the Workspace | Combined Stack Lineage (`0..100` *Lex Superior*) | How It Activates (`1` Command) | Effective Antigravity Agent Persona |
| :--- | :--- | :--- | :--- | :--- |
| **1. Corporate / Departmental Operations** *(Contracts, IP Registries, Ledgers, SOPs)* | `Root 0` (`10`) or `Department` (`5..35`) | `universal-base` $\rightarrow$ `business-base` $\rightarrow$ `corporate-operations` + `templates/<dept>/` | `zcg bootstrap-workspace` / `make sync` | **Normative & SSoT Ledger Auditor** (`corporate-operations`) |
| **2. Scientific / Statutory Knowledge Atlas** *(Axioms, Statutes, Geographic Registries)* | `Knowledge` Node (`gov-*`, `sci-*`, `geo-*`, `org-*`, `20`) | `universal-base` $\rightarrow$ `science-base` $\rightarrow$ `scientific-methodology` + `templates/<atlas>/` | `zcg bootstrap-workspace --role knowledge` | **Epistemic Corpus Steward (`E3..E0` & `citation_receipt`)** |
| **3. Personal Academic Tutor (`M1 -> M4`)** *(Multi-specialty Socratic study hub)* | `Individual` Tutor Sub-Layer (`<persona>-tutor`, `86`) | `universal-base` $\rightarrow$ `academic-base` $\rightarrow$ `academic-curriculum` + `tutor-study-cockpit` | `zcg bootstrap-workspace --templates academic-base,academic-curriculum,tutor-study-cockpit` | **Socratic `M1..M4` Study Coach (`specialty/*` `DMCP`)** |
| **4. Software & Cloud Engineering Squad** *(Microservices, GCP IaC, 100% isolated `1:1:1`)* | `Department` (`25`) / `Squad` (`50`) / `Project` (`80`) | `Corp` (`10`) $\rightarrow$ `science-base` $\rightarrow$ `software-engineering` $\rightarrow$ `google-cloud-iac` | `zcg apply-project <app> --parent-dir <dept> --template google-cloud-iac` | **1:1:1 Software & Google Cloud IaC Architect** |
| **5. Fiduciary SecOps & Legal Guardian** *(Cross-departmental `NIST-01..04` & IP gate)* | `dept-legal-ip` (`5`) or `dept-secops` (`5`) | `science-base` $\rightarrow$ `software-engineering` $\rightarrow$ `nist-csf-security` $\rightarrow$ `secops-mcp-guardian` | `zcg sync-layer --templates nist-csf-security,secops-mcp-guardian` | **Zero-Trust Fiduciary & Ephemeral Bot Orchestrator** |
| **6. Punctual Cross-Layer Consultation** *(Read-only `rcap1` capsule across layers)* | Any consumer workspace | Active workspace + **Ephemeral `rcap1` Capsule (`kr: true`)** | `make consult LAYER=dept-legal-ip QUERY="..."` | **Zero-Residue Read-Only Inter-Layer Advisor** |

#### 2.3.2. Zero-Friction Browser-First Day-0 Setup (`1 Command -> Live Web Studio -> Local Antigravity Chat -> Configured Node`)

Once `~/zero-cloud-gravity` is installed in `$HOME`, every new repository starts with its web UI immediately live in **Pending Initial Setup** mode (`GET /` auto-saving your prompt edits in `.zcg/runtime/onboarding_draft.json` across browsers before you open a chat):

```bash
# 1. Run 1 command in terminal (initializes workspace & starts its local *.localhost web server):
zcg bootstrap-workspace ~/Projects/<persona>-tutor --id <persona>-tutor --purpose academic-tutor --from-parent ~/<persona>-profile

# 2. Open http://<persona>-tutor.localhost:8786/ in your browser -> customize & click "Copy Prompt for Antigravity Chat"
# 3. Open ~/Projects/<persona>-tutor in Antigravity Agents (Projects -> select folder -> New Conversation, IDE optional)
#    or launch the terminal TUI CLI alternative, then paste the prompt and split the integrated browser right:
cd ~/Projects/<persona>-tutor && agy
```

```text
# Ongoing 4-Step Upstream Upgrade & Version Reconciliation (once setup_state == "configured"):
/sopen — Execute the 4-Step Upstream Upgrade & Version Reconciliation Flow:
1. Step 1 (Topology & Horizon Audit): Run make status, make horizon, and make upstream-diff.
2. Step 2 (Zero-Loss Reconciliation): Run make sync STRATEGY=reconcile (preserving templates/<layer-id>/rules/<layer-id>.md while syncing templates/*-stack/*).
3. Step 3 (Selective Stack & Plugin Review): Verify active templates/plugins and confirm make diff (0 drift).
4. Step 4 (Environment Gate & Closure): Validate make env-gate ENV=tst|pre|pro and close via /sclose.
```

---

## 3. Natural Code Evolution, Command Consciousness & Reproducible Metrics

Code structure, CLI commands, and repository health evolve deterministically across three coupled axes:

| Dimension / Lifecycle Point | Reproducible Target Metric / Invariant | Human & Architectural Value Added | Agent Deviation / Drift Signal (Validation Gate) |
| :--- | :--- | :--- | :--- |
| **1. Session Startup & Orientation (`/sopen` / `make status`)** | **`1` CLI call (`< 0.2s`)** returning `entity_identity`, `network_topology`, `work_orchestration`, `runtime_orchestration`, `setup_state`, `horizon`, and `agent_diff` | Eliminates 6–8 slow shell/git/file probes at session start and prevents blind `brain/` scans | Multi-step manual `git`/`ls` probing on startup or mutating read-only upstream templates |
| **2. Context-Window & Compaction (`AGENTS.md` & `rcap1`)** | **`<= 18,000` bytes** global `AGENTS.md` (`universal-base` `~2.6 KB`); **`67%–88.7%` token savings** at `L1`/`L0` (`~16 ms`) | Zero rule eviction under Antigravity's `20,000`-token inline budget; workspaces load only rules matching their active stack lineage | `AGENTS.md > 18 KB`, workspace `.agents/rules/ > 80 KB`, or unindexed `#####` headings |
| **3. Natural Code Maintainability & `1:1:1` Subpackages** | **`<= 384` lines** source cap, **`<= 464` lines** test/doc cap, **`<= 400` lines** root `README.md` cap, `$M_{\text{cluster}} < 1,200$`, and `0` cross-peer `_private` imports | Prevents God Components and coupled cluster drift; every module's `1:1:1` triad (`Spec <-> Test <-> Code`) is discoverable in $O(1)$ | Source file `> 384` lines, doc/test `> 464` lines, cross-peer `_private` import, or missing `Specification:` header |
| **4. Bidirectional `1:1:1` Test Symbiosis (`Unit -> Imp -> E2E`)** | **`100.00%` single-file isolated unit statement + branch coverage (`143/143` modules)**, `# Arrange / # Act / # Assert`, `0-byte` `__init__.py` | Self-documenting executable specs where each `test_<mod>.py` reaches `100.00%` statement and branch coverage in complete isolation | Coverage `< 100%` in single-file isolation, missing standalone AAA markers (`[missing-aaa]`), or non-empty `__init__.py` |
| **5. Inter-Layer Governance & Stage Gates (`dev -> tst -> pre -> pro`)** | **Strict 1-hop horizon**, `4`-role roster (`owner`, `maintainer`, `validator`, `member`) + `consumer`, and $N$-departmental surface consensus | Unifies Business (`Root 0` / `Department` SSoT ledgers & *Lex Superior* `0..100`) and Technical (`Squad` / `Project`) delivery on `feature/<TICKET-ID>-<slug>` | `CROSS_TIER_PROMOTION_BYPASS`, `PATH_CONTAINMENT_VIOLATION`, open `P0` in `tst`, or unchecked `WORKVALI.md` items in `pre` |

---

## 4. Repository Structure (`5 × 5 × 5` Architecture)

The repository tree separates the `antigravity/` Stow module, the `3-Tier` `docs/` corpus, the `19` declarative `templates/` packs, the `7` automation & workstation scripts, and the `143`-module `src/zcg/` engine:

```text
zero-cloud-gravity/
├── antigravity/.gemini/config/        ← GNU Stow module -> ~/.gemini/config/ (AGENTS.md, hooks.json, 5 scripts, 8 global skills)
├── docs/                              ← 3-Tier 1:1:1 documentation corpus (< 465 lines/file)
│   ├── README.md                      ←   Tier 1: Documentation router, 4-Act compositional journey & 19-pack matrix
│   ├── guides/                        ←   Tier 2 (E1): 01..03 Personal, 04 Corpora, 05..06 Enterprise, 07..08 Network of Networks
│   ├── architecture/                  ←   Tier 3A (E3): 01_core, 02_topology, 03_governance, 04_cockpit, 05_contextual_mcp, 06_web_engine
│   └── reference/                     ←   Tier 3B (E2): 01_stack_and_plugin_matrix.md, 02_cli_mcp_and_security_reference.md
├── scripts/                           ← Workstation & CI automation (verify-repo.sh, install-antigravity.sh, stage-showcase.sh, workstation-{sync,backup,audit,restore}.sh)
├── server.json                        ← Official GitHub MCP Registry manifest (io.github.mtwuser/zero-cloud-gravity · pypi/stdio)
├── src/zcg/                           ← Zero-dependency Python 3.14 engine (143 modules, <= 384 lines each, <= 10/dir, 100.00% isolated coverage)
│   ├── core/                          ←   constants.py, manifests.py, markdown_scan.py, epistemics.py, blueprints.py, surface_composer.py, domain.py, sqlite_repo.py, ast_graph.py (9)
│   ├── platform/                      ←   type_registry.py, schema_discovery.py, cdc.py, cvs.py, projection.py, pipeline_router.py, projection_router.py (7)
│   ├── web/                           ←   http/ (6) + auth/ (5) + ui/ (4) + ops/ (4) + capabilities/ (9) + assets/{css,js,img,templates}/ (28)
│   ├── topology/                      ←   identity.py, network.py, posture.py, subtrees.py, exposure.py (5)
│   ├── governance/                    ←   policy/ (8) + work/ (8) + runtime/ (5) + workspace/ (9) (30)
│   ├── cockpit/                       ←   ops/ (10) + routing/ (10) + views/ (10) (30)
│   ├── plugins/                       ←   wallet_ledger.py, wallet_treasury.py, settlement_airlock.py, portal_channels.py, portal_inbox.py, portal_cv.py, public_portals.py + templates/*.html (7)
│   ├── providers/                     ←   oidc_presets.py, cloud_gcp.py, container_edge.py, gemini_decisions.py, antigravity_runtime.py (5)
│   ├── cli/                           ←   parser.py, discovery.py, commands.py, dispatcher.py (4)
│   ├── capsules/                      ←   constants.py, markdown.py, codec.py, citations.py, grcc.py, surfaces.py (6)
│   ├── ephemeral/                     ←   lifecycle.py, spawner.py, briefs.py (3)
│   └── mcp/                           ←   catalogs.py, node_base.py, compaction.py, unfold.py, surfaces.py, federation.py, orchestrator.py, server.py, http_transport.py (9)
├── system/zcg-node.json               ← Sovereign node manifest (schema_version: "zcg-node-v1")
├── templates/                         ← 19 declarative packs across {human,context,tool,plugin}-stack/* (zcg-template-v1)
└── tests/                             ← 143 isolated 1:1 unit suites + tests/imp/test_*_contracts.py + tests/e2e/test_*_journeys.py
```

---

## 5. Lifecycle Hooks, `zcg` CLI & Verification Cheat-Sheet

Daily governance and verification are enforced by 5 Python 3.14 lifecycle hooks (`session_start_orientation.py`, `pre_tool_guard.py`, `post_edit_format.py`, `post_invocation_lint.py`, `stop_verify_tests.py`) and the `zcg` CLI:

```bash
# 1. C1 Discovery, Subtree & Workstation Host Operations:
zcg status [<dir>]                                   # Consolidated < 0.2s node, posture, origin, network & ledger digest
zcg inspect-remote <git-url-or-path> [--branch <b>]  # Inspect remote/local zcg-node-v1 manifest without repo-name heuristics
zcg list-templates [<dir>]                           # Catalog of 19 templates, federated MCPs & ephemeral bots
zcg inspect-horizon [<dir>]                          # 1-hop upstream/downstream radar & actor RBAC profile
zcg compare-upstream [<dir>] [--apply-safe]          # Section-level (#/##) upstream vs. local template diff
zcg diff-project <target-dir>                        # Verify 0 drift between .agents/ and canonical templates
zcg lint-arch [<dir>] [--no-tests]                   # AST Hexagonal Functional Core & 1:1:1 AAA boundary audit
zcg lint-skills [<dir>] [--parent-dir <dir>]         # < 50 ms static security audit (Unicode, curl|sh, egress, paths)
zcg check-handoff [<dir>] --text "<txt>"             # Bidirectional canonical_terms axis alignment & symmetry rebound
zcg consult-layer [<dir>] --layer <id> --query <q>   # One-shot rcap1 consultation against a mounted layer
zcg subtree <list|pull|pull-all|register> [args]     # Manage mounted child/knowledge layers under layers/*
zcg workstation-sync [sync|setup|status|--auto]      # Synchronize ~/zero-cloud-gravity + ~/<persona>-profile + Stow
zcg install-antigravity [--agents|--cli|--ide|--all] # Install/update Google Antigravity binaries & agy CLI
zcg workstation-backup [<ws-dir>]                    # Snapshot APT, Snap, NPM, external & GNOME manifests
zcg workstation-audit [<ws-dir>] [--clean]           # Read-only drift audit across Stow, packages, GNOME & Git
zcg workstation-restore [<ws-dir>] [--all|--stow]    # Provision or restore an Ubuntu 26.04 workstation

# 2. C2 Lifecycle & C3 Sovereign Governance Operations:
zcg set-global-profile <profile> --lang <en|es|it|fr|de|pt> [--workstation-dir <dir>] [--stow]
zcg bootstrap-workspace <dir> --id <id> [--purpose <p>] [--role <role>] [--from-parent <url|dir>]
zcg sync-layer [<dir>] [--strategy reconcile|accept-upstream|merge|keep-local]
zcg apply-project <dir> [--template <pack>] [--service-action install|activate|healthcheck|teardown]
zcg scaffold-plugin-module <plugin-id> <module-name> [--target-dir <dir>] [--overlay]
zcg scaffold-web-app <target-dir> [--id <id>] [--standalone | --parent-dir <node-dir>]
zcg link [<dir>] (--target <id> | --from <url|path>) --relation <lateral-peer|spinout-project|hr-process|b2b-collaboration|knowledge-feed>
zcg unlink [<dir>] --target <id>
zcg spinout-project <target-dir> --from-branch <branch> --id <id> [--templates <csv>]
zcg start-task [<dir>] --task "<id>" [--ticket <id>]
zcg complete-task [<dir>] --task "<id>" [--deliverable <path>] [--create-pr]
zcg delegate-to-child [<dir>] --to-child <layer> --task "<directive>" [--ticket <id>]
zcg promote-from-project <dir> --source <rel-path> [--to-layer <id>] [--create-pr]
zcg check-env-promotion [<dir>] --to-env <tst|pre|pro> [--files <csv>]
zcg oss <push-branch|promote-master|publish> [<dir>] # Isolated Open-Source engine contribution workflow (Makefile oss-*)

# 3. Deterministic 8-Gate Repository Verification Suite:
make setup-dev && make verify                        # Ruff + Mypy --strict + ShellCheck + 100.00% 1:1 isolated unit + imp + e2e + zcg-mcp --self-test
```

---

## 6. Contributing, Security & Open-Source Patronage

Community governance, vulnerability reporting, and independent stewardship follow these repository policies:

- **Contributing & `1:1:1` Verification**: [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) · [`ACCESSIBILITY.md`](ACCESSIBILITY.md)
- **Security Policy & Boundary Isolation**: [`SECURITY.md`](SECURITY.md) · [`LICENSE` (MIT)](LICENSE)
- **Independent Open-Source Patronage**: [`.github/FUNDING.md`](.github/FUNDING.md) *(activated via GitHub **Sponsor** / [`.github/FUNDING.yml`](.github/FUNDING.yml))*
