"""Unit tests for zcg.web.probes.

Specification: docs/architecture/06_web_and_api_application_engine.md
"""

from __future__ import annotations

import pytest

from zcg.web.probes import (
    HeartbeatJitterTracker,
    JitterHealthStatus,
    ProgressStatus,
    SamplingCadenceCalculator,
    SlidingProgressMonitor,
)


class TestProbes:
    """Verify anti-aliasing sampling cadence, sliding progress verdicts, and jitter tracking."""

    def test_sampling_cadence_calculator_schedule_and_bipolar_bounds_expected(self) -> None:
        """Verify W >= 2 * T_cycle cadence math, deterministic/random jitter, and guard errors."""
        # Arrange
        calc = SamplingCadenceCalculator(10.0, jitter_ratio=0.10)

        # Act
        low = calc.compute_next_schedule(jitter_seed=-1.0)
        high = calc.compute_next_schedule(jitter_seed=1.0)
        rng_sched = calc.compute_next_schedule()

        # Assert
        assert calc.cycle_period_seconds == 10.0
        assert calc.recommended_sample_interval_seconds == 5.0
        assert calc.minimum_window_seconds == 20.0
        assert low.jitter_bound_seconds == 0.5
        assert low.next_delay_seconds == 4.5
        assert high.next_delay_seconds == 5.5
        assert 4.5 <= rng_sched.next_delay_seconds <= 5.5
        assert ProgressStatus.choices() == [
            "PROGRESSING",
            "INSUFFICIENT_SAMPLES",
            "STAGNANT_LOOP",
        ]
        with pytest.raises(ValueError, match="cycle_period_seconds"):
            SamplingCadenceCalculator(0.0005)
        with pytest.raises(ValueError, match="jitter_ratio"):
            SamplingCadenceCalculator(1.0, jitter_ratio=0.51)
        with pytest.raises(ValueError, match="jitter_seed"):
            calc.compute_next_schedule(jitter_seed=1.5)

    def test_sliding_progress_monitor_progressing_stagnant_and_cutpoints_expected(self) -> None:
        """Verify empty, sub-window, progressing, stagnant-loop, and pruning cut-points."""
        # Arrange
        mon = SlidingProgressMonitor(5.0)
        custom_mon = SlidingProgressMonitor(2.0, window_seconds=6.0)
        live_mon = SlidingProgressMonitor(1.0)

        # Act
        empty_verdict = mon.evaluate()
        mon.record(0.10, state_key="init", now=0.0)
        mon.record(0.20, state_key="step-1", now=5.0)
        two_sample_verdict = mon.evaluate(now=5.0)
        mon.record(0.30, state_key="step-2", now=9.99)
        short_span_verdict = mon.evaluate(now=9.99)
        mon.record(0.45, state_key="step-3", now=10.0)
        progressing_verdict = mon.evaluate(now=10.0)

        # Advance window past initial progress and remain flat -> STAGNANT_LOOP
        mon.record(0.50, state_key="loop-a", now=25.0)
        mon.record(0.55, state_key="loop-b", now=30.0)
        mon.record(0.50, state_key="loop-a", now=35.0)
        stagnant_verdict = mon.evaluate(now=35.0)
        live_mon.record(0.1)

        # Assert
        assert mon.required_window_seconds == 10.0
        assert custom_mon.required_window_seconds == 6.0
        assert empty_verdict.status == ProgressStatus.INSUFFICIENT_SAMPLES
        assert two_sample_verdict.status == ProgressStatus.INSUFFICIENT_SAMPLES
        assert short_span_verdict.status == ProgressStatus.INSUFFICIENT_SAMPLES
        assert progressing_verdict.status == ProgressStatus.PROGRESSING
        assert progressing_verdict.distinct_states == 4
        assert stagnant_verdict.status == ProgressStatus.STAGNANT_LOOP
        assert stagnant_verdict.net_progress_delta == 0.0
        assert live_mon.evaluate().sample_count == 1
        with pytest.raises(ValueError, match="anti-aliasing minimum"):
            SlidingProgressMonitor(5.0, window_seconds=9.9)
        with pytest.raises(ValueError, match="max_samples"):
            SlidingProgressMonitor(1.0, max_samples=2)

    def test_heartbeat_jitter_tracker_cutpoints_and_validation_expected(self) -> None:
        """Verify STABLE, exact 50 ms ELEVATED, and exact 200 ms SATURATED cut-points."""
        # Arrange
        tracker = HeartbeatJitterTracker(elevated_threshold_ms=50.0, saturated_threshold_ms=200.0)
        sat_tracker = HeartbeatJitterTracker(
            elevated_threshold_ms=50.0, saturated_threshold_ms=200.0
        )
        live_tracker = HeartbeatJitterTracker()

        # Act
        empty_snap = tracker.snapshot()
        first_snap = tracker.record_tick(now=1.000)
        single_interval = tracker.record_tick(now=1.100)
        elevated_snap = tracker.record_tick(now=1.300)

        sat_tracker.record_tick(now=0.0)
        sat_tracker.record_tick(now=0.100)
        saturated_snap = sat_tracker.record_tick(now=0.600)
        live_snap = live_tracker.record_tick()

        # Assert
        assert empty_snap.status == JitterHealthStatus.STABLE and empty_snap.sample_count == 0
        assert first_snap.sample_count == 0
        assert single_interval.status == JitterHealthStatus.STABLE
        assert single_interval.jitter_ms == 0.0
        assert elevated_snap.status == JitterHealthStatus.ELEVATED
        assert elevated_snap.jitter_ms == 50.0
        assert saturated_snap.status == JitterHealthStatus.SATURATED
        assert saturated_snap.jitter_ms == 200.0
        assert live_snap.status == JitterHealthStatus.STABLE
        with pytest.raises(ValueError, match="max_intervals"):
            HeartbeatJitterTracker(max_intervals=1)
        with pytest.raises(ValueError, match="elevated_threshold_ms"):
            HeartbeatJitterTracker(elevated_threshold_ms=100.0, saturated_threshold_ms=100.0)
