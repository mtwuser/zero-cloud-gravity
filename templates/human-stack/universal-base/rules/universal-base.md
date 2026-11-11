---
trigger: always_on
description: Universal cognitive, organizational, and ZeroCloudGravity orchestration rules applying to all workspaces
---
# ZeroCloudGravity Universal Rules (`universal-base` Global Baseline)

> Universal cognitive, organizational, and `ZeroCloudGravity` orchestration rules for ALL workspaces. Domain rules layer via **`academic-base`**, **`science-base`** (`context-stack/software-engineering`), and **`business-base`**.

---

## Agent Behavior

- **Description**: Universal behavioral mandates, mindset, and execution rigor
- **Applies**: Always

### Agent Behavior Manifesto

Verify these mandates before proposing solutions or modifying files:

#### 1. Reusability First, Orthogonal Taxonomy (`X × Y`) & Symmetry-Asymmetry Gate
**Mandate:** Scan (`grep`/semantic) before creating functions, templates, or policies; compose orthogonal axes (`entity_kind × layer_role × stack_groups`, `0` flat case enums or heuristics); disambiguate axes (`1 Skill = 1 Verb` in `SKILL.md` vs. `Makefile` flags) or log in `WORKTASK.md` / `BACKLOG.md`.

#### 2. Professional Robustness & Modularity
**Mandate:** Keep source (`<= 385` target), test, root `README.md`, `docs/**/*.md`, and `corporate/**/*.md` `< 465` lines; extract modules, `docs/guides/`, or specs before `465` lines.

#### 3. Verification & Quality Integrity
**Mandate:** No task is complete while verification (`make verify`, `zcg diff-project`, `audit_node_drift`), linters, strict typing, or compliance checks report errors/warnings (`ZCG_NO_BROWSER=1`).

#### 4. Atomic Deliverable & Verification Inclusion
**Mandate:** Pair every change with active-layer verification (`AAA` tests, `corporate/` gates, or `verify-mastery`) and verify Markdown links (`Spec <-> Verification <-> Deliverable`).

#### 5. Specification Hierarchy & Purpose-Scoped Ripple
**Mandate:** Run `make status` first, follow **`1. Guides/Specs -> 2. Verification/Tests -> 3. Execution`**, treat `docs/`/specs as supreme law, and propagate across active surfaces (`academic-base`, `business-base`, or `science-base`).

#### 6. Continuous Consolidation
**Mandate:** Update `WORKTASK.md`, `BACKLOG.md`, `CHANGELOG.md`, and guides after each phase (`-> /continue`, `/sclose`).

#### 7. Zero-Backward Law & Atomic Structural Cutover (`[WIRE]` / `[CONSOLIDATE]` / `[PRUNE]`)
**Mandate:** Reserve `"migration"` for DB schemas; execute reorganizations via `[WIRE] -> [CONSOLIDATE] -> [PRUNE]` (`0` shims or duplicates), verifying **both paths (`find`/`rglob`) and contents (`grep`)** plus `git log -S` + `docs/` before deleting.

#### 8. Pre-Commit Hygiene & Zero-Literal Exclusion (Anti-Streisand Gate)
**Mandate:** Before commits: (1) **Pesticide Scan** (delete scratch files); (2) **Side-Effect Coherence** (`make status|diff|verify`); (3) **Sterile Root** (`git status --short`); (4) **Multi-Repo Parity** (`CHANGELOG.md`, `README.md`, tests); (5) **ISO-Neutral Examples** (`0` private IDs/credentials; use `gov-iso`, `geo-iso`, `[ISO-NNNN]`, `Record #NNN`).

#### 9. In-Flight Precedence (`#0`), `human-stack` (`M1..M4`), Bounded Lots & 4-Line Compass (`Human <-> AI`)
**Mandate:** (1) **Priority `#0` & 3-Path Valve**: In-flight findings override `WORKTASK.md`; secure via **(a) Immediate** (`T1 [Lot 1..N]`), **(b) Governance** (`WORKTASK.md`/`WORKROAD.md`/`BACKLOG.md`), or **(c) Artifact** (`SESSION.md` / brain). (2) **`human-stack` (`M1..M4`) & Bounded Lots (`3–5` files/lot, `1` lot/turn)**: Adapt via `human_stack` (`M1..M4` + `{domain,bridge,soft,hat}-*`), walk personas, and execute `1` lot/turn (`0` lossy Markdown compression). (3) **4-Line Compass & Silent Probe**: Close every turn with `✅ Done · 📍 [Lot k/N] · 👤 Action · ⏭️ Next`; probe `git status --short` silently so completed `👤 Action`s proceed automatically. (4) **Horizon Isolation & `BACKLOG.md`**: Keep future horizons in `BACKLOG.md` / `roadmaps/`; log non-blocking smells (`Collateral Freeze`) in `BACKLOG.md` (`[BKL-NNN]`).

#### 10. Documentation Coherence, 2D Disclosure, Closed-Loop Knowledge & `L1` Exon Readiness
**Mandate:** (1) **3-Tier & 2D Disclosure**: `README.md` ($\le 400$ lines) $\rightarrow$ `docs/guides/*.md` (`E1` `M1..M4`) $\rightarrow$ `docs/{architecture,reference}/*.md` (`E3/E2` `1:1:1`). Conceptual columns left, file/test pointers right; order `#..####` (`0` `#####`) with a **1-line lead sentence** before tables/diagrams/code and **`###` subsections**. (2) **Closed-Loop Knowledge**: Link via `citation_receipt` (`<layer>::<file>#<slug>@<digest16>:<E3..E0>`) and `l3_targets`; consume via `zcg-mcp` `rcap1` (`L0..L3`), `consumer_viewpoint`, `GRCC`/`DMCP`, and `Q1..Q4` telemetry.

#### 11. 3-Tier Rule Propagation, Two-World Contract, 3-Scope Commands & Hook Gates
**Mandate:** (1) **Two-World Contract**: Tier 0 (`$HOME` = `universal-base`) $\rightarrow$ Tier 1 (`{academic,business,science}-base`) $\rightarrow$ Tier 2 (`{context,framework,plugin}-stack/*`). Keep inherited templates **read-only for local specifics** (edit only for `/enrich` $\rightarrow$ `make promote`); author node rules in `templates/<layer_id>/rules/<layer_id>.md` + `AGENTS.md` (`skip_id = layer_id`). (2) **3-Scope Routing**: Intra-Node (`/sopen|/continue|/sclose|/review`), 1-Hop Inter-Layer (`/governance|/enrich`), and Global OSS (`/audit|/architecture|/release`). (3) **Hook Gates (`pre_tool_guard.py`)**: Claim via `make task`, close via `make complete`; blocks automated mutating Git, edits to `.agents/rules/layer-*.md`, and writes (`> 0 bytes`) to `{src,tests}/**/__init__.py`.

#### 12. Model Delegation Discipline (`flash` vs `inherit` vs `pro` & 4-Channel Digest)
**Mandate:** Use `flash` (`// delegate: flash`), `inherit` (architectural), `pro` (deep/`L3`). Require a **4-channel digest**: (1) **Domain State**, (2) **Affected Surface**, (3) **Invariants & Constraints**, (4) **Actionable Delta**.

#### 13. Language Purity, Semantic Naming Synthesis & Pre-Edit Scope Gate
**Mandate:** (1) **Dual-Plane Language Purity (`Interaction Language: English (en)`)**: Respond in `Interaction Language` (`--lang <en|es|it|fr|de|pt>`); keep repo artifacts in 100% English. (2) **Factored Naming**: Factor shared suffixes (`{human,context,framework,plugin}-stack`). (3) **Pre-Edit Blueprint**: Present target files/symbols before edits. (4) **Collateral Freeze**: Never modify untouched files in the same turn; log in `BACKLOG.md`.

---

## Governance (Universal)

- **Description**: Commit discipline, priority chain, and global config persistence
- **Applies**: Always

### Commit Discipline
1. **NEVER run mutating git commands** (`git add|commit|push|commit --amend|reset`) automatically.
2. **ONE commit/repo** via Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`).
3. **Independent repos**: Emit 1 block/repo (`cd <REPO_PATH> && git add ... && git commit -m "..."`).
4. **At-Stop Delivery (`0` In-Flight)**: Wait until all tests/tasks (`make verify`) finish, sync trackers, and emit commits ONLY at full stop.
5. **Staging**: Use `git add -u` (`&& git add <new_path>` or `&& git add -f <ignored_file>`; **NEVER** `git add -u <untracked_path>`).
6. **Releases (`[Unreleased]`)**: **NEVER** bump `VERSION`/`pyproject.toml`/`README.md` or chain `git push`; log under `## [Unreleased]` in `CHANGELOG.md` and release via `/release`.

### Priority Chain & Global Config Persistence
- **Priority Chain**: (0) **In-Flight (3-Path Valve)** $\rightarrow$ (1) `WORKTASK.md` $\rightarrow$ (2) `WORKROAD.md` / `BACKLOG.md` $\rightarrow$ (3) `roadmaps/`.
- **Global Config & Skills**: `$ZCG_RUNTIME_DIR` + `$ZCG_WORKSTATION_DIR` (`~/<user-pc>`); sync via `zcg-sync --sync` and promote via `/enrich` $\rightarrow$ `make promote`.
