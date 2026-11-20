"""Adaptive sampling cadence, anti-aliasing progress monitor, and heartbeat jitter tracker.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import statistics
import time
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

from zcg.web.http.channels import BaseStrEnum

MIN_CYCLE_PERIOD_SECONDS: Final[float] = 0.001
ANTI_ALIASING_WINDOW_MULTIPLIER: Final[float] = 2.0
DEFAULT_SAMPLING_FACTOR: Final[float] = 0.5
DEFAULT_JITTER_RATIO: Final[float] = 0.10
MAX_JITTER_RATIO: Final[float] = 0.50
MIN_UNIT_SEED: Final[float] = -1.0
MAX_UNIT_SEED: Final[float] = 1.0
MIN_PROGRESS_SAMPLES: Final[int] = 3
DEFAULT_MAX_PROGRESS_HISTORY: Final[int] = 128
MIN_JITTER_SAMPLES: Final[int] = 2
DEFAULT_MAX_JITTER_INTERVALS: Final[int] = 64
DEFAULT_ELEVATED_JITTER_MS: Final[float] = 50.0
DEFAULT_SATURATED_JITTER_MS: Final[float] = 200.0
MS_PER_SECOND: Final[float] = 1000.0

_SYS_RNG: Final[secrets.SystemRandom] = secrets.SystemRandom()


class ProgressStatus(BaseStrEnum):
    """Anti-aliasing sliding-window progress classification."""

    PROGRESSING = "PROGRESSING"
    INSUFFICIENT_SAMPLES = "INSUFFICIENT_SAMPLES"
    STAGNANT_LOOP = "STAGNANT_LOOP"


class JitterHealthStatus(BaseStrEnum):
    """Heartbeat inter-arrival dispersion classification."""

    STABLE = "STABLE"
    ELEVATED = "ELEVATED"
    SATURATED = "SATURATED"


@dataclass(frozen=True, slots=True)
class SamplingCadenceSnapshot:
    """Computed sampling cadence and bounded anti-thundering-herd schedule."""

    cycle_period_seconds: float
    recommended_sample_interval_seconds: float
    minimum_window_seconds: float
    jitter_bound_seconds: float
    next_delay_seconds: float


class SamplingCadenceCalculator:
    """Derive anti-aliasing sampling intervals (W >= 2 * T_cycle) and bounded jitter delays."""

    def __init__(
        self,
        cycle_period_seconds: float,
        *,
        jitter_ratio: float = DEFAULT_JITTER_RATIO,
    ) -> None:
        if cycle_period_seconds < MIN_CYCLE_PERIOD_SECONDS:
            raise ValueError(
                f"cycle_period_seconds must be >= {MIN_CYCLE_PERIOD_SECONDS}s, "
                f"got {cycle_period_seconds}"
            )
        if not (0.0 <= jitter_ratio <= MAX_JITTER_RATIO):
            raise ValueError(
                f"jitter_ratio must be within [0.0, {MAX_JITTER_RATIO}], got {jitter_ratio}"
            )
        self._cycle_period_seconds = float(cycle_period_seconds)
        self._jitter_ratio = float(jitter_ratio)

    @property
    def cycle_period_seconds(self) -> float:
        """Return the configured dominant operational cycle period in seconds."""
        return self._cycle_period_seconds

    @property
    def recommended_sample_interval_seconds(self) -> float:
        """Return the base sampling period (0.5 * T_cycle) guaranteeing >= 2 samples/cycle."""
        return self._cycle_period_seconds * DEFAULT_SAMPLING_FACTOR

    @property
    def minimum_window_seconds(self) -> float:
        """Return the minimum anti-aliasing observation window (2.0 * T_cycle)."""
        return self._cycle_period_seconds * ANTI_ALIASING_WINDOW_MULTIPLIER

    def compute_next_schedule(
        self,
        *,
        jitter_seed: float | None = None,
    ) -> SamplingCadenceSnapshot:
        """Compute the next sample delay using optional deterministic unit seed [-1.0, 1.0]."""
        if jitter_seed is None:
            unit_offset = _SYS_RNG.uniform(MIN_UNIT_SEED, MAX_UNIT_SEED)
        else:
            if not (MIN_UNIT_SEED <= jitter_seed <= MAX_UNIT_SEED):
                raise ValueError(
                    f"jitter_seed must be within [{MIN_UNIT_SEED}, {MAX_UNIT_SEED}], "
                    f"got {jitter_seed}"
                )
            unit_offset = float(jitter_seed)
        base_interval = self.recommended_sample_interval_seconds
        jitter_bound = base_interval * self._jitter_ratio
        raw_delay = base_interval + (unit_offset * jitter_bound)
        next_delay = max(MIN_CYCLE_PERIOD_SECONDS, raw_delay)
        return SamplingCadenceSnapshot(
            cycle_period_seconds=self._cycle_period_seconds,
            recommended_sample_interval_seconds=base_interval,
            minimum_window_seconds=self.minimum_window_seconds,
            jitter_bound_seconds=jitter_bound,
            next_delay_seconds=next_delay,
        )


@dataclass(frozen=True, slots=True)
class _ProgressSample:
    timestamp: float
    progress: float
    state_key: str


@dataclass(frozen=True, slots=True)
class ProgressVerdict:
    """Sliding-window stagnation evaluation verdict."""

    status: ProgressStatus
    sample_count: int
    distinct_states: int
    observed_span_seconds: float
    required_window_seconds: float
    net_progress_delta: float
    latest_progress: float


class SlidingProgressMonitor:
    """Detect stagnant execution and oscillatory state loops over W >= 2 * T_cycle."""

    def __init__(
        self,
        cycle_period_seconds: float,
        *,
        window_seconds: float | None = None,
        max_samples: int = DEFAULT_MAX_PROGRESS_HISTORY,
    ) -> None:
        cadence = SamplingCadenceCalculator(cycle_period_seconds)
        min_window = cadence.minimum_window_seconds
        if window_seconds is not None and window_seconds < min_window:
            raise ValueError(
                f"window_seconds ({window_seconds}s) violates anti-aliasing minimum "
                f"({min_window}s = 2 * T_cycle)"
            )
        if max_samples < MIN_PROGRESS_SAMPLES:
            raise ValueError(f"max_samples must be >= {MIN_PROGRESS_SAMPLES}")
        self._required_window = float(window_seconds) if window_seconds is not None else min_window
        self._samples: deque[_ProgressSample] = deque(maxlen=max_samples)

    @property
    def required_window_seconds(self) -> float:
        """Return the enforced anti-aliasing sliding window duration in seconds."""
        return self._required_window

    def record(
        self,
        progress: float,
        *,
        state_key: str = "",
        now: float | None = None,
    ) -> None:
        """Append a monotonic progress sample and evict samples outside the window."""
        ts = time.monotonic() if now is None else float(now)
        self._prune_expired(ts)
        self._samples.append(
            _ProgressSample(timestamp=ts, progress=float(progress), state_key=state_key)
        )

    def _prune_expired(self, current_ts: float) -> None:
        cutoff = current_ts - self._required_window
        while self._samples and self._samples[0].timestamp < cutoff:
            self._samples.popleft()

    def evaluate(self, *, now: float | None = None) -> ProgressVerdict:
        """Evaluate whether observed samples demonstrate net forward progress."""
        if now is not None:
            self._prune_expired(float(now))
        count = len(self._samples)
        if count == 0:
            return ProgressVerdict(
                status=ProgressStatus.INSUFFICIENT_SAMPLES,
                sample_count=0,
                distinct_states=0,
                observed_span_seconds=0.0,
                required_window_seconds=self._required_window,
                net_progress_delta=0.0,
                latest_progress=0.0,
            )
        first = self._samples[0]
        last = self._samples[-1]
        span = max(0.0, last.timestamp - first.timestamp)
        distinct = len({s.state_key for s in self._samples if s.state_key})
        net_delta = last.progress - first.progress
        if count < MIN_PROGRESS_SAMPLES or span < self._required_window:
            status = ProgressStatus.INSUFFICIENT_SAMPLES
        elif net_delta > 0.0:
            status = ProgressStatus.PROGRESSING
        else:
            status = ProgressStatus.STAGNANT_LOOP
        return ProgressVerdict(
            status=status,
            sample_count=count,
            distinct_states=distinct,
            observed_span_seconds=span,
            required_window_seconds=self._required_window,
            net_progress_delta=net_delta,
            latest_progress=last.progress,
        )


@dataclass(frozen=True, slots=True)
class HeartbeatJitterSnapshot:
    """Heartbeat interval dispersion metrics in milliseconds."""

    status: JitterHealthStatus
    sample_count: int
    mean_interval_ms: float
    jitter_ms: float


class HeartbeatJitterTracker:
    """Measure inter-arrival mean latency and standard-deviation jitter across ticks."""

    def __init__(
        self,
        *,
        max_intervals: int = DEFAULT_MAX_JITTER_INTERVALS,
        elevated_threshold_ms: float = DEFAULT_ELEVATED_JITTER_MS,
        saturated_threshold_ms: float = DEFAULT_SATURATED_JITTER_MS,
    ) -> None:
        if max_intervals < MIN_JITTER_SAMPLES:
            raise ValueError(f"max_intervals must be >= {MIN_JITTER_SAMPLES}")
        if elevated_threshold_ms <= 0.0 or saturated_threshold_ms <= elevated_threshold_ms:
            raise ValueError("Expected 0 < elevated_threshold_ms < saturated_threshold_ms")
        self._intervals_ms: deque[float] = deque(maxlen=max_intervals)
        self._elevated_ms = float(elevated_threshold_ms)
        self._saturated_ms = float(saturated_threshold_ms)
        self._last_tick_ts: float | None = None

    def record_tick(self, *, now: float | None = None) -> HeartbeatJitterSnapshot:
        """Record an arrival timestamp and return the updated dispersion snapshot."""
        ts = time.monotonic() if now is None else float(now)
        if self._last_tick_ts is not None:
            delta_ms = max(0.0, (ts - self._last_tick_ts) * MS_PER_SECOND)
            self._intervals_ms.append(delta_ms)
        self._last_tick_ts = ts
        return self.snapshot()

    def snapshot(self) -> HeartbeatJitterSnapshot:
        """Compute current mean interval and population standard-deviation jitter."""
        count = len(self._intervals_ms)
        if count == 0:
            return HeartbeatJitterSnapshot(
                status=JitterHealthStatus.STABLE,
                sample_count=0,
                mean_interval_ms=0.0,
                jitter_ms=0.0,
            )
        mean_ms = round(statistics.fmean(self._intervals_ms), 3)
        jitter_ms = (
            round(statistics.pstdev(self._intervals_ms), 3) if count >= MIN_JITTER_SAMPLES else 0.0
        )
        if jitter_ms >= self._saturated_ms:
            status = JitterHealthStatus.SATURATED
        elif jitter_ms >= self._elevated_ms:
            status = JitterHealthStatus.ELEVATED
        else:
            status = JitterHealthStatus.STABLE
        return HeartbeatJitterSnapshot(
            status=status,
            sample_count=count,
            mean_interval_ms=mean_ms,
            jitter_ms=jitter_ms,
        )


@dataclass(frozen=True, slots=True)
class PeerHealthVerdict:
    """Structured peer /healthz probe result for autonomous mesh resilience."""

    peer_url: str
    healthy: bool
    status_code: int
    regime: str
    latency_ms: float


def notify_systemd_ready(
    state_msg: str = "READY=1",
    *,
    notify_socket: str | None = None,
    sock_factory: Callable[..., Any] | None = None,
) -> bool:
    """Send sd_notify datagram over UNIX NOTIFY_SOCKET when supervised by systemd."""
    raw_sock = os.environ.get("NOTIFY_SOCKET", "") if notify_socket is None else notify_socket
    target = raw_sock.strip()
    if not target:
        return False
    addr = "\x00" + target[1:] if target.startswith("@") else target
    eff_factory = socket.socket if sock_factory is None else sock_factory
    try:
        with eff_factory(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(state_msg.encode("utf-8"), addr)
    except OSError:
        return False
    return True


def probe_peer_healthz(
    peer_base_url: str,
    *,
    timeout_seconds: float = 2.0,
    opener: Callable[..., Any] | None = None,
) -> PeerHealthVerdict:
    """Probe a peer node /healthz endpoint and return a bounded PeerHealthVerdict."""
    clean = peer_base_url.strip().rstrip("/")
    parts = urlsplit(clean)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username:
        raise ValueError(f"INVALID_PEER_PROBE_URL: expected http(s) origin, got {peer_base_url!r}")
    url = clean if clean.endswith("/healthz") else f"{clean}/healthz"
    eff_opener = urllib.request.urlopen if opener is None else opener
    t0 = time.monotonic()
    try:
        with eff_opener(url, timeout=timeout_seconds) as resp:
            code = int(getattr(resp, "status", 200))
            doc = json.loads(resp.read().decode("utf-8"))
        lat_ms = round((time.monotonic() - t0) * MS_PER_SECOND, 2)
        if not isinstance(doc, dict):
            return PeerHealthVerdict(url, False, code, "INVALID_PAYLOAD", lat_ms)
        regime = str(doc.get("health_regime") or "OPTIMAL")
        return PeerHealthVerdict(
            url, code == 200 and doc.get("status") == "ok", code, regime, lat_ms
        )
    except OSError, ValueError:
        lat_ms = round((time.monotonic() - t0) * MS_PER_SECOND, 2)
        return PeerHealthVerdict(url, False, 0, "UNREACHABLE", lat_ms)
