---
name: release
description: "Cut and publish an explicit SemVer release (vX.Y.Z) — promotes [Unreleased] in CHANGELOG.md, syncs VERSION/pyproject.toml/README.md, runs agnosticism & verification gates, and delivers the release commit + tag + push block."
---

# Release Workflow — `/release`

Execute this workflow **ONLY** when the user explicitly requests cutting or publishing a new versioned release (`vX.Y.Z`). During normal development (`/continue`, `/sclose`), changes remain under `## [Unreleased]` in `CHANGELOG.md` and `VERSION` is never bumped prematurely.

---

## 1. Layer Authority, Agnosticism & Zero-Residue Scan

1. **Layer Owner vs. Consumer Authority Gate (`check-authority --op release`)**:
   - When releasing a governance layer repository (`system/zcg-node.json`), verify caller authority via `zcg check-authority <repo-dir> --op release`.
   - If the caller is a downstream consumer (or their `git config user.email` does not match `layer_authority.authorized_emails`), **STOP**: a consumer squad must **never** publish upstream department/corporate rules directly. Instead, run `zcg promote-from-project <your-workspace> --source <file> --to-layer <upstream-layer> --create-pr` to open a Pull Request from the originating layer's context and coordinate with `layer_authority.escalation_contact`.
2. **Open-Source Agnosticism, ISO-Neutral Examples & Zero-Literal Exclusion Gate (Public / Upstream Repos)**:
   - Verify that zero private downstream organization names, internal project codenames, national agency acronyms, or private vertical terminology appear anywhere in `CHANGELOG.md`, `README.md`, `docs/`, `templates/`, `scripts/`, or `tests/`. Always use ISO-neutral, jurisdiction-agnostic, and industry-neutral identifiers (`gov-iso`, `gov-eu`, `geo-iso`, `[ISO-NNNN]`, `[LAW-YYYY-NNNN]`, `Record #NNN`).
   - **Anti-Streisand Invariant**: Never hardcode forbidden private names (not even hex- or base64-encoded) inside the repository's own tests or scripts; rely on dynamic local discovery or structural regex patterns.
3. **Sterile Working Tree & Residue Scan**:
   - Check `git status --short` and remove any temporary scratch files, `.svg` renders, or untracked artifacts.

---

## 2. Target SemVer Resolution & Multi-File Version Sync

1. **Determine Target Version (`X.Y.Z`)**:
   - Read the current published version from `VERSION` (and `git tag --list` / `origin`).
   - Apply the requested increment (`patch`, `minor`, `major`, or explicit `X.Y.Z` based on `## [Unreleased]` scope: `### Added` $\rightarrow$ `minor`, `### Fixed` only $\rightarrow$ `patch`).
2. **Promote `## [Unreleased]` in `CHANGELOG.md`**:
   - Replace `## [Unreleased]` with `## [X.Y.Z] - YYYY-MM-DD` (using today's ISO date).
   - Ensure all entries under the new version heading are clean, accurate, and free of internal ticket references.
3. **Synchronize Version Markers in Lockstep**:
   - Update `VERSION` to `X.Y.Z`.
   - If `pyproject.toml` exists, update `version = "X.Y.Z"`.
   - If `README.md` contains version badges (`version-X.Y.Z-blue.svg`) or inline version references (`VERSION` (`X.Y.Z`)), update them to `X.Y.Z`.

---

## 3. Deterministic Verification Gate

1. **Discover Active Verification Target & Branch First**:
   - Check `git branch --show-current` (never hardcode `main` vs `master`) and inspect the `Makefile` / `operating_state`: run `make verify` (or `./scripts/verify-repo.sh`) in technical/software repositories, or `make diff && make horizon && make mcp-test` in `corporate-root` / `department` / `squad` governance repositories.
2. If any linter, type-check, unit/E2E test, coverage gate, or parity check fails, **STOP** and fix all issues before delivering the release commit block.

---

## 4. Deliver Explicit Release Commit, Tag & Push Block

Never execute mutating git commands automatically. Substitute `<branch>` with the exact output of `git branch --show-current` (`master` or `main`).

- **Standard Repository (`origin` only)**:
```bash
### Release vX.Y.Z (<Repo Name>)
cd <REPO_PATH>
git add -A
git commit -m "chore(release): publish vX.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin <branch> --follow-tags
```

- **Dual-Remote Private Dev Workspace (`dev-<repo>` $\rightarrow$ Private CI Gate $\rightarrow$ Public Open-Source Snapshot)**:
  When releasing an Open-Source upstream repository, **always execute `/release` from `ZCG_DEV_REPO_DIR` (`dev-zero-cloud-gravity`, `entity_kind: "open-source"` on verified linear `master`), NEVER from a personal or corporate runtime clone (`~/<user-pc>`)** (`OSS_PERSONAL_REPO_PUBLISH_BLOCKED`). Follow the two-step CI-verified export so a public tag never needs re-patching:
  1. **Step A — Seal & Validate Release Commit on Private `origin` First**: Commit the release bump (`CHANGELOG.md`, `VERSION`, `pyproject.toml`, `README.md`), tag `vX.Y.Z` locally, push to private `origin` (`git push origin <branch> --follow-tags`), and confirm private GitHub Actions (`8/8` gates) turns green.
  2. **Step B — Export Sterile Single-Commit Snapshot to Public `upstream` + Sync `$HOME`**: Run `make publish-oss RELEASE_VERSION=X.Y.Z` (authorized directly for the repository admin via GitHub Ruleset bypass while external contributors use Fork Pull Requests or `make publish-oss CREATE_PR=1 CONTRIB_BRANCH=contrib/<slug> OSS_REMOTE_URL=<fork-url>`), which exports `1` tracker-free commit (`git archive HEAD` minus `WORK*.md`, `BACKLOG.md`, `roadmaps/`) + annotated tag `vX.Y.Z` onto public `master` and syncs `$HOME`:
```bash
### Step A — Seal & Push Release Candidate to Private Origin (Wait for Green Private CI)
cd <DEV_REPO_PATH>
git add -u
git commit -m "chore(release): publish vX.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin <branch> --follow-tags

### Step B — Export Verified Snapshot to Public Open-Source Upstream (Once Private CI is Green)
cd <DEV_REPO_PATH>
make publish-oss RELEASE_VERSION=X.Y.Z
```
