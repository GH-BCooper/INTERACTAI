from __future__ import annotations

from services.realtime.app.asr.confidence import (
    CONFIDENCE_THRESHOLD,
    is_confident,
    load_clarification_pool,
    pick_clarification,
)
from services.realtime.app.asr.whisper import RtfMonitor, confidence_from_avg_logprob


def test_confidence_threshold_boundary() -> None:
    assert is_confident(CONFIDENCE_THRESHOLD) is True
    assert is_confident(CONFIDENCE_THRESHOLD - 0.01) is False


def test_clarification_pool_loads_and_cycles() -> None:
    pool = load_clarification_pool()
    assert len(pool) >= 1
    first = pick_clarification(pool, 0)
    wrapped = pick_clarification(pool, len(pool))
    assert first == wrapped  # cycles rather than repeating the same line every call


def test_confidence_from_avg_logprob_maps_to_unit_interval() -> None:
    assert confidence_from_avg_logprob(0.0) == 1.0  # exp(0) = 1
    assert 0.0 <= confidence_from_avg_logprob(-0.5) <= 1.0
    assert (
        confidence_from_avg_logprob(-100.0) < 1e-10
    )  # exp(-100) underflows near zero, never negative


def test_rtf_monitor_does_not_flag_below_window_size() -> None:
    monitor = RtfMonitor()
    for _ in range(4):
        monitor.record(0.95)  # above threshold, but window of 5 not yet full
    assert monitor.should_downgrade() is False


def test_rtf_monitor_flags_after_five_slow_turns() -> None:
    monitor = RtfMonitor()
    for _ in range(5):
        monitor.record(0.95)
    assert monitor.should_downgrade() is True


def test_rtf_monitor_rolls_off_old_values() -> None:
    monitor = RtfMonitor()
    for _ in range(5):
        monitor.record(0.95)
    assert monitor.should_downgrade() is True
    for _ in range(5):
        monitor.record(0.1)  # five fast turns push the slow ones out of the window
    assert monitor.should_downgrade() is False


def test_rtf_monitor_uses_mean_not_any_single_spike() -> None:
    monitor = RtfMonitor()
    for rtf in [0.1, 0.1, 0.1, 0.1, 1.0]:  # one spike; mean is 0.28, still well under 0.8
        monitor.record(rtf)
    assert monitor.should_downgrade() is False
