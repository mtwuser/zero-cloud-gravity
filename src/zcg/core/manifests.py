"""Node manifest, template catalog, schema stamping, and path-containment helpers.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from zcg.core.constants import (
    GIT_CMD_TIMEOUT_SECONDS,
    INDIVIDUAL_MIN_PRECEDENCE,
    MAX_SKILL_FRONTMATTER_LINES,
    MISSING_VERSION_SENTINEL,
    NODE_MANIFEST_REL_PATH,
    REPO_DIR,
    TEMPLATE_MANIFEST_CONTRACT_REV,
    TEMPLATE_STACK_GROUP_DIRS,
    VALID_KNOWLEDGE_PREFIXES,
    VALID_LAYER_ROLES,
    VALID_TEMPLATE_KINDS,
)


def ensure_contained_path(candidate: Path, workspace_root: Path) -> Path:
    """Resolve candidate and enforce containment inside workspace_root."""
    resolved_root = workspace_root.resolve()
    resolved_target = (
        candidate.resolve() if candidate.is_absolute() else (resolved_root / candidate).resolve()
    )
    if not resolved_target.is_relative_to(resolved_root):
        msg = f"PATH_CONTAINMENT_VIOLATION: '{candidate}' escapes '{resolved_root}'"
        raise ValueError(msg)
    return resolved_target


def read_version(repo_dir: Path | None = None) -> str:
    """Return SemVer string from VERSION file or MISSING_VERSION_SENTINEL."""
    vf = (repo_dir or REPO_DIR) / "VERSION"
    return vf.read_text(encoding="utf-8").strip() if vf.is_file() else MISSING_VERSION_SENTINEL


def read_os_pretty_name(os_release: Path | None = None) -> str:
    """Return human-readable OS release label from /etc/os-release or platform fallback."""
    rf = os_release or Path("/etc/os-release")
    if rf.is_file():
        for line in rf.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    return f"{platform.system()} {platform.release()}"


def is_running_in_container(marker_path: Path | None = None) -> bool:
    """Return True when container marker file exists."""
    return (marker_path or Path("/.dockerenv")).is_file()


def read_git_commit(repo_dir: Path | None = None) -> str:
    """Return short HEAD SHA for repo_dir, ZCG_GIT_COMMIT fallback, or 'unknown'."""
    base_dir = repo_dir or REPO_DIR
    env_fb = os.environ.get("ZCG_GIT_COMMIT", "").strip()
    git_bin = shutil.which("git")
    if not git_bin:
        return env_fb or "unknown"
    with contextlib.suppress(OSError):
        proc = subprocess.run(  # noqa: S603
            [git_bin, "rev-parse", "--short", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=GIT_CMD_TIMEOUT_SECONDS,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    return env_fb or "unknown"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest using C-backed hashlib.file_digest."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load_node_manifest(target_dir: Path) -> dict[str, Any]:
    """Load <target_dir>/system/zcg-node.json as a dict, or {} when absent/non-dict."""
    mpath = target_dir / NODE_MANIFEST_REL_PATH
    loaded = json.loads(mpath.read_text(encoding="utf-8")) if mpath.is_file() else {}
    return loaded if isinstance(loaded, dict) else {}


def is_oss_root_manifest(manifest: dict[str, Any]) -> bool:
    """Return True when manifest represents the Open-Source community root layer."""
    ek = str(manifest.get("entity_kind", "")).strip().lower()
    if ek == "individual" or int(manifest.get("precedence", 0) or 0) >= INDIVIDUAL_MIN_PRECEDENCE:
        return False
    role = str(manifest.get("layer_role", ""))
    return str(manifest.get("layer_id", "")) == "root" or role in ("root", "workstation")


def parse_skill_frontmatter(skill_md: Path, repo_dir: Path | None = None) -> dict[str, Any]:
    """Extract skill name, description, relative path, and line count from SKILL.md."""
    base_dir = repo_dir or REPO_DIR
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    name, description = skill_md.parent.name, ""
    if lines and lines[0].strip() == "---":
        for idx in range(1, min(len(lines), MAX_SKILL_FRONTMATTER_LINES)):
            if lines[idx].strip() == "---":
                fm = "\n".join(lines[1:idx])
                if name_m := re.search(r"^name:\s*(.+)$", fm, re.MULTILINE):
                    name = name_m.group(1).strip().strip("'\"")
                if desc_m := re.search(r"^description:\s*(.+)$", fm, re.MULTILINE):
                    description = desc_m.group(1).strip().strip("'\"")
                break
    return {
        "name": name,
        "description": description,
        "path": str(skill_md.relative_to(base_dir)),
        "line_count": len(lines),
    }


def has_stale_schema(json_file: Path, expected_rev: str) -> bool:
    """Return True when json_file exists and its schema_version or enum fields are stale."""
    if not json_file.is_file():
        return False
    d = json.loads(json_file.read_text(encoding="utf-8"))
    is_tpl = expected_rev == TEMPLATE_MANIFEST_CONTRACT_REV
    return (
        not isinstance(d, dict)
        or d.get("schema_version") != expected_rev
        or (
            is_tpl
            and (
                d.get("kind") not in VALID_TEMPLATE_KINDS
                or d.get("target_role") not in VALID_LAYER_ROLES
            )
        )
    )


def stamp_schema_rev(json_file: Path, expected_rev: str) -> None:
    """Normalize schema_version and template kind/target_role in json_file when stale."""
    if has_stale_schema(json_file, expected_rev):
        raw = json.loads(json_file.read_text(encoding="utf-8"))
        d: dict[str, Any] = {
            **(raw if isinstance(raw, dict) else {}),
            "schema_version": expected_rev,
        }
        if expected_rev == TEMPLATE_MANIFEST_CONTRACT_REV:
            if d.get("kind") not in VALID_TEMPLATE_KINDS:
                grp = json_file.parent.parent.name
                d["kind"] = grp if grp in VALID_TEMPLATE_KINDS else "context-stack"
            if d.get("target_role") not in VALID_LAYER_ROLES:
                d["target_role"] = "department" if d.get("kind") == "context-stack" else "squad"
        json_file.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_rule_file_frontmatter(rule_path: Path, *, sync_in_place: bool = True) -> str:
    """Ensure a Markdown rule file starts with Antigravity 'trigger: always_on' frontmatter."""
    text = rule_path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        return text
    desc = f"Governance rules for {rule_path.stem}"
    for line in text.splitlines():
        if line.startswith("# "):
            desc = line.removeprefix("# ").strip().replace('"', "'")
            break
    updated = f'---\ntrigger: always_on\ndescription: "{desc}"\n---\n{text}'
    if sync_in_place:
        rule_path.write_text(updated, encoding="utf-8")
    return updated


def iter_layer_template_dirs(layer_dir: Path) -> list[tuple[str, Path]]:
    """Return sorted (template_name, template_dir) pairs across root and stack-group folders."""
    templates_root = layer_dir / "templates"
    if not templates_root.is_dir():
        return []
    found: dict[str, Path] = {}
    for d in sorted(templates_root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if d.name in TEMPLATE_STACK_GROUP_DIRS:
            for sub in sorted(d.iterdir()):
                if sub.is_dir() and not sub.name.startswith("."):
                    found.setdefault(sub.name, sub)
        else:
            found[d.name] = d
    return sorted(found.items(), key=lambda item: item[0])


def resolve_template_dir(layer_dir: Path, tpl_ref: str) -> Path | None:
    """Resolve a template pack directory by short name or stack-group relative path."""
    clean = tpl_ref.strip().strip("/")
    if not clean or clean in TEMPLATE_STACK_GROUP_DIRS:
        return None
    t_root, leaf = layer_dir / "templates", clean.split("/")[-1]
    cands = (t_root / clean, t_root / leaf, *(t_root / g / leaf for g in TEMPLATE_STACK_GROUP_DIRS))
    return next((c for c in cands if c.is_dir() and c.name not in TEMPLATE_STACK_GROUP_DIRS), None)


def resolve_template_dest_dir(
    layer_dir: Path, tpl_name: str, *, kind: str | None = None, src_tpl: Path | None = None
) -> Path:
    """Resolve destination directory for creating, syncing, or promoting a template pack."""
    if src_tpl is not None and src_tpl.parent.name in TEMPLATE_STACK_GROUP_DIRS:
        return layer_dir / "templates" / src_tpl.parent.name / tpl_name
    if (existing := resolve_template_dir(layer_dir, tpl_name)) is not None:
        return existing
    if kind in TEMPLATE_STACK_GROUP_DIRS:
        return layer_dir / "templates" / str(kind) / tpl_name
    return layer_dir / "templates" / tpl_name


def discover_layer_template_names(layer_dir: Path) -> list[str]:
    """Return sorted template pack names present under layer_dir/templates."""
    return [name for name, _path in iter_layer_template_dirs(layer_dir)]


def inspect_single_template_dir(
    tpl_dir: Path, layer_dir: Path, source_layer: str
) -> dict[str, Any]:
    """Build catalog metadata dictionary for a single template pack directory."""
    meta_file = tpl_dir / "template.json"
    loaded = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else {}
    meta: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
    rules = [str(p.relative_to(layer_dir)) for p in sorted((tpl_dir / "rules").glob("*.md"))]
    skills = [
        parse_skill_frontmatter(p, layer_dir)
        for p in sorted((tpl_dir / "skills").glob("*/SKILL.md"))
    ]
    gov = [str(p.relative_to(layer_dir)) for p in sorted((tpl_dir / "governance").glob("*.md"))]
    assets_dir = tpl_dir / "assets"
    assets = (
        [str(p.relative_to(layer_dir)) for p in sorted(assets_dir.rglob("*")) if p.is_file()]
        if assets_dir.is_dir()
        else []
    )
    raw_k = str(meta.get("kind", "framework-stack"))
    eff_k = raw_k if raw_k in VALID_TEMPLATE_KINDS else "framework-stack"
    parent_grp = tpl_dir.parent.name if tpl_dir.parent.name in TEMPLATE_STACK_GROUP_DIRS else eff_k
    return {
        "template_name": tpl_dir.name, "source_layer": source_layer, "kind": eff_k,
        "stack_group": str(meta.get("stack_group", parent_grp)), "extends": meta.get("extends"),
        "target_role": str(meta.get("target_role", "squad")),
        "description": str(meta.get("description", f"Template pack {tpl_dir.name}")),
        "upstream_framework": meta.get("upstream_framework"),
        "runtime_service": meta.get("runtime_service"),
        "rules": rules, "skills": skills, "governance_files": gov, "assets": assets,
        "recommended_surface_bindings": list(meta.get("recommended_surface_bindings", [])),
    }  # fmt: skip


def discover_templates_catalog(
    repo_dir: Path, mounted_layers: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Discover all template packs across repo_dir and mounted subtrees."""
    search_targets: list[tuple[str, Path]] = [("root", repo_dir)]
    for entry in mounted_layers or []:
        if rel := str(entry.get("relative_path", "")):
            search_targets.append((str(entry.get("name", rel)), repo_dir / rel))
    return [
        inspect_single_template_dir(tpl_dir, ldir, source_layer)
        for source_layer, ldir in search_targets
        for _tpl_name, tpl_dir in iter_layer_template_dirs(ldir)
    ]


def canonicalize_local_node_url(
    raw_url: str,
    *,
    node_id: str,
    layer_role: str = "department",
    active_env: str = "dev",
    local_dev_zone: str = "",
    fallback_port: int = 0,
) -> str:
    """Upgrade raw 127.0.0.1 loopback URLs to RFC 6761 *.localhost origins."""
    cleaned = raw_url.strip()
    clean_id = node_id.strip()
    if not clean_id or (not cleaned and fallback_port <= 0):
        return ""
    parsed = urlsplit(cleaned) if cleaned else None
    if (
        parsed
        and parsed.scheme in ("http", "https")
        and parsed.hostname
        not in (
            None,
            "127.0.0.1",
            "localhost",
        )
    ):
        return f"{parsed.scheme}://{parsed.netloc}"
    eff_port = (parsed.port if (parsed and parsed.port) else 0) or fallback_port
    if eff_port <= 0:
        return ""
    q_env = parse_qs(parsed.query).get("env", [""])[0] if parsed else ""
    is_pub_know = layer_role == "knowledge" or clean_id.startswith(
        (*VALID_KNOWLEDGE_PREFIXES, "pub-")
    )
    eff_env = q_env or ("pro" if (is_pub_know and active_env == "pro") else active_env)
    clean_slug = clean_id.lower().removeprefix("corp-").removesuffix("-root") or clean_id.lower()
    raw_zone = local_dev_zone.strip().lower().strip(".")
    zone_stem = raw_zone.removesuffix(".localhost")
    ldz = f"{zone_stem}.localhost" if zone_stem else f"{clean_slug}.localhost"
    is_root = layer_role in ("corporate", "workstation") or zone_stem == clean_slug
    root_host = ldz if (zone_stem and zone_stem in clean_slug) else f"{clean_slug}.localhost"
    node_host = (
        root_host
        if is_root
        else (f"{clean_id.lower()}.localhost" if is_pub_know else f"{clean_id.lower()}.{ldz}")
    )
    sub_host = node_host if eff_env == "pro" else f"{eff_env}.{node_host}"
    return f"http://{sub_host}:{eff_port}"
