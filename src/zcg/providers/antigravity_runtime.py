"""Headless Google Antigravity runtime detector, ASAR version parser, and online release checker.

Specification: docs/architecture/04_cockpit_and_intranet_surfaces.md
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

from zcg.core.constants import REPO_DIR, SKILLS_MANIFEST_REL_PATH
from zcg.core.manifests import is_oss_root_manifest, load_node_manifest
from zcg.governance.workspace.baseline_fallback import has_global_zcg_baseline
from zcg.topology.posture import resolve_governance_posture

ANTIGRAVITY_RUNTIME_CONTRACT_REV: Final[str] = "zcg-agy-runtime-v1"
DEFAULT_AGENTS_DIR: Final[Path] = Path("/opt/antigravity-agents")
DEFAULT_IDE_DIR: Final[Path] = Path("/opt/antigravity-ide")
HUB_RELEASES_URL: Final[str] = (
    "https://antigravity-hub-auto-updater-974169037036.us-central1.run.app/releases"
)
CLI_MANIFEST_URL: Final[str] = (
    "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/linux_amd64.json"
)
IDE_RELEASES_URL: Final[str] = (
    "https://antigravity-ide-auto-updater-974169037036.us-central1.run.app/releases"
)
DEFAULT_RELEASE_CHECK_TIMEOUT_SEC: Final[float] = 3.0
CLI_VERSION_TIMEOUT_SEC: Final[float] = 2.0
ASAR_HEADER_BYTES: Final[int] = 16
ASAR_DATA_BASE_OFFSET: Final[int] = 8
_SEMVER_SEGMENT_COUNTS: Final[tuple[int, int]] = (2, 3)


def parse_semver_tuple(raw_version: str | None) -> tuple[int, int, int] | None:
    """Parse a 2- or 3-segment SemVer string deterministically without regular expressions."""
    if raw_version is None:
        return None
    cleaned = raw_version.strip()
    if not cleaned:
        return None
    if cleaned[0] in ("v", "V"):
        cleaned = cleaned[1:]
    core = cleaned.split("-", 1)[0].split("+", 1)[0].strip()
    parts = core.split(".")
    if len(parts) not in _SEMVER_SEGMENT_COUNTS or not all(
        p.isascii() and p.isdigit() for p in parts
    ):
        return None
    nums = [int(p) for p in parts]
    return (nums[0], nums[1], nums[2] if len(nums) == 3 else 0)


def _read_json_field(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    val = doc.get(key)
    return val.strip() if isinstance(val, str) and val.strip() else None


def _read_asar_package_version(asar_path: Path) -> str | None:
    if not asar_path.is_file():
        return None
    try:
        with asar_path.open("rb") as fh:
            raw_hdr = fh.read(ASAR_HEADER_BYTES)
            if len(raw_hdr) < ASAR_HEADER_BYTES:
                return None
            _, header_size, _, json_size = struct.unpack("<IIII", raw_hdr)
            header_doc = json.loads(fh.read(json_size).decode("utf-8"))
            pkg_meta = header_doc["files"]["package.json"]
            fh.seek(ASAR_DATA_BASE_OFFSET + header_size + int(pkg_meta["offset"]))
            pkg_doc = json.loads(fh.read(int(pkg_meta["size"])).decode("utf-8"))
            val = pkg_doc.get("version")
            return val.strip() if isinstance(val, str) and val.strip() else None
    except OSError, ValueError, KeyError, TypeError, struct.error:
        return None


def read_installed_bundle_version(bundle_dir: Path) -> str | None:
    """Read installed Antigravity bundle version from marker, product/package JSON, or app.asar."""
    marker = bundle_dir / ".installed-version"
    if marker.is_file():
        try:
            marker_ver = marker.read_text(encoding="utf-8").strip()
        except OSError:
            marker_ver = ""
        if marker_ver:
            return marker_ver
    prod_ver = _read_json_field(bundle_dir / "resources/app/product.json", "ideVersion")
    if prod_ver:
        return prod_ver
    pkg_ver = _read_json_field(bundle_dir / "resources/app/package.json", "version")
    if pkg_ver:
        return pkg_ver
    return _read_asar_package_version(bundle_dir / "resources/app.asar")


def _read_cli_version(cli_bin: Path) -> str | None:
    if not cli_bin.is_file() or not os.access(cli_bin, os.X_OK):
        return None
    try:
        proc = subprocess.run(  # noqa: S603
            [str(cli_bin), "--version"],
            capture_output=True,
            text=True,
            timeout=CLI_VERSION_TIMEOUT_SEC,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if proc.returncode != 0:
        return None
    tokens = proc.stdout.strip().split()
    return tokens[0] if tokens else None


def inspect_local_antigravity_runtime(
    workspace_dir: Path,
    *,
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    ide_dir: Path = DEFAULT_IDE_DIR,
    cli_bin: Path | None = None,
    home_dir: Path | None = None,
    engine_dir: Path = REPO_DIR,
) -> dict[str, Any]:
    """Inspect local Antigravity Agents, CLI, IDE, Stow baseline, and workspace projection."""
    ws = workspace_dir.resolve()
    eff_home = (home_dir or Path.home()).resolve()
    eff_cli = cli_bin or (eff_home / ".local/bin/agy")

    agents_ver = read_installed_bundle_version(agents_dir)
    ide_ver = read_installed_bundle_version(ide_dir)
    cli_ver = _read_cli_version(eff_cli)

    home_stow_coupled = has_global_zcg_baseline(eff_home)
    manifest = load_node_manifest(ws)
    posture = resolve_governance_posture(ws, manifest)
    online_checks_allowed = posture.get("personal_pillar") != "wallet"

    rules_dir, skills_dir = ws / ".agents/rules", ws / ".agents/skills"
    rules_count = sum(1 for _ in rules_dir.glob("*.md")) if rules_dir.is_dir() else 0
    local_sk = (
        {p.parent.name for p in skills_dir.glob("*/SKILL.md")} if skills_dir.is_dir() else set()
    )
    sk_path = ws / SKILLS_MANIFEST_REL_PATH
    try:
        sk_doc = json.loads(sk_path.read_text(encoding="utf-8")) if sk_path.is_file() else None
    except OSError, ValueError:
        sk_doc = None
    raw_en = sk_doc.get("enabled_skills") if isinstance(sk_doc, dict) else None
    en_sk = {s for x in raw_en if (s := str(x).strip())} if isinstance(raw_en, list) else set()
    skills_count = len(local_sk | en_sk)
    has_session_pin = (ws / ".zcg/runtime/session_pin.json").is_file()
    has_sidecar = (ws / ".agents/sidecar.json").is_file()

    installer = f"{engine_dir.resolve()}/scripts/install-antigravity.sh"
    is_workstation_node = (
        manifest.get("layer_role") == "workstation"
        and (ws / "Makefile").is_file()
        and not is_oss_root_manifest(manifest)
    )
    commands: dict[str, str] = {
        "workspace_path": str(ws),
        "open_workspace": f"cd {ws} && agy",
        "update_agents": (
            "make workstation-update-agy" if is_workstation_node else f"{installer} --agents"
        ),
        "update_cli": f"{installer} --cli",
        "update_all": f"{installer} --all",
    }
    return {
        "contract_rev": ANTIGRAVITY_RUNTIME_CONTRACT_REV,
        "any_installed": bool(agents_ver or cli_ver or ide_ver),
        "online_checks_allowed": online_checks_allowed,
        "home_stow_coupled": home_stow_coupled,
        "components": {
            "agents": {
                "label": "Antigravity Agents",
                "path": str(agents_dir),
                "installed": bool(agents_ver),
                "version": agents_ver,
            },
            "cli": {
                "label": "Antigravity CLI (agy)",
                "path": str(eff_cli),
                "installed": bool(cli_ver),
                "version": cli_ver,
            },
            "ide": {
                "label": "Antigravity IDE",
                "path": str(ide_dir),
                "installed": bool(ide_ver),
                "version": ide_ver,
            },
        },
        "workspace_projection": {
            "rules_count": rules_count,
            "skills_count": skills_count,
            "has_session_pin": has_session_pin,
            "has_sidecar": has_sidecar,
        },
        "commands": commands,
    }


def _default_fetch_json(url: str, timeout_sec: float) -> Any:
    if not url.startswith("https://"):
        raise ValueError(f"Only HTTPS release endpoints are allowed: {url!r}")
    with urllib.request.urlopen(url, timeout=timeout_sec) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def check_antigravity_online_releases(
    workspace_dir: Path,
    *,
    local_runtime: Mapping[str, Any] | None = None,
    fetch_json: Callable[[str, float], Any] | None = None,
    timeout_sec: float = DEFAULT_RELEASE_CHECK_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Check official Antigravity HTTPS release endpoints unless blocked by Wallet airlock."""
    loc = (
        dict(local_runtime)
        if local_runtime is not None
        else inspect_local_antigravity_runtime(workspace_dir)
    )
    if not loc.get("online_checks_allowed", True):
        return {
            "checked": False,
            "reason": "WALLET_AIRLOCK_OFFLINE",
            "updates_available": False,
            "components": {},
        }

    fetcher = fetch_json or _default_fetch_json
    raw_comps = loc.get("components")
    loc_comps: Mapping[str, Any] = raw_comps if isinstance(raw_comps, Mapping) else {}
    specs: tuple[tuple[str, str, bool], ...] = (
        ("agents", HUB_RELEASES_URL, True),
        ("cli", CLI_MANIFEST_URL, False),
        ("ide", IDE_RELEASES_URL, True),
    )
    comp_results: dict[str, dict[str, Any]] = {}
    for key, url, is_list in specs:
        raw_entry = loc_comps.get(key)
        entry: Mapping[str, Any] = raw_entry if isinstance(raw_entry, Mapping) else {}
        raw_inst = entry.get("version")
        inst_ver = raw_inst.strip() if isinstance(raw_inst, str) and raw_inst.strip() else None

        latest_ver: str | None = None
        try:
            payload = fetcher(url, timeout_sec)
            item = payload[0] if is_list else payload
            raw_lat = item["version"] if isinstance(item, Mapping) else None
            latest_ver = raw_lat.strip() if isinstance(raw_lat, str) and raw_lat.strip() else None
        except OSError, ValueError, KeyError, IndexError, TypeError:
            latest_ver = None

        if latest_ver is None:
            update_available, status = False, "unreachable"
        elif inst_ver is None:
            update_available, status = False, "not-installed"
        else:
            inst_t, lat_t = parse_semver_tuple(inst_ver), parse_semver_tuple(latest_ver)
            update_available = bool(inst_t is not None and lat_t is not None and inst_t < lat_t)
            status = "update-available" if update_available else "up-to-date"

        comp_results[key] = {
            "installed_version": inst_ver,
            "latest_version": latest_ver,
            "update_available": update_available,
            "status": status,
        }

    any_upd = any(bool(item["update_available"]) for item in comp_results.values())
    return {
        "checked": True,
        "reason": "OK",
        "updates_available": any_upd,
        "components": comp_results,
    }
