#!/usr/bin/env bash
# ZeroCloudGravity (v1.0.1) — Official Google Antigravity Agents, CLI (agy) & IDE Installer/Updater
# Usage: ./scripts/install-antigravity.sh [--agents | --cli | --ide | --all] [--force] [--dry-run] [--version] [--help]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION_STR="$(tr -d '[:space:]' < "${REPO_DIR}/VERSION" 2>/dev/null || echo "unknown")"
DOWNLOADS_DIR="${ANTIGRAVITY_DOWNLOADS_DIR:-${HOME}/Downloads}"
AGENTS_DEST="${ANTIGRAVITY_AGENTS_DEST:-/opt/antigravity-agents}"
IDE_DEST="${ANTIGRAVITY_IDE_DEST:-/opt/antigravity-ide}"
CLI_BIN="${ANTIGRAVITY_CLI_BIN:-${HOME}/.local/bin/agy}"
CLI_INSTALL_URL="https://antigravity.google/cli/install.sh"
CLI_MANIFEST_URL="https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/linux_amd64.json"
HUB_RELEASES_URL="https://antigravity-hub-auto-updater-974169037036.us-central1.run.app/releases"
HUB_BUCKET_BASE="https://storage.googleapis.com/antigravity-public/antigravity-hub"
IDE_RELEASES_URL="https://antigravity-ide-auto-updater-974169037036.us-central1.run.app/releases"
IDE_BUCKET_BASE="https://edgedl.me.gvt1.com/edgedl/release2/j0qc3/antigravity/stable"
DOWNLOAD_PAGE_URL="https://antigravity.google/download"

MODE="interactive"
FORCE=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./scripts/install-antigravity.sh [--agents | --cli | --ide | --all] [--force] [--dry-run] [--version] [--help]

Modes:
  (no flag)      Interactive — prompts before each component
  --agents       (Recommended) Auto-download & install/update Antigravity Agents + agy CLI
  --cli          Install/update Antigravity CLI (agy) only (~/.local/bin/agy)
  --ide          (Optional) Install/update Antigravity IDE only
  --all          Install/update Antigravity Agents, CLI (agy), and optional IDE
  -f, --force    Re-download and reinstall even if the latest version is already installed
  -n, --dry-run  Inspect installed versions and print planned actions without modifying disk
  -v, --version  Show ZeroCloudGravity version
  -h, --help     Show this help message
EOF
}

for arg in "$@"; do
  case "${arg}" in
    interactive|--all|--agents|--cli|--ide) MODE="${arg}" ;;
    -f|--force) FORCE=1 ;;
    -n|--dry-run) DRY_RUN=1 ;;
    -v|--version) echo "zero-cloud-gravity v${VERSION_STR}"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Error: Unknown option '${arg}'." >&2
      usage >&2
      exit 1
      ;;
  esac
done

confirm() {
  if [[ "${MODE}" == "--all" ]] || [[ "${DRY_RUN}" -eq 1 ]]; then return 0; fi
  read -rp "$1 (y/N): " answer
  [[ "${answer}" == "y" ]] || [[ "${answer}" == "Y" ]]
}

ensure_unzip() {
  if ! command -v unzip &>/dev/null; then
    echo "  -> Installing unzip..."
    sudo apt-get update -qq && sudo apt-get install -y -qq unzip
  fi
}

extract_archive() {
  local archive="$1" target_dir="$2"
  echo "  -> Extracting archive: $(basename "${archive}")..."
  rm -rf "${target_dir}" && mkdir -p "${target_dir}"
  case "${archive}" in
    *.zip) ensure_unzip; unzip -q -o "${archive}" -d "${target_dir}" ;;
    *.tar.gz|*.tgz) tar -xzf "${archive}" -C "${target_dir}" ;;
    *) echo "Warning: Unsupported archive format: ${archive}"; return 1 ;;
  esac
}

parse_latest_release_id() {
  python3 -c 'import json,sys; d=json.load(sys.stdin); r=d[0]; print(str(r["version"]) + "-" + str(r["execution_id"]))' 2>/dev/null || true
}

extract_version_from_url() {
  local url="$1"
  echo "${url}" | grep -oE '/[0-9]+\.[0-9]+\.[0-9]+-[0-9]+/' | tr -d '/' | cut -d- -f1 || true
}

read_installed_app_version() {
  local dest="$1" ver=""
  if [[ -f "${dest}/.installed-version" ]]; then
    ver="$(tr -d '[:space:]' < "${dest}/.installed-version" 2>/dev/null || true)"
    [[ -n "${ver}" ]] && { echo "${ver}"; return 0; }
  fi
  if [[ -f "${dest}/resources/app/product.json" ]]; then
    ver="$(python3 -c 'import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text("utf-8")); print(d.get("ideVersion") or "")' "${dest}/resources/app/product.json" 2>/dev/null || true)"
    [[ -n "${ver}" ]] && { echo "${ver}"; return 0; }
  fi
  if [[ -f "${dest}/resources/app/package.json" ]]; then
    ver="$(python3 -c 'import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text("utf-8")).get("version",""))' "${dest}/resources/app/package.json" 2>/dev/null || true)"
    [[ -n "${ver}" ]] && { echo "${ver}"; return 0; }
  fi
  if [[ -f "${dest}/resources/app.asar" ]]; then
    python3 -c 'import json,pathlib,struct,sys; f=pathlib.Path(sys.argv[1]).open("rb"); _,hs,_,js=struct.unpack("<IIII",f.read(16)); h=json.loads(f.read(js).decode("utf-8")); m=h["files"]["package.json"]; f.seek(16+hs-8+int(m["offset"])); print(json.loads(f.read(m["size"]).decode("utf-8")).get("version",""))' "${dest}/resources/app.asar" 2>/dev/null || true
  fi
  return 0
}

if [[ "${DRY_RUN}" -eq 1 ]]; then
  ag_ver="$(read_installed_app_version "${AGENTS_DEST}")"
  ide_ver="$(read_installed_app_version "${IDE_DEST}")"
  cli_ver=""
  [[ -x "${CLI_BIN}" ]] && cli_ver="$("${CLI_BIN}" --version 2>/dev/null | tr -d '[:space:]' || true)"
  echo "[dry-run] Google Antigravity installer (mode=${MODE}, force=${FORCE})"
  echo "  Agents (${AGENTS_DEST}): ${ag_ver:-not-installed}"
  echo "  CLI    (${CLI_BIN}): ${cli_ver:-not-installed}"
  echo "  IDE    (${IDE_DEST}): ${ide_ver:-not-installed}"
  exit 0
fi

resolve_latest_agents_url() {
  local rel_json rel_id url=""
  rel_json="$(curl -fsSL --max-time 10 "${HUB_RELEASES_URL}" 2>/dev/null || true)"
  if [[ -n "${rel_json}" ]]; then
    rel_id="$(parse_latest_release_id <<<"${rel_json}")"
    [[ -n "${rel_id}" ]] && url="${HUB_BUCKET_BASE}/${rel_id}/linux-x64/Antigravity.tar.gz"
  fi
  if [[ -z "${url}" ]]; then
    url="$(curl -fsSL --max-time 10 "${DOWNLOAD_PAGE_URL}" 2>/dev/null | grep -oE 'https://storage\.googleapis\.com/antigravity-public/antigravity-hub/[^"'\'' >]+/linux-x64/Antigravity\.tar\.gz' | head -n 1 || true)"
  fi
  echo "${url}"
}

prepare_agents_src() {
  mkdir -p "${DOWNLOADS_DIR}"
  local latest_url latest_ver installed_ver archive=""
  echo "  -> Checking latest Antigravity Agents release from official feed..." >&2
  latest_url="$(resolve_latest_agents_url)"
  latest_ver="$(extract_version_from_url "${latest_url}")"
  installed_ver="$(read_installed_app_version "${AGENTS_DEST}")"
  if [[ "${FORCE}" -eq 0 ]] && [[ -n "${latest_ver}" ]] && [[ "${installed_ver}" == "${latest_ver}" ]]; then
    echo "ALREADY_INSTALLED:${latest_ver}"
    return 0
  fi
  if [[ -n "${latest_url}" ]]; then
    echo "  -> Downloading Antigravity Agents v${latest_ver:-latest} (${installed_ver:+installed: v${installed_ver} -> }${latest_url})..." >&2
    rm -rf "${DOWNLOADS_DIR}/Antigravity" "${DOWNLOADS_DIR}/Antigravity.zip" "${DOWNLOADS_DIR}/Antigravity.tar.gz" \
           "${DOWNLOADS_DIR}/Antigravity-x64.zip" "${DOWNLOADS_DIR}/Antigravity-x64.tar.gz"
    local curl_dl_flags=(-sSfL)
    [[ -t 2 ]] && curl_dl_flags=(-fL --progress-bar)
    if curl "${curl_dl_flags[@]}" -o "${DOWNLOADS_DIR}/Antigravity.tar.gz.part" "${latest_url}" >&2; then
      mv -f "${DOWNLOADS_DIR}/Antigravity.tar.gz.part" "${DOWNLOADS_DIR}/Antigravity.tar.gz"
    else
      rm -f "${DOWNLOADS_DIR}/Antigravity.tar.gz.part"
      echo "Warning: Automatic download failed; checking ${DOWNLOADS_DIR} for manual archive..." >&2
    fi
  else
    echo "Warning: Could not resolve latest release URL automatically; checking ${DOWNLOADS_DIR}..." >&2
  fi
  for candidate in \
    "${DOWNLOADS_DIR}/Antigravity.zip" \
    "${DOWNLOADS_DIR}/Antigravity.tar.gz" \
    "${DOWNLOADS_DIR}/Antigravity-x64.zip" \
    "${DOWNLOADS_DIR}/Antigravity-x64.tar.gz"; do
    if [[ -f "${candidate}" ]] && { [[ -z "${archive}" ]] || [[ "${candidate}" -nt "${archive}" ]]; }; then
      archive="${candidate}"
    fi
  done
  [[ -n "${archive}" ]] && extract_archive "${archive}" "${DOWNLOADS_DIR}/Antigravity" >&2
  if [[ -d "${DOWNLOADS_DIR}/Antigravity/Antigravity-x64" ]]; then
    echo "${DOWNLOADS_DIR}/Antigravity/Antigravity-x64"
  elif [[ -f "${DOWNLOADS_DIR}/Antigravity/antigravity" ]]; then
    echo "${DOWNLOADS_DIR}/Antigravity"
  else
    echo "${DOWNLOADS_DIR}/Antigravity-x64"
  fi
}

resolve_latest_ide_url() {
  local rel_json rel_id url=""
  rel_json="$(curl -fsSL --max-time 10 "${IDE_RELEASES_URL}" 2>/dev/null || true)"
  if [[ -n "${rel_json}" ]]; then
    rel_id="$(parse_latest_release_id <<<"${rel_json}")"
    [[ -n "${rel_id}" ]] && url="${IDE_BUCKET_BASE}/${rel_id}/linux-x64/Antigravity%20IDE.tar.gz"
  fi
  if [[ -z "${url}" ]]; then
    url="$(curl -fsSL --max-time 10 "${DOWNLOAD_PAGE_URL}" 2>/dev/null \
      | grep -oE 'https://[^"'\'' >]+/linux-x64/Antigravity(%20| )IDE\.tar\.gz' \
      | sed 's/ /%20/g' | head -n 1 || true)"
  fi
  echo "${url}"
}

prepare_ide_src() {
  mkdir -p "${DOWNLOADS_DIR}"
  local latest_url latest_ver installed_ver archive=""
  echo "  -> Checking latest Antigravity IDE release from official feed..." >&2
  latest_url="$(resolve_latest_ide_url)"
  latest_ver="$(extract_version_from_url "${latest_url}")"
  installed_ver="$(read_installed_app_version "${IDE_DEST}")"
  if [[ "${FORCE}" -eq 0 ]] && [[ -n "${latest_ver}" ]] && [[ "${installed_ver}" == "${latest_ver}" ]]; then
    echo "ALREADY_INSTALLED:${latest_ver}"
    return 0
  fi
  if [[ -n "${latest_url}" ]]; then
    echo "  -> Downloading Antigravity IDE v${latest_ver:-latest} (${installed_ver:+installed: v${installed_ver} -> }${latest_url})..." >&2
    rm -rf "${DOWNLOADS_DIR}/Antigravity IDE" "${DOWNLOADS_DIR}/Antigravity IDE.zip" "${DOWNLOADS_DIR}/Antigravity IDE.tar.gz"
    local curl_dl_flags=(-sSfL)
    [[ -t 2 ]] && curl_dl_flags=(-fL --progress-bar)
    if curl "${curl_dl_flags[@]}" -o "${DOWNLOADS_DIR}/Antigravity IDE.tar.gz.part" "${latest_url}" >&2; then
      mv -f "${DOWNLOADS_DIR}/Antigravity IDE.tar.gz.part" "${DOWNLOADS_DIR}/Antigravity IDE.tar.gz"
    else
      rm -f "${DOWNLOADS_DIR}/Antigravity IDE.tar.gz.part"
      echo "Warning: Automatic IDE download failed; checking ${DOWNLOADS_DIR}..." >&2
    fi
  else
    echo "Warning: Could not resolve latest IDE release URL automatically; checking ${DOWNLOADS_DIR}..." >&2
  fi
  for candidate in "${DOWNLOADS_DIR}/Antigravity IDE.zip" "${DOWNLOADS_DIR}/Antigravity IDE.tar.gz"; do
    if [[ -f "${candidate}" ]] && { [[ -z "${archive}" ]] || [[ "${candidate}" -nt "${archive}" ]]; }; then
      archive="${candidate}"
    fi
  done
  if [[ -n "${archive}" ]]; then
    local stage_dir="${DOWNLOADS_DIR}/.antigravity-ide-stage"
    extract_archive "${archive}" "${stage_dir}" >&2
    rm -rf "${DOWNLOADS_DIR}/Antigravity IDE"
    if [[ -d "${stage_dir}/Antigravity IDE" ]]; then
      mv "${stage_dir}/Antigravity IDE" "${DOWNLOADS_DIR}/Antigravity IDE" && rm -rf "${stage_dir}"
    else
      mv "${stage_dir}" "${DOWNLOADS_DIR}/Antigravity IDE"
    fi
  fi
  echo "${DOWNLOADS_DIR}/Antigravity IDE"
}

install_or_update() {
  local name="$1" src="$2" dest="$3" retry_flag="--agents"
  [[ "${name}" == *"IDE"* ]] && retry_flag="--ide"
  if [[ "${src}" == ALREADY_INSTALLED:* ]]; then
    local ver="${src#ALREADY_INSTALLED:}"
    echo "=== ${name} ==="
    echo "  OK: ${name} is already up to date (v${ver} at ${dest}) — skipping download."
    return 0
  fi
  if [[ ! -d "${src}" ]]; then
    echo "Warning: Source not found: ${src}"
    echo "  Download Linux (x64) archive from ${DOWNLOAD_PAGE_URL} into ~/Downloads/ and re-run with ${retry_flag}."
    return 1
  fi
  echo "=== ${name} ==="
  if [[ ! -d "${dest}" ]]; then
    echo "  -> Fresh install (creating ${dest})"
    sudo mkdir -p "${dest}"
  else
    echo "  -> Backing up current installation..."
    sudo rm -rf "${dest}.backup" && sudo cp -r "${dest}" "${dest}.backup"
    sudo rm -rf "${dest:?}"/*
  fi
  sudo cp -r "${src}"/* "${dest}"/
  if [[ -f "${dest}/chrome-sandbox" ]]; then
    sudo chmod 4755 "${dest}/chrome-sandbox"
  fi
  local new_ver
  new_ver="$(read_installed_app_version "${dest}")"
  echo "  OK: ${name} ${new_ver:+v${new_ver} }installed at ${dest}"
}

cleanup_backup() {
  local dest="$1"
  if [[ -d "${dest}.backup" ]]; then
    if confirm "  Remove backup (${dest}.backup)?"; then
      sudo rm -rf "${dest}.backup"
    fi
  fi
}

install_or_update_cli() {
  echo "=== Antigravity CLI (agy) ==="
  mkdir -p "$(dirname "${CLI_BIN}")"
  local installed_cli="" latest_cli=""
  [[ -x "${CLI_BIN}" ]] && installed_cli="$("${CLI_BIN}" --version 2>/dev/null | tr -d '[:space:]' || true)"
  latest_cli="$(curl -fsSL --max-time 10 "${CLI_MANIFEST_URL}" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))' 2>/dev/null || true)"
  if [[ "${FORCE}" -eq 0 ]] && [[ -n "${installed_cli}" ]] && [[ -n "${latest_cli}" ]] && [[ "${installed_cli}" == "${latest_cli}" ]]; then
    echo "  OK: Antigravity CLI (agy) is already up to date (v${installed_cli} at ${CLI_BIN}) — skipping download."
    return 0
  fi
  [[ -f "${CLI_BIN}" ]] && mv -f "${CLI_BIN}" "${CLI_BIN}.backup"
  if curl -fsSL "${CLI_INSTALL_URL}" | bash 2> >(grep -v "^ERROR: logging before google.Init: I" >&2); then
    rm -f "${CLI_BIN}.backup"
    # Clean redundant PATH block appended by upstream installer to stowed shell profiles
    for rc_file in "${HOME}/.bashrc" "${HOME}/.profile"; do
      if [[ -f "${rc_file}" ]] && grep -q "# Added by Antigravity CLI installer" "${rc_file}" 2>/dev/null; then
        python3 -c 'import pathlib,re,sys; p=pathlib.Path(sys.argv[1]).resolve(); t=p.read_text(encoding="utf-8"); p.write_text(re.sub(r"\n*# Added by Antigravity CLI installer\nexport PATH=\"[^\"]*\.local/bin:[$]PATH\"\n*", "\n", t), encoding="utf-8")' "${rc_file}" 2>/dev/null || true
      fi
    done
    echo "  OK: Antigravity CLI (agy) installed/updated at ${CLI_BIN}"
  else
    [[ -f "${CLI_BIN}.backup" ]] && mv -f "${CLI_BIN}.backup" "${CLI_BIN}"
    echo "Warning: Failed to download Antigravity CLI from ${CLI_INSTALL_URL}."
    return 1
  fi
}

if [[ "${MODE}" == "--all" ]] || [[ "${MODE}" == "--agents" ]] || [[ "${MODE}" == "interactive" ]]; then
  if [[ "${MODE}" == "interactive" ]] && ! confirm "Install/update Antigravity Agents (recommended)?"; then
    echo "Skipping Agents."
  else
    AGENTS_SRC="$(prepare_agents_src)"
    install_or_update "Antigravity Agents" "${AGENTS_SRC}" "${AGENTS_DEST}"
    cleanup_backup "${AGENTS_DEST}"
    echo ""
    install_or_update_cli
  fi
fi

if [[ "${MODE}" == "--cli" ]] || { [[ "${MODE}" == "interactive" ]] && [[ ! -f "${CLI_BIN}" ]]; }; then
  if [[ "${MODE}" == "--cli" ]] || confirm "Install/update Antigravity CLI (agy)?"; then
    install_or_update_cli
  fi
fi

if [[ "${MODE}" == "--all" ]] || [[ "${MODE}" == "--ide" ]] || [[ "${MODE}" == "interactive" ]]; then
  if [[ "${MODE}" == "interactive" ]] && ! confirm "Install/update Antigravity IDE (optional)?"; then
    echo "Skipping IDE."
  else
    IDE_SRC="$(prepare_ide_src)"
    install_or_update "Antigravity IDE" "${IDE_SRC}" "${IDE_DEST}"
    cleanup_backup "${IDE_DEST}"
  fi
fi

update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true
echo "Done. Restart running Antigravity instances to apply updates."
