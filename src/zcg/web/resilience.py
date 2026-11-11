"""In-flight deadline guard, batch chunker, deferred job queue, reaper, and bulkhead.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio
import itertools
import time
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import Any, Final

from zcg.web.channels import BaseStrEnum, Tier

DEFAULT_MAX_IN_FLIGHT: Final[int] = 32
MIN_DEADLINE_BUDGET_SECONDS: Final[float] = 0.0
DEFAULT_MAX_TASK_AGE_SECONDS: Final[float] = 300.0
DEFAULT_MAX_STAGNANT_SECONDS: Final[float] = 60.0
DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_BULKHEAD_SATURATION_RATIO: Final[float] = 0.80
MIN_PROGRESS_RATIO: Final[float] = 0.0
MAX_PROGRESS_RATIO: Final[float] = 1.0
VALID_DEFERRED_TIERS: Final[frozenset[Tier]] = frozenset({Tier.T2, Tier.T3, Tier.T4, Tier.T5})


def chunk_items[T](items: Iterable[T], max_chunk_size: int) -> list[tuple[T, ...]]:
    """Partition an iterable into bounded non-empty tuples without raw index slicing."""
    if max_chunk_size < 1:
        raise ValueError(f"max_chunk_size must be >= 1, got {max_chunk_size}")
    iterator = iter(items)
    batches: list[tuple[T, ...]] = []
    while batch := tuple(itertools.islice(iterator, max_chunk_size)):
        batches.append(batch)
    return batches


@dataclass(frozen=True, slots=True)
class InFlightSnapshot:
    """Point-in-time state of bounded unacknowledged operations and remaining budget."""

    in_flight_count: int
    max_in_flight: int
    remaining_budget_seconds: float
    accepting: bool


class DeadlineBudgetGuard:
    """Bound unacknowledged in-flight operations and enforce monotonic deadline budgets."""

    def __init__(
        self, deadline_monotonic: float, *, max_in_flight: int = DEFAULT_MAX_IN_FLIGHT
    ) -> None:
        if max_in_flight < 1:
            raise ValueError(f"max_in_flight must be >= 1, got {max_in_flight}")
        self._deadline_monotonic = float(deadline_monotonic)
        self._max_in_flight = max_in_flight
        self._in_flight: dict[str, float] = {}

    def remaining_budget_seconds(self, *, now: float | None = None) -> float:
        """Return remaining monotonic budget in seconds (clamped to >= 0.0)."""
        ts = time.monotonic() if now is None else float(now)
        return max(0.0, self._deadline_monotonic - ts)

    def can_accept(
        self,
        *,
        min_required_seconds: float = MIN_DEADLINE_BUDGET_SECONDS,
        now: float | None = None,
    ) -> bool:
        """Return True when in-flight capacity and remaining deadline budget allow work."""
        if len(self._in_flight) >= self._max_in_flight:
            return False
        return self.remaining_budget_seconds(now=now) > min_required_seconds

    def acquire(
        self,
        operation_id: str,
        *,
        min_required_seconds: float = MIN_DEADLINE_BUDGET_SECONDS,
        now: float | None = None,
    ) -> bool:
        """Register an in-flight operation if unique and within window + deadline bounds."""
        ts = time.monotonic() if now is None else float(now)
        if not operation_id or operation_id in self._in_flight:
            return False
        if not self.can_accept(min_required_seconds=min_required_seconds, now=ts):
            return False
        self._in_flight[operation_id] = ts
        return True

    def acknowledge(self, operation_id: str) -> bool:
        """Release an acknowledged operation slot; return True if previously active."""
        return self._in_flight.pop(operation_id, None) is not None

    def snapshot(self, *, now: float | None = None) -> InFlightSnapshot:
        """Return a frozen snapshot of in-flight occupancy and budget health."""
        rem = self.remaining_budget_seconds(now=now)
        return InFlightSnapshot(
            in_flight_count=len(self._in_flight),
            max_in_flight=self._max_in_flight,
            remaining_budget_seconds=rem,
            accepting=len(self._in_flight) < self._max_in_flight and rem > 0.0,
        )


class DeferredTaskStatus(BaseStrEnum):
    """Lifecycle states for T2..T5 asynchronous or background jobs."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


TERMINAL_TASK_STATUSES: Final[frozenset[DeferredTaskStatus]] = frozenset(
    {DeferredTaskStatus.COMPLETED, DeferredTaskStatus.FAILED, DeferredTaskStatus.EXPIRED}
)


@dataclass(slots=True)
class DeferredTaskRecord:
    """Mutable state record for a tracked T2..T5 background job."""

    task_id: str
    tier: Tier
    status: DeferredTaskStatus
    created_at: float
    updated_at: float
    progress: float = MIN_PROGRESS_RATIO
    retries: int = 0
    result: object = None
    error: str = ""

    @property
    def is_terminal(self) -> bool:
        """Return True if the task has reached COMPLETED, FAILED, or EXPIRED."""
        return self.status in TERMINAL_TASK_STATUSES


class DeferredJobQueue:
    """Track, execute, and prune T2..T5 deferred background jobs."""

    def __init__(self) -> None:
        self._records: dict[str, DeferredTaskRecord] = {}
        self._bg_tasks: set[asyncio.Task[None]] = set()

    def register(
        self, task_id: str, *, tier: Tier = Tier.T2, now: float | None = None
    ) -> DeferredTaskRecord:
        """Register a PENDING deferred task record after validating tier and uniqueness."""
        if tier not in VALID_DEFERRED_TIERS:
            raise ValueError(f"Deferred jobs require tier in T2..T5, got {tier.value}")
        if not task_id or task_id in self._records:
            raise ValueError(f"Duplicate or empty task_id: {task_id!r}")
        ts = time.monotonic() if now is None else float(now)
        rec = DeferredTaskRecord(task_id, tier, DeferredTaskStatus.PENDING, ts, ts)
        self._records[task_id] = rec
        return rec

    def submit_async(
        self,
        task_id: str,
        coro_factory: Callable[[], Coroutine[Any, Any, object]],
        *,
        tier: Tier = Tier.T2,
        now: float | None = None,
    ) -> DeferredTaskRecord:
        """Schedule an asyncio background job and update record status on completion."""
        rec = self.register(task_id, tier=tier, now=now)
        rec.status = DeferredTaskStatus.RUNNING

        async def _runner() -> None:
            try:
                rec.result = await coro_factory()
                if not rec.is_terminal:
                    rec.progress = MAX_PROGRESS_RATIO
                    rec.status = DeferredTaskStatus.COMPLETED
                    rec.updated_at = time.monotonic()
            except Exception as exc:
                rec.error = str(exc)
                rec.status = DeferredTaskStatus.FAILED
                rec.updated_at = time.monotonic()

        bg = asyncio.create_task(_runner())
        self._bg_tasks.add(bg)
        bg.add_done_callback(self._bg_tasks.discard)
        return rec

    def update_progress(
        self,
        task_id: str,
        progress: float,
        *,
        increment_retry: bool = False,
        now: float | None = None,
    ) -> DeferredTaskRecord:
        """Update clamped [0.0, 1.0] progress on a non-terminal task."""
        rec = self._records[task_id]
        if rec.is_terminal:
            return rec
        ts = time.monotonic() if now is None else float(now)
        clamped = min(MAX_PROGRESS_RATIO, max(MIN_PROGRESS_RATIO, float(progress)))
        rec.progress = clamped
        rec.status = (
            DeferredTaskStatus.COMPLETED
            if clamped >= MAX_PROGRESS_RATIO
            else DeferredTaskStatus.RUNNING
        )
        if increment_retry:
            rec.retries += 1
        rec.updated_at = ts
        return rec

    def mark_expired(
        self, task_id: str, reason: str, *, now: float | None = None
    ) -> DeferredTaskRecord:
        """Transition a non-terminal task to EXPIRED with an eviction diagnostic."""
        rec = self._records[task_id]
        if not rec.is_terminal:
            rec.status = DeferredTaskStatus.EXPIRED
            rec.error = reason
            rec.updated_at = time.monotonic() if now is None else float(now)
        return rec

    def get(self, task_id: str) -> DeferredTaskRecord | None:
        """Return the task record for task_id or None if absent."""
        return self._records.get(task_id)

    def records(self) -> tuple[DeferredTaskRecord, ...]:
        """Return all tracked task records in insertion order."""
        return tuple(self._records.values())

    @property
    def active_count(self) -> int:
        """Return the count of non-terminal (PENDING or RUNNING) tasks."""
        return sum(1 for rec in self._records.values() if not rec.is_terminal)

    def prune_terminal(self) -> int:
        """Remove all terminal records and return the count of pruned entries."""
        terminal_ids = [tid for tid, rec in self._records.items() if rec.is_terminal]
        for tid in terminal_ids:
            del self._records[tid]
        return len(terminal_ids)


class EvictionReason(BaseStrEnum):
    """Deterministic eviction causes for stale or runaway background tasks."""

    RETRY_BUDGET_EXHAUSTED = "RETRY_BUDGET_EXHAUSTED"
    MAX_AGE_EXCEEDED = "MAX_AGE_EXCEEDED"
    STAGNATION_TIMEOUT = "STAGNATION_TIMEOUT"


@dataclass(frozen=True, slots=True)
class ResourceTTLPolicy:
    """Lifecycle bounds governing background task age, stagnation, and retry caps."""

    max_age_seconds: float = DEFAULT_MAX_TASK_AGE_SECONDS
    max_stagnant_seconds: float = DEFAULT_MAX_STAGNANT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES


@dataclass(frozen=True, slots=True)
class ReaperEvictionSignal:
    """Diagnostic signal emitted when StaleResourceReaper evicts an active job."""

    task_id: str
    reason: EvictionReason
    age_seconds: float
    stagnant_seconds: float
    retries: int


class StaleResourceReaper:
    """Inspect and evict active jobs violating age, stagnation, or retry TTL policies."""

    def __init__(self, policy: ResourceTTLPolicy | None = None) -> None:
        self._policy = policy or ResourceTTLPolicy()

    def inspect_task(
        self, record: DeferredTaskRecord, *, now: float | None = None
    ) -> ReaperEvictionSignal | None:
        """Return an eviction signal if a non-terminal task violates policy, else None."""
        if record.is_terminal:
            return None
        ts = time.monotonic() if now is None else float(now)
        age = max(0.0, ts - record.created_at)
        stagnant = max(0.0, ts - record.updated_at)
        reason: EvictionReason | None = None
        if record.retries > self._policy.max_retries:
            reason = EvictionReason.RETRY_BUDGET_EXHAUSTED
        elif age >= self._policy.max_age_seconds:
            reason = EvictionReason.MAX_AGE_EXCEEDED
        elif stagnant >= self._policy.max_stagnant_seconds:
            reason = EvictionReason.STAGNATION_TIMEOUT
        if reason is None:
            return None
        return ReaperEvictionSignal(record.task_id, reason, age, stagnant, record.retries)

    def sweep(
        self, queue: DeferredJobQueue, *, now: float | None = None
    ) -> tuple[ReaperEvictionSignal, ...]:
        """Mark all policy-violating active jobs EXPIRED and return emitted signals."""
        ts = time.monotonic() if now is None else float(now)
        signals: list[ReaperEvictionSignal] = []
        for rec in queue.records():
            if (sig := self.inspect_task(rec, now=ts)) is not None:
                queue.mark_expired(rec.task_id, sig.reason.value, now=ts)
                signals.append(sig)
        return tuple(signals)


class BulkheadStatus(BaseStrEnum):
    """Saturation isolation posture protecting interactive T1 threads."""

    OPEN = "OPEN"
    SHIELDED = "SHIELDED"


@dataclass(frozen=True, slots=True)
class ContextLoadSnapshot:
    """Current runtime utilization ratio [0.0..1.0] and active heavy background jobs."""

    utilization_ratio: float
    active_heavy_tasks: int


@dataclass(frozen=True, slots=True)
class BulkheadDecision:
    """Load-shedding decision recommending T1 interactive vs. T2 deferred execution."""

    status: BulkheadStatus
    recommended_tier: Tier
    utilization_ratio: float
    reason: str


class BulkheadIsolationGuard:
    """Isolate T1 interactive responsiveness by deferring to T2 under heavy saturation."""

    def __init__(self, *, saturation_threshold: float = DEFAULT_BULKHEAD_SATURATION_RATIO) -> None:
        if not (0.0 < saturation_threshold <= MAX_PROGRESS_RATIO):
            raise ValueError(
                f"saturation_threshold must be in (0.0, 1.0], got {saturation_threshold}"
            )
        self._saturation_threshold = float(saturation_threshold)

    def evaluate(self, load: ContextLoadSnapshot) -> BulkheadDecision:
        """Evaluate load and shed to Tier.T2 when saturated with active heavy work."""
        ratio = min(MAX_PROGRESS_RATIO, max(MIN_PROGRESS_RATIO, float(load.utilization_ratio)))
        if ratio >= self._saturation_threshold and load.active_heavy_tasks > 0:
            msg = (
                f"Utilization {ratio:.2f} >= {self._saturation_threshold:.2f} "
                f"with {load.active_heavy_tasks} heavy task(s); deferring to T2."
            )
            return BulkheadDecision(BulkheadStatus.SHIELDED, Tier.T2, ratio, msg)
        return BulkheadDecision(
            BulkheadStatus.OPEN, Tier.T1, ratio, "Interactive T1 capacity available."
        )
