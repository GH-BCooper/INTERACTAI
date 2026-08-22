"""The turn pipeline (Task 1.6) — wires VAD, the endpointing cascade, ASR, the persona, the
chunker and TTS into one coroutine per turn, instrumented at every stage (Task 1.6a). This is
what `_receive_loop` in `main.py` calls once the cascade decides a turn has ended, and what the
CLI harness (Task 1.6b) closes the loop against.

Runs as a background `asyncio.Task` per turn (see `SessionRuntime.speaking_task` in
`session.py`) so incoming mic frames keep being read — and fed to the VAD-based interrupt
guard — while the persona is thinking and speaking. True full-duplex barge-in is out of scope
(CLAUDE.md §9); this is the documented cheap approximation (Task 1.5d).
"""

from __future__ import annotations

import asyncio
import time
import uuid as std_uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from .asr.confidence import is_confident, pick_clarification
from .asr.delivery_metrics import compute_delivery_metrics
from .asr.whisper import RtfMonitor, transcribe_final
from .core.config import get_settings
from .core.ids import uuid7
from .core.logging import get_logger
from .endpointing.cascade import AdaptiveThresholdTracker, EndpointState
from .metrics.latency import LatencyRecorder, stage
from .metrics.model_calls import ModelCallRecord, ModelCallWriter, record_model_call
from .persona.engine import PersonaReplyResult, generate_persona_reply
from .persona.minimal import canned_stub_reply
from .persona.prompt import PROMPT_VERSION as PERSONA_PROMPT_VERSION
from .persona.prompt import STATIC_TEXT, DynamicContext, PersonaContext
from .persona.question_plan import advance_plan, current_topic, is_plan_exhausted
from .persona.safety import is_distress_exit_reply
from .persona.similarity import is_repeated_question
from .persona.vagueness import is_answer_vague
from .schemas.ws import Stage as StageName
from .session import SessionRuntime
from .tts.chunker import SentenceChunker
from .tts.piper import (
    BACKCHANNEL_PHRASES,
    BackchannelCache,
    HoldingLine,
    IdlePromptCache,
    SynthFn,
    VoicePool,
    synthesize_with_deadline,
)

logger = get_logger(__name__)

UPSTREAM_FRAME_MS = 20
ASR_DOWNGRADE_TARGET_MODEL = "tiny.en"


class TurnSink(Protocol):
    """What `process_turn` needs from the caller — deliberately narrow, so this module never
    touches the WebSocket, the DB session, or the ASR model registry directly. `main.py` wires
    the real implementations; tests wire fakes."""

    async def send_state_change(
        self,
        state: str,
        *,
        turn_id: std_uuid.UUID | None = None,
        component: str | None = None,
        recoverable: bool = True,
    ) -> None: ...
    async def send_partial_transcript(self, text: str, stability: float) -> None: ...
    async def send_turn_finalized(
        self,
        turn_id: std_uuid.UUID,
        text: str,
        start_ms: int,
        end_ms: int,
        confidence: float,
        words: list[dict[str, Any]],
    ) -> None: ...
    async def send_persona_text(self, turn_id: std_uuid.UUID, delta: str, done: bool) -> None: ...
    async def send_audio_chunk(
        self,
        turn_id: std_uuid.UUID,
        chunk_seq: int,
        audio_int16: np.ndarray,
        sample_rate: int,
        is_final: bool,
    ) -> None: ...
    async def send_degraded(self, component: str, message: str, recoverable: bool) -> None: ...
    async def send_interrupted(
        self, turn_id: std_uuid.UUID, at_ms: int, truncated_text: str
    ) -> None: ...
    async def send_latency_report(
        self, turn_id: std_uuid.UUID, stage_ms: dict[str, float], e2e_ms: float
    ) -> None: ...
    async def persist_turn(
        self,
        *,
        turn_id: std_uuid.UUID,
        index: int,
        speaker: str,
        text: str,
        start_ms: int,
        end_ms: int,
        word_timings: list[dict[str, Any]],
        truncated: bool,
        asr_confidence: float | None,
    ) -> None: ...
    async def persist_turn_metrics(
        self,
        *,
        turn_id: std_uuid.UUID,
        wpm: float,
        filler_count: int,
        filler_rate: float,
        longest_pause_ms: int,
        speech_ratio: float,
        word_count: int,
    ) -> None: ...


@dataclass
class PipelineResources:
    """Process-global, shared across every session — loaded once at startup (Task 1.1/1.3/1.4)."""

    asr_model: Any
    voice_pool: VoicePool
    backchannel_cache: BackchannelCache
    holding_line: HoldingLine
    idle_prompt_cache: IdlePromptCache
    model_calls_writer: ModelCallWriter
    persona_model: str
    persona_model_local: str
    default_voice_id: str
    secondary_voice_id: str
    clarification_pool: list[str]
    max_tokens_per_turn: int = 180
    rtf_monitor: RtfMonitor = field(default_factory=RtfMonitor)


@dataclass
class TurnProgress:
    """Published by `process_turn` as it runs so a concurrent stop-on-speech interrupt (Task
    1.5d) can read `turn_id` and what was actually sent so far after cancelling the task —
    "the text actually spoken... not from chunks generated" means the caller needs this
    visible from outside the (about-to-be-cancelled) coroutine's local variables."""

    turn_id: std_uuid.UUID | None = None
    sent_text_parts: list[str] = field(default_factory=list)


@dataclass
class UtteranceBuffer:
    """Accumulates one in-progress utterance's audio and endpointing state. Lives on
    `SessionRuntime` between `on_frame` calls (Task 1.3b/c)."""

    start_ms: int
    frames: list[np.ndarray] = field(default_factory=list)
    endpoint_state: EndpointState = field(
        default_factory=lambda: EndpointState(
            silence_ms=0.0, utterance_duration_ms=0.0, threshold_ms=500.0
        )
    )
    partial_transcript: str = ""
    windows_since_partial: int = 0
    last_voiced_monotonic: float = field(default_factory=time.perf_counter)
    partial_in_flight: bool = False

    def append(self, samples: np.ndarray) -> None:
        self.frames.append(samples)

    def concat(self) -> np.ndarray:
        if not self.frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.frames)


def int16_bytes_to_float32(payload: bytes) -> np.ndarray:
    return np.frombuffer(payload, dtype=np.int16).astype(np.float32) / 32768.0


def float32_to_int16(samples: np.ndarray) -> np.ndarray:
    clamped = np.clip(samples, -1.0, 1.0)
    result: np.ndarray = np.where(clamped < 0, clamped * 0x8000, clamped * 0x7FFF).astype(np.int16)
    return result


def should_play_backchannel(
    *, runtime: SessionRuntime, persona_context: PersonaContext | None, turn_index: int
) -> bool:
    """Task 2.4 point 3 (PA-10): "at most 1 in 3 turns, never twice consecutively, never at hard
    difficulty, never before a wrap-up." Pure function of runtime state so it's directly
    testable without a live session. `turn_index` is this turn's 0-based index — checked, not
    `runtime.turn_index`, which `frame_pipeline.py` has already advanced past it by the time
    `process_turn` runs."""
    settings = get_settings()
    if not settings.backchannel_enabled or persona_context is None:
        return False
    if persona_context.difficulty.challenge_claims or persona_context.difficulty.time_pressure:
        # difficulty.py: both are absent/False on gentle and standard, present/True only on
        # hard — there's no separate tier name on DifficultyParams, so this is the tier check.
        return False
    if runtime.last_turn_was_backchannel:
        return False
    if is_plan_exhausted(runtime.question_plan):
        return False
    turns_including_this_one = turn_index + 1
    prospective_rate = (runtime.backchannel_turns_used + 1) / turns_including_this_one
    return prospective_rate <= settings.backchannel_rate_max


async def process_turn(
    *,
    resources: PipelineResources,
    latency: LatencyRecorder,
    sink: TurnSink,
    runtime: SessionRuntime,
    session_id: std_uuid.UUID,
    turn_index: int,
    utterance: UtteranceBuffer,
    end_ms: int,
    adaptive_threshold: AdaptiveThresholdTracker,
    progress: TurnProgress,
    endpoint_detect_ms: float,
    last_voiced_monotonic: float,
) -> None:
    """One full turn: ASR final -> confidence gate -> persona -> chunker -> TTS. Cancellable —
    stop-on-speech cancels the enclosing asyncio.Task, which unwinds this coroutine at whatever
    `await` it's suspended on (Task 1.5d). `progress` is published as we go so the caller can
    read it after cancellation."""
    voice_id = runtime.voice_id
    persona_stub = runtime.persona_stub
    turn_id = uuid7()
    progress.turn_id = turn_id
    audio = utterance.concat()
    stage_ms: dict[str, float] = {"endpoint_detect": endpoint_detect_ms}
    latency.record(session_id, turn_id, StageName.endpoint_detect, endpoint_detect_ms)

    @asynccontextmanager
    async def _measured_stage(name: StageName) -> AsyncGenerator[None]:
        t0 = time.perf_counter()
        async with stage(latency, session_id, turn_id, name):
            yield
        stage_ms[name.value] = (time.perf_counter() - t0) * 1000

    await sink.send_state_change("thinking", turn_id=turn_id)

    persona_context = (
        runtime.persona_context if isinstance(runtime.persona_context, PersonaContext) else None
    )
    chunk_seq = 0
    spoke_backchannel = False
    if should_play_backchannel(
        runtime=runtime, persona_context=persona_context, turn_index=turn_index
    ):
        clip = resources.backchannel_cache.get(
            voice_id, BACKCHANNEL_PHRASES[turn_index % len(BACKCHANNEL_PHRASES)]
        )
        if clip is not None:
            spoke_backchannel = True
            await sink.send_state_change("speaking", turn_id=turn_id)
            await sink.send_audio_chunk(
                turn_id, chunk_seq, float32_to_int16(clip.pcm), clip.sample_rate, False
            )
            chunk_seq += 1
    runtime.last_turn_was_backchannel = spoke_backchannel
    if spoke_backchannel:
        runtime.backchannel_turns_used += 1

    async with _measured_stage(StageName.asr_finalize):
        result = await transcribe_final(resources.asr_model, audio)
    resources.rtf_monitor.record(result.rtf)
    if resources.rtf_monitor.should_downgrade():
        logger.warning("asr_rtf_downgrade", session_id=str(session_id), rtf=result.rtf)
        await sink.send_degraded("asr", "ASR running behind real time; quality reduced.", True)

    word_timings_raw = [
        {"word": w.word, "start_ms": w.start_ms, "end_ms": w.end_ms} for w in result.words
    ]

    if not result.text.strip():
        return  # empty transcript on a real utterance -> discard, no turn (Task 1.4 edge case)

    if not is_confident(result.confidence):
        text_for_persona = pick_clarification(resources.clarification_pool, turn_index)
        is_clarification = True
    else:
        text_for_persona = result.text
        is_clarification = False

    metrics = compute_delivery_metrics(
        result.words, utterance_start_ms=utterance.start_ms, utterance_end_ms=end_ms
    )
    adaptive_threshold.record_utterance([metrics.longest_pause_ms])

    await sink.send_turn_finalized(
        turn_id, result.text, utterance.start_ms, end_ms, result.confidence, word_timings_raw
    )
    await sink.persist_turn(
        turn_id=turn_id,
        index=turn_index,
        speaker="user",
        text=result.text,
        start_ms=utterance.start_ms,
        end_ms=end_ms,
        word_timings=word_timings_raw,
        truncated=False,
        asr_confidence=result.confidence,
    )
    await sink.persist_turn_metrics(
        turn_id=turn_id,
        wpm=metrics.wpm,
        filler_count=metrics.filler_count,
        filler_rate=metrics.filler_rate,
        longest_pause_ms=metrics.longest_pause_ms,
        speech_ratio=metrics.speech_ratio,
        word_count=metrics.word_count,
    )

    if persona_context is not None and persona_context.difficulty.silence_after_answer_ms > 0:
        # Task 2.3c: enforced in code, not just prompt text — hard difficulty's deliberate
        # pause after the candidate finishes answering (the pressure it's meant to create is a
        # real elapsed delay, not something a model can be trusted to improvise consistently).
        await asyncio.sleep(persona_context.difficulty.silence_after_answer_ms / 1000)

    dynamic_context: DynamicContext | None = None
    async with _measured_stage(StageName.prompt_assemble):
        if persona_context is not None and not persona_stub:
            dynamic_context = _build_dynamic_context(
                runtime,
                candidate_speech=text_for_persona,
                target_minutes=persona_context.target_minutes,
            )

    chunker = SentenceChunker()
    persona_text_parts: list[str] = []
    did_speak = spoke_backchannel  # backchannel already sent real audio for this turn
    ttft_ms: float | None = None
    reply_result: PersonaReplyResult | None = None
    is_distress_exit = False

    async def _mark_speaking_once() -> None:
        """Fires on the real reply's first chunk even when a backchannel already played —
        `e2e`/`tts_first_chunk` must keep measuring genuine model+synthesis speed, not how often
        a cached backchannel clip happened to go out first (CLAUDE.md §8/§10: never let a UX
        trick suppress the metric meant to catch real slowness). Only the redundant
        `speaking`-state re-announcement is skipped — the state machine is already there."""
        nonlocal did_speak
        if not spoke_backchannel:
            if did_speak:
                return
            did_speak = True
            await sink.send_state_change("speaking", turn_id=turn_id)
        e2e_ms = (time.perf_counter() - last_voiced_monotonic) * 1000
        if "e2e" not in stage_ms:
            stage_ms["e2e"] = e2e_ms
            latency.record(session_id, turn_id, StageName.e2e, e2e_ms)

    async def _emit_chunk(text_chunk: str) -> None:
        nonlocal chunk_seq
        async with _measured_stage(
            StageName.tts_first_chunk if chunk_seq == 0 else StageName.first_chunk_assemble
        ):
            synth = _make_synth_fn(resources)
            result = await synthesize_with_deadline(
                primary_voice_id=voice_id,
                secondary_voice_id=resources.secondary_voice_id,
                text=text_chunk,
                synth=synth,
            )
        if result.used_holding_line:
            holding = resources.holding_line.get()
            await sink.send_degraded("tts", "Synthesis failed; playing a holding line.", True)
            if holding is not None:
                await _mark_speaking_once()
                await sink.send_audio_chunk(
                    turn_id, chunk_seq, float32_to_int16(holding.pcm), holding.sample_rate, False
                )
                chunk_seq += 1
            return
        if result.audio is None or len(result.audio) == 0:
            return  # zero-length synthesis -> skip, never send a zero-length frame
        await _mark_speaking_once()
        await sink.send_audio_chunk(
            turn_id, chunk_seq, float32_to_int16(result.audio), result.sample_rate, False
        )
        chunk_seq += 1
        progress.sent_text_parts.append(text_chunk)

    if persona_stub or persona_context is None or dynamic_context is None:
        # persona_stub (Task 1.6b, still used by Task 2.4's pipeline-latency isolation), or no
        # PersonaContext was ever attached to this runtime (should not happen once main.py's
        # Task 2.3 wiring runs, but a missing context degrades to a canned line, never a crash).
        reply_text = canned_stub_reply(turn_index)
        persona_text_parts.append(reply_text)
        for chunk_text in chunker.feed(reply_text):
            await _emit_chunk(chunk_text)
            await sink.send_persona_text(turn_id, chunk_text, False)
    elif is_clarification:
        # Task 1.4/SP-08: below-confidence transcripts get a clarification line the persona
        # *speaks directly* — `text_for_persona` already *is* that line (picked by
        # `pick_clarification` above), not something to feed to the model as if it were the
        # candidate's speech and hope for a sensible reply. No model call, no cost, no chance
        # of the model inventing something unrelated to the actual ASR failure.
        persona_text_parts.append(text_for_persona)
        for chunk_text in chunker.feed(text_for_persona):
            await _emit_chunk(chunk_text)
            await sink.send_persona_text(turn_id, chunk_text, False)
    else:
        model = (
            resources.persona_model_local
            if runtime.persona_use_local_for_remainder
            else resources.persona_model
        )
        reply_result = await generate_persona_reply(
            model=model,
            max_tokens=resources.max_tokens_per_turn,
            persona_context=persona_context,
            dynamic_context=dynamic_context,
            static_prompt_text=STATIC_TEXT,
            turn_index=turn_index,
        )
        if reply_result.ttft_ms is not None:
            ttft_ms = reply_result.ttft_ms
            stage_ms[StageName.model_ttft.value] = ttft_ms
            latency.record(session_id, turn_id, StageName.model_ttft, ttft_ms)
        is_distress_exit = is_distress_exit_reply(reply_result.text)
        if is_distress_exit:
            logger.info("persona_distress_exit", session_id=str(session_id), turn_id=str(turn_id))
        persona_text_parts.append(reply_result.text)
        for chunk_text in chunker.feed(reply_result.text):
            await _emit_chunk(chunk_text)
            await sink.send_persona_text(turn_id, chunk_text, False)
        if reply_result.violations and not reply_result.used_canned_deflection:
            logger.info(
                "persona_character_break",
                session_id=str(session_id),
                turn_id=str(turn_id),
                violations=reply_result.violations,
            )

    for chunk_text in chunker.flush():
        await _emit_chunk(chunk_text)
        await sink.send_persona_text(turn_id, chunk_text, False)

    full_reply = "".join(persona_text_parts).strip()
    await sink.send_persona_text(turn_id, "", True)
    await sink.send_latency_report(turn_id, stage_ms, stage_ms.get("e2e", 0.0))

    persona_turn_id = uuid7()
    await sink.persist_turn(
        turn_id=persona_turn_id,
        index=turn_index,
        speaker="persona",
        text=full_reply,
        start_ms=end_ms,
        end_ms=end_ms,
        word_timings=[],
        truncated=False,
        asr_confidence=None,
    )

    if not persona_stub and reply_result is not None:
        # docs/decisions/0010: `cached` is always False for Groq — the provider exposes no
        # cache-hit signal to measure it from, not a claim caching isn't happening.
        await record_model_call(
            resources.model_calls_writer,
            ModelCallRecord(
                session_id=session_id,
                turn_id=turn_id,
                role="persona",
                model=resources.persona_model_local
                if runtime.persona_use_local_for_remainder
                else resources.persona_model,
                prompt_version=PERSONA_PROMPT_VERSION,
                tokens_in=reply_result.tokens_in,
                tokens_out=reply_result.tokens_out,
                ttft_ms=reply_result.ttft_ms,
                total_latency_ms=reply_result.total_latency_ms,
                cost_cents=reply_result.cost_cents,
                cached=reply_result.cached,
            ),
        )

    if (
        persona_context is not None
        and not persona_stub
        and not is_clarification
        and not is_distress_exit
    ):
        # Task 2.3b/2.3d: conversation memory and plan state, updated after every real
        # (non-clarification, non-stub) turn. A clarification exchange isn't a real answer to
        # advance the plan on, and never happened as far as the persona's own memory is
        # concerned — repeating the question next turn would be wrong. A distress exit is
        # skipped for the same reason plus a stronger one (Task 2.6/AS-07): the session is
        # ending right now, so there's no "next turn" for this memory/plan update to serve.
        runtime.persona_history.append({"speaker": "user", "text": result.text})
        runtime.persona_history.append({"speaker": "persona", "text": full_reply})
        runtime.turns_since_summary += 1

        if reply_result is not None and not reply_result.used_canned_deflection and full_reply:
            if is_repeated_question(full_reply, runtime.recent_persona_questions):
                logger.info(
                    "persona_repeated_question", session_id=str(session_id), turn_id=str(turn_id)
                )
            runtime.recent_persona_questions.append(full_reply)
            runtime.recent_persona_questions = runtime.recent_persona_questions[-10:]

        if isinstance(runtime.question_plan, dict):
            vague = is_answer_vague(word_count=metrics.word_count, filler_rate=metrics.filler_rate)
            existing_obligation = runtime.question_plan.get("pending_obligation")
            runtime.question_plan = advance_plan(
                runtime.question_plan,
                followups_cap=persona_context.difficulty.followups_on_vague,
                answer_was_vague=vague,
                obligation=existing_obligation if isinstance(existing_obligation, str) else None,
            )

    if not did_speak:
        # Every chunk failed even its holding line (e.g. the holding line itself never
        # preloaded) — "thinking" has no direct edge to "idle" in the state machine, so route
        # through "degraded" first, which does (Task 1.1's transition table).
        await sink.send_degraded("tts", "No audio could be produced for this turn.", True)
        await sink.send_state_change("degraded", turn_id=turn_id, component="tts", recoverable=True)
    await sink.send_state_change("idle", turn_id=turn_id)
    if is_distress_exit:
        # Only set once the persona has *finished speaking* its distress-exit line — never
        # mid-speech, or the watchdog (which polls every 250ms, timeouts.py) could end the
        # session before the caring message it's meant to protect has actually been delivered.
        runtime.distress_exit_pending = True


def _make_synth_fn(resources: PipelineResources) -> SynthFn:
    from .tts.piper import synthesize_chunk

    async def _synth(voice_id: str, text: str) -> tuple[np.ndarray, int] | None:
        return await synthesize_chunk(resources.voice_pool, voice_id, text)

    return _synth


def _build_dynamic_context(
    runtime: SessionRuntime, *, candidate_speech: str, target_minutes: int
) -> DynamicContext:
    """Task 2.3a's per-turn dynamic layer, assembled from the runtime state Task 2.3b/2.3d
    maintain. Pure with respect to `runtime` — reads only, mutation happens after generation
    (see the state-update block above)."""
    plan = runtime.question_plan if isinstance(runtime.question_plan, dict) else None
    topic = current_topic(plan)
    obligation = plan.get("pending_obligation") if plan else None
    return DynamicContext(
        candidate_speech=candidate_speech,
        recent_turns=runtime.persona_history[-6:],
        history_summary=runtime.persona_history_summary,
        elapsed_minutes=int(runtime.elapsed_ms() / 60_000),
        target_minutes=target_minutes,
        plan_topic=str(topic["topic"]) if topic else None,
        pending_obligation=obligation if isinstance(obligation, str) else None,
    )
