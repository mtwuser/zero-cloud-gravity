---
name: ledger-surface-audit
description: "Author and verify Hexagonal Business 1:1:1 traceability between Inner Ledgers (corporate/ledgers/), Business AAA Policies (corporate/policies/), and Outer Surfaces (surfaces/{web,forms,print}/); automatically invoked by /review and /audit when corporate-operations is active."
---
# Skill: Hexagonal Business Ledger-to-Surface `1:1:1` Playbook (`ledger-surface-audit`)

---

## Purpose & Context-Adaptive `/review` / `/audit` Integration

Provides the **Hexagonal Business `1:1:1` Domain Playbook (`Inner Ledger <-> Policy/SOP <-> Outer Surface`)** for workspaces using `context-stack/corporate-operations`:
1. **Automatic Context-Adaptive Invocation via `/review` & `/audit`**: Whenever `corporate-operations` (`rules/corporate-operations.md`) is active in `.agents/rules/`, running **`/review`** (`/review arch` or `/review 1:1:1`, `C1` tactical) or **`/audit`** (`/audit arch` or `/audit 1:1:1`, `C2` closed-world) automatically executes the 4-Step Audit Workflow below.
2. **Constructive Authoring & Direct Invocation**: Invoke `ledger-surface-audit` directly when authoring new `corporate/ledgers/*.md` records (`[DEPT]-[TYPE]-[YYYY]-[NNN]`), drafting Business `AAA` policies (`corporate/{policies,sops}/*.md`), or publishing outward `surfaces/{web,forms,print}/` deliverables.

---

## 4-Step Audit Workflow

### Step 1: Inventory Inner Ledgers (`corporate/ledgers/`)
1. Read the active ledger files under `corporate/ledgers/` (financial/pricing tables, legal/IP docket, operational release logs).
2. Extract the authoritative `[DEPT]-[TYPE]-[YYYY]-[NNN]` identifiers, exact figures (`EUR`/`USD`), `SI`/`ISO` units, and confidentiality classification (`Public`, `20/80 Summary`, `Restricted <TS-ID>`).

### Step 2: Verify Business `AAA` Structure in Policies & SOPs (`corporate/{policies,sops}/`)
Check every Markdown document in `corporate/policies/` and `corporate/sops/` for the three mandatory sections:
- `## Scope & Surface Target` (*Arrange*)
- `## Normative Invariants` (*Act*)
- `## Verification & Sign-Off Gates` (*Assert*)

Flag any policy missing one of these sections or lacking a `> **Ledger Grounding**:` header.

### Step 3: Cross-Surface Claim & Drift Sweep (`surfaces/{web,forms,print}/`)
Scan all files in `surfaces/web/`, `surfaces/forms/`, and `surfaces/print/`:
1. **Unbacked Claim Detection**: Flag any price, discount, lead time, regulatory claim, or technical tolerance that does not cite or match an entry in `corporate/ledgers/`.
2. **Rounding & Unit Drift**: Verify that currencies (`EUR` vs. `USD`), cost basis (`Lean` vs. `Full COTS`, VAT inclusion), and `SI`/`ISO` units match the ledger character-for-character.
3. **Print & Accessibility Pre-Flight**: On `surfaces/print/` and `surfaces/web/` specs, verify WCAG contrast gates (`>= 4.5:1` body, `>= 7:1` safety) and print bleed/resolution gates (`>= 3 mm` bleed, `>= 300 DPI`).

### Step 4: Confidentiality & Trade Secret Firewall Check
Confirm that restricted items (`<IP-ID>` prior to public release or `<TS-ID>` trade secrets) are referenced only by their opaque registry ID or approved `20/80` functional outcome, never exposing internal algorithmic parameters or confidential BOM breakdowns on external surfaces.
