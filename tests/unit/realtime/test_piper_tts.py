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
    CHUNK_DEADLINE_MS,
    LATER_CHUNK_MS_PER_WORD,
    TARGET_SAMPLE_RATE,
    BackchannelCache,
    HoldingLine,
    VoiceLoadError,
    VoicePool,
    deadline_for_chunk,
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
async def test_a_slow_primary_goes_straight_to_the_holding_line() -> None:
    """docs/decisions/0031: a timeout must NOT start a second synthesis. `synth` ends in
    `asyncio.to_thread`, the abandoned call keeps burning CPU, and racing a retry against it made
    the next chunk miss too — measured at 25/48 chunks missing versus 3/48 genuinely slow. The
    deadline is already spent by the time we know it was missed; a retry cannot win it back."""
    attempted: list[str] = []

    async def fake_synth(voice_id: str, _text: str) -> tuple[np.ndarray, int] | None:
        attempted.append(voice_id)
        if voice_id == "primary":
            await asyncio.sleep(1.0)  # far past the deadline
        return np.zeros(5, dtype=np.float32), TARGET_SAMPLE_RATE

    result = await synthesize_with_deadline(
        primary_voice_id="primary",
        secondary_voice_id="secondary",
        text="hi",
        synth=fake_synth,
        deadline_ms=20,
    )
    assert result.used_holding_line is True
    assert result.used_fallback_voice is False
    assert attempted == ["primary"], "a timeout must not trigger a second synthesis"


@pytest.mark.asyncio
async def test_a_failing_primary_still_falls_back_to_the_secondary_voice() -> None:
    """The other half of 0031's split: an *exception* (missing voice file, corrupt model, engine
    crash) leaves nothing running, so the secondary voice is free to try and can genuinely
    succeed. This is the case a fallback voice exists for."""

    async def fake_synth(voice_id: str, _text: str) -> tuple[np.ndarray, int] | None:
        if voice_id == "primary":
            raise VoiceLoadError("corrupt model")
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


def test_first_chunk_keeps_the_specd_flat_deadline() -> None:
    """The first chunk is the one the user waits on in silence, so it keeps the 400ms number
    from Task 1.5b however long it is — a long opener is a chunker problem, not a licence to
    make the user wait."""
    assert deadline_for_chunk("Thanks for coming in.", is_first_chunk=True) == CHUNK_DEADLINE_MS
    long_text = " ".join(f"word{i}" for i in range(30))
    assert deadline_for_chunk(long_text, is_first_chunk=True) == CHUNK_DEADLINE_MS


def test_later_chunk_deadline_scales_with_length() -> None:
    """The regression this guards: a flat 400ms applied to every chunk meant any sentence past
    ~6 words missed its deadline twice and spoke a holding line *mid-reply*, on every turn."""
    twelve_words = " ".join(f"word{i}" for i in range(12))
    assert deadline_for_chunk(twelve_words, is_first_chunk=False) == pytest.approx(
        12 * LATER_CHUNK_MS_PER_WORD
    )
    # ...and it never drops below the flat deadline for a very short chunk.
    assert deadline_for_chunk("Right.", is_first_chunk=False) == CHUNK_DEADLINE_MS


@pytest.mark.asyncio
async def test_real_first_chunk_synthesis_meets_its_deadline(pool: VoicePool) -> None:
    """The end of the chain the two tests above only describe: a real first chunk, sized by the
    real chunker cap, synthesised by the real committed voice, inside the real deadline. This is
    the test that fails when the ONNX Runtime thread pool is mistuned (docs/decisions/0029) —
    every unit test above it passes in that state while no user ever hears the persona."""
    from services.realtime.app.tts.chunker import FIRST_CHUNK_MAX_WORDS, chunk_text

    first_chunk = chunk_text(
        "So walk me through the deployment you shipped last week and what you checked first."
    )[0]
    assert len(first_chunk.split()) <= FIRST_CHUNK_MAX_WORDS

    async def synth(voice_id: str, text: str) -> tuple[np.ndarray, int] | None:
        return await synthesize_chunk(pool, voice_id, text)

    await synth(DEFAULT_VOICE, "warm the graph up first")  # steady state, not a cold load
    result = await synthesize_with_deadline(
        primary_voice_id=DEFAULT_VOICE,
        secondary_voice_id=SECONDARY_VOICE,
        text=first_chunk,
        synth=synth,
        deadline_ms=deadline_for_chunk(first_chunk, is_first_chunk=True),
    )
    assert result.used_holding_line is False, "first chunk missed the 400ms deadline"
    assert result.used_fallback_voice is False, "primary voice missed the 400ms deadline"
    assert result.audio is not None and len(result.audio) > 0
