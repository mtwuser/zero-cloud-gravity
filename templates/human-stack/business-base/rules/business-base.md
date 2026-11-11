---
trigger: always_on
description: Universal corporate ledger integrity, Lex Superior IP firewall, cross-surface cascade, and functional verification rules
---
# Enterprise, Normative & Functional Governance Baseline (`business-base`)

> Universal corporate, regulatory, financial, and surface rules for holdings, departments, and functional workspaces (`1:1:1` traceability, `100%` coverage, `AAA` verification).

---

## Corporate Ledger & Normative Integrity

- **Description**: Single Source of Truth ledgers, deontic authority (*Lex Superior*), and confidentiality gates
- **Applies**: All corporate (`corporate/**`), departmental (`layers/dept-*/**`), documentation (`docs/**`), and surface (`surfaces/**`) files

1. **Single Source of Truth Ledgers (`corporate/`)**: Records in `corporate/` (IP, contract, BOM/CAPEX, release) enforce production schemas; never invent, round, or estimate figures or clauses (`[DEPT]-[TYPE]-[YYYY]-[NNN]`).
2. **Deontic Precedence (*Lex Superior*), Libraries (`{gov,geo,org}-*`) & IP Firewall**: Enforce `precedence` (`0..100`), `entity_kind` (`public-government` `1..4`, `enterprise` `5..84`, `individual` `85..95`), and `governing_root_id`: Public `Root 0` (`1..2`) $\rightarrow$ Public Dept (`3..4`) $\rightarrow$ Legal/IP (`5`) $\rightarrow$ Corporate `Root 0` (`10`) $\rightarrow$ Dept (`15..40`) $\rightarrow$ Squad (`40..60`) $\rightarrow$ Project (`80`) $\rightarrow$ `Human-Stack` (`85..95`). Leak zero trade secrets into `surfaces/{web,forms,print}/`; cite `<IP-ID>`, `<TS-ID>`, `Record #NNN`, and `citation_receipt` (`CITATION_DRIFT_DETECTED`).
3. **Cross-Surface Cascade, $N$-Layer Consensus & SLAs**: Audit `surfaces/{web,forms,print}/**`, enforcing SLAs (`P0 < 1h`, `P1 < 4h`, `P2 < 24h`) and 4-state consensus (`RECONCILED_FLOW`, `ITERATION_REQUIRED`, `ESCALATE_TO_ROOT`, `ESCALATE_INTER_ENTITY_ROOTS`).

---

## Functional Verification & Documentary Decommissioning

- **Description**: Business `100%` coverage, `AAA` structure, and zero-residue refactoring
- **Applies**: All policies, contracts, SOPs, financial ledgers, and surface specifications

1. **Three-Part Functional Verification (Business `AAA` — MANDATORY)**: Policies, contracts, SOPs, and surface specs MUST include `# Scope & Surface Target` (*Arrange*), `# Normative Invariants` (*Act*: `<DEPT>-01`), and `# Verification & Sign-Off Gates` (*Assert*: pass/fail gates, co-signatures, MCP/CLI checks).
2. **Quantitative, Financial & Unit Precision**: Specify currency (`EUR` / `USD`), cost basis (`Lean` vs `Full COTS`, tax/VAT), SI/ISO unit, grade, and `Record #NNN`.
3. **Brand, Print QA, Evidence, `Q1..Q4` & `BACKLOG.md`**: Enforce corporate casing, Design (`30`) $\rightarrow$ Marketing (`35`) token locks, WCAG (`>= 4.5:1` body, `>= 7:1` safety), and print pre-flight (`>= 3 mm` bleed, `>= 300 DPI`). Ground claims in `corporate/` (`Record #NNN`), audit `Q4_NORMATIVE_OBSOLESCENCE`, log `< 465`-line splits in `BACKLOG.md` (`[BKL-NNN]`), pass `strictly-read-only` checks before `pre`/`pro`, and log in `CHANGELOG.md`.
