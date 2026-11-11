"""Department Bot delegation advisories and Antigravity subagent invocation brief builders.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

from typing import Any

from zcg.capsules.constants import (
    CAPSULE_BRIEF_PREVIEW_CHARS,
    DEFAULT_EPHEMERAL_TTL_SECONDS,
    MAX_BRIEF_INVARIANTS,
)


def extract_ephemeral_advisories(
    resolved_bindings: list[dict[str, Any]], target_path: str
) -> list[dict[str, Any]]:
    """Extract Department Bot delegation advisories from matched surface bindings."""
    advisories, seen_roles = list[dict[str, Any]](), set[str]()
    for binding in resolved_bindings:
        policy = binding.get("ephemeral_fork_policy")
        bot_role = str(policy.get("bot_role", "")).strip() if isinstance(policy, dict) else ""
        if not bot_role or bot_role in seen_roles or not isinstance(policy, dict):
            continue
        seen_roles.add(bot_role)
        call_args = {"action": "evaluate", "bot_role": bot_role, "target_path": target_path or "*"}
        advisories.append(
            {
                "bot_role": bot_role,
                "source_layer": str(binding.get("layer", "root")),
                "source_binding_id": str(binding.get("binding_id", "")),
                "trigger": str(policy.get("trigger", "on_surface_match")),
                "model_tier": str(policy.get("model_tier", "flash")),
                "access_mode": str(policy.get("access_mode", "strictly-read-only")),
                "mount_templates": [str(t) for t in policy.get("mount_templates", [])],
                "resolution": str(policy.get("resolution", "L2")),
                "ttl_seconds": int(policy.get("ttl_seconds", DEFAULT_EPHEMERAL_TTL_SECONDS)),
                "handback_contract": str(policy.get("handback_contract", "4-channel-digest+rcap1")),
                "recommended_mcp_call": {
                    "tool": "orchestrate_ephemeral_fork",
                    "arguments": call_args,
                },
            }
        )
    return advisories


def build_subagent_invocation_brief(
    manifest: dict[str, Any],
    target_path: str,
    surface_projection: dict[str, Any],
    capsule_token: str | None,
) -> dict[str, Any]:
    """Build a deterministic Antigravity invoke_subagent brief with 4-Channel digest contract."""
    meta = manifest.get("ephemeral_metadata", {})
    bot_role = str(meta.get("bot_role", manifest.get("layer_id", "ephemeral-bot")))
    model_tier = str(meta.get("model_tier", "flash"))
    access_mode = str(meta.get("access_mode", "strictly-read-only"))
    invariants = list(surface_projection.get("effective_invariants", []))
    eph_scope = str(meta.get("ephemeral_scope", "intra-layer"))
    actor_role = str(meta.get("actor_role", "member"))
    channels = [
        "1. Domain State",
        "2. Affected Surface",
        "3. Invariants & Constraints",
        "4. Actionable Delta",
    ]
    cap_line = (
        [f"Sealed Capsule: {capsule_token[:CAPSULE_BRIEF_PREVIEW_CHARS]}..."]
        if capsule_token
        else []
    )
    p_lines = [
        f"Bot '{bot_role}' (scope={eph_scope}, role={actor_role}, access={access_mode}).",
        f"Target Surface: {target_path or '*'}\nEnforced Invariants:",
        *(f"- {inv}" for inv in invariants[:MAX_BRIEF_INVARIANTS]),
        "Return ONLY a compact 4-Channel Executive Digest (AGENTS.md §12):",
        *(f"  {ch}" for ch in channels),
        *cap_line,
    ]
    return {
        "subagent_type": "research" if access_mode == "strictly-read-only" else "self",
        "model_tier": model_tier,
        "access_mode": access_mode,
        "role": f"Department Bot ({bot_role})",
        "ephemeral_scope": eph_scope,
        "actor_role": actor_role,
        "target_path": target_path or "*",
        "effective_invariants": invariants,
        "canonical_templates": list(surface_projection.get("canonical_templates", [])),
        "handback_channels": channels,
        "capsule_token": capsule_token,
        "prompt": "\n".join(p_lines),
    }
