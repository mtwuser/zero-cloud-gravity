"""Unit tests for zcg.capsules.codec.

Specification: docs/architecture/05_contextual_mcp_and_capsules.md
"""

from __future__ import annotations

import base64
import json

import pytest

from zcg.capsules.codec import (
    CapsuleError,
    orchestrate_ephemeral_return_capsule,
    parse_capsule_envelope,
    seal_dmcp_context_frame,
    seal_ephemeral_digest_capsule,
    unseal_ephemeral_digest_capsule,
    verify_dmcp_context_frame,
)


def _sample_digest(files: list[str] | str | None = None) -> dict[str, object]:
    return {
        "channel_1_domain_state": "Clean topology",
        "channel_2_affected_surface": ["docs/spec.md"] if files is None else files,
        "channel_3_invariants_and_constraints": ["1:1:1 symmetry"],
        "channel_4_actionable_delta": "Ready",
    }


class TestCapsuleCodec:
    """Verify rcap1 cryptographic envelopes, 4-Channel digests, and DMCP context frames."""

    def test_parse_capsule_envelope_rejects_malformed_headers_and_levels(self) -> None:
        """Raise ValueError on malformed envelopes, invalid base64/JSON, or unsupported levels."""
        # Arrange
        bad_lvl = base64.urlsafe_b64encode(json.dumps({"lvl": "L9"}).encode()).decode().rstrip("=")

        # Act
        with pytest.raises(ValueError, match="Malformed rcap1"):
            parse_capsule_envelope("bad.token")
        with pytest.raises(ValueError, match="Invalid base64 or JSON"):
            parse_capsule_envelope("rcap1.!!!.YWJj.deadbeef")
        # Assert
        with pytest.raises(ValueError, match="Invalid or unsupported"):
            parse_capsule_envelope(f"rcap1.{bad_lvl}.YWJj.deadbeef")

    def test_ephemeral_digest_seal_and_unseal_nominal_and_guard_branches(self) -> None:
        """Seal and unseal 4-Channel digests while enforcing fields, keys, HMAC, and globs."""
        # Arrange
        meta = {"session_resonance_key": "sec-key-1", "target_globs": ["docs/**"]}
        sealed = seal_ephemeral_digest_capsule(
            "eph-1",
            "dept-specialist-bot",
            "root-node",
            ["docs/**"],
            _sample_digest(),
            session_key="sec-key-1",
        )
        non_list_sealed = seal_ephemeral_digest_capsule(
            "eph-1",
            "dept-specialist-bot",
            "root-node",
            ["**"],
            _sample_digest("not-a-list"),
            session_key="sec-key-1",
        )
        escape_sealed = seal_ephemeral_digest_capsule(
            "eph-1",
            "dept-specialist-bot",
            "root-node",
            ["docs/**"],
            _sample_digest(["src/escape.py"]),
            session_key="sec-key-1",
        )

        # Act
        verified = unseal_ephemeral_digest_capsule(
            sealed["capsule_token"], expected_parent_layer_id="root-node", active_fork_meta=meta
        )
        wildcard_ok = unseal_ephemeral_digest_capsule(
            non_list_sealed["capsule_token"],
            expected_parent_layer_id="root-node",
            active_fork_meta={"session_resonance_key": "sec-key-1"},
        )

        # Assert
        assert verified["verified"] is True
        assert wildcard_ok["verified"] is True
        with pytest.raises(ValueError, match="Missing required 4-Channel"):
            seal_ephemeral_digest_capsule("f", "r", "p", [], {}, session_key="k")
        with pytest.raises(ValueError, match="Missing session_resonance_key"):
            seal_ephemeral_digest_capsule("f", "r", "p", [], _sample_digest(), session_key=" ")
        with pytest.raises(CapsuleError, match="CAPSULE_ISSUER_MISMATCH"):
            unseal_ephemeral_digest_capsule(
                sealed["capsule_token"], expected_parent_layer_id="other", active_fork_meta=meta
            )
        with pytest.raises(CapsuleError, match="EPHEMERAL_LEASE_EXPIRED_OR_SHREDDED"):
            unseal_ephemeral_digest_capsule(
                sealed["capsule_token"], expected_parent_layer_id="root-node", active_fork_meta=None
            )
        with pytest.raises(CapsuleError, match="CAPSULE_SIGNATURE_INVALID"):
            unseal_ephemeral_digest_capsule(
                sealed["capsule_token"],
                expected_parent_layer_id="root-node",
                active_fork_meta={"session_resonance_key": "wrong-key"},
            )
        with pytest.raises(CapsuleError, match="SURFACE_BOUNDARY_VIOLATION"):
            unseal_ephemeral_digest_capsule(
                escape_sealed["capsule_token"],
                expected_parent_layer_id="root-node",
                active_fork_meta=meta,
            )

    def test_orchestrate_ephemeral_return_capsule_roundtrip_and_errors(self) -> None:
        """Orchestrate seal-return and verify-return actions across active and invalid states."""
        # Arrange
        meta = {
            "bot_role": "dept-specialist-bot",
            "session_resonance_key": "res-key",
            "target_globs": [],
        }
        resolver = lambda fid, pid: meta if fid == "eph-9" and pid == "root" else None  # noqa: E731

        # Act
        sealed = orchestrate_ephemeral_return_capsule(
            "seal-return",
            fork_id="eph-9",
            parent_layer_id="root",
            meta_resolver=resolver,
            arguments={"digest": _sample_digest()},
        )
        verified = orchestrate_ephemeral_return_capsule(
            "verify-return",
            fork_id=None,
            parent_layer_id="root",
            meta_resolver=resolver,
            arguments={"capsule_token": sealed["capsule_token"]},
        )

        # Assert
        assert sealed["action"] == "seal-return"
        assert verified["action"] == "verify-return"
        with pytest.raises(ValueError, match="Missing required 'fork_id'"):
            orchestrate_ephemeral_return_capsule(
                "seal-return",
                fork_id=None,
                parent_layer_id="root",
                meta_resolver=resolver,
                arguments={},
            )
        with pytest.raises(ValueError, match="EPHEMERAL_FORK_EXPIRED"):
            orchestrate_ephemeral_return_capsule(
                "seal-return",
                fork_id="dead",
                parent_layer_id="root",
                meta_resolver=resolver,
                arguments={},
            )
        with pytest.raises(ValueError, match="Missing or invalid 'digest'"):
            orchestrate_ephemeral_return_capsule(
                "seal-return",
                fork_id="eph-9",
                parent_layer_id="root",
                meta_resolver=resolver,
                arguments={},
            )
        with pytest.raises(ValueError, match="Missing required 'capsule_token'"):
            orchestrate_ephemeral_return_capsule(
                "verify-return",
                fork_id="eph-9",
                parent_layer_id="root",
                meta_resolver=resolver,
                arguments={},
            )

    def test_dmcp_context_frame_seal_and_verify_all_fail_closed_branches(self) -> None:
        """Seal DMCP frames and verify nominal plus fail-closed HMAC, TTL, and glob checks."""
        # Arrange
        frame = seal_dmcp_context_frame(
            "repo-a",
            "specialty/sec",
            "abcdef1234",
            "step-1",
            ["docs/**"],
            parent_frame_hash="",
            ttl_seconds=60,
            now_epoch=1000.0,
            session_key="dmcp-sec",
        )
        default_globs_frame = seal_dmcp_context_frame(
            "repo-a",
            "specialty/sec",
            "abcdef1234",
            "step-2",
            [],
            now_epoch=None,
            session_key="dmcp-sec",
        )

        # Act
        ok = verify_dmcp_context_frame(
            frame["context_frame_token"],
            expected_repo_id="repo-a",
            session_key="dmcp-sec",
            target_path="docs/spec.md",
            expected_parent_frame_hash="genesis",
            now_epoch=1010.0,
        )
        ok_default_clock = verify_dmcp_context_frame(
            default_globs_frame["context_frame_token"],
            expected_repo_id="repo-a",
            session_key="dmcp-sec",
        )
        bad_env = verify_dmcp_context_frame(
            "bad", expected_repo_id="repo-a", session_key="dmcp-sec"
        )
        bad_iss = verify_dmcp_context_frame(
            frame["context_frame_token"], expected_repo_id="other", session_key="dmcp-sec"
        )
        bad_sig = verify_dmcp_context_frame(
            frame["context_frame_token"], expected_repo_id="repo-a", session_key="wrong"
        )
        expired = verify_dmcp_context_frame(
            frame["context_frame_token"],
            expected_repo_id="repo-a",
            session_key="dmcp-sec",
            now_epoch=2000.0,
        )
        bad_parent = verify_dmcp_context_frame(
            frame["context_frame_token"],
            expected_repo_id="repo-a",
            session_key="dmcp-sec",
            expected_parent_frame_hash="other-hash",
            now_epoch=1010.0,
        )
        escaped = verify_dmcp_context_frame(
            frame["context_frame_token"],
            expected_repo_id="repo-a",
            session_key="dmcp-sec",
            target_path="src/secret.py",
            now_epoch=1010.0,
        )

        # Assert
        assert ok["verified"] is True
        assert ok_default_clock["verified"] is True
        for failed in (bad_env, bad_iss, bad_sig, expired, bad_parent, escaped):
            assert failed["verified"] is False
            assert failed["fallback_activated"] is True
        with pytest.raises(ValueError, match="Missing required DMCP"):
            seal_dmcp_context_frame("", "b", "c", "s", [], session_key="k")
        with pytest.raises(ValueError, match="Missing session_resonance_key"):
            seal_dmcp_context_frame("r", "b", "c", "s", [], session_key=" ")
