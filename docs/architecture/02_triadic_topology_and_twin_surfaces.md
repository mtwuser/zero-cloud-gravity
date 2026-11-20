---
epistemic_grade: E3
---

# Architecture 02 — Triadic Topology, Subtrees & Private-Public Twin Surfaces (`src/zcg/topology/`)

> **Normative Specification — Subsystem 2 (`src/zcg/topology/{identity,network,posture,subtrees,exposure}.py`)**
>
> This specification defines filesystem path containment (`PATH_CONTAINMENT_VIOLATION`), the triadic **`Node × Layer × Network`** topological model, setup `--purpose` archetypes, `sovereign` vs. `managed` governance posture (including the `R3`-isolated `wallet` personal pillar), sovereign exposure posture & selective `Web <-> Repo` veracity classification (`exposure.py`), `SurfaceOriginResolver`, `1-hop` upward/downward/lateral connection discovery, `Private <-> Public` twin attestation (`root_0_public_approved`), 3-stage `knowledge` stewardship with strict sibling isolation, and `layers/*` subtree synchronization in `src/zcg/topology/`.

---

## 1. `1:1:1` Source $\leftrightarrow$ Unit Test $\leftrightarrow$ Responsibility Matrix (`src/zcg/topology/`)

All five modules in `src/zcg/topology/` depend exclusively on `src/zcg/core/` and enforce strict workspace path containment:

| Implementation Module | Isolated `1:1` Unit Suite | Primary Symbols & Normative Scope |
| :--- | :--- | :--- |
| [src/zcg/topology/identity.py](../../src/zcg/topology/identity.py) | [tests/unit/zcg/topology/test_identity.py](../../tests/unit/zcg/topology/test_identity.py) | `ensure_contained_path` (`PATH_CONTAINMENT_VIOLATION`), `resolve_layer_entity_identity` (`operating_state`, `mcp_operating_mode`, `visibility_scope`, `private_public_twin`, `can_expose_to_oss`), `classify_inter_layer_relationship` (`5` MCP communication modes), and `resolve_knowledge_mount_endpoints` (`3`-tier resolution cascade). |
| [src/zcg/topology/network.py](../../src/zcg/topology/network.py) | [tests/unit/zcg/topology/test_network.py](../../tests/unit/zcg/topology/test_network.py) | `discover_network_topology` (`own_network_*`, `root_composite_*`, `upward_governor`, `downward_governed_nodes`, `lateral_peers`, `knowledge_nodes`, `linked_nodes`, and strict `public-community` sibling isolation). |
| [src/zcg/topology/posture.py](../../src/zcg/topology/posture.py) | [tests/unit/zcg/topology/test_posture.py](../../tests/unit/zcg/topology/test_posture.py) | `resolve_purpose_archetype` (`7` setup `--purpose` archetypes), `resolve_governance_posture` (`sovereign` vs. `managed`, 6-pillar personal constellation & `wallet` `R3` airlock), `resolve_surface_origin` (`loopback \| intranet-gateway \| cloud-ephemeral`), `open_parent_source`, and repository-name-agnostic `inspect_remote_node_manifest`. |
| [src/zcg/topology/subtrees.py](../../src/zcg/topology/subtrees.py) | [tests/unit/zcg/topology/test_subtrees.py](../../tests/unit/zcg/topology/test_subtrees.py) | `inspect_mounted_children_drifts`, `sync_mounted_children_into_parent` (`layers/<name>/` rollup & `[x]` task completion reconciliation). |
| [src/zcg/topology/exposure.py](../../src/zcg/topology/exposure.py) | [tests/unit/zcg/topology/test_exposure.py](../../tests/unit/zcg/topology/test_exposure.py) | `POSTURE_DEFAULT_RINGS`, `classify_exposure_posture` (`public-live \| public-preview \| private-personal \| private-intranet`), `is_public_portal_enabled` (single-source `/portal` menu gate across `/`, `/admin`, and `/settings`), `resolve_active_env_stages` (returning `()` on purely `local-sovereign` nodes vs. real promotion stages on deployed/staged nodes), `resolve_surface_veracity_mode` (`full-open-source \| curated-public-surface \| attestation-only`), `resolve_posture_default_ring` (`R0 \| R2 \| R3`), symmetric `Individual <-> Individual` `resolve_co_sovereign_union_contract` (`0` `Lex Superior` over `<persona>-profile`, `WALLET_CO_SOVEREIGN_UNION_FORBIDDEN`), and zero-leakage `R3` `compile_local_trust_circle_grants` (`TRUST_CIRCLE_R3_EXPORT_FORBIDDEN`, mapping outward strictly to anonymous `R2..R0` grants). |

---

## 2. Triadic `Node × Layer × Network` Disambiguation & Path Containment

ZeroCloudGravity separates physical repository identity from normative authority and composite organizational scope:

```mermaid
flowchart LR
    Node["1. Node (node_id)\nPhysical Git Repository, Work Ledger & Cockpit\n(is_layer_origin_node: true | false)"] --> Layer["2. Layer (layer_id × precedence 0..100)\nNormative Authority Tier & Surface Bindings\n(TOPOLOGICAL_ROLE_CLASSES)"]
    Layer --> Net["3. Composite Network (network_scope)\n1-Hop Upward Governor, Downward Children,\nLateral Peers & Mounted Knowledge Nodes"]
```

1. **Cryptographic Path Containment (`ensure_contained_path`)**: Every file lookup across `topology`, `governance`, `cockpit`, `capsules`, and `mcp` resolves `candidate.resolve()` and verifies `resolved.is_relative_to(workspace_root.resolve())`. Any traversal (`../`), symlink escape, or out-of-tree target raises `ValueError("PATH_CONTAINMENT_VIOLATION: ...")`.
2. **Bounded `operating_state × mcp_operating_mode` Matrix (`resolve_layer_entity_identity`)**:
   - **`oss-readonly-appliance` (`workstation-baseline-provider`)**: Clean Open-Source runtime clone (`~/zero-cloud-gravity`).
   - **`oss-dev` (`self-test-and-dev-only`)**: Engine contributor clone (`~/Projects/dev-zero-cloud-gravity`).
   - **`individual-root` (`personal-root-hub`)**: Personal Sovereign `Root 0` profile hub (`~/<persona>-profile`, `entity_kind: "individual"`, `precedence: 90`, `.personal.local`).
   - **`corporate-root` (`enterprise-governance-hub`)**: Enterprise (`10`) or Public-Government (`1..2`) `Root 0` hub (`.intranet.local`).
   - **`domain-policy` / `department` (`departmental-policy-hub`)**: Fiduciary (`5..9`), functional (`15..45`), or personal sovereign tutor/work (`86..89`) department node.
   - **`squad` (`squad-execution-hub`)**: Operational unit or delivery squad (`40..60`).
   - **`knowledge` (`knowledge-corpus-provider`)**: Curated epistemic corpus or sovereign public twin (`VALID_KNOWLEDGE_PREFIXES = ("gov-", "sci-", "geo-", "org-")` with `PUBLIC_GOV_PREFIXES = ("gov-", "geo-")` at `precedence: 20` or explicit node precedence, `.knowledge.local`; `pub-*` is reserved strictly for optional static `R0` mirrors outside epistemic `knowledge` corpora).
   - **`project` (`project-consumer-only`)**: Consumer application or case workspace (`80`).

---

## 3. Universal `Private Root 0 <-> Public Sovereign Twin` Attestation & Subordinate Outward Gate

Every sovereign entity across `VALID_ENTITY_KINDS` (`public-government`, `enterprise`, `individual`, `open-source`) separates its **internal private `Root 0` hierarchy** (host configurations, private keys, internal contracts, work ledgers) from its **curated Public Sovereign Twin (`gov-<id>`, `geo-<id>`, `sci-<id>`, `org-<id>`, `pub-<persona>`)** under an identical, non-preferential cryptographic contract:

| Boundary Condition | `resolve_node_entity_identity` Contract | Security, Privacy & Anti-Spoofing Guarantee |
| :--- | :--- | :--- |
| **Corporate / Institutional `Root 0` (`corporate` / `1..2`)** | `can_expose_to_oss: True`, `exposure_boundary: "root-0-gateway"` | Governs internal departments (`private`) and attests (`governing_root_id`) its paired public twin (`org-*`, `gov-*`, `geo-*`, `sci-*`). |
| **Individual `Root 0` (`~/<persona>-profile`, `workstation`, `90`)** | `operating_state: "individual-root"`, `visibility: "private"`, `can_expose_to_oss: True` | Keeps host packages, shell/git config, private keys, `<persona>-tutor`, and `<persona>-work` 100% private while governing optional personal public static `R0` mirror **`pub-<persona>`** (`entity_kind: "individual"`). |
| **Subordinate Internal Layer (`department`, `domain-policy`, `squad`) without `Root 0` Attestation** | `visibility_scope: "private:<entity_kind>:<scope>"`, `can_expose_to_oss: False` | Even if `visibility: "public"` is set in a subordinate department's manifest, outward public/OSS exposure remains blocked unless `root_0_public_approved: True` is explicitly attested. |
| **Public Sovereign Twin (`layer_role: "knowledge"`, `visibility: "public"`)** | `visibility_scope: "public:knowledge:<domain>"`, `bridge_mode: "private-to-public-twin"` (when `governing_root_id != layer_id`) | Exposes only curated public surfaces (`pro` = `public-remote-live`), `rcap1` (`L0..L3`), and `citation_receipt`. Protocol parity is strictly symmetric across `gov-*`, `sci-*`, `org-*`, and `pub-*`: relational affinity or priority between an individual (`pub-*` / `<persona>-work`) and an institution/enterprise (`gov-*` / `org-*`) requires bilateral attestation (`linked_nodes` / `roster`), preventing unilateral weight spoofing. |

---

## 4. Three-Stage `knowledge` Stewardship, 3-Tier Endpoint Cascade & Sibling Isolation

Public and organizational `knowledge` corpora (`VALID_KNOWLEDGE_PREFIXES = ("gov-", "sci-", "geo-", "org-")` with `PUBLIC_GOV_PREFIXES = ("gov-", "geo-")`, plus optional static `R0` `pub-*` mirrors) progress through three deterministic stewardship stages (`VALID_KNOWLEDGE_STEWARDSHIP_STAGES`):

| Stewardship Stage | Endpoint Resolution Cascade (`resolve_knowledge_mount_endpoints`) | Sibling Isolation & Network Discovery Contract (`discover_network_topology`) |
| :--- | :--- | :--- |
| **`1. private-incubation`** | `local-mcp-clone` (`layers/<id>/` or sibling clone) $\rightarrow$ `private-mirror-remote` | Internal organizational corpus (e.g., `org-acme` under `governing_root_id: "acme"`); discovered as part of the governing `Root 0`'s composite network (`root_composite_nodes_count`). |
| **`2. public-community`** | `local-mcp-clone` $\rightarrow$ `private-mirror-remote` $\rightarrow$ `public-canonical-remote` (`https://github.com/mtwuser/<id>.git`) | Community-stewarded open corpus (`DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY`: `gov-es`, `geo-es`, `sci-maths`, `sci-physics`, `sci-biology`, `sci-engineering`, `sci-economic`). **Strictly isolated from sibling `public-community` clones in `~/Projects/`**: `discover_network_topology` never auto-links sibling `public-community` repositories (`own_network_nodes_count: 1`, `lateral_peers: []`) unless explicitly declared in `mounted_layers`. |
| **`3. sovereign-authority`** | `local-mcp-clone` $\rightarrow$ `canonical_authority_url` (official ministry / standards body) | Official statutory or scientific consortium repository (`canonical_authority_verified: True`). |

---

## 5. Five Inter-Layer Communication Modes & `layers/*` Subtree Rollup

`classify_inter_layer_relationship(source_dir, target_dir)` classifies every node-to-node interaction into one of 5 deterministic modes:
1. **`internal-1hop-hierarchical`**: Vertical 1-hop delegation (`make delegate`) and promotion (`make promote`) within the same `governing_root_id`.
2. **`knowledge-rcap1-and-citation`**: Read-only `rcap1` capsule consultation and `citation_receipt` verification against a mounted `knowledge` node (`layers/<id>/`).
3. **`external-root0-to-oss-sanitized`**: Anonymized template/rule promotion from a `Root 0` (`can_expose_to_oss: True`) to Open Source (`zero-cloud-gravity`).
4. **`external-peer-root0-pr-and-readonly-mcp`**: Horizontal collaboration between two sovereign `Root 0` entities via `.agents/proposals/from-peer-root-<id>/`.
5. **`blocked-must-route-via-governing-root0`**: Blocks direct external promotion from subordinate internal tiers (`CROSS_TIER_PROMOTION_BYPASS`).

---

## 6. Setup `--purpose` Archetypes, `Sovereign` vs. `Managed` Posture & `SurfaceOriginResolver`

`src/zcg/topology/posture.py` resolves purpose-driven setup defaults, workspace autonomy boundaries, canonical browser origins, and repository-name-agnostic remote `zcg-node-v1` manifests:

| Contract Function | Input Axes & Guards | Normative Output & Security Invariants |
| :--- | :--- | :--- |
| **`resolve_purpose_archetype`** | `purpose` $\in$ `{individual-sovereign, academic-tutor, enterprise-network, public-institution, knowledge-commons, standalone-project, b2b-consortium}` $\times$ optional `layer_role` | Resolves `(default_role, default_entity_kind, default_governance_posture, default_precedence, default_templates)` without name heuristics (`individual-sovereign` $\rightarrow$ `workstation` / `individual` / `precedence=90`; `academic-tutor` $\rightarrow$ `department` / `individual` / `precedence=86`); flips subordinate corporate/public tiers (`department`, `domain-policy`, `squad`, `project`) to `managed`. |
| **`resolve_governance_posture`** | `(workspace_dir, manifest, parent_dir)` | Classifies `governance_posture` (`sovereign` vs. `managed`), `workspace_isolation_ok` (flags corporate `managed` clones placed inside an `individual` `Root 0` tree), and the 6-pillar personal constellation (`PERSONAL_CONSTELLATION_PILLARS = ("profile", "tutor", "work", "wallet", "security", "game")` where `wallet` enforces `default_surface_ring: "R3"`, `allow_external_peer_links: False`, `allow_cross_workspace_1hop_read: False`, and `settlement_airlock_via: "work"`). |
| **`resolve_surface_origin`** | `(manifest, active_env, port, forwarded_proto, forwarded_host, env_vars)` | Resolves `loopback` (`http://<env>.<slug>.localhost:<port>` for local / Antigravity `Remote Control`), `intranet-gateway` (`https://<env>.<canonical_domain>`), or `cloud-ephemeral` (`ZCG_SURFACE_PUBLIC_ORIGIN` / validated `forwarded_host` for Antigravity `Remote Agents` & Cloud Run), rejecting header-injection hosts (`INVALID_SURFACE_ORIGIN_HOST`). |
| **`open_parent_source` & `inspect_remote_node_manifest`** | `(source_ref, branch, timeout_seconds)` | Opens or inspects `system/zcg-node.json` from a local directory or shallow `git clone --depth 1` in an auto-cleaned ephemeral `TemporaryDirectory` (`GIT_TERMINAL_PROMPT=0`) for cascading `--from-parent` bootstrap and `zcg inspect-remote`, rejecting leading-dash option injection (`UNSAFE_GIT_REMOTE_REF`). |

---

## 7. Universal Node Outward Exposure, 3-Mode Connectivity & 3-Tier Data Residency Law

Every sovereign node (`Profile` Root 0, dedicated personal spokes `work / tutor / game / wallet`, community `knowledge` corpora, and corporate hubs) exposes outward strictly the ring and facet required for its purpose while keeping local `R3` control absolute:

1. **Four-Mode Local Exposure & Presence Control (`public_exposure.mode`)**:
   - **`online` (`Available / Interactive`)**: Outward `/portal` active with live availability banner (`availability_note`) and open `POST /portal/{contact,handshake}` forms.
   - **`inbox-only` (`Async Mailbox`)**: Outward `/portal` visible without live presence; queues requests silently into `.zcg/runtime/portal/` for deferred `R3` triage.
   - **`members-only` (`Restricted R1/R2`)**: Rejects anonymous `R0` visitors (`403 PUBLIC_PORTAL_MEMBERS_ONLY`); only authenticated `R1..R3` contacts may view or submit.
   - **`disabled` (`1-Click Kill-Switch`)**: Immediately closes outward `/portal` and incoming forms (`503 PUBLIC_SURFACE_DISABLED_BY_OWNER`), isolating the node to private `R3` operation.
2. **Three-Mode Connectivity Matrix (`Local <-> Neutral Relay <-> Local`)**:
   - **Mode A — Direct `Local <-> Local` (`LAN / WireGuard / Tailscale`)**: Trusted peers connect directly to each node's Native ASGI/SSE server via TTL-bounded `R1 guest` grants (`0` cloud intermediaries).
   - **Mode B — `Scale-to-Zero` Cloud `Profile` Blind Mailbox**: Protects home residential IPs and NAT routers from cold internet traffic; accepts public contact/handshake envelopes while the local PC is offline or in `inbox-only` mode until pulled outbound by the owner.
   - **Mode C — Ephemeral Neutral Session Rooms (`v2.0.0` Horizon)**: Stateless `scale-to-zero` Cloud Run or repo-provisioned temporary neutral containers hosting shared live state (e.g. `game` board moves, `tutor` 1:1 capsule, `work` B2B session) without exposing either participant's private machine.
3. **Three-Tier Data Residency & Privacy Law**:
   - **Tier 1 — Sovereign `R3` Local Disk (`.zcg/runtime/`)**: Vault blobs, `wallet` ledgers, full contact circles, and private notes reside **exclusively** on local storage (`0%` uploaded to cloud relays or shared repos).
   - **Tier 2 — Neutral Transit / Session TTL**: Pending mailbox envelopes and active shared session state exist in the neutral relay strictly for the session/pickup TTL and are purged automatically upon completion or `disabled` kill-switch activation.
   - **Tier 3 — Consolidated Receipts**: Participants persist only their own final signed receipt or summary locally after the ephemeral neutral room is torn down.
