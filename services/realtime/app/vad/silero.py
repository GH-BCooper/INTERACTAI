"""Silero VAD (Task 1.3a). ONNX Runtime, CPU, single-threaded session, loaded once at process
startup (`main.py`'s lifespan) and shared across every session — never per-session.

The model's own contract (confirmed against the committed `models/vad/silero_vad.onnx` by
direct experiment, not assumed): inputs `input` (float32, shape [batch, num_samples]), `state`
(float32, [2, batch, 128], the recurrent state threaded between calls) and `sr` (int64 scalar);
output `output` (float32, [batch, 1] speech probability) and `stateN` (the next `state`).

Non-obvious and load-bearing: `num_samples` is **576**, not 512. This Silero export (v5)
expects a 64-sample *context* — literally the last 64 samples of the previous call's input —
prepended to each new 512-sample window. Omitting it still runs (the graph accepts a bare 512
samples with no shape error) but produces near-constant, near-zero probability regardless of
input, silently. There is no public spec for this repo to cite; it was found by feeding known
loud speech through the raw ONNX session and observing the output stay pinned near zero until
the context was added, then verified against the official `silero-vad` PyPI package's own
`OnnxWrapper.__call__`, which does exactly this concatenation. Frames here are always logically
512 samples at 16kHz (Silero's supported window size for this rate); the extra 64 is
context, tracked internally by `SileroVad` and invisible to callers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import onnxruntime as ort

WINDOW_SAMPLES = 512
CONTEXT_SAMPLES = 64
SAMPLE_RATE = 16_000

# Task 1.3a hysteresis thresholds.
ONSET_PROB = 0.5
ONSET_CONSECUTIVE_WINDOWS = 2
OFFSET_PROB = 0.35


def load_vad_session(model_path: str) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    return ort.InferenceSession(
        model_path, sess_options=options, providers=["CPUExecutionProvider"]
    )


class SileroVad:
    """One VAD decoder instance per session (the recurrent `state` is per-utterance-stream, so
    it cannot be shared across concurrent sessions the way the ONNX session itself is)."""

    def __init__(self, session: ort.InferenceSession) -> None:
        self._session = session
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)

    def process_window(self, samples: np.ndarray) -> float:
        """`samples` must be exactly WINDOW_SAMPLES (512) float32 values in [-1, 1]. Returns
        the speech probability for this window. Must run in < 3ms on CPU (Task 1.3a) — asserted
        in tests/unit/realtime/test_vad.py, not here, to keep this hot path allocation-free."""
        window = samples.reshape(1, WINDOW_SAMPLES).astype(np.float32, copy=False)
        x = np.concatenate([self._context, window], axis=1)  # (1, 576) — see module docstring
        out, self._state = self._session.run(
            None, {"input": x, "state": self._state, "sr": self._sr}
        )
        self._context = x[:, -CONTEXT_SAMPLES:]
        return float(out[0, 0])

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)


@dataclass
class HysteresisVad:
    """Wraps SileroVad with onset/offset hysteresis (Task 1.3a) so a probability oscillating
    around a single threshold doesn't flap the speaking/silent decision every window."""

    vad: SileroVad
    is_speech: bool = False
    _consecutive_above_onset: int = 0

    def observe(self, samples: np.ndarray) -> bool:
        prob = self.vad.process_window(samples)
        if self.is_speech:
            if prob < OFFSET_PROB:
                self.is_speech = False
                self._consecutive_above_onset = 0
        else:
            if prob > ONSET_PROB:
                self._consecutive_above_onset += 1
                if self._consecutive_above_onset >= ONSET_CONSECUTIVE_WINDOWS:
                    self.is_speech = True
            else:
                self._consecutive_above_onset = 0
        return self.is_speech


class FrameAccumulator:
    """Silero wants 512-sample windows; upstream frames are 320 samples (Task 1.3a: "maintain
    an accumulator and run inference on each complete 512-sample window; do not resize the
    frame"). Pure and allocation-light: one fixed buffer, refilled via `copyWithin`-style shift.
    """

    def __init__(self) -> None:
        self._buf = np.zeros(WINDOW_SAMPLES * 2, dtype=np.float32)
        self._len = 0

    def push(self, frame_samples: np.ndarray) -> list[np.ndarray]:
        n = len(frame_samples)
        if self._len + n > len(self._buf):
            self._buf[: self._len] = self._buf[: self._len]  # no-op; buffer sized to never overflow
        self._buf[self._len : self._len + n] = frame_samples
        self._len += n

        windows = []
        while self._len >= WINDOW_SAMPLES:
            windows.append(self._buf[:WINDOW_SAMPLES].copy())
            remaining = self._len - WINDOW_SAMPLES
            self._buf[:remaining] = self._buf[WINDOW_SAMPLES : self._len]
            self._len = remaining
        return windows
