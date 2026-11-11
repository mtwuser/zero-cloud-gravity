---
epistemic_grade: E3
---

# Architecture 04 — Zero-Cloud Cockpit, `$HOME` Composer & Intranet Surfaces (`src/zcg/cockpit/`)

> **Normative Specification — Subsystem 4 (`src/zcg/cockpit/{workstation,surfaces,provenance,mesh_router,ledger_router,dashboard_app,node_context,orientation_ui,plugin_sdk,asgi,lifecycle,status}.py`)**
>
> This specification defines global `AGENTS.md` composition (`<= 18,000` bytes with Dual-Repo `$HOME` personal rule injection and `zcg-mcp` `--repo-dir` binding), deterministic `.intranet.local` / `.personal.local` / `.knowledge.local` & RFC 6761 `*.localhost` routing (`:8700 + precedence` + `Root 0` `domain_governance` & DNS zone manifests), `3-Scope` JSON surface projection (`0` host path leaks), Sovereign Exposure Posture (`private-personal` vs. `private-intranet` vs. `public-live` External Node Passport), selective `Web <-> Repo` veracity (`surface_veracity_mode`, `public_surface_seal.json`, and `GET /.well-known/zcg-attestation.json`), parallel context branch discovery & `spinout-project` graduation studio, WCAG 2.2 AA zero-build HTML5 cockpits, composable `enabled_modules` capability composition and contained `plugin-stack` `routers/*.py` SDK loading over [`src/zcg/web/`](06_web_and_api_application_engine.md) (`create_web_app`), and `PYTEST_CURRENT_TEST`-safe background daemon management in `src/zcg/cockpit/`.

---

## 1. `1:1:1` Source $\leftrightarrow$ Unit Test $\leftrightarrow$ Responsibility Matrix (`src/zcg/cockpit/`)

All twelve modules in `src/zcg/cockpit/` project sovereign node governance onto the decoupled [`src/zcg/web/`](06_web_and_api_application_engine.md) engine and manage `$HOME` workstation state without external web frameworks or frontend build toolchains:

| Implementation Module | Isolated `1:1` Unit Suite | Primary Symbols & Normative Scope |
| :--- | :--- | :--- |
| [src/zcg/cockpit/workstation.py](../../src/zcg/cockpit/workstation.py) | [tests/unit/zcg/cockpit/test_workstation.py](../../tests/unit/zcg/cockpit/test_workstation.py) | `register_antigravity_workspace` (`~/.gemini/antigravity/workspaces.json`), `set_global_agents_profile` (`PROFILE_TEMPLATE_CHAIN` + `--lang` + `--workstation-dir` personal rule composition + `<= 18,000`-byte cap + GNU Stow), and `_ensure_fixed_mcp_registered` (`--repo-dir <workstation_dir>`). |
| [src/zcg/cockpit/surfaces.py](../../src/zcg/cockpit/surfaces.py) | [tests/unit/zcg/cockpit/test_surfaces.py](../../tests/unit/zcg/cockpit/test_surfaces.py) | `resolve_node_intranet_topology` (`:8700 + precedence`, `.intranet.local` / `.personal.local` / `.knowledge.local`, & RFC 6761 `*.localhost` subdomain routing), `materialize_node_data_scopes` (`node_scope.json`, `network_scope.json`, `federation_scope.json`, external `cockpit-shell.js`, + DNS/attestation provenance surfaces with `0` host `workspace_path` leaks), `COCKPIT_SHELL_JS`, and strict-CSP WCAG 2.2 AA `render_node_cockpit_html`. |
| [src/zcg/cockpit/provenance.py](../../src/zcg/cockpit/provenance.py) | [tests/unit/zcg/cockpit/test_provenance.py](../../tests/unit/zcg/cockpit/test_provenance.py) | `Root 0` `domain_governance` inheritance & RFC 6761 `*.localhost` subdomain routing (`resolve_domain_governance`), declarative DNS manifest projection (`materialize_dns_zone_manifest`), privacy-safe copyright & GitHub source-origin resolution (`normalize_repo_web_url`, `resolve_source_origin_metadata`, `render_provenance_footer_html`), and selective `Web <-> Repo` veracity (`resolve_surface_veracity_mode`, `build_public_surface_seal`, `materialize_node_provenance_surfaces`). |
| [src/zcg/cockpit/mesh_router.py](../../src/zcg/cockpit/mesh_router.py) | [tests/unit/zcg/cockpit/test_mesh_router.py](../../tests/unit/zcg/cockpit/test_mesh_router.py) | Cohesive `1:1` sovereign node `APIRouter` (`create_node_mesh_router`) inspecting `3-Scope` topology (`1-hop` governor, children, lateral peers, sanitized `linked_nodes`, and federated mounts). |
| [src/zcg/cockpit/ledger_router.py](../../src/zcg/cockpit/ledger_router.py) | [tests/unit/zcg/cockpit/test_ledger_router.py](../../tests/unit/zcg/cockpit/test_ledger_router.py) | Cohesive `1:1` sovereign node `APIRouter` (`create_work_ledger_router`) exposing `own_node_ledger` sprint metrics, `environment_gates`, and `DeferredJobQueue` `T2` lifecycle (`POST /jobs`, `POST /jobs/{task_id}/progress`). |
| [src/zcg/cockpit/dashboard_app.py](../../src/zcg/cockpit/dashboard_app.py) | [tests/unit/zcg/cockpit/test_dashboard_app.py](../../tests/unit/zcg/cockpit/test_dashboard_app.py) | Declarative multi-capability Reference Dashboard composer: `VALID_DASHBOARD_MODULES` (`7` capability modules), `ARCHETYPE_DEFAULT_MODULES`, `ARCHETYPE_DEFAULT_PLUGIN` (`6` `plugin-stack` Reference Dashboards), `resolve_archetype_crud_schema` (`study-drills`, `epistemic-entries`, `workspace-records`), `resolve_enabled_modules`, `build_modular_workbench_spec`, `MODULAR_WORKBENCH_JS`, and `build_dashboard_routers`. |
| [src/zcg/cockpit/node_context.py](../../src/zcg/cockpit/node_context.py) | [tests/unit/zcg/cockpit/test_node_context.py](../../tests/unit/zcg/cockpit/test_node_context.py) | Sovereign Exposure Posture (`classify_exposure_posture`), External Node Passport sanitization (`build_cockpit_passport_data`), parallel context branch discovery (`inspect_context_branches`), host/knowledge metadata collectors, and directional cross-node links (`build_cross_node_links`). |
| [src/zcg/cockpit/orientation_ui.py](../../src/zcg/cockpit/orientation_ui.py) | [tests/unit/zcg/cockpit/test_orientation_ui.py](../../tests/unit/zcg/cockpit/test_orientation_ui.py) | `SafeHTML` node orientation compass (`orientation_bar_html`), directional cross-node switcher (`cross_node_nav_html`), archetype-tailored host, `specialty/*` knowledge, and `spinout-project` spotlight cards (`build_node_dashboard_enrichment`), and `/api/modules/node-context` (`create_node_context_router`). |
| [src/zcg/cockpit/plugin_sdk.py](../../src/zcg/cockpit/plugin_sdk.py) | [tests/unit/zcg/cockpit/test_plugin_sdk.py](../../tests/unit/zcg/cockpit/test_plugin_sdk.py) | Plugin Application SDK: `resolve_plugin_pack_dir`, namespace-isolated & path-contained `load_plugin_routers` (`templates/plugin-stack/<plugin>/routers/*.py`), and `scaffold_plugin_module` (`zcg scaffold-plugin-module <plugin> <module>` generating Hexagonal `models.py` + `service.py` + `routers/<pkg>.py` + `web/templates/partials/<mod>.html`). |
| [src/zcg/cockpit/asgi.py](../../src/zcg/cockpit/asgi.py) | [tests/unit/zcg/cockpit/test_asgi.py](../../tests/unit/zcg/cockpit/test_asgi.py) | Sovereign node Native ASGI adapter (`resolve_cockpit_web_dirs`, `create_node_cockpit_asgi_app`, and `run_cockpit_daemon_cli`) delegating to `create_web_app` (`zcg.web.factory`) with cascading `<ws>/surfaces/web/{templates,static}` $\rightarrow$ active `plugin-stack` $\rightarrow$ base archetype resolution, contained plugin `routers/*.py` mounting, `/`, `/dashboard`, `/dashboard/overview`, & `/fragments/ack` routes, and `surfaces/{data,web}` fallback. |
| [src/zcg/cockpit/lifecycle.py](../../src/zcg/cockpit/lifecycle.py) | [tests/unit/zcg/cockpit/test_lifecycle.py](../../tests/unit/zcg/cockpit/test_lifecycle.py) | `manage_plugin_daemon` (spawning detached `zcg.cockpit.asgi:run_cockpit_daemon_cli` loopback daemon with `DocsAccessMode` scoped by environment), `manage_plugin_service` (`10` lifecycle actions: `install`..`teardown` with `0` automatic OS browser launches), and `summarize_runtime_orchestration`. |
| [src/zcg/cockpit/status.py](../../src/zcg/cockpit/status.py) | [tests/unit/zcg/cockpit/test_status.py](../../tests/unit/zcg/cockpit/test_status.py) | `inspect_workspace_status` (`zcg status`) combining `entity_identity`, `network_topology`, `work_orchestration`, `runtime_orchestration`, `setup_state`, `horizon`, and `agent_diff` in `< 0.2s`. |

---

## 2. Global `AGENTS.md` Composer & Dual-Repo `$HOME` Coupling (`workstation.py`)

`set_global_agents_profile` composes `antigravity/.gemini/config/AGENTS.md` from modular `human-stack` and `context-stack` templates while bridging the passive Open-Source engine (`~/zero-cloud-gravity`) with the operator's personal `Root 0` workstation (`~/<persona>-pc`):

| Profile (`VALID_GLOBAL_PROFILES`) | Composed Template Chain (`PROFILE_TEMPLATE_CHAIN`) | Optional Personal Workstation Rule (`--workstation-dir`) | Byte Budget Gate (`AGENTS_MD_MAX_BYTES`) |
| :--- | :--- | :--- | :--- |
| `universal-base` *(Recommended for `$HOME`)* | `universal-base.md` (`~2,571 B`) | `+ <ws-dir>/templates/<ws-id>/rules/<ws-id>.md` (`~400 B`) | Strictly `<= 18,000` bytes (`~15 KB` headroom) |
| `academic-base` / `academic` | `universal-base.md` + `academic-base.md` | `+ <ws-id>.md` when `--workstation-dir` is supplied | Strictly `<= 18,000` bytes |
| `science-base` / `science` | `universal-base.md` + `science-base.md` | `+ <ws-id>.md` when `--workstation-dir` is supplied | Strictly `<= 18,000` bytes |
| `technical` | `universal-base.md` + `science-base.md` + `software-engineering.md` | `+ <ws-id>.md` when `--workstation-dir` is supplied | Strictly `<= 18,000` bytes |
| `business-base` / `business` | `universal-base.md` + `business-base.md` | `+ <ws-id>.md` when `--workstation-dir` is supplied | Strictly `<= 18,000` bytes |
| `full` | `universal-base` + `academic-base` + `science-base` + `software-engineering` + `business-base` (`~7,425 B`) | `+ <ws-id>.md` when `--workstation-dir` is supplied | Strictly `<= 18,000` bytes |

1. **Dual-Plane Language Injection (`--lang <en|es|it|fr|de|pt>`)**: Substitutes `Interaction Language: <Label> (<code>)` in `AGENTS.md` and persists `global_profile` and `interaction_language` into `workstation_dir/system/zcg-node.json` without translating English repository files.
2. **Personal `Root 0` `zcg-mcp` Binding (`_ensure_fixed_mcp_registered`)**: When `run_stow=True` and `workstation_dir` contains `system/zcg-node.json`, `~/.gemini/config/mcp_config.json` (and symlinked `~/.gemini/antigravity/mcp_config.json`) registers `"command": "<engine_dir>/.venv/bin/zcg-mcp"` with `"args": ["--repo-dir", "<workstation_dir>"]` so `zcg-mcp` serves the operator's personal `Root 0` node by default.

---

## 3. Deterministic Port & `.local` Subdomain Topology (`surfaces.py`)

Every sovereign node maps its `precedence` (`0..100`), `entity_kind`, `layer_role`, and `active_env` (`dev|tst|pre|pro`) to a collision-free localhost port (`8700 + precedence`) and canonical `.local` intranet domain:

| Node Archetype | Port Formula | Canonical Subdomain Pattern | Default Cockpit (`plugin-stack`) |
| :--- | :--- | :--- | :--- |
| **`$HOME` Personal Workstation (`90`)** | `8700 + 90 = 8790` | `https://<env>.<id>.personal.local` | [`workstation-control-tower`](../../templates/plugin-stack/workstation-control-tower/README.md) |
| **Personal Tutor Sub-Layer (`86`)** | `8700 + 86 = 8786` | `https://<env>.<id>.<root>.personal.local` | [`tutor-study-cockpit`](../../templates/plugin-stack/tutor-study-cockpit/README.md) |
| **Personal Career & Ventures Hub (`87`)** | `8700 + 87 = 8787` | `https://<env>.<id>.<root>.personal.local` | [`node-work-cockpit`](../../templates/plugin-stack/node-work-cockpit/README.md) (`personal-career-and-ventures`) |
| **Corporate `Root 0` Hub (`10`)** | `8700 + 10 = 8710` | `https://<env>.<id>.intranet.local` | [`corporate-root-hub`](../../templates/plugin-stack/corporate-root-hub/README.md) |
| **Fiduciary SecOps / Legal (`5`)** | `8700 + 5 = 8705` | `https://<env>.<id>.<root>.intranet.local` | [`secops-mcp-guardian`](../../templates/plugin-stack/secops-mcp-guardian/README.md) |
| **Functional Department / Squad (`15..50`)** | `8700 + precedence` | `https://<env>.<id>.<root>.intranet.local` | [`node-work-cockpit`](../../templates/plugin-stack/node-work-cockpit/README.md) |
| **Public / Private `knowledge` & Sovereign Twins (`gov-*`, `sci-*`, `geo-*`, `org-*`, `pub-*`, `20` / `88`)** | `8700 + precedence` | `https://<env>.<id>.knowledge.local` (`pro` = `public-remote-live` when `visibility == "public"`) | [`knowledge-stewardship-portal`](../../templates/plugin-stack/knowledge-stewardship-portal/README.md) *(or custom portal plugin)* |

---

## 4. `DeliveryChannel` (`Z1..Z4 × T1..T5`), Adaptive Runtime Telemetry, Three-Scope Feeds & Headless Daemon (`surfaces.py`, `lifecycle.py`)

When a cockpit plugin is installed or activated (`zcg apply-project <dir> --service-action activate` or `make activate-plugin`), `materialize_node_data_scopes` writes three hermetic JSON feeds consumed by `surfaces/web/index.html` using the 4-zone presentation and adaptive runtime observability engine:
1. **`surfaces/data/node_scope.json`**: Node identity, `precedence`, `active_env`, `intranet_topology`, `own_node_ledger` task metrics, and `representation_context` containing:
   - **`delivery_channel` (`Zone Z1..Z4 × Tier T1..T5`)**: Declares `protocol: "python314-native-asgi"`, `zones: ["Z1", "Z2", "Z3", "Z4"]`, `tier` (`T1..T5` with latency budget `200..300000 ms`), and `http_poll_stop_status: 286`.
   - **`runtime_telemetry` (`OPTIMAL | DEGRADED | CRITICAL`)**: Evaluates runtime/work-ledger `health_score` and bridges health regime alerts directly to `.agents/telemetry/` (`Q1..Q4`) and `WORKTASK.md` (`0` separate external ledger DB).
   - **`dual_world_contract` (`Common Base vs. Use-Case Overlay`)**: Separates the reusable `common_base_plugin` from the sovereign `use_case_overlay` (`school-student-m1-m2` vs. `university-specialty-m2-m3`, `small-startup` vs. `medium-scaleup` vs. `large-enterprise`, `knowledge-stewardship-portal`, `secops-mcp-guardian`), **strictly omitting host filesystem paths**.
2. **`surfaces/data/network_scope.json`**: `1-hop` `upward_governor`, `downward_governed_nodes`, `lateral_peers`, sanitized `linked_nodes` (`relation`, `cockpit_url`, `shared_packs` with `0` host `workspace_path` or local `target_ref` leaks), and `inter_layer_exchange` delegations/proposals, rendered in **`Z2` (`1-Hop & Linked Cloud Directory`)**.
3. **`surfaces/data/federation_scope.json`**: Active `fleet_plugin_inventory`, `mounted_layers`, `intranet_topology`, and `cloud_iac_target`.
4. **4-Zone HTML5 Cockpit (`data-zcg-surface="cockpit"`) & Zero-Auto-Browser Policy**: `render_node_cockpit_html` emits a WCAG 2.2 AA zero-build surface using `--zcg-*` CSS tokens, `Z1..Z4` zones, and `window.IslandBus`, while `manage_plugin_service` and `bootstrap_node_workspace` never spawn OS browser tabs (`0` `xdg-open` invocations), returning clickable `local_subdomain_dashboard_url` (`active_dashboard_url`) and `localhost_url` endpoints instead.

---

## 5. `16`-Channel `DeliveryChannel` Matrix (`Zone × Tier`), Native ASGI Runtime, `SSE` & Transport Security (`channels.py`, `asgi.py`)

Every HTTP/ASGI endpoint served by a Zero-Cloud Node cockpit binds an explicit `DeliveryChannel` (`x-zcg-delivery-channel`) combining presentation `Zone` (`Z1..Z4`) and processing `Tier` (`T1..T5`), enforced by the zero-dependency Python 3.14 Native ASGI engine (`create_node_cockpit_asgi_app`):

| Zone (`Presentation`) | Allowed Tiers (`T1..T5`) | Derived `CommPattern` | Zone-Graded `Content-Security-Policy` (`script-src` / `connect-src`) |
| :--- | :--- | :--- | :--- |
| **`Z1` (`static`)** | `T1` (`STATIC_SYNC` only; `Z1 × T2..T5` rejected) | `request_response` | `script-src 'none'; frame-ancestors 'none'` (`0 KB` client JS enforced by browser) |
| **`Z2` (`swap`)** | `T1..T5` (`SWAP_SYNC..SWAP_PIPELINE`) | `T1`: `request_response`; `T2,T4`: `polling`; `T3,T5`: `sse` | `script-src 'self'; connect-src 'self'; frame-ancestors 'none'` |
| **`Z3` (`island`)** | `T1..T5` (`ISLAND_SYNC..ISLAND_PIPELINE`) | `T1`: `request_response`; `T2,T4`: `polling`; `T3,T5`: `sse` | `script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'` |
| **`Z4` (`immersive`)** | `T1..T5` (`IMMERSIVE_SYNC..IMMERSIVE_PIPELINE`) | `T1`: `request_response`; `T2,T4`: `polling`; `T3`: `websocket`; `T5`: `sse` | `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; connect-src 'self' ws: wss:` |

1. **Adaptive Partial Swap (`HX-Request`) & `HTTP 286` Poll-Stop**: `GET /` serves the full 4-zone HTML5 cockpit (`ISLAND_SYNC`) on standard navigation and switches to a targeted `Z2` partial fragment (`SWAP_SYNC`, with optional `hx-reselect` / `hx-reswap: outerHTML` auto-fragment headers) when `hx-request: true` is present. `GET /api/poll/status` (`SWAP_DEFERRED`) returns `HTTP 200` while tasks remain in flight and **`HTTP 286`** (`poll_status_code(done=True)`) upon completion to terminate client polling loops deterministically.
2. **Versioned `SSE` Streaming (`SSEMessage`, `VersionedPayload`, `heartbeat_sse_stream`)**: `GET /events` (`ISLAND_STREAM`, `text/event-stream`) emits monotonic `VersionedPayload` snapshots for anti-race client reconciliation interleaved with `: heartbeat` comments on idle intervals and clean `lifespan.shutdown` stream termination.
3. **Transport Hardening (`CSRF`, `413` Payload Cap, `DocsAccessMode`, Path Containment)**: Mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`) on `Z1`/`Z2` require constant-time `hmac.compare_digest` verification of `x-zcg-csrf-token` (`403 CSRF_VALIDATION_FAILED`); request bodies exceeding `max_payload_bytes` (`DEFAULT_MAX_PAYLOAD_BYTES = 1,048,576`) abort immediately with `413 PAYLOAD_TOO_LARGE`; `/docs` and `/openapi.json` enforce `DocsAccessMode` (`PUBLIC` -> `200`, `AUTHENTICATED` -> Bearer check `200/401`, `DISABLED` -> `404` default in `pro`); and static `/data/*` + `surfaces/web/*` lookups enforce `ensure_contained_path`.

---

## 6. Adaptive Health Probes, Resilience Pipeline, Bulkhead & Runtime Telemetry Audit DAG (`probes.py`, `resilience.py`, `telemetry.py`)

Sovereign node cockpits maintain deterministic runtime stability, saturation isolation, and tamper-evident observability using three pure stdlib control-theory modules (`0` external runtime dependencies):

| Subsystem Module | Control-Theory Primitive | Exact Cut-Points (`N` vs. `N ± 1`) & Operational Contract |
| :--- | :--- | :--- |
| **`probes.py`** | `SamplingCadenceCalculator`, `SlidingProgressMonitor`, `HeartbeatJitterTracker` | Enforces anti-aliasing sliding observation windows (`W >= 2.0 * T_cycle`, `T_sample = 0.5 * T_cycle`, bounded jitter `<= 0.5`), classifies task progress into `PROGRESSING \| INSUFFICIENT_SAMPLES \| STAGNANT_LOOP`, and grades tick dispersion (`jitter_ms`) across `STABLE (< 50 ms) \| ELEVATED (>= 50 ms) \| SATURATED (>= 200 ms)`. |
| **`resilience.py`** | `DeadlineBudgetGuard`, `chunk_items`, `DeferredJobQueue`, `StaleResourceReaper`, `BulkheadIsolationGuard` | Bounds unacknowledged in-flight operations (`max_in_flight`) and monotonic remaining deadline budgets, chunks batch payloads via `itertools.islice`, schedules `T2..T4` background jobs, evicts stale/stagnant/over-retried tasks (`EXPIRED`), and sheds interactive `T1` load to `T2` (`SHIELDED`) when `utilization_ratio >= saturation_threshold` and `active_heavy_tasks > 0`. |
| **`telemetry.py`** | `TelemetryGrade` (`G1..G3`), `HealthRegime`, `RuntimeTelemetryScorer`, `TelemetryAuditDAG` | Computes `4`-weight composite health (`0.30 * volume + 0.25 * latency + 0.30 * success + 0.15 * trend` on `0.0..100.0`), maps regimes (`OPTIMAL >= 80`, `DEGRADED >= 55`, `PROTECTIVE >= 30`, `CRITICAL < 30`) and `TransitionAction` (`CHANNEL_PROMOTE >= 85`, `STABLE >= 55`, `CHANNEL_DEMOTE > 20`, `RETIREMENT <= 20`, `auto_eligible` strictly at `G3`), and persists SHA-256 hash-chained `AuditDecisionNode` records in SQLite WAL under `.agents/telemetry/runtime_audit_dag.sqlite3`. |

---

## 7. Composable Capability Modules (`enabled_modules`) & `create_web_app` Composition (`mesh_router.py`, `ledger_router.py`, `dashboard_app.py`)

Instead of hardcoded vertical silos, every Reference Dashboard composes an ordered tuple of domain-neutral capability `APIRouter` modules (`enabled_modules` in `node_scope.json` and `modular_workbench` in Zone `Z3`, mounted under `/api/modules/*` onto `create_web_app` and parameterized by each node or `plugin-stack` pack):

| Capability Slug (`VALID_DASHBOARD_MODULES`) | Source Layer & Router Factory (`1:1` Module) | Mounted Prefix | Parameterized Behavior & Default Archetype Composition |
| :--- | :--- | :--- | :--- |
| **`crud`** | `zcg.web.capabilities.crud:create_crud_router` | `/api/modules/crud` | Declarative `CollectionSchema` (`ResourceFieldSpec` + `CARDS \| LIST \| TABLE` + SQLite WAL `CollectionRepository` search/filter/pagination); parameterizes Academic Study Drills, Decision Records, or B2B Inquiries per dashboard. |
| **`vault`** | `zcg.web.capabilities.vault:create_vault_router` | `/api/modules/vault` | Content-addressed `LocalFileVault` (`multipart/form-data` `UploadFile`, streaming attachment download, SHA-256 verification, `CARDS \| LIST \| TABLE` listing, and `HTTP 200 -> 286` `DeferredJobQueue` jobs). |
| **`telemetry`** | `zcg.web.capabilities.telemetry_router:create_telemetry_router` | `/api/modules/telemetry` | Live `SamplingCadenceCalculator`, `HeartbeatJitterTracker`, `BulkheadIsolationGuard`, `RuntimeTelemetryScorer`, `RouteSignalCollector`, and SQLite WAL `TelemetryAuditDAG` (`GET ""`, `GET/POST "/audit"`). |
| **`data_pipeline`** | `zcg.platform.pipeline_router:create_data_pipeline_router` | `/api/modules/data-pipeline` | Stateful `DataPipelineRuntime` tracking `SchemaDiscovery`, `ChangeDataCapture` (`INSERT/UPDATE`), `ContinuousValidationScorer`, and `SchemaDriftDetector` across ingested batches. |
| **`role_projection`** | `zcg.platform.projection_router:create_role_projection_router` | `/api/modules/role-projection` | Minimal-disclosure `RolePayloadProjector` across `DisclosureTier × ExchangeStage` (`CANDIDATE_APPLICATION` PII withholding vs. `DAY1_ONBOARDING` vs. `B2B_PROPOSAL`). |
| **`node_mesh`** | `zcg.cockpit.mesh_router:create_node_mesh_router` | `/api/modules/node-mesh` | Sovereign `3-Scope` topology (`1-hop` governor/children/peers, sanitized `linked_nodes`, and federated mounts). |
| **`work_ledger`** | `zcg.cockpit.ledger_router:create_work_ledger_router` | `/api/modules/work-ledger` | Node `own_node_ledger`, `environment_gates`, and `DeferredJobQueue` coupled to `/api/poll/status` (`HTTP 200 -> 286`). |

---

## 8. Plugin Application SDK (`plugin_sdk.py` & `zcg scaffold-plugin-module`)

Departmental engineering squads and sovereign individuals build custom web/API applications as installable `plugin-stack` packs (`templates/plugin-stack/<plugin-id>/`) combining the generic capabilities above with plugin-owned Hexagonal modules:

1. **Contained & Namespace-Isolated `routers/*.py` Loading (`load_plugin_routers`)**:
   - Inspects `plugin_dir / "routers/*.py"` (skipping `_*.py`), enforcing `ensure_contained_path(router_file, plugin_dir)` (`PATH_CONTAINMENT_VIOLATION` on symlink/traversal escapes) and rejecting world-writable files (`UNSAFE_PLUGIN_ROUTER_PERMISSIONS`).
   - Loads each router module inside an isolated synthetic package namespace (`_zcg_plugin_<slug>`) without mutating `sys.path`, invoking `build_router(workspace_dir, state)` / `create_router(workspace_dir, state)` or reading `router: APIRouter` (`INVALID_PLUGIN_ROUTER_CONTRACT` otherwise).
2. **Hexagonal Module Generator (`scaffold_plugin_module` / `zcg scaffold-plugin-module`)**:
   - Scaffolds `modules/<pkg>/models.py` (`frozen=True` `DomainEntity`), `modules/<pkg>/service.py` (pure `L2` Functional Core passing `zcg lint-arch`), `routers/<pkg>.py` (`SWAP_SYNC` / `ISLAND_SYNC` `APIRouter`), `web/templates/partials/<module>.html`, `0`-byte `__init__.py` files, and registers `plugin_routers` in `template.json`.

---

## 9. Sovereign Exposure Posture, Parallel Context Branches & Cross-Node Orientation (`node_context.py`, `surfaces.py`)

Every Reference Dashboard (`/dashboard`) and Sovereign Node Cockpit (`/`) surfaces explicit orientation, privacy boundaries, parallel Git context tracks, and directional cross-node navigation:

1. **Sovereign Exposure Posture (`classify_exposure_posture`)**:
   - Distinguishes `private-personal` (`127.0.0.1` loopback only — `workstation`, `academic-tutor`, `personal-work`, `project`), `private-intranet` (internal RBAC — `corporate`, `department`, `domain-policy`), `public-preview` (`visibility == "public"` in `dev|tst|pre`), and `public-live` (`visibility == "public"` in `pro`).
   - When `public-live` is active on `/`, `render_node_cockpit_html` renders an **External Sovereign Node Passport** (omitting internal sprint task lists and private fleet paths while surfacing public governance rules, epistemic mounts, `zcg link` peer commands, and a direct button to `/dashboard`).
2. **Archetype Context Spotlights & Spin-Off Studio (`build_node_dashboard_enrichment` & `/api/modules/node-context`)**:
   - **Workstation (`:8790`)**: Host OS/kernel/architecture/CPU/Python summary, `global_profile` & `interaction_language`, governed Stow roots (`bash/`, `git/`, `system/`, `antigravity/`), parallel `machine/*` & `hat/*` branches, and fleet quick-launch cards.
   - **Academic Tutor (`:8786`)**: Parallel `specialty/*` curriculum branches (`maths`, `physics`, `biology`, `engineering`, `maths-physics`), mastery stage, local `docs/` study guides, and structured connected `knowledge` rows distinguishing passive `rcap1 · make consult` corpora (linked cleanly to their normalized GitHub repositories, never emitting empty endpoints) from active `*.localhost` peer hubs.
   - **Personal Work (`:8787`) & Department Ops**: Parallel `opportunity/*`, `venture/*`, `engagement/*`, and `feature/*` branches plus an interactive **Project Graduation Studio** (`GET /api/modules/node-context/spinout-preview`) synthesizing `zcg spinout-project` commands to graduate any context branch into a standalone sovereign repository.
3. **Directional Cross-Node Switcher & Canonical `*.localhost` Origin Purity (`build_cross_node_links` & `canonicalize_local_node_url`)**:
   - Groups connected nodes by relationship (`↑ Governor`, `↓ Sub-Node`, `↔ Peer`, `🔗 Link`, `⚡ Fleet`) with explicit target role and exposure badges, canonicalizing all local browser navigation (`network_representation_links`, `fleet_plugin_inventory`, `zcg link`, and Cockpit `/` switchers) onto RFC 6761 `*.localhost` origins (`0` mixed `127.0.0.1` links in frontend HTML).

---

## 10. `Root 0` Domain & DNS Governance, Source-Origin Footer & Selective `Web <-> Repo` Veracity (`provenance.py`, `asgi.py`)

Sovereign networks unify zero-root local subdomain ergonomics, authoritative DNS delegation, repository provenance links, and selective web veracity without forcing proprietary source code exposure:

1. **Centralized `Root 0` `domain_governance` & RFC 6761 `*.localhost` Subdomains (`resolve_domain_governance` & `materialize_dns_zone_manifest`)**:
   - Declared once on `Root 0` (`system/zcg-node.json -> domain_governance`: `canonical_domain`, `intranet_zone`, `local_dev_zone`, `dns_authority`) and inherited downward across governed child layers (`up to MAX_GOVERNANCE_HOPS = 3` within the same `governing_root_id`, strictly excluding `OSS_WORKSTATION_IDS`).
   - Alongside `localhost_url` (`http://127.0.0.1:<port>/?env=<env>`), every node exposes first-class RFC 6761 loopback subdomains (`http://<env>.<node>.<net>.localhost:<port>/dashboard` or `http://<twin>.localhost:<port>/dashboard` in `pro`) resolving natively to `127.0.0.1` on Linux (`nss-myhostname` / `systemd-resolved`) and modern browsers with `0` `/etc/hosts` edits.
   - Materializes `surfaces/infra/dns_zone_manifest.json` (`zcg-dns-zone-v1`): private individual nodes emit `"dns_publication": "disabled-private-loopback"` (`0` records), whereas enterprise/public nodes declare authorized `A` and `_zcg-attest.<fqdn>` `TXT` records bound to `dns_authority` (`governed_by`, `delegated_operator_layer`, `required_role`, `provider`).
2. **Privacy-Safe Copyright & Source-Origin Repository Footer (`resolve_source_origin_metadata` & `render_provenance_footer_html`)**:
   - Normalizes SSH/HTTPS remotes (`git@github.com:owner/repo.git` $\rightarrow$ `https://github.com/owner/repo`, rejecting local filesystem paths) and renders `<div class="zcg-provenance-footer" data-zcg-provenance="footer">` across all `6` `plugin-stack` Reference Dashboards and Cockpit `/`.
   - In `public + pro` (`is_public_pro=True`), `resolve_source_origin_metadata` strictly reads **only** the public node's own public repository URL (suppressing private `upstream_layer.repository` URLs or omitting the link when `hide_source_repo_in_pro` is set).
3. **Selective `Web <-> Repo` Veracity (`VALID_SURFACE_VERACITY_MODES`, `build_public_surface_seal` & `GET /.well-known/zcg-attestation.json`)**:
   - Supports three declarative `surface_veracity_mode` contracts: `"full-open-source"` (default for `open-source` and `gov-*`/`geo-*`/`sci-*`), `"curated-public-surface"` (default for `org-*` and `pub-*` twins — public manifest/docs/curated presentation in Git while backend `routers/*.py` and business logic remain private), and `"attestation-only"` (`0` web source code required in Git).
   - Materializes `surfaces/attestation/public_surface_seal.json` (`zcg-surface-seal-v1`) using C-backed `hashlib.file_digest` (`served_assets_merkle_root` over static/template files excluding `.py` code + `public_routes_digest` + `seal_digest`) and serves live **`GET /.well-known/zcg-attestation.json`** (`DeliveryChannel.STATIC_SYNC`) on `zcg.cockpit.asgi` for bidirectional `Web <-> Repo` legitimacy checks.
