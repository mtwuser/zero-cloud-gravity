---
epistemic_grade: E3
---

# Architecture 03 — Governance, Work Ledger, Lifecycle Hooks & Tiered CLI (`src/zcg/governance/`, `src/zcg/cli/` & `antigravity/`)

> **Normative Specification — Subsystem 3 (`src/zcg/governance/*`, `src/zcg/cli/*` & `antigravity/.gemini/config/scripts/*`)**
>
> This specification defines the 5 deterministic Python 3.14 Antigravity lifecycle hooks (`SessionStart`, `PreToolUse`, `PostToolUse`, `PostInvocation`, `Stop` with `continuationActive` loop guard), sovereign node bootstrapping (`--purpose` & `--from-parent`), native Antigravity 2.0 plugin bundle (`plugin.json` + `.agents/plugins.json`) and project-level permission compilation (`.agents/antigravity-permissions.json`), declarative node linking (`zcg link --from` / `zcg unlink` + epistemic `R3` wallet airlock), branch-to-project graduation (`zcg spinout-project`), plugin module scaffolding (`zcg scaffold-plugin-module`), executable AST hexagonal boundary linting (`zcg lint-arch`), unified `Node × Layer × Network` capability gating & `< 50 ms` skill static scanning (`zcg lint-skills`), deterministic bidirectional contract alignment (`zcg check-handoff`), isolated OSS engine contribution workflows (`zcg oss` / `mk/oss-contrib.mk`), 4-mode upstream template reconciliation, RBAC authority gates, $N$-departmental surface consensus, the *Node Work & Sprint Ledger*, `1-hop` directive/promotion workflows, and the 38-subcommand `zcg` console dispatcher (`42` dispatcher tokens with shorthand aliases).

---

## 1. `1:1:1` Source $\leftrightarrow$ Unit Test $\leftrightarrow$ Responsibility Matrix (`governance/` & `cli/`)

Fourteen governance modules and four CLI modules implement all `C1`/`C2`/`C3`/`Subtree`/`Workstation`/`OSS` node lifecycle operations (`100.00%` isolated unit statement and branch coverage):

| Implementation Module | Isolated `1:1` Unit Suite | Primary Symbols & Normative Scope |
| :--- | :--- | :--- |
| [src/zcg/governance/authority.py](../../src/zcg/governance/authority.py) | [tests/unit/zcg/governance/test_authority.py](../../tests/unit/zcg/governance/test_authority.py) | `resolve_git_user_email`, `configure_layer_authority`, `resolve_actor_role_profile` (`owner`, `maintainer`, `validator`, `member`, `consumer` + `UPSTREAM_HIERARCHICAL_AUTHORITY`), `verify_layer_operation_authority`, `verify_single_hop_upstream` (`CROSS_TIER_PROMOTION_BYPASS`), and `scan_open_source_agnosticism`. |
| [src/zcg/governance/ledger.py](../../src/zcg/governance/ledger.py) | [tests/unit/zcg/governance/test_ledger.py](../../tests/unit/zcg/governance/test_ledger.py) | `summarize_work_orchestration_ledger` (`own_node_ledger` vs. `inter_layer_exchange`), `manage_layer_roster` (`.github/CODEOWNERS` sync), `configure_git_governance_policy`, and `record_governance_decision` (`logs/governance_audit.jsonl`). |
| [src/zcg/governance/consensus.py](../../src/zcg/governance/consensus.py) | [tests/unit/zcg/governance/test_consensus.py](../../tests/unit/zcg/governance/test_consensus.py) | `collect_layer_effective_bindings`, `match_authoritative_surface_bindings`, `evaluate_multilayer_surface_consensus` (`RECONCILED_FLOW`, `ITERATION_REQUIRED`, `ESCALATE_TO_ROOT`, `ESCALATE_INTER_ENTITY_ROOTS`), and `evaluate_environment_promotion` (`dev -> tst -> pre -> pro`). |
| [src/zcg/governance/workflows.py](../../src/zcg/governance/workflows.py) | [tests/unit/zcg/governance/test_workflows.py](../../tests/unit/zcg/governance/test_workflows.py) | `start_task_workflow` (`feature/<TICKET-ID>-<slug>` + `.agents/SESSION.md`), `complete_task_workflow` (intra-node or `parent_dir` `Outbound Delegations` rollup), and `delegate_directive_to_child` (`1-hop` downward delivery + non-destructive `.agents/proposals/from-<parent>/` staging). |
| [src/zcg/governance/horizon.py](../../src/zcg/governance/horizon.py) | [tests/unit/zcg/governance/test_horizon.py](../../tests/unit/zcg/governance/test_horizon.py) | `diff_project_against_layers` (`SHA-256` drift audit), `compare_upstream_templates` (`#`/`##` section diff), and `inspect_layer_horizon` (`inbound_from_upstream`, `inbound_from_downstream`, `local_workspace_changes`). |
| [src/zcg/governance/promotion.py](../../src/zcg/governance/promotion.py) | [tests/unit/zcg/governance/test_promotion.py](../../tests/unit/zcg/governance/test_promotion.py) | `reconcile_template_pack_sync` (`reconcile`, `accept-upstream`, `merge`, `keep-local`), `promote_project_asset_to_layer` (`1-hop` upward PR + OSS anonymization), and `consult_layer_ephemeral` (`make consult`). |
| [src/zcg/governance/scaffolder.py](../../src/zcg/governance/scaffolder.py) | [tests/unit/zcg/governance/test_scaffolder.py](../../tests/unit/zcg/governance/test_scaffolder.py) | `configure_node_manifest`, `scaffold_template_pack`, and `apply_templates_to_project` (materializing `.agents/rules/layer-<NN>-<id>.md`, `.agents/skills/`, filtered `.agents/skills.json`, `.agents/zcg.mk` on `project` workspaces, `.agents/LAYER_LINEAGE.md`, and pruning deselected plugins). |
| [src/zcg/governance/bootstrap.py](../../src/zcg/governance/bootstrap.py) | [tests/unit/zcg/governance/test_bootstrap.py](../../tests/unit/zcg/governance/test_bootstrap.py) | `register_mounted_subtree`, `bootstrap_node_workspace` (`--purpose` archetype synthesis, `--from-parent` shallow `1-hop` inheritance, composable `Makefile` / non-invasive `.agents/zcg.mk`, auto-installing & activating default Cockpit + Antigravity IDE workspace registration), and `sync_node_workspace`. |
| [src/zcg/governance/links.py](../../src/zcg/governance/links.py) | [tests/unit/zcg/governance/test_links.py](../../tests/unit/zcg/governance/test_links.py) | `resolve_linked_node_dir`, `link_node` (`zcg link` with `--from <url\|path>`, unified capability gate, and epistemic `R3` `wallet` airlock allowing read-only `knowledge-feed` to `knowledge` corpora while blocking peer/settlement links), `unlink_node` (`zcg unlink`), and `spinout_branch_to_project` (`zcg spinout-project --from-branch`). |
| [src/zcg/governance/arch_linter.py](../../src/zcg/governance/arch_linter.py) | [tests/unit/zcg/governance/test_arch_linter.py](../../tests/unit/zcg/governance/test_arch_linter.py) | `BoundaryViolation`, `check_domain_module`, `check_test_suite`, and `lint_architecture` (`zcg lint-arch`) enforcing `0` infrastructure/I/O imports in `domain/` (`models.py`, `entities.py`, `service.py`), `0`-byte `__init__.py`, `excluded_contexts`, and `1:1:1` `AAA` test contracts. |
| [src/zcg/governance/capabilities.py](../../src/zcg/governance/capabilities.py) | [tests/unit/zcg/governance/test_capabilities.py](../../tests/unit/zcg/governance/test_capabilities.py) | `resolve_effective_capability_ceiling` (*Lex Superior* `Root 0 -> Layer -> Node` intersection), `evaluate_capability_gate`, `enforce_capability_gate` (`Actor Role ∩ Lex Superior Ceiling` across `install/uninstall`, `activate/deactivate`, `deploy`, `link/unlink`, and `promote`), `lint_single_skill_file`, and `lint_skills_security` (`zcg lint-skills`). |
| [src/zcg/governance/handoff.py](../../src/zcg/governance/handoff.py) | [tests/unit/zcg/governance/test_handoff.py](../../tests/unit/zcg/governance/test_handoff.py) | `DEFAULT_CANONICAL_AXIS_GLOSSARY`, `load_merged_canonical_glossary` (`GLOSSARY_DEFINITION_CONFLICT`), and `check_handoff_symmetry` (`zcg check-handoff`: `INFORMAL_ALIAS_REBOUND`, `MULTI_AXIS_CONFLATION_REBOUND`, `MISSING_REQUIRED_HANDOFF_SECTION`, and `UNSTANDARDIZED_ASYMMETRY_PROPOSAL`). |
| [src/zcg/governance/oss_contrib.py](../../src/zcg/governance/oss_contrib.py) | [tests/unit/zcg/governance/test_oss_contrib.py](../../tests/unit/zcg/governance/test_oss_contrib.py) | `should_expose_oss_targets` and `run_oss_action` (`zcg oss <push-branch\|promote-master\|publish>` backing `mk/oss-contrib.mk` `oss-*` targets with `[OSS_DEV_ONLY_BLOCKED]`, `[OSS_DEV_ORIGIN_MISMATCH]`, `[OSS_BRANCH_REQUIRED]`, and sterile `git archive` snapshot export stripping `WORK*.md`, `BACKLOG.md`, `roadmaps/`, and `.github/dependabot.yml`). |
| [src/zcg/governance/antigravity_sync.py](../../src/zcg/governance/antigravity_sync.py) | [tests/unit/zcg/governance/test_antigravity_sync.py](../../tests/unit/zcg/governance/test_antigravity_sync.py) | `build_plugin_bundle_manifest` (official Antigravity 2.0 `plugin.json` allowlist), `sync_antigravity_plugins` (`.agents/plugins/<pack>/` with frontmatter-free `rules/AGENTS.md` + `.agents/plugins.json`), `compile_antigravity_permissions` (`.agents/antigravity-permissions.json` with `R3` `wallet` `non_workspace_file_access: "deny"`, `0` mutations to `~/.gemini/config/config.json`), and `sync_workspace_antigravity_surfaces`. |
| [src/zcg/cli/parser.py](../../src/zcg/cli/parser.py) | [tests/unit/zcg/cli/test_parser.py](../../tests/unit/zcg/cli/test_parser.py) | Deterministic flag parsing (`parse_cli_options`, `parse_pos_and_options`), `CLIUsageError` (exit `1`), and `CLIAuthorityBlockedError` (exit `2`). |
| [src/zcg/cli/discovery.py](../../src/zcg/cli/discovery.py) | [tests/unit/zcg/cli/test_discovery.py](../../tests/unit/zcg/cli/test_discovery.py) | `dispatch_c1` (`11` read-only discovery commands including `inspect-remote`, `lint-arch`, `lint-skills`, and `check-handoff`), `dispatch_subtree` (`subtree <list\|pull\|pull-all\|register>`), `dispatch_workstation`, and `dispatch_oss` (`zcg oss`). |
| [src/zcg/cli/commands.py](../../src/zcg/cli/commands.py) | [tests/unit/zcg/cli/test_commands.py](../../tests/unit/zcg/cli/test_commands.py) | `dispatch_c2` (`13` lifecycle tokens including `bootstrap-workspace --purpose --from-parent`, `link --from`, `unlink`, `spinout-project`, `scaffold-plugin-module`, and `set-global-profile --workstation-dir`) and `dispatch_c3` (`8` RBAC-gated governance commands). |
| [src/zcg/cli/dispatcher.py](../../src/zcg/cli/dispatcher.py) | [tests/unit/zcg/cli/test_dispatcher.py](../../tests/unit/zcg/cli/test_dispatcher.py) | `dispatch_zcg_cli` and `main` console entrypoint (`zcg`). |

---

## 2. Deterministic Python 3.14 Antigravity Lifecycle Hooks (`antigravity/.gemini/config/`)

All five lifecycle hooks execute in `< 50 ms` using 100% Python 3.14 Standard Library (`hooks.json`):

```mermaid
sequenceDiagram
    participant Start as session_start_orientation.py (SessionStart)
    participant Agent as Antigravity Agent
    participant Pre as pre_tool_guard.py (PreToolUse)
    participant Tool as File / Shell Tool
    participant PostEdit as post_edit_format.py (PostToolUse)
    participant PostInv as post_invocation_lint.py (PostInvocation)
    participant Stop as stop_verify_tests.py (Stop)

    Start-->>Agent: Inject user_markdown & systemMessage node orientation badge
    Agent->>Pre: Propose tool call (write_file / edit_file / run_command)
    Pre-->>Agent: Block (exit 2) if mutating git, >0B __init__.py, or editing layer-*.md
    Pre->>Tool: Allow safe tool execution
    Tool->>PostEdit: Modified .py file
    PostEdit->>PostEdit: Auto-run ruff format
    Tool->>PostInv: Turn complete
    PostInv-->>Agent: Verify <=384 src / <=464 doc-test lines, Specification:, # Arrange/# Act/# Assert, <=18KB AGENTS.md
    Agent->>Stop: Conclude task
    Stop->>Stop: Guard continuationActive, then run affected unit tests
```

1. **`session_start_orientation.py` (`SessionStart`)**: Reads `system/zcg-node.json` from active `workspacePaths` and emits `injectSteps` (`systemMessage` + `metadata.user_markdown`) orienting the agent and operator on `layer_id`, `layer_role`, `precedence`, `interaction_language`, and `:8700 + precedence` port without spawning subprocesses.
2. **`pre_tool_guard.py` (`PreToolUse`)**: Blocks automated mutating `git` commands (`add`, `commit`, `push`, `reset`, `rebase`, `checkout`, `merge`, `clean`, `subtree`), writes (`> 0 bytes`) to `{src,tests}/**/__init__.py`, and direct edits to inherited `.agents/rules/layer-*.md` across both file tools and shell redirections (`heredoc`, `tee`, `sed -i`, `python -c`).
3. **`post_edit_format.py` (`PostToolUse`)**: Automatically formats modified `.py` files with `ruff format`.
4. **`post_invocation_lint.py` (`PostInvocation`)**: Enforces `<= 384` lines on `src/**/*.py`, `<= 400` lines on root `README.md`, `<= 464` lines on `docs/**/*.md` and `tests/**/*.py`, `Specification: docs/architecture/*.md` headers, standalone `# Arrange`, `# Act`, and `# Assert` comments in every `def test_*`, `ruff check`, and `AGENTS.md <= 18,000` bytes (`force_continue: True` on violations).
5. **`stop_verify_tests.py` (`Stop`)**: Short-circuits immediately when `continuationActive` is `True` (preventing infinite continuation loops) and executes affected unit test suites before concluding a task turn.

---

## 3. *Node Work & Sprint Ledger*, 4-Mode Reconciliation & $N$-Departmental Consensus

`src/zcg/governance/` enforces three core state machines across every governed repository:

### 3.1. Dual-Plane *Node Work & Sprint Ledger* (`summarize_work_orchestration_ledger`)

Every node's work ledger (`WORKROAD.md`, `WORKTASK.md`, `WORKVALI.md`, `BACKLOG.md`) separates **intra-node execution** from **inter-layer governance exchange**:
- **`own_node_ledger`**: Counts `pending_count` (`[ ]`), `in_progress_count` (`[/]`), and `completed_count` (`[x]`) across `WORKROAD.md`, `WORKTASK.md`, `WORKVALI.md`, and `BACKLOG.md`, extracting active task IDs and sprint progress percentage.
- **`inter_layer_exchange`**: Tracks `outbound_delegations` (`- [/] **[<TICKET> -> <child> (stage: delegated)]**` under `## Outbound Delegations` in `WORKTASK.md`), `inbound_proposals` (`.agents/proposals/from-*`), and `outbound_proposals` (`.agents/proposals/to-*`).

### 3.2. Four-Mode Upstream Template Reconciliation (`reconcile_template_pack_sync`)

When `zcg sync-layer` updates inherited templates from a parent layer or `zero-cloud-gravity`, `--strategy` controls conflict resolution while always skipping the node's own sovereign pack (`skip_id = layer_id`):
1. **`reconcile` (Default — Zero-Loss)**: Adopts clean upstream updates and stages any locally diverged inherited rule file non-destructively under `.agents/proposals/from-upstream/<pack>/<file>`.
2. **`accept-upstream`**: Overwrites inherited template packs with the canonical upstream version.
3. **`merge`**: Preserves local-only `# / ## / ###` Markdown sections while updating shared upstream sections.
4. **`keep-local`**: Keeps existing local template files untouched while adding only newly introduced upstream files.

### 3.3. Progressive `env-gate` (`dev -> tst -> pre -> pro`) & 4-State $N$-Departmental Consensus

`evaluate_environment_promotion` and `evaluate_multilayer_surface_consensus` enforce progressive quality and authority gates:

| Target Environment | Required Ledger & Git State | Required RBAC Role (`effective_role`) | Multi-Department Surface Consensus (`--files`) |
| :--- | :--- | :--- | :--- |
| **`tst`** | `0` open `[P0]` blockers in `WORKTASK.md` | `member`, `validator`, `maintainer`, or `owner` | Evaluates matching `surface_bindings` across mounted layers. |
| **`pre`** | `tst` gates + `0` unchecked `[ ]` items in `WORKVALI.md` | `validator`, `maintainer`, or `owner` | Requires `RECONCILED_FLOW` (no unresolved `REJECTED`/`DEFERRED` co-owners). |
| **`pro`** | `pre` gates + non-empty `CHANGELOG.md` | `owner` (or internal parent `Root 0` `owner` via `UPSTREAM_HIERARCHICAL_AUTHORITY`) | Halts on `ESCALATE_TO_ROOT` (internal deadlock) or `ESCALATE_INTER_ENTITY_ROOTS` (external `public-government` statutory block). |

---

## 4. Executable AST Hexagonal Boundary Enforcer (`arch_linter.py` / `zcg lint-arch`)

`lint_architecture` (`zcg lint-arch [<dir>] [--no-tests]`) statically parses Python ASTs across source and test trees (`exit 0` when `violation_count == 0`, `exit 1` otherwise) while ignoring static-only `if TYPE_CHECKING:` blocks:

| Rule Identifier | Target Surface | Normative AST / Structural Condition |
| :--- | :--- | :--- |
| `domain-imports-infrastructure` | `domain/**`, `models.py`, `entities.py`, `service.py` | Rejects runtime imports from `infrastructure`, `adapters`, `router`, `repository`, `sqlite_repo`, `asgi`, `server`, or `dependencies`. |
| `domain-imports-io-package` | `domain/**`, `models.py`, `entities.py`, `service.py` | Rejects runtime I/O, network, process, or DB imports (`sqlite3`, `subprocess`, `socket`, `http`, `urllib`, `asyncio`, `sqlalchemy`, `httpx`, etc.). |
| `non-empty-init-file` | `{src,tests}/**/__init__.py` | Enforces `0`-byte / empty package initializers across source and test packages. |
| `excluded-context-import` | `src/<context>/**/*.py` | Rejects cross-context imports forbidden by `excluded_contexts` in `system/zcg-node.json`. |
| `flat-test-file` / `orphan-test-file` | `tests/**/*.py` | Requires `test_*.py` under `tests/{unit,imp,e2e}/` and `1:1` matching `src/` modules for every `tests/unit/**/test_<mod>.py`. |
| `one-test-class-per-file` / `db-fixture-in-unit-test` / `missing-aaa-comments` | `tests/**/*.py` | Requires exactly `1` top-level `Test*` class per file, `0` DB session/engine fixtures in `tests/unit/`, and `# Act` + `# Assert` markers in every `test_*`. |

---

## 5. Unified `Node × Layer × Network` Capability Gate, `lint-skills` & Bidirectional `check-handoff`

`capabilities.py` and `handoff.py` enforce deterministic local capability boundaries and cross-layer lexical alignment using 100% Python 3.14 Standard Library:

| Subsystem Contract | Enforcing Function & CLI | Normative Behavior & Deterministic Outcome |
| :--- | :--- | :--- |
| **`Actor Role ∩ Lex Superior Ceiling`** | `enforce_capability_gate` (`install`, `uninstall`, `activate`, `deactivate`, `deploy`, `link`, `unlink`, `promote`) | Intersects `verify_layer_operation_authority` with inherited `capability_policy` (`curated-allowlist` `allowed_plugins` / `allowed_link_targets` + additive `blocked_operations`); refines `<persona>-wallet` `R3` airlock so read-only `knowledge-feed` links to `knowledge` corpora (`sci-economic`, `gov-*`, `cockpit_url == ""`) pass while peer/settlement links raise `WALLET_EXTERNAL_LINK_BLOCKED`. |
| **`< 50 ms` Static Skill & Config Scanner** | `lint_skills_security` (`zcg lint-skills [<dir>] [--parent-dir <dir>]`) | Scans `SKILL.md`, `hooks.json`, and `mcp_config.json` for hidden/bidi Unicode (`BIDI_OR_ZERO_WIDTH_UNICODE`), `curl\|wget \| sh` (`PIPE_TO_SHELL_EXECUTION`), unauthorized egress hosts under `network_egress_policy` (`UNAUTHORIZED_EGRESS_URL`), and `..` path escapes (`CONFIG_PATH_ESCAPES_WORKSPACE`). |
| **Bidirectional Symmetry Rebound** | `check_handoff_symmetry` (`zcg check-handoff [<dir>] (--text <txt>\|--source <f>) [--target-dir <d>] [--single-axis] [--stage-proposal]`) | Rebounds informal aliases (`"front, bk, db"` $\rightarrow$ `"frontend, backend, database"`), multi-axis conflation, missing `required_sections`, or `GLOSSARY_DEFINITION_CONFLICT` (`exit 1`), and emits/stages `UNSTANDARDIZED_ASYMMETRY_PROPOSAL` (`exit 0`) when sender-vs-receiver templates diverge without a *Lex Superior* rule. |
