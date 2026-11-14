## Summary

<!-- Describe what this Pull Request adds, fixes, or refactors, linking the authoritative specification under docs/architecture/01..06. -->

## Affected Architectural Plane / Subsystem

- [ ] **Core, Domain Primitives & Data Platform (`src/zcg/core/`, `src/zcg/platform/`)**
- [ ] **Autonomous Native ASGI Web & API Engine (`src/zcg/web/`)**
- [ ] **Topology, Multi-Layer Governance & CLI (`src/zcg/topology/`, `src/zcg/governance/`, `src/zcg/cli/`)**
- [ ] **Node Cockpits, RFC 6761 Domains & Plugin SDK (`src/zcg/cockpit/`)**
- [ ] **Contextual MCP Server, `rcap1` Capsules & Ephemeral Bots (`src/zcg/capsules/`, `src/zcg/ephemeral/`, `src/zcg/mcp/`)**
- [ ] **Declarative `16`-Pack Stack Templates (`templates/{human,context,framework,plugin}-stack/`)**
- [ ] **Antigravity 2.0 Global Rules, Lifecycle Hooks & Skills (`antigravity/.gemini/config/`)**
- [ ] **Ubuntu 26.04 Workstation Scripts, CI & Documentation (`install.sh`, `scripts/`, `.github/`, `README.md`, `docs/`)**

## Community Attribution & Upward Promotion Metadata (Optional)

<!-- Optional when promoting anonymized patterns upward from a Root 0 or Departmental workspace (/enrich -> OSS PR). -->

| Field | Value |
| :--- | :--- |
| **Origin Archetype / Template Pack** | `e.g., corporate-root-0 -> templates/context-stack/corporate-operations` |
| **Contributing Organization (Optional)** | `Anonymous Organization (default)` |
| **Contributors / Roles (Optional)** | `e.g., Principal Systems Architect, SecOps Lead (@github-handles or roles)` |
| **Validation Topology** | `e.g., Verified across Root 0 + 3 Department layers + Squad projects` |
| **Release Notes Attribution** | `[ ] Credit in CHANGELOG.md` / `[x] Keep anonymous` |

## `1:1:1` Verification & Hygiene Checklist

- [ ] **Specification First**: Synced `docs/architecture/01..06` (and `docs/guides/` or `docs/reference/` where applicable) prior to implementation.
- [ ] **Modularity & Package Purity**: All `src/zcg/**.py` `<= 384` lines, docs/tests/`SKILL.md` `<= 464` lines (`0` `#####` headings), and `{src,tests}/**/__init__.py` strictly `0 bytes`.
- [ ] **8/8 Verification Gate**: `make verify` (`./scripts/verify-repo.sh`) passes with `0` errors (`ruff`, `mypy --strict`, `zcg lint-arch`, `zcg-mcp --self-test`, and **`100.00%` isolated `1:1` unit + total statement/branch coverage**).
- [ ] **Ecosystem & Privacy Purity**: 100% technical English, ISO-neutral examples (`0` private IDs or credentials), and `0` retired third-party framework tokens.
- [ ] **Changelog Discipline**: User-visible changes recorded under `## [Unreleased]` in `CHANGELOG.md` (`VERSION` bumped only in dedicated release PRs).
