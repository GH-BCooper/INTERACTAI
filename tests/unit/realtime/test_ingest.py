from __future__ import annotations

import wave
from pathlib import Path

from services.realtime.app.audio.ingest import (
    IngestRateLimiter,
    SequenceTracker,
    SessionWavWriter,
)


def test_sequence_tracker_in_order_has_no_gap() -> None:
    tracker = SequenceTracker()
    for seq in range(5):
        result = tracker.observe(seq)
        assert result.gap_frames == 0
        assert result.degraded is False


def test_sequence_tracker_small_gap_tolerated() -> None:
    tracker = SequenceTracker()
    tracker.observe(0)
    result = tracker.observe(4)  # missing 1,2,3 -> gap of 3
    assert result.gap_frames == 3
    assert result.degraded is False


def test_sequence_tracker_large_gap_is_degraded() -> None:
    tracker = SequenceTracker()
    tracker.observe(0)
    result = tracker.observe(21)  # missing 1..20 -> gap of 20
    assert result.gap_frames == 20
    assert result.degraded is True


def test_sequence_tracker_boundary_five_is_not_degraded() -> None:
    tracker = SequenceTracker()
    tracker.observe(0)
    result = tracker.observe(6)  # missing 1..5 -> gap of exactly 5
    assert result.gap_frames == 5
    assert result.degraded is False


def test_sequence_tracker_boundary_six_is_degraded() -> None:
    tracker = SequenceTracker()
    tracker.observe(0)
    result = tracker.observe(7)  # gap of 6
    assert result.degraded is True


def test_sequence_tracker_ignores_stale_or_duplicate() -> None:
    tracker = SequenceTracker()
    tracker.observe(10)
    result = tracker.observe(5)  # stale/reordered, not a forward gap
    assert result.gap_frames == 0
    assert result.degraded is False


def test_rate_limiter_denies_burst_and_allows_after_interval() -> None:
    clock = {"t": 0.0}
    limiter = IngestRateLimiter(min_interval_s=0.010, clock=lambda: clock["t"])

    assert limiter.allow() is True  # first frame always allowed
    assert limiter.allow() is False  # same instant -> too fast

    clock["t"] += 0.005
    assert limiter.allow() is False  # still under the interval

    clock["t"] += 0.010
    assert limiter.allow() is True  # now past the interval


def test_rate_limiter_tolerates_a_catch_up_burst_after_server_side_delay() -> None:
    """A real client sending steadily can still arrive at the server in a burst if the server
    itself briefly fell behind (a slow VAD/ASR call delaying the next `receive()`). That must
    not be mistaken for a hostile fast client — only a *sustained* excess rate should be."""
    clock = {"t": 0.0}
    limiter = IngestRateLimiter(min_interval_s=0.010, burst_capacity=10.0, clock=lambda: clock["t"])
    limiter.allow()  # consume the initial token

    clock["t"] += 0.100  # server was busy for 100ms -> 10 frames' worth of real time passed
    allowed = [limiter.allow() for _ in range(10)]
    assert all(allowed), "a legitimate catch-up burst must not be dropped"

    # but the burst budget is finite: an 11th frame with no further elapsed time is rejected
    assert limiter.allow() is False


def test_rate_limiter_rejects_a_sustained_too_fast_client() -> None:
    clock = {"t": 0.0}
    limiter = IngestRateLimiter(min_interval_s=0.010, burst_capacity=5.0, clock=lambda: clock["t"])
    limiter.allow()

    accepted = 0
    for _ in range(100):
        clock["t"] += 0.001  # sending 10x faster than the 10ms real-time interval
        if limiter.allow():
            accepted += 1
    # sustained abuse settles to roughly the refill rate, not the offered rate
    assert accepted < 30


def test_wav_writer_round_trips_pitch_and_speed(tmp_path: Path) -> None:
    out = tmp_path / "session.wav"
    payload = b"\x10\x00" * 320  # 320 samples, arbitrary non-zero value
    with SessionWavWriter(out) as writer:
        for _ in range(10):
            writer.write_frame(payload)

    with wave.open(str(out), "rb") as f:
        assert f.getframerate() == 16_000
        assert f.getnchannels() == 1
        assert f.getsampwidth() == 2
        assert f.getnframes() == 320 * 10  # correct duration -> correct pitch and speed


def test_wav_writer_silence_fill(tmp_path: Path) -> None:
    out = tmp_path / "session_gap.wav"
    payload = b"\x10\x00" * 320
    with SessionWavWriter(out) as writer:
        writer.write_frame(payload)
        writer.write_silence(frame_bytes=len(payload), count=3)
        writer.write_frame(payload)

    with wave.open(str(out), "rb") as f:
        assert f.getnframes() == 320 * (1 + 3 + 1)
        frames = f.readframes(f.getnframes())
        # the middle 3 frames (1920 bytes) must be exact digital silence
        silence_region = frames[640 : 640 + 640 * 3]
        assert silence_region == b"\x00" * (640 * 3)
