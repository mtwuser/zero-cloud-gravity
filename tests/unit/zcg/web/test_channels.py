"""Unit tests for zcg.web.channels.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from zcg.web.channels import (
    CommPattern,
    DeliveryChannel,
    SSEMessage,
    Tier,
    VersionedPayload,
    Zone,
    build_swap_response_headers,
    encode_sse_comment,
    from_zone_tier,
    get_swap_current_url,
    get_swap_prompt,
    get_swap_target,
    get_swap_trigger,
    heartbeat_sse_stream,
    is_boosted_request,
    is_partial_swap_request,
    is_valid_channel,
    poll_status_code,
)


class TestChannels:
    """Verify 16-channel Zone x Tier matrix, partial-swap headers, SSE framing, and heartbeats."""

    def test_zone_tier_delivery_channel_matrix_and_comm_patterns_expected(self) -> None:
        """Verify all 16 valid channels, Z1xT2..T5 rejection, choices, and CommPattern rules."""
        # Arrange
        expected_zones = ["static", "swap", "island", "immersive"]
        expected_tiers = ["sync", "deferred", "stream", "queued", "pipeline"]

        # Act
        all_channels = list(DeliveryChannel)
        invalid_z1 = [t for t in Tier if t != Tier.T1 and not is_valid_channel(Zone.Z1, t)]
        resolved_swap = from_zone_tier(Zone.Z2, Tier.T2)

        # Assert
        assert Zone.choices() == expected_zones
        assert Tier.choices() == expected_tiers
        assert len(all_channels) == 16
        assert len(invalid_z1) == 4
        assert is_valid_channel(Zone.Z1, Tier.T1) is True
        assert resolved_swap == DeliveryChannel.SWAP_DEFERRED
        assert DeliveryChannel.STATIC_SYNC.zone == Zone.Z1
        assert DeliveryChannel.STATIC_SYNC.tier == Tier.T1
        assert DeliveryChannel.STATIC_SYNC.comm_pattern == CommPattern.REQUEST_RESPONSE
        assert DeliveryChannel.STATIC_SYNC.is_canonical is True
        assert DeliveryChannel.SWAP_DEFERRED.comm_pattern == CommPattern.POLLING
        assert DeliveryChannel.ISLAND_QUEUED.comm_pattern == CommPattern.POLLING
        assert DeliveryChannel.ISLAND_STREAM.comm_pattern == CommPattern.SSE
        assert DeliveryChannel.IMMERSIVE_STREAM.comm_pattern == CommPattern.WEBSOCKET
        assert DeliveryChannel.SWAP_PIPELINE.comm_pattern == CommPattern.SSE
        assert DeliveryChannel.SWAP_PIPELINE.is_canonical is False

        with pytest.raises(ValueError, match="Invalid Zone x Tier combination: Z1 x T2"):
            from_zone_tier(Zone.Z1, Tier.T2)

    def test_partial_swap_headers_and_poll_status_codes_expected(self) -> None:
        """Verify hx-* header extractors, swap response header builder, and HTTP 286 poll stop."""
        # Arrange
        req_headers = {
            "hx-request": "true",
            "hx-boosted": "true",
            "hx-target": "#z2-links",
            "hx-trigger": "refresh-btn",
            "hx-current-url": "http://127.0.0.1:8787/",
            "hx-prompt": "confirm",
        }

        # Act
        resp_full = build_swap_response_headers(
            trigger="saved",
            trigger_after_swap="swapped",
            trigger_after_settle="settled",
            push_url="/updated",
            redirect="/login",
            refresh=True,
            reswap="outerHTML",
            retarget="#main",
            reselect="#card",
        )
        resp_min = build_swap_response_headers()

        # Assert
        assert is_partial_swap_request(req_headers) is True
        assert is_partial_swap_request({}) is False
        assert is_boosted_request(req_headers) is True
        assert get_swap_target(req_headers) == "#z2-links"
        assert get_swap_trigger(req_headers) == "refresh-btn"
        assert get_swap_current_url(req_headers) == "http://127.0.0.1:8787/"
        assert get_swap_prompt(req_headers) == "confirm"
        assert resp_full["hx-refresh"] == "true"
        assert resp_full["hx-reselect"] == "#card"
        assert resp_min == {}
        assert poll_status_code(done=False) == 200
        assert poll_status_code(done=True) == 286

    def test_sse_message_versioned_payload_and_heartbeat_stream_expected(self) -> None:
        """Verify SSE wire framing, multi-line/empty payloads, heartbeats, and shutdown exit."""
        # Arrange
        msg_full = SSEMessage(event="tick", data="line1\nline2", id="42", retry=2500)
        msg_empty = SSEMessage(event="empty", data="")
        v_payload = VersionedPayload(data={"ok": True}, version=123.456789)
        ticks: list[float] = []

        async def _run_streams() -> tuple[list[bytes], list[bytes], list[bytes]]:
            async def _slow_source() -> AsyncIterator[SSEMessage]:
                await asyncio.sleep(0.03)
                yield SSEMessage(event="ready", data={"n": 1})

            out_hb = [
                f
                async for f in heartbeat_sse_stream(
                    _slow_source(), interval=0.005, on_tick=ticks.append
                )
            ]
            stop_mid = asyncio.Event()

            async def _hanging_source() -> AsyncIterator[SSEMessage]:
                await asyncio.sleep(10.0)
                yield msg_empty

            out_no_tick: list[bytes] = []
            async for frame in heartbeat_sse_stream(
                _hanging_source(), interval=0.005, shutdown_event=stop_mid
            ):
                out_no_tick.append(frame)
                stop_mid.set()

            async def _fast_source() -> AsyncIterator[SSEMessage]:
                yield msg_empty

            out_raw = [f async for f in heartbeat_sse_stream(_fast_source(), interval=0.0)]

            stop_ev = asyncio.Event()
            stop_ev.set()
            out_stopped = [
                f
                async for f in heartbeat_sse_stream(
                    _fast_source(), interval=1.0, shutdown_event=stop_ev
                )
            ]
            return [*out_hb, *out_no_tick], out_raw, out_stopped

        # Act
        wire_full = msg_full.encode_wire()
        wire_ver = v_payload.to_sse(event="snapshot", source="node").encode_wire()
        comment = encode_sse_comment("ping")
        hb_frames, raw_frames, stopped_frames = asyncio.run(_run_streams())

        # Assert
        assert wire_full == b"id: 42\nevent: tick\nretry: 2500\ndata: line1\ndata: line2\n\n"
        assert b"id: 123.456789\nevent: snapshot\n" in wire_ver
        assert comment == b": ping\n\n"
        assert any(f == b": heartbeat\n\n" for f in hb_frames)
        assert any(b"event: ready" in f for f in hb_frames)
        assert len(ticks) >= 2
        assert raw_frames == [b"event: empty\ndata: \n\n"]
        assert stopped_frames == []
