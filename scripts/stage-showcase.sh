#!/usr/bin/env bash
# ZeroCloudGravity (v1.2.0) — Ephemeral Live [CAP-01..CAP-14] Showcase, TLS 1.3 & /mcp Stager
# Usage: ./scripts/stage-showcase.sh [--dir <path>] [--base-port <port>] [--https-demo] [--status] [--stop] [--dry-run] [--help]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SHOWCASE_DIR="${ZCG_SHOWCASE_DIR:-/tmp/zcg-showcase}"
SHOWCASE_BASE_PORT="${ZCG_SHOWCASE_BASE_PORT:-9700}"
PYTHON_BIN="${REPO_DIR}/.venv/bin/python"
[[ -x "${PYTHON_BIN}" ]] || PYTHON_BIN="python3"

ACTION="stage"
DRY_RUN=0
HTTPS_DEMO=0

usage() {
  cat <<'EOF'
Usage: ./scripts/stage-showcase.sh [--dir <path>] [--base-port <port>] [--https-demo] [--status] [--stop] [--dry-run] [--help]

Provisions all ISO-neutral [CAP-01..CAP-14] ZeroCloudGravity reference topologies (including
R3 persona-wallet, R0 pub-persona Download CV, and R2 dept-finance-supply) in an ephemeral directory
outside the repository and launches live Native Python 3.14 ASGI daemons on isolated ports
(base_port + precedence, default 9700..9799) plus optional TLS 1.3 HTTPS and Streamable HTTP /mcp.

Options:
  --dir <path>         Target ephemeral showcase root (default: /tmp/zcg-showcase)
  --base-port <port>   Base port offset for showcase daemons (default: 9700)
  --https-demo         Also launch an ephemeral ECDSA TLS 1.3 HTTPS portal & Streamable HTTP /mcp
  --status             Inspect active showcase ports, daemon PIDs, and /healthz status
  --stop               Stop all running showcase ASGI daemons and remove <dir>
  -n, --dry-run        Print the showcase staging matrix without modifying disk
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
    --https-demo) HTTPS_DEMO=1; shift ;;
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
  local p00=$((SHOWCASE_BASE_PORT))
  local p90=$((SHOWCASE_BASE_PORT + 90))
  local p85=$((SHOWCASE_BASE_PORT + 85))
  local p86=$((SHOWCASE_BASE_PORT + 86))
  local p20=$((SHOWCASE_BASE_PORT + 20))
  local p10=$((SHOWCASE_BASE_PORT + 10))
  local p11=$((SHOWCASE_BASE_PORT + 11))
  local p05=$((SHOWCASE_BASE_PORT + 5))
  local p87=$((SHOWCASE_BASE_PORT + 87))
  local p21=$((SHOWCASE_BASE_PORT + 21))
  local p88=$((SHOWCASE_BASE_PORT + 88))
  local p22=$((SHOWCASE_BASE_PORT + 22))
  local p31=$((SHOWCASE_BASE_PORT + 31))
  local p43=$((SHOWCASE_BASE_PORT + 43))
  local p40=$((SHOWCASE_BASE_PORT + 40))
  cat <<EOF
=== ZeroCloudGravity Live Showcase Matrix (root: ${SHOWCASE_DIR}, base_port: ${SHOWCASE_BASE_PORT}) ===
  [CAP-01] Individual Root 0 Workstation   -> http://dev.persona-profile.localhost:${p90}/dashboard
  [CAP-02] School Student Study Cockpit    -> http://dev.persona-tutor-school.persona-profile.localhost:${p85}/dashboard
  [CAP-03] University Specialty Studio     -> http://dev.persona-tutor.persona-profile.localhost:${p86}/dashboard
  [CAP-04] Scientific Knowledge Portal     -> http://dev.sci-physics.localhost:${p20}/dashboard
  [CAP-05] Small Startup Compact Hub       -> http://dev.nova.localhost:${p10}/dashboard
  [CAP-06] Medium Scaleup Departmental Hub -> http://dev.alpha.localhost:${p11}/dashboard
  [CAP-07] Regulated Enterprise SecOps     -> http://pro.dept-secops.titan.localhost:${p05}/dashboard
  [CAP-08] Panoramic Mesh Synthesis        -> :${p90} + :${p86} + :${p20} + :${p11} (simultaneous live mesh)
  [CAP-09] Personal Work & Spin-Off Studio -> http://dev.persona-work.persona-profile.localhost:${p87}/dashboard
  [CAP-10] Public Corporate Pro Portal     -> http://org-alpha.localhost:${p21}/dashboard
  [CAP-11] Personal R3 Sovereign Wallet    -> http://dev.persona-wallet.persona-profile.localhost:${p88}/dashboard
  [CAP-12] Personal Public Portfolio & CV  -> http://pub-persona.localhost:${p22}/portal?format=html
  [CAP-13] Corporate R2 Finance Treasury   -> http://dev.dept-finance-supply.alpha.localhost:${p31}/dashboard
  [CAP-14] OSS Platform Flagship Portal    -> http://zcg-flagship.localhost:${p00}/portal?format=html
EOF
  if [[ "${HTTPS_DEMO}" -eq 1 ]]; then
    cat <<EOF
  [TLS-13] Native OpenSSL 3 HTTPS Portal   -> https://localhost:${p43}/portal?format=html
  [MCP-HT] Streamable HTTP /mcp Endpoint   -> http://127.0.0.1:${p40}/mcp
EOF
  fi
}

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[dry-run] Would stage 13 live ASGI nodes covering [CAP-01..CAP-14] (https_demo=${HTTPS_DEMO}) in ${SHOWCASE_DIR}"
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
import ssl
import sys
import urllib.request
from pathlib import Path

root = Path(sys.argv[1]).resolve()
unverified = ssl._create_unverified_context()
print(f"=== Showcase Runtime Status ({root}) ===")
for rt_file in sorted(root.rglob(".agents/runtime/*.json")):
    doc = json.loads(rt_file.read_text("utf-8"))
    ws_name = doc.get("label") or rt_file.parents[2].name
    port = int((doc.get("intranet_topology") or {}).get("port") or 0)
    scheme = str(doc.get("scheme") or "http")
    probe_path = str(doc.get("probe_path") or "/healthz")
    pid = doc.get("daemon_pid")
    alive = "STOPPED"
    if port:
        try:
            ctx = unverified if scheme == "https" else None
            with urllib.request.urlopen(
                f"{scheme}://127.0.0.1:{port}{probe_path}", timeout=1.0, context=ctx
            ) as resp:
                alive = "HEALTHY" if resp.status in (200, 400, 405) else f"HTTP_{resp.status}"
        except OSError:
            alive = "UNREACHABLE"
    print(f"  - {ws_name:<22} port={port:<5} pid={str(pid):<8} status={alive}")
PY
  exit 0
fi

if [[ -d "${SHOWCASE_DIR}" ]]; then
  stop_showcase >/dev/null
fi
mkdir -p "${SHOWCASE_DIR}"

ZCG_LOCAL_QA_SWITCH=1 ZCG_NO_BROWSER=1 PYTHONPATH="${REPO_DIR}/src" "${PYTHON_BIN}" - "${REPO_DIR}" "${SHOWCASE_DIR}" "${SHOWCASE_BASE_PORT}" "${HTTPS_DEMO}" <<'PY'
import json
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from zcg.cockpit.ops.lifecycle import manage_plugin_service
from zcg.governance.workspace.bootstrap import bootstrap_node_workspace
from zcg.governance.workspace.links import link_node

engine_dir = Path(sys.argv[1]).resolve()
stage_root = Path(sys.argv[2]).resolve()
base_port = int(sys.argv[3])
https_demo = int(sys.argv[4]) == 1

SCENARIOS = [
    ("persona-profile", "workstation", 90, base_port + 90, "individual", "dev", "universal-base,workstation-control-tower", {"enabled_modules": ["node_mesh", "spatial_atlas", "tool_stack", "telemetry", "work_ledger", "vault"]}),
    ("persona-tutor-school", "squad", 85, base_port + 85, "individual", "dev", "academic-base,tutor-study-cockpit", {"academic_stage": "school", "governing_root_id": "persona-profile", "base_domain": "persona-profile.personal.local"}),
    ("persona-tutor", "squad", 86, base_port + 86, "individual", "dev", "academic-base,science-base,tutor-study-cockpit", {"academic_stage": "university", "governing_root_id": "persona-profile", "base_domain": "persona-profile.personal.local"}),
    ("sci-physics", "knowledge", 20, base_port + 20, "open-source", "dev", "science-base,scientific-methodology,spatial-simulation,knowledge-stewardship-portal", {"visibility": "public", "knowledge_domain": "scientific-epistemic", "enabled_modules": ["spatial_atlas", "data_pipeline", "crud", "vault", "node_mesh"]}),
    ("corp-nova-root", "corporate", 10, base_port + 10, "enterprise", "dev", "business-base,corporate-root-hub", {"governing_root_id": "corp-nova-root"}),
    ("corp-alpha-root", "corporate", 11, base_port + 11, "enterprise", "dev", "business-base,software-engineering,corporate-root-hub", {"governing_root_id": "corp-alpha-root", "enabled_modules": ["node_mesh", "spatial_atlas", "work_ledger", "crud", "vault", "data_pipeline"]}),
    ("dept-secops", "domain-policy", 5, base_port + 5, "enterprise", "pro", "business-base,nist-csf-security,secops-mcp-guardian", {"governing_root_id": "corp-titan-root", "base_domain": "titan.intranet.local", "enabled_modules": ["telemetry", "spatial_atlas", "tool_stack", "node_mesh", "work_ledger"]}),
    ("persona-work", "squad", 87, base_port + 87, "individual", "dev", "business-base,software-engineering,node-work-cockpit", {"governing_root_id": "persona-profile", "base_domain": "persona-profile.personal.local"}),
    ("org-alpha", "knowledge", 21, base_port + 21, "enterprise", "pro", "business-base,scientific-methodology,knowledge-stewardship-portal", {"visibility": "public", "governing_root_id": "corp-alpha-root", "use_case_overlay": "alpha-public-portal", "domain_governance": {"canonical_domain": "corp-alpha.example.com", "intranet_zone": "corp-alpha.example.net"}, "surface_access": {"default_ring": "R0", "loopback_operator_bypass": False}}),
    ("persona-wallet", "squad", 88, base_port + 88, "individual", "dev", "science-base,sovereign-wallet-cockpit", {"governing_root_id": "persona-profile", "base_domain": "persona-profile.personal.local"}),
    ("pub-persona", "knowledge", 22, base_port + 22, "individual", "pro", "universal-base,knowledge-stewardship-portal", {"visibility": "public", "domain_governance": {"canonical_domain": "persona.example.org"}, "surface_access": {"default_ring": "R0", "loopback_operator_bypass": False}}),
    ("dept-finance-supply", "department", 31, base_port + 31, "enterprise", "dev", "business-base,corporate-operations,sovereign-wallet-cockpit", {"governing_root_id": "corp-alpha-root", "base_domain": "alpha.intranet.local", "enabled_modules": ["wallet_treasury", "spatial_atlas", "work_ledger", "crud", "vault", "telemetry"], "surface_access": {"default_ring": "R0", "loopback_operator_bypass": False, "route_rules": [{"path_pattern": "/api/modules/wallet-treasury*", "ring": "R2", "required_groups": ["dept-finance"]}]}}),
    ("zcg-flagship", "knowledge", 19, base_port, "open-source", "pro", "science-base,spatial-simulation,knowledge-stewardship-portal", {"visibility": "public", "domain_governance": {"canonical_domain": "zerocloudgravity.org", "developer_domain": "zerocloudgravity.dev"}, "enabled_modules": ["spatial_atlas", "wallet_treasury", "tool_stack", "node_mesh", "telemetry"], "surface_access": {"default_ring": "R0", "loopback_operator_bypass": False}}),
]

iso_home = stage_root / ".isolated-home"
for nid, role, prec, port, ekind, env, tpls, extra in SCENARIOS:
    ws = stage_root / nid
    m_path = ws / "system/zcg-node.json"
    m_path.parent.mkdir(parents=True, exist_ok=True)
    m_path.write_text(json.dumps({"cockpit_port": port, **extra}, indent=2) + "\n", encoding="utf-8")
    bootstrap_node_workspace(
        engine_dir, ws, layer_id=nid, layer_role=role, precedence=prec,
        templates=tpls.split(","), entity_kind=ekind, home_dir=iso_home,
    )
    m_doc = {**json.loads(m_path.read_text("utf-8")), "cockpit_port": port, "entity_kind": ekind, **extra}
    if nid == "corp-alpha-root":
        child_dir = ws / "layers/dept-platform"
        child_m = child_dir / "system/zcg-node.json"
        child_m.parent.mkdir(parents=True, exist_ok=True)
        child_m.write_text(json.dumps({"cockpit_port": base_port + 30}, indent=2) + "\n", encoding="utf-8")
        bootstrap_node_workspace(
            engine_dir, child_dir, layer_id="dept-platform", layer_role="department",
            precedence=30, templates=["business-base", "software-engineering", "node-work-cockpit"],
            parent_dir=ws, home_dir=iso_home,
        )
        m_doc["mounted_layers"] = [{"name": "dept-platform", "relative_path": "layers/dept-platform"}]
    if env == "pro":
        (ws / "CHANGELOG.md").write_text("# Changelog\n\n## [1.0.0] - 2026-11-14\n- Initial production baseline.\n", encoding="utf-8")
        (ws / "WORKVALI.md").write_text("# Validation\n\n- [x] Verified.\n", encoding="utf-8")
    rm_p, wt_p = ws / "README.md", ws / "WORKTASK.md"
    if rm_p.is_file():
        rm_p.write_text(rm_p.read_text("utf-8").replace("[Fill:", "Configured:"), encoding="utf-8")
    if wt_p.is_file():
        wt_p.write_text(
            wt_p.read_text("utf-8").replace("- [ ] Complete `Layer Setup Blueprint`", "- [x] Complete `Layer Setup Blueprint`"),
            encoding="utf-8",
        )
    m_path.write_text(json.dumps(m_doc, indent=2) + "\n", encoding="utf-8")

link_node(stage_root / "persona-profile", target_id="persona-tutor", relation="lateral-peer", target_ref=str(stage_root / "persona-tutor"), cockpit_url=f"http://dev.persona-tutor.persona-profile.localhost:{base_port + 86}")
link_node(stage_root / "persona-profile", target_id="persona-work", relation="spinout-project", target_ref=str(stage_root / "persona-work"), cockpit_url=f"http://dev.persona-work.persona-profile.localhost:{base_port + 87}")
link_node(stage_root / "persona-profile", target_id="sci-physics", relation="knowledge-feed", target_ref=str(stage_root / "sci-physics"), cockpit_url=f"http://dev.sci-physics.localhost:{base_port + 20}")
link_node(stage_root / "persona-work", target_id="corp-alpha-root", relation="b2b-collaboration", target_ref=str(stage_root / "corp-alpha-root"), cockpit_url=f"http://dev.alpha.localhost:{base_port + 11}")
link_node(stage_root / "persona-wallet", target_id="sci-physics", relation="knowledge-feed", target_ref=str(stage_root / "sci-physics"), cockpit_url="")

ports: list[tuple[str, int, str, str]] = []
for nid, _role, _prec, port, _ekind, env, _tpls, _extra in SCENARIOS:
    ws = stage_root / nid
    manage_plugin_service(ws, action="restart", target_env=env, engine_dir=engine_dir)
    ports.append((nid, port, "http", "/healthz"))

if https_demo:
    tls_dir = stage_root / ".tls"
    tls_dir.mkdir(parents=True, exist_ok=True)
    cert_f, key_f = tls_dir / "localhost.crt", tls_dir / "localhost.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "ec",
            "-pkeyopt", "ec_paramgen_curve:prime256v1", "-days", "1", "-nodes",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout", str(key_f), "-out", str(cert_f),
        ],
        check=True, capture_output=True,
    )
    aux_rt = stage_root / ".aux/.agents/runtime"
    aux_rt.mkdir(parents=True, exist_ok=True)
    sub_env = {"PYTHONPATH": str(engine_dir / "src"), "ZCG_NO_BROWSER": "1", "ZCG_LOCAL_QA_SWITCH": "1", "PATH": "/usr/bin:/bin"}
    tls_port, mcp_port = base_port + 43, base_port + 40
    p_tls = subprocess.Popen(
        [
            sys.executable, "-m", "zcg.cockpit.ops.asgi", "--workspace", str(stage_root / "org-alpha"),
            "--host", "127.0.0.1", "--port", str(tls_port),
            "--tls-certfile", str(cert_f), "--tls-keyfile", str(key_f),
        ],
        env=sub_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    (aux_rt / "https-demo.json").write_text(
        json.dumps({"label": "https-tls13-demo", "daemon_pid": p_tls.pid, "scheme": "https", "intranet_topology": {"port": tls_port}}),
        encoding="utf-8",
    )
    ports.append(("https-tls13-demo", tls_port, "https", "/healthz"))
    mcp_logs = stage_root / ".mcp-logs"
    mcp_logs.mkdir(parents=True, exist_ok=True)
    p_mcp = subprocess.Popen(
        [
            sys.executable, "-m", "zcg.mcp.server", "--repo-dir", str(engine_dir),
            "--log-dir", str(mcp_logs), "--http-host", "127.0.0.1", "--http-port", str(mcp_port),
        ],
        env=sub_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    (aux_rt / "mcp-http.json").write_text(
        json.dumps({"label": "mcp-streamable-http", "daemon_pid": p_mcp.pid, "scheme": "http", "probe_path": "/healthz", "intranet_topology": {"port": mcp_port}}),
        encoding="utf-8",
    )
    ports.append(("mcp-streamable-http", mcp_port, "http", "/healthz"))

unverified = ssl._create_unverified_context()
deadline = time.monotonic() + 10.0
for nid, port, scheme, probe in ports:
    ok = False
    while time.monotonic() < deadline:
        try:
            ctx = unverified if scheme == "https" else None
            with urllib.request.urlopen(f"{scheme}://127.0.0.1:{port}{probe}", timeout=0.5, context=ctx) as resp:
                if resp.status == 200:
                    ok = True
                    break
        except OSError:
            time.sleep(0.15)
    if not ok:
        raise RuntimeError(f"Showcase node {nid} failed to respond on {scheme}://127.0.0.1:{port}{probe}")
PY

print_catalog
echo ""
echo "All showcase ASGI daemons are LIVE. Open the URLs above in your browser to validate & capture screenshots."
echo "Run 'zcg stage-showcase --stop' when finished to terminate daemons and clean ${SHOWCASE_DIR}."
