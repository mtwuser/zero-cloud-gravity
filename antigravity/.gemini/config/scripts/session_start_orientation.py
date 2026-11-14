#!/usr/bin/env python3
"""SessionStart hook: inject concise Zero-Cloud Node orientation badge and systemMessage.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_DEFAULT_BASE_PORT: int = 8700
_DEFAULT_PRECEDENCE: int = 80
_MANIFEST_REL: str = "system/zcg-node.json"


def build_session_orientation_payload(workspace_paths: list[str]) -> dict[str, Any]:
    """Build Antigravity 2.0 SessionStart injectSteps payload from the first node workspace."""
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
        sys_msg = (
            f"Zero-Cloud Node active: `{lid}` (`{lrole}`, precedence `{prec}`, "
            f"lang `{lang}`, port `:{port}`). Run `make status` first per Specification Hierarchy."
        )
        user_md = f"🧭 **Zero-Cloud Node**: `{lid}` (`{lrole}` · `prec {prec}` · `:{port}`)"
        return {
            "injectSteps": [
                {
                    "systemMessage": {
                        "systemMessage": sys_msg,
                        "metadata": {"user_markdown": user_md},
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
    json.dump(build_session_orientation_payload(ws_paths), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
