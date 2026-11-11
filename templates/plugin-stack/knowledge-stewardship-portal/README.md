# `knowledge-stewardship-portal` (`plugin-stack`) — Tier 2 Epistemic Corpus & Public Twin Portal

> Tier 2 runtime Reference Dashboard extending `scientific-methodology` for public and institutional `knowledge` nodes (`gov-*`, `geo-*`, `sci-*`, `org-*`, `:8720`), combining `data_pipeline` (`SchemaDiscovery` / `CDC` / `CVS`), `crud` (`epistemic-entries`), `vault`, and `node_mesh`.

---

## 1. Template Identity & Service Contract (`template.json` & `service_contract.json`)

The table below summarizes the canonical metadata declared in [`template.json`](template.json), [`assets/service_contract.json`](assets/service_contract.json), and [`rules/knowledge-stewardship-portal.md`](rules/knowledge-stewardship-portal.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `knowledge-stewardship-portal` | Default `knowledge` role plugin in `CANONICAL_STARTER_TEMPLATES` (`constants.py`) |
| **`stack_group`** | `plugin-stack` | Editable Reference Dashboard & Runtime Surface Axis |
| **`extends`** | `"scientific-methodology"` | Transitively resolves `universal-base -> science-base -> scientific-methodology` |
| **`enabled_modules`** | `["data_pipeline", "crud", "vault", "node_mesh"]` | Composes stateful CDC/CVS ingestion, epistemic CRUD entries, blob vault, and 1-hop mesh |
| **`web_assets`** | `web/templates/` + `web/static/` | Cascading `TemplateCatalog` (`index.html`, `partials/overview.html`) & `--zcg-*` `plugin.css` |

---

## 2. Core Epistemic & Public Twin Capabilities

The `knowledge-stewardship-portal` plugin powers `.knowledge.local` (`:8720`) portals across all 3 stewardship stages (`private-incubation -> public-community -> sovereign-authority`):

1. **Data Pipeline & Drift Validation (`data_pipeline`)**: Runs `SchemaDiscovery`, `ChangeDataCapture` (`INSERT` / `UPDATE`), `ContinuousValidationScorer`, and `SchemaDriftDetector` over curated tabular datasets at `/api/modules/data-pipeline`.
2. **Epistemic Collection & Asset Vault (`crud` + `vault`)**: Exposes `epistemic-entries` (`E3..E0` filterable cards/list/table at `/api/modules/crud`) and SHA-256 content-addressed annexes (`/api/modules/vault`) stored under untracked `.agents/telemetry/`.
3. **Two-World Editable Web Templates (`/dashboard`)**: Ships editable [`web/templates/index.html`](web/templates/index.html) and [`web/static/css/plugin.css`](web/static/css/plugin.css) overridable per node in `<workspace>/surfaces/web/{templates,static}/`.

---

## 3. Activation & Cross-References

Bootstrap or synchronize a `knowledge` node with `knowledge-stewardship-portal`:

```bash
zcg bootstrap-workspace /path/to/sci-corpus --id sci-corpus --role knowledge --precedence 20
```

- **Parent Context Stack**: [`scientific-methodology`](../../context-stack/scientific-methodology/README.md)
- **Cockpit Architecture**: [`docs/architecture/04_cockpit_and_intranet_surfaces.md`](../../../docs/architecture/04_cockpit_and_intranet_surfaces.md)
- **Web Engine Specification**: [`docs/architecture/06_web_and_api_application_engine.md`](../../../docs/architecture/06_web_and_api_application_engine.md)
