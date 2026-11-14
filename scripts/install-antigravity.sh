#!/usr/bin/env bash
# ZeroCloudGravity (v1.1.0) — Official Google Antigravity Agents, CLI (agy) & IDE Installer/Updater
# Usage: ./scripts/install-antigravity.sh [--agents | --cli | --ide | --all] [--from-archive <file>] [--force] [--dry-run] [--version] [--help]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION_STR="$(tr -d '[:space:]' < "${REPO_DIR}/VERSION" 2>/dev/null || echo "unknown")"
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
ARCHIVE_PATH=""
FORCE=0
DRY_RUN=0
STAGE_ROOT=""

cleanup_stage() {
  if [[ -n "${STAGE_ROOT}" ]] && [[ -d "${STAGE_ROOT}" ]]; then
    rm -rf "${STAGE_ROOT}"
  fi
}
trap cleanup_stage EXIT

usage() {
  cat <<'EOF'
Usage: ./scripts/install-antigravity.sh [--agents | --cli | --ide | --all] [--from-archive <file>] [--force] [--dry-run] [--version] [--help]

Modes:
  (no flag)               Interactive — prompts before each component
  --agents                (Recommended) Auto-download & install/update Antigravity Agents + agy CLI
  --cli                   Install/update Antigravity CLI (agy) only (~/.local/bin/agy)
  --ide                   (Optional) Install/update Antigravity IDE only
  --all                   Install/update Antigravity Agents, CLI (agy), and optional IDE
  --from-archive <file>   Explicit offline install from a local .tar.gz/.tgz/.zip (requires --agents or --ide)
  -f, --force             Re-download and reinstall even if the latest version is already installed
  -n, --dry-run           Inspect installed versions and print planned actions without modifying disk
  -v, --version           Show ZeroCloudGravity version
  -h, --help              Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    interactive|--all|--agents|--cli|--ide) MODE="$1"; shift ;;
    --from-archive)
      [[ $# -ge 2 ]] || { echo "Error: --from-archive requires a file path." >&2; exit 1; }
      ARCHIVE_PATH="$2"
      shift 2
      ;;
    --from-archive=*)
      ARCHIVE_PATH="${1#--from-archive=}"
      shift
      ;;
    -f|--force) FORCE=1; shift ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    -v|--version) echo "zero-cloud-gravity v${VERSION_STR}"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Error: Unknown option '$1'." >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -n "${ARCHIVE_PATH}" ]]; then
  if [[ "${MODE}" != "--agents" ]] && [[ "${MODE}" != "--ide" ]]; then
    echo "Error: --from-archive requires an explicit target flag (--agents or --ide)." >&2
    exit 1
  fi
  if [[ ! -f "${ARCHIVE_PATH}" ]]; then
    echo "Error: Offline archive not found: ${ARCHIVE_PATH}" >&2
    exit 1
  fi
fi

confirm() {
  if [[ "${MODE}" == "--all" ]] || [[ "${DRY_RUN}" -eq 1 ]] || [[ -n "${ARCHIVE_PATH}" ]]; then
    return 0
  fi
  read -rp "$1 (y/N): " answer
  [[ "${answer}" == "y" ]] || [[ "${answer}" == "Y" ]]
}

run_dest_op() {
  local target_dir="$1"
  shift
  local check_dir="${target_dir}"
  while [[ ! -e "${check_dir}" ]] && [[ "${check_dir}" != "/" ]]; do
    check_dir="$(dirname "${check_dir}")"
  done
  if [[ -w "${check_dir}" ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

ensure_unzip() {
  if ! command -v unzip &>/dev/null; then
    echo "  -> Installing unzip..." >&2
    sudo apt-get update -qq && sudo apt-get install -y -qq unzip
  fi
}

extract_archive() {
  local archive="$1" target_dir="$2"
  echo "  -> Extracting archive: $(basename "${archive}")..." >&2
  rm -rf "${target_dir}" && mkdir -p "${target_dir}"
  case "${archive}" in
    *.zip) ensure_unzip; unzip -q -o "${archive}" -d "${target_dir}" ;;
    *.tar.gz|*.tgz) tar -xzf "${archive}" -C "${target_dir}" ;;
    *) echo "Error: Unsupported archive format: ${archive}" >&2; return 1 ;;
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
  echo "[dry-run] Google Antigravity installer (mode=${MODE}, force=${FORCE}, archive=${ARCHIVE_PATH:-none})"
  echo "  Agents (${AGENTS_DEST}): ${ag_ver:-not-installed}"
  echo "  CLI    (${CLI_BIN}): ${cli_ver:-not-installed}"
  echo "  IDE    (${IDE_DEST}): ${ide_ver:-not-installed}"
  exit 0
fi

STAGE_ROOT="$(mktemp -d -t zcg-antigravity-stage.XXXXXX)"

resolve_bundle_root() {
  local extract_dir="$1"
  if [[ -f "${extract_dir}/resources/app/package.json" ]] || [[ -f "${extract_dir}/resources/app.asar" ]]; then
    echo "${extract_dir}"
    return 0
  fi
  local sub
  for sub in "${extract_dir}"/*; do
    if [[ -d "${sub}" ]] && { [[ -f "${sub}/resources/app/package.json" ]] || [[ -f "${sub}/resources/app.asar" ]] || [[ -f "${sub}/antigravity" ]]; }; then
      echo "${sub}"
      return 0
    fi
  done
  echo "${extract_dir}"
}

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

stage_component_src() {
  local label="$1" slug="$2" dest="$3" latest_url="$4"
  local extract_dir="${STAGE_ROOT}/${slug}-extracted"
  if [[ -n "${ARCHIVE_PATH}" ]]; then
    echo "  -> Staging ${label} from offline archive: ${ARCHIVE_PATH}..." >&2
    extract_archive "${ARCHIVE_PATH}" "${extract_dir}"
    resolve_bundle_root "${extract_dir}"
    return 0
  fi
  local latest_ver installed_ver archive_file="${STAGE_ROOT}/${slug}.tar.gz"
  latest_ver="$(extract_version_from_url "${latest_url}")"
  installed_ver="$(read_installed_app_version "${dest}")"
  if [[ "${FORCE}" -eq 0 ]] && [[ -n "${latest_ver}" ]] && [[ "${installed_ver}" == "${latest_ver}" ]]; then
    echo "ALREADY_INSTALLED:${latest_ver}"
    return 0
  fi
  if [[ -z "${latest_url}" ]]; then
    echo "Error: Could not resolve official ${label} release URL (use --from-archive <file> for offline install)." >&2
    return 1
  fi
  echo "  -> Downloading ${label} v${latest_ver:-latest} into ephemeral staging (${installed_ver:+installed: v${installed_ver}})..." >&2
  local curl_dl_flags=(-sSfL)
  [[ -t 2 ]] && curl_dl_flags=(-fL --progress-bar)
  if ! curl "${curl_dl_flags[@]}" -o "${archive_file}" "${latest_url}" >&2; then
    echo "Error: Failed to download ${label} from ${latest_url} (pass --from-archive <file> for offline install)." >&2
    return 1
  fi
  extract_archive "${archive_file}" "${extract_dir}"
  rm -f "${archive_file}"
  local bundle_dir staged_ver
  bundle_dir="$(resolve_bundle_root "${extract_dir}")"
  staged_ver="$(read_installed_app_version "${bundle_dir}")"
  if [[ -n "${latest_ver}" ]] && [[ -n "${staged_ver}" ]] && [[ "${staged_ver}" != "${latest_ver}" ]]; then
    echo "Error: Staged ${label} version (${staged_ver}) does not match expected release (${latest_ver})." >&2
    return 1
  fi
  echo "${bundle_dir}"
}

install_or_update() {
  local name="$1" src="$2" dest="$3"
  if [[ "${src}" == ALREADY_INSTALLED:* ]]; then
    local ver="${src#ALREADY_INSTALLED:}"
    echo "=== ${name} ==="
    echo "  OK: ${name} is already up to date (v${ver} at ${dest}) — skipping download."
    return 0
  fi
  if [[ ! -d "${src}" ]]; then
    echo "Error: Extracted bundle directory not found: ${src}" >&2
    return 1
  fi
  echo "=== ${name} ==="
  if [[ ! -d "${dest}" ]]; then
    echo "  -> Fresh install (creating ${dest})"
    run_dest_op "${dest}" mkdir -p "${dest}"
  else
    echo "  -> Backing up current installation..."
    run_dest_op "${dest}.backup" rm -rf "${dest}.backup"
    run_dest_op "${dest}.backup" cp -r "${dest}" "${dest}.backup"
    run_dest_op "${dest}" find "${dest}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  fi
  run_dest_op "${dest}" cp -r "${src}"/. "${dest}"/
  if [[ -f "${dest}/chrome-sandbox" ]] && [[ ! -w "${dest}" ]]; then
    sudo chmod 4755 "${dest}/chrome-sandbox"
  fi
  local new_ver
  new_ver="$(read_installed_app_version "${src}")"
  if [[ -n "${new_ver}" ]]; then
    if [[ -w "${dest}" ]]; then
      printf '%s\n' "${new_ver}" > "${dest}/.installed-version"
    else
      printf '%s\n' "${new_ver}" | sudo tee "${dest}/.installed-version" >/dev/null
    fi
  fi
  echo "  OK: ${name} ${new_ver:+v${new_ver} }installed at ${dest} (ephemeral staging cleaned)"
}

cleanup_backup() {
  local dest="$1"
  if [[ -d "${dest}.backup" ]]; then
    if confirm "  Remove backup (${dest}.backup)?"; then
      run_dest_op "${dest}.backup" rm -rf "${dest}.backup"
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
    echo "  -> Checking Antigravity Agents release metadata..." >&2
    AGENTS_URL=""
    [[ -z "${ARCHIVE_PATH}" ]] && AGENTS_URL="$(resolve_latest_agents_url)"
    AGENTS_SRC="$(stage_component_src "Antigravity Agents" "agents" "${AGENTS_DEST}" "${AGENTS_URL}")"
    install_or_update "Antigravity Agents" "${AGENTS_SRC}" "${AGENTS_DEST}"
    cleanup_backup "${AGENTS_DEST}"
    if [[ -z "${ARCHIVE_PATH}" ]]; then
      echo ""
      install_or_update_cli
    fi
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
    echo "  -> Checking Antigravity IDE release metadata..." >&2
    IDE_URL=""
    [[ -z "${ARCHIVE_PATH}" ]] && IDE_URL="$(resolve_latest_ide_url)"
    IDE_SRC="$(stage_component_src "Antigravity IDE" "ide" "${IDE_DEST}" "${IDE_URL}")"
    install_or_update "Antigravity IDE" "${IDE_SRC}" "${IDE_DEST}"
    cleanup_backup "${IDE_DEST}"
  fi
fi

if [[ -d "${HOME}/.local/share/applications" ]]; then
  update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true
fi
echo "Done. Restart running Antigravity instances to apply updates."
