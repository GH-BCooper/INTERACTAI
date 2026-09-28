"""Piper synthesis (Task 1.5b). Voices loaded lazily by `voice_id` and cached per process;
synthesis runs in a thread pool (onnxruntime inference is CPU-bound, same rule as VAD/ASR).
Output is always resampled server-side to one fixed 24000 Hz before it leaves this module —
never send mixed rates downstream.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime
from piper import PiperVoice
from piper.config import PiperConfig

from ..core.logging import get_logger

logger = get_logger(__name__)

TARGET_SAMPLE_RATE = 24_000

# The spec'd per-chunk synthesis deadline (docs/phase-1-BUILD Task 1.5b). It is a
# *time-to-first-audio* number: it bounds how long the user waits in silence, which is only
# what the first chunk of a reply actually decides.
CHUNK_DEADLINE_MS = 400.0

# Every later chunk is synthesised while the previous one is still playing, so its real
# constraint is "ready before the queued audio drains", not 400ms. Piper synthesises ~290ms of
# speech per word at ~60ms/word (p95, measured at PIPER_INTRA_OP_THREADS — docs/decisions/0029),
# i.e. roughly 5x faster than playback, so a per-word allowance keeps the holding line for
# genuine engine failures instead of firing on every chunk longer than six words.
LATER_CHUNK_MS_PER_WORD = 90.0

# See `_load_voice` for the benchmark this comes from.
PIPER_INTRA_OP_THREADS = 4
BACKCHANNEL_PHRASES = ("mm-hm", "right", "okay", "sure")
HOLDING_LINE_TEXT = "Sorry, one moment."
IDLE_PROMPT_TEXT = "Whenever you're ready, go ahead."


class VoiceLoadError(Exception):
    pass


def _resample_linear(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Same linear-interpolation approach as the browser capture worklet
    (docs/decisions/0004-worklet-resampling.md) — one algorithm, not two, and good enough for
    speech at this quality level."""
    if src_rate == dst_rate or len(audio) == 0:
        return audio.astype(np.float32, copy=False)
    dst_n = round(len(audio) * dst_rate / src_rate)
    src_positions = np.arange(dst_n) * (src_rate / dst_rate)
    result: np.ndarray = np.interp(src_positions, np.arange(len(audio)), audio).astype(np.float32)
    return result


def _load_voice(model_path: Path) -> PiperVoice:
    """Builds the same `PiperVoice` that `PiperVoice.load()` would (same config-loading and
    provider logic — see its source), except with a constrained `onnxruntime.SessionOptions`.

    `PiperVoice.load()`'s default `SessionOptions()` leaves `intra_op_num_threads` at
    onnxruntime's default (one per physical core), and a small VITS graph like Piper's pays more
    in per-call thread-pool wake/synchronization overhead than it gains from that parallelism —
    see docs/decisions/0011. That finding still holds; its *chosen value* does not. Re-measured
    at steady state (4 warm-up calls, then the median and max of 10, on an otherwise idle
    machine — docs/decisions/0029):

    | `intra_op_num_threads` | short sentence p50 / p95 | 14-word sentence p50 / p95 |
    |---|---|---|
    | 1 | 470 / 537 ms | 1567 / 1589 ms |
    | 2 | 310 / 322 ms | 957 / 985 ms |
    | 4 | **219 / 258 ms** | **717 / 767 ms** |
    | 8 | 664 / 728 ms | 1719 / 1797 ms |
    | default | 841 / 916 ms | 1465 / 1572 ms |

    1 and the onnxruntime default sit on opposite sides of the same curve and 4 is its floor
    here. 0011 measured only the first few calls after a voice load, which are unrepresentatively
    fast (~110-170ms at any thread count) before the session settles — that is why it read 1 as
    the winner. At 1, every real chunk missed the 400ms `CHUNK_DEADLINE_MS` and every persona
    reply degraded to a holding line. `inter_op_num_threads` stays 1: the graph has no parallel
    branches to schedule across. Concurrency across sessions still comes from `asyncio.to_thread`
    dispatching each call to its own OS thread — this only bounds each session's *internal*
    thread pool, which is the one thing `PiperVoice.load()` doesn't let a caller configure."""
    config_path = f"{model_path}.json"
    with open(config_path, encoding="utf-8") as f:
        config_dict = json.load(f)
    sess_options = onnxruntime.SessionOptions()
    sess_options.intra_op_num_threads = PIPER_INTRA_OP_THREADS
    sess_options.inter_op_num_threads = 1
    session = onnxruntime.InferenceSession(
        str(model_path), sess_options=sess_options, providers=["CPUExecutionProvider"]
    )
    return PiperVoice(config=PiperConfig.from_dict(config_dict), session=session)


class VoicePool:
    """Lazily-loaded, per-process voice cache (Task 1.5b)."""

    def __init__(self, voice_dir: Path) -> None:
        self._voice_dir = voice_dir
        self._voices: dict[str, PiperVoice] = {}

    def get(self, voice_id: str) -> PiperVoice:
        if voice_id not in self._voices:
            model_path = self._voice_dir / f"{voice_id}.onnx"
            if not model_path.exists():
                raise VoiceLoadError(f"missing Piper voice: {model_path}")
            self._voices[voice_id] = _load_voice(model_path)
        return self._voices[voice_id]

    def is_loaded(self, voice_id: str) -> bool:
        return voice_id in self._voices


def get_voice_or_default(
    pool: VoicePool, voice_id: str, default_voice_id: str
) -> tuple[PiperVoice, bool]:
    """Task 1.5 edge case: a missing *persona* voice falls back to the default voice, logged;
    the default voice itself missing is a hard startup failure, never silently substituted.
    Returns `(voice, used_fallback)`."""
    try:
        return pool.get(voice_id), False
    except VoiceLoadError:
        if voice_id == default_voice_id:
            raise
        return pool.get(default_voice_id), True


def _load_and_synthesize_sync(pool: VoicePool, voice_id: str, text: str) -> tuple[np.ndarray, int]:
    """Runs entirely off the event loop thread. `VoicePool.get()` is a plain synchronous call
    that, for a not-yet-cached voice, loads an ONNX model and espeak-ng data from disk — calling
    it directly on the event loop (as an earlier version of this function did) blocks it for
    however long that load takes, during which `asyncio.wait_for`'s deadline in
    `synthesize_with_deadline` cannot even be checked, let alone fire. Both the load and the
    synthesis belong in the same thread hop."""
    voice = pool.get(voice_id)
    parts = [chunk.audio_float_array for chunk in voice.synthesize(text)]
    audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    return audio, voice.config.sample_rate


async def synthesize_chunk(
    pool: VoicePool, voice_id: str, text: str
) -> tuple[np.ndarray, int] | None:
    """Returns `(pcm_float32_at_24000hz, sample_rate)`, or `None` if synthesis produced no
    audio at all (Task 1.5 edge case: skip the chunk, log, continue — never send a zero-length
    frame)."""
    audio, src_rate = await asyncio.to_thread(_load_and_synthesize_sync, pool, voice_id, text)
    if len(audio) == 0:
        return None
    return _resample_linear(audio, src_rate, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE


def deadline_for_chunk(text: str, *, is_first_chunk: bool) -> float:
    """The synthesis deadline for one chunk, in milliseconds.

    The first chunk of a reply gets the spec'd `CHUNK_DEADLINE_MS` because it is the one the
    user waits on in silence. Later chunks are overlapped with playback of the chunks already
    sent, so holding them to the same flat 400ms made a normal-length sentence — anything past
    about six words — fail on every attempt and speak a holding line mid-reply."""
    if is_first_chunk:
        return CHUNK_DEADLINE_MS
    return max(CHUNK_DEADLINE_MS, LATER_CHUNK_MS_PER_WORD * len(text.split()))


SynthFn = Callable[[str, str], Awaitable["tuple[np.ndarray, int] | None"]]


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    audio: (
        np.ndarray | None
    )  # float32 @ TARGET_SAMPLE_RATE; None only if the holding line itself is unset
    sample_rate: int
    used_fallback_voice: bool = False
    used_holding_line: bool = False


async def synthesize_with_deadline(
    *,
    primary_voice_id: str,
    secondary_voice_id: str,
    text: str,
    synth: SynthFn,
    deadline_ms: float = CHUNK_DEADLINE_MS,
) -> SynthesisResult:
    """Decides *which* audio to use for one chunk. The caller does the playing and the
    `degraded` (component="tts") signalling, since those need session/websocket context this
    module doesn't have.

    **A chunk that is too slow and a chunk that failed outright are handled differently, and
    this is a deliberate departure from Task 1.5b's "if a chunk takes > 400 ms, fall back to the
    secondary voice".** They read as the same thing — both leave you with no audio — but they
    are not, because of how the timeout works. `synth` ends in `asyncio.to_thread`, and a thread
    is not cancellable: when `wait_for` gives up, the abandoned synthesis keeps running to
    completion, still holding its ONNX Runtime threads. Re-synthesising on the secondary voice at
    that moment puts a second CPU-bound job against the first one, so the retry misses the same
    deadline, and the orphan is still running when the *next* chunk starts. The failures
    compound.

    Measured (48 chunks of four realistic replies, both voices pre-warmed, real chunker splits —
    docs/decisions/0031):

    | | outcome |
    |---|---|
    | secondary-voice retry on timeout | 25/48 chunks missed, p50 719ms, p95 2537ms |
    | same 48 chunks, nothing ever abandoned | p50 142ms, p95 424ms, 3/48 genuinely over 400ms |

    So the retry-on-slow rule manufactured roughly eight times the failures it caught. A timeout
    therefore goes straight to the holding line: the deadline has already been spent, a second
    synthesis cannot beat it, and starting one only damages the chunks that follow.

    An *exception* still falls back to the secondary voice, which is what a fallback voice is
    actually for — a missing voice file, a corrupt model, an engine crash (CLAUDE.md §6's
    SYNTHESIS_* class). Nothing is occupying the CPU in that case, so the retry is free and can
    genuinely succeed."""
    try:
        result = await asyncio.wait_for(synth(primary_voice_id, text), timeout=deadline_ms / 1000)
    except TimeoutError:
        logger.warning(
            "tts_chunk_missed_deadline", voice_id=primary_voice_id, deadline_ms=deadline_ms
        )
        return SynthesisResult(audio=None, sample_rate=TARGET_SAMPLE_RATE, used_holding_line=True)
    except Exception:
        logger.warning("tts_synthesis_failed", voice_id=primary_voice_id, is_fallback=False)
        try:
            result = await asyncio.wait_for(
                synth(secondary_voice_id, text), timeout=deadline_ms / 1000
            )
        except TimeoutError:
            return SynthesisResult(
                audio=None, sample_rate=TARGET_SAMPLE_RATE, used_holding_line=True
            )
        except Exception:
            logger.warning("tts_synthesis_failed", voice_id=secondary_voice_id, is_fallback=True)
            return SynthesisResult(
                audio=None, sample_rate=TARGET_SAMPLE_RATE, used_holding_line=True
            )
        if result is not None:
            audio, sr = result
            return SynthesisResult(audio=audio, sample_rate=sr, used_fallback_voice=True)
        return SynthesisResult(audio=None, sample_rate=TARGET_SAMPLE_RATE, used_holding_line=True)

    if result is not None:
        audio, sr = result
        return SynthesisResult(audio=audio, sample_rate=sr, used_fallback_voice=False)
    return SynthesisResult(audio=None, sample_rate=TARGET_SAMPLE_RATE, used_holding_line=True)


@dataclass(frozen=True, slots=True)
class AudioClip:
    pcm: np.ndarray
    sample_rate: int


class BackchannelCache:
    """Pre-synthesised short acknowledgements per voice, held in memory for zero-latency
    playback (Task 1.5b, TS-07). Consumed by latency masking in Phase 2; built now so it's
    ready when that lands."""

    def __init__(self) -> None:
        self._clips: dict[tuple[str, str], AudioClip] = {}

    async def preload(self, pool: VoicePool, voice_ids: list[str]) -> None:
        for voice_id in voice_ids:
            for phrase in BACKCHANNEL_PHRASES:
                result = await synthesize_chunk(pool, voice_id, phrase)
                if result is not None:
                    audio, sr = result
                    self._clips[(voice_id, phrase)] = AudioClip(pcm=audio, sample_rate=sr)

    def get(self, voice_id: str, phrase: str) -> AudioClip | None:
        return self._clips.get((voice_id, phrase))

    def is_fully_loaded_for(self, voice_id: str) -> bool:
        return all((voice_id, phrase) in self._clips for phrase in BACKCHANNEL_PHRASES)


class IdlePromptCache:
    """Task 2.1's `idle` 20s soft timeout (SP-09: "persona prompts the user"). Keyed per voice,
    same shape as `BackchannelCache` — the nudge has to play in the session's actual persona
    voice, not a fixed one, or a different voice interjecting mid-session reads as broken, not
    reassuring. Pre-synthesised at startup for the same reason as `HoldingLine`: producing it
    must never itself depend on the model path that might be the reason the user has gone
    quiet."""

    def __init__(self) -> None:
        self._clips: dict[str, AudioClip] = {}

    async def preload(self, pool: VoicePool, voice_id: str) -> None:
        result = await synthesize_chunk(pool, voice_id, IDLE_PROMPT_TEXT)
        if result is not None:
            audio, sr = result
            self._clips[voice_id] = AudioClip(pcm=audio, sample_rate=sr)

    def get(self, voice_id: str) -> AudioClip | None:
        return self._clips.get(voice_id)


class HoldingLine:
    """The canned spoken fallback for a TTS failure that survives even the secondary voice
    (Task 1.5b) — pre-synthesised once at startup, never generated on the failure path itself,
    since if synthesis is already failing that is exactly the wrong moment to ask it for more."""

    def __init__(self) -> None:
        self._clip: AudioClip | None = None

    async def preload(self, pool: VoicePool, voice_id: str) -> None:
        result = await synthesize_chunk(pool, voice_id, HOLDING_LINE_TEXT)
        if result is not None:
            audio, sr = result
            self._clip = AudioClip(pcm=audio, sample_rate=sr)

    def get(self) -> AudioClip | None:
        return self._clip
