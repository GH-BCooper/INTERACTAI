"""Task 1.5b acceptance criteria. Voice loading and real synthesis use the actual committed
Piper voices (models/piper/) — no mocking the thing under test. The deadline/fallback
orchestration uses an injected `synth` callable with real asyncio timing but fake (instant or
deliberately slow) audio, since that's testing the *state machine*, not Piper itself.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from services.realtime.app.tts.piper import (
    TARGET_SAMPLE_RATE,
    BackchannelCache,
    HoldingLine,
    VoiceLoadError,
    VoicePool,
    get_voice_or_default,
    synthesize_chunk,
    synthesize_with_deadline,
)

VOICE_DIR = Path("models/piper")
DEFAULT_VOICE = "en_US-lessac-medium"
SECONDARY_VOICE = "en_US-ryan-medium"
pytestmark = pytest.mark.skipif(not VOICE_DIR.exists(), reason="Piper voices not present")


@pytest.fixture(scope="module")
def pool() -> VoicePool:
    return VoicePool(VOICE_DIR)


def test_voice_pool_lazy_loads_and_caches(pool: VoicePool) -> None:
    assert pool.is_loaded(DEFAULT_VOICE) is False
    pool.get(DEFAULT_VOICE)
    assert pool.is_loaded(DEFAULT_VOICE) is True


def test_missing_voice_raises() -> None:
    empty_pool = VoicePool(Path("models/piper/_does_not_exist"))
    with pytest.raises(VoiceLoadError):
        empty_pool.get("no-such-voice")


def test_get_voice_or_default_falls_back_for_missing_persona_voice(pool: VoicePool) -> None:
    voice, used_fallback = get_voice_or_default(pool, "nonexistent-persona-voice", DEFAULT_VOICE)
    assert used_fallback is True
    assert voice is pool.get(DEFAULT_VOICE)


def test_get_voice_or_default_raises_when_default_itself_missing() -> None:
    empty_pool = VoicePool(Path("models/piper/_does_not_exist"))
    with pytest.raises(VoiceLoadError):
        get_voice_or_default(empty_pool, "missing-default", "missing-default")


@pytest.mark.asyncio
async def test_synthesize_chunk_resamples_to_target_rate(pool: VoicePool) -> None:
    result = await synthesize_chunk(pool, DEFAULT_VOICE, "This is a short test sentence.")
    assert result is not None
    audio, sample_rate = result
    assert sample_rate == TARGET_SAMPLE_RATE
    assert audio.dtype == np.float32
    assert len(audio) > 0
    # sanity: a few hundred ms of speech shouldn't be wildly off given the target rate
    duration_s = len(audio) / TARGET_SAMPLE_RATE
    assert 0.2 < duration_s < 5.0


@pytest.mark.asyncio
async def test_synthesize_chunk_returns_none_for_empty_text(pool: VoicePool) -> None:
    result = await synthesize_chunk(pool, DEFAULT_VOICE, "")
    assert result is None


@pytest.mark.asyncio
async def test_deadline_uses_primary_when_fast_enough() -> None:
    async def fake_synth(voice_id: str, _text: str) -> tuple[np.ndarray, int]:
        return np.zeros(10, dtype=np.float32), TARGET_SAMPLE_RATE

    result = await synthesize_with_deadline(
        primary_voice_id="primary",
        secondary_voice_id="secondary",
        text="hi",
        synth=fake_synth,
        deadline_ms=50,
    )
    assert result.used_fallback_voice is False
    assert result.used_holding_line is False
    assert result.audio is not None


@pytest.mark.asyncio
async def test_deadline_falls_back_to_secondary_voice_when_primary_too_slow() -> None:
    async def fake_synth(voice_id: str, _text: str) -> tuple[np.ndarray, int] | None:
        if voice_id == "primary":
            await asyncio.sleep(1.0)  # far past the deadline
            return np.zeros(10, dtype=np.float32), TARGET_SAMPLE_RATE
        return np.zeros(5, dtype=np.float32), TARGET_SAMPLE_RATE

    result = await synthesize_with_deadline(
        primary_voice_id="primary",
        secondary_voice_id="secondary",
        text="hi",
        synth=fake_synth,
        deadline_ms=20,
    )
    assert result.used_fallback_voice is True
    assert result.used_holding_line is False
    assert result.audio is not None
    assert len(result.audio) == 5


@pytest.mark.asyncio
async def test_deadline_falls_back_to_holding_line_when_both_too_slow() -> None:
    async def fake_synth(_voice_id: str, _text: str) -> tuple[np.ndarray, int] | None:
        await asyncio.sleep(1.0)
        return np.zeros(10, dtype=np.float32), TARGET_SAMPLE_RATE

    result = await synthesize_with_deadline(
        primary_voice_id="primary",
        secondary_voice_id="secondary",
        text="hi",
        synth=fake_synth,
        deadline_ms=20,
    )
    assert result.used_holding_line is True
    assert result.audio is None


@pytest.mark.asyncio
async def test_backchannel_cache_preloads_every_phrase(pool: VoicePool) -> None:
    cache = BackchannelCache()
    await cache.preload(pool, [DEFAULT_VOICE])
    assert cache.is_fully_loaded_for(DEFAULT_VOICE) is True
    clip = cache.get(DEFAULT_VOICE, "okay")
    assert clip is not None
    assert clip.sample_rate == TARGET_SAMPLE_RATE
    assert len(clip.pcm) > 0


@pytest.mark.asyncio
async def test_holding_line_preloads(pool: VoicePool) -> None:
    holding = HoldingLine()
    assert holding.get() is None
    await holding.preload(pool, DEFAULT_VOICE)
    clip = holding.get()
    assert clip is not None
    assert len(clip.pcm) > 0
