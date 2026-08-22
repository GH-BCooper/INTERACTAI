#!/usr/bin/env python3
"""Evaluates the endpointing cascade against data/boundaries/labels.jsonl (Task 1.3d).

Simulates the real pipeline offline: Silero VAD -> FrameAccumulator -> HysteresisVad feed the
same `should_endpoint` cascade the realtime service uses, with the transcript tail at each
instant taken from a real faster-whisper pass over the same clip (so the filler/syntax rules
are genuinely exercised, not just the acoustic-silence rule). The one step not exercised is
step 5 (the semantic check): there's no live MODEL_ENDPOINTER in an offline batch script, so a
`NEEDS_SEMANTIC_CHECK` verdict is resolved the same way the running service resolves an
unreachable one — falls through to END (docs/phase-1-BUILD.md Task 1.3c: "this step is
cuttable"). The adaptive threshold (step 2) also never leaves its base value here, because
every item is a single independent one-utterance "session" — see data/boundaries/README.md.

Usage: uv run python scripts/eval_endpointing.py [--labels PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "realtime"))

from app.endpointing.cascade import (  # noqa: E402
    BASE_SILENCE_MS,
    EndpointDecision,
    EndpointState,
    should_endpoint,
)
from app.vad.silero import (  # noqa: E402
    WINDOW_SAMPLES,
    FrameAccumulator,
    HysteresisVad,
    SileroVad,
    load_vad_session,
)

WINDOW_MS = WINDOW_SAMPLES / 16_000 * 1000
FRAME_SAMPLES = 320
TAIL_WORDS = 6

DEFAULT_LABELS = REPO_ROOT / "data" / "boundaries" / "labels.jsonl"
DEFAULT_OUT = REPO_ROOT / "data" / "boundaries" / "eval_report.json"
VAD_MODEL_PATH = REPO_ROOT / "models" / "vad" / "silero_vad.onnx"


def _load_pcm(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _transcribe_words(model: Any, path: Path) -> list[tuple[str, float]]:
    """Returns [(word, end_ms), ...] in order. A real faster-whisper pass (Task 1.4's own
    final-pass settings), used here only to give the cascade a real transcript tail."""
    segments, _info = model.transcribe(
        str(path), beam_size=5, word_timestamps=True, condition_on_previous_text=False
    )
    words: list[tuple[str, float]] = []
    for seg in segments:
        for w in seg.words or []:
            words.append((w.word.strip(), w.end * 1000))
    return words


def _tail_at(words: list[tuple[str, float]], now_ms: float) -> str:
    spoken = [w for w, end_ms in words if end_ms <= now_ms]
    return " ".join(spoken[-TAIL_WORDS:])


def simulate_endpointing(
    pcm: np.ndarray, words: list[tuple[str, float]], vad_session: Any
) -> float | None:
    vad = HysteresisVad(vad=SileroVad(vad_session))
    acc = FrameAccumulator()
    heard_speech = False
    in_endpointing = False
    silence_ms = 0.0
    utterance_start_ms = 0.0
    threshold_ms = BASE_SILENCE_MS
    extensions_used = 0
    window_count = 0

    for start in range(0, len(pcm), FRAME_SAMPLES):
        frame = pcm[start : start + FRAME_SAMPLES]
        if len(frame) < FRAME_SAMPLES:
            frame = np.pad(frame, (0, FRAME_SAMPLES - len(frame)))
        for window in acc.push(frame):
            window_count += 1
            now_ms = window_count * WINDOW_MS
            is_speech = vad.observe(window)
            if is_speech:
                if not heard_speech:
                    heard_speech = True
                    utterance_start_ms = now_ms
                if in_endpointing:
                    in_endpointing = False
                    silence_ms = 0.0
            elif heard_speech:
                silence_ms += WINDOW_MS
                in_endpointing = True
                state = EndpointState(
                    silence_ms=silence_ms,
                    utterance_duration_ms=now_ms - utterance_start_ms,
                    threshold_ms=threshold_ms,
                    transcript_tail=_tail_at(words, now_ms),
                    extensions_used=extensions_used,
                )
                decision = should_endpoint(state)
                threshold_ms, extensions_used = state.threshold_ms, state.extensions_used
                if decision in (EndpointDecision.END, EndpointDecision.NEEDS_SEMANTIC_CHECK):
                    return now_ms
    return None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    lo, hi = int(rank), min(int(rank) + 1, len(ordered) - 1)
    return ordered[lo] + (rank - lo) * (ordered[hi] - ordered[lo])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--limit", type=int, default=None, help="evaluate only the first N items (debugging)"
    )
    args = parser.parse_args()

    if not args.labels.exists():
        print(
            f"no labels file at {args.labels} — run scripts/generate_synthetic_boundaries.py first",
            file=sys.stderr,
        )
        return 1
    if not VAD_MODEL_PATH.exists():
        print(f"missing VAD model at {VAD_MODEL_PATH}", file=sys.stderr)
        return 1

    from faster_whisper import WhisperModel

    print("loading models (once, shared across every item)...")
    vad_session = load_vad_session(str(VAD_MODEL_PATH))
    asr_model = WhisperModel("base.en", device="cpu", compute_type="int8")

    items = [
        json.loads(line)
        for line in args.labels.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        items = items[: args.limit]

    early_cutoffs = 0
    missed = 0
    latencies_ms: list[float] = []
    by_case: dict[str, dict[str, Any]] = {}

    for i, item in enumerate(items):
        path = REPO_ROOT / item["audio_path"]
        true_end_ms = float(item["true_end_ms"])
        case_type = item["notes"].split(":", 1)[0].strip()
        bucket = by_case.setdefault(
            case_type, {"n": 0, "early_cutoffs": 0, "missed": 0, "latencies_ms": []}
        )
        bucket["n"] += 1

        pcm = _load_pcm(path)
        words = _transcribe_words(asr_model, path)
        declared_ms = simulate_endpointing(pcm, words, vad_session)

        if declared_ms is None:
            missed += 1
            bucket["missed"] += 1
        elif declared_ms < true_end_ms:
            early_cutoffs += 1
            bucket["early_cutoffs"] += 1
        else:
            latency = declared_ms - true_end_ms
            latencies_ms.append(latency)
            bucket["latencies_ms"].append(latency)

        if (i + 1) % 25 == 0 or (i + 1) == len(items):
            print(f"  {i + 1}/{len(items)} evaluated")

    n = len(items)
    declared = n - missed
    recall = declared / n if n else float("nan")
    precision = (declared - early_cutoffs) / declared if declared else float("nan")

    report = {
        "n_items": n,
        "recall": recall,
        "precision": precision,
        "early_cutoffs": early_cutoffs,
        "missed_entirely": missed,
        "latency_ms_p50": _percentile(latencies_ms, 50),
        "latency_ms_p95": _percentile(latencies_ms, 95),
        "by_case_type": {
            case: {
                "n": b["n"],
                "early_cutoffs": b["early_cutoffs"],
                "missed": b["missed"],
                "latency_ms_p50": _percentile(b["latencies_ms"], 50),
                "latency_ms_p95": _percentile(b["latencies_ms"], 95),
            }
            for case, b in sorted(by_case.items())
        },
        "known_limitations": [
            "Ground truth is synthetic (Piper TTS + exact silence splicing), not real "
            "hand-marked human speech — see data/boundaries/README.md.",
            "Step 5 (semantic completeness check) is not exercised: no live MODEL_ENDPOINTER "
            "in this offline script, so NEEDS_SEMANTIC_CHECK always resolves to END here.",
            "The adaptive threshold (step 2) never leaves its base value: every item is one "
            "independent single-utterance session, and it requires >=3 completed utterances.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nn={n}  recall={recall:.3f}  precision={precision:.3f}")
    print(f"early cutoffs: {early_cutoffs}   missed entirely: {missed}")
    print(f"latency p50={report['latency_ms_p50']:.0f}ms  p95={report['latency_ms_p95']:.0f}ms")
    print(f"\nfull report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
