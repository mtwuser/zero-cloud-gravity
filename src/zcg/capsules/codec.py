"""Cryptographic rcap1 envelope codec, 4-Channel digest sealing, and DMCP frame verification.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import zlib
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

from zcg.capsules.constants import (
    CAPSULE_PREFIX,
    DEFAULT_EPHEMERAL_TTL_SECONDS,
    DIGEST_REQUIRED_CHANNELS,
    EPOCH_DECIMAL_PLACES,
    MAX_EPHEMERAL_TTL_SECONDS,
    MIN_EPHEMERAL_TTL_SECONDS,
    NEXT_LEVEL_MAP,
    SHA256_BLOCK_BYTES,
    ZLIB_MAX_COMPRESSION_LEVEL,
)
from zcg.core.constants import CAPSULE_DIGEST_HEX_LEN, CAPSULE_HMAC_HEX_LEN


class CapsuleError(ValueError):
    """Raised when an rcap1 context capsule fails verification and has emitted an alert."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(token: str) -> bytes:
    padding = "=" * ((4 - len(token) % 4) % 4)
    return base64.urlsafe_b64decode((token + padding).encode("ascii"))


def compute_digest16(*parts: str) -> str:
    """Compute a 16-hex-char SHA-256 prefix across pipe-delimited string parts."""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:CAPSULE_DIGEST_HEX_LEN]


def derive_chain_key(
    secret: bytes, layer_name: str, level: str, parent_hash: str, env_scope: str
) -> bytes:
    """Derive a per-hop HMAC-SHA256 key bound to layer, level, parent hash, and environment."""
    ctx = f"rcap1-key:{layer_name}:{level}:{parent_hash}:{env_scope}".encode()
    return hmac.new(secret, ctx, hashlib.sha256).digest()


def xor_keystream(data: bytes, key: bytes) -> bytes:
    """Encrypt or decrypt data with a deterministic SHA-256 counter-mode keystream."""
    n_bytes = len(data)
    blocks = (n_bytes + SHA256_BLOCK_BYTES - 1) // SHA256_BLOCK_BYTES
    stream = b"".join(
        hashlib.sha256(key + ctr.to_bytes(4, "big")).digest() for ctr in range(blocks)
    )
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream[:n_bytes], "big")).to_bytes(
        n_bytes, "big"
    )


def seal_single_capsule(header: dict[str, Any], inner_payload: dict[str, Any], key: bytes) -> str:
    """Compress, encrypt, and HMAC-sign a single rcap1 capsule envelope."""
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    raw_inner = json.dumps(inner_payload, separators=(",", ":")).encode("utf-8")
    cipher_b64 = _b64url_encode(
        xor_keystream(zlib.compress(raw_inner, ZLIB_MAX_COMPRESSION_LEVEL), key)
    )
    signing_input = f"{CAPSULE_PREFIX}.{header_b64}.{cipher_b64}".encode("ascii")
    sig_hex = hmac.new(key, signing_input, hashlib.sha256).hexdigest()[:CAPSULE_HMAC_HEX_LEN]
    return f"{CAPSULE_PREFIX}.{header_b64}.{cipher_b64}.{sig_hex}"


def parse_capsule_envelope(capsule_token: str) -> tuple[dict[str, Any], str, bytes, str]:
    """Parse and validate outer rcap1 token framing before cryptographic verification."""
    parts = capsule_token.strip().split(".")
    if len(parts) != 4 or parts[0] != CAPSULE_PREFIX:
        raise ValueError("Malformed rcap1 context capsule envelope")
    _, header_b64, cipher_b64, sig_hex = parts
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        cipher_bytes = _b64url_decode(cipher_b64)
    except Exception as exc:
        raise ValueError(f"Invalid base64 or JSON in rcap1 capsule header: {exc}") from exc
    if not isinstance(header, dict) or header.get("lvl") not in NEXT_LEVEL_MAP:
        raise ValueError("Invalid or unsupported rcap1 capsule header level")
    return header, f"{CAPSULE_PREFIX}.{header_b64}.{cipher_b64}", cipher_bytes, sig_hex


def seal_ephemeral_digest_capsule(
    fork_id: str,
    bot_role: str,
    parent_layer_id: str,
    surface_globs: list[str],
    digest_channels: dict[str, Any],
    *,
    session_key: str,
) -> dict[str, Any]:
    """Seal an Ephemeral Bot's 4-Channel Executive Digest into an rcap1 return capsule."""
    if missing := [ch for ch in DIGEST_REQUIRED_CHANNELS if ch not in digest_channels]:
        raise ValueError(f"Missing required 4-Channel Executive Digest fields: {missing}")
    clean_key = session_key.strip()
    if not clean_key:
        raise ValueError("Missing session_resonance_key for ephemeral digest sealing")
    raw_digest = json.dumps(digest_channels, sort_keys=True, separators=(",", ":"))
    d_hash = compute_digest16(fork_id, bot_role, parent_layer_id, raw_digest)
    ck = derive_chain_key(clean_key.encode("utf-8"), fork_id, "L1", d_hash, parent_layer_id)
    hdr = {
        "v": 1,
        "lvl": "L1",
        "next": "L2",
        "kind": "ephemeral-digest",
        "iss": fork_id,
        "parent_iss": parent_layer_id,
        "role": bot_role,
        "ph": d_hash,
    }
    inner = {
        "fork_id": fork_id,
        "bot_role": bot_role,
        "parent_layer_id": parent_layer_id,
        "surface_globs": list(surface_globs),
        "digest_sha256": d_hash,
        "digest": digest_channels,
    }
    return {
        "capsule_token": seal_single_capsule(hdr, inner, ck),
        "fork_id": fork_id,
        "bot_role": bot_role,
        "parent_layer_id": parent_layer_id,
        "digest_sha256": d_hash,
        "surface_globs": list(surface_globs),
    }


def unseal_ephemeral_digest_capsule(
    capsule_token: str, *, expected_parent_layer_id: str, active_fork_meta: dict[str, Any] | None
) -> dict[str, Any]:
    """Verify and decapsulate an Ephemeral Bot's rcap1 return digest while its lease is active."""
    header, signing_prefix, cipher_bytes, sig_hex = parse_capsule_envelope(capsule_token)
    if (
        header.get("kind") != "ephemeral-digest"
        or header.get("parent_iss") != expected_parent_layer_id
    ):
        raise CapsuleError("CAPSULE_ISSUER_MISMATCH: invalid ephemeral digest parent issuer")
    if active_fork_meta is None or not str(active_fork_meta.get("session_resonance_key", "")):
        raise CapsuleError(
            "EPHEMERAL_LEASE_EXPIRED_OR_SHREDDED: ephemeral fork lease is inactive; "
            "session resonance key has been crypto-shredded"
        )
    fork_id, bot_role, d_hash = str(header["iss"]), str(header["role"]), str(header["ph"])
    s_key = str(active_fork_meta["session_resonance_key"]).strip().encode("utf-8")
    ck = derive_chain_key(s_key, fork_id, "L1", d_hash, expected_parent_layer_id)
    exp_sig = hmac.new(ck, signing_prefix.encode("ascii"), hashlib.sha256).hexdigest()[
        :CAPSULE_HMAC_HEX_LEN
    ]
    if not hmac.compare_digest(sig_hex, exp_sig):
        raise CapsuleError("CAPSULE_SIGNATURE_INVALID: ephemeral digest HMAC verification failed")
    inner = json.loads(zlib.decompress(xor_keystream(cipher_bytes, ck)).decode("utf-8"))
    globs = list(active_fork_meta.get("target_globs") or inner.get("surface_globs") or [])
    ch2 = inner.get("digest", {}).get("channel_2_affected_surface", [])
    files = ch2 if isinstance(ch2, list) else []
    if globs and "**" not in globs:
        for fpath in files:
            p = PurePosixPath(str(fpath).lstrip("/"))
            if not any(p.match(g) or str(p).startswith(g.rstrip("/*")) for g in globs):
                raise CapsuleError(
                    f"SURFACE_BOUNDARY_VIOLATION: reported file {fpath!r} escapes {globs}"
                )
    return {
        "verified": True,
        "fork_id": fork_id,
        "bot_role": bot_role,
        "parent_layer_id": expected_parent_layer_id,
        "digest_sha256": d_hash,
        "surface_globs": globs,
        "digest": inner["digest"],
    }


def orchestrate_ephemeral_return_capsule(
    action: str,
    *,
    fork_id: str | None,
    parent_layer_id: str,
    meta_resolver: Callable[[str, str], dict[str, Any] | None],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Execute seal-return or verify-return for an Ephemeral Bot's 4-Channel Executive Digest."""
    if action == "seal-return":
        if not fork_id:
            raise ValueError("Missing required 'fork_id' for action='seal-return'")
        active_meta = meta_resolver(fork_id, parent_layer_id)
        if active_meta is None:
            raise ValueError(f"EPHEMERAL_FORK_EXPIRED: Cannot seal return for inactive {fork_id!r}")
        digest_raw = arguments.get("digest")
        if not isinstance(digest_raw, dict):
            raise ValueError("Missing or invalid 'digest' dict for action='seal-return'")
        globs = list(active_meta.get("target_globs") or arguments.get("target_globs") or ["**"])
        sealed = seal_ephemeral_digest_capsule(
            fork_id,
            str(active_meta.get("bot_role", "dept-specialist-bot")),
            parent_layer_id,
            globs,
            digest_raw,
            session_key=str(active_meta.get("session_resonance_key", "")),
        )
        return {"action": "seal-return", **sealed}
    token = str(arguments.get("capsule_token") or "").strip()
    if not token:
        raise ValueError("Missing required 'capsule_token' for action='verify-return'")
    header, _, _, _ = parse_capsule_envelope(token)
    active_meta = meta_resolver(fork_id or str(header.get("iss", "")), parent_layer_id)
    unsealed = unseal_ephemeral_digest_capsule(
        token, expected_parent_layer_id=parent_layer_id, active_fork_meta=active_meta
    )
    return {"action": "verify-return", **unsealed}


def seal_dmcp_context_frame(
    repo_id: str,
    branch_ref: str,
    commit_sha: str,
    task_step_id: str,
    surface_globs: list[str],
    *,
    parent_frame_hash: str = "genesis",
    ttl_seconds: int = DEFAULT_EPHEMERAL_TTL_SECONDS,
    now_epoch: float | None = None,
    session_key: str,
) -> dict[str, Any]:
    """Seal a DMCP Decision-Tree Context Frame into an HMAC-signed rcap1 token."""
    c_repo, c_br = repo_id.strip(), branch_ref.strip()
    c_sha, c_step = commit_sha.strip(), task_step_id.strip()
    if not (c_repo and c_br and c_sha and c_step):
        raise ValueError("Missing required DMCP context frame identifiers")
    clean_key = session_key.strip()
    if not clean_key:
        raise ValueError("Missing session_resonance_key for DMCP context frame sealing")
    now = now_epoch if now_epoch is not None else time.time()
    ttl_ep = round(
        now + max(MIN_EPHEMERAL_TTL_SECONDS, min(ttl_seconds, MAX_EPHEMERAL_TTL_SECONDS)),
        EPOCH_DECIMAL_PLACES,
    )
    globs = list(surface_globs) if surface_globs else ["**"]
    p_hash = parent_frame_hash.strip() or "genesis"
    f_hash = compute_digest16(c_repo, c_br, c_sha, c_step, p_hash, ",".join(globs))
    ck = derive_chain_key(clean_key.encode("utf-8"), c_repo, "L1", f_hash, c_br)
    hdr = {
        "v": 1,
        "lvl": "L1",
        "next": "L2",
        "kind": "dmcp-context-frame",
        "iss": c_repo,
        "br": c_br,
        "step": c_step,
        "ph": f_hash,
    }
    inner = {
        "repo_id": c_repo,
        "branch_ref": c_br,
        "commit_sha": c_sha,
        "task_step_id": c_step,
        "parent_frame_hash": p_hash,
        "frame_hash": f_hash,
        "surface_globs": globs,
        "ttl_epoch": ttl_ep,
    }
    return {"context_frame_token": seal_single_capsule(hdr, inner, ck), **inner}


def verify_dmcp_context_frame(
    context_frame_token: str,
    *,
    expected_repo_id: str,
    session_key: str,
    target_path: str = "",
    expected_parent_frame_hash: str | None = None,
    now_epoch: float | None = None,
    fallback_branch: str = "master",
) -> dict[str, Any]:
    """Verify a DMCP rcap1 context_frame_token or fail-closed to fallback_branch."""

    def _fail(reason: str) -> dict[str, Any]:
        return {
            "verified": False,
            "error_code": "DMCP_CONTEXT_FRAME_INVALID",
            "reason": reason,
            "effective_branch_ref": fallback_branch,
            "fallback_activated": True,
        }

    try:
        hdr, signing_prefix, cipher_bytes, sig_hex = parse_capsule_envelope(context_frame_token)
    except ValueError as exc:
        return _fail(str(exc))
    clean_key = session_key.strip()
    if (
        hdr.get("kind") != "dmcp-context-frame"
        or hdr.get("iss") != expected_repo_id.strip()
        or not clean_key
    ):
        return _fail("DMCP frame issuer, kind, or session key mismatch")
    ck = derive_chain_key(
        clean_key.encode("utf-8"),
        str(hdr["iss"]),
        "L1",
        str(hdr.get("ph", "")),
        str(hdr.get("br", "")),
    )
    exp_sig = hmac.new(ck, signing_prefix.encode("ascii"), hashlib.sha256).hexdigest()[
        :CAPSULE_HMAC_HEX_LEN
    ]
    if not hmac.compare_digest(sig_hex, exp_sig):
        return _fail("DMCP context frame HMAC signature verification failed")
    inner = json.loads(zlib.decompress(xor_keystream(cipher_bytes, ck)).decode("utf-8"))
    if (now_epoch if now_epoch is not None else time.time()) > float(inner.get("ttl_epoch", 0.0)):
        return _fail("DMCP context frame TTL expired")
    if (
        expected_parent_frame_hash is not None
        and str(inner.get("parent_frame_hash", "")) != expected_parent_frame_hash.strip()
    ):
        return _fail("DMCP parent_frame_hash lineage mismatch")
    globs = list(inner.get("surface_globs") or ["**"])
    clean_t = target_path.strip().lstrip("/")
    if clean_t and "**" not in globs and "*" not in globs:
        p = PurePosixPath(clean_t)
        if not any(p.match(g) or str(p).startswith(g.rstrip("/*")) for g in globs):
            return _fail(f"Target path {target_path!r} escapes frame surface_globs {globs}")
    return {
        "verified": True,
        "error_code": None,
        "reason": "verified",
        "effective_branch_ref": str(inner["branch_ref"]),
        "fallback_activated": False,
        "repo_id": str(inner["repo_id"]),
        "commit_sha": str(inner["commit_sha"]),
        "task_step_id": str(inner["task_step_id"]),
        "frame_hash": str(inner["frame_hash"]),
        "parent_frame_hash": str(inner["parent_frame_hash"]),
        "surface_globs": globs,
        "ttl_epoch": float(inner["ttl_epoch"]),
    }
