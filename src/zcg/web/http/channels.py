"""16-channel Zone x Tier DeliveryChannel, partial-swap, and SSE wire contracts.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from http import HTTPStatus
from typing import Any

HTTP_POLL_STOP_STATUS: int = 286
CHANNEL_HEADER: str = "x-zcg-delivery-channel"

HX_REQUEST: str = "hx-request"
HX_BOOSTED: str = "hx-boosted"
HX_TARGET: str = "hx-target"
HX_TRIGGER: str = "hx-trigger"
HX_TRIGGER_NAME: str = "hx-trigger-name"
HX_CURRENT_URL: str = "hx-current-url"
HX_PROMPT: str = "hx-prompt"

HX_RESP_TRIGGER: str = "hx-trigger"
HX_RESP_TRIGGER_AFTER_SWAP: str = "hx-trigger-after-swap"
HX_RESP_TRIGGER_AFTER_SETTLE: str = "hx-trigger-after-settle"
HX_RESP_PUSH_URL: str = "hx-push-url"
HX_RESP_REDIRECT: str = "hx-redirect"
HX_RESP_REFRESH: str = "hx-refresh"
HX_RESP_RESWAP: str = "hx-reswap"
HX_RESP_RETARGET: str = "hx-retarget"
HX_RESP_RESELECT: str = "hx-reselect"


class BaseStrEnum(StrEnum):
    """String enumeration base providing deterministic choice lists for schemas and forms."""

    @classmethod
    def choices(cls) -> list[str]:
        """Return all enumeration member values in declaration order."""
        return [member.value for member in cls]


class Zone(BaseStrEnum):
    """Presentation medium across Z1..Z4."""

    Z1 = "static"
    Z2 = "swap"
    Z3 = "island"
    Z4 = "immersive"


class Tier(BaseStrEnum):
    """Processing execution tier across T1..T5."""

    T1 = "sync"
    T2 = "deferred"
    T3 = "stream"
    T4 = "queued"
    T5 = "pipeline"


class CommPattern(BaseStrEnum):
    """Transport communication pattern derived from Zone x Tier."""

    REQUEST_RESPONSE = "request_response"
    POLLING = "polling"
    SSE = "sse"
    WEBSOCKET = "websocket"


_ZONE_BY_VALUE: dict[str, Zone] = {z.value: z for z in Zone}
_TIER_BY_VALUE: dict[str, Tier] = {t.value: t for t in Tier}
_CANONICAL_CHANNELS: frozenset[str] = frozenset(
    {
        "static_sync",
        "swap_sync",
        "swap_deferred",
        "island_stream",
        "immersive_stream",
        "immersive_queued",
    }
)


class DeliveryChannel(BaseStrEnum):
    """All 16 valid Zone x Tier delivery channels for Zero-Cloud web applications."""

    STATIC_SYNC = "static_sync"

    SWAP_SYNC = "swap_sync"
    SWAP_DEFERRED = "swap_deferred"
    SWAP_STREAM = "swap_stream"
    SWAP_QUEUED = "swap_queued"
    SWAP_PIPELINE = "swap_pipeline"

    ISLAND_SYNC = "island_sync"
    ISLAND_DEFERRED = "island_deferred"
    ISLAND_STREAM = "island_stream"
    ISLAND_QUEUED = "island_queued"
    ISLAND_PIPELINE = "island_pipeline"

    IMMERSIVE_SYNC = "immersive_sync"
    IMMERSIVE_DEFERRED = "immersive_deferred"
    IMMERSIVE_STREAM = "immersive_stream"
    IMMERSIVE_QUEUED = "immersive_queued"
    IMMERSIVE_PIPELINE = "immersive_pipeline"

    @property
    def zone(self) -> Zone:
        """Presentation Zone component of the channel."""
        prefix, _, _ = self.value.partition("_")
        return _ZONE_BY_VALUE[prefix]

    @property
    def tier(self) -> Tier:
        """Processing Tier component of the channel."""
        _, _, suffix = self.value.partition("_")
        return _TIER_BY_VALUE[suffix]

    @property
    def comm_pattern(self) -> CommPattern:
        """Derived communication pattern for this Zone x Tier intersection."""
        t = self.tier
        if t == Tier.T1:
            return CommPattern.REQUEST_RESPONSE
        if t == Tier.T3:
            return CommPattern.WEBSOCKET if self.zone == Zone.Z4 else CommPattern.SSE
        if t in (Tier.T2, Tier.T4):
            return CommPattern.POLLING
        return CommPattern.SSE

    @property
    def is_canonical(self) -> bool:
        """Return True when the channel sits on the canonical Zone x Tier diagonal."""
        return self.value in _CANONICAL_CHANNELS


_VALID_COMBINATIONS: frozenset[tuple[Zone, Tier]] = frozenset(
    (ch.zone, ch.tier) for ch in DeliveryChannel
)


def is_valid_channel(zone: Zone, tier: Tier) -> bool:
    """Return True if (zone, tier) maps to a valid DeliveryChannel."""
    return (zone, tier) in _VALID_COMBINATIONS


def from_zone_tier(zone: Zone, tier: Tier) -> DeliveryChannel:
    """Resolve a DeliveryChannel from Zone and Tier, raising ValueError on Z1 x T2..T5."""
    try:
        return DeliveryChannel(f"{zone.value}_{tier.value}")
    except ValueError:
        raise ValueError(f"Invalid Zone x Tier combination: {zone.name} x {tier.name}") from None


def is_partial_swap_request(headers: Mapping[str, str]) -> bool:
    """Return True when lowercase request headers indicate a partial DOM swap (hx-request)."""
    return headers.get(HX_REQUEST) == "true"


def is_boosted_request(headers: Mapping[str, str]) -> bool:
    """Return True when lowercase request headers indicate boosted navigation (hx-boosted)."""
    return headers.get(HX_BOOSTED) == "true"


def get_swap_target(headers: Mapping[str, str]) -> str | None:
    """Return target element selector/ID from hx-target, if present."""
    return headers.get(HX_TARGET)


def get_swap_trigger(headers: Mapping[str, str]) -> str | None:
    """Return triggering element ID from hx-trigger, if present."""
    return headers.get(HX_TRIGGER)


def get_swap_current_url(headers: Mapping[str, str]) -> str | None:
    """Return browser current URL from hx-current-url, if present."""
    return headers.get(HX_CURRENT_URL)


def get_swap_prompt(headers: Mapping[str, str]) -> str | None:
    """Return prompt input from hx-prompt, if present."""
    return headers.get(HX_PROMPT)


def build_swap_response_headers(
    *,
    trigger: str | None = None,
    trigger_after_swap: str | None = None,
    trigger_after_settle: str | None = None,
    push_url: str | None = None,
    redirect: str | None = None,
    refresh: bool = False,
    reswap: str | None = None,
    retarget: str | None = None,
    reselect: str | None = None,
) -> dict[str, str]:
    """Build deterministic partial-swap response control headers."""
    pairs = (
        (HX_RESP_TRIGGER, trigger),
        (HX_RESP_TRIGGER_AFTER_SWAP, trigger_after_swap),
        (HX_RESP_TRIGGER_AFTER_SETTLE, trigger_after_settle),
        (HX_RESP_PUSH_URL, push_url),
        (HX_RESP_REDIRECT, redirect),
        (HX_RESP_RESWAP, reswap),
        (HX_RESP_RETARGET, retarget),
        (HX_RESP_RESELECT, reselect),
    )
    out = {k: val for k, val in pairs if val is not None}
    return {**out, HX_RESP_REFRESH: "true"} if refresh else out


def poll_status_code(*, done: bool) -> int:
    """Return HTTP 286 to terminate polling when done=True, else HTTP 200."""
    return HTTP_POLL_STOP_STATUS if done else int(HTTPStatus.OK)


@dataclass(frozen=True)
class SSEMessage:
    """Immutable Server-Sent Event frame with W3C EventStream wire serialization."""

    event: str = "message"
    data: Any = ""
    id: str | None = None
    retry: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize SSE fields into a minimal dictionary."""
        raw = self.data if isinstance(self.data, str) else json.dumps(self.data, default=str)
        base: dict[str, Any] = {"event": self.event, "data": raw}
        with_id = {**base, "id": self.id} if self.id is not None else base
        return {**with_id, "retry": self.retry} if self.retry is not None else with_id

    def encode_wire(self) -> bytes:
        """Encode the SSE message into UTF-8 W3C text/event-stream wire bytes."""
        d = self.to_dict()
        lines: list[str] = []
        if "id" in d:
            lines.append(f"id: {d['id']}")
        lines.append(f"event: {d['event']}")
        if "retry" in d:
            lines.append(f"retry: {d['retry']}")
        for line in str(d["data"]).splitlines() or [""]:
            lines.append(f"data: {line}")
        return ("\n".join(lines) + "\n\n").encode("utf-8")


@dataclass(frozen=True)
class VersionedPayload:
    """Monotonic versioned SSE payload preventing out-of-order client state overwrites."""

    data: Any = None
    version: float = field(default_factory=time.time)

    def to_sse(self, event: str = "update", source: str = "server") -> SSEMessage:
        """Wrap the versioned payload into a typed SSEMessage."""
        return SSEMessage(
            event=event,
            data={"version": self.version, "data": self.data, "source": source},
            id=f"{self.version:.6f}",
        )


def encode_sse_comment(comment: str = "heartbeat") -> bytes:
    """Encode an SSE comment keepalive frame (': <comment>\\n\\n')."""
    return f": {comment}\n\n".encode()


async def heartbeat_sse_stream(
    source: AsyncIterator[SSEMessage],
    *,
    interval: float = 15.0,
    shutdown_event: asyncio.Event | None = None,
    on_tick: Callable[[float], None] | None = None,
) -> AsyncIterator[bytes]:
    """Stream encoded SSE frames interleaved with periodic ': heartbeat' comments."""
    src_iter = source.__aiter__()
    next_task: asyncio.Task[SSEMessage] | None = None

    async def _pull_next() -> SSEMessage:
        return await src_iter.__anext__()

    try:
        while True:
            if shutdown_event is not None and shutdown_event.is_set():
                return
            if next_task is None:
                next_task = asyncio.create_task(_pull_next())
            if interval > 0:
                done, _ = await asyncio.wait({next_task}, timeout=interval)
                if not done:
                    if on_tick is not None:
                        on_tick(time.monotonic() * 1000.0)
                    yield encode_sse_comment("heartbeat")
                    continue
            try:
                msg = await next_task
            except StopAsyncIteration:
                return
            finally:
                next_task = None
            if on_tick is not None:
                on_tick(time.monotonic() * 1000.0)
            yield msg.encode_wire()
    finally:
        if next_task is not None and not next_task.done():
            next_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await next_task
