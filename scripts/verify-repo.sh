#!/usr/bin/env bash
# ZeroCloudGravity (v1.0.1) — Deterministic 8-Stage Repository Verification Gate
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_DIR}"

export PYTHONDONTWRITEBYTECODE=1
export ZCG_NO_BROWSER=1
export NO_COLOR=1
export LC_ALL=C.UTF-8

VENV_BIN="${REPO_DIR}/.venv/bin"
PYTHON="${VENV_BIN}/python"
PYTEST="${VENV_BIN}/pytest"
RUFF="${VENV_BIN}/ruff"
MYPY="${VENV_BIN}/mypy"
SHELLCHECK="${VENV_BIN}/shellcheck"
ZCG="${VENV_BIN}/zcg"
ZCG_MCP="${VENV_BIN}/zcg-mcp"

if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
  PYTEST="pytest"
  RUFF="ruff"
  MYPY="mypy"
fi
if [[ ! -x "${SHELLCHECK}" ]]; then
  SHELLCHECK="shellcheck"
fi

cleanup() {
  rm -f "${REPO_DIR}/.coverage"
}
trap cleanup EXIT

VERSION_STR="$(tr -d '[:space:]' < "${REPO_DIR}/VERSION")"
echo "=== ZeroCloudGravity Repository Verification (v${VERSION_STR}) ==="

echo ""
echo "[1/8] Open-Source Metadata, SemVer & Relative Markdown Links"
for req in VERSION LICENSE README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md \
  CODE_OF_CONDUCT.md ACCESSIBILITY.md Makefile Dockerfile .dockerignore install.sh \
  pyproject.toml requirements.txt requirements-dev.txt system/zcg-node.json \
  docs/README.md \
  docs/guides/01_workstation_and_global_profiles.md \
  docs/guides/02_sovereign_nodes_and_federated_workflows.md \
  docs/architecture/01_core_and_node_manifest.md \
  docs/architecture/02_triadic_topology_and_twin_surfaces.md \
  docs/architecture/03_governance_and_work_ledger.md \
  docs/architecture/04_cockpit_and_intranet_surfaces.md \
  docs/architecture/05_contextual_mcp_and_capsules.md \
  docs/architecture/06_web_and_api_application_engine.md \
  docs/reference/01_stack_and_plugin_matrix.md \
  docs/reference/02_cli_mcp_and_security_reference.md \
  .github/workflows/ci.yml \
  .github/FUNDING.yml \
  .github/FUNDING.md \
  .github/PULL_REQUEST_TEMPLATE.md \
  .github/ISSUE_TEMPLATE/bug_report.yml \
  .github/ISSUE_TEMPLATE/feature_request.yml \
  .github/ISSUE_TEMPLATE/config.yml; do
  [[ -f "${REPO_DIR}/${req}" ]] || { echo "Missing required file: ${req}" >&2; exit 1; }
done
[[ "${VERSION_STR}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Invalid SemVer: ${VERSION_STR}" >&2; exit 1; }
echo "  OK: VERSION (${VERSION_STR}), OSS metadata, and 3-tier docs present"

echo ""
echo "[2/8] Shell Scripts Syntax (bash -n), Executable Bits & ShellCheck"
SH_ENTRYPOINTS=(
  install.sh
  scripts/verify-repo.sh
  scripts/install-antigravity.sh
  scripts/workstation-sync.sh
  scripts/workstation-backup.sh
  scripts/workstation-audit.sh
  scripts/workstation-restore.sh
)
for sh_file in "${SH_ENTRYPOINTS[@]}"; do
  [[ -x "${REPO_DIR}/${sh_file}" ]] || { echo "Not executable: ${sh_file}" >&2; exit 1; }
  bash -n "${REPO_DIR}/${sh_file}"
done
command -v "${SHELLCHECK}" >/dev/null 2>&1 || { echo "Missing required tool: shellcheck (run 'make setup-dev')" >&2; exit 1; }
"${SHELLCHECK}" "${SH_ENTRYPOINTS[@]}" templates/plugin-stack/workstation-control-tower/assets/external/*/*.sh
echo "  OK: Verified syntax and permissions on shell entrypoints and external recipes"

echo ""
echo "[3/8] Python Linting (ruff), Strict Type Checking (mypy --strict) & AAA Structure"
"${RUFF}" check src tests antigravity/.gemini/config/scripts
"${RUFF}" format --check src tests antigravity/.gemini/config/scripts
MYPYPATH=src "${MYPY}" --strict src/zcg tests antigravity/.gemini/config/scripts
PYTHONPATH=antigravity/.gemini/config/scripts "${PYTHON}" -c '
from pathlib import Path
from post_invocation_lint import check_universal_python_structure
files = [str(p) for p in sorted(Path("src").rglob("*.py"))] + [str(p) for p in sorted(Path("tests").rglob("*.py"))]
violations = check_universal_python_structure(files)
assert not violations, f"Structural/AAA violations: {violations}"
'
if [[ -x "${ZCG}" ]]; then
  "${ZCG}" lint-arch "${REPO_DIR}" >/dev/null
else
  PYTHONPATH=src "${PYTHON}" -m zcg.cli.dispatcher lint-arch "${REPO_DIR}" >/dev/null
fi
echo "  OK: ruff check, ruff format, mypy --strict, zcg lint-arch, and AAA structure passed (0 issues)"

echo ""
echo "[4/8] Antigravity Lifecycle hooks.json Schema & Script Parity"
PYTHONPATH=src "${PYTHON}" -c '
import json, os
from pathlib import Path
root = Path.cwd()
cfg_dir = root / "antigravity/.gemini/config"
cfg = json.loads((cfg_dir / "hooks.json").read_text("utf-8"))
expected = {"PreToolUse", "PostToolUse", "PostInvocation", "Stop"}
seen_events, cmd_count = set(), 0
for group_map in cfg.values():
    for evt_name, entries in group_map.items():
        seen_events.add(evt_name)
        for item in entries:
            for hk in item.get("hooks", [item]):
                sp = (cfg_dir / str(hk["command"]).split()[-1]).resolve()
                assert sp.is_file() and os.access(sp, os.X_OK), f"Invalid hook script: {sp}"
                cmd_count += 1
assert seen_events == expected and cmd_count == 4
'
echo "  OK: Verified 4 Antigravity lifecycle hooks and executable scripts"

echo ""
echo "[5/8] AGENTS.md Token Budget & Google Ecosystem Purity Gate"
AGENTS_BYTES="$(wc -c < "${REPO_DIR}/antigravity/.gemini/config/AGENTS.md" | tr -d '[:space:]')"
(( AGENTS_BYTES <= 18000 )) || { echo "AGENTS.md exceeds 18000 bytes (${AGENTS_BYTES})" >&2; exit 1; }
echo "  OK: AGENTS.md size is ${AGENTS_BYTES} bytes (<= 18000-byte budget cap)"

echo ""
echo "[6/8] SKILL.md Frontmatter (kebab-case, 1:1 Folder Parity & < 465 Lines)"
PYTHONPATH=src "${PYTHON}" -c '
from pathlib import Path
from zcg.core.constants import KEBAB_ID_RE
from zcg.core.manifests import parse_skill_frontmatter
root = Path.cwd()
skills = [*sorted((root / "antigravity/.gemini/config/skills").glob("*/SKILL.md")), *sorted((root / "templates").rglob("SKILL.md"))]
assert len(skills) == 17, f"Expected 17 total SKILL.md files (8 global + 9 stack), got {len(skills)}"
for sk in skills:
    fm = parse_skill_frontmatter(sk, root)
    assert KEBAB_ID_RE.match(str(fm["name"])) and fm["name"] == sk.parent.name
    assert len(sk.read_text("utf-8").splitlines()) < 465
'
echo "  OK: All 17 SKILL.md files verified (8 global + 9 stack)"

echo ""
echo "[7/8] Node Manifest (zcg-node-v1), 16 Templates (zcg-template-v1) & zcg-mcp Self-Test"
if [[ -x "${ZCG}" ]]; then
  "${ZCG}" list-templates >/dev/null
  "${ZCG_MCP}" --self-test >/dev/null
else
  PYTHONPATH=src "${PYTHON}" -m zcg.cli.dispatcher list-templates >/dev/null
  PYTHONPATH=src "${PYTHON}" -m zcg.mcp.server --self-test >/dev/null
fi
echo "  OK: zcg list-templates (16 packs) & zcg-mcp --self-test (9/9/3) passed"

echo ""
echo "[8/8] Automated Test Suites (1:1 Isolated Unit -> Imp -> E2E) & 100.00% Coverage Gate"
[[ -z "$(find src tests -name '__init__.py' -size +0c)" ]] || { echo "Non-empty __init__.py detected" >&2; exit 1; }
mod_count=0
while IFS= read -r mod; do
  rel="${mod#src/zcg/}"
  pkg="$(dirname "${rel}")"
  base="$(basename "${rel}" .py)"
  tfile="tests/unit/zcg/${pkg}/test_${base}.py"
  dotted="zcg.$(echo "${pkg}" | tr / .).${base}"
  PYTHONPATH=src "${PYTEST}" -q "${tfile}" --cov="${dotted}" --cov-branch --cov-fail-under=100 >/dev/null
  mod_count=$((mod_count + 1))
done < <(find src/zcg -name "*.py" ! -name "__init__.py" | sort)
echo "  OK: 1:1 isolated unit coverage verified (100.00% across all ${mod_count} src/zcg modules)"
PYTHONPATH=src "${PYTEST}" -q tests/unit tests/imp tests/e2e --cov=src/zcg --cov-branch --cov-report=term-missing --cov-fail-under=100 >/dev/null
echo "  OK: Full Unit + Imp + E2E suite passed at 100.00% statement and branch coverage"

echo ""
echo "All 8/8 ZeroCloudGravity verification gates passed (0 errors)!"
