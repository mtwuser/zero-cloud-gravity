#!/usr/bin/env bash
# ZeroCloudGravity (v1.0.1) — Read-Only Ubuntu Workstation Drift Audit
# Usage: ./scripts/workstation-audit.sh [<workstation-dir>] [--clean] [--version] [--help]

set -euo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION_STR="$(tr -d '[:space:]' < "${REPO_DIR}/VERSION" 2>/dev/null || echo "unknown")"

WORKSTATION_DIR=""
MODE="audit"

usage() {
  cat <<'EOF'
Usage: ./scripts/workstation-audit.sh [<workstation-dir>] [--clean] [--version] [--help]

Modes:
  (no flag)      Read-only audit across Stow symlinks, APT, Snap, NPM, External, GNOME, and Git
  --clean        Interactive cleanup of residual backup files in $HOME
  -v, --version  Show ZeroCloudGravity version
  -h, --help     Show this help message
EOF
}

for arg in "$@"; do
  case "${arg}" in
    audit|--clean) MODE="${arg}" ;;
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
ZCG_RUNTIME_DIR="${REPO_DIR}"
ACTIVE_PROFILE="universal-base"
if [[ -f "${WORKSTATION_CONF}" ]]; then
  # shellcheck disable=SC1090
  . "${WORKSTATION_CONF}"
  ACTIVE_PROFILE="${ZCG_GLOBAL_PROFILE:-universal-base}"
fi
ZCG_RUNTIME_REAL="$(cd "${ZCG_RUNTIME_DIR}" 2>/dev/null && pwd || echo "${REPO_DIR}")"
export ZCG_ENGINE_DIR="${ZCG_RUNTIME_REAL}"

if [[ -n "${NO_COLOR:-}" ]]; then
  RED='' GREEN='' YELLOW='' BLUE='' NC='' BOLD=''
else
  RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[1;33m'
  BLUE='\033[0;34m' NC='\033[0m' BOLD='\033[1m'
fi

ISSUES=0
AUDIT_IGNORE=""
if [[ -f "${WORKSTATION_DIR}/.audit-ignore" ]]; then
  AUDIT_IGNORE="$(grep -v '^#' "${WORKSTATION_DIR}/.audit-ignore" | grep -v '^$' | sort || true)"
fi

section() { echo -e "\n${BLUE}=== $1 ===${NC}"; }
ok()      { echo -e "  ${GREEN}OK:${NC} $1"; }
warn()    { echo -e "  ${YELLOW}WARN:${NC} $1"; ISSUES=$((ISSUES + 1)); }
item()    { echo -e "      $1"; }
confirm() { read -rp "  $1 (y/N): " answer; [[ "${answer}" == "y" ]] || [[ "${answer}" == "Y" ]]; }

echo -e "${BOLD}ZeroCloudGravity Workstation Audit — $(basename "${WORKSTATION_DIR}") ($(date +%Y-%m-%d))${NC}"

# 1. Stow Symlinks (Antigravity engine + Workstation host modules)
section "Stow Symlinks"
STOW_OK=0
STOW_ISSUES=0

audit_stow_module() {
  local base_dir="$1" alt_base="$2" module_name="$3"
  [[ -d "${base_dir}/${module_name}" ]] || return 0
  while IFS= read -r relpath; do
    [[ -z "${relpath}" ]] && continue
    local target="${HOME}/${relpath}"
    local source="${base_dir}/${module_name}/${relpath}"
    local alt_source="${alt_base}/${module_name}/${relpath}"
    if [[ -e "${target}" ]] || [[ -L "${target}" ]]; then
      local resolved_target resolved_source resolved_alt
      resolved_target="$(readlink -f "${target}" 2>/dev/null || echo "BROKEN")"
      resolved_source="$(readlink -f "${source}")"
      resolved_alt="$(readlink -f "${alt_source}" 2>/dev/null || echo "${resolved_source}")"
      if [[ "${resolved_target}" == "${resolved_source}" ]] || [[ "${resolved_target}" == "${resolved_alt}" ]]; then
        STOW_OK=$((STOW_OK + 1))
      else
        warn "[${module_name}] ~/${relpath} -> wrong target (actual: ${resolved_target})"
        STOW_ISSUES=$((STOW_ISSUES + 1))
      fi
    else
      warn "[${module_name}] ~/${relpath} -> missing"
      STOW_ISSUES=$((STOW_ISSUES + 1))
    fi
  done < <(find "${base_dir}/${module_name}" -type f -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -name '*.pyc' -printf '%P\n')
}

ANTIGRAVITY_STOW_BASE="${ZCG_RUNTIME_REAL}"
if [[ -d "${WORKSTATION_DIR}/antigravity" ]]; then
  ANTIGRAVITY_STOW_BASE="${WORKSTATION_DIR}"
elif [[ -n "${ZCG_WORKSTATION_DIR:-}" ]] && [[ -d "${ZCG_WORKSTATION_DIR}/antigravity" ]]; then
  ANTIGRAVITY_STOW_BASE="$(cd "${ZCG_WORKSTATION_DIR}" && pwd)"
fi
audit_stow_module "${ANTIGRAVITY_STOW_BASE}" "${ZCG_RUNTIME_REAL}" "antigravity"
for mod_path in "${WORKSTATION_DIR}"/*/; do
  [[ -d "${mod_path}" ]] || continue
  mod_name="$(basename "${mod_path}")"
  case "${mod_name}" in
    antigravity|system|scripts|templates|docs|roadmaps|corporate|surfaces|layers|logs|tests|src|venv|.venv|htmlcov|.git|.github|.agents) continue ;;
  esac
  audit_stow_module "${WORKSTATION_DIR}" "${WORKSTATION_DIR}" "${mod_name}"
done

if [[ "${STOW_ISSUES}" -eq 0 ]]; then
  if [[ -L "${HOME}/.gemini" ]] || [[ -L "${HOME}/.gemini/config" ]] || [[ -L "${HOME}/.gemini/config/skills" ]]; then
    warn "${HOME}/.gemini/config or ${HOME}/.gemini/config/skills is a folded symlink instead of a real directory"
  else
    ok "All ${STOW_OK} symlinks healthy (tree-unfolded)"
  fi
fi

# 2. APT Packages
section "APT Packages"
EXT_DIR="${SYSTEM_DIR}/external"
if [[ -f "${SYSTEM_DIR}/packages-manual.txt" ]]; then
  CURRENT_APT="$(apt-mark showmanual 2>/dev/null | grep -v '^linux-generic-hwe-' | sort || true)"
  UBUNTU_REMOTE="$(grep -h '^Package: ' /var/lib/apt/lists/*ubuntu.com*Packages 2>/dev/null | awk '{print $2}' | sort -u || true)"
  if [[ -n "${UBUNTU_REMOTE}" ]]; then
    CURRENT_APT="$(awk 'NR==FNR {ok[$1]=1; next} {base=$1; sub(/:.*/, "", base); if (ok[base]) print $1}' <(echo "${UBUNTU_REMOTE}") <(echo "${CURRENT_APT}"))"
  fi
  MANIFEST_APT="$(grep -v '^$' "${SYSTEM_DIR}/packages-manual.txt" | sort || true)"
  ONLY_SYSTEM="$(comm -23 <(echo "${CURRENT_APT}") <(echo "${MANIFEST_APT}") || true)"
  ONLY_MANIFEST="$(comm -13 <(echo "${CURRENT_APT}") <(echo "${MANIFEST_APT}") || true)"

  EXTERNAL_PKGS=""
  for ext_file in "${EXT_DIR}"/deb-url/*.sh "${EXT_DIR}"/script/*.sh "${EXT_DIR}"/apt-repo/*.sh; do
    [[ -f "${ext_file}" ]] || continue
    ext_check="$(grep '^CHECK=' "${ext_file}" 2>/dev/null | head -1 | cut -d'"' -f2 || true)"
    [[ -n "${ext_check}" ]] && EXTERNAL_PKGS="${EXTERNAL_PKGS} ${ext_check}"
    ext_packages="$(grep '^PACKAGES=' "${ext_file}" 2>/dev/null | head -1 | cut -d'"' -f2 || true)"
    [[ -n "${ext_packages}" ]] && EXTERNAL_PKGS="${EXTERNAL_PKGS} ${ext_packages}"
    repo_helpers="$(grep -oP '[a-z0-9][-a-z0-9]*-(?:stable-)?release[_/]' "${ext_file}" 2>/dev/null | sed 's|[_/]$||' | sort -u || true)"
    [[ -n "${repo_helpers}" ]] && EXTERNAL_PKGS="${EXTERNAL_PKGS} ${repo_helpers}"
  done
  EXTERNAL_PKGS_SORTED="$(echo "${EXTERNAL_PKGS}" | tr ' ' '\n' | grep -v '^$' | sort -u || true)"
  if [[ -n "${EXTERNAL_PKGS_SORTED}" ]]; then
    ONLY_SYSTEM="$(comm -23 <(echo "${ONLY_SYSTEM}") <(echo "${EXTERNAL_PKGS_SORTED}") || true)"
    ONLY_MANIFEST="$(comm -23 <(echo "${ONLY_MANIFEST}") <(echo "${EXTERNAL_PKGS_SORTED}") || true)"
  fi
  if [[ -n "${AUDIT_IGNORE}" ]]; then
    ONLY_SYSTEM="$(comm -23 <(echo "${ONLY_SYSTEM}") <(echo "${AUDIT_IGNORE}") || true)"
    ONLY_MANIFEST="$(comm -23 <(echo "${ONLY_MANIFEST}") <(echo "${AUDIT_IGNORE}") || true)"
  fi
  HAS_DRIFT=false
  if [[ -n "${ONLY_SYSTEM}" ]]; then
    HAS_DRIFT=true
    COUNT="$(echo "${ONLY_SYSTEM}" | wc -l)"
    warn "${COUNT} installed but not in manifest (run 'make backup-system' to capture):"
    echo "${ONLY_SYSTEM}" | head -20 | while IFS= read -r pkg; do item "${GREEN}+ ${pkg}${NC}"; done
  fi
  if [[ -n "${ONLY_MANIFEST}" ]]; then
    HAS_DRIFT=true
    COUNT="$(echo "${ONLY_MANIFEST}" | wc -l)"
    warn "${COUNT} in manifest but not installed:"
    echo "${ONLY_MANIFEST}" | while IFS= read -r pkg; do item "${RED}- ${pkg}${NC}"; done
  fi
  if [[ "${HAS_DRIFT}" == false ]]; then
    TOTAL="$(grep -c . <<< "${MANIFEST_APT}" || true)"
    ok "In sync (${TOTAL} packages)"
  fi
else
  ok "APT manifest not configured in ${SYSTEM_DIR}"
fi

# 3. Snap Packages
section "Snap Packages"
if [[ -f "${SYSTEM_DIR}/snaps.txt" ]] && command -v snap &>/dev/null; then
  CURRENT_SNAPS="$(snap list 2>/dev/null | tail -n +2 | awk '$6 !~ /^(base|snapd)$/ && $1 !~ /^(gnome-[0-9]|gtk-common-themes|mesa-[0-9])/ {print $1}' | sort || true)"
  MANIFEST_SNAPS="$(grep -v '^$' "${SYSTEM_DIR}/snaps.txt" | sort || true)"
  ONLY_SYSTEM="$(comm -23 <(echo "${CURRENT_SNAPS}") <(echo "${MANIFEST_SNAPS}") | grep -v '^$' || true)"
  ONLY_MANIFEST="$(comm -13 <(echo "${CURRENT_SNAPS}") <(echo "${MANIFEST_SNAPS}") | grep -v '^$' || true)"
  if [[ -n "${ONLY_SYSTEM}" ]] || [[ -n "${ONLY_MANIFEST}" ]]; then
    [[ -n "${ONLY_SYSTEM}" ]] && warn "Installed snaps missing from manifest: $(echo "${ONLY_SYSTEM}" | tr '\n' ' ')"
    [[ -n "${ONLY_MANIFEST}" ]] && warn "Manifest snaps not installed: $(echo "${ONLY_MANIFEST}" | tr '\n' ' ')"
  else
    TOTAL="$(grep -c . <<< "${MANIFEST_SNAPS}" || true)"
    ok "In sync (${TOTAL} snaps)"
  fi
else
  ok "Snap manifest skipped or not applicable"
fi

# 4. NPM Globals
section "NPM Globals"
if ! command -v npm &>/dev/null && [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  export NVM_DIR="${HOME}/.nvm"
  # shellcheck source=/dev/null
  . "${NVM_DIR}/nvm.sh"
fi
if [[ -f "${SYSTEM_DIR}/npm-globals.txt" ]] && command -v npm &>/dev/null; then
  CURRENT_NPM="$(npm list -g --depth=0 2>/dev/null | tail -n +2 | sed 's/^[-├└─+` ]*//g' | grep -v '^$' | sort || true)"
  MANIFEST_NPM="$(grep -v '^$' "${SYSTEM_DIR}/npm-globals.txt" | sort || true)"
  ONLY_SYSTEM="$(comm -23 <(echo "${CURRENT_NPM}") <(echo "${MANIFEST_NPM}") | grep -v '^$' || true)"
  ONLY_MANIFEST="$(comm -13 <(echo "${CURRENT_NPM}") <(echo "${MANIFEST_NPM}") | grep -v '^$' || true)"
  if [[ -n "${ONLY_SYSTEM}" ]] || [[ -n "${ONLY_MANIFEST}" ]]; then
    [[ -n "${ONLY_SYSTEM}" ]] && warn "Installed NPM globals missing from manifest: $(echo "${ONLY_SYSTEM}" | tr '\n' ' ')"
    [[ -n "${ONLY_MANIFEST}" ]] && warn "Manifest NPM globals not installed: $(echo "${ONLY_MANIFEST}" | tr '\n' ' ')"
  else
    TOTAL="$(grep -c . <<< "${MANIFEST_NPM}" || true)"
    ok "In sync (${TOTAL} packages)"
  fi
else
  ok "NPM globals check skipped or not applicable"
fi

# 5. External Packages
section "External Packages"
if [[ -d "${EXT_DIR}" ]]; then
  EXT_INSTALLED=0
  EXT_MISSING=0
  MISSING_NAMES=()
  UNTRACKED_NAMES=()
  INACTIVE_REPOS=()
  MANIFEST_EXT=""
  [[ -f "${SYSTEM_DIR}/external.txt" ]] && MANIFEST_EXT="$(grep -v '^#' "${SYSTEM_DIR}/external.txt" | grep -v '^$' | sort || true)"
  for pkg_file in "${EXT_DIR}"/apt-repo/*.sh "${EXT_DIR}"/deb-url/*.sh "${EXT_DIR}"/script/*.sh; do
    [[ -f "${pkg_file}" ]] || continue
    rel_ext="${pkg_file#"${EXT_DIR}"/}"
    IN_MANIFEST=true
    if [[ -f "${SYSTEM_DIR}/external.txt" ]] && ! grep -qxF "${rel_ext}" <<< "${MANIFEST_EXT}"; then
      IN_MANIFEST=false
    fi
    # shellcheck disable=SC2034
    NAME="" DESCRIPTION="" CHECK="" CHECK_CMD="" URL="" PACKAGES="" INSTALL_CMD=""
    unset -f setup_repo
    # shellcheck source=/dev/null
    source "${pkg_file}"
    INSTALLED=false
    if [[ -n "${CHECK:-}" ]] && dpkg -s "${CHECK}" &>/dev/null 2>&1; then
      INSTALLED=true
      if [[ "${IN_MANIFEST}" == true ]] && [[ "${pkg_file}" == *"/apt-repo/"* ]] && ! apt-cache policy "${CHECK}" 2>/dev/null | grep -q 'http'; then
        INACTIVE_REPOS+=("${NAME}")
      fi
    elif [[ -n "${CHECK_CMD:-}" ]] && eval "${CHECK_CMD}" &>/dev/null 2>&1; then
      INSTALLED=true
    fi
    if [[ "${IN_MANIFEST}" == true ]]; then
      if [[ "${INSTALLED}" == true ]]; then
        EXT_INSTALLED=$((EXT_INSTALLED + 1))
      else
        MISSING_NAMES+=("${NAME} (${rel_ext})")
        EXT_MISSING=$((EXT_MISSING + 1))
      fi
    elif [[ "${INSTALLED}" == true ]]; then
      UNTRACKED_NAMES+=("${NAME} (${rel_ext})")
    fi
  done
  [[ "${#UNTRACKED_NAMES[@]}" -gt 0 ]] && warn "${#UNTRACKED_NAMES[@]} external package(s) installed but untracked: ${UNTRACKED_NAMES[*]}"
  [[ "${EXT_MISSING}" -gt 0 ]] && warn "${EXT_MISSING} external package(s) missing: ${MISSING_NAMES[*]}"
  [[ "${#INACTIVE_REPOS[@]}" -gt 0 ]] && warn "${#INACTIVE_REPOS[@]} external APT repo(s) inactive: ${INACTIVE_REPOS[*]}"
  if [[ "${#UNTRACKED_NAMES[@]}" -eq 0 ]] && [[ "${EXT_MISSING}" -eq 0 ]] && [[ "${#INACTIVE_REPOS[@]}" -eq 0 ]]; then
    ok "In sync (${EXT_INSTALLED} external packages active)"
  fi
else
  ok "No external packages defined"
fi

# 6. GNOME Extensions
section "GNOME Extensions"
if [[ -f "${SYSTEM_DIR}/gnome-extensions.txt" ]] && command -v gnome-extensions &>/dev/null; then
  CURRENT_EXT="$(gnome-extensions list --enabled 2>/dev/null | sort || true)"
  MANIFEST_EXT_GNOME="$(grep -v '^#' "${SYSTEM_DIR}/gnome-extensions.txt" | grep -v '^$' | sort || true)"
  MISSING_EXT_GNOME="$(comm -13 <(echo "${CURRENT_EXT}") <(echo "${MANIFEST_EXT_GNOME}") | grep -v '^$' || true)"
  if [[ -n "${MISSING_EXT_GNOME}" ]]; then
    warn "GNOME extension(s) in manifest but not enabled: $(echo "${MISSING_EXT_GNOME}" | tr '\n' ' ')"
  else
    TOTAL="$(grep -c . <<< "${MANIFEST_EXT_GNOME}" || true)"
    ok "In sync (${TOTAL} extensions enabled)"
  fi
else
  ok "GNOME extensions check skipped or not applicable"
fi

# 7. Residual Files
section "Residual Files"
BACKUPS="$(find "${HOME}" -maxdepth 4 -name '*.backup.*' \
  -not -path '*/zero-cloud-gravity/*' -not -path "${WORKSTATION_DIR}/*" -not -path '*/.git/*' 2>/dev/null || true)"
if [[ -n "${BACKUPS}" ]]; then
  COUNT="$(echo "${BACKUPS}" | wc -l)"
  warn "${COUNT} residual backup file(s) in \$HOME"
  if [[ "${MODE}" == "--clean" ]] && confirm "Delete ${COUNT} backup file(s)?"; then
    echo "${BACKUPS}" | while IFS= read -r f; do rm -rf "${f}"; done
    ok "Backup files removed"
  fi
else
  ok "No residual files found"
fi

# 8. Workstation Repo Status
section "Repo Status"
STATUS_LINES="$(git -C "${WORKSTATION_DIR}" status --porcelain 2>/dev/null || true)"
if [[ "${ACTIVE_PROFILE}" != "universal-base" || "${ZCG_INTERACTION_LANG:-en}" != "en" || -n "${ZCG_WORKSTATION_DIR:-}" ]] && [[ "${STATUS_LINES}" == " M antigravity/.gemini/config/AGENTS.md" ]]; then
  ok "Working tree clean (composed global AGENTS.md: profile=${ACTIVE_PROFILE}, lang=${ZCG_INTERACTION_LANG:-en})"
elif [[ -n "${STATUS_LINES}" ]]; then
  warn "Uncommitted changes in ${WORKSTATION_DIR}"
else
  ok "Working tree clean"
fi

echo ""
if [[ "${ISSUES}" -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}OK: Workstation is clean and in sync.${NC}"
  exit 0
else
  echo -e "${YELLOW}${BOLD}WARN: ${ISSUES} issue(s) found.${NC}"
  exit 1
fi
