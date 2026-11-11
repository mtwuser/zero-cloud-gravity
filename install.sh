#!/usr/bin/env bash
# ZeroCloudGravity v1.0.0 — Sovereign Zero-Cloud Antigravity Node Bootstrapper
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/zero-cloud-gravity"
CONFIG_FILE="${CONFIG_DIR}/workstation.conf"

PROFILE="universal-base"
LANG_CODE="en"
WORKSTATION_DIR="${ZCG_WORKSTATION_DIR:-}"
AUTO_SYNC="${ZCG_AUTO_SYNC:-boot}"
RUN_STOW="0"
DRY_RUN="0"
NO_BROWSER="${ZCG_NO_BROWSER:-0}"
INSTALL_AGY=""

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Bootstrap a ZeroCloudGravity workstation or sovereign node environment.

Options:
  --profile <name>              Global profile: universal-base|academic-base|science-base|business-base|academic|science|technical|business|full
  --lang <code>                 Interaction language: en|es|it|fr|de|pt (default: en)
  --workstation-dir <path>      Personal Root 0 workstation node path (auto-detected if ~/*-pc exists)
  --auto-sync <mode>            Shell startup sync policy: boot|always|off (default: boot)
  --stow                        Stow antigravity/.gemini/config into $HOME and register zcg-mcp
  --install-antigravity <mode>  Install/update Google Antigravity: agents|cli|ide|all
  --no-browser                  Suppress automatic browser launch (sets ZCG_NO_BROWSER=1)
  --dry-run                     Preview actions without modifying $HOME or workstation state
  -h, --help                    Show this help message and exit
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      if [[ $# -lt 2 ]]; then
        echo "Error: --profile requires a value." >&2
        exit 1
      fi
      PROFILE="$2"
      shift 2
      ;;
    --lang)
      if [[ $# -lt 2 ]]; then
        echo "Error: --lang requires a value." >&2
        exit 1
      fi
      LANG_CODE="$2"
      shift 2
      ;;
    --workstation-dir)
      if [[ $# -lt 2 ]]; then
        echo "Error: --workstation-dir requires a path." >&2
        exit 1
      fi
      WORKSTATION_DIR="$(cd "$2" && pwd)"
      shift 2
      ;;
    --auto-sync)
      if [[ $# -lt 2 ]]; then
        echo "Error: --auto-sync requires boot|always|off." >&2
        exit 1
      fi
      AUTO_SYNC="$2"
      shift 2
      ;;
    --stow)
      RUN_STOW="1"
      shift
      ;;
    --install-antigravity)
      if [[ $# -lt 2 ]]; then
        echo "Error: --install-antigravity requires agents|cli|ide|all." >&2
        exit 1
      fi
      INSTALL_AGY="$2"
      shift 2
      ;;
    --no-browser)
      NO_BROWSER="1"
      shift
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown argument '$1'." >&2
      usage >&2
      exit 1
      ;;
  esac
done

export ZCG_NO_BROWSER="${NO_BROWSER}"

VENV_DIR="${REPO_DIR}/.venv"
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[dry-run] python3 -m venv ${VENV_DIR} && ${VENV_DIR}/bin/pip install -e ${REPO_DIR}"
  else
    python3 -m venv "${VENV_DIR}"
    "${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null
    "${VENV_DIR}/bin/pip" install -e "${REPO_DIR}" >/dev/null
  fi
fi

if [[ -z "${WORKSTATION_DIR}" ]]; then
  for _cand in "${HOME}"/*-pc; do
    if [[ -f "${_cand}/system/zcg-node.json" ]]; then
      WORKSTATION_DIR="$(cd "${_cand}" && pwd)"
      break
    fi
  done
fi

ZCG_ARGS=("--repo-dir" "${REPO_DIR}")
if [[ "${DRY_RUN}" == "1" ]]; then
  ZCG_ARGS+=("--dry-run")
fi
ZCG_ARGS+=("set-global-profile" "${PROFILE}" "--lang" "${LANG_CODE}")
if [[ -n "${WORKSTATION_DIR}" ]] && [[ -f "${WORKSTATION_DIR}/system/zcg-node.json" ]]; then
  ZCG_ARGS+=("--workstation-dir" "${WORKSTATION_DIR}")
fi
if [[ "${RUN_STOW}" == "1" ]]; then
  if [[ "${DRY_RUN}" == "0" ]]; then
    STOW_ROOT="${WORKSTATION_DIR:-${REPO_DIR}}"
    while IFS= read -r -d '' _sl; do
      _r_sl="$(readlink -f "${_sl}" 2>/dev/null || echo "")"
      if [[ ! -e "${_sl}" ]] || [[ "${_r_sl}" != "${STOW_ROOT}/"* ]]; then
        rm -f "${_sl}"
      fi
    done < <(find "${HOME}/.gemini/config" "${HOME}/.local/share/applications" -maxdepth 3 -type l -print0 2>/dev/null || true)
    find "${HOME}/.gemini/config/skills" "${HOME}/.gemini/config/scripts" -mindepth 1 -maxdepth 1 -type d -empty -delete 2>/dev/null || true
    mkdir -p "${HOME}/.gemini/config/skills" "${HOME}/.local/share/applications" "${HOME}/.local/bin" 2>/dev/null || true
    [[ -x "${VENV_DIR}/bin/zcg" ]] && ln -sfn "${VENV_DIR}/bin/zcg" "${HOME}/.local/bin/zcg"
    [[ -x "${VENV_DIR}/bin/zcg-mcp" ]] && ln -sfn "${VENV_DIR}/bin/zcg-mcp" "${HOME}/.local/bin/zcg-mcp"
    [[ -x "${REPO_DIR}/scripts/workstation-sync.sh" ]] && ln -sfn "${REPO_DIR}/scripts/workstation-sync.sh" "${HOME}/.local/bin/zcg-sync"
  fi
  ZCG_ARGS+=("--stow")
fi

if [[ -x "${VENV_DIR}/bin/zcg" ]]; then
  "${VENV_DIR}/bin/zcg" "${ZCG_ARGS[@]}"
else
  PYTHONPATH="${REPO_DIR}/src" python3 -c "import sys; from zcg.cli.dispatcher import main; raise SystemExit(main(sys.argv[1:]))" "${ZCG_ARGS[@]}"
fi

if [[ "${RUN_STOW}" == "1" ]] && [[ "${DRY_RUN}" == "0" ]]; then
  command -v update-desktop-database >/dev/null 2>&1 &&
    update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true
fi

if [[ "${DRY_RUN}" == "0" ]]; then
  mkdir -p "${CONFIG_DIR}"
  DEV_REPO=""
  [[ -f "${HOME}/Projects/dev-zero-cloud-gravity/system/zcg-node.json" ]] && DEV_REPO="${HOME}/Projects/dev-zero-cloud-gravity"
  cat >"${CONFIG_FILE}" <<EOF
# Declarative Workstation Configuration for ZeroCloudGravity
export ZCG_RUNTIME_DIR="${REPO_DIR}"
export ZCG_WORKSTATION_DIR="${WORKSTATION_DIR}"
export ZCG_DEV_REPO_DIR="${DEV_REPO}"
export ZCG_GLOBAL_PROFILE="${PROFILE}"
export ZCG_INTERACTION_LANG="${LANG_CODE}"
export ZCG_AUTO_SYNC="${AUTO_SYNC}"
export ZCG_NO_BROWSER="${NO_BROWSER}"
EOF
fi

if [[ -n "${INSTALL_AGY}" ]]; then
  AGY_FLAG="--${INSTALL_AGY#--}"
  AGY_ARGS=("${AGY_FLAG}")
  [[ "${DRY_RUN}" == "1" ]] && AGY_ARGS+=("--dry-run")
  "${REPO_DIR}/scripts/install-antigravity.sh" "${AGY_ARGS[@]}"
fi

echo "ZeroCloudGravity node initialized (profile=${PROFILE}, lang=${LANG_CODE}, dry_run=${DRY_RUN})."
