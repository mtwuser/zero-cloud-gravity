# External Host Provisioning Assets (`workstation-control-tower/assets/external`)

> Curated, auditable APT repository setup scripts and host binary installers bundled with the `workstation-control-tower` plugin for `Root 0` (`workstation_root`) Ubuntu workstations.

---

## 1. Curated Installer Inventory (`apt-repo/` & `script/`)

The following table catalogs the 5 host provisioning scripts verified by `scripts/workstation-install.sh` and `scripts/workstation-audit.sh`:

| Category | Script Path | Target Capability & Verification |
| :--- | :--- | :--- |
| **`apt-repo`** | [`apt-repo/docker.sh`](apt-repo/docker.sh) | Official Docker Engine & Compose v2 APT keyring and repository configuration |
| **`apt-repo`** | [`apt-repo/google-chrome.sh`](apt-repo/google-chrome.sh) | Official Google Chrome Stable APT signing key and repository configuration |
| **`apt-repo`** | [`apt-repo/google-cloud-cli.sh`](apt-repo/google-cloud-cli.sh) | Official Google Cloud SDK (`gcloud`, `bq`, `gsutil`) APT keyring and source list |
| **`script`** | [`script/antigravity-ide.sh`](script/antigravity-ide.sh) | Google Antigravity IDE (`agy`) host binary and desktop integration |
| **`script`** | [`script/antigravity-agents.sh`](script/antigravity-agents.sh) | Global Antigravity runtime directories (`~/.gemini/config`, `~/.gemini/antigravity`) |

---

## 2. Execution & Security Invariants

All external provisioning scripts adhere to strict host-safety mandates:

1. **Explicit User Consent & Idempotency**: Scripts check whether the target repository or binary is already installed before invoking privileged package operations.
2. **Cryptographic Keyring Isolation**: APT repositories store GPG keys under `/etc/apt/keyrings/` with explicit `[signed-by=...]` source declarations.
3. **Dry-Run & Audit Visibility**: Inspect host drift at any time via `zcg workstation-audit` (`scripts/workstation-audit.sh`).
