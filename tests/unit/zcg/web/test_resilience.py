"""Unit tests for zcg.web.resilience.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import asyncio

import pytest

from zcg.web.channels import Tier
from zcg.web.resilience import (
    BulkheadIsolationGuard,
    BulkheadStatus,
    ContextLoadSnapshot,
    DeadlineBudgetGuard,
    DeferredJobQueue,
    DeferredTaskStatus,
    EvictionReason,
    ResourceTTLPolicy,
    StaleResourceReaper,
    chunk_items,
)


class TestResilience:
    """Verify batch chunking, deadline budget guards, deferred queues, reaper, and bulkhead."""

    def test_chunk_items_and_deadline_budget_guard_cutpoints_expected(self) -> None:
        """Verify PEP 695 chunk_items partitioning and DeadlineBudgetGuard window/budget bounds."""
        # Arrange
        guard = DeadlineBudgetGuard(deadline_monotonic=100.0, max_in_flight=2)
        live_guard = DeadlineBudgetGuard(deadline_monotonic=1e12)

        # Act
        empty_input: list[int] = []
        batches = chunk_items([1, 2, 3, 4, 5], 2)
        empty_batches = chunk_items(empty_input, 3)
        ok_a = guard.acquire("op-1", min_required_seconds=5.0, now=90.0)
        dup_a = guard.acquire("op-1", now=90.0)
        empty_id = guard.acquire("", now=90.0)
        low_budget = guard.acquire("op-low", min_required_seconds=10.0, now=90.0)
        ok_b = guard.acquire("op-2", now=91.0)
        full_snap = guard.snapshot(now=91.0)
        over_cap = guard.acquire("op-3", now=91.0)
        acked = guard.acknowledge("op-1")
        missing_ack = guard.acknowledge("unknown")
        reopened_snap = guard.snapshot(now=95.0)
        live_ok = live_guard.acquire("op-live")

        # Assert
        assert batches == [(1, 2), (3, 4), (5,)]
        assert empty_batches == []
        assert ok_a is True and dup_a is False and empty_id is False and low_budget is False
        assert ok_b is True and over_cap is False
        assert full_snap.in_flight_count == 2 and full_snap.accepting is False
        assert acked is True and missing_ack is False
        assert reopened_snap.accepting is True and reopened_snap.remaining_budget_seconds == 5.0
        assert live_ok is True
        with pytest.raises(ValueError, match="max_chunk_size"):
            chunk_items([1], 0)
        with pytest.raises(ValueError, match="max_in_flight"):
            DeadlineBudgetGuard(10.0, max_in_flight=0)

    def test_deferred_job_queue_async_execution_progress_and_pruning_expected(self) -> None:
        """Verify async job runner, terminal guards, progress clamping, and terminal pruning."""
        # Arrange
        queue = DeferredJobQueue()
        manual = queue.register("job-manual", tier=Tier.T4)

        async def _run() -> tuple[DeferredTaskStatus, DeferredTaskStatus, DeferredTaskStatus]:
            gate = asyncio.Event()

            async def _ok_job() -> str:
                return "done-payload"

            async def _fail_job() -> None:
                raise RuntimeError("upstream timeout")

            async def _pre_expired_job() -> str:
                await gate.wait()
                return "late"

            r_ok = queue.submit_async("job-ok", _ok_job, tier=Tier.T2, now=1.0)
            r_err = queue.submit_async("job-err", _fail_job, tier=Tier.T3, now=1.0)
            r_exp = queue.submit_async("job-exp", _pre_expired_job, tier=Tier.T2, now=1.0)
            queue.mark_expired("job-exp", "preempted")
            gate.set()
            await asyncio.sleep(0.01)
            return r_ok.status, r_err.status, r_exp.status

        # Act
        st_ok, st_err, st_exp = asyncio.run(_run())
        queue.update_progress("job-manual", 0.4, increment_retry=True)
        queue.update_progress("job-manual", 1.5, now=20.0)
        queue.update_progress("job-manual", 0.2, now=25.0)
        queue.mark_expired("job-manual", "ignored", now=25.0)
        active_before_prune = queue.active_count
        pruned = queue.prune_terminal()

        # Assert
        assert st_ok == DeferredTaskStatus.COMPLETED
        assert st_err == DeferredTaskStatus.FAILED
        assert st_exp == DeferredTaskStatus.EXPIRED
        assert manual.progress == 1.0 and manual.retries == 1
        assert active_before_prune == 0
        assert pruned == 4 and queue.get("job-ok") is None
        with pytest.raises(ValueError, match=r"T2\.\.T5"):
            queue.register("sync-invalid", tier=Tier.T1)
        with pytest.raises(ValueError, match="Duplicate or empty"):
            queue.register("")

    def test_stale_resource_reaper_and_bulkhead_isolation_guard_expected(self) -> None:
        """Verify retry/age/stagnation eviction sweep and Bulkhead T1->T2 saturation shedding."""
        # Arrange
        queue = DeferredJobQueue()
        r_healthy = queue.register("healthy", now=100.0)
        r_retry = queue.register("over-retry", now=100.0)
        r_retry.retries = 4
        queue.register("too-old", now=0.0)
        r_stag = queue.register("stagnant", now=80.0)
        r_stag.updated_at = 30.0
        r_done = queue.register("done", now=0.0)
        queue.update_progress("done", 1.0, now=1.0)
        reaper = StaleResourceReaper(
            ResourceTTLPolicy(max_age_seconds=90.0, max_stagnant_seconds=50.0, max_retries=3)
        )
        live_reaper = StaleResourceReaper()
        live_queue = DeferredJobQueue()
        live_rec = live_queue.register("live-ok")
        bulkhead = BulkheadIsolationGuard(saturation_threshold=0.80)

        # Act
        signals = reaper.sweep(queue, now=100.0)
        done_sig = reaper.inspect_task(r_done, now=100.0)
        live_sig = live_reaper.inspect_task(live_rec)
        live_sweep = live_reaper.sweep(live_queue)
        dec_shielded = bulkhead.evaluate(
            ContextLoadSnapshot(utilization_ratio=0.80, active_heavy_tasks=2)
        )
        dec_no_heavy = bulkhead.evaluate(
            ContextLoadSnapshot(utilization_ratio=0.95, active_heavy_tasks=0)
        )
        dec_low_util = bulkhead.evaluate(
            ContextLoadSnapshot(utilization_ratio=0.50, active_heavy_tasks=3)
        )

        # Assert
        assert [s.reason for s in signals] == [
            EvictionReason.RETRY_BUDGET_EXHAUSTED,
            EvictionReason.MAX_AGE_EXCEEDED,
            EvictionReason.STAGNATION_TIMEOUT,
        ]
        assert not r_healthy.is_terminal and queue.active_count == 1
        assert done_sig is None and live_sig is None and live_sweep == ()
        assert dec_shielded.status == BulkheadStatus.SHIELDED
        assert dec_shielded.recommended_tier == Tier.T2
        assert dec_no_heavy.status == BulkheadStatus.OPEN
        assert dec_no_heavy.recommended_tier == Tier.T1
        assert dec_low_util.status == BulkheadStatus.OPEN
        with pytest.raises(ValueError, match="saturation_threshold"):
            BulkheadIsolationGuard(saturation_threshold=0.0)
