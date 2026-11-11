# `workstation-control-tower` (`plugin-stack`) — Tier 2 `Root 0` Personal Workstation Surface

> Tier 2 runtime surface plugin extending `software-engineering` for `Root 0` (`workstation_root`) nodes (`~/alex-pc`), GNU Stow `$HOME` linking, and curated external APT/installer hooks.

---

## 1. Template Identity & Service Contract (`template.json` & `service_contract.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json), [`assets/service_contract.json`](assets/service_contract.json), and [`rules/workstation-control-tower.md`](rules/workstation-control-tower.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `workstation-control-tower` | Runtime surface in `CANONICAL_STARTER_TEMPLATES` (`constants.py`) |
| **`stack_group`** | `plugin-stack` | Editable Reference Dashboard & Cockpit Capability Axis |
| **`extends`** | `"universal-base"` | Inherits universal 13-mandate workstation baseline |
| **`service_contract`** | [`assets/service_contract.json`](assets/service_contract.json) | Declares `enabled_modules`, `web_templates`, `web_static`, and Stow targets |
| **`web_assets`** | [`web/templates/index.html`](web/templates/index.html) · [`web/static/css/plugin.css`](web/static/css/plugin.css) | Editable Two-World `/dashboard` layout and `--zcg-*` theme overrides |
| **`external_assets`** | [`assets/external/README.md`](assets/external/README.md) | Curated `apt-repo/` and `script/` host provisioning hooks |

---

## 2. Core Workstation Capabilities & Dual-Repo `$HOME` Coexistence

The `workstation-control-tower` plugin powers personal `Root 0` workstation nodes (`~/alex-pc`) alongside the `~/zero-cloud-gravity` engine appliance:

1. **Unified `$HOME` Synchronization (`workstation-sync.sh` / `zcg-sync`)**: Fast-forwards `~/zero-cloud-gravity` from clean `~/Projects/dev-zero-cloud-gravity`, synchronizes `~/alex-pc`, and links `bash`, `git`, and `antigravity` into `$HOME` via GNU Stow.
2. **Global Profile & Personal Rule Composition**: Composes the active global profile (`universal-base | academic-base | science-base | business-base`) with the personal workstation overlay (`templates/alex-pc/rules/alex-pc.md`) inside `~/.gemini/config/AGENTS.md` (`<= 18,000` bytes).
3. **Curated Host Provisioning (`assets/external/`)**: Provides auditable scripts for `docker.sh`, `google-chrome.sh`, `google-cloud-cli.sh`, `antigravity-ide.sh`, and `antigravity-agents.sh`.

---

## 3. Activation & Cross-References

Synchronize a `workstation_root` node and `$HOME` runtime in one command:

```bash
~/zero-cloud-gravity/scripts/workstation-sync.sh --setup --profile universal-base --lang es --workstation-dir "$HOME/alex-pc" --auto-sync boot
```

- **External Installers Index**: [`assets/external/README.md`](assets/external/README.md)
- **Workstation Guide**: `docs/guides/01_workstation_and_global_profiles.md`
- **Cockpit Architecture**: `docs/architecture/04_cockpit_and_intranet_surfaces.md`
