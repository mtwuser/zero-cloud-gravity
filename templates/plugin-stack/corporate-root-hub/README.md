# `corporate-root-hub` (`plugin-stack`) — Tier 2 `Root 0` Enterprise Portfolio Hub Surface

> Tier 2 runtime surface plugin extending `corporate-operations` for `Root 0` (`corporate_root`) hubs (`acme-root`), multi-node portfolio telemetry, and intranet cockpit generation.

---

## 1. Template Identity & Service Contract (`template.json` & `service_contract.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json), [`assets/service_contract.json`](assets/service_contract.json), and [`rules/corporate-root-hub.md`](rules/corporate-root-hub.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `corporate-root-hub` | Runtime surface in `CANONICAL_STARTER_TEMPLATES` (`constants.py`) |
| **`stack_group`** | `plugin-stack` | Editable Reference Dashboard & Cockpit Capability Axis |
| **`extends`** | `"corporate-operations"` | Inherits portfolio and RBAC governance from `corporate-operations` |
| **`service_contract`** | [`assets/service_contract.json`](assets/service_contract.json) | Declares `enabled_modules`, `web_templates`, `web_static`, and RBAC gates |
| **`web_assets`** | [`web/templates/index.html`](web/templates/index.html) · [`web/static/css/plugin.css`](web/static/css/plugin.css) | Editable Two-World `/dashboard` layout and `--zcg-*` theme overrides |
| **`rules_file`** | [`rules/corporate-root-hub.md`](rules/corporate-root-hub.md) | Hub-to-spoke delegation (`make delegate`), `corporate/` parity, and release gates |

---

## 2. Core Enterprise Hub Capabilities

The `corporate-root-hub` plugin equips `corporate_root` repositories with cross-portfolio visibility and governance enforcement:

1. **Multi-Node Topology Aggregation**: Discovers and audits federated child nodes (`node` / `subnode`) registered in the corporate portfolio, aggregating `WORKROAD.md` and `WORKTASK.md` completion states.
2. **RBAC & Stage-Gate Enforcement**: Integrates `zcg roster`, `zcg decision`, and `zcg env-gate` into the hub's intranet cockpit (`zcg generate-intranet`) with `ZCG_NO_BROWSER=1` headless safety.
3. **1-Hop Directive Delegation (`zcg delegate`)**: Dispatches bounded work directives from the corporate hub to child repositories with deterministic receipt tracking.

---

## 3. Mounting & Cross-References

Declare `corporate-root-hub` in `system/zcg-node.json` under `stack_groups.plugin_stack` and synchronize the hub:

```bash
zcg sync-layer /path/to/corporate-hub
```

- **Parent Context Stack**: `templates/context-stack/corporate-operations/README.md`
- **Cockpit Architecture**: `docs/architecture/04_cockpit_and_intranet_surfaces.md`
- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
