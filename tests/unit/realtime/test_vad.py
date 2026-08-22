"""Task 1.3a acceptance: VAD < 3ms/window (asserted), hysteresis prevents flapping."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from services.realtime.app.vad.silero import (
    OFFSET_PROB,
    WINDOW_SAMPLES,
    FrameAccumulator,
    HysteresisVad,
    SileroVad,
    load_vad_session,
)

VAD_MODEL_PATH = Path("models/vad/silero_vad.onnx")
pytestmark = pytest.mark.skipif(not VAD_MODEL_PATH.exists(), reason="silero_vad.onnx not present")


@pytest.fixture(scope="module")
def vad_session():  # type: ignore[no-untyped-def]
    return load_vad_session(str(VAD_MODEL_PATH))


def test_process_window_runs_under_3ms(vad_session) -> None:  # type: ignore[no-untyped-def]
    vad = SileroVad(vad_session)
    silence = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
    for _ in range(10):  # warm up: first call pays one-time graph-load cost
        vad.process_window(silence)

    durations_ms = []
    rng = np.random.default_rng(0)
    for _ in range(200):
        window = rng.uniform(-0.1, 0.1, size=WINDOW_SAMPLES).astype(np.float32)
        t0 = time.perf_counter()
        vad.process_window(window)
        durations_ms.append((time.perf_counter() - t0) * 1000)

    p95 = sorted(durations_ms)[int(0.95 * len(durations_ms))]
    assert p95 < 3.0, f"p95 window latency {p95:.3f}ms exceeds the 3ms budget"


def test_silence_gives_low_probability(vad_session) -> None:  # type: ignore[no-untyped-def]
    vad = SileroVad(vad_session)
    silence = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
    prob = None
    for _ in range(5):
        prob = vad.process_window(silence)
    assert prob is not None
    assert prob < OFFSET_PROB


def test_hysteresis_requires_two_consecutive_windows_above_onset() -> None:
    class _FakeVad:
        def __init__(self, probs: list[float]) -> None:
            self._probs = iter(probs)

        def process_window(self, _samples: np.ndarray) -> float:
            return next(self._probs)

    # A single window above onset, then back down, must NOT flip to speech.
    hv = HysteresisVad(vad=_FakeVad([0.6, 0.1, 0.1]))  # type: ignore[arg-type]
    dummy = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
    results = [hv.observe(dummy) for _ in range(3)]
    assert results == [False, False, False]


def test_hysteresis_flips_on_two_consecutive_onset_windows() -> None:
    class _FakeVad:
        def __init__(self, probs: list[float]) -> None:
            self._probs = iter(probs)

        def process_window(self, _samples: np.ndarray) -> float:
            return next(self._probs)

    hv = HysteresisVad(vad=_FakeVad([0.6, 0.6, 0.6]))  # type: ignore[arg-type]
    dummy = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
    results = [hv.observe(dummy) for _ in range(3)]
    assert results == [False, True, True]


def test_hysteresis_does_not_flap_at_the_boundary() -> None:
    """A probability oscillating right around a single threshold (e.g. 0.5) must not flap
    speech/silence every window — the offset threshold (0.35) is deliberately lower than the
    onset threshold (0.5) to create a dead zone."""

    class _FakeVad:
        def __init__(self, probs: list[float]) -> None:
            self._probs = iter(probs)

        def process_window(self, _samples: np.ndarray) -> float:
            return next(self._probs)

    boundary_noise = [0.6, 0.6, 0.45, 0.4, 0.45, 0.6, 0.4]  # never drops below OFFSET_PROB
    hv = HysteresisVad(vad=_FakeVad(boundary_noise))  # type: ignore[arg-type]
    dummy = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
    results = [hv.observe(dummy) for _ in boundary_noise]
    # Onset locks in at index 1 (two consecutive >0.5) and, since probability never falls below
    # OFFSET_PROB (0.35), speech never flaps back off despite hovering near 0.5.
    assert results == [False, True, True, True, True, True, True]


def test_offset_below_threshold_flips_back_to_silence() -> None:
    class _FakeVad:
        def __init__(self, probs: list[float]) -> None:
            self._probs = iter(probs)

        def process_window(self, _samples: np.ndarray) -> float:
            return next(self._probs)

    hv = HysteresisVad(vad=_FakeVad([0.6, 0.6, 0.2]))  # type: ignore[arg-type]
    dummy = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
    results = [hv.observe(dummy) for _ in range(3)]
    assert results == [False, True, False]


class TestFrameAccumulator:
    def test_accumulates_320_sample_frames_into_512_sample_windows(self) -> None:
        acc = FrameAccumulator()
        frame = np.ones(320, dtype=np.float32)

        windows = acc.push(frame)
        assert windows == []  # 320 < 512, nothing to emit yet

        windows = acc.push(frame)  # now have 640 samples -> one window, 128 left over
        assert len(windows) == 1
        assert windows[0].shape == (WINDOW_SAMPLES,)

    def test_does_not_resize_the_frame_itself(self) -> None:
        acc = FrameAccumulator()
        frame = np.arange(320, dtype=np.float32)
        acc.push(frame)
        windows = acc.push(frame)
        assert len(windows) == 1
        # first 320 values of the window are exactly the first pushed frame, unmodified
        assert np.array_equal(windows[0][:320], frame)
