"""Mounted subtree drift inspection, template freshness, and child proposal rollup.

Specification: docs/architecture/02_triadic_topology_and_twin_surfaces.md
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zcg.core.blueprints import is_makefile_outdated, render_layer_makefile
from zcg.core.constants import (
    NODE_MANIFEST_CONTRACT_REV,
    NODE_MANIFEST_REL_PATH,
    REPO_DIR,
    TEMPLATE_MANIFEST_CONTRACT_REV,
)
from zcg.core.manifests import (
    has_stale_schema,
    iter_layer_template_dirs,
    resolve_template_dir,
    sha256_file,
    stamp_schema_rev,
)


def is_git_historical_blob(src_tpl: Path, dest_rf: Path) -> bool:
    """Return True if dest_rf matches any historical git blob in src_tpl's repository."""
    src_repo = next((p for p in src_tpl.parents if (p / ".git").exists()), None)
    if src_repo is None:
        return True
    raw = dest_rf.read_bytes()
    oid = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()
    cmd = [shutil.which("git") or "/usr/bin/git", "-C", str(src_repo), "cat-file", "-e", oid]
    return subprocess.run(cmd, check=False, capture_output=True).returncode == 0  # noqa: S603


def is_dest_template_newer(src_tpl: Path, dest_tpl: Path) -> bool:
    """Return True if dest_tpl has a modified rule file with newer mtime, sha, or local blob."""
    if not (dest_tpl / "rules").is_dir() or not (src_tpl / "rules").is_dir():
        return False
    tj = dest_tpl / "template.json"
    t_dict: dict[str, Any] = json.loads(tj.read_text(encoding="utf-8")) if tj.is_file() else {}
    raw_rec = t_dict.get("reconciled_upstream_sha256")
    rec_map: dict[str, Any] = raw_rec if isinstance(raw_rec, dict) else {}
    for dest_rf in sorted((dest_tpl / "rules").glob("*.md")):
        if dest_rf.is_file() and (src_rf := src_tpl / "rules" / dest_rf.name).is_file():
            dest_sha, src_sha = sha256_file(dest_rf), sha256_file(src_rf)
            rec_sha = rec_map.get(dest_rf.name)
            if dest_sha != src_sha and (
                dest_sha != rec_sha
                if isinstance(rec_sha, str)
                else (
                    dest_rf.stat().st_mtime_ns > src_rf.stat().st_mtime_ns
                    or not is_git_historical_blob(src_tpl, dest_rf)
                )
            ):
                return True
    return False


def inspect_mounted_children_drifts(
    workspace_dir: Path, mounted_layers: list[Any]
) -> list[dict[str, Any]]:
    """Detect contract, Makefile, or shared-template drift inside mounted layers/<child>/."""
    ws, drifts = workspace_dir.resolve(), []
    for entry in (e for e in (mounted_layers or []) if isinstance(e, dict)):
        cname = str(entry.get("name") or entry.get("layer_id") or "").strip()
        mdir = ws / "layers" / cname
        if not cname or not mdir.is_dir():
            continue
        cm_f = mdir / NODE_MANIFEST_REL_PATH
        cm = json.loads(cm_f.read_text(encoding="utf-8")) if cm_f.is_file() else {}
        crole = str(cm.get("layer_role") or entry.get("layer_role") or "department")
        c_files = (
            [NODE_MANIFEST_REL_PATH] if has_stale_schema(cm_f, NODE_MANIFEST_CONTRACT_REV) else []
        )
        if is_makefile_outdated(mdir, crole):
            c_files.append("Makefile")
        for tname, ctdir in iter_layer_template_dirs(mdir):
            if has_stale_schema(tj := ctdir / "template.json", TEMPLATE_MANIFEST_CONTRACT_REV):
                c_files.append(str(tj.relative_to(mdir)).replace("\\", "/"))
            ptdir = resolve_template_dir(ws, tname)
            for src_rf in sorted((ptdir / "rules").glob("*.md")) if ptdir else ():
                dst_rf = ctdir / "rules" / src_rf.name
                if not dst_rf.is_file() or sha256_file(src_rf) != sha256_file(dst_rf):
                    c_files.append(str(dst_rf.relative_to(mdir)).replace("\\", "/"))
        if c_files:
            br = str(entry.get("branch") or "master").strip()
            drifts.append(
                {
                    "layer_id": cname,
                    "mounted_path": f"layers/{cname}",
                    "drift_files": c_files,
                    "subtree_push_command": f"zcg subtree push {cname} {br}",
                    "subtree_pull_command": f"zcg subtree pull {cname}",
                }
            )
    return drifts


def sync_mounted_children_into_parent(
    target_dir: Path, mounted_layers: list[Any], *, dry_run: bool = False
) -> list[str]:
    """Synchronize parent contracts, Makefile, and shared templates into layers/<child>/."""
    ws = target_dir.resolve()
    rem = {
        str(e.get("name") or e.get("layer_id") or "").strip()
        for e in (mounted_layers or [])
        if isinstance(e, dict) and str(e.get("repository") or "").strip()
    }
    drifts = inspect_mounted_children_drifts(ws, mounted_layers)
    synced = [str(d["layer_id"]) for d in drifts if str(d["layer_id"]) not in rem]
    for cname in () if dry_run else synced:
        mdir, cm_f = ws / "layers" / cname, ws / "layers" / cname / NODE_MANIFEST_REL_PATH
        stamp_schema_rev(cm_f, NODE_MANIFEST_CONTRACT_REV)
        cm = json.loads(cm_f.read_text(encoding="utf-8")) if cm_f.is_file() else {}
        cid = str(cm.get("layer_id") or cname)
        crole = str(cm.get("layer_role") or "department")
        if is_makefile_outdated(mdir, crole):
            (mdir / "Makefile").write_text(
                render_layer_makefile(cid, crole, ws, REPO_DIR), encoding="utf-8"
            )
        for tname, ctdir in iter_layer_template_dirs(mdir):
            stamp_schema_rev(ctdir / "template.json", TEMPLATE_MANIFEST_CONTRACT_REV)
            ptdir = resolve_template_dir(ws, tname)
            for src_rf in sorted((ptdir / "rules").glob("*.md")) if ptdir else ():
                dst_rf = ctdir / "rules" / src_rf.name
                dst_rf.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_rf, dst_rf)
                if (ag_rf := mdir / ".agents/rules" / src_rf.name).is_file():
                    shutil.copy2(src_rf, ag_rf)
    p_wt = ws / "WORKTASK.md"
    if not dry_run and p_wt.is_file() and (ws / "layers").is_dir():
        tk_re = re.compile(r"\b([A-Z]{2,12}-\d{2,6}(?:-\d{1,6})?)\b")
        done_tks = {
            m.group(1).lower()
            for cwt in (ws / "layers").glob("*/WORKTASK.md")
            for ln in cwt.read_text(encoding="utf-8").splitlines()
            if re.match(r"^\s*-\s*\[[xX]\]\s+", ln) and (m := tk_re.search(ln))
        }
        p_txt = p_wt.read_text(encoding="utf-8")
        p_lines = [
            re.sub(r"^(\s*-\s*\[)[ /](\])", r"\1x\2", pl).replace(
                "stage: `delegated`", "stage: `completed (pro)`"
            )
            if re.match(r"^\s*-\s*\[[ /]\]\s+", pl)
            and "->" in pl
            and any(tk in pl.lower() for tk in done_tks)
            else pl
            for pl in p_txt.splitlines()
        ]
        for cp in (
            p
            for p in sorted((ws / "layers").glob("*/.agents/proposals/**/*.md"))
            if not p.parent.name.startswith("from-")
        ):
            cname = cp.relative_to(ws / "layers").parts[0]
            rel_p = f".agents/proposals/from-{cname}/{cp.name}"
            (ws / f".agents/proposals/from-{cname}").mkdir(parents=True, exist_ok=True)
            shutil.copy2(cp, ws / rel_p)
            dec_ln = (
                f"- [ ] **[GOVERNANCE DECISION: from-{cname}/{cp.name}]**: "
                f"Review staged child proposal `{rel_p}` via `make decision`"
            )
            if rel_p not in "\n".join(p_lines):
                p_lines.append(dec_ln)
        if (new_p_txt := "\n".join(p_lines) + "\n") != p_txt:
            p_wt.write_text(new_p_txt, encoding="utf-8")
    return synced
