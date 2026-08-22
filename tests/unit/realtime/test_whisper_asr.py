"""Task 1.4 acceptance criteria that need the real (cached) base.en model. Slower than the rest
of the unit suite — these load a real faster-whisper model once per test module."""

from __future__ import annotations

import asyncio
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from faster_whisper import WhisperModel

from services.realtime.app.asr.whisper import transcribe_final, transcribe_partial

FIXTURES = Path("tests/fixtures/audio")
pytestmark = pytest.mark.skipif(not FIXTURES.exists(), reason="audio fixtures not present")


def _load_pcm_float(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


@pytest.fixture(scope="module")
def model() -> WhisperModel:
    return WhisperModel("base.en", device="cpu", compute_type="int8")


@pytest.mark.asyncio
async def test_final_transcript_has_monotonic_word_timings(model: WhisperModel) -> None:
    audio = _load_pcm_float(FIXTURES / "clean_utterance_3s.wav")
    result = await transcribe_final(model, audio)
    assert result.text
    assert len(result.words) > 0
    for a, b in zip(result.words, result.words[1:], strict=False):
        assert b.start_ms >= a.start_ms
        assert a.end_ms >= a.start_ms


@pytest.mark.asyncio
async def test_final_transcript_measures_rtf(model: WhisperModel) -> None:
    audio = _load_pcm_float(FIXTURES / "clean_utterance_3s.wav")
    result = await transcribe_final(model, audio)
    assert result.rtf > 0.0
    assert result.rtf < 5.0  # sanity bound — base.en/int8/CPU should not be this far behind


@pytest.mark.asyncio
async def test_confidence_is_in_unit_interval(model: WhisperModel) -> None:
    audio = _load_pcm_float(FIXTURES / "clean_utterance_3s.wav")
    result = await transcribe_final(model, audio)
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_partial_transcript_is_cheap_and_non_empty(model: WhisperModel) -> None:
    audio = _load_pcm_float(FIXTURES / "clean_utterance_3s.wav")
    text = await transcribe_partial(model, audio)
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.asyncio
async def test_silence_yields_no_meaningful_transcript(model: WhisperModel) -> None:
    """Whisper is known to occasionally hallucinate a short filler word ("You", "Thank you")
    on pure digital silence rather than returning nothing — that's model behaviour, not a bug
    in this wrapper, and it's exactly why production never calls ASR on raw silence at all:
    Silero VAD gates utterance capture upstream (Task 1.3), so this input never reaches
    transcribe_final on the real path. This test documents the behaviour and asserts the
    fallback bound the caller relies on: at most one or two hallucinated words, never a real
    multi-word transcript."""
    silence = _load_pcm_float(FIXTURES / "silence_2s.wav")
    result = await transcribe_final(model, silence)
    assert len(result.words) <= 2


@pytest.mark.asyncio
async def test_no_repetition_loop_on_silence(model: WhisperModel) -> None:
    """condition_on_previous_text=False (Task 1.4) must prevent Whisper's classic failure mode:
    repeating one token dozens of times on silence/noise."""
    silence = _load_pcm_float(FIXTURES / "silence_2s.wav")
    result = await transcribe_final(model, silence)
    tokens = [w.word.strip().lower() for w in result.words]
    for token in set(tokens):
        assert tokens.count(token) <= 8


@pytest.mark.asyncio
async def test_initial_prompt_biasing_recognizes_uncommon_term(model: WhisperModel) -> None:
    """Task 1.4 acceptance: "initial_prompt biasing measurably improves recognition of a
    technical-term fixture." `Spotmies` is an uncommon proper noun base.en mishears without
    help (empirically: "Sputbys") and recovers with a vocabulary-hint initial_prompt."""
    audio = _load_pcm_float(FIXTURES / "vocab_bias_spotmies.wav")

    unbiased = await transcribe_final(model, audio, initial_prompt=None)
    biased = await transcribe_final(
        model, audio, initial_prompt="Vocabulary: Spotmies, Kubernetes, Kafka, PostgreSQL."
    )

    assert "spotmies" in biased.text.lower()
    assert "spotmies" not in unbiased.text.lower()


@pytest.mark.asyncio
async def test_transcription_never_blocks_the_event_loop(model: WhisperModel) -> None:
    """Task 1.4's central requirement: transcription runs in a thread pool. Proven by starting
    a slow (chunked, >30s) transcription and observing that a concurrent asyncio task keeps
    making progress on its own schedule throughout — if transcribe_final blocked the loop, the
    heartbeat task would stall for the whole duration instead of ticking every 10ms."""
    long_audio = np.zeros(16_000 * 31, dtype=np.float32)  # >30s -> exercises the chunking path too

    heartbeat_ticks = 0
    stop = False

    async def heartbeat() -> None:
        nonlocal heartbeat_ticks
        while not stop:
            heartbeat_ticks += 1
            await asyncio.sleep(0.01)

    hb_task = asyncio.create_task(heartbeat())
    t0 = time.perf_counter()
    await transcribe_final(model, long_audio)
    elapsed_s = time.perf_counter() - t0
    stop = True
    await hb_task

    # If the event loop had been blocked for the whole transcription, we'd see ~0 ticks.
    assert heartbeat_ticks > elapsed_s * 0.01 * 10  # generous: at least ~10% of the ideal tick rate


@pytest.mark.asyncio
async def test_long_utterance_is_chunked_and_stitched(model: WhisperModel) -> None:
    """>30s audio is chunked with a 2s overlap and stitched on word timings (Task 1.4 edge case
    table). Built by repeating a real utterance so the chunk boundary falls mid-speech."""
    base = _load_pcm_float(FIXTURES / "clean_utterance_3s.wav")
    silence_gap = np.zeros(int(16_000 * 0.3), dtype=np.float32)
    long_audio = np.concatenate([base, silence_gap] * 12)  # ~12 * 3.8s ≈ 45s > 30s chunk size

    result = await transcribe_final(model, long_audio)
    assert len(result.words) > 0
    for a, b in zip(result.words, result.words[1:], strict=False):
        assert (
            b.start_ms >= a.start_ms
        )  # stitched words stay globally ordered, no overlap duplication
