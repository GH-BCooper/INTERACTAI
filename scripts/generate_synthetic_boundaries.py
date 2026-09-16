#!/usr/bin/env python3
"""Generates data/boundaries/ — docs/phase-1-BUILD.md TASK 1.3d.

The task asks for >=200 *hand-marked* boundaries: a human listens to real speech and marks
where they judged it ended. There is no microphone and no human available to do that in this
build environment (the same constraint documented in scripts/generate_audio_fixtures.py for
Phase 0's audio fixtures). This script produces a *synthetic* substitute instead: short
utterances built from Piper TTS segments spliced together with exact, programmatically-known
silence gaps, so `true_end_ms` is exact by construction rather than estimated by ear.

That is a materially different (weaker) kind of ground truth than real hand-labelling —
see data/boundaries/README.md for exactly what this does and does not validate. `make cli`'s
--replay mode and the real collection tool (`scripts/collect_boundaries.py`, built and ready
for a human with a microphone) are how this gets upgraded to real data.

Usage: uv run python scripts/generate_synthetic_boundaries.py
Requires: piper-tts, ffmpeg on PATH.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPER_DIR = REPO_ROOT / "models" / "piper"
OUT_DIR = REPO_ROOT / "data" / "boundaries"
AUDIO_DIR = OUT_DIR / "audio"
LABELS_PATH = OUT_DIR / "labels.jsonl"
TARGET_RATE = 16_000
TRAILING_SILENCE_MS = 1200  # room for an endpointer to declare an end after the true boundary
VOICES = ["en_US-lessac-medium", "en_US-ryan-medium", "en_GB-alan-medium"]

CLEAN_ENDINGS = [
    "That's the whole story.",
    "So that's basically how we fixed it.",
    "I think that answers your question.",
    "We shipped it the following week.",
    "That was the biggest lesson from that project.",
    "In the end, the team was happy with the outcome.",
    "It's been running in production ever since.",
    "That's pretty much everything I remember.",
    "The fix held up under the next load test.",
    "We haven't seen the issue since.",
    "It turned out to be a simple configuration error.",
    "Everyone on the team agreed it was the right call.",
]

UNFINISHED_TAILS = [
    "So I was thinking, um",
    "And then we realized that, uh",
    "The main issue was, like",
    "We looked into it and",
    "I handed the ticket off to",
    "The root cause turned out to be the",
    "We eventually migrated it to",
    "It mostly came down to",
    "The team decided to go with",
    "We were blocked on",
]

LIST_ITEMS = [
    "Kafka.",
    "Postgres.",
    "Redis.",
    "the ingestion service.",
    "the retry queue.",
    "and finally the dead letter topic.",
]

FALSE_START_FIRST = [
    "So the way it worked was",
    "I think the first time we",
    "Actually, let me back up",
    "The initial plan was to",
]

ALL_TEXTS = sorted(set(CLEAN_ENDINGS + UNFINISHED_TAILS + LIST_ITEMS + FALSE_START_FIRST))


def _piper_synthesize(text: str, voice: str, out_wav: Path) -> None:
    model = PIPER_DIR / f"{voice}.onnx"
    if not model.exists():
        raise FileNotFoundError(f"missing Piper voice: {model}")
    cmd = [
        sys.executable,
        "-m",
        "piper",
        "--model",
        str(model),
        "--output_file",
        str(out_wav),
        "--sentence-silence",
        "0.05",
    ]
    subprocess.run(cmd, input=text.encode(), check=True)  # noqa: S603 — fixed argv, no shell


def _resample_to_contract(src: Path, dst: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        str(TARGET_RATE),
        "-sample_fmt",
        "s16",
        str(dst),
    ]
    subprocess.run(cmd, check=True)  # noqa: S603 — fixed argv, no shell


def _read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == TARGET_RATE
        assert w.getsampwidth() == 2
        assert w.getnchannels() == 1
        return w.readframes(w.getnframes())


def _silence_bytes(ms: float) -> bytes:
    n_samples = round(TARGET_RATE * ms / 1000)
    return b"\x00\x00" * n_samples


def _write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_RATE)
        w.writeframes(pcm)


def _samples_to_ms(n_bytes: int) -> float:
    return (n_bytes / 2) / TARGET_RATE * 1000


@dataclass
class BoundaryItem:
    audio_path: str
    true_end_ms: float
    notes: str


def _build_item(name: str, segments: list[bytes], case_type: str, notes: str) -> BoundaryItem:
    """`segments` are the speech+silence pieces, in order. `true_end_ms` is the cumulative
    duration of everything *up to and including the last speech segment* — i.e. excluding the
    trailing padding silence appended after it."""
    speech_and_gaps = b"".join(segments)
    true_end_ms = _samples_to_ms(len(speech_and_gaps))
    full = speech_and_gaps + _silence_bytes(TRAILING_SILENCE_MS)
    out_path = AUDIO_DIR / f"{name}.wav"
    _write_wav(out_path, full)
    return BoundaryItem(
        audio_path=str(out_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        true_end_ms=round(true_end_ms, 1),
        notes=f"{case_type}: {notes}",
    )


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 1

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_DIR / "_tmp"
    tmp.mkdir(exist_ok=True)

    print(f"synthesizing {len(ALL_TEXTS)} base segments across {len(VOICES)} voices...")
    pool: dict[str, bytes] = {}
    for voice in VOICES:
        for text in ALL_TEXTS:
            key = f"{voice}::{text}"
            raw = tmp / "raw.wav"
            resampled = tmp / "resampled.wav"
            _piper_synthesize(text, voice, raw)
            _resample_to_contract(raw, resampled)
            pool[key] = _read_pcm(resampled)

    rng = random.Random(20260821)  # noqa: S311 — dataset generation, not security-sensitive
    items: list[BoundaryItem] = []

    def pick(texts: list[str], voice: str) -> bytes:
        return pool[f"{voice}::{rng.choice(texts)}"]

    # 1. Clean, unambiguous endings (60).
    for i in range(60):
        voice = rng.choice(VOICES)
        seg = pick(CLEAN_ENDINGS, voice)
        items.append(_build_item(f"clean_{i:03d}", [seg], "clean_definitive_end", f"voice={voice}"))

    # 2. Mid-sentence thinking pauses — NOT the true end; true end is after the continuation (50).
    gap_choices = [400, 600, 800, 1000, 1500]
    for i in range(50):
        voice = rng.choice(VOICES)
        gap_ms = rng.choice(gap_choices)
        lead = pick(UNFINISHED_TAILS, voice)
        tail = pick(CLEAN_ENDINGS, voice)
        items.append(
            _build_item(
                f"mid_pause_{i:03d}",
                [lead, _silence_bytes(gap_ms), tail],
                "mid_sentence_pause",
                f"voice={voice} gap_ms={gap_ms}",
            )
        )

    # 3. Trailing filler — two flavours: genuinely done right after the filler, or continues (40).
    for i in range(20):
        voice = rng.choice(VOICES)
        seg = pick(UNFINISHED_TAILS, voice)
        items.append(
            _build_item(
                f"filler_done_{i:03d}", [seg], "trailing_filler_then_done", f"voice={voice}"
            )
        )
    for i in range(20):
        voice = rng.choice(VOICES)
        gap_ms = rng.choice(gap_choices)
        lead = pick(UNFINISHED_TAILS, voice)
        tail = pick(CLEAN_ENDINGS, voice)
        items.append(
            _build_item(
                f"filler_continues_{i:03d}",
                [lead, _silence_bytes(gap_ms), tail],
                "trailing_filler_then_continues",
                f"voice={voice} gap_ms={gap_ms}",
            )
        )

    # 4. Lists with pauses between items (40).
    for i in range(40):
        voice = rng.choice(VOICES)
        n_items = rng.choice([3, 4])
        chosen = rng.sample(LIST_ITEMS, k=n_items)
        segs: list[bytes] = []
        for j, text in enumerate(chosen):
            segs.append(pool[f"{voice}::{text}"])
            if j < len(chosen) - 1:
                segs.append(_silence_bytes(rng.choice([250, 350, 450])))
        items.append(
            _build_item(
                f"list_pause_{i:03d}",
                segs,
                "list_with_pauses",
                f"voice={voice} n_items={n_items}",
            )
        )

    # 5. False starts — true end is after the SECOND (real) utterance (30).
    for i in range(30):
        voice = rng.choice(VOICES)
        gap_ms = rng.choice([200, 300, 400])
        first = pick(FALSE_START_FIRST, voice)
        second = pick(CLEAN_ENDINGS, voice)
        items.append(
            _build_item(
                f"false_start_{i:03d}",
                [first, _silence_bytes(gap_ms), second],
                "false_start",
                f"voice={voice} restart_gap_ms={gap_ms}",
            )
        )

    shutil.rmtree(tmp)

    with LABELS_PATH.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(
                json.dumps(
                    {
                        "audio_path": item.audio_path,
                        "true_end_ms": item.true_end_ms,
                        "notes": item.notes,
                    }
                )
                + "\n"
            )

    print(f"wrote {len(items)} items to {LABELS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
