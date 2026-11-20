"""Headless Day-0 onboarding draft store, self-contained prompt resolver, and TTY guide.

Specification: docs/architecture/03_governance_and_work_ledger.md
"""

from __future__ import annotations

import hashlib
import itertools
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from zcg.core import blueprints, constants, manifests

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

ONBOARDING_DRAFT_REL_PATH: Final[str] = ".zcg/runtime/onboarding_draft.json"
MAX_ONBOARDING_DRAFT_CHARS: Final[int] = 16_384
MARKDOWN_DRAFTS_REL_DIR: Final[str] = ".zcg/runtime/md_drafts"
MAX_MARKDOWN_DRAFT_CHARS: Final[int] = 65_536
DRAFT_DIGEST_HEX_LEN: Final[int] = 16
DEFAULT_LOCAL_FALLBACK_PORT: Final[int] = 8750


def _digest_prefix(text: str) -> str:
    full_hex = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return "".join(itertools.islice(full_hex, DRAFT_DIGEST_HEX_LEN))


def canonical_workspace_root_url(
    raw_url: str | None, *, fallback_port: int = DEFAULT_LOCAL_FALLBACK_PORT
) -> str:
    """Normalize a dashboard or localhost URL into its canonical root Workspace URL."""
    cleaned = str(raw_url or "").strip()
    if cleaned:
        parts = urlsplit(cleaned)
        if parts.scheme in ("http", "https") and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}/"
    return f"http://127.0.0.1:{fallback_port}/"


def _synthesize_fallback_prompt(ws_dir: Path, manifest: Mapping[str, Any]) -> str:
    lid = str(manifest.get("layer_id") or ws_dir.name)
    role = str(manifest.get("layer_role") or "project")
    prec = int(manifest.get("precedence", constants.ROLE_DEFAULT_PRECEDENCE.get(role, 80)))
    lang = str(manifest.get("interaction_language") or constants.DEFAULT_INTERACTION_LANGUAGE)
    raw_tpls = manifest.get("default_stack_templates")
    tpls = [str(t) for t in raw_tpls] if isinstance(raw_tpls, list) else []
    rendered = blueprints.render_layer_onboarding_readme(
        lid,
        role,
        prec,
        lid,
        tpls,
        str(manifest.get("upstream_layer_id") or "") or None,
        entity_kind=str(manifest.get("entity_kind") or "") or None,
        interaction_language=lang,
    )
    return blueprints.extract_kickoff_prompt(rendered)


def _read_draft_doc(ws_dir: Path) -> dict[str, Any]:
    draft_path = manifests.ensure_contained_path(ws_dir / ONBOARDING_DRAFT_REL_PATH, ws_dir)
    if not draft_path.is_file():
        return {}
    try:
        parsed = json.loads(draft_path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def inspect_onboarding_studio_state(workspace_dir: Path) -> dict[str, Any]:
    """Inspect Day-0 setup state, default archetype kickoff prompt, and saved draft."""
    ws = workspace_dir.resolve()
    manifest = manifests.load_node_manifest(ws)
    setup_state = blueprints.resolve_workspace_setup_state(ws, manifest)
    lid = str(manifest.get("layer_id") or ws.name)
    default_prompt = str(setup_state["kickoff_prompt"]).strip() or _synthesize_fallback_prompt(
        ws, manifest
    )
    default_digest = _digest_prefix(default_prompt)
    draft_doc = _read_draft_doc(ws)
    saved_prompt = str(draft_doc.get("draft_prompt") or "")
    has_draft = bool(saved_prompt.strip()) and saved_prompt.strip() != default_prompt.strip()
    active_prompt = saved_prompt if saved_prompt.strip() else default_prompt
    return {
        "layer_id": lid,
        "workspace_path": str(ws),
        "setup_state": setup_state["state"],
        "is_configured": bool(setup_state["is_configured"]),
        "entity_kind": setup_state["entity_kind"],
        "layer_role": setup_state["layer_role"],
        "default_prompt": default_prompt,
        "active_prompt": active_prompt,
        "default_digest": default_digest,
        "has_saved_draft": has_draft,
        "updated_at": str(draft_doc.get("updated_at") or ""),
        "open_workspace_cmd": f"cd {ws} && agy",
        "install_agents_cmd": "zcg install-antigravity --agents",
    }


def save_onboarding_draft(workspace_dir: Path, *, prompt_text: str) -> dict[str, Any]:
    """Persist an edited kickoff prompt draft inside gitignored .zcg/runtime/."""
    ws = workspace_dir.resolve()
    cleaned = prompt_text.replace("\r\n", "\n")
    if not cleaned.strip():
        raise ValueError("INVALID_ONBOARDING_DRAFT: prompt_text must not be empty.")
    if len(cleaned) > MAX_ONBOARDING_DRAFT_CHARS:
        raise ValueError(
            f"INVALID_ONBOARDING_DRAFT: exceeds {MAX_ONBOARDING_DRAFT_CHARS} characters."
        )
    base_state = inspect_onboarding_studio_state(ws)
    default_prompt = str(base_state["default_prompt"])
    now_iso = datetime.now(UTC).replace(microsecond=0).isoformat()
    draft_path = manifests.ensure_contained_path(ws / ONBOARDING_DRAFT_REL_PATH, ws)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "layer_id": base_state["layer_id"],
        "draft_prompt": cleaned,
        "default_digest": base_state["default_digest"],
        "updated_at": now_iso,
    }
    draft_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "saved": True,
        "layer_id": base_state["layer_id"],
        "has_saved_draft": cleaned.strip() != default_prompt.strip(),
        "updated_at": now_iso,
        "char_count": len(cleaned),
        "active_prompt": cleaned,
    }


def reset_onboarding_draft(workspace_dir: Path) -> dict[str, Any]:
    """Delete any saved onboarding draft and restore the default archetype kickoff prompt."""
    ws = workspace_dir.resolve()
    draft_path = manifests.ensure_contained_path(ws / ONBOARDING_DRAFT_REL_PATH, ws)
    if draft_path.is_file():
        draft_path.unlink()
    fresh = inspect_onboarding_studio_state(ws)
    return {
        "reset": True,
        "layer_id": fresh["layer_id"],
        "has_saved_draft": False,
        "active_prompt": fresh["default_prompt"],
        "default_digest": fresh["default_digest"],
    }


def _resolve_md_draft_file(ws: Path, draft_key: str) -> Path:
    digest = _digest_prefix(draft_key.strip())
    return manifests.ensure_contained_path(ws / MARKDOWN_DRAFTS_REL_DIR / f"{digest}.json", ws)


def load_markdown_draft(workspace_dir: Path, draft_key: str) -> dict[str, Any]:
    """Load an unapplied Markdown draft from gitignored .zcg/runtime/md_drafts/."""
    clean_key = draft_key.strip()
    empty = {
        "has_draft": False,
        "draft_key": clean_key,
        "content": "",
        "rel_path": "",
        "updated_at": "",
    }
    if not clean_key:
        return empty
    draft_file = _resolve_md_draft_file(workspace_dir.resolve(), clean_key)
    if not draft_file.is_file():
        return empty
    try:
        parsed = json.loads(draft_file.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return empty
    if not isinstance(parsed, dict):
        return empty
    content = str(parsed.get("content") or "")
    if not content.strip():
        return empty
    return {
        "has_draft": True,
        "draft_key": clean_key,
        "content": content,
        "rel_path": str(parsed.get("rel_path") or ""),
        "updated_at": str(parsed.get("updated_at") or ""),
    }


def save_markdown_draft(
    workspace_dir: Path,
    *,
    draft_key: str,
    content: str,
    rel_path: str = "",
) -> dict[str, Any]:
    """Persist an unapplied Markdown editor draft inside gitignored .zcg/runtime/md_drafts/."""
    clean_key = draft_key.strip()
    cleaned = content.replace("\r\n", "\n")
    if not clean_key:
        raise ValueError("INVALID_MARKDOWN_DRAFT: draft_key must not be empty.")
    if not cleaned.strip():
        raise ValueError("INVALID_MARKDOWN_DRAFT: content must not be empty.")
    if len(cleaned) > MAX_MARKDOWN_DRAFT_CHARS:
        raise ValueError(f"INVALID_MARKDOWN_DRAFT: exceeds {MAX_MARKDOWN_DRAFT_CHARS} characters.")
    now_iso = datetime.now(UTC).replace(microsecond=0).isoformat()
    draft_file = _resolve_md_draft_file(workspace_dir.resolve(), clean_key)
    draft_file.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "draft_key": clean_key,
        "rel_path": rel_path.strip(),
        "content": cleaned,
        "updated_at": now_iso,
    }
    draft_file.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "saved": True,
        "draft_key": clean_key,
        "updated_at": now_iso,
        "line_count": len(cleaned.splitlines()),
    }


def discard_markdown_draft(workspace_dir: Path, draft_key: str) -> dict[str, Any]:
    """Delete an unapplied Markdown draft from gitignored .zcg/runtime/md_drafts/ if present."""
    clean_key = draft_key.strip()
    if clean_key:
        draft_file = _resolve_md_draft_file(workspace_dir.resolve(), clean_key)
        if draft_file.is_file():
            draft_file.unlink()
    return {"discarded": True, "draft_key": clean_key}


def format_bootstrap_tty_guide(payload: Mapping[str, Any]) -> str:
    """Format a scannable 3-step Day-0 terminal guide after bootstrapping a node."""
    lid = str(payload.get("layer_id") or "node")
    tdir = str(payload.get("target_dir") or ".")
    prec = int(payload.get("precedence", 50))
    fb_port = constants.DEFAULT_PLUGIN_BASE_PORT + prec
    raw_url = str(payload.get("active_dashboard_url") or payload.get("active_cockpit_url") or "")
    web_url = canonical_workspace_root_url(raw_url, fallback_port=fb_port)
    mode_tag = "dry-run preview" if payload.get("dry_run") else "pending initial setup"
    lines = (
        f"✓ Zero-Cloud Node '{lid}' initialized ({mode_tag})",
        f"  Workspace Path : {tdir}",
        f"  Live Node Web  : {web_url}",
        "",
        "Next steps (Zero-Friction Day-0 Setup):",
        "  1. Open the Node Web Studio first to customize & copy your setup prompt:",
        f"       {web_url}",
        "  2. Optional — install Google Antigravity Agents / CLI if not yet installed:",
        "       zcg install-antigravity --agents",
        "  3. Open this folder in the Antigravity Agents desktop app (IDE optional):",
        f"       Projects -> {tdir} -> New Conversation",
        "     Or start an interactive terminal agent session directly:",
        f"       cd {tdir} && agy",
        "     Paste the copied prompt into your new conversation, then reload",
        f"     {web_url} once Phase D finishes to unlock your configured node.",
    )
    return "\n".join(lines)
