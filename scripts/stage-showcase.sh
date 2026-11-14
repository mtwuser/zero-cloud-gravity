#!/usr/bin/env bash
# ZeroCloudGravity (v1.1.0) — Ephemeral Live [CAP-01..CAP-10] Showcase Scenario Stager
# Usage: ./scripts/stage-showcase.sh [--dir <path>] [--status] [--stop] [--dry-run] [--help]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SHOWCASE_DIR="${ZCG_SHOWCASE_DIR:-/tmp/zcg-showcase}"
SHOWCASE_BASE_PORT="${ZCG_SHOWCASE_BASE_PORT:-9700}"
PYTHON_BIN="${REPO_DIR}/.venv/bin/python"
[[ -x "${PYTHON_BIN}" ]] || PYTHON_BIN="python3"

ACTION="stage"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./scripts/stage-showcase.sh [--dir <path>] [--base-port <port>] [--status] [--stop] [--dry-run] [--help]

Provisions all 10 ISO-neutral [CAP-01..CAP-10] ZeroCloudGravity reference topologies in an
ephemeral directory outside the repository and launches live Native Python 3.14 ASGI daemons
on isolated ports (base_port + precedence, default 9700..9799) for interactive browser
inspection and authentic manual screenshot capture without colliding with active 87xx nodes.

Options:
  --dir <path>         Target ephemeral showcase root (default: /tmp/zcg-showcase)
  --base-port <port>   Base port offset for showcase daemons (default: 9700)
  --status             Inspect active showcase ports, daemon PIDs, and /healthz status
  --stop               Stop all running showcase ASGI daemons and remove <dir>
  -n, --dry-run        Print the 10-capture [CAP-01..CAP-10] staging matrix without modifying disk
  -h, --help           Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      [[ $# -ge 2 ]] || { echo "Error: --dir requires a directory path." >&2; exit 1; }
      SHOWCASE_DIR="$2"
      shift 2
      ;;
    --dir=*)
      SHOWCASE_DIR="${1#--dir=}"
      shift
      ;;
    --base-port)
      [[ $# -ge 2 ]] || { echo "Error: --base-port requires a numeric port." >&2; exit 1; }
      SHOWCASE_BASE_PORT="$2"
      shift 2
      ;;
    --base-port=*)
      SHOWCASE_BASE_PORT="${1#--base-port=}"
      shift
      ;;
    --status) ACTION="status"; shift ;;
    --stop) ACTION="stop"; shift ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Error: Unknown option '$1'." >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! [[ "${SHOWCASE_BASE_PORT}" =~ ^[0-9]+$ ]] || (( SHOWCASE_BASE_PORT < 1024 || SHOWCASE_BASE_PORT > 65000 )); then
  echo "Error: --base-port '${SHOWCASE_BASE_PORT}' must be an integer between 1024 and 65000." >&2
  exit 1
fi

print_catalog() {
  local p90=$((SHOWCASE_BASE_PORT + 90))
  local p85=$((SHOWCASE_BASE_PORT + 85))
  local p86=$((SHOWCASE_BASE_PORT + 86))
  local p20=$((SHOWCASE_BASE_PORT + 20))
  local p10=$((SHOWCASE_BASE_PORT + 10))
  local p11=$((SHOWCASE_BASE_PORT + 11))
  local p05=$((SHOWCASE_BASE_PORT + 5))
  local p87=$((SHOWCASE_BASE_PORT + 87))
  local p21=$((SHOWCASE_BASE_PORT + 21))
  cat <<EOF
=== ZeroCloudGravity Live Showcase Matrix (root: ${SHOWCASE_DIR}, base_port: ${SHOWCASE_BASE_PORT}) ===
  [CAP-01] Individual Root 0 Workstation   -> http://dev.alex-pc.localhost:${p90}/dashboard
  [CAP-02] School Student Study Cockpit    -> http://dev.alex-tutor-school.alex-pc.localhost:${p85}/dashboard
  [CAP-03] University Specialty Studio     -> http://dev.alex-tutor.alex-pc.localhost:${p86}/dashboard
  [CAP-04] Scientific Knowledge Portal     -> http://dev.sci-physics.localhost:${p20}/dashboard
  [CAP-05] Small Startup Compact Hub       -> http://dev.nova.localhost:${p10}/dashboard
  [CAP-06] Medium Scaleup Departmental Hub -> http://dev.alpha.localhost:${p11}/dashboard
  [CAP-07] Regulated Enterprise SecOps     -> http://pro.dept-secops.titan.localhost:${p05}/dashboard
  [CAP-08] Panoramic Mesh Synthesis        -> :${p90} + :${p86} + :${p20} + :${p11} (simultaneous live mesh)
  [CAP-09] Personal Work & Spin-Off Studio -> http://dev.alex-work.alex-pc.localhost:${p87}/dashboard
  [CAP-10] Public Corporate Pro Portal     -> http://org-alpha.localhost:${p21}/dashboard
EOF
}

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[dry-run] Would stage 9 live ASGI nodes covering [CAP-01..CAP-10] in ${SHOWCASE_DIR}"
  print_catalog
  exit 0
fi

stop_showcase() {
  if [[ ! -d "${SHOWCASE_DIR}" ]]; then
    echo "Showcase directory ${SHOWCASE_DIR} is not staged (nothing to stop)."
    return 0
  fi
  PYTHONPATH="${REPO_DIR}/src" "${PYTHON_BIN}" - "${SHOWCASE_DIR}" <<'PY'
import json
import os
import signal
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
stopped = 0
for rt_file in sorted(root.rglob(".agents/runtime/*.json")):
    try:
        pid = json.loads(rt_file.read_text("utf-8")).get("daemon_pid")
        if isinstance(pid, int) and pid > 0:
            os.kill(pid, signal.SIGTERM)
            stopped += 1
    except (OSError, ValueError, json.JSONDecodeError):
        pass
print(f"Stopped {stopped} showcase ASGI daemon(s) under {root}.")
PY
  rm -rf "${SHOWCASE_DIR}"
  echo "Removed ephemeral showcase directory ${SHOWCASE_DIR}."
}

if [[ "${ACTION}" == "stop" ]]; then
  stop_showcase
  exit 0
fi

if [[ "${ACTION}" == "status" ]]; then
  if [[ ! -d "${SHOWCASE_DIR}" ]]; then
    echo "Showcase directory ${SHOWCASE_DIR} is not staged."
    exit 0
  fi
  PYTHONPATH="${REPO_DIR}/src" "${PYTHON_BIN}" - "${SHOWCASE_DIR}" <<'PY'
import json
import sys
import urllib.request
from pathlib import Path

root = Path(sys.argv[1]).resolve()
print(f"=== Showcase Runtime Status ({root}) ===")
for rt_file in sorted(root.rglob(".agents/runtime/*.json")):
    doc = json.loads(rt_file.read_text("utf-8"))
    ws_name = rt_file.parents[2].name
    port = int((doc.get("intranet_topology") or {}).get("port") or 0)
    pid = doc.get("daemon_pid")
    alive = "STOPPED"
    if port:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1.0) as resp:
                alive = "HEALTHY" if resp.status == 200 else f"HTTP_{resp.status}"
        except OSError:
            alive = "UNREACHABLE"
    print(f"  - {ws_name:<20} port={port:<5} pid={str(pid):<8} status={alive}")
PY
  exit 0
fi

if [[ -d "${SHOWCASE_DIR}" ]]; then
  stop_showcase >/dev/null
fi
mkdir -p "${SHOWCASE_DIR}"

ZCG_NO_BROWSER=1 PYTHONPATH="${REPO_DIR}/src" "${PYTHON_BIN}" - "${REPO_DIR}" "${SHOWCASE_DIR}" "${SHOWCASE_BASE_PORT}" <<'PY'
import json
import sys
import time
import urllib.request
from pathlib import Path

from zcg.cockpit.lifecycle import manage_plugin_service
from zcg.governance.bootstrap import bootstrap_node_workspace
from zcg.governance.links import link_node

engine_dir = Path(sys.argv[1]).resolve()
stage_root = Path(sys.argv[2]).resolve()
base_port = int(sys.argv[3])

SCENARIOS = [
    ("alex-pc", "workstation", 90, base_port + 90, "individual", "dev", "universal-base,workstation-control-tower", {}),
    ("alex-tutor-school", "squad", 85, base_port + 85, "individual", "dev", "academic-base,tutor-study-cockpit", {"academic_stage": "school", "governing_root_id": "alex-pc", "base_domain": "alex-pc.personal.local"}),
    ("alex-tutor", "squad", 86, base_port + 86, "individual", "dev", "academic-base,science-base,tutor-study-cockpit", {"academic_stage": "university", "governing_root_id": "alex-pc", "base_domain": "alex-pc.personal.local"}),
    ("sci-physics", "knowledge", 20, base_port + 20, "open-source", "dev", "science-base,scientific-methodology,knowledge-stewardship-portal", {"visibility": "public", "knowledge_domain": "scientific-epistemic"}),
    ("corp-nova-root", "corporate", 10, base_port + 10, "enterprise", "dev", "business-base,corporate-root-hub", {"governing_root_id": "corp-nova-root"}),
    ("corp-alpha-root", "corporate", 11, base_port + 11, "enterprise", "dev", "business-base,software-engineering,corporate-root-hub", {"governing_root_id": "corp-alpha-root"}),
    ("dept-secops", "domain-policy", 5, base_port + 5, "enterprise", "pro", "business-base,nist-csf-security,secops-mcp-guardian", {"governing_root_id": "corp-titan-root", "base_domain": "titan.intranet.local"}),
    ("alex-work", "squad", 87, base_port + 87, "individual", "dev", "business-base,software-engineering,node-work-cockpit", {"governing_root_id": "alex-pc", "base_domain": "alex-pc.personal.local"}),
    ("org-alpha", "knowledge", 21, base_port + 21, "enterprise", "pro", "business-base,scientific-methodology,knowledge-stewardship-portal", {"visibility": "public", "governing_root_id": "corp-alpha-root", "use_case_overlay": "alpha-public-portal"}),
]

iso_home = stage_root / ".isolated-home"
for nid, role, prec, port, ekind, env, tpls, extra in SCENARIOS:
    ws = stage_root / nid
    m_path = ws / "system/zcg-node.json"
    m_path.parent.mkdir(parents=True, exist_ok=True)
    m_path.write_text(json.dumps({"cockpit_port": port, **extra}, indent=2) + "\n", encoding="utf-8")
    bootstrap_node_workspace(
        engine_dir,
        ws,
        layer_id=nid,
        layer_role=role,
        precedence=prec,
        templates=tpls.split(","),
        entity_kind=ekind,
        home_dir=iso_home,
    )
    m_doc = {
        **json.loads(m_path.read_text("utf-8")),
        "cockpit_port": port,
        "entity_kind": ekind,
        **extra,
    }
    if nid == "corp-alpha-root":
        child_dir = ws / "layers/dept-platform"
        child_m = child_dir / "system/zcg-node.json"
        child_m.parent.mkdir(parents=True, exist_ok=True)
        child_m.write_text(json.dumps({"cockpit_port": base_port + 30}, indent=2) + "\n", encoding="utf-8")
        bootstrap_node_workspace(
            engine_dir,
            child_dir,
            layer_id="dept-platform",
            layer_role="department",
            precedence=30,
            templates=["business-base", "software-engineering", "node-work-cockpit"],
            parent_dir=ws,
            home_dir=iso_home,
        )
        m_doc["mounted_layers"] = [{"name": "dept-platform", "relative_path": "layers/dept-platform"}]
    if env == "pro":
        (ws / "CHANGELOG.md").write_text("# Changelog\n\n## [1.0.0] - 2026-11-14\n- Initial production baseline.\n", encoding="utf-8")
        (ws / "WORKVALI.md").write_text("# Validation\n\n- [x] Verified.\n", encoding="utf-8")
    m_path.write_text(json.dumps(m_doc, indent=2) + "\n", encoding="utf-8")

link_node(stage_root / "alex-pc", target_id="alex-tutor", relation="lateral-peer", target_ref=str(stage_root / "alex-tutor"), cockpit_url=f"http://dev.alex-tutor.alex-pc.localhost:{base_port + 86}")
link_node(stage_root / "alex-pc", target_id="alex-work", relation="spinout-project", target_ref=str(stage_root / "alex-work"), cockpit_url=f"http://dev.alex-work.alex-pc.localhost:{base_port + 87}")
link_node(stage_root / "alex-pc", target_id="sci-physics", relation="knowledge-feed", target_ref=str(stage_root / "sci-physics"), cockpit_url=f"http://dev.sci-physics.localhost:{base_port + 20}")
link_node(stage_root / "alex-work", target_id="corp-alpha-root", relation="b2b-collaboration", target_ref=str(stage_root / "corp-alpha-root"), cockpit_url=f"http://dev.alpha.localhost:{base_port + 11}")

ports = []
for nid, _role, _prec, port, _ekind, env, _tpls, _extra in SCENARIOS:
    ws = stage_root / nid
    manage_plugin_service(ws, action="restart", target_env=env, engine_dir=engine_dir)
    ports.append((nid, port))

deadline = time.monotonic() + 8.0
for nid, port in ports:
    ok = False
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.5) as resp:
                if resp.status == 200:
                    ok = True
                    break
        except OSError:
            time.sleep(0.15)
    if not ok:
        raise RuntimeError(f"Showcase node {nid} failed to respond on port {port}")
PY

print_catalog
echo ""
echo "All 9 showcase ASGI daemons are LIVE. Open the URLs above in your browser to capture screenshots."
echo "Run 'zcg stage-showcase --stop' when finished to terminate daemons and clean ${SHOWCASE_DIR}."
