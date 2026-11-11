---
name: sopen
description: restore session state and initialize workspace — first command in every conversation
---

# Session Open — `/sopen`

> **Run this FIRST** in every new conversation. It restores context, applies governance rules, and presents the current state.

---

## 0. Single-Shot Global Sync & Consolidated Workspace Status

// delegate: flash
1. **Run ONE combined command** in `<PROJECT_ROOT>` to synchronize the workstation runtime (`$ZCG_RUNTIME_DIR` / `~/<user-pc>`) and collect the entire workspace status digest in `< 0.2s`:
   ```bash
   ~/.local/bin/zcg-sync --sync 2>/dev/null || true
   ~/.local/bin/zcg status "<PROJECT_ROOT>"
   ```
   *(If `Makefile` defines `status:`, `make status` runs `zcg status` with `PARENT_DIR` automatically.)*
2. **Parse the returned JSON digest** — it provides in a single call:
   - `operating_state` (`"oss-readonly-appliance"` | `"oss-dev"` | `"individual-root"` | `"corporate-root"` | `"domain-policy"` | `"department"` | `"squad"` | `"project"`), `workspace_mode` (`"business"` | `"technical"` | `"hybrid"`), `layer_id`, `layer_role`, `precedence`, `active_templates`, `active_rules`, and `command_tiers` (`auto_reflexive`, `guided_tactical`, `conscious_human_gated`)
   - **Read-Only Appliance vs. Personal Sovereign Hub Gate**: If `operating_state == "oss-readonly-appliance"` (`mode=readonly`), warn immediately that `$ZCG_RUNTIME_DIR` is a read-only runtime appliance and redirect any authoring to `ZCG_DEV_REPO_DIR` (`make setup-dev`). When `operating_state == "individual-root"` (`~/<user-pc>`, `mode=private`), the operator's personal `$HOME` hub is mutable for personal tasks, `Human-Stack`, and mounted `layers/*` knowledge nodes, while upstream `zero-cloud-gravity` engine/base edits still belong in `ZCG_DEV_REPO_DIR`.
   - `has_project_start_skill` (`bool` — if `false`, do NOT search for `.agents/skills/start/SKILL.md`)
   - `setup_state` (`state`: `"uninitialized"` | `"pending_customization"` | `"configured"`, `is_configured`, `layer_role`, `topological_class`, `entity_kind`, `orthogonal_dimensions`, `kickoff_prompt`, `next_action`)
   - `session_state` (`exists`, `last_conversation_id`, and `excerpt` of `.agents/SESSION.md`)
   - `priority_state` (`active_tracker` and `excerpt` of `WORKTASK.md` / `WORKROAD.md` / `ROADMAP.md` / `BACKLOG.md` / `README.md`)
   - `git_state` (`is_git_repo`, `status_short` including branch and ahead/behind status, `recent_commits`)
   - `horizon` (`oss_root_version`, `upstream_version`, `workspace_version`, `downward_sync_needed`, `child_sync_needed`, `shared_template_drifts`, `downstream_layer_drifts`, `upward_promotion_suggestions`)
   - `git_governance` (`current_branch`, `active_environment`, `makefile_outdated`, `manifest_contracts_outdated`, `staged_proposals`, `stale_proposals`)
   - `agent_diff` (`in_sync`, `modified_in_project`, `novel_in_project`)
3. **Assisted Upgrade Reconciliation (`make sync`) & Automatic Session Plugin Activation (`make activate-plugin`)**:
   - **If `horizon.downward_sync_needed`, `horizon.child_sync_needed`, `git_governance.makefile_outdated`, or `git_governance.manifest_contracts_outdated` is `true`**, run `make sync` (or `~/.local/bin/zcg sync-layer "<PROJECT_ROOT>"`) using the default non-destructive `--strategy reconcile`. This self-heals generated `# Role-Specialized Layer Makefile` targets in place (preserving any `# --- Custom Targets ---` block), normalizes `zcg-node-v1` / `squad` manifest contracts, and updates unmodified upstream template packs and mounted child layers (`layers/*`).
   - **If the workspace has any installed `plugin-stack` runtime plugin** (in `active_templates` or `runtime_orchestration.static_runtime.plugins`), run `make activate-plugin` (or `~/.local/bin/zcg apply-project "<PROJECT_ROOT>" --service-action activate`) so the node's 3-Scope Data Topology (`surfaces/data/{node,network,federation}_scope.json`) and Cockpit Web (`surfaces/web/index.html`) are refreshed and served live in the background (`http://127.0.0.1:<port>/?env=<env>` + `active_subdomain_url`) for the duration of the session.
   - **If `reconciliation_conflicts` or `git_governance.staged_proposals` (`from-upstream/*`) are present**, run `make upstream-diff` (`~/.local/bin/zcg compare-upstream "<PROJECT_ROOT>"`) to inspect section-level differences (`upstream_only_sections`, `local_only_sections`, `diverged_sections`) and ask the user which reconciliation strategy to apply:
     - `make sync STRATEGY=accept-upstream` — adopt the upstream template pack in full
     - `make sync STRATEGY=merge` — adopt upstream updates while preserving local-only `# / ## / ###` rule sections
     - `make sync STRATEGY=keep-local` — keep local rule customizations untouched and clear the staged proposal

> [!NOTE]
> This single-command pre-flight replaces separate calls to `make horizon`, `make diff`, `git status`, `git log`, `.agents/SESSION.md`, and tracker file probes.

### 0.1. Interactive First-Time Setup & On-Demand Re-Customization (`setup_state`) Across Orthogonal Dimensions (`X × Y`)

Inspect `setup_state.state` from the Step 0 JSON digest (plus any user customization arguments passed to `/sopen`):

1. **State `U0` (`setup_state.state == "uninitialized"` — Freshly Cloned / Unbootstrapped Repository)**:
   - **If the user invoked `/sopen` with an adapted Kickoff Prompt** (already specifying the repository's mission, `layer_role`, `--templates`/plugins, or `gov-*/geo-*/sci-*/org-*` knowledge mounts): do **NOT** stop to ask redundant wizard questions. Infer the orthogonal coordinates directly from the prompt, execute `~/.local/bin/zcg bootstrap-workspace "<PROJECT_ROOT>" --id <id> --role <role> --precedence <prec> [--parent-dir <parent-dir>] --templates <templates-and-knowledge-ids>` (which automatically installs, activates, and opens the role's default Node Cockpit plugin in the browser on initial setup, plus `set-authority --emails "<owner-email>,$(git config user.email)"` so the local Git operator remains in the owner list, and English technical terms/proper nouns in `make consult QUERY="..."` per `artifact_language: "en"`), re-read `setup_state`, and execute **State `U1` (`Phase A -> Phase D`)** immediately in the same turn so `setup_state.state` transitions directly to `"configured"`, **keeping the Node Cockpit daemon active (`daemon_active: true`) — do NOT run `/sclose` (`make deactivate-plugin`) during initial `/sopen` onboarding** so the user can immediately use the live browser cockpit!
   - **If the user invoked bare `/sopen` (with no arguments)**: ask the user to select the repository's **orthogonal coordinates (`setup_state.orthogonal_dimensions`: `entity_kind × layer_role × stack_groups`)** and core parameters:
     - **`entity_kind`**: `"individual"` (`workstation` `0`, personal layers `85..95`), `"enterprise"` (`5..84`), `"public-government"` (`1..4`), or `"open-source"`
     - **`layer_role` (`topological_class`)**:
       - `workstation` (`runtime-node` — Personal `Root 0` Workstation `~/<persona>-pc`: `init-fork --id <persona>-pc --role workstation --precedence 0 --entity-kind individual`)
       - `corporate` (`governance-layer` — Collective `Root 0`: `bootstrap-workspace --id <root-id> --role corporate --precedence <1..15> --templates ...`)
       - `domain-policy` or `department` (`governance-layer` — Transversal Policy `5..25`, Functional Department `20..35`, or Individual Specialty Node `85..95` governed by `--parent-dir <root-dir>`: `bootstrap-workspace --id <id> --role <domain-policy|department> --precedence <prec> --parent-dir <parent-dir> --templates ...`)
       - `squad` (`governance-layer` — Execution Unit `40..60`: `bootstrap-workspace --id <squad-id> --role squad --precedence 50 --parent-dir <dept-dir> --templates ...`)
       - `knowledge` (`knowledge` — Curated Epistemic/Normative Corpus `gov-*`, `sci-*`, `geo-*`, `org-*`: `bootstrap-workspace --id <know-id> --role knowledge --precedence <1..30> [--parent-dir <root-dir>] --templates ...`)
       - `project` (`consumer-workspace` — Consumer Application at Level 4: `apply-project <dir> [--parent-dir <parent-dir>] --template ...`)
   - Execute the selected `~/.local/bin/zcg` command, re-read `setup_state`, and proceed immediately to **State `U1`** below in the same turn.
2. **State `U1` (`setup_state.state == "pending_customization"` — Bootstrapped Skeleton Pending Initial Purpose Customization)**:
   - Present the resolved orthogonal coordinates (`setup_state.entity_kind`, `setup_state.layer_role`, `setup_state.topological_class`), summarize the `[Fill: ...]` blueprint fields in `README.md` or `.agents/LAYER_LINEAGE.md` (mission, owner email, branch topology `specialty/*` or `env/*`, `Human-Stack` `M1..M4`, mounted `knowledge` nodes), and **print directly in the chat the pre-adapted `setup_state.kickoff_prompt` inside a copyable block** so the user can copy, adapt, and launch it (or simply confirm in chat to execute it).
   - Once the 4-Phase Kickoff customization (`Phase A -> Phase D`) completes, replace all `[Fill: ...]` placeholders in `README.md` / `.agents/LAYER_LINEAGE.md` and mark `- [x] Complete Layer Setup Blueprint in README.md and run Kickoff Prompt.` in `WORKTASK.md`. This permanently transitions `setup_state.state` to `"configured"` so future `/sopen` runs skip the initial setup wizard automatically.
3. **State `U2` (`setup_state.state == "configured"` — Normal Operation + On-Demand Re-Customization)**:
   - **Default (`/sopen` with no customization intent)**: Skip the setup wizard and proceed directly to Step 1 (`< 0.2s` fast session recovery).
   - **On-Demand Re-Customization (`/sopen <customization intent>`)**: When the user invokes `/sopen` requesting a configuration change (e.g., adding a new `specialty/<track>` branch, mounting a `gov-*/sci-*/geo-*/org-*` `knowledge` node, enabling/pruning a `plugin-stack` plugin, changing `--lang`, or updating `templates/<layer_id>/rules/<layer_id>.md`), run the guided customization update (`make sync` / `make apply-template` / branch setup) and verify `make diff` (`0` drift).

---

## 1. Recover Conversation Context (Tier 1 — richest source)

// delegate: flash
1. **Check `session_state.last_conversation_id`** from the Step 0 JSON digest:
   - **If `last_conversation_id` is non-null**: read `~/.gemini/antigravity/brain/<last_conversation_id>/task.md` (and `walkthrough.md` / `implementation_plan.md` if present) directly by path.
   - **If `last_conversation_id` is `null`** (fresh workspace or `.agents/SESSION.md` was just initialized): **skip `brain/` scanning completely** — do NOT run `ls -lt ~/.gemini/antigravity/brain/` or inspect conversations belonging to other workspaces.
2. **If `.agents/SESSION.md` lists a separate entry for the current hostname**, read that conversation's `brain/<id>/task.md` directly as well.

> [!IMPORTANT]
> When `last_conversation_id` is present in `.agents/SESSION.md`, `brain/<last_conversation_id>/` is the **primary source of truth** for what was done in the previous session. Never blind-scan unrelated `brain/` directories when `last_conversation_id` is `null`.

> [!NOTE]
> **New machine / fresh clone**: Both `brain/` (Tier 1) and `.agents/SESSION.md` (Tier 2) are **local to the machine/operator** (`.agents/` is gitignored and never force-tracked in Git so team members and parallel machines never collide on local session logs or personal `Human-Stack` profiles). On a new machine or fresh clone, **Tier 3 (`git_state` + `priority_state`: `WORKTASK.md` with exact `[Lot k/N]` status, `WORKROAD.md`, `BACKLOG.md`, `CHANGELOG.md`, and `git log`)** is the portable cross-machine ground truth and is 100% sufficient to recover context. Report Tier 1/2 as "local-only (new machine — recovered from Tier 3 trackers & git)" in the status presentation.

---

## 2. Read Local Session State & Active `Human-Stack` Profile (Tier 2 — local machine & operator state)

// delegate: flash
1. **Use `session_state.excerpt` from Step 0** (or read `.agents/SESSION.md` in full only if the excerpt is truncated):
   - **Top Session Log entry** — most recent session: conversation ID, machine, completed items
   - **Last entry for this machine** — if different from top entry, read it too (reveals this machine's last known state)
   - If any entry has a **Resume from** note → this is the exact continuation point
2. **Adopt the Operator's Optional `Human-Stack Profile` (`precedence: 85..95`)**:
   - Inspect `.agents/SESSION.md` (*Case 2: personal evolving `Human-Stack`*), `.agents/LAYER_LINEAGE.md` or `README.md` (*Case 3: Squad/Department onboarding directive*), or any punctual in-chat request (*Case 1*) using the specificity chain `In-Chat Override -> Personal .agents/SESSION.md -> Team Blueprint -> Default (Case 0 when blank/omitted)`.
   - When one or more `Human-Stack` facets (`domain-<area>:M1..M4`, `bridge-*`, `soft-*`, `hat-*`) are declared, adapt explanation depth, cross-discipline vocabulary bridges (`bridge-tech-for-business` / `bridge-business-for-tech`), and Socratic guidance accordingly while keeping all organizational and technical gates (`precedence: 0..80`) strictly invariant.

3. **Cross-reference against Tier 1 artifacts**:
   - If `walkthrough.md` documents verified work not in any Session Log entry → SESSION.md missed it
   - Trust Tier 1 artifacts over SESSION.md when they conflict

> [!CAUTION]
> **Historical `Uncommitted` fields are snapshots, not current state.** Each Session Log entry
> records what was uncommitted *at the time of session close*. After the user commits manually,
> these lines become stale but remain in the log (append-only). **Only Tier 3 (`git_state`)
> determines current uncommitted state.** Never treat a past entry's `Uncommitted` field as
> actionable — always verify against git.

---

## 3. Verify Against Code & Priority (Tier 3 — ground truth)

// delegate: flash
1. **Use `git_state` and `priority_state` from the Step 0 JSON digest** (`status_short`, `recent_commits`, `active_tracker`, and `excerpt`). Do NOT re-run `git status`, `git log`, or probe `WORKTASK.md` / `WORKROAD.md` / `BACKLOG.md` separately for a single-repo workspace.
2. **Multi-Repo Parent Workspace Only**: If `<PROJECT_ROOT>` is a parent folder containing multiple independent git repositories (`*/.git`), run a single loop across sub-repos to check `git status --short --branch` and `git log --oneline -3`.

4. **Resolve conflicts** — when SESSION.md and git disagree:
   - SESSION.md says "pending commits" but git is clean → already committed, SESSION.md stale (historical snapshot — not an error)
   - SESSION.md says "completed" but no git commit exists → work was lost or not committed
   - Unpushed commits exist → flag them explicitly
   - Local behind origin → another machine pushed changes; recommend `git pull --ff-only`

---

## 4. Present Status

Present a structured summary (always placing the **`🌐 Live Node Cockpit`** callout box at the very top whenever `active_cockpit` is active):

```markdown
> [!TIP]
> 🌐 **Live Node Cockpit (`[plugin_id]` · `PID [daemon_pid]`)**: **[Open Node Cockpit (`[localhost_url]`)]([localhost_url])**
> Environments: [`DEV`]([dev_url]) · [`TST`]([tst_url]) · [`PRE`]([pre_url]) · [`PRO`]([pro_url]) · Subdomain: `[active_subdomain_url]`

## Session Recovery

**Current machine**: [hostname]
**Last session (this machine)**: [date] · conv [id]
**Last session (any machine)**: [date] · conv [id] · machine [name] (only if different)

### 🔍 Recovery Sources
- Tier 1: [brain/ artifacts found/not found]
- Tier 2: [SESSION.md status: current/stale/missing]
- Tier 3: [git state summary + behind-origin status]

### ✅ Completed
- [items verified against Tier 1 artifacts + git commits]

### 📦 Uncommitted / Unpushed
- [repos with uncommitted changes or unpushed commits]
- (only from current git status — NEVER from historical SESSION.md entries)

### 📡 Cross-Machine Sync (only if behind origin)
- [repos behind origin with commit count]
- Recommendation: `git pull --ff-only` in each behind repo before starting work

### 🎯 Next (Priority Chain)
- [next task from active task tracker → backlog → roadmaps/]
```

---

## 5. Rules

- **NEVER ask** "what do you want to do?" — present the next step per the priority chain (`#0 In-Flight -> #1 WORKTASK.md -> #2 WORKROAD.md / BACKLOG.md -> #3 roadmaps/`)
- **NEVER start working** — only present state and propose. Wait for user confirmation
- **NEVER deduce** — always read brain/ artifacts and SESSION.md before presenting state
- **Tier precedence**: brain/ artifacts (richest) → SESSION.md (portable) → git (ground truth for code)
- **When SESSION.md conflicts with git**, trust git for code state (commits, changes)
- **When SESSION.md conflicts with brain/ artifacts**, trust artifacts for work state (what was done)
- **Historical Uncommitted is NOT current state** — SESSION.md `Uncommitted` fields in past entries are snapshots. Only `git status` determines current uncommitted state.
- **Machine identification**: Always determine the current hostname and match against Session Log `**Machine**` entries.
- **New machine**: If Tier 1 is empty, Tier 2 + Tier 3 are sufficient. Do not treat missing brain/ artifacts as an error.
- **Path resolution**: Never hardcode absolute paths. Resolve all repo paths dynamically from workspace metadata.
- **Behind origin**: If any repo is behind origin, present the sync recommendation prominently. Do NOT auto-pull — let the user decide.
- **`.agents/SESSION.md` preservation**: Never run `rm -rf .agents` inside an active workspace (even to simulate clean CI checkouts), because `.agents/` is gitignored and contains `.agents/SESSION.md` (Tier 2 session recovery state).
- After presenting, the user may:
  - Confirm → proceed with governance rules and work
  - Redirect → user gives a different task
  - Request commits → execute `/continue` to deliver commit blocks for uncommitted changes

---

## 6. Edge Cases — Session Lifecycle Gaps

### No `/sopen` before work

**Scenario**: User opens Antigravity and starts working directly without running `/sopen`.

**Agent behavior**: If `/continue` is called without a prior `/sopen`, the agent should:
1. **Detect the gap** — check if SESSION.md was updated in this conversation. If not, this is a session without `/sopen`.
2. **Adopt the session gracefully** — create the session entry in SESSION.md as part of the `/continue` snapshot step. Do NOT force the user to re-run `/sopen`.
3. **Warn once**: _"No `/sopen` was run at session start. Session entry created. Consider running `/sopen` when opening each new chat for full context."_

**User action**: Not required. The agent self-heals. For best context, run `/sopen` first next time.

### Unexpected close (no `/sclose`)

**Scenario**: Antigravity closes unexpectedly (crash, closed tab, internet drop) without `/sclose`.

**What becomes stale**: `SESSION.md` still shows the last **committed** session entry, not the work done after. Brain artifacts (`task.md`, `walkthrough.md`) may be partially written.

**Recovery in next `/sopen`**:
1. `/sopen` Step 3 runs `git status` across all repos → detects uncommitted changes from the crashed session
2. `/sopen` Step 1 reads brain artifacts → detects partially completed task.md
3. **Conflict resolution**: git state (Tier 3) is ground truth for what files changed. Brain artifacts (Tier 1) show what the agent was doing. SESSION.md (Tier 2) may be outdated.
4. Present the gap clearly: _"SESSION.md appears outdated. Git shows uncommitted changes not recorded in the last session entry."_

**User action**: Run `/sopen` normally — its multi-tier recovery handles this automatically. Then decide:
- `/continue` to commit the orphaned changes
- Or discard them with `git checkout .` if unwanted
