#!/usr/bin/env python3
"""SessionStart hook: inject Zero-Cloud Node orientation badge and immutable context pin.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

_DEFAULT_BASE_PORT: int = 8700
_DEFAULT_PRECEDENCE: int = 80
_MANIFEST_REL: str = "system/zcg-node.json"
_SESSION_PIN_REL: str = ".zcg/runtime/session_pin.json"
_SESSION_PIN_SCHEMA: str = "zcg-session-pin-v1"
_COMMIT_SHORT_LEN: int = 12
_DIGEST_SHORT_LEN: int = 16


def _read_git_head_fast(ws_dir: Path) -> str:
    git_dir = ws_dir / ".git"
    if git_dir.is_file():
        raw_ptr = git_dir.read_text(encoding="utf-8", errors="ignore").strip()
        if raw_ptr.startswith("gitdir:"):
            git_dir = (ws_dir / raw_ptr.removeprefix("gitdir:").strip()).resolve()
    head_file = git_dir / "HEAD"
    if head_file.is_file():
        head_txt = head_file.read_text(encoding="utf-8", errors="ignore").strip()
        if not head_txt.startswith("ref:"):
            return head_txt[:_COMMIT_SHORT_LEN] or "untracked"
        ref_rel = head_txt.removeprefix("ref:").strip()
        ref_file = git_dir / ref_rel
        if ref_file.is_file():
            return ref_file.read_text(encoding="utf-8", errors="ignore").strip()[:_COMMIT_SHORT_LEN]
        packed = git_dir / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.strip().split()
                if len(parts) == 2 and parts[1] == ref_rel:
                    return parts[0][:_COMMIT_SHORT_LEN]
    return os.environ.get("ZCG_GIT_COMMIT", "").strip()[:_COMMIT_SHORT_LEN] or "untracked"


def compute_rules_merkle_digest(ws_dir: Path) -> str:
    """Compute a deterministic 16-hex SHA-256 Merkle digest across active workspace rules."""
    hasher = hashlib.sha256()
    candidates = [
        *sorted((ws_dir / ".agents/rules").glob("*.md")),
        ws_dir / "antigravity/.gemini/config/AGENTS.md",
    ]
    for path in candidates:
        if path.is_file():
            rel = path.relative_to(ws_dir).as_posix()
            with path.open("rb") as handle:
                file_hex = hashlib.file_digest(handle, "sha256").hexdigest()
            hasher.update(f"{rel}:{file_hex}\n".encode())
    return hasher.hexdigest()[:_DIGEST_SHORT_LEN]


def build_session_orientation_payload(
    workspace_paths: list[str],
    *,
    model_id: str = "inherit",
    persist_pin: bool = False,
) -> dict[str, Any]:
    """Build Antigravity 2.0 SessionStart injectSteps payload with immutable context pin."""
    clean_model = model_id.strip() or "inherit"
    for raw_ws in workspace_paths:
        ws_dir = Path(raw_ws)
        manifest_path = ws_dir / _MANIFEST_REL
        if not manifest_path.is_file():
            continue
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            continue
        lid = str(loaded.get("layer_id") or ws_dir.name)
        lrole = str(loaded.get("layer_role") or "project")
        prec = int(loaded.get("precedence", _DEFAULT_PRECEDENCE))
        lang = str(loaded.get("interaction_language") or "en")
        port = int(loaded.get("cockpit_port") or (_DEFAULT_BASE_PORT + prec))
        commit_sha = _read_git_head_fast(ws_dir)
        rules_dig = compute_rules_merkle_digest(ws_dir)
        pin_doc = {
            "schema_version": _SESSION_PIN_SCHEMA,
            "layer_id": lid,
            "git_commit_sha": commit_sha,
            "rules_merkle_digest": rules_dig,
            "model_id": clean_model,
        }
        if persist_pin:
            with contextlib.suppress(OSError):
                pin_path = ws_dir / _SESSION_PIN_REL
                pin_path.parent.mkdir(parents=True, exist_ok=True)
                pin_path.write_text(json.dumps(pin_doc, indent=2) + "\n", encoding="utf-8")
        sys_msg = (
            f"Zero-Cloud Node active: `{lid}` (`{lrole}`, precedence `{prec}`, "
            f"lang `{lang}`, port `:{port}`, pin `{commit_sha}@{rules_dig}`). "
            "Run `make status` first per Specification Hierarchy."
        )
        user_md = (
            f"🧭 **Zero-Cloud Node**: `{lid}` (`{lrole}` · `prec {prec}` · "
            f"`:{port}` · `pin {commit_sha}@{rules_dig}`)"
        )
        return {
            "injectSteps": [
                {
                    "systemMessage": {
                        "systemMessage": sys_msg,
                        "metadata": {"user_markdown": user_md, "session_pin": pin_doc},
                    }
                }
            ]
        }
    return {}


def main() -> None:
    """Read SessionStart JSON from stdin and emit optional orientation step on stdout."""
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {}
    raw_ws = payload.get("workspacePaths") if isinstance(payload, dict) else None
    ws_paths = [str(w) for w in raw_ws] if isinstance(raw_ws, list) else []
    if not ws_paths and isinstance(payload, dict) and payload.get("cwd"):
        ws_paths = [str(payload["cwd"])]
    if not ws_paths:
        ws_paths = [str(Path.cwd())]
    raw_mod = payload.get("model") if isinstance(payload, dict) else None
    eff_mod = str(raw_mod or os.environ.get("ZCG_MODEL_ID") or "inherit")
    persist = "PYTEST_CURRENT_TEST" not in os.environ
    out = build_session_orientation_payload(ws_paths, model_id=eff_mod, persist_pin=persist)
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
