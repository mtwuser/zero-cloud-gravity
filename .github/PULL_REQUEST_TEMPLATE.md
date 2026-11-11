## Summary

Describe the architectural, governance, template, or documentation change and link the authoritative specification under `docs/architecture/01..05`.

## `1:1:1` Verification Checklist

- [ ] **Specification Synced**: Updated `docs/architecture/0X_*.md` (or `docs/guides/` / `docs/reference/`) first.
- [ ] **Size & Package-Marker Discipline**: All `src/zcg/*/*.py` `< 385` lines, docs/tests/`SKILL.md` `< 465` lines, and `{src,tests}/**/__init__.py` `0 bytes`.
- [ ] **100.00% Isolated Coverage**: `make verify` (`./scripts/verify-repo.sh` `8/8`) passes with `100.00%` statement and branch coverage across unit (`1:1` isolated), `imp`, and `e2e` suites.
- [ ] **Google & Antigravity Purity**: 100% technical English in repo artifacts, ISO-neutral examples (`0` private IDs), and `0` retired third-party framework references.
- [ ] **Changelog**: Recorded notable changes under `## [Unreleased]` in `CHANGELOG.md`.
