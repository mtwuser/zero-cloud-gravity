---
epistemic_grade: E2
---

# Reference 02 — `zcg` CLI, `zcg-mcp` JSON-RPC 2.0 Catalog, Multi-Service Mesh & Maintainer Guide

> **Normative Architecture**: [`docs/architecture/03_governance_and_work_ledger.md`](../architecture/03_governance_and_work_ledger.md) and [`docs/architecture/05_contextual_mcp_and_capsules.md`](../architecture/05_contextual_mcp_and_capsules.md)
>
> This reference documents all 39 `zcg` console subcommands (`43` dispatcher tokens including shorthand aliases), the `zcg-mcp` JSON-RPC 2.0 catalog (`9` resources, `9` tools, `3` prompts), Docker/Cloud Run/SSH federated MCP deployment patterns, OWASP ASVS + `MCP-Sec` security error contracts, and the Maintainer Extension Playbook.

---

## 1. Complete `zcg` Console CLI Reference (`zcg [--repo-dir <dir>] [--dry-run] <subcommand>`)

All 39 canonical subcommands are partitioned into six deterministic capability families (`exit 0` success, `exit 1` usage/validation error, `exit 2` RBAC/env-gate blocked):

| Capability Family | Subcommand & Canonical Synopsis | Mutates Disk? | Primary Purpose |
| :--- | :--- | :---: | :--- |
| **`C1` Discovery** | `zcg status [<dir>] [--parent-dir <dir>]` | No | Returns `< 0.2s` JSON digest (`entity_identity`, `posture`, `surface_origin`, `network_topology`, `work_orchestration`, `runtime_orchestration`, `setup_state`, `horizon`, `agent_diff`). |
| **`C1` Discovery** | `zcg inspect-remote <git-url-or-path> [--branch <ref>]` | No (ephemeral) | Reads `system/zcg-node.json` from any local directory or shallow `--depth 1` Git remote without repository-name heuristics (`UNSAFE_GIT_REMOTE_REF` guarded). |
| **`C1` Discovery** | `zcg list-templates [<dir>]` | No | Lists all `19` `zcg-template-v1` packs, `federated_mcps`, and `ephemeral_bots` across the node and mounted `layers/*`. |
| **`C1` Discovery** | `zcg inspect-horizon [<dir>] [--parent-dir <dir>] [--email <e>]` | No | Returns `actor_role_profile` and 3-bucket `1-hop` radar (`inbound_from_upstream`, `inbound_from_downstream`, `local_workspace_changes`). |
| **`C1` Discovery** | `zcg compare-upstream [<dir>] [--template <id>] [--apply-safe]` | No (`--apply-safe` writes) | Compares `#`/`##` Markdown sections between upstream and local templates (`NEW_UPSTREAM`, `IN_SYNC`, `DIVERGED`, `LOCAL_ONLY`). |
| **`C1` Discovery** | `zcg diff-project <target-dir> [--parent-dir <dir>]` | No | Verifies `SHA-256` parity between projected `.agents/{rules,skills}/` and canonical `templates/`. |
| **`C1` Discovery** | `zcg check-authority [<dir>] --op <op> [--email <e>] [--file <f>]` | No | Evaluates RBAC permission (`owner`, `maintainer`, `validator`, `member`, `consumer` + `UPSTREAM_HIERARCHICAL_AUTHORITY`). |
| **`C1` Discovery** | `zcg consult-layer [<dir>] --layer <id> --query <q> [--tier <t>]` | No (auto-reaped) | Spawns a one-shot `strictly-read-only` ephemeral consultation against `<id>`, returning a 4-Channel Digest + `rcap1` capsules. |
| **`C1` Discovery** | `zcg lint-arch [<dir>] [--no-tests]` | No | Statically audits Hexagonal Functional Core boundaries (`0` infrastructure/I/O imports in `domain/`), `0`-byte `__init__.py`, `excluded_contexts`, and `1:1:1` `AAA` test rules (`exit 1` on violations). |
| **`C1` Discovery** | `zcg lint-skills [<dir>] [--parent-dir <dir>]` | No | `< 50 ms` `0-dep` static security audit of `SKILL.md`, `hooks.json`, and `mcp_config.json` (`BIDI_OR_ZERO_WIDTH_UNICODE`, `PIPE_TO_SHELL_EXECUTION`, `UNAUTHORIZED_EGRESS_URL`, `CONFIG_PATH_ESCAPES_WORKSPACE`; `exit 1` on violations). |
| **`C1` Discovery** | `zcg check-handoff [<dir>] (--text <txt> \| --source <file>) [--target-dir <dir>] [--parent-dir <dir>] [--email <e>] [--single-axis] [--stage-proposal]` | No (`--stage-proposal` stages) | Validates cross-layer directives against `canonical_terms` axis glossaries, rebounding informal aliases / multi-axis conflation (`exit 1`) or emitting an `/enrich` standardization proposal (`exit 0`). |
| **`C2` Lifecycle** | `zcg bootstrap-workspace <dir> --id <id> [--purpose <p>] [--role <r>] [--from-parent <url\|dir>] [--precedence <n>] [--templates <csv>] [--lang <l>]` | Yes | Scaffolds a sovereign or managed node (`system/zcg-node.json`, `Makefile`, `README.md`, `WORK*`, `templates/<id>/`, `.agents/`), inherits `1-hop` parent stacks, activates its Cockpit, and registers it in Antigravity IDE. |
| **`C2` Lifecycle** | `zcg sync-layer [<dir>] [--parent-dir <d>] [--templates <csv>] [--strategy reconcile\|accept-upstream\|merge\|keep-local]` | Yes | Self-heals `Makefile` and `zcg-node-v1`, reconciles inherited templates (`skip_id = layer_id`), rolls up `[x]` child tasks, and refreshes `.agents/` + Cockpit JSON feeds. |
| **`C2` Lifecycle** | `zcg apply-project <dir> [--parent-dir <d>] [--template <id>] [--layers <csv>] [--service-action <act>] [--env <e>]` | Yes | Projects `.agents/rules/layer-<NN>-<id>.md` & `.agents/skills/` into a project, or executes cockpit plugin lifecycle actions (`install`..`teardown`). |
| **`C2` Lifecycle** | `zcg set-global-profile <profile> [--lang <l>] [--workstation-dir <d>] [--stow]` | Yes | Composes `antigravity/.gemini/config/AGENTS.md` (`<= 18,000` bytes) with optional personal `<ws-id>.md`, stows into `$HOME`, and binds `zcg-mcp` to `--repo-dir <workstation-dir>`. |
| **`C2` Lifecycle** | `zcg start-task [<dir>] --task <id> [--ticket <t>] [--prefix <p>]` | Yes | Marks task `[/]` in `WORKTASK.md`, updates `.agents/SESSION.md`, and emits `git checkout -b feature/<TICKET>-<slug>`. |
| **`C2` Lifecycle** | `zcg scaffold-template <name> [--kind <k>] [--register-binding]` | Yes (`owner`/`maintainer`) | Scaffolds a new `zcg-template-v1` pack under `templates/<kind>/<name>/`. |
| **`C2` Lifecycle** | `zcg scaffold-plugin-module <plugin-id\|local> <module-name> [--target-dir <d>] [--prefix <p>] [--description <d>] [--overlay \| --in-pack]` | Yes (`owner`/`maintainer`) | Scaffolds a Hexagonal `L1..L4` module (`modules/<pkg>/{models,service}.py`, `routers/<pkg>.py`, `{% if %}`/`{% for %}` `partials/<mod>.html`) into `<workspace>/surfaces/web/` for community starter packs (keeping `templates/plugin-stack/*` read-only) or into custom `<dept>/templates/<pack>/`. |
| **`C2` Lifecycle** | `zcg scaffold-web-app <target-dir> [--id <id>] [--title <txt>] [--port <n>] [--standalone \| --parent-dir <node-dir>] [--template <stack>]` | Yes | Scaffolds a zero-dependency Hexagonal `zcg.web` application (`src/<pkg>/{domain,routers,app.py}`, `web/templates/{index.html,partials/items.html}`, `web/static/css/app.css`, `1:1` `AAA` tests) runnable standalone (`0` `zcg.cockpit` / node requirement) or governed via `--parent-dir`. |
| **`C2` Lifecycle** | `zcg init-fork --id <id> [--role <r>] [--precedence <n>] [--prune-default-templates]` | Yes (`owner`) | Parameterizes `system/zcg-node.json` in place for a cloned node fork. |
| **`C2` Lifecycle** | `zcg link [<dir>] (--target <id> \| --from <url\|path>) [--branch <ref>] [--relation <rel>] [--ref <path\|url>] [--url <cockpit-url>] [--packs <csv>]` | Yes | Registers a zero-copy declarative node connection in `system/zcg-node.json -> linked_nodes` (`lateral-peer`, `spinout-project`, `hr-process`, `b2b-collaboration`, `knowledge-feed`; `R3` `<persona>-wallet` permits only read-only `knowledge-feed` to `knowledge` corpora). |
| **`C2` Lifecycle** | `zcg unlink [<dir>] --target <id>` | Yes | Removes a declarative node connection from `system/zcg-node.json -> linked_nodes`. |
| **`C2` Lifecycle** | `zcg spinout-project <target-dir> --id <id> --from-branch <branch> [--source-dir <dir>] [--packs <csv>]` | Yes | Graduates an incubated branch (`venture/*`, `engagement/*`) into a standalone governed repository (`precedence: 80`) with bidirectional `spinout-project` links. |
| **`C3` Governance** | `zcg complete-task [<dir>] --task <id> [--deliverable <p>] [--parent-dir <d>] [--create-pr]` | Yes | Marks task `[x]` in `WORKTASK.md` and optionally rolls up completion to `parent-dir`'s `## Outbound Delegations`. |
| **`C3` Governance** | `zcg delegate-to-child [<dir>] --to-child <id> (--task <t>\|--source <f>) [--ticket <id>] [--priority P0\|P1\|P2]` | Yes (`owner`/`maintainer`) | Delivers a 1-hop downward directive into `layers/<child>/` and records `stage: delegated` in parent `WORKTASK.md`. |
| **`C3` Governance** | `zcg promote-from-project <dir> --source <rel> [--to-layer <id>] [--upstream-dir <d>] [--create-pr]` | Yes | Promotes a reusable rule/skill 1-hop upward (with `scan_open_source_agnosticism` and anonymization when targeting OSS). |
| **`C3` Governance** | `zcg manage-roster [<dir>] [--add <e>] [--remove <e>] [--role <r>]` | Yes (`owner`) | Updates `layer_authority.roster` in `system/zcg-node.json` and synchronizes `.github/CODEOWNERS`. |
| **`C3` Governance** | `zcg set-authority [<dir>] --owner-role <title> [--emails <csv>]` | Yes (`owner`) | Sets primary owner role title and authorized emails in `system/zcg-node.json`. |
| **`C3` Governance** | `zcg configure-git-policy [<dir>] [--protected <csv>]` | Yes (`owner`) | Configures protected branches (`main,master,env/pre,env/pro`) and PR gates. |
| **`C3` Governance** | `zcg check-env-promotion [<dir>] --to-env <tst\|pre\|pro> [--files <csv>]` | Audit log | Evaluates progressive `dev -> tst -> pre -> pro` gates and $N$-departmental surface consensus. |
| **`C3` Governance** | `zcg record-decision [<dir>] --item <ref> --decision <approve\|reject\|defer\|blocked> --reason <txt>` | Yes (`validator`+) | Records a signed governance decision in `WORKTASK.md` and `logs/governance_audit.jsonl`. |
| **`Subtree`** | `zcg subtree <list\|pull\|pull-all\|register> [args]` | Git sync | Lists, registers (`layers/<name>`), or synchronizes mounted child/knowledge subtrees. |
| **`Workstation`** | `zcg install-antigravity \| workstation-sync \| workstation-backup \| workstation-audit \| workstation-restore \| stage-showcase [--json]` | Host ops | Executes the corresponding Ubuntu 26.04 physical workstation or ephemeral showcase script in `scripts/` (streams live TTY progress/colors interactively; returns JSON when non-TTY or `--json`). |
| **`OSS` Engine** | `zcg oss <push-branch\|promote-master\|publish> [<dir>] [--remote-url <u>] [--release-version <v>] [--contrib-branch <b>] [--create-pr] [--verify]` | Git / Release | Executes isolated Open-Source engine contribution workflows (root `Makefile` `oss-push-branch`, `oss-promote-master`, `oss-publish`) strictly guarded by `[OSS_DEV_ONLY_BLOCKED]` and `git archive` tracker stripping. |

---

## 2. `zcg-mcp` JSON-RPC 2.0 Catalog (`9` Resources, `9` Tools, `3` Prompts)

`zcg-mcp` communicates over `stdio` (supporting both `Content-Length` LSP framing and newline-delimited JSON-RPC 2.0, protocol `2024-11-05`) and **MCP `Streamable HTTP` (`POST/GET/DELETE /mcp` via `zcg-mcp --http-port <port> [--http-host <host>]`)**, accepting `workspace_dir` on every tool call so a single `$HOME` daemon or `.agents/sidecar.json` supervisor serves any open workspace:

| Surface Kind & Identifier | Ring | Arguments / Parameters | Returned Payload & Normative Contract |
| :--- | :---: | :--- | :--- |
| `zcg://node/identity` | `R0` | Resource URI | Node SemVer, `layer_id`, `layer_role`, `precedence`, OS release, container flag, and upstream lineage. |
| `zcg://system/manifests` | `R0` | Resource URI | Workstation APT, Snap, NPM, external recipes, and GNOME extension inventories from `system/*.txt`. |
| `zcg://governance/rules` | `R0` | Resource URI | Active `antigravity/.gemini/config/AGENTS.md` global baseline. |
| `zcg://governance/hooks` | `R0` | Resource URI | Active `antigravity/.gemini/config/hooks.json` lifecycle configuration. |
| `zcg://governance/skills` | `R0` | Resource URI | Parsed frontmatter catalog of global Antigravity `SKILL.md` playbooks. |
| `zcg://governance/templates` | `R0` | Resource URI | Full `19`-pack `templates/` metadata catalog (`zcg-template-v1`). |
| `zcg://docs/index` | `R0` | Resource URI | Authoritative documentation index ([`docs/README.md`](../README.md)). |
| `zcg://mcp/topology` | `R0` | Resource URI | Validated `system/zcg-node.json`, mounted layers, and `R0..W` capability rings. |
| `zcg://mcp/diagnostics` | `R0` | Resource URI | Runtime JSONL telemetry summary (`logs/mcp_invocations.jsonl`, `mcp_compaction.jsonl`, `mcp_alerts.jsonl`). |
| `get_layer_overview` | `R0` | `workspace_dir?`, `layer?`, `include_ast_graph?` | **4-Channel Executive Digest**: Channel 1 (`entity_identity`, `network_topology`, `work_orchestration`, `runtime_orchestration`), Channel 2 (`templates`, optional `codebase_ast_graph`), Channel 3 (`hooks`, `warnings`), Channel 4 (`deep_context_index`). |
| `audit_node_drift` | `R1` | `workspace_dir?`, `mode` (`verify-repo` \| `system-audit` \| `both`) | Runs `scripts/verify-repo.sh` and/or `scripts/workstation-audit.sh` (`180s` bounded timeout) plus `citation_lifecycle_radar` (`Q1..Q4`). |
| `read_layer_document` | `R0` | `relative_path`, `layer?`, `branch_ref?`, `workspace_dir?` | Path-contained reader for `README.md`, `SYLLABUS.md`, `WORK*`, `docs/**`, `corporate/**`, `surfaces/**`, `roadmaps/**`, `templates/**`, and `.agents/{rules,skills}/` (with zero-checkout `branch_ref` `DMCP`). |
| `query_governance_rules` | `R0` | `query`, `layer?`, `resolution` (`L0\|L1\|L2`), `min_epistemic_grade?`, `branch_ref?`, `workspace_dir?` | Searches rules/docs across layers, adaptive `consumer_viewpoint` (`M1..M4`), `citation_receipt`, and `rcap1` `capsule_token`. |
| `unfold_context_capsule` | `R0` | `capsule_token`, `target_level?` (`L0..L3`), `agent_tier?`, `environment?`, `resonance_key?`, `workspace_dir?` | Cryptographically verifies and unfolds `rcap1` envelopes hop-by-hop (`L0 -> L1 -> L2 -> L3`) and runs `verify_epistemic_context_claims`. |
| `resolve_surface_governance` | `R0` | `target_path?`, `architectural_plane?`, `scope?`, `traits?`, `environment?`, `resolution_override?`, `workspace_dir?` | Weaves `0..N` layer `surface_bindings` in *Lex Superior* (`0..100`) and *Lex Specialis* order for `target_path`. |
| `compare_layer_patterns` | `R1` | `project_rules?`, `project_skills?`, `layer?`, `workspace_dir?` | Compares a project's `.agents/` against layer templates (`in_sync`, `drifted`, `novel_project_assets`). |
| `discover_federated_mcps` | `R1` | `workspace_dir?`, `filter_role?`, `environment?`, `layer?` | Lists environment-scoped (`dev..pro`) federated MCPs, `effective_guardrails`, and `mcp_autonomy_matrix` (`R0..W`). |
| `orchestrate_ephemeral_fork` | `R2` | `action` (`spawn\|inspect\|evaluate\|reap\|catalog\|seal-return\|verify-return\|project-branch\|chain-capsule-ref`), ... | Manages `strictly-read-only` Ephemeral Department Bots, `rcap1` return digest membranes, `GRCC` refs, and `DMCP` branch projections. |
| `orient-on-node`, `audit-container-or-node`, `orchestrate-federated-mcps` | `R0` | `environment?`, `target_scope?` | Structured MCP prompts returning step-by-step orientation, drift audit, and federation playbooks. |

---

## 3. Standalone Container, Cloud Run & SSH Federated MCP Orchestration

Because `ZeroCloudGravity` has `0` external runtime dependencies (`pyproject.toml` `dependencies = []`) and ships a hardened non-root `Dockerfile` (`USER zcg`, `ZCG_NO_BROWSER=1`, `ENTRYPOINT ["zcg-mcp"]`), any container, VM, or remote layer node can expose `zcg-mcp` over `stdio`:

```json
{
  "mcpServers": {
    "zcg-mcp": {
      "command": "/home/user/zero-cloud-gravity/.venv/bin/zcg-mcp",
      "args": ["--repo-dir", "/home/user/<persona>-profile"]
    },
    "zcg-container-node": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--read-only", "zero-cloud-gravity:1.2.0", "--layer-id", "prod-api-node", "--layer-role", "service-node"]
    },
    "zcg-remote-ssh": {
      "command": "ssh",
      "args": ["zcg@node.intranet.local", "/opt/zero-cloud-gravity/.venv/bin/zcg-mcp", "--repo-dir", "/srv/dept-node"]
    }
  }
}
```

---

## 4. Security Error Contracts (`OWASP ASVS` + `MCP-Sec`) & Maintainer Extension Playbook

The table below catalogs the deterministic security and governance error codes enforced across `src/zcg/`:

| Canonical Error Code | Enforcing Module | Trigger Condition & Remediation |
| :--- | :--- | :--- |
| `PATH_CONTAINMENT_VIOLATION` | `topology/identity.py`, `mcp/node_base.py` | Path traversal (`../`), symlink escape, or out-of-workspace file access attempt. |
| `CROSS_TIER_PROMOTION_BYPASS` | `governance/policy/authority.py` | Attempting to promote or delegate across non-adjacent tiers (`Squad -> Root 0` or `Department -> OSS`). Route 1-hop via immediate parent. |
| `EPISTEMIC_PRECEDENCE_VIOLATION` | `capsules/citations.py` | Lower-credibility claim (`E0/E1`) attempting to override a higher-credibility law or contract (`E2/E3`). |
| `CITATION_DRIFT_DETECTED` | `capsules/citations.py` | Cited `citation_receipt` `@<digest16>` does not match current official section digest. Re-query section and update citation. |
| `CAPSULE_CAPABILITY_INSUFFICIENT` | `mcp/unfold.py` | `flash`/`flash_lite` tier attempting to unfold `L2`/`L3`, or non-`pro` tier unfolding `L3` in `"pro"` environment. |
| `CAPSULE_RESONANCE_DENIED` | `mcp/unfold.py`, `capsules/codec.py` | Missing or invalid `resonance_key`, cross-issuer (`iss`) mismatch, or cross-environment (`env`) replay. |
| `EPHEMERAL_LEASE_EXPIRED_OR_SHREDDED` | `ephemeral/lifecycle.py`, `capsules/codec.py` | Attempting to use or verify a return capsule from an expired or reaped ephemeral fork. |
| `SURFACE_BOUNDARY_VIOLATION` | `capsules/codec.py` | Ephemeral bot return digest touches `modified_files` outside its leased `surface_globs`. |
| `WALLET_EXTERNAL_LINK_BLOCKED` | `governance/policy/capabilities.py`, `governance/workspace/links.py`, `cockpit/routing/mesh_router.py` | Attempting non-epistemic `zcg link` or `POST /api/modules/node-mesh/link` on an `R3` local-only `<persona>-wallet` node (only read-only `knowledge-feed` links to `knowledge` corpora with empty `cockpit_url` are allowed; route peer/settlement links via `<persona>-work`). |
| `CAPABILITY_ACTOR_ROLE_BLOCKED` / `CAPABILITY_CEILING_*_BLOCKED` | `governance/policy/capabilities.py` | Actor role lacks lifecycle permission or inherited *Lex Superior* `capability_policy` (`blocked_operations` / `curated-allowlist`) forbids the plugin, link target, or operation. |
| `SKILL_SECURITY_VIOLATION` | `governance/policy/capabilities.py`, `cockpit/ops/lifecycle.py`, `governance/workspace/promotion.py` | Skill or config failed `lint-skills` static scan (bidi/zero-width Unicode, `curl \| sh`, unauthorized egress URL, or `..` path escape). |
| `GLOSSARY_DEFINITION_CONFLICT` | `governance/policy/handoff.py` | Sender and receiver nodes map the same informal alias on the same axis to conflicting canonical terms without a *Lex Superior* parent resolution. |
| `CAPABILITY_CEILING_PLUGIN_DIGEST_MISMATCH` | `governance/policy/capabilities.py`, `cockpit/ops/lifecycle.py` | Plugin pack's C-backed `SHA-256` Merkle digest does not match `Root 0` `capability_policy.allowed_plugin_digests`, or upstream/local digests conflict. |
| `STATIC_GCP_KEY_FORBIDDEN` / `STATIC_CONTAINER_SECRET_FORBIDDEN` | `providers/cloud_gcp.py`, `providers/container_edge.py` | Static `service_account` JSON key file (`GOOGLE_APPLICATION_CREDENTIALS`), inline `private_key` material, or inline container secret detected; migrate to Workload Identity Federation, ambient ADC, or runtime secret mounts. |
| `SRI_POLICY_VIOLATION` | `web/auth/security.py`, `web/http/factory.py` | HTML response references an external `<script src>` or `<link rel="stylesheet" href>` outside `allowed_cdn_origins` or missing `integrity="sha384-..."` + `crossorigin`. |
| `UNAUTHORIZED_CDN_EGRESS_ORIGIN` / `UNAUTHORIZED_ARTIFACT_MIRROR` | `governance/policy/egress.py` | Declared `cdn_origins` or private `artifact_mirrors` (`Artifact Registry` / PyPI / APT) fall outside the inherited *Lex Superior* `network_egress_policy.allowed_domains` ceiling. |
| `DECISIONS_BATCH_LIMIT_EXCEEDED` | `governance/runtime/tool_isolation.py` | Calibrated `Gemini Decisions API` / `LiteRT` (`Gemma 4`) request batch is empty or exceeds `MAX_GEMINI_DECISIONS_BATCH` (`1,000` items). |
| `MCP_CONNECTOR_NOT_ALLOWLISTED` / `MCP_CONNECTOR_WRITE_MODE_BLOCKED` | `governance/runtime/mcp_connectors.py` | Opt-in external MCP connector is absent from `OFFICIAL_MCP_CONNECTORS` / `allowed_mcp_connectors`, or requests mutating (`read_only: false`) mode in `"pro"` without explicit authorization. |
| `MCP_HTTP_ORIGIN_DENIED` | `mcp/http_transport.py` | Untrusted `Origin` header attempted to invoke `POST/GET/DELETE /mcp` over `Streamable HTTP` (DNS-rebinding guard). |
| `PLAINTEXT_NON_LOOPBACK_BLOCKED` / `INVALID_TLS_CONFIGURATION` | `web/auth/tls.py`, `web/http/server.py` | Non-loopback listener (`0.0.0.0` / LAN IP) started without `--tls-certfile`/`--tls-keyfile` or `--behind-tls-proxy`, or incomplete/missing PEM certificate/key/CA files. |
| `COMMUNITY_PLUGIN_READ_ONLY` | `cockpit/ops/plugin_sdk.py` | Attempting `--in-pack` mutation on a community starter `plugin-stack` pack outside `open-source` engine clones; omit `--in-pack` to write into `<workspace>/surfaces/web/`. |

### 4.1. Maintainer Checklist for Extending `ZeroCloudGravity`

1. **Adding or Modifying a Source Module (`src/zcg/<subpkg>/<mod>.py`)**: Keep `<= 384` lines, include `Specification: docs/architecture/0X_*.md` in the module docstring, create the `1:1` unit test at `tests/unit/zcg/<subpkg>/test_<mod>.py` (`<= 464` lines, standalone `# Arrange`, `# Act`, `# Assert` comments in every `def test_*`, `100.00%` isolated statement & branch coverage), and register both in the `1:1:1` table of `docs/architecture/0X_*.md`.
2. **Adding a New Declarative Template Pack (`templates/<group>/<id>/`)**: Run `zcg scaffold-template <id> --kind <group>`, author `template.json` (`zcg-template-v1`), `rules/<id>.md`, and `README.md` (`< 465` lines), and verify with `make verify` (`8/8` gates).
