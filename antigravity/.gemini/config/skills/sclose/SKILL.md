---
name: sclose
description: full session close — recap, consolidation, commits, and summary
---

# Session Close — `/sclose`

> **End of work session.** Closes the session entry, delivers final commits, and provides a summary.
> For task-level cleanup (task tracker, CHANGELOG), see `/continue` §2.5 — that happens between tasks, not at session close.

---

## 1. Session Recap

Summarize **everything accomplished** in the session:

```markdown
## Session Summary — [date]

### Completed
- [Item 1: brief description]
- [Item 2: brief description]

### Deferred
- [Items started but not finished, with reason]
```

---

## 2. Close SESSION.md Entry & Deactivate Background Session Plugins (`make deactivate-plugin`)

1. **If any `plugin-stack` runtime plugin is active in `.agents/runtime/*.json` (`"status": "active"` / `"daemon_active": true`)**:
   - Run `make deactivate-plugin` (or `~/.local/bin/zcg apply-project "<PROJECT_ROOT>" --service-action deactivate`) to cleanly terminate the background HTTP daemon (`daemon_pid`) and mark `.agents/runtime/<plugin_id>.json` as `"status": "inactive"` so zero orphan background listeners remain after the session closes.
2. **Update the current session entry** in `.agents/SESSION.md`:
   - Finalize **Completed** list
   - Update **Uncommitted** to reflect any remaining changes
3. **Prune Session Log** — keep a maximum of 5 entries (oldest are already captured in CHANGELOG)

> [!IMPORTANT]
> **SESSION.md content is preserved within a session.** Only prune entries from *previous* sessions,
> never delete work logged in the current session.

---

## 2.5. Governance Promotion (if applicable)

> [!IMPORTANT]
> `/sclose` **MUST** run governance promotion before delivering commits. This is the same
> logic as `/continue` §2.5, ensuring completed work is always finalized regardless of
> whether `/continue` was run during the session.

Scan the task tracker for **fully completed task blocks** (every item `[x]`):

1. **Detect completion** — if a task block has ALL sub-items marked `[x]` (deferred items count as complete)
2. **If found**, execute governance promotion in ONE step:
   a. **Write CHANGELOG entry** — add user-facing summary under `[Unreleased]` (user language, no filenames)
   b. **Delete the task block** — remove entire block from the task tracker (`WORKTASK.md`) + remove row from Priority Summary table
   c. **Clean active roadmap/backlog** — delete the completed phase/item from `WORKROAD.md` / `BACKLOG.md` (Zero-clutter invariant: never leave `~~strikethrough~~`)
   d. **Delete implemented phases from source roadmap** — remove the completed phase section(s) from the origin roadmap file in `roadmaps/`. If ALL phases of a roadmap are implemented, delete the entire file.
3. **If no completed blocks** → proceed to Inline Work scan (do NOT skip entirely)

**Inline Work scan** (MANDATORY — always runs):

> [!IMPORTANT]
> Even if no task blocks are found, scan `BACKLOG.md` and `WORKROAD.md` for items completed during this session
> without task block promotion (inline/direct implementation). If found:
> a. **Delete the completed item** from `BACKLOG.md` / `WORKROAD.md` (Zero-clutter invariant)
> b. **Write CHANGELOG entry** if the work is user-facing
> c. **Delete implemented phases from source roadmap** if applicable
> d. **Multi-Repo Parity**: If multiple repositories (e.g., shared platform + consumer services) were modified during the session, update `CHANGELOG.md` and verify `README.md` directory trees (§10) in **every** modified repository before delivering commits.

---

## 3. Deliver Commits & Multi-Machine Persistence (`WORKTASK.md` / `CHANGELOG.md` + `git push origin`)

Follow commit rules in `/continue` (`skills/continue/SKILL.md` §3) — provide commit commands for **all repos with uncommitted tracked changes** AND ensure committed work is pushed to the working repository's `origin` remote so the project can be resumed seamlessly from any machine via `/sopen` (Tier 3: `WORKTASK.md [Lot k/N]`, `WORKROAD.md`, `BACKLOG.md`, `CHANGELOG.md`, and `git log`):

1. **Keep `.agents/SESSION.md` Strictly Local (`Zero Force-Track on .agents/*`)**:
   - `.agents/SESSION.md` is updated locally on disk in Step 2 (storing the current machine's `conv-id` pointer to `brain/<conv-id>` and local operator `Human-Stack:` profile), and is **never** force-tracked in Git (`0` `git add -f .agents/SESSION.md`).
   - All portable cross-machine progress (`[Lot k/N]` in `WORKTASK.md`, `WORKROAD.md`, `BACKLOG.md`, and `## [Unreleased]` in `CHANGELOG.md`) lives in the root governance files.
2. **Push to Working `origin` at Session Close (Never Public `upstream`)**:
   - **If uncommitted tracked changes exist**: deliver the commit block (`git add -u`, chaining `&& git add <new_path>` when new untracked paths exist; never `git add -u <untracked_path>`) + `&& git push origin <branch>` (where `<branch>` is resolved via `git branch --show-current`).
   - **If all tracked files were already committed earlier in the session**, check `git status --short --branch`:
     - If the local branch is `[ahead N]` of `origin/<branch>`, deliver the standalone `git push origin <branch>` command so those commits reach `origin` before closing.
     - If the working tree is clean (`0` tracked diffs — e.g. because `make deactivate-plugin` restored `surfaces/` to `inactive` and `.agents/SESSION.md` is gitignored) AND `0` commits ahead of `origin/<branch>`, explicitly state why `0` tracked files changed and emit the optional session-close audit commit block (`cd <REPO_PATH> && git commit --allow-empty -m "chore(<layer_id>): record session close validation checkpoint" && git push origin <branch>`); **never** scan unrelated sibling repositories (`~/Projects/*`).

> [!IMPORTANT]
> Steps 1–2.5 AND all background verification/test tasks (`pytest -q -x` / `make verify`, `0` running `task-NNNN` tasks) must be 100% complete before this step. All edits (`.agents/SESSION.md`, task tracker, backlog, `CHANGELOG.md`) must be saved and verified BEFORE delivering commits — commits are delivered **strictly at a full stop (`at full stop`), with or after the session or checkpoint summary**, never while any test or validation is still executing.

> [!NOTE]
> **Post-commit convention**: The `**Uncommitted**` field written in Step 2 records the state
> *before* commits are delivered. Future agents running `/sopen` must treat historical
> `Uncommitted` fields as snapshots, not current state — only `git status` determines current state.

---

## 3.5. Global Config Sync (Post-Commits)

If any shared rules, skills, or system config in the `zero-cloud-gravity` maintainer clone (`ZCG_DEV_REPO_DIR` / `~/Projects/dev-<repo>`) were modified during this session, run `make verify` first to confirm all verification gates pass, log changes under `## [Unreleased]` in `CHANGELOG.md` without bumping `VERSION`, and deliver a single commit block that pushes to private `origin` and chains `&& ~/.local/bin/zcg-sync --sync` (which synchronizes `~/<user-pc>` and `$HOME` Stow links; public Open-Source `upstream` remains untouched until `/release`):

```bash
### zero-cloud-gravity (session close -> private origin + $HOME workstation sync)
cd "${ZCG_DEV_REPO_DIR:-$ZCG_RUNTIME_DIR}" && git add -u && git commit -m "<summary of config changes>" && git push origin <branch> && ~/.local/bin/zcg-sync --sync
```

> [!NOTE]
> Only include this commit block if tracked files in `zero-cloud-gravity` were edited (or `git push origin <branch> && ~/.local/bin/zcg-sync --sync` if already committed locally but unpushed).
> Chaining `&& ~/.local/bin/zcg-sync --sync` automatically resolves `$ZCG_RUNTIME_DIR` and `$ZCG_WORKSTATION_DIR` (`~/.config/zero-cloud-gravity/workstation.conf`), reconciles global rules/skills with the workstation's configured `--profile` and `--lang`, and re-stows `~/.gemini/config/` from `~/<user-pc>`.

---

## 3.6. Knowledge Signal (active reflection)

Two-part scan for knowledge enrichment:

### Part A — File Change Detection (passive)

1. **Check**: Were any files in `.agents/rules/`, `.agents/skills/`, or `zero-cloud-gravity/` modified during this session?
2. **If YES** → append to the session summary:
   ```
   💡 Rules/skills were modified. Consider running `/enrich` to evaluate upstream promotion.
   ```

### Part B — Behavioral Pattern Detection (active)

3. **Reflect**: Did the user correct the agent's behavior, catch recurring errors, or point out patterns that the agent should have detected autonomously during this session?
4. **If YES** → analyze each correction:
   - **Root cause**: Why did the agent fail? Missing mandate? Mandate too vague? Agent not following an existing mandate?
   - **Rule gap or rule drift?**: Is this a NEW pattern that no existing rule covers, or is it an existing rule that the agent failed to apply?
   - **Propose**: Suggest a concrete rule addition or refinement targeting the specific failure mode.
   - Append to the session summary:
   ```
   💡 Behavioral pattern detected: [brief description]. Consider adding/refining rule in [target layer].
   ```
5. **If NO** → skip silently (zero overhead)

---

## 4. Final Summary

One-paragraph natural language recap for the user — what was done, what's next in the priority chain (`WORKTASK.md` $\rightarrow$ `WORKROAD.md` / `BACKLOG.md` $\rightarrow$ `roadmaps/`).

---

## 5. Rules

- **ALWAYS update SESSION.md** — this is mandatory, no exceptions
- **ALWAYS deliver commits** — do not ask whether the user wants them
- **ALWAYS run governance promotion** — `/sclose` is the last chance to finalize completed work
- **Keep the recap concise** — bullet points, not paragraphs
