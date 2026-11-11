#!/usr/bin/env bash
# ZeroCloudGravity (v1.0.0) — Ubuntu Physical Workstation Restore & Provisioner
# Usage: ./scripts/workstation-restore.sh [<workstation-dir>] [--all | --antigravity | --packages | --stow | --nvm | --gnome | --external] [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION_STR="$(tr -d '[:space:]' < "${REPO_DIR}/VERSION" 2>/dev/null || echo "unknown")"

WORKSTATION_DIR=""
MODE="interactive"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./scripts/workstation-restore.sh [<workstation-dir>] [mode] [--dry-run] [--version] [--help]

Modes:
  (no flag)      Interactive mode — prompts before each step
  --antigravity  Stow Antigravity global rules, skills, hooks, and zcg-mcp (~/.gemini/config/)
  --all          Restore all workstation components without prompting
  --packages     APT manual packages + Snaps + NPM globals
  --stow         Host Stow modules (bash + git) + Antigravity global configuration
  --nvm          NVM + Node.js default version
  --gnome        GNOME extensions checklist + declarative dconf settings
  --external     External packages (APT repos, .deb downloads, custom installer scripts)
  -n, --dry-run  Preview restore plan without modifying packages, symlinks, or dconf
  -v, --version  Show ZeroCloudGravity version
  -h, --help     Show this help message
EOF
}

for arg in "$@"; do
  case "${arg}" in
    interactive|--all|--antigravity|--packages|--stow|--nvm|--gnome|--external) MODE="${arg}" ;;
    -n|--dry-run) DRY_RUN=1 ;;
    -v|--version) echo "zero-cloud-gravity v${VERSION_STR}"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    -*)
      echo "Error: Unknown option '${arg}'." >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -z "${WORKSTATION_DIR}" ]]; then
        WORKSTATION_DIR="$(cd "${arg}" && pwd)"
      else
        echo "Error: Unexpected positional argument '${arg}'." >&2
        exit 1
      fi
      ;;
  esac
done

if [[ -z "${WORKSTATION_DIR}" ]]; then
  WORKSTATION_DIR="${ZCG_WORKSTATION_DIR:-${PWD}}"
  WORKSTATION_DIR="$(cd "${WORKSTATION_DIR}" && pwd)"
fi

SYSTEM_DIR="${WORKSTATION_DIR}/system"
WORKSTATION_CONF="${ZCG_WORKSTATION_CONF:-${HOME}/.config/zero-cloud-gravity/workstation.conf}"
if [[ -f "${WORKSTATION_CONF}" ]]; then
  # shellcheck disable=SC1090
  . "${WORKSTATION_CONF}"
fi
ZCG_ENGINE_DIR="${ZCG_RUNTIME_DIR:-${REPO_DIR}}"
export ZCG_ENGINE_DIR

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[dry-run] Workstation restore plan (workstation=${WORKSTATION_DIR}, engine=${ZCG_ENGINE_DIR}, mode=${MODE})"
  exit 0
fi

confirm() {
  if [[ "${MODE}" != "interactive" ]]; then return 0; fi
  read -rp "$1 (y/N): " answer
  [[ "${answer}" == "y" ]] || [[ "${answer}" == "Y" ]]
}

if [[ "${MODE}" == "--antigravity" ]]; then
  exec "${ZCG_ENGINE_DIR}/install.sh" \
    --profile "${ZCG_GLOBAL_PROFILE:-universal-base}" \
    --lang "${ZCG_INTERACTION_LANG:-en}" \
    --stow
fi

# --- Step 1: APT packages ---
if [[ "${MODE}" == "--all" ]] || [[ "${MODE}" == "--packages" ]] || [[ "${MODE}" == "interactive" ]]; then
  if [[ -f "${SYSTEM_DIR}/packages-manual.txt" ]] && confirm "Install APT packages?"; then
    echo "=== Step 1: APT packages ==="
    if grep -q ':i386$' "${SYSTEM_DIR}/packages-manual.txt" && ! dpkg --print-foreign-architectures | grep -qx 'i386'; then
      sudo dpkg --add-architecture i386
    fi
    sudo apt-get update
    AVAILABLE_PKGS="$(grep -h '^Package: ' /var/lib/apt/lists/*Packages 2>/dev/null | awk '{print $2}' | sort -u || apt-cache pkgnames 2>/dev/null | sort -u)"
    mapfile -t INSTALL_LIST < <(
      awk 'NR==FNR {ok[$1]=1; next} NF {base=$1; sub(/:.*/, "", base); if (ok[base]) print $1; else print "SKIP:" $1 > "/dev/stderr"}' \
        <(echo "${AVAILABLE_PKGS}") "${SYSTEM_DIR}/packages-manual.txt" 2> >(sed 's/^SKIP:/  Skip (not in APT): /' >&2)
    )
    if [[ "${#INSTALL_LIST[@]}" -gt 0 ]]; then
      sudo apt-get install -y "${INSTALL_LIST[@]}"
    fi
  fi
fi

# --- Step 2: Snaps ---
if [[ "${MODE}" == "--all" ]] || [[ "${MODE}" == "--packages" ]] || [[ "${MODE}" == "interactive" ]]; then
  if [[ -f "${SYSTEM_DIR}/snaps.txt" ]] && confirm "Install Snap packages?"; then
    echo "=== Step 2: Snaps ==="
    while read -r snap_pkg; do
      [[ -z "${snap_pkg}" ]] && continue
      sudo snap install "${snap_pkg}" 2>/dev/null || \
      sudo snap install "${snap_pkg}" --classic 2>/dev/null || \
      echo "  Skip: ${snap_pkg} (manual install may be required)"
    done < "${SYSTEM_DIR}/snaps.txt"
  fi
fi

# --- Step 3: GNU Stow (Host modules + Antigravity global configuration) ---
if [[ "${MODE}" == "--all" ]] || [[ "${MODE}" == "--stow" ]] || [[ "${MODE}" == "interactive" ]]; then
  if confirm "Link shell/Git profiles and Antigravity config via GNU Stow?"; then
    echo "=== Step 3: GNU Stow ==="
    if ! command -v stow &>/dev/null; then
      sudo apt-get install -y stow
    fi
    cd "${WORKSTATION_DIR}"
    for mod_dir in */; do
      [[ -d "${mod_dir}" ]] || continue
      module="${mod_dir%/}"
      case "${module}" in
        antigravity|system|scripts|templates|docs|roadmaps|corporate|surfaces|layers|logs|tests|src|venv|.venv|htmlcov|.git|.github|.agents) continue ;;
      esac
      echo "  -> stow ${module}"
      if [[ "${module}" == "git" ]] && [[ ! -f "${HOME}/.gitconfig.local" ]] && [[ -f "${HOME}/.gitconfig" ]] && [[ ! -L "${HOME}/.gitconfig" ]]; then
        existing_name="$(git config --file "${HOME}/.gitconfig" user.name 2>/dev/null || true)"
        existing_email="$(git config --file "${HOME}/.gitconfig" user.email 2>/dev/null || true)"
        if [[ -n "${existing_name}" ]] || [[ -n "${existing_email}" ]]; then
          printf "[user]\n\tname = %s\n\temail = %s\n" "${existing_name}" "${existing_email}" > "${HOME}/.gitconfig.local"
        fi
      fi
      while IFS= read -r f; do
        [[ -z "${f}" ]] && continue
        if [[ -L "${HOME}/${f}" ]]; then
          target_real="$(readlink -f "${HOME}/${f}" 2>/dev/null || true)"
          if [[ -z "${target_real}" ]] || [[ "${target_real}" != "${WORKSTATION_DIR}/"* ]]; then
            rm -f "${HOME}/${f}"
          fi
        elif [[ -f "${HOME}/${f}" ]]; then
          mv "${HOME}/${f}" "${HOME}/${f}.backup.$(date +%Y%m%d)"
        fi
      done < <(find "${module}" -type f -printf '%P\n')
      stow -t "${HOME}" "${module}"
    done
    "${ZCG_ENGINE_DIR}/install.sh" \
      --profile "${ZCG_GLOBAL_PROFILE:-universal-base}" \
      --lang "${ZCG_INTERACTION_LANG:-en}" \
      --stow
  fi
fi

# --- Step 4: NVM + Node ---
if [[ "${MODE}" == "--all" ]] || [[ "${MODE}" == "--nvm" ]] || [[ "${MODE}" == "interactive" ]]; then
  if [[ -f "${SYSTEM_DIR}/nvm-default.txt" ]] && confirm "Install NVM and Node.js?"; then
    echo "=== Step 4: NVM + Node ==="
    NODE_VERSION="$(cat "${SYSTEM_DIR}/nvm-default.txt")"
    if [[ ! -s "${HOME}/.nvm/nvm.sh" ]]; then
      curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
    fi
    export NVM_DIR="${HOME}/.nvm"
    # shellcheck source=/dev/null
    [[ -s "${NVM_DIR}/nvm.sh" ]] && . "${NVM_DIR}/nvm.sh"
    if [[ -z "${NODE_VERSION}" ]] || [[ "${NODE_VERSION}" == "none" ]]; then
      nvm install --lts && nvm alias default 'lts/*'
    else
      nvm install "${NODE_VERSION}" && nvm alias default "${NODE_VERSION}"
    fi
  fi
fi

# --- Step 5: NPM globals ---
if [[ "${MODE}" == "--all" ]] || [[ "${MODE}" == "--packages" ]] || [[ "${MODE}" == "interactive" ]]; then
  if [[ -f "${SYSTEM_DIR}/npm-globals.txt" ]] && confirm "Install NPM global packages?"; then
    echo "=== Step 5: NPM globals ==="
    export NVM_DIR="${HOME}/.nvm"
    # shellcheck source=/dev/null
    [[ -s "${NVM_DIR}/nvm.sh" ]] && . "${NVM_DIR}/nvm.sh"
    [[ -f "${SYSTEM_DIR}/nvm-default.txt" ]] && { nvm use "$(cat "${SYSTEM_DIR}/nvm-default.txt")" 2>/dev/null || true; }
    if command -v npm &>/dev/null && [[ -w "$(npm config get prefix 2>/dev/null || echo /usr)" ]]; then
      while read -r pkg; do
        [[ -z "${pkg}" ]] && continue
        npm install -g "${pkg}" 2>/dev/null || echo "  Skip: ${pkg}"
      done < "${SYSTEM_DIR}/npm-globals.txt"
    else
      echo "  Warning: npm missing or prefix not user-writable (run with --nvm first)"
    fi
  fi
fi

# --- Step 6 & 7: GNOME extensions & declarative dconf ---
if [[ "${MODE}" == "--all" ]] || [[ "${MODE}" == "--gnome" ]] || [[ "${MODE}" == "interactive" ]]; then
  if [[ -f "${SYSTEM_DIR}/gnome-extensions.txt" ]] && confirm "Show GNOME extensions to install?"; then
    echo "=== Step 6: GNOME extensions ==="
    while read -r ext; do [[ -n "${ext}" ]] && echo "  - ${ext}"; done < "${SYSTEM_DIR}/gnome-extensions.txt"
  fi
  if [[ -f "${SYSTEM_DIR}/gnome-settings.dconf" ]] && confirm "Restore GNOME settings (dconf)?"; then
    echo "=== Step 7: GNOME settings ==="
    dconf load / < "${SYSTEM_DIR}/gnome-settings.dconf"
    echo "  OK: GNOME settings restored"
  fi
fi

# --- Step 8: External packages ---
if [[ "${MODE}" == "--all" ]] || [[ "${MODE}" == "--external" ]] || [[ "${MODE}" == "interactive" ]]; then
  EXT_DIR="${SYSTEM_DIR}/external"
  if [[ -d "${EXT_DIR}" ]] && confirm "Install external packages?"; then
    echo "=== Step 8: External packages ==="
    is_external_enabled() {
      local rel_ext="${1#"${EXT_DIR}"/}"
      [[ ! -f "${SYSTEM_DIR}/external.txt" ]] && return 0
      grep -qxF "${rel_ext}" "${SYSTEM_DIR}/external.txt" 2>/dev/null
    }
    if [[ -d "${EXT_DIR}/apt-repo" ]]; then
      NEED_UPDATE=false
      for pkg_file in "${EXT_DIR}/apt-repo"/*.sh; do
        [[ -f "${pkg_file}" ]] || continue
        is_external_enabled "${pkg_file}" || continue
        # shellcheck disable=SC2034
        NAME="" DESCRIPTION="" PACKAGES="" CHECK=""
        setup_repo() { :; }
        # shellcheck source=/dev/null
        source "${pkg_file}"
        if ! { dpkg -s "${CHECK}" &>/dev/null && apt-cache policy "${CHECK}" 2>/dev/null | grep -q 'http'; }; then
          echo "  -> Setting up repo: ${NAME}"
          setup_repo
          NEED_UPDATE=true
        fi
      done
      [[ "${NEED_UPDATE}" == true ]] && sudo apt-get update -qq
      for pkg_file in "${EXT_DIR}/apt-repo"/*.sh; do
        [[ -f "${pkg_file}" ]] || continue
        is_external_enabled "${pkg_file}" || continue
        # shellcheck disable=SC2034
        NAME="" DESCRIPTION="" PACKAGES="" CHECK=""
        setup_repo() { :; }
        # shellcheck source=/dev/null
        source "${pkg_file}"
        if ! dpkg -s "${CHECK}" &>/dev/null; then
          # shellcheck disable=SC2086
          sudo apt-get install -y ${PACKAGES}
        fi
      done
    fi
    if [[ -d "${EXT_DIR}/deb-url" ]]; then
      for pkg_file in "${EXT_DIR}/deb-url"/*.sh; do
        [[ -f "${pkg_file}" ]] || continue
        is_external_enabled "${pkg_file}" || continue
        # shellcheck disable=SC2034
        NAME="" DESCRIPTION="" URL="" CHECK=""
        # shellcheck source=/dev/null
        source "${pkg_file}"
        if ! dpkg -s "${CHECK}" &>/dev/null; then
          TMP_DIR="$(mktemp -d)"
          if curl -fsSL -o "${TMP_DIR}/download" "${URL}"; then
            if echo "${URL}" | grep -qi '\.zip$'; then
              command -v unzip &>/dev/null || sudo apt-get install -y -qq unzip
              unzip -q "${TMP_DIR}/download" -d "${TMP_DIR}"
              DEB_FILE="$(find "${TMP_DIR}" -name '*.deb' | head -1)"
            else
              DEB_FILE="${TMP_DIR}/download"
            fi
            [[ -n "${DEB_FILE}" ]] && [[ -f "${DEB_FILE}" ]] && { sudo dpkg -i "${DEB_FILE}" || sudo apt-get install -f -y; }
          fi
          rm -rf "${TMP_DIR}"
        fi
      done
    fi
    if [[ -d "${EXT_DIR}/script" ]]; then
      for pkg_file in "${EXT_DIR}/script"/*.sh; do
        [[ -f "${pkg_file}" ]] || continue
        is_external_enabled "${pkg_file}" || continue
        # shellcheck disable=SC2034
        NAME="" DESCRIPTION="" INSTALL_CMD="" CHECK_CMD=""
        # shellcheck source=/dev/null
        source "${pkg_file}"
        if [[ -z "${CHECK_CMD}" ]] || ! eval "${CHECK_CMD}" &>/dev/null; then
          eval "${INSTALL_CMD}" || echo "  Warning: Install failed: ${NAME}"
        fi
      done
    fi
  fi
fi

echo "Workstation restore complete."
