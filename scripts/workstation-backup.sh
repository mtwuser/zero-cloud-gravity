#!/usr/bin/env bash
# ZeroCloudGravity (v1.0.0) — Ubuntu Physical Workstation State Backup
# Usage: ./scripts/workstation-backup.sh [<workstation-dir>] [--dry-run] [--version] [--help]

set -euo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION_STR="$(tr -d '[:space:]' < "${REPO_DIR}/VERSION" 2>/dev/null || echo "unknown")"

WORKSTATION_DIR=""
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./scripts/workstation-backup.sh [<workstation-dir>] [--dry-run] [--version] [--help]

Captures the current Ubuntu machine's manual APT packages, application Snaps,
NPM globals, NVM default version, active system/external/ recipes, GNOME
extensions, and declarative GNOME dconf settings into <workstation-dir>/system/.
EOF
}

for arg in "$@"; do
  case "${arg}" in
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
EXT_DIR="${SYSTEM_DIR}/external"
if [[ ! -d "${EXT_DIR}" ]]; then
  EXT_DIR="${REPO_DIR}/templates/plugin-stack/workstation-control-tower/assets/external"
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[dry-run] Would capture Ubuntu workstation manifests into ${SYSTEM_DIR}/ (recipes=${EXT_DIR})"
  exit 0
fi

mkdir -p "${SYSTEM_DIR}"
export ZCG_ENGINE_DIR="${REPO_DIR}"

echo "Capturing Ubuntu workstation manifests into ${SYSTEM_DIR}/..."

echo "  -> APT packages (manual only, excluding external, obsolete & machine-local)..."
RAW_APT="$(apt-mark showmanual 2>/dev/null | grep -v '^linux-generic-hwe-' | sort || true)"

UBUNTU_REMOTE="$(grep -h '^Package: ' /var/lib/apt/lists/*ubuntu.com*Packages 2>/dev/null | awk '{print $2}' | sort -u || true)"
if [[ -n "${UBUNTU_REMOTE}" ]] && [[ -n "${RAW_APT}" ]]; then
  RAW_APT="$(awk 'NR==FNR {ok[$1]=1; next} {base=$1; sub(/:.*/, "", base); if (ok[base]) print $1}' <(echo "${UBUNTU_REMOTE}") <(echo "${RAW_APT}"))"
fi

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

if [[ -n "${EXTERNAL_PKGS_SORTED}" ]] && [[ -n "${RAW_APT}" ]]; then
  RAW_APT="$(comm -23 <(echo "${RAW_APT}") <(echo "${EXTERNAL_PKGS_SORTED}") || true)"
fi

if [[ -f "${WORKSTATION_DIR}/.audit-ignore" ]] && [[ -n "${RAW_APT}" ]]; then
  AUDIT_IGNORE="$(grep -v '^#' "${WORKSTATION_DIR}/.audit-ignore" | grep -v '^$' | sort || true)"
  if [[ -n "${AUDIT_IGNORE}" ]]; then
    RAW_APT="$(comm -23 <(echo "${RAW_APT}") <(echo "${AUDIT_IGNORE}") || true)"
  fi
fi

if [[ -n "${RAW_APT}" ]]; then
  echo "${RAW_APT}" > "${SYSTEM_DIR}/packages-manual.txt"
else
  : > "${SYSTEM_DIR}/packages-manual.txt"
fi
echo "    $(wc -l < "${SYSTEM_DIR}/packages-manual.txt") packages"

echo "  -> Snap packages (applications only, excluding base/content runtimes)..."
if command -v snap &>/dev/null; then
  { snap list 2>/dev/null | tail -n +2 | awk '$6 !~ /^(base|snapd)$/ && $1 !~ /^(gnome-[0-9]|gtk-common-themes|mesa-[0-9])/ {print $1}' | sort || true; } > "${SYSTEM_DIR}/snaps.txt"
else
  : > "${SYSTEM_DIR}/snaps.txt"
fi
echo "    $(wc -l < "${SYSTEM_DIR}/snaps.txt") snaps"

echo "  -> NPM globals..."
if ! command -v npm &>/dev/null && [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  export NVM_DIR="${HOME}/.nvm"
  # shellcheck source=/dev/null
  . "${NVM_DIR}/nvm.sh"
fi
if command -v npm &>/dev/null; then
  { npm list -g --depth=0 2>/dev/null | tail -n +2 | sed 's/^[-├└─+` ]*//g' | grep -v '^$' | sort || true; } > "${SYSTEM_DIR}/npm-globals.txt"
else
  : > "${SYSTEM_DIR}/npm-globals.txt"
fi
echo "    $(wc -l < "${SYSTEM_DIR}/npm-globals.txt") packages"

echo "  -> NVM default version..."
cat "${HOME}/.nvm/alias/default" 2>/dev/null > "${SYSTEM_DIR}/nvm-default.txt" || echo "none" > "${SYSTEM_DIR}/nvm-default.txt"
echo "    $(cat "${SYSTEM_DIR}/nvm-default.txt")"

echo "  -> External packages..."
ENABLED_EXT=""
if [[ -d "${EXT_DIR}" ]]; then
  for pkg_file in "${EXT_DIR}"/apt-repo/*.sh "${EXT_DIR}"/deb-url/*.sh "${EXT_DIR}"/script/*.sh; do
    [[ -f "${pkg_file}" ]] || continue
    # shellcheck disable=SC2034
    NAME="" DESCRIPTION="" CHECK="" CHECK_CMD="" URL="" PACKAGES="" INSTALL_CMD=""
    setup_repo() { :; }
    # shellcheck source=/dev/null
    source "${pkg_file}"
    rel_ext="${pkg_file#"${EXT_DIR}"/}"
    if [[ -n "${CHECK:-}" ]] && dpkg -s "${CHECK}" &>/dev/null 2>&1; then
      ENABLED_EXT="${ENABLED_EXT}${rel_ext}"$'\n'
    elif [[ -n "${CHECK_CMD:-}" ]] && eval "${CHECK_CMD}" &>/dev/null 2>&1; then
      ENABLED_EXT="${ENABLED_EXT}${rel_ext}"$'\n'
    fi
  done
fi
if [[ -n "${ENABLED_EXT}" ]]; then
  echo "${ENABLED_EXT}" | grep -v '^$' | sort > "${SYSTEM_DIR}/external.txt"
else
  : > "${SYSTEM_DIR}/external.txt"
fi
echo "    $(wc -l < "${SYSTEM_DIR}/external.txt") external packages"

echo "  -> GNOME extensions..."
if command -v gnome-extensions &>/dev/null; then
  { gnome-extensions list 2>/dev/null | sort || true; } > "${SYSTEM_DIR}/gnome-extensions.txt"
else
  : > "${SYSTEM_DIR}/gnome-extensions.txt"
fi
echo "    $(wc -l < "${SYSTEM_DIR}/gnome-extensions.txt") extensions"

echo "  -> GNOME settings (declarative dconf paths only)..."
dconf dump / 2>/dev/null | awk '
  /^\[/ {
    keep = ($0 ~ /^\[(org\/gnome\/TextEditor|org\/gnome\/desktop\/(input-sources|interface|peripherals\/(keyboard|mouse|touchpad)|privacy|search-providers|session|sound|wm\/preferences)|org\/gnome\/mutter(\/keybindings)?|org\/gnome\/nautilus\/preferences|org\/gnome\/settings-daemon\/plugins\/power|org\/gnome\/shell\/extensions\/(dash-to-dock|ding|tiling-assistant))\]$/)
  }
  keep { print }
' > "${SYSTEM_DIR}/gnome-settings.dconf" || true
echo "    $(wc -l < "${SYSTEM_DIR}/gnome-settings.dconf") lines"

echo "Manifests updated in ${SYSTEM_DIR}/"
