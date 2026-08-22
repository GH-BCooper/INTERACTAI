#!/usr/bin/env python3
"""Generates tests/fixtures/audio/ — docs/phase-0-BUILD.md TASK 0.7.

These are synthesized with Piper (models/piper/), not recorded. A committed audio fixture set
was required now so Phase 1 doesn't start by recording under deadline pressure, and there is
no microphone available in this environment to record real human speech. Piper output is a
defensible stand-in — it has real formant structure and timing, unlike a synthetic tone — but
it is not a substitute for real speech before tuning VAD/endpointing against real users. See
the fixture README for what to do about that.

Every output is resampled to the frozen capture contract: 16 kHz, mono, 16-bit PCM
(AUDIO_SAMPLE_RATE / AUDIO_CHANNELS / AUDIO_SAMPLE_FORMAT in .env.example).

Usage: uv run python scripts/generate_audio_fixtures.py
Requires: piper-tts (root dev-dependencies), ffmpeg on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPER_DIR = REPO_ROOT / "models" / "piper"
OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "audio"
TARGET_RATE = 16000


def _piper_synthesize(
    text: str, voice: str, out_wav: Path, *, sentence_silence: float = 0.05
) -> None:
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
        str(sentence_silence),
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


def _concat_with_silence(clip_a: Path, clip_b: Path, silence_ms: int, dst: Path) -> None:
    """Concatenate two 16kHz mono s16 WAVs with an exact silence gap between them."""
    with wave.open(str(clip_a), "rb") as wa, wave.open(str(clip_b), "rb") as wb:
        assert wa.getframerate() == wb.getframerate() == TARGET_RATE
        frames_a = wa.readframes(wa.getnframes())
        frames_b = wb.readframes(wb.getnframes())
        sampwidth = wa.getsampwidth()
        nchannels = wa.getnchannels()

    silence_frame_count = int(TARGET_RATE * silence_ms / 1000)
    silence_bytes = b"\x00" * (silence_frame_count * sampwidth * nchannels)

    with wave.open(str(dst), "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(TARGET_RATE)
        out.writeframes(frames_a + silence_bytes + frames_b)


def _write_silence(dst: Path, duration_s: float) -> None:
    n_frames = int(TARGET_RATE * duration_s)
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(TARGET_RATE)
        out.writeframes(b"\x00\x00" * n_frames)


def _duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_DIR / "_tmp"
    tmp.mkdir(exist_ok=True)

    # 1. Clean utterance, ~3s.
    raw = tmp / "clean.wav"
    _piper_synthesize(
        "The deployment finished about ten minutes ago, and it looks good.",
        "en_US-lessac-medium",
        raw,
    )
    clean_dst = OUT_DIR / "clean_utterance_3s.wav"
    _resample_to_contract(raw, clean_dst)

    # 2. Utterance with a 700ms mid-sentence pause.
    part_a_raw = tmp / "pause_a.wav"
    part_b_raw = tmp / "pause_b.wav"
    _piper_synthesize("I checked the logs first,", "en_US-ryan-medium", part_a_raw)
    _piper_synthesize("and found the issue quickly.", "en_US-ryan-medium", part_b_raw)
    part_a = tmp / "pause_a_16k.wav"
    part_b = tmp / "pause_b_16k.wav"
    _resample_to_contract(part_a_raw, part_a)
    _resample_to_contract(part_b_raw, part_b)
    pause_dst = OUT_DIR / "mid_sentence_pause_700ms.wav"
    _concat_with_silence(part_a, part_b, 700, pause_dst)

    # 3. Accented utterance (British English — genuinely distinct from the US voices above).
    accented_raw = tmp / "accented.wav"
    _piper_synthesize(
        "I'd say the whole process took roughly three weeks, give or take a few days.",
        "en_GB-alan-medium",
        accented_raw,
    )
    accented_dst = OUT_DIR / "accented_utterance.wav"
    _resample_to_contract(accented_raw, accented_dst)

    # 4. Two seconds of silence.
    silence_dst = OUT_DIR / "silence_2s.wav"
    _write_silence(silence_dst, 2.0)

    shutil.rmtree(tmp)

    for f in sorted(OUT_DIR.glob("*.wav")):
        print(f"{f.name}: {_duration_seconds(f):.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
