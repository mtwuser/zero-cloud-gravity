---
epistemic_grade: E3
---

# Architecture 06 — Autonomous Web Frontend & Backend API Application Engine (`src/zcg/web/`)

> **Normative Specification — Subsystem 6 (`src/zcg/web/{channels,security,probes,resilience,telemetry,request,router,templates,components,static_files,factory,server}.py` & `src/zcg/web/capabilities/{crud,vault,telemetry_router}.py`)**
>
> This specification defines the zero-dependency Python 3.14 Web Frontend and Backend API constructor (`src/zcg/web/`) powering both Zero-Cloud Node Reference Dashboards and standalone or `plugin-stack` web/API applications. It enforces **`0` runtime imports** from `zcg.{governance,topology,mcp,capsules,cockpit,cli,ephemeral}` (verified by `zcg lint-arch` via `excluded_contexts`), providing the `16`-channel `DeliveryChannel` (`Zone Z1..Z4 × Tier T1..T5`), Zone-graded `CSP`/`CSRF`/signed-cookie security, typed `Request` (`urlencoded` Form + stdlib `multipart/form-data` `UploadFile`), composable `APIRouter` with OpenAPI 3.1 synthesis, cascading multi-directory `TemplateCatalog`, `14` WCAG 2.2 AA UI & Collection Macros (`components.py`: `render_card_grid`, `render_item_list`, `render_table`), layered `FallbackStaticCatalog` + zero-build ES2024 client runtimes (`zcg-swap.js`, `island-bus.js`, `hydrator.js`), adaptive probes, bulkhead/reaper resilience, `G1..G3` `RuntimeTelemetryScorer` + `RouteSignalCollector` + SQLite WAL `TelemetryAuditDAG`, generic composable capability routers (`capabilities/{crud,vault,telemetry_router}.py`), and the `create_web_app` Native ASGI 3.0 factory.

---

## 1. `1:1:1` Source $\leftrightarrow$ Unit Test $\leftrightarrow$ Responsibility Matrix (`src/zcg/web/`)

All fifteen modules across `src/zcg/web/` (`12`) and `src/zcg/web/capabilities/` (`3`) rely exclusively on Python 3.14 stdlib and `src/zcg/core/` primitives (`<= 384` lines/module, `0` hardcoded vertical domain nouns, `100.00%` isolated statement and branch coverage across 4-quadrant `AAA` suites):

| Implementation Module | Isolated `1:1` Unit Suite | Primary Symbols & Normative Scope |
| :--- | :--- | :--- |
| [src/zcg/web/channels.py](../../src/zcg/web/channels.py) | [tests/unit/zcg/web/test_channels.py](../../tests/unit/zcg/web/test_channels.py) | `BaseStrEnum`, `Zone` (`Z1..Z4`), `Tier` (`T1..T5`), `CommPattern`, `DeliveryChannel` (`16` valid `Zone × Tier` channels + `from_zone_tier`), partial-swap (`HX-Request`) header contracts, `poll_status_code` (`HTTP 286` poll-stop), `SSEMessage` / `VersionedPayload` EventStream framing, and `heartbeat_sse_stream`. |
| [src/zcg/web/security.py](../../src/zcg/web/security.py) | [tests/unit/zcg/web/test_security.py](../../tests/unit/zcg/web/test_security.py) | `DocsAccessMode` (`PUBLIC \| AUTHENTICATED \| DISABLED`), `ErrorSeverity`, `ErrorAction`, Zone-graded `CSP` `build_zone_security_headers`, constant-time `verify_csrf_request` (`x-zcg-csrf-token` on mutating `Z1/Z2`), HMAC-SHA256 `sign_cookie_value` / `verify_cookie_value`, `evaluate_docs_access`, and `WebAppError` JSON/HTML formatters. |
| [src/zcg/web/probes.py](../../src/zcg/web/probes.py) | [tests/unit/zcg/web/test_probes.py](../../tests/unit/zcg/web/test_probes.py) | `SamplingCadenceCalculator` (`W >= 2 * T_cycle` sampling interval + bounded anti-thundering-herd jitter), `SlidingProgressMonitor` (`PROGRESSING \| INSUFFICIENT_SAMPLES \| STAGNANT_LOOP`), and `HeartbeatJitterTracker` (`STABLE \| ELEVATED \| SATURATED` mean + standard deviation `jitter_ms`). |
| [src/zcg/web/resilience.py](../../src/zcg/web/resilience.py) | [tests/unit/zcg/web/test_resilience.py](../../tests/unit/zcg/web/test_resilience.py) | `chunk_items` (`PEP 695` `itertools.islice` batch chunker), `DeadlineBudgetGuard` (unacknowledged in-flight window + monotonic deadline budget), `DeferredJobQueue` (`T2..T5` background jobs), `StaleResourceReaper` (`ResourceTTLPolicy` age/stagnation/retry eviction), and `BulkheadIsolationGuard` (`OPEN \| SHIELDED` `T1 -> T2` saturation shedding). |
| [src/zcg/web/telemetry.py](../../src/zcg/web/telemetry.py) | [tests/unit/zcg/web/test_telemetry.py](../../tests/unit/zcg/web/test_telemetry.py) | `TelemetryGrade` (`G1 \| G2 \| G3`), `HealthRegime` (`OPTIMAL \| DEGRADED \| PROTECTIVE \| CRITICAL`), `RuntimeTelemetryScorer` (`4`-weight composite health score + `TransitionAction`), `RequestSignal` / `RouteSignalCollector` (per-route bounded ring telemetry), and SQLite WAL `TelemetryAuditDAG` (`verify_integrity`). |
| [src/zcg/web/request.py](../../src/zcg/web/request.py) | [tests/unit/zcg/web/test_request.py](../../tests/unit/zcg/web/test_request.py) | Runtime-resolvable ASGI boundary types (`Scope`, `Message`, `Receive`, `Send`, `ASGIApp`), `UploadFile`, `MultipartFormData`, typed `Request` (`query`, `json`, `form` via `parse_qs`, `multipart` via stdlib `BytesFeedParser`), `read_bounded_body` (`413` guard), `WebResponse`, `respond`, `respond_poll`, and `respond_empty`. |
| [src/zcg/web/router.py](../../src/zcg/web/router.py) | [tests/unit/zcg/web/test_router.py](../../tests/unit/zcg/web/test_router.py) | `RouteDefinition`, `RouteMatch`, and composable `APIRouter` (`prefix`, `tags`, `.get/.post/.put/.patch/.delete`, `.include_router`, `{param}` regex extraction, `405` allowed-methods discovery, and `build_openapi_paths` OpenAPI 3.1 generator). |
| [src/zcg/web/templates.py](../../src/zcg/web/templates.py) | [tests/unit/zcg/web/test_templates.py](../../tests/unit/zcg/web/test_templates.py) | `SafeHTML`, `escape_html`, `BUILTIN_TEMPLATES` (`base.html` & `plugin_shell.html` with default `/static/img/logo.svg` `<link rel="icon">` favicon and `.zcg-brand-logo` header emblem), bounded multi-level `{% extends %}` / `{% block %}` inheritance (`MAX_TEMPLATE_INHERITANCE_DEPTH = 4`), auto-injected `ICON_TEMPLATE_GLOBALS` (`{{ icon_* }}`), and cascading `TemplateCatalog` (`respond_template`). |
| [src/zcg/web/components.py](../../src/zcg/web/components.py) | [tests/unit/zcg/web/test_components.py](../../tests/unit/zcg/web/test_components.py) | `VALID_HYDRATION_STRATEGIES` (`eager \| visible \| idle`), `ZCG_ICONS` + `render_icon` + `ICON_TEMPLATE_GLOBALS` (`16` zero-dependency `16×16` inline stroke SVGs), and `14` WCAG 2.2 AA UI & Collection Macros (`render_card`, `render_card_grid`, `render_item_list`, `render_table`, `render_pagination`, `render_search_bar`, `render_form_field`, `render_modal`, `render_tabs`, `render_alert`, `render_file_dropzone`, `render_progress_bar`, `render_kpi_stat`, `render_island`). |
| [src/zcg/web/static_files.py](../../src/zcg/web/static_files.py) | [tests/unit/zcg/web/test_static_files.py](../../tests/unit/zcg/web/test_static_files.py) | `ZCG_BRAND_LOGO_SVG`, `BUILTIN_STATIC_ASSETS` (`img/logo.svg`, `css/design-system.css`, `css/layout.css`, `css/components.css`, `js/zcg-swap.js`, `js/island-bus.js`, `js/hydrator.js`), and cascading `FallbackStaticCatalog` (`ensure_contained_path` + SHA-256 `ETag` / `304 Not Modified`). |
| [src/zcg/web/capabilities/crud.py](../../src/zcg/web/capabilities/crud.py) | [tests/unit/zcg/web/capabilities/test_crud.py](../../tests/unit/zcg/web/capabilities/test_crud.py) | Declarative Frontend ↔ Backend CRUD & Collection Persistence Engine: `FieldKind`, `CollectionLayout` (`CARDS \| LIST \| TABLE`), `ResourceFieldSpec`, `CollectionSchema`, `CollectionRecord(DomainEntity)`, SQLite WAL `CollectionRepository` (`itertools.islice` search/filter/pagination), and `create_crud_router` (`GET/POST ""`, `GET/PUT/DELETE "/{item_id}"`). |
| [src/zcg/web/capabilities/vault.py](../../src/zcg/web/capabilities/vault.py) | [tests/unit/zcg/web/capabilities/test_vault.py](../../tests/unit/zcg/web/capabilities/test_vault.py) | Content-Addressed Binary Blob & Multipart Transport Engine: `StoredFileRecord(DomainEntity)`, `FileVaultRepository`, path-contained `LocalFileVault` (SHA-256 digests), and `create_vault_router` (`CARDS \| LIST \| TABLE` view, `multipart/form-data` & JSON upload, streaming download, delete, and `DeferredJobQueue` `HTTP 200 -> 286` jobs). |
| [src/zcg/web/capabilities/telemetry_router.py](../../src/zcg/web/capabilities/telemetry_router.py) | [tests/unit/zcg/web/capabilities/test_telemetry_router.py](../../tests/unit/zcg/web/capabilities/test_telemetry_router.py) | Composable Runtime Observability & Audit DAG Router: `create_telemetry_router` exposing `GET ""` (`SamplingCadenceCalculator`, `HeartbeatJitterTracker`, `BulkheadIsolationGuard`, `RuntimeTelemetryScorer`, `RouteSignalCollector`), `GET "/audit"`, and `POST "/audit"` (`TelemetryAuditDAG` integrity & decision sealing). |
| [src/zcg/web/factory.py](../../src/zcg/web/factory.py) | [tests/unit/zcg/web/test_factory.py](../../tests/unit/zcg/web/test_factory.py) | Per-instance `WebAppState` (`PEP 703` zero-mutable-globals) and `create_web_app` Native ASGI 3.0 application factory wiring `lifespan`, `/static/*`, `/healthz` (`healthz_extra_provider`), `/events` (`sse_event_name`), `/api/poll/status` (`HTTP 286`), `/openapi.json`, `/docs`, `APIRouter` dispatch, `fallback_handler`, `CSP`/`CSRF`/`413` guards, and dual JSON/HTML error handling. |
| [src/zcg/web/server.py](../../src/zcg/web/server.py) | [tests/unit/zcg/web/test_server.py](../../tests/unit/zcg/web/test_server.py) | Zero-dependency `asyncio` HTTP/1.1 -> ASGI 3.0 loopback bridge (`handle_http_stream`, `serve_asgi_loopback`, `run_asgi_self_test`, `run_server_cli`, and CLI `main`) with `HTTP 286 Stop Polling` wire framing and streaming `SSE` support. |

---

## 2. Architectural Independence & `16`-Channel `DeliveryChannel` Matrix (`channels.py`, `security.py`)

`src/zcg/web/` and `src/zcg/platform/` declare explicit `excluded_contexts` in [`system/zcg-node.json`](../../system/zcg-node.json) blocking any runtime import from `governance`, `topology`, `mcp`, `capsules`, `cockpit`, `cli`, or `ephemeral`. Every HTTP/ASGI route binds one of the `16` valid `Zone (Z1..Z4) × Tier (T1..T5)` `DeliveryChannel` values:

| Zone (`Presentation`) | Allowed Tiers (`T1..T5`) | Derived `CommPattern` | Zone-Graded `Content-Security-Policy` (`script-src` / `connect-src`) |
| :--- | :--- | :--- | :--- |
| **`Z1` (`static`)** | `T1` (`STATIC_SYNC` only; `Z1 × T2..T5` rejected) | `request_response` | `script-src 'none'; frame-ancestors 'none'` (`0 KB` client JS enforced by browser) |
| **`Z2` (`swap`)** | `T1..T5` (`SWAP_SYNC..SWAP_PIPELINE`) | `T1`: `request_response`; `T2,T4`: `polling`; `T3,T5`: `sse` | `script-src 'self'; connect-src 'self'; frame-ancestors 'none'` |
| **`Z3` (`island`)** | `T1..T5` (`ISLAND_SYNC..ISLAND_PIPELINE`) | `T1`: `request_response`; `T2,T4`: `polling`; `T3,T5`: `sse` | `script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'` |
| **`Z4` (`immersive`)** | `T1..T5` (`IMMERSIVE_SYNC..IMMERSIVE_PIPELINE`) | `T1`: `request_response`; `T2,T4`: `polling`; `T3`: `websocket`; `T5`: `sse` | `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; connect-src 'self' ws: wss:` |

1. **Constant-Time `CSRF` & HMAC-Signed Cookies (`security.py`)**: Mutating `POST|PUT|PATCH|DELETE` requests on `Z1`/`Z2` require constant-time `hmac.compare_digest` verification of `x-zcg-csrf-token`. Stateless session payloads are sealed via `sign_cookie_value` / `verify_cookie_value` (`base64url(canonical_json) + "." + hmac_sha256_hex`).
2. **Dual Error Adaptation (`WebAppError`)**: Raising `WebAppError` returns an escaped `<div class="zcg-alert ... zcg-error ...">` HTML swap fragment when `request.is_partial_swap` is `True` and a structured JSON envelope (`error`, `message`, `severity`, `action`, `user_hint`) otherwise.

---

## 3. Typed `Request`, Composable `APIRouter` & OpenAPI 3.1 Synthesis (`request.py`, `router.py`, `factory.py`)

The backend API layer provides ergonomic routing, form/multipart parsing, and automatic schema generation using 100% Python 3.14 stdlib:

1. **Typed `Request` & Streaming Body Parsers (`request.py`)**:
   - `read_bounded_body` streams ASGI `http.request` chunks while aborting immediately with `413 PAYLOAD_TOO_LARGE` when `content-length` or cumulative bytes exceed `max_payload_bytes`.
   - `Request.json()` decodes JSON payloads (`400 INVALID_JSON` on syntax errors); `Request.form()` / `Request.form_multi()` parse `application/x-www-form-urlencoded` bodies via `urllib.parse.parse_qs`; and `Request.multipart()` parses `multipart/form-data` streams via stdlib `email.parser.BytesFeedParser(policy=email.policy.HTTP)`, sanitizing `UploadFile.filename` basenames to prevent directory traversal.
2. **Composable `APIRouter` & OpenAPI 3.1 (`router.py`)**:
   - `APIRouter` compiles `{param}` templates into named-group regular expressions, supports nested composition via `include_router`, distinguishes `404` vs. `405 Method Not Allowed` (`Allow` header), and synthesizes OpenAPI `3.1.0` `paths` with path parameter schemas and `x-delivery-channel` extensions.
3. **Adaptive Responses (`respond`, `respond_poll`, `respond_empty`) & Styled OpenAPI Explorer (`/docs`)**:
   - `respond` returns `SWAP_SYNC` HTML fragments on partial swap requests, `ISLAND_SYNC` full pages when `full_html` is provided on standard navigation, and `ISLAND_SYNC` JSON payloads for API callers. `respond_poll` emits `HTTP 200` while active and **`HTTP 286`** (`Stop Polling`) when `done=True`.
   - When `DocsAccessMode` permits access, `GET /docs` renders a styled zero-build HTML5 OpenAPI 3.1 Route & `DeliveryChannel` Explorer (`/static/css/*.css`, method pills, `x-delivery-channel` badges, summaries, `/openapi.json`, and `/dashboard` navigation). When `DocsAccessMode.DISABLED` is active (default in `pro`), `GET /docs` returns `HTTP 404` (`DOCS_DISABLED`, `ErrorSeverity.INFO`) with an explicit `user_hint` explaining production API surface hardening.

---

## 4. Cascading `TemplateCatalog`, UI Macros & Zero-Build Static Assets (`templates.py`, `components.py`, `static_files.py`)

The frontend presentation layer enables zero-build progressive enhancement and clean Two-World customization (`node local overrides -> active plugin web/ -> built-in zcg.web defaults`):

1. **Cascading `TemplateCatalog`, Dual Shell (`plugin_shell.html` vs. `base.html`) & Auto-Escaping (`templates.py`)**:
   - Resolves templates across `search_dirs` (enforcing `ensure_contained_path`) before falling back to `BUILTIN_TEMPLATES` (`base.html` for standalone/brand websites and `plugin_shell.html` for unified operational `plugin-stack` dashboards).
   - Supports bounded multi-level `{% extends "..." %}` + flat sibling `{% block <name> %}...{% endblock %}` layout inheritance (`MAX_TEMPLATE_INHERITANCE_DEPTH = 4`) and `{{ variable }}` interpolation that auto-injects `ICON_TEMPLATE_GLOBALS` (`{{ icon_shield }}`, `{{ icon_vault }}`, etc.), escapes untrusted strings via `html.escape(..., quote=True)`, and preserves `SafeHTML` instances.
   - Ships `16` zero-dependency inline `16×16` stroke SVG icons (`ZCG_ICONS` / `render_icon`) alongside `14` typed UI & Collection macros (`render_card`, `render_card_grid`, `render_item_list`, `render_table`, `render_pagination`, `render_search_bar`, `render_form_field`, `render_modal`, `render_tabs`, `render_alert`, `render_file_dropzone`, `render_progress_bar`, `render_kpi_stat`, `render_island`) and visual action tiers (`.zcg-btn`, `.zcg-btn--secondary`, `.zcg-chip`, `.zcg-nav-shell`).
2. **Layered `FallbackStaticCatalog`, Default Vector Brand Emblem & Zero-Build ES2024 Client Runtimes (`static_files.py`)**:
   - Serves `/static/*` with `ensure_contained_path` traversal protection and SHA-256 `ETag` (`304 Not Modified`) caching, allowing any sovereign node (`surfaces/web/static/img/logo.svg`) or plugin (`plugin.css`) to override the built-in `ZCG_BRAND_LOGO_SVG` (`img/logo.svg`) and `--zcg-*` design tokens without modifying engine source files.
   - Ships `css/{design-system,layout,components}.css`, `js/zcg-swap.js` (partial swaps, `FormData` / `URLSearchParams` form submission with automatic `x-zcg-csrf-token` header injection, `<dialog>` modals, tabs, `HTTP 286` poll termination, and `SSE` bridge), `js/island-bus.js` (`window.IslandBus` pub/sub + state replay), and `js/hydrator.js` (`[data-island]` `eager | visible | idle` progressive hydration).

---

## 5. Adaptive Probes, Resilience Pipeline & Multi-Grade Telemetry (`probes.py`, `resilience.py`, `telemetry.py`)

Every `create_web_app` instance maintains isolated per-application control-theory telemetry (`WebAppState`, `0` mutable module globals):

| Module | Core Primitives | Exact Cut-Points (`N` vs. `N ± 1`) & Operational Invariants |
| :--- | :--- | :--- |
| **`probes.py`** | `SamplingCadenceCalculator`, `SlidingProgressMonitor`, `HeartbeatJitterTracker` | Enforces `W >= 2.0 * T_cycle` (`T_sample = 0.5 * T_cycle`, jitter `<= 0.5`), classifies progress (`PROGRESSING \| INSUFFICIENT_SAMPLES \| STAGNANT_LOOP`), and grades tick dispersion (`STABLE < 50 ms`, `ELEVATED >= 50 ms`, `SATURATED >= 200 ms`). |
| **`resilience.py`** | `chunk_items`, `DeadlineBudgetGuard`, `DeferredJobQueue`, `StaleResourceReaper`, `BulkheadIsolationGuard` | Chunks iterables via `itertools.islice`, bounds in-flight windows and monotonic deadlines, runs `T2..T5` background jobs, evicts stale/over-retried tasks (`EXPIRED`), and sheds `T1 -> T2` (`SHIELDED`) when `utilization_ratio >= saturation_threshold` and `active_heavy_tasks > 0`. |
| **`telemetry.py`** | `RuntimeTelemetryScorer`, `RouteSignalCollector`, `TelemetryAuditDAG` | Scores composite health (`0.30 * volume + 0.25 * latency + 0.30 * success + 0.15 * trend` across `OPTIMAL >= 80`, `DEGRADED >= 55`, `PROTECTIVE >= 30`, `CRITICAL < 30`), tracks bounded per-route latency/error signals, and chains SHA-256 `AuditDecisionNode` records in SQLite WAL. |

---

## 6. Generic Composable Capability Routers (`capabilities/crud.py`, `capabilities/vault.py`, `capabilities/telemetry_router.py`)

Rather than embedding concrete domain verticals inside the framework engine, `src/zcg/web/` extracts pure, domain-neutral Frontend ↔ Backend capabilities (`0` governance/cockpit dependencies, `0` hardcoded vertical schemas) that any standalone application or `plugin-stack` Reference Dashboard parameterizes with its own schemas and templates:

| Capability Module | Factory & Default Prefix | Endpoints & Adaptive Dual-Format Contract (`SWAP_SYNC` HTML + `ISLAND_SYNC` JSON) |
| :--- | :--- | :--- |
| **`crud.py`** | `create_crud_router(workspace_dir, *, schema=CollectionSchema(...))` | Parameterized by `ResourceFieldSpec` (`TEXT`, `LONG_TEXT`, `SLUG`, `CHOICE`, `BOOL`, `INT`) and `CollectionLayout` (`CARDS \| LIST \| TABLE`): `GET ""` (`?q=`, `?filter_<field>=`, `?page=&page_size=&view=cards\|list\|table` via `render_card_grid` / `render_item_list` / `render_table`), `POST ""` (`201` via JSON or `urlencoded` form, `400/422` validation), `GET "/{item_id}"`, `PUT "/{item_id}"`, and `DELETE "/{item_id}"`. |
| **`vault.py`** | `create_vault_router(workspace_dir, *, job_queue=..., prefix="/api/vault")` | `GET ""` (`?view=cards\|list\|table` with `render_file_dropzone`), `POST ""` (`201` via `multipart/form-data` `UploadFile` or JSON stored under `.agents/telemetry/vault_blobs/` with SHA-256 digest), `GET "/{file_id}/download"` (`STATIC_SYNC` attachment + `x-content-sha256`), `DELETE "/{file_id}"`, and `POST "/jobs"` + `GET "/jobs/{task_id}"` (`HTTP 200 -> 286` `respond_poll` with generated UUID `Identifier`s). |
| **`telemetry_router.py`** | `create_telemetry_router(workspace_dir, *, prefix="/api/telemetry")` | `GET ""` (live `SamplingCadenceCalculator`, `HeartbeatJitterTracker`, `BulkheadIsolationGuard`, `RuntimeTelemetryScorer`, `RouteSignalCollector`, and `TelemetryAuditDAG` integrity), `GET "/audit"` (hash-chained decision history), and `POST "/audit"` (`201` validating non-blank `rationale` and sealing `AuditDecisionNode` in SQLite WAL). |
