---
name: continue
description: mid-session checkpoint — safety valve to prevent context loss between tasks
---

# Continue & Progression — `/continue`

> **The unified state-driven progression & checkpoint command (`1 Skill = 1 Verb`).** Inspect workspace state via the Silent Pre-Flight Probe, snapshot progress, anchor on-the-fly lots (`1` lot/turn), clean completed work, deliver pending commit blocks, and advance automatically along the priority chain (`/continue` or `/continue <natural intent>`).

---

## How `/continue` Works (`State-Driven Single Verb + Natural-Language Intent`)

`/continue` operates as a single state-driven conversational verb with **zero nested CLI subcommands** (`1 Skill = 1 Verb`):

| Invocation | Operator Intent | State-Driven Behavior |
| :--- | :--- | :--- |
| `/continue` | *"Save progress, give me any pending commits, and advance to what's next"* | Runs the Silent Pre-Flight Probe (`git status --short`), snapshots `.agents/SESSION.md` & `WORKTASK.md` (`[Lot k/N]`), cleans completed `[x]` work (`Zero-Clutter Invariant`), delivers ready-to-run commit blocks first if uncommitted changes exist (*Safety Margin* pause), or advances along the 4-stage priority & promotion chain (`#0 In-Flight` $\rightarrow$ `#1 WORKTASK.md [Lot k/N]` $\rightarrow$ `#2 WORKROAD.md / BACKLOG.md` $\rightarrow$ `#3 roadmaps/`, §2.6) when the tree is clean, closing with the 4-Line Compass Footer |
| `/continue <natural intent>` | *"Continue with this specific indication, question, or focus"* | Applies **Priority `#0` (In-Flight Precedence)** to honor the operator's natural-language indication directly — anchoring a new on-the-fly lot (`T1 [Lot 1/N]`), answering a read-only status/orientation question with zero file mutations, or scoping commit blocks to a requested repository — without requiring memorized subcommands |

> [!NOTE]
> Because every turn already closes with the **4-Line Compass Footer** (`✅ Done · 📍 Position [Lot k/N] · 👤 Action · ⏭️ Next + Cmds`) and every lot automatically delivers its commit block upon completion, `/continue` never requires nested subcommands (`checkpoint` or `commits`). When uncommitted changes exist, `/continue` delivers the commit block first and pauses promotion (*Safety Margin*, §2.5) until the working tree is clean.

---

## 1. Snapshot Current State & On-the-Fly Lot Anchoring

1. **Update `.agents/SESSION.md`** — prepend new entry or update existing one in place.
2. **Sync task tracker progress** — mark completed sub-items `[x]`, in-progress `[/]`, update metrics.
3. **Priority `#0` — In-Flight Discovery Precedence & 3-Path Safety Valve (`Zero In-Flight Loss`)**:
   - Volatile in-flight reflections, findings, or unpersisted refinements in the active conversation ALWAYS take priority `#0` over already-crystallized items in `WORKTASK.md` / `WORKROAD.md`.
   - Before advancing or closing a checkpoint, secure every in-flight finding via one of 3 paths:
     - **Path A (Immediate Execution — Default)**: Anchor the in-flight finding as `T1` (`[/]`, `[ ] Lot 1/N`, `[ ] Lot 2/N`...) at the top of `WORKTASK.md` and `.agents/SESSION.md` (pushing existing crystallized `T1` down to `T2` without overwriting or breaking it) and execute **strictly `1` lot per turn** (`[Lot k/N]`).
     - **Path B (Deferred Governance Persistence & In-Flight `BACKLOG.md` Smell Capture Loop)**: Whenever a non-blocking smell, scalability threshold ($< 465$ lines, $M_{\text{cluster}}$, `Q4` obsolescence, or policy duplication), or refactoring need outside the active lot's scope (`Collateral Freeze`) is spotted during any task across any node (`Root 0`, `department`, `squad`, `knowledge`, `project`, `tutor`), record it immediately in `BACKLOG.md` (`- [ ] **[BKL-NNN] (<Scope> · <Dedicated Skill: /refactoring | /architecture | /review | /governance>)**: <finding + target files>`) or `WORKROAD.md` without interrupting the active lot, closing the universal tracker loop (`own_node_ledger` $\leftrightarrow$ `inter_layer_exchange`).
     - **Path C (Exploratory Artifact Safety Net)**: If still exploratory, persist it in `.agents/SESSION.md` (`### In-Flight Findings`) or a brain artifact before any context transition.
4. **Silent Pre-Flight Human-Action Probe (`git status --short` / State Check)**:
   - Whenever the previous turn ended with a **Pending Human Action (`👤 Action`)** — such as a `git commit` block, a branch switch, a file/config adjustment, or a `WORKVALI.md` check — **silently verify whether the action was already executed (`git status --short` or target state check)** at the start of the next turn, even if the user replies with a new reflection or does not explicitly say *"Commit done"*.
   - **If already completed**: Never ask the user to confirm it and never re-emit a completed commit/action block — proceed naturally with the user's reflection or next step (and clean completed `[x]` tracker items if the repo is clean).
   - **If still pending**:
     - If the user is exploring a reflection or non-overlapping question: address the reflection naturally and keep the pending action listed under `👤 Pending Human Action` in the 4-Line Compass Footer without blocking the conversation.
     - If the user requests a mutating step or promotion that depends on the pending action being completed first: briefly remind the user that the action is still pending and re-surface the ready-to-run command.
5. **Document context** — if task is partially done, note the exact `[Lot k/N]` stopping point.

---

## 2. Verify Alignment

1. **Re-read task tracker** — confirm no drift from active task scope
2. **Anti-drift check**: Compare work against original task description → flag if drifted
3. **Staleness check**: Scan open items for obsolescence from design changes → flag and propose removal

---

## 2.5. Clean Completed Work (Governance Promotion)

After alignment, scan for **all completed work** — task blocks, backlogs, AND inline work:

### Task Blocks (promoted tasks from backlog)

1. **Detect completion** — task block has ALL sub-items `[x]` (deferred = complete)
2. **Check repos are clean** — if uncommitted changes exist:
   - Deliver commits first (§3)
   - **STOP** — promotion deferred to next `/continue` after commits are clean
3. **If repos are clean** — execute full promotion in ONE step:
   a. **Complete the Task Locally (`make complete`, when delegated or ticketed)** — run `zcg complete-task . --task "<id-or-text>" [--deliverable <rel-path>]` (or `make complete TASK="<id-or-text>" [DELIVERABLE=<rel-path>]`) without `PARENT_SYNC=1` so completion stays strictly inside the current workspace (only pass `PARENT_SYNC=1` when explicitly closing a mounted child subtree delegation from the parent workspace itself).
   b. **CHANGELOG entry** — ONE bullet per feature under `[Unreleased]`. Max 2 lines. User-facing language only — no filenames, test counts, class names.
   c. **Update `docs/`** — ensure all new/modified capabilities are documented in permanent architecture/reference docs.
   d. **Delete the task block** from task tracker (`WORKTASK.md`) + Priority Summary table row.
   e. **Clean active roadmap/backlog** — delete the completed phase/item from `WORKROAD.md` / `BACKLOG.md` (Zero-clutter invariant: never leave completed items or `~~strikethrough~~`).
   f. **Delete implemented phases** from source roadmap in `roadmaps/`. If ALL phases done, delete the file (or archive to `docs/history/`).
   g. **No completed tracking** in the backlog — completed work lives in `CHANGELOG.md` only.

### Inline Work (completed without task block promotion)

> [!IMPORTANT]
> **Catches work implemented directly without task block promotion.** Task block governance only fires
> for promoted tasks. Inline work silently skips governance without this step.

1. **Scan backlog (`BACKLOG.md` / `WORKROAD.md`)** — compare session work (SESSION.md + conversation) against pending items
2. **If any item was fully implemented** without a task block:
   a. Delete the completed item from `BACKLOG.md` / `WORKROAD.md` (Zero-clutter invariant)
   b. Write CHANGELOG entry if user-facing
   c. Delete implemented phases from source roadmap if applicable
3. **MANDATORY** — runs every `/continue` and `/sclose`, regardless of task block state

### Backlogs (standing sections in task tracker)

1. **Delete `### Completed ✅` sections** — historical noise, already in CHANGELOG/git
2. **Delete fully-completed backlog blocks** — no remaining `[ ]` items → delete entire block
3. **Keep only actionable items** — header, context note, and pending `[ ]` items

> [!IMPORTANT]
> **Safety margin**: Promotion NEVER runs in same `/continue` that marks last item `[x]` — uncommitted changes force a commit-first pause. `[x]` items are transient — once promoted, delete them. Completed work lives in CHANGELOG and git only.

---

## 2.6. Priority Chain & Phase Promotion Mechanics (`#0 -> #1 -> #2 -> #3`)

The diagram below shows the canonical 4-stage priority and promotion chain executed automatically by `/continue`:

```
In-Flight Findings (#0 Safety Valve) → Task Tracker (WORKTASK.md) → Active Roadmap / Backlog (WORKROAD.md / ROADMAP.md / BACKLOG.md) → roadmaps/
```

All work plans and tasks are centralized at the repository root:
1. **Priority `#0` — Volatile In-Flight Findings First (`3-Path Safety Valve`)** — live reflections, findings, or unpersisted refinements in the active conversation ALWAYS take precedence over already-crystallized items in `WORKTASK.md` (§1.3).
2. **Priority `#1` — Task Tracker (`WORKTASK.md`) Next** — in-progress (`[/]`) and pending (`[ ]`) tasks promoted from the active roadmap/backlog (`P0` before `P1`), executed strictly `1` lot per turn (`[Lot k/N]`).
3. **Never ask** *"where do you want to continue?"* — the priority chain answers that deterministically.
4. **Hierarchical `1-Hop Parent (RO)` Consultation, Fixed `zcg-mcp` Introspection & Strict Workspace Containment (`make consult`)** — use the fixed `zcg-mcp` server (`workspace_dir="<PROJECT_ROOT>"`) for read-only introspection of the current workspace and its mounted `layers/*`, and when a child layer (`Department`, `Squad`, `Project/Case`) needs normative or structural context from its 1-hop parent (`PARENT_DIR`) or from published peer snapshots mounted inside `PARENT_DIR/layers/<peer>/`, query them **exclusively via `make consult LAYER=<id> QUERY="<keywords>" [PATH_TARGET=<rel-path>] [TIER=pro]`** (`strictly-read-only` `L2` excerpt). **NEVER** run `git -C` or read files directly from external sibling working clones (`*-org/*` or `../*`) outside the current workspace.
5. **Strict Horizon Isolation (`Zero Premature Horizon Mixing`)** — while executing an active milestone `vN` (`WORKTASK.md`), **never** mix, leak, or prematurely introduce concepts, symbols, or promises belonging to a future roadmap horizon `v(N+1)` (`WORKROAD.md` / `roadmaps/`) into source code, templates, tests, or public documentation (`README.md`, `docs/`, `CHANGELOG.md`). Future-horizon architecture is analyzed and refined exclusively inside `roadmaps/*` and `WORKROAD.md` until its milestone is formally promoted to `WORKTASK.md`.
6. **Naming Convention** — Active Roadmap / Backlog items use roadmap/phase prefixes (`R1`, `RV2.1`, `RG.1`, etc.); Task tracker items use prefix `T` (`T1`, `T2`, `T3`…); when promoting to `WORKTASK.md`, assign the next available `T` number.

### Future Roadmap (`roadmaps/`) → Active Roadmap (`WORKROAD.md`)

When `WORKROAD.md` has no pending items for the current stage, or when a new roadmap is scheduled:
1. **Identify** the next future roadmap in `roadmaps/` by priority.
2. **Deep-analysis (Phase 0.5, Mode-Aware)** — before promoting, inspect according to `workspace_mode` (`make status`):
   - **In `technical` or `hybrid` mode**: Codebase & infrastructure audit $\rightarrow$ already-implemented detection $\rightarrow$ implementation strategy $\rightarrow$ added-value discovery.
   - **In `business` mode (`corporate-root` / `domain-policy` / `department`)**: Normative policy & *Lex Superior* (`0..100`) audit $\rightarrow$ Single Source of Truth ledger (`corporate/`) & Traceable ID check $\rightarrow$ cross-surface & 1-hop downstream layer impact strategy.
3. **Present analysis** to the user for review.
4. **Enrich** the roadmap file in `roadmaps/` and add its phase checklist into `WORKROAD.md`.
5. **Keep the source file in `roadmaps/`** while its phases are pending — it serves as the detailed technical specification until all phases are implemented (at which point it is deleted or archived to `docs/history/`).

### Active Roadmap (`WORKROAD.md`) → Task Tracker (`WORKTASK.md`) (Phase by Phase)

When starting work on the next phase in `WORKROAD.md`, promote individual phases/blocks **one at a time** (never the entire roadmap at once; `WORKROAD.md` retains the strategic picture while `WORKTASK.md` holds only the active tactical phase):
1. **Identify** the next pending phase/block within `WORKROAD.md` (or `ROADMAP.md` / `BACKLOG.md`).
2. **Execute Promotion Analysis Checklist (Mode-Aware Reading Priority)** — mandatory research in strict top-down order based on `workspace_mode` (`make status` / `.agents/rules/*.md`):
   - **In `technical` or `hybrid` mode (`software-engineering` / `framework-stack/*`)**:
     - Phase 1: Human guides & normative specifications (`docs/guides/`, `docs/architecture/<spec>.md` `1:1:1` tables, and source file in `roadmaps/`)
     - Phase 2: Self-documenting test hierarchy (`tests/e2e/` persona journeys $\rightarrow$ `tests/imp/` boundary implementation $\rightarrow$ `tests/unit/` 4-quadrant `Test<Module>` suites)
     - Phase 3: Existing source code, staleness (`> 90d`), & consistency analysis (`src/` / `scripts/` — verify new code does not diverge from adjacent existing code; propose atomic refactoring or log in `BACKLOG.md` if touched modules use older idioms or over-compression)
     - Phase 4: Structural evolution (`Inline -> Function -> Class -> Protocol/Catalog -> Module`), file-prefix/suffix naming (`tools_*`, `*_engine`, `NN_*`, `test_*`), & outbound non-restriction alignment
     - Phase 5: Documentation & `1:1:1` traceability persistence plan
   - **In `business` mode (`business-base` / `context-stack/*` / `Root 0` / `Department`)**:
     - Phase 1: Normative policies, *Lex Superior* hierarchy (`0..100`), and full deontic precedence (`1..95`: Public-Admin `Root 0` & Depts `1..4`, Enterprise `Root 0` & Depts/Units `5..80`, Contextual `Human-Stack` `85..95`) in `corporate/`, `docs/`, and `.agents/rules/*.md`
     - Phase 2: Single Source of Truth ledgers (`corporate/`), quantitative/unit precision, and Traceable Ledger IDs (`[DEPT]-[TYPE]-[YYYY]-[NNN]`)
     - Phase 3: Three-Part Functional Verification Structure (`# Scope & Surface Target`, `# Normative Invariants`, `# Verification & Sign-Off Gates`) and IP/confidentiality firewall gates
     - Phase 4: Cross-Surface Cascade (`surfaces/web/`, `surfaces/forms/`, `surfaces/print/`) and 1-hop child delegation needs (`make delegate`)
3. **Cross-task analysis** — if `WORKTASK.md` already has active items: scan active tasks $\rightarrow$ detect relationships $\rightarrow$ analyze dependencies $\rightarrow$ present brief report.
4. **Move** only that phase into `WORKTASK.md` as a `T` item (`T1`, `T2`, etc.) and **mark** the promoted phase in `WORKROAD.md` as `→ promoted to TN`.
5. **Claim & Start the Task (`make task`)**: Run `zcg start-task . --task "<id-or-text>" [--ticket <TICKET-ID>]` (or `make task TASK="<id-or-text>" [TICKET=<TICKET-ID>]`) to mark the item `[/]` in `WORKTASK.md`, record the active task, `Ticket ID`, `Origin Layer`, and branch in `.agents/SESSION.md`, and emit the canonical Git branch command (`git checkout -b feature/<TICKET-ID>-<slug>` when a ticket ID is present, or `git checkout -b task/<slug>`).

---

## 3. Execution Flow & Commit Delivery Rules

### 3.1. State-Driven Progression Flow (`/continue` or `/continue <natural intent>`)

When `/continue` is invoked, execute the following deterministic progression sequence:

1. **Idempotency & Silent Pre-Flight Probe** — verify `git status --short` and target workspace state first; if the user asks a purely read-only orientation question via `/continue <natural intent>`, render the 4-Line Human Compass with zero file mutations; otherwise skip commits if already delivered with no new changes and skip snapshot if unchanged.
2. **Deliver commits first when dirty (*Safety Margin*)** — if uncommitted changes exist, sync `[x]`/`[/]` tracker state, deliver the ready-to-run commit block(s) (§3.2), and pause task promotion until the next `/continue` on a clean tree.
3. **Conversation context & In-Flight Precedence (`Priority #0`)** — if the user provided an actionable natural-language indication or the last interaction concluded with an agreement $\rightarrow$ **anchor (`[Lot 1..N]`) and execute Lot `1` directly**; if no actionable conclusion $\rightarrow$ step 4.
4. **In-progress work (`Priority #1 — WORKTASK.md [Lot k/N]`)** — if `[/]` items exist in the task tracker (`P0` before `P1`), present the exact `[Lot k/N]` status and next bounded lot first.
5. **Automatic Priority & Promotion Chain (`Priority #2..#3`, §2.6)** — when the active task is complete on a clean tree (or no `[/]` task is in progress), automatically execute the promotion chain (`WORKTASK.md` $\rightarrow$ `WORKROAD.md` / `BACKLOG.md` $\rightarrow$ `roadmaps/`) to promote and claim (`make task`) the next phase.
6. **Present next task & 4-Line Compass Footer** — user approves ($\rightarrow$ execute) or closes:
   - **✅ Functional Summary (`What has been done`)**: Concise functional summary of completed lots in the active session/task (clearly distinguishing committed vs. uncommitted work).
   - **📍 Current Position (`Where we are — [Lot/Step k of N]`)**: Active ticket/task ID in `WORKTASK.md` and exact lot/step position (including any on-the-fly lots).
   - **👤 Pending Human Action (`What needs human action`)**: Pending `git commit` block, architectural approval/decision, manual validation item in `WORKVALI.md`, or `0 blocking actions`.
   - **⏭️ Next Step & Contextual Commands (`Where we are going`)**: The immediate next bounded step (`1` lot) and 2–3 contextual commands relevant to the current state (`/continue`, `/review`, `/sclose`).

> [!IMPORTANT]
> **Conversation context (`Priority #0`) always wins.** `/continue` applies the priority chain automatically in order (`#0 In-Flight` $\rightarrow$ `#1 WORKTASK.md` $\rightarrow$ `#2 WORKROAD.md / BACKLOG.md` $\rightarrow$ `#3 roadmaps/`).

### 3.2. Commit Delivery & Pre-Commit Verification Rules

#### Pre-Commit Verification Checklist

Answer these 4 verification questions before generating any commit block:

> [!IMPORTANT]
> **Before writing ANY commit**, answer these 5 questions:
> 1. Which repos did I actually edit files in?
> 2. Did I already deliver commits earlier? → only include repos with NEW changes since.
> 3. Did I remove all completed items from `BACKLOG.md` / `WORKROAD.md`? (§2.5 Inline Work — Zero-clutter invariant)
> 4. Is SESSION.md updated and saved?
> 5. Have **100% of background tasks (`task-NNNN`) and the full Stop-Hook test suite (`pytest -q -x` / `make verify`) already finished with exit code `0`**? (NEVER emit a commit block while any test/validation is still running or after running only a partial subset of unit tests when `.py` or rule files changed.)

#### Strict Rules

Enforce the following 12 rules whenever delivering commit blocks:

1. **NEVER run mutating git commands** — no `git add/commit/push/amend`. User handles all git mutations.
2. **At-Stop Commit Delivery Gate (`Zero In-Flight Tasks -> Full Stop-Gate Verified -> Summary -> Commit Block -> 4-Line Compass`)**:
   - **Never emit a `git commit` block while any background command or verification task (`task-NNNN`) is still running**: If `make verify` or `pytest` backgrounds due to `WaitMsBeforeAsync`, end the turn with a brief 1-line progress note (*"Waiting for verification task to finish..."*) and **zero commit blocks** until the background task completes with exit code `0`.
   - **Always run the full Stop-Hook gate (`venv/bin/pytest -q -x` or `make verify`) to completion before emitting a commit block**: When `.py`, `.sh`, or rule files (`universal-base.md`, `academic-base.md`, `science-base.md`, `software-engineering.md`, `business-base.md`) are edited, running only isolated unit tests is insufficient because `stop_verify_tests.py` runs the full `pytest -q -x` suite on turn termination (and will wake the agent back up if an `imp`/`e2e` test fails after the user already copied the commit block).
   - **Strict End-of-Turn Ordering (`Always at Full Stop`)**: Deliver the commit block **only at a full verified stop**, strictly placed **with or after the functional or checkpoint summary** (`1. All Tests and Validations Finished (0 In-Flight) -> 2. Tracker Sync ([x] or [/]) -> 3. Functional or Checkpoint Summary -> 4. Commit Block -> 5. 4-Line Compass Footer`).
3. **Silent Pre-Flight Probe (`git status --short` / State Check)** — before assuming a previous commit or human action is still pending, silently verify the workspace state (`git status --short` or artifact check). If already executed, never ask the user for confirmation and never repeat the commit block; if still pending, note it in the 4-Line Compass Footer (or request it only when a dependent step requires a clean tree).
4. **ONE commit per repo** — never split.
5. **Format & Pre-Commit Target Discovery** — resolve `<PROJECT_ROOT>` from workspace metadata, dynamically detect sub-repos, and verify the exact branch name (`git branch --show-current`, never assuming `main` vs `master`) and role-specialized `Makefile` targets (`make verify` in software/technical repos vs. `make diff && make horizon && make mcp-test` in `corporate-root`/`department`/`squad` workspaces) before chaining verification or push commands. **NEVER** append `(vX.Y.Z)` to working commit messages, **NEVER** bump `VERSION` mid-iteration, and **NEVER** include `git push` by default unless the user explicitly asks to push or runs `/release` (`skills/release/SKILL.md`):

```bash
### <Root Repo>
cd <PROJECT_ROOT>
git add -A
git commit -m "<summary of ALL root changes>"

### <Sub-Repo>
cd <PROJECT_ROOT>/<sub-repo>
git add -A
git commit -m "<summary of ALL sub-repo changes>"
```

Same pattern for any additional sub-repos when applicable.

6. Commit message = concise summary, not a list. No commentary around commits.
7. **Sub-repos are INDEPENDENT nested repos, NOT submodules.** Listed in `.gitignore`. NEVER stage a sub-repo from root.
8. **Staging Tracked vs. New/Ignored Paths (`git add -u && git add <new_path>` — NEVER `git add -u <untracked_path>`) & Local `.agents/SESSION.md` (`Zero Force-Track on .agents/*`)**:
   - **Never force-track `.agents/SESSION.md` (`0` `git add -f .agents/SESSION.md`)**: The entire `.agents/` directory (including `.agents/SESSION.md`, `.agents/LAYER_LINEAGE.md`, `.agents/rules/`, `.agents/skills/`, and `.agents/telemetry/`) is strictly **local machine & operator state** (holding the local `conv-id` pointer to `~/.gemini/antigravity/brain/<conv-id>` and the operator's personal `Human-Stack:` facets). Portable cross-machine continuity lives in `WORKTASK.md` (`[Lot k/N]`), `WORKROAD.md`, `BACKLOG.md`, and `CHANGELOG.md`.
   - If a repository force-tracks root governance files listed in `.gitignore` (such as `WORKROAD.md`, `WORKTASK.md`, `WORKVALI.md`, `BACKLOG.md`, or `roadmaps/*.md`), use `git add -u` so already-tracked root governance files stay staged without touching `.agents/*`.
   - **When staging new/moved untracked files or directories alongside tracked changes**: **NEVER** pass an untracked pathspec to `git add -u` (`git add -u <new_path>` fails with `error: pathspec '<new_path>' did not match any file(s) known to git`). Always chain a separate command: `git add -u && git add <new_path>` (or `git add -u && git add -f <new_ignored_file>`).
9. **Commit frequency**: after each plan execution, after accumulated changes, before session end.
10. **Sync task tracker before commits** — mark `[x]`/`[/]` sub-items first.
11. **Global config repo (`ZCG_DEV_REPO_DIR` $\rightarrow$ `$HOME` Workstation Sync)** — if `zero-cloud-gravity` engine/rule/skill files were modified in the contributor development clone (`ZCG_DEV_REPO_DIR` / `~/Projects/dev-<repo>`), deliver a single commit block that chains `&& ~/.local/bin/zcg-sync --sync` (`cd <DEV_REPO_PATH> && git add -u && git commit -m "..." && ~/.local/bin/zcg-sync --sync`). This commits in `dev` and automatically propagates, reconciles, and re-stows the workstation repository (`ZCG_WORKSTATION_DIR` in `~/.config/zero-cloud-gravity/workstation.conf`) without hardcoding `$HOME` repository names or requiring a second manual commit block.
12. **`.agents/SESSION.md` preservation** — never delete `.agents/` in-place (`rm -rf .agents`) in an active workspace (e.g. when simulating clean CI checkouts), as `.agents/` is gitignored and holds `.agents/SESSION.md` (Tier 2 session state). Always isolate clean-checkout tests via temporary rename (`mv .agents .agents.bak` $\rightarrow$ test $\rightarrow$ `mv .agents.bak .agents`) or an ephemeral worktree.

> [!IMPORTANT]
> **Auto-commit after plan execution**: When plan finishes (all `[x]`), deliver commits **immediately** as final step — snapshot → sync task tracker → commits → present next step. Never require the user to invoke `/continue` just for commits.

---

## 4. Rules & Mandatory End-of-Turn 4-Line Compass Footer

- **NEVER skip the snapshot** — persist state before advancing (unless answering a purely read-only orientation question via `/continue <natural intent>`)
- **NEVER start new work** without presenting pending items first
- **NEVER execute $\ge 2$ on-the-fly lots without anchoring them in `WORKTASK.md` first** — execute strictly `1` lot per turn (`[Lot k/N]`)
- **SESSION.md is mandatory** — the lifeline for session continuity
- **Task tracker sync before ANY commit** — even ad-hoc requests must sync `[x]`/`[/]` first
- **Plan execution = one fluid unit per lot** — implement `1` lot, verify (`1:1:1`), deliver commit block, and present next lot (`[Lot k+1/N]`)
- **Mandatory 4-Line Compass Footer (`100%` of turns)** — end **every** turn (analysis, lot implementation, commit delivery, or checkpoint) with the 4-line Human Compass (`✅ Functional Summary` · `📍 Current Position [Lot k/N]` · `👤 Pending Human Action` · `⏭️ Next Step + Contextual Commands`)
- **Idempotent** — no repeated commits if nothing changed since last delivery
