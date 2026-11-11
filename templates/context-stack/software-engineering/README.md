# `software-engineering` (`context-stack`) — Tier 2 Architecture, Refactoring & `100%` Isolated Testing

> Tier 2 software engineering specialization extending `science-base` with strict typing, 3-regime determinism, OWASP ASVS / MCP-Sec gates, and `100.00%` isolated `Unit -> Imp -> E2E` verification.

---

## 1. Template Identity & Lineage (`template.json`)

The following table summarizes the canonical metadata declared in [`template.json`](template.json) and enforced by [`rules/software-engineering.md`](rules/software-engineering.md):

| Attribute | Canonical Value | Verification & Runtime Role |
| :--- | :--- | :--- |
| **`id`** | `software-engineering` | Domain specialization in `VALID_CONTEXT_STACK_IDS` (`constants.py`) |
| **`stack_group`** | `context-stack` | Domain Methodology & Practice Axis |
| **`tier`** | `2` (`Domain Specialization`) | Materialized into `.agents/rules/software-engineering.md` via `zcg sync-layer` |
| **`extends`** | `["science-base"]` | Transitively resolves `universal-base -> science-base -> software-engineering` |
| **`rules_file`** | [`rules/software-engineering.md`](rules/software-engineering.md) | Strict typing, $M_{\text{cluster}}$ refactoring, AppSec/MCP-Sec, and `100%` unit coverage |

---

## 2. Core Engineering & Testing Mandates

The `software-engineering` specialization governs all application, CLI, library, and MCP server repositories:

1. **Strict Typing, C-Backed Stdlib & Package-Marker Gate**: Require zero errors across `ruff`, `mypy --strict`, and `bash -n`; prefer C-backed stdlib (`hashlib.file_digest`, `stat.S_IWUSR`, `HTTPStatus`), explicit absolute imports (`0` aliases), and `0-byte` `{src,tests}/**/__init__.py` markers.
2. **3-Regime Determinism & 5-Surface Ripple**: Propagate changes across `1. Rule/Function -> 2. CLI/Process -> 3. Makefile/Hook -> 4. Spec Table -> 5. Docs/Verification` in the same iteration while keeping modules `< 465` lines (target `<= 385`).
3. **AppSec & Multi-Layer MCP Security (`OWASP ASVS` + `MCP-Sec`)**: Enforce boundary schema validation, subprocess argument lists (`shell=False`), `Path.resolve().is_relative_to(workspace_root)` (`PATH_CONTAINMENT_VIOLATION`), and HMAC `DMCP` frames.
4. **100% Isolated `Unit -> Imp -> E2E` Flow (`AAA`)**: Deduce top-down (`E2E -> Imp -> Unit`), author bottom-up (`Unit -> Imp -> E2E`), and enforce `100.00%` isolated statement and branch coverage on `tests/unit/<path>/test_<module>.py`.

---

## 3. Mounting & Cross-References

Declare `software-engineering` in `system/zcg-node.json` under `stack_groups.context_stack` and synchronize the node:

```bash
zcg sync-layer /path/to/software-node
```

- **Parent Human Stack**: `templates/human-stack/science-base/README.md`
- **Catalog Reference**: `docs/reference/01_stack_and_plugin_matrix.md`
