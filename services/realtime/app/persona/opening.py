"""docs/phase-2-BUILD.md TASK 2.3f: the scripted opening line. "Generated and synthesised
during warm-up, while the user is still reading the scenario card. It plays with near-zero
perceived latency, which sets the user's expectation for the whole session."

Kicked off from `main.py` the moment `ready` is sent (before any user utterance exists), so
generation and synthesis happen while the client is still doing its own local warm-up (mic
permission, rendering the scenario card) rather than after the user has already started
listening for a reply. State-machine note: reaching `speaking` here needs `idle -> thinking`,
which Task 2.1's literal table doesn't have — see docs/decisions/0008 point 4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ..core.ids import uuid7
from ..core.logging import get_logger
from ..tts.chunker import SentenceChunker
from ..tts.piper import SynthFn, synthesize_chunk, synthesize_with_deadline
from .engine import generate_persona_reply
from .prompt import STATIC_TEXT, DynamicContext, PersonaContext

if TYPE_CHECKING:
    from ..session import SessionRuntime
    from ..sink import WsTurnSink
    from ..turn import PipelineResources

logger = get_logger(__name__)

OPENING_TURN_INDEX = -1  # before any real (0-indexed) user turn — see coach/report/build.py's
# `_find_preceding_question`, which looks for the most recent persona turn with a lower index.

_OPENING_INSTRUCTION = (
    "Begin the conversation now, in character. Follow your opening strategy exactly — the "
    "candidate has not said anything yet, so do not respond to or reference anything from "
    "them. Do not explain the format or introduce yourself as an AI."
)


def _float32_to_int16(samples: np.ndarray) -> np.ndarray:
    clamped = np.clip(samples, -1.0, 1.0)
    result: np.ndarray = np.where(clamped < 0, clamped * 0x8000, clamped * 0x7FFF).astype(np.int16)
    return result


async def generate_opening_line(
    *, model: str, max_tokens: int, persona_context: PersonaContext
) -> str:
    dynamic_context = DynamicContext(candidate_speech=_OPENING_INSTRUCTION)
    result = await generate_persona_reply(
        model=model,
        max_tokens=max_tokens,
        persona_context=persona_context,
        dynamic_context=dynamic_context,
        static_prompt_text=STATIC_TEXT,
        turn_index=OPENING_TURN_INDEX,
    )
    return result.text


async def deliver_opening_line(
    *, runtime: SessionRuntime, resources: PipelineResources, sink: WsTurnSink
) -> None:
    """Never raises — a failed opening line falls back to speaking the scenario's
    `opening_strategy` text directly (still in character, just not model-polished), and if even
    that can't synthesize, the session continues silently into `idle` rather than dying before
    it started."""
    persona_context = runtime.persona_context
    if not isinstance(persona_context, PersonaContext):
        return

    model = (
        resources.persona_model_local
        if runtime.persona_use_local_for_remainder
        else resources.persona_model
    )
    try:
        text = await generate_opening_line(
            model=model, max_tokens=resources.max_tokens_per_turn, persona_context=persona_context
        )
    except Exception:
        logger.warning("opening_line_generation_failed", session_id=str(runtime.session_id))
        text = persona_context.opening_strategy
    if not text.strip():
        text = persona_context.opening_strategy
    if not text.strip():
        return  # nothing to say and no fallback strategy text either — stay silent, not crash

    turn_id = uuid7()
    await sink.send_state_change("thinking", turn_id=turn_id)

    async def _synth(voice_id: str, chunk: str) -> tuple[np.ndarray, int] | None:
        return await synthesize_chunk(resources.voice_pool, voice_id, chunk)

    synth_fn: SynthFn = _synth
    chunker = SentenceChunker()
    chunk_seq = 0
    did_speak = False
    for chunk_text in [*chunker.feed(text), *chunker.flush()]:
        result = await synthesize_with_deadline(
            primary_voice_id=runtime.voice_id,
            secondary_voice_id=resources.secondary_voice_id,
            text=chunk_text,
            synth=synth_fn,
        )
        if result.used_holding_line:
            # Task 1.5b's fallback chain applies here too — a chunk that missed its deadline
            # twice is exactly as unplayable as one that errored outright, and the opening
            # line is the *one* moment CLAUDE.md §14 (Task 2.3f) says most sets user
            # expectations; going fully silent here is worse than a generic holding line.
            holding = resources.holding_line.get()
            await sink.send_degraded("tts", "Opening line synthesis missed its deadline.", True)
            if holding is not None:
                if not did_speak:
                    did_speak = True
                    await sink.send_state_change("speaking", turn_id=turn_id)
                await sink.send_audio_chunk(
                    turn_id, chunk_seq, _float32_to_int16(holding.pcm), holding.sample_rate, False
                )
                chunk_seq += 1
            continue
        if result.audio is None or len(result.audio) == 0:
            continue  # zero-length synthesis -> skip, never send a zero-length frame
        if not did_speak:
            did_speak = True
            await sink.send_state_change("speaking", turn_id=turn_id)
        await sink.send_audio_chunk(
            turn_id, chunk_seq, _float32_to_int16(result.audio), result.sample_rate, False
        )
        chunk_seq += 1
        await sink.send_persona_text(turn_id, chunk_text, False)

    await sink.send_persona_text(turn_id, "", True)
    await sink.persist_turn(
        turn_id=turn_id,
        index=OPENING_TURN_INDEX,
        speaker="persona",
        text=text,
        start_ms=0,
        end_ms=0,
        word_timings=[],
        truncated=False,
        asr_confidence=None,
    )
    runtime.persona_history.append({"speaker": "persona", "text": text})
    if did_speak:
        await sink.send_state_change("idle", turn_id=turn_id)
    else:
        await sink.send_degraded("tts", "Opening line could not be synthesized.", True)
        await sink.send_state_change("degraded", turn_id=turn_id, component="tts", recoverable=True)
        await sink.send_state_change("idle", turn_id=turn_id)
