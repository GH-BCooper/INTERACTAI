"""Server-side ingest primitives (Task 1.2c): sequence-gap classification, an ingest rate cap,
and the append-as-it-arrives WAV writer so a crash never loses the recording. Frame length/kind
validation lives in `protocol.validate_upstream_frame` — this module assumes a frame already
passed that check.

Wiring these into the session state machine (raising `degraded` on a large gap, uploading
during the session) is orchestration and lives in `session.py`, not here — this module stays a
set of small, independently testable primitives.
"""

from __future__ import annotations

import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .protocol import UPSTREAM_CHANNELS, UPSTREAM_SAMPLE_RATE

# A gap of 1-5 frames is tolerated (filled with silence); more than that raises `degraded`.
SMALL_GAP_MAX_FRAMES = 5

# No two upstream frames closer together than this — 20ms of audio arriving faster than every
# 10ms is either a broken client clock or a hostile one sending faster than real time.
MIN_FRAME_INTERVAL_S = 0.010


@dataclass(frozen=True, slots=True)
class SequenceGapResult:
    gap_frames: int  # 0 = in order; N = frames missing immediately before this one
    degraded: bool  # True once gap_frames exceeds the tolerated small-gap window


class SequenceTracker:
    """Tracks the last-seen upstream seq for one connection and classifies each new frame's
    gap size against Task 1.2c's edge-case table. A `seq` at or before the last one seen
    (stale/duplicate/reordered) is treated as in-order noise, not a gap — there is nothing to
    fill and nothing to flag."""

    def __init__(self) -> None:
        self._last_seq: int | None = None

    def observe(self, seq: int) -> SequenceGapResult:
        if self._last_seq is None:
            self._last_seq = seq
            return SequenceGapResult(gap_frames=0, degraded=False)

        gap = seq - self._last_seq - 1
        self._last_seq = max(self._last_seq, seq)
        if gap <= 0:
            return SequenceGapResult(gap_frames=0, degraded=False)
        return SequenceGapResult(gap_frames=gap, degraded=gap > SMALL_GAP_MAX_FRAMES)


class IngestRateLimiter:
    """Token bucket, refilling at exactly real-time rate (one token per `min_interval_s`).
    Starts with one token, so back-to-back frames with no real elapsed time between them are
    rejected (a genuinely too-fast client) — but a *legitimate* client is never penalized for
    a delivery burst caused by the server itself briefly falling behind (a slow VAD/ASR call
    delaying the next `websocket.receive()`), because tokens accumulated during that delay are
    still there once the server catches up. `burst_capacity` caps how much catch-up credit can
    accumulate, matching Task 1.2c's actual intent ("a client sending faster than real time is
    either broken or hostile") rather than penalizing server-side jitter."""

    def __init__(
        self,
        min_interval_s: float = MIN_FRAME_INTERVAL_S,
        burst_capacity: float = 50.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval = min_interval_s
        self._burst_capacity = burst_capacity
        self._clock = clock
        self._tokens = 1.0
        self._last_check = clock()

    def allow(self) -> bool:
        now = self._clock()
        elapsed = now - self._last_check
        self._last_check = now
        self._tokens = min(self._burst_capacity, self._tokens + elapsed / self._min_interval)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class SessionWavWriter:
    """Appends raw 16kHz mono PCM16 to a per-session WAV file as frames arrive. Opening the
    file and writing incrementally (rather than buffering in memory and writing once at the
    end) is the point: a crash mid-session loses at most the last unflushed frame, not the
    whole recording."""

    def __init__(
        self,
        path: Path,
        *,
        sample_rate: int = UPSTREAM_SAMPLE_RATE,
        channels: int = UPSTREAM_CHANNELS,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._wav = wave.open(str(path), "wb")
        self._wav.setnchannels(channels)
        self._wav.setsampwidth(2)
        self._wav.setframerate(sample_rate)
        self.path = path

    def write_silence(self, frame_bytes: int, count: int) -> None:
        if count > 0:
            self._wav.writeframes(b"\x00" * (frame_bytes * count))

    def write_frame(self, payload: bytes) -> None:
        self._wav.writeframes(payload)

    def close(self) -> None:
        self._wav.close()

    def __enter__(self) -> SessionWavWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
