#!/usr/bin/env python3
"""The real hand-labelling tool for data/boundaries/ (Task 1.3d). Records real speech (or
reviews an existing directory of WAV files), plays each utterance back, and lets a human mark
the true end-of-speech sample index.

This is the genuine article — it was not runnable in the build environment this repo was
first assembled in (no microphone, no human available to sit and label audio interactively),
so the committed data/boundaries/labels.jsonl was produced by
scripts/generate_synthetic_boundaries.py instead. See data/boundaries/README.md. Running this
script for real, on real recorded speech, and re-running scripts/eval_endpointing.py against
the result, is the single highest-value thing to do before trusting any endpointing tuning
decision made against the synthetic set.

Usage:
    uv run python scripts/collect_boundaries.py --record 20                 # record 20 utterances
    uv run python scripts/collect_boundaries.py --review data/boundaries/raw
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "boundaries" / "labels.jsonl"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "boundaries" / "raw"
SAMPLE_RATE = 16_000
MAX_RECORD_SECONDS = 20


def append_label(path: Path, *, audio_path: str, true_end_ms: float, notes: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps({"audio_path": audio_path, "true_end_ms": true_end_ms, "notes": notes})
            + "\n"
        )


def parse_end_input(raw: str, playback_duration_ms: float) -> float:
    """Accepts a plain number of milliseconds, or a bare Enter meaning "the very end of the
    clip". Raises ValueError on anything else, including a value past the clip's own length."""
    raw = raw.strip()
    if raw == "":
        return playback_duration_ms
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"not a number: {raw!r}") from exc
    if not (0.0 <= value <= playback_duration_ms):
        raise ValueError(f"{value}ms is outside the clip's {playback_duration_ms}ms length")
    return value


def _wav_duration_ms(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate() * 1000


def _record_one(out_path: Path, seconds: float = MAX_RECORD_SECONDS) -> None:
    import sounddevice as sd

    print(f"  recording for up to {seconds:.0f}s — speak now, then wait for silence...")
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())


def _play(path: Path) -> None:
    import numpy as np
    import sounddevice as sd

    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    sd.play(data, rate)
    sd.wait()


def _review_one(path: Path, labels_path: Path) -> None:
    duration_ms = _wav_duration_ms(path)
    print(f"\n{path.name} ({duration_ms:.0f}ms)")
    while True:
        _play(path)
        raw = input("  true end in ms (Enter = end of clip, 'r' to replay, 'q' to skip): ")
        if raw.strip().lower() == "r":
            continue
        if raw.strip().lower() == "q":
            print("  skipped")
            return
        try:
            true_end_ms = parse_end_input(raw, duration_ms)
        except ValueError as exc:
            print(f"  {exc}")
            continue
        notes = input("  notes (optional): ").strip()
        append_label(
            labels_path,
            audio_path=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
            true_end_ms=true_end_ms,
            notes=notes,
        )
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record", type=int, metavar="N", help="record N new utterances, then review them"
    )
    parser.add_argument(
        "--review", type=Path, metavar="DIR", help="review every .wav in an existing directory"
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help=f"labels file (default: {DEFAULT_OUT})"
    )
    args = parser.parse_args()

    if not args.record and not args.review:
        parser.error("pass --record N or --review DIR")

    if args.record:
        DEFAULT_RAW_DIR.mkdir(parents=True, exist_ok=True)
        existing = len(list(DEFAULT_RAW_DIR.glob("utterance_*.wav")))
        paths = []
        for i in range(args.record):
            path = DEFAULT_RAW_DIR / f"utterance_{existing + i:04d}.wav"
            input(f"[{i + 1}/{args.record}] press Enter, then speak one utterance...")
            _record_one(path)
            paths.append(path)
        review_paths = paths
    else:
        review_paths = sorted(args.review.glob("*.wav"))
        if not review_paths:
            print(f"no .wav files found in {args.review}", file=sys.stderr)
            return 1

    for path in review_paths:
        _review_one(path, args.out)

    print(f"\nlabels written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
