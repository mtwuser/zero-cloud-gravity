---
trigger: always_on
description: "Multi-ring zero-custody treasury & portfolio invariants across R0 public reserve, R2 corporate finance, and R3 private sovereign vaults (sovereign-wallet-cockpit)."
---

# Multi-Ring Zero-Custody Treasury & Portfolio Rules (`sovereign-wallet-cockpit`)

> Extends `science-base.md` with **`WALLET-01..04`** governing public reserve stewardship (`R0`), corporate finance/multisig modules (`R2`), and airlocked personal sovereign portfolios (`R3`).

---

## 1. Normative Invariants (`WALLET-01..04`)

1. **`WALLET-01` — Zero Custody & Zero Private Financial State in Git**:
   - Never commit private keys, BIP-39 seed mnemonics, `xprv`/`yprv`/`zprv` extended keys, API secrets, account IDs, or private fiat/crypto balances into Git (`PRIVATE_SECRET_REJECTED`).
   - Persist portable allocation targets (`%`), rebalance bands, `cashflow_buckets`, `thesis_exposure_graph` weights, and schema mappers in Git while keeping read-only watch addresses (`CAIP-10`, `BIP-173`, `EIP-55`, `Solana Base58`) and statements inside `.zcg/runtime/wallet/` SQLite WAL outside Git.
2. **`WALLET-02` — Multi-Ring Composition (`R0` Public / `R2` Corporate / `R3` Private)**:
   - **`R0` (`public`)**: Publish verified reserve allocations and human-readable bilateral receipts (`public-patronage | agreed-settlement | venture-allocation`) with block-explorer verification links (`export-r0`).
   - **`R2` (`network-member`)**: Mount `wallet_treasury` inside `<corp>-finance-supply` (`precedence: 20`) without splitting statutory accounting and supply into separate departments.
   - **`R3` (`operator` on `<persona>-wallet`)**: Enforce `loopback-only` network isolation, enable the **`Base-100 / %` Privacy Shield** by default, and block direct external peer or MCP connectors (`WALLET_EXTERNAL_LINK_BLOCKED`).
3. **`WALLET-03` — Epistemic Tax/Portfolio Grounding (`E3 > E2 > E1`) & Non-Custodial Discovery**:
   - Compose `gov-*` (`E3` statutory tax, FIFO vs. fund-transfer deferral, and reporting rules) above `sci-economic` (`E2` quantitative allocation/risk laws) and personal strategy (`E1`) via read-only `knowledge-feed` capsules.
   - Discover browser wallets strictly via vendor-neutral **`Wallet Standard` (`window.navigator.wallets`)** and **`EIP-6963`** (`Phantom` across `BTC + EVM + Solana`, `Ledger`, `Trezor`, `Squads`, `Safe {Wallet}`) using read-only `CAIP-122` / `SIWS` / `SIWE` / `BIP-322` challenges.
4. **`WALLET-04` — `<persona>-work` Settlement Airlock & `0%` Plutocracy (`AuthZ ⊥ W_interaction ⊥ S_treasury`)**:
   - Keep `settlement_mode: "none"` by default; bind opt-in `agreed-settlement` receipts exclusively on `<persona>-work` for verified `WORKVALI.md` deliverables (`WALLET_DIRECT_SETTLEMENT_BLOCKED` on `<persona>-wallet`), reconciled unidirectionally on localhost.
   - Scope `Verified Prior Counterparty Link` handshake badges strictly to bilateral receipts directly involving the target node (`0%` third-party wash-trading weight, `auto_grant_ring = None`).
