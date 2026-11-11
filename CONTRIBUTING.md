# Contributing to ZeroCloudGravity

Thank you for contributing to **ZeroCloudGravity (`zero-cloud-gravity`)**. Every change must preserve sovereign Zero-Cloud determinism, `1:1:1` (`Specification <-> Verification <-> Implementation`) symmetry, and `100.00%` isolated unit coverage.

---

## Development Setup

Initialize a clean Python 3.12+ virtual environment and run the full verification gate before making changes:

```bash
make setup-dev
make verify
```

---

## Architectural & Code Standards

All pull requests are validated automatically against these repository invariants:

| Invariant | Mandatory Requirement |
| :--- | :--- |
| **Pure Stdlib Runtime** | `pyproject.toml` runtime `dependencies` must remain empty (`[]`); use C-backed Python 3.12+ stdlib modules. |
| **Module Size & Cohesion** | Source modules in `src/zcg/*/*.py` must stay `< 385` lines (`3..8` modules per subpackage); docs, tests, and `SKILL.md` files must stay `< 465` lines (`0` `#####` headings). |
| **Zero-Byte `__init__.py`** | Every `__init__.py` under `src/` and `tests/` must be strictly `0 bytes` (pure package markers). |
| **Strict Typing & Linting** | Zero `ruff check`, `ruff format --check`, or `mypy --strict` errors across `src/`, `tests/`, and `antigravity/.gemini/config/scripts/`. |
| **`1:1:1` Traceability** | Every `src/zcg/<pkg>/<mod>.py` declares `Specification: docs/architecture/0X_*.md`, maps to `tests/unit/zcg/<pkg>/test_<mod>.py`, and appears in the spec's `1:1:1` table. |
| **`100.00%` Isolated Coverage** | `tests/unit/` must pass at `100.00%` statement and branch coverage both collectively and `1:1` per module (`make test-unit-isolated`). |
| **Language & Ecosystem Purity** | Repository files must be 100% technical English and 100% aligned with the Google Antigravity / Google Cloud ecosystem (`0` private IDs; use ISO-neutral examples). |

---

## Spec-First Contribution Workflow

Follow the `1 -> 2 -> 3` progression for all features, refactors, and bug fixes:

1. **Update Specification (`docs/architecture/01..05`)**: Define or refine the contract, constants, error codes, and `1:1:1` row first.
2. **Author `AAA` Tests (`tests/unit/` $\rightarrow$ `tests/imp/` $\rightarrow$ `tests/e2e/`)**: Write `# Arrange`, `# Act`, `# Assert` tests covering nominal paths, `N` vs `N ± 1` boundaries, and bipolar error guards.
3. **Implement & Verify (`make verify`)**: Implement the change cleanly (`0` compatibility shims) and ensure `./scripts/verify-repo.sh` passes all `8/8` checks with `0` warnings.
4. **Conventional Commits & Changelog**: Record user-visible changes under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) and submit atomic Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`).
