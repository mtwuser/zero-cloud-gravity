#!/usr/bin/env bash
# ZeroCloudGravity (v1.0.1) — Unified Workstation & Engine Runtime Synchronizer
# Usage: ./scripts/workstation-sync.sh [sync | setup | status | --auto | --help | --version]

set -euo pipefail
export LC_ALL=C

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION_STR="$(tr -d '[:space:]' < "${REPO_DIR}/VERSION" 2>/dev/null || echo "unknown")"

CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/zero-cloud-gravity"
CONFIG_FILE="${ZCG_WORKSTATION_CONF:-${CONFIG_DIR}/workstation.conf}"
STAMP_DIR="${XDG_RUNTIME_DIR:-/tmp}"
USER_UID="${UID:-$(id -u)}"
STAMP_FILE="${ZCG_SYNC_STAMP:-${STAMP_DIR}/zero-cloud-gravity-${USER_UID}.synced}"

ZCG_RUNTIME_DIR="${ZCG_RUNTIME_DIR:-}"
ZCG_WORKSTATION_DIR="${ZCG_WORKSTATION_DIR:-}"
ZCG_DEV_REPO_DIR="${ZCG_DEV_REPO_DIR:-}"
ZCG_GLOBAL_PROFILE="${ZCG_GLOBAL_PROFILE:-universal-base}"
ZCG_INTERACTION_LANG="${ZCG_INTERACTION_LANG:-en}"
ZCG_AUTO_SYNC="${ZCG_AUTO_SYNC:-boot}"
ZCG_NO_BROWSER="${ZCG_NO_BROWSER:-0}"

if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck disable=SC1090
  . "${CONFIG_FILE}"
fi

usage() {
  cat <<'EOF'
Usage: ./scripts/workstation-sync.sh [COMMAND] [OPTIONS]

Commands:
  sync, --sync               Synchronize engine runtime, personal Root 0 workstation, profile, and Stow links (default)
  setup, --setup             Persist ~/.config/zero-cloud-gravity/workstation.conf and run synchronization
  status, --status           Print workstation and engine runtime status as JSON
  --auto                     Boot-throttled quiet synchronization invoked from ~/.bashrc
  -v, --version              Show ZeroCloudGravity version
  -h, --help                 Show this help message

Options:
  --profile <name>           Global AGENTS.md profile: universal-base|academic-base|science-base|business-base|academic|science|technical|business|full
  --lang <code>              Interaction language: en|es|it|fr|de|pt
  --workstation-dir <path>   Personal Root 0 workstation node path (e.g. ~/<persona>-pc)
  --dev-repo <path>          Local engine development clone path (e.g. ~/Projects/dev-zero-cloud-gravity)
  --auto-sync <mode>         Shell startup sync policy: boot|always|off (default: boot)
  --no-browser               Suppress automatic browser launches (sets ZCG_NO_BROWSER=1)
  --no-sync                  Write workstation.conf during setup without running synchronization
  --dry-run                  Preview synchronization without modifying $HOME or repository state
EOF
}

resolve_runtime_dir() {
  if [[ -n "${ZCG_RUNTIME_DIR}" ]] && [[ -d "${ZCG_RUNTIME_DIR}" ]]; then
    (cd "${ZCG_RUNTIME_DIR}" && pwd)
    return
  fi
  echo "${REPO_DIR}"
}

detect_dev_repo() {
  if [[ -n "${ZCG_DEV_REPO_DIR}" ]] && [[ -f "${ZCG_DEV_REPO_DIR}/system/zcg-node.json" ]]; then
    (cd "${ZCG_DEV_REPO_DIR}" && pwd)
    return
  fi
  local candidate="${HOME}/Projects/dev-zero-cloud-gravity"
  if [[ -f "${candidate}/system/zcg-node.json" ]]; then
    (cd "${candidate}" && pwd)
    return
  fi
  echo ""
}

detect_workstation_dir() {
  if [[ -n "${ZCG_WORKSTATION_DIR}" ]] && [[ -f "${ZCG_WORKSTATION_DIR}/system/zcg-node.json" ]]; then
    (cd "${ZCG_WORKSTATION_DIR}" && pwd)
    return
  fi
  local candidate
  for candidate in "${HOME}"/*-pc; do
    if [[ -f "${candidate}/system/zcg-node.json" ]]; then
      (cd "${candidate}" && pwd)
      return
    fi
  done
  echo ""
}

RUNTIME_DIR="$(resolve_runtime_dir)"
DEV_DIR="$(detect_dev_repo)"
WS_DIR="$(detect_workstation_dir)"

run_zcg() {
  local venv_zcg="${RUNTIME_DIR}/.venv/bin/zcg"
  if [[ -x "${venv_zcg}" ]]; then
    "${venv_zcg}" "$@"
  else
    PYTHONPATH="${RUNTIME_DIR}/src" python3 -c "import sys; from zcg.cli.dispatcher import main; raise SystemExit(main(sys.argv[1:]))" "$@"
  fi
}

write_workstation_conf() {
  mkdir -p "${CONFIG_DIR}"
  cat >"${CONFIG_FILE}" <<EOF
# Declarative Workstation Configuration for ZeroCloudGravity
export ZCG_RUNTIME_DIR="${RUNTIME_DIR}"
export ZCG_WORKSTATION_DIR="${WS_DIR}"
export ZCG_DEV_REPO_DIR="${DEV_DIR}"
export ZCG_GLOBAL_PROFILE="${ZCG_GLOBAL_PROFILE}"
export ZCG_INTERACTION_LANG="${ZCG_INTERACTION_LANG}"
export ZCG_AUTO_SYNC="${ZCG_AUTO_SYNC}"
export ZCG_NO_BROWSER="${ZCG_NO_BROWSER}"
EOF
}

run_sync() {
  local quiet_unchanged="${1:-0}" dry_run="${2:-0}" old_ver new_ver
  old_ver="$(tr -d '[:space:]' < "${RUNTIME_DIR}/VERSION" 2>/dev/null || echo "unknown")"

  if [[ "${dry_run}" == "1" ]]; then
    echo "[dry-run] sync engine=${RUNTIME_DIR} dev=${DEV_DIR:-none} workstation=${WS_DIR:-none} profile=${ZCG_GLOBAL_PROFILE} lang=${ZCG_INTERACTION_LANG}"
    return 0
  fi

  # 1. Synchronize Engine Runtime ($ZCG_RUNTIME_DIR)
  if [[ -d "${RUNTIME_DIR}/.git" ]]; then
    if [[ -z "${WS_DIR}" ]]; then
      git -C "${RUNTIME_DIR}" checkout -- antigravity/.gemini/config/AGENTS.md 2>/dev/null || true
    fi
    if [[ -n "${DEV_DIR}" ]] && [[ -d "${DEV_DIR}/.git" ]] && [[ "${DEV_DIR}" != "${RUNTIME_DIR}" ]]; then
      if git -C "${DEV_DIR}" rev-parse --verify HEAD >/dev/null 2>&1 &&
         git -C "${DEV_DIR}" diff --quiet &&
         git -C "${DEV_DIR}" diff --cached --quiet; then
        local dev_head rt_head
        dev_head="$(git -C "${DEV_DIR}" rev-parse HEAD 2>/dev/null || echo "")"
        rt_head="$(git -C "${RUNTIME_DIR}" rev-parse HEAD 2>/dev/null || echo "")"
        if [[ -n "${dev_head}" ]] && [[ "${dev_head}" != "${rt_head}" ]]; then
          git -C "${RUNTIME_DIR}" fetch "${DEV_DIR}" master -q 2>/dev/null &&
            git -C "${RUNTIME_DIR}" reset --hard FETCH_HEAD -q 2>/dev/null &&
            git -C "${RUNTIME_DIR}" clean -fd -q 2>/dev/null || true
        fi
      fi
    elif [[ "${ZCG_SKIP_PULL:-0}" != "1" ]] && git -C "${RUNTIME_DIR}" config --get remote.origin.url >/dev/null 2>&1; then
      GIT_TERMINAL_PROMPT=0 timeout 4s git -C "${RUNTIME_DIR}" pull --ff-only -q 2>/dev/null || true
    fi
  fi

  # 2. Synchronize Personal Root 0 Workstation Node (e.g. $HOME/<persona>-pc)
  if [[ -n "${WS_DIR}" ]] && [[ -f "${WS_DIR}/system/zcg-node.json" ]] && [[ "${WS_DIR}" != "${RUNTIME_DIR}" ]]; then
    if [[ -d "${WS_DIR}/.git" ]] && git -C "${WS_DIR}" diff --quiet && git -C "${WS_DIR}" diff --cached --quiet; then
      run_zcg --repo-dir "${RUNTIME_DIR}" sync-layer "${WS_DIR}" >/dev/null 2>&1 || true
    fi
    if [[ "${ZCG_SKIP_STOW:-0}" != "1" ]] && command -v stow >/dev/null 2>&1; then
      for bf in .bashrc .profile .bash_logout; do
        [[ -f "${HOME}/${bf}" ]] && [[ ! -L "${HOME}/${bf}" ]] &&
          mv "${HOME}/${bf}" "${HOME}/${bf}.backup.$(date +%Y%m%d)" 2>/dev/null || true
      done
      [[ -d "${WS_DIR}/bash" ]] && stow -d "${WS_DIR}" -t "${HOME}" -R bash 2>/dev/null || true
      if [[ -d "${WS_DIR}/git" ]] && { [[ "${ZCG_STOW_GIT:-1}" == "1" ]] || [[ -L "${HOME}/.gitconfig" ]]; }; then
        stow -d "${WS_DIR}" -t "${HOME}" -R git 2>/dev/null || true
      fi
    fi
  fi

  # 3. Compose Global AGENTS.md (with Personal Workstation Rules) & Stow Antigravity Config
  local profile_args=("--repo-dir" "${RUNTIME_DIR}" "set-global-profile" "${ZCG_GLOBAL_PROFILE}" "--lang" "${ZCG_INTERACTION_LANG}")
  local stow_root="${RUNTIME_DIR}"
  if [[ -n "${WS_DIR}" ]] && [[ -f "${WS_DIR}/system/zcg-node.json" ]]; then
    profile_args+=("--workstation-dir" "${WS_DIR}")
    stow_root="${WS_DIR}"
  fi
  if [[ "${ZCG_SKIP_STOW:-0}" != "1" ]] && command -v stow >/dev/null 2>&1; then
    for p in "${HOME}/.gemini/config/skills" "${HOME}/.gemini/config" "${HOME}/.gemini"; do
      [[ -L "${p}" ]] && rm -f "${p}"
    done
    while IFS= read -r -d '' sl; do
      local r_sl
      r_sl="$(readlink -f "${sl}" 2>/dev/null || echo "")"
      if [[ ! -e "${sl}" ]] || [[ "${r_sl}" != "${stow_root}/"* ]]; then
        rm -f "${sl}"
      fi
    done < <(find "${HOME}/.gemini/config" "${HOME}/.local/share/applications" -maxdepth 3 -type l -print0 2>/dev/null || true)
    find "${HOME}/.gemini/config/skills" "${HOME}/.gemini/config/scripts" -mindepth 1 -maxdepth 1 -type d -empty -delete 2>/dev/null || true
    mkdir -p "${HOME}/.gemini/config/skills" "${HOME}/.local/share/applications" "${HOME}/.local/bin" 2>/dev/null || true
    [[ -x "${RUNTIME_DIR}/.venv/bin/zcg" ]] && ln -sfn "${RUNTIME_DIR}/.venv/bin/zcg" "${HOME}/.local/bin/zcg"
    [[ -x "${RUNTIME_DIR}/.venv/bin/zcg-mcp" ]] && ln -sfn "${RUNTIME_DIR}/.venv/bin/zcg-mcp" "${HOME}/.local/bin/zcg-mcp"
    [[ -x "${RUNTIME_DIR}/scripts/workstation-sync.sh" ]] && ln -sfn "${RUNTIME_DIR}/scripts/workstation-sync.sh" "${HOME}/.local/bin/zcg-sync"
    profile_args+=("--stow")
  fi
  run_zcg "${profile_args[@]}" >/dev/null
  if [[ "${ZCG_SKIP_STOW:-0}" != "1" ]]; then
    command -v update-desktop-database >/dev/null 2>&1 &&
      update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true
  fi

  if [[ -d "${HOME}/.gemini/config/skills" ]]; then
    find "${HOME}/.gemini/config/skills" -maxdepth 2 -xtype l -delete 2>/dev/null || true
    find "${HOME}/.gemini/config/skills" -mindepth 1 -maxdepth 1 -type d -empty -delete 2>/dev/null || true
  fi

  new_ver="$(tr -d '[:space:]' < "${RUNTIME_DIR}/VERSION" 2>/dev/null || echo "unknown")"
  mkdir -p "$(dirname "${STAMP_FILE}")" 2>/dev/null || true
  printf '%s\n' "${new_ver}" >"${STAMP_FILE}" 2>/dev/null || true

  if [[ "${quiet_unchanged}" == "1" ]]; then
    if [[ "${old_ver}" != "${new_ver}" ]]; then
      echo "ZeroCloudGravity runtime updated: v${old_ver} -> v${new_ver} (profile=${ZCG_GLOBAL_PROFILE}, lang=${ZCG_INTERACTION_LANG})"
    fi
  else
    echo "OK: ZeroCloudGravity workstation synced (v${new_ver}, profile=${ZCG_GLOBAL_PROFILE}, lang=${ZCG_INTERACTION_LANG}, workstation=${WS_DIR:-none})."
  fi
}

CMD="sync"
if [[ $# -gt 0 ]]; then
  case "$1" in
    sync|--sync|setup|--setup|status|--status|--auto|-v|--version|-h|--help)
      CMD="$1"
      shift
      ;;
  esac
fi

QUIET_FLAG="0"
DRY_RUN="0"
NO_SYNC="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) ZCG_GLOBAL_PROFILE="${2:-}"; shift 2 ;;
    --lang) ZCG_INTERACTION_LANG="${2:-}"; shift 2 ;;
    --workstation-dir) WS_DIR="$(cd "${2:-}" && pwd)"; shift 2 ;;
    --dev-repo) DEV_DIR="$(cd "${2:-}" && pwd)"; shift 2 ;;
    --auto-sync) ZCG_AUTO_SYNC="${2:-}"; shift 2 ;;
    --no-browser) ZCG_NO_BROWSER="1"; shift ;;
    --no-sync) NO_SYNC="1"; shift ;;
    --quiet-if-unchanged|--auto) QUIET_FLAG="1"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    -v|--version) echo "zero-cloud-gravity v${VERSION_STR}"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Error: Unknown option '$1'." >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "${ZCG_GLOBAL_PROFILE}" in
  universal-base|academic-base|science-base|business-base|academic|science|technical|business|full) ;;
  *) echo "Error: Invalid --profile '${ZCG_GLOBAL_PROFILE}'." >&2; exit 1 ;;
esac
case "${ZCG_INTERACTION_LANG}" in
  en|es|it|fr|de|pt) ;;
  *) echo "Error: Invalid --lang '${ZCG_INTERACTION_LANG}'." >&2; exit 1 ;;
esac
case "${ZCG_AUTO_SYNC}" in
  boot|always|off) ;;
  *) echo "Error: Invalid --auto-sync '${ZCG_AUTO_SYNC}' (expected boot|always|off)." >&2; exit 1 ;;
esac

case "${CMD}" in
  -v|--version)
    echo "zero-cloud-gravity v${VERSION_STR}"
    ;;
  -h|--help)
    usage
    ;;
  --auto)
    [[ "${ZCG_AUTO_SYNC}" == "off" ]] && exit 0
    [[ "${ZCG_AUTO_SYNC}" == "boot" ]] && [[ -f "${STAMP_FILE}" ]] && exit 0
    run_sync "1" "${DRY_RUN}"
    ;;
  setup|--setup)
    RUNTIME_DIR="${REPO_DIR}"
    if [[ "${DRY_RUN}" == "0" ]]; then
      write_workstation_conf
      echo "OK: Workstation configuration written to ${CONFIG_FILE}."
    fi
    if [[ "${NO_SYNC}" == "0" ]]; then
      run_sync "${QUIET_FLAG}" "${DRY_RUN}"
    fi
    ;;
  status|--status)
    BOOT_SYNCED="false"
    [[ -f "${STAMP_FILE}" ]] && BOOT_SYNCED="true"
    cat <<EOF
{
  "version": "${VERSION_STR}",
  "runtime_dir": "${RUNTIME_DIR}",
  "workstation_dir": "${WS_DIR}",
  "dev_repo_dir": "${DEV_DIR}",
  "config_file": "${CONFIG_FILE}",
  "profile": "${ZCG_GLOBAL_PROFILE}",
  "interaction_language": "${ZCG_INTERACTION_LANG}",
  "auto_sync": "${ZCG_AUTO_SYNC}",
  "boot_synced": ${BOOT_SYNCED}
}
EOF
    ;;
  sync|--sync)
    run_sync "${QUIET_FLAG}" "${DRY_RUN}"
    ;;
esac
