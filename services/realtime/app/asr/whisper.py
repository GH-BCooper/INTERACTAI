"""Streaming ASR (Task 1.4). One `faster-whisper` model instance per process, loaded once at
startup and shared across every session. Every transcription call runs through
`asyncio.to_thread` — it's CPU-bound and would otherwise block the event loop for every other
concurrent session. This is, per the spec, the single most important line in this file.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field

import numpy as np
from faster_whisper import WhisperModel

CHUNK_S = 30.0
OVERLAP_S = 2.0
SAMPLE_RATE = 16_000


def load_asr_model(
    model_name: str, *, compute_type: str = "int8", device: str = "cpu"
) -> WhisperModel:
    """Fails fast at boot if the model file/name is bad — never start half-loaded (Task 1.4
    edge case table)."""
    return WhisperModel(model_name, device=device, compute_type=compute_type)


@dataclass(frozen=True, slots=True)
class WordTiming:
    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class TranscriptResult:
    text: str
    words: list[WordTiming]
    confidence: float  # mean segment logprob mapped to [0, 1]
    rtf: float  # seconds of compute per second of audio


def confidence_from_avg_logprob(avg_logprob: float) -> float:
    """exp() maps a mean log-probability back into probability space; clamped because a very
    negative logprob (near-total noise) would otherwise underflow below a usable [0, 1] score."""
    return max(0.0, min(1.0, math.exp(avg_logprob)))


async def transcribe_partial(
    model: WhisperModel, audio: np.ndarray, *, initial_prompt: str | None = None
) -> str:
    """Task 1.4: re-transcribe the buffered utterance every ~500ms during `listening`,
    beam_size=1 (greedy). Cosmetic only — never lets a slow partial block audio ingest, because
    it runs off-thread and its result is never awaited by the ingest path."""

    def _run() -> str:
        segments, _info = model.transcribe(
            audio,
            beam_size=1,
            word_timestamps=False,
            condition_on_previous_text=False,
            vad_filter=False,
            initial_prompt=initial_prompt,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    return await asyncio.to_thread(_run)


def _transcribe_chunk_sync(
    model: WhisperModel, audio: np.ndarray, *, offset_ms: int, initial_prompt: str | None
) -> tuple[list[WordTiming], list[float], float]:
    t0 = time.perf_counter()
    segments, _info = model.transcribe(
        audio,
        beam_size=5,
        word_timestamps=True,
        condition_on_previous_text=False,
        vad_filter=False,
        initial_prompt=initial_prompt,
    )
    segments = list(segments)
    elapsed_s = time.perf_counter() - t0
    audio_duration_s = len(audio) / SAMPLE_RATE
    rtf = elapsed_s / audio_duration_s if audio_duration_s > 0 else 0.0

    words: list[WordTiming] = []
    logprobs: list[float] = []
    for seg in segments:
        logprobs.append(seg.avg_logprob)
        for w in seg.words or []:
            words.append(
                WordTiming(
                    word=w.word.strip(),
                    start_ms=offset_ms + round(w.start * 1000),
                    end_ms=offset_ms + round(w.end * 1000),
                )
            )
    return words, logprobs, rtf


async def transcribe_final(
    model: WhisperModel, audio: np.ndarray, *, initial_prompt: str | None = None
) -> TranscriptResult:
    """Task 1.4 final pass: beam_size=5, word_timestamps=True,
    condition_on_previous_text=False (prevents the repetition-loop failure mode on silence/
    noise). Utterances over 30s are chunked with a 2s overlap and stitched on word timings
    (Task 1.4 edge case table)."""
    audio_duration_s = len(audio) / SAMPLE_RATE

    if audio_duration_s <= CHUNK_S:
        words, logprobs, rtf = await asyncio.to_thread(
            _transcribe_chunk_sync, model, audio, offset_ms=0, initial_prompt=initial_prompt
        )
        confidence = confidence_from_avg_logprob(sum(logprobs) / len(logprobs)) if logprobs else 0.0
        text = " ".join(w.word for w in words)
        return TranscriptResult(text=text, words=words, confidence=confidence, rtf=rtf)

    stride_s = CHUNK_S - OVERLAP_S
    all_words: list[WordTiming] = []
    all_logprobs: list[float] = []
    all_rtfs: list[float] = []

    start_s = 0.0
    while True:
        end_s = min(start_s + CHUNK_S, audio_duration_s)
        chunk = audio[int(start_s * SAMPLE_RATE) : int(end_s * SAMPLE_RATE)]
        offset_ms = round(start_s * 1000)
        words, logprobs, rtf = await asyncio.to_thread(
            _transcribe_chunk_sync, model, chunk, offset_ms=offset_ms, initial_prompt=initial_prompt
        )
        # Drop words landing in this chunk's overlap with the *previous* chunk — the previous
        # chunk already covered that audio with cleaner boundary context.
        cutoff_ms = offset_ms + round(OVERLAP_S * 1000)
        kept = words if start_s == 0.0 else [w for w in words if w.start_ms >= cutoff_ms]
        all_words.extend(kept)
        all_logprobs.extend(logprobs)
        all_rtfs.append(rtf)

        if end_s >= audio_duration_s:
            break
        start_s += stride_s

    all_words.sort(key=lambda w: w.start_ms)
    confidence = (
        confidence_from_avg_logprob(sum(all_logprobs) / len(all_logprobs)) if all_logprobs else 0.0
    )
    text = " ".join(w.word for w in all_words)
    return TranscriptResult(
        text=text, words=all_words, confidence=confidence, rtf=sum(all_rtfs) / len(all_rtfs)
    )


@dataclass
class RtfMonitor:
    """Task 1.4: "If RTF > 0.8 over a rolling window of 5 turns, automatically downgrade to
    tiny.en... Log the switch. Never silently degrade quality without recording it."""

    window: int = 5
    threshold: float = 0.8
    _history: list[float] = field(default_factory=list)

    def record(self, rtf: float) -> None:
        self._history.append(rtf)
        if len(self._history) > self.window:
            self._history.pop(0)

    def should_downgrade(self) -> bool:
        if len(self._history) < self.window:
            return False
        return (sum(self._history) / self.window) > self.threshold
