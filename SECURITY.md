# Security Policy (`NIST CSF 2.0` + `OWASP ASVS` + `MCP-Sec`)

**ZeroCloudGravity (`zero-cloud-gravity`)** treats capability security, path containment, and read-only MCP isolation as foundational architectural invariants.

---

## Supported Versions

Security patches are maintained for the active `1.x` release line:

| Version | Supported | Notes |
| :--- | :--- | :--- |
| `1.0.x` | Yes | Current Sovereign Zero-Cloud Node & `zcg-mcp` baseline. |

---

## Built-In Security Controls

Every ZeroCloudGravity node enforces five defense-in-depth rings across CLI, hooks, MCP, and container boundaries:

| Control Plane | Mechanism | Concrete Enforcement |
| :--- | :--- | :--- |
| **1. Path Containment** | `Path.resolve().is_relative_to(root)` | Blocks `..` traversal, symlink escapes, and unauthorized root reads with `PATH_CONTAINMENT_VIOLATION` in [identity.py](src/zcg/topology/identity.py) and [node_base.py](src/zcg/mcp/node_base.py). |
| **2. Read-Only `zcg-mcp`** | Capability Rings (`R0..R2`, `0` `W` tools) | `ZeroCloudMCPServer` exposes strictly read-only inspection, capsule compaction, and sandboxed fork tools (`mcp_security_mode: "strictly-read-only-path-contained"`). |
| **3. Ephemeral Sandboxes** | `chmod 0o555` + TTL Reaper | Ephemeral Department Bots ([spawner.py](src/zcg/ephemeral/spawner.py)) materialize read-only (`0o555`/`0o444`) sandboxes with bounded TTLs and zero write capabilities. |
| **4. Cryptographic Capsules** | `HMAC-SHA256` + `SHA-256` Receipts | `rcap1` capsules ([codec.py](src/zcg/capsules/codec.py)) authenticate `ZCG_RESONANCE_KEY` frames and detect source tampering via `CITATION_DRIFT_DETECTED` ([citations.py](src/zcg/capsules/citations.py)). |
| **5. Lifecycle Hook Guard** | `PreToolUse` (`pre_tool_guard.py`) | Deterministic Antigravity hook ([pre_tool_guard.py](antigravity/.gemini/config/scripts/pre_tool_guard.py)) blocks automated mutating Git commands, destructive shell patterns, and protected rule overwrites. |

---

## Subprocess & Container Hardening

- **Zero Shell Interpolation**: Python modules execute external binaries (`git`, `xdg-open`, verification scripts) strictly as argument lists with `shell=False`.
- **Non-Root Container**: [Dockerfile](Dockerfile) runs `zcg-mcp` under an unprivileged `zcg` user (`UID 10001`) with `ZCG_NO_BROWSER=1` and zero network ports exposed.
- **Zero Secrets in Git**: Never commit API keys, `ZCG_RESONANCE_KEY` secrets, or private organizational identifiers; inject credentials exclusively via runtime environment variables or Google Cloud Application Default Credentials (`IAM/ADC`).

---

## Reporting a Vulnerability

Please **do not** open public GitHub issues for suspected security vulnerabilities:

1. Report vulnerabilities privately via [GitHub Security Advisories](https://github.com/mtwuser/zero-cloud-gravity/security/advisories/new).
2. Include affected module paths, reproduction inputs, and expected vs. observed capability boundaries.
3. Maintainers acknowledge reports within `72 hours` and publish coordinated fixes with regression unit tests.
