# Multi-Ring Sovereign Wallet & Treasury Cockpit (`sovereign-wallet-cockpit`)

> **Stack Group**: `plugin-stack` · **Extends**: [`science-base`](../../human-stack/science-base/README.md) · **Target Role**: `department` / `squad` · **Default Port**: `8700 + precedence` (`:8720` corporate finance / `:8788` personal `<persona>-wallet`)

`sovereign-wallet-cockpit` delivers a unified, zero-custody treasury and portfolio surface across **`R0` public reserve stewardship**, **`R2` corporate finance & supply departments**, and **`R3` airlocked personal sovereign vaults**, backed by [`src/zcg/plugins/wallet_ledger.py`](../../../src/zcg/plugins/wallet_ledger.py), [`src/zcg/plugins/wallet_treasury.py`](../../../src/zcg/plugins/wallet_treasury.py), and [`src/zcg/plugins/settlement_airlock.py`](../../../src/zcg/plugins/settlement_airlock.py).

---

## 1. Three Operational Capability Rings (`R0` · `R2` · `R3`)

The table below summarizes how the same declarative `plugin-stack` pack adapts across public open-source stewardship, enterprise finance departments, and private individual nodes:

| Ring Mode | Target Node Archetype | Exposed Capabilities & Strict Privacy / Security Boundary |
| :--- | :--- | :--- |
| **`R0` (`public`)** | `zero-cloud-gravity` (`zerocloudgravity.org/stewardship`) & public `org-*` / `pub-*` twins | Publishes public reserve watch addresses (`BTC BIP-173`, `EVM EIP-55`, `Solana Base58`) and verified bilateral receipts (`public-patronage \| agreed-settlement \| venture-allocation`) with block-explorer verification links (`GET /api/modules/wallet-treasury/export-r0`). |
| **`R2` (`network-member`)** | `<corp>-finance-supply` (`precedence: 20`, `:8720`) | Composes `wallet_treasury` directly inside the corporate Finance & Supply department (`cashflow_buckets` *Profit First* / statutory tax vaults, multisig watch addresses `Safe {Wallet}` / `Squads`, and `TelemetryAuditDAG`) without splitting accounting into a separate `<corp>-wallet` silo. |
| **`R3` (`operator`)** | `<persona>-wallet` (`precedence: 88`, `:8788`) | Enforces `loopback-only` egress, `WALLET_EXTERNAL_LINK_BLOCKED` on external peers/MCPs, read-only `knowledge-feed` grounding (`gov-*` `E3` > `sci-economic` `E2` > personal `E1`), **`Base-100 / %` Privacy Shield** (`0` balances or keys in Git), 4-ring `thesis_exposure_graph`, and unidirectional localhost reconciliation from `<persona>-work`. |

---

## 2. Quick-Start CLI Usage

Bootstrap a private `R3` `<persona>-wallet` vault or attach `sovereign-wallet-cockpit` to a corporate finance department:

```bash
# 1. Bootstrap an R3-airlocked personal sovereign portfolio node (:8788):
zcg bootstrap-workspace ~/Projects/<persona>-wallet \
  --id <persona>-wallet --purpose individual-sovereign --role squad --precedence 88 \
  --parent-dir ~/<persona>-profile --templates science-base,scientific-methodology,sovereign-wallet-cockpit

# 2. Mount read-only E3 statutory tax and E2 quantitative economics feeds:
zcg link ~/Projects/<persona>-wallet --target sci-economic --relation knowledge-feed --ref https://github.com/mtwuser/sci-economic
zcg link ~/Projects/<persona>-wallet --target gov-es --relation knowledge-feed --ref https://github.com/mtwuser/gov-es

# 3. Install on an R2 corporate Finance & Supply department (:8720):
zcg apply-project ~/Projects/dept-finance-supply --template sovereign-wallet-cockpit --service-action install
```

---

## 3. Non-Custodial Wallet Discovery (`Wallet Standard` + `EIP-6963`)

`web/static/js/islands/plugin-island.js` and `render_wallet_cockpit_html` discover browser providers via **`window.navigator.wallets` (`Wallet Standard`)** and **`eip6963:announceProvider` (`EIP-6963`)**, supporting **`Phantom`** (`BTC + EVM + Solana`), **`Ledger`**, **`Trezor`**, **`Squads`**, and **`Safe {Wallet}`** strictly for read-only `CAIP-10` ownership proofs (`SIWS`, `SIWE EIP-4361`, `BIP-322`) while rejecting any private key or seed phrase (`422 PRIVATE_SECRET_REJECTED`).
