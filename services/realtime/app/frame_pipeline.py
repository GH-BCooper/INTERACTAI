"""Per-VAD-window state machine driving (Task 1.3/1.5d) — the glue between raw audio frames
and `turn.process_turn`. Kept separate from `main.py` so the ingest loop stays readable: this
module owns "what does one 512-sample VAD decision mean right now," `main.py` owns the socket.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import numpy as np

from .asr.whisper import transcribe_partial
from .core.config import get_settings
from .core.logging import get_logger
from .endpointing.cascade import EndpointDecision, is_utterance_too_short, resolve_endpoint
from .metrics.latency import LatencyRecorder
from .persona.memory import split_recent_and_older, summarize_history
from .schemas.ws import ServerMachineState
from .session import SessionRuntime
from .sink import WsTurnSink
from .turn import PipelineResources, TurnProgress, UtteranceBuffer, process_turn

logger = get_logger(__name__)

WINDOW_MS = 512 / 16_000 * 1000  # 32.0 — Silero's fixed window size at 16kHz
INTERRUPT_GUARD_MS = 250.0
PARTIAL_TRANSCRIPT_INTERVAL_WINDOWS = round(500 / WINDOW_MS)  # ~500ms, Task 1.4

SemanticChecker = Callable[[str], Awaitable[bool]] | None


async def _run_partial_transcript(
    resources: PipelineResources, sink: WsTurnSink, utt: UtteranceBuffer
) -> None:
    """Task 1.4: "never let a partial pass block the audio ingest path." Fired as a background
    task from `handle_speech_window` rather than awaited inline — the ingest loop keeps
    consuming frames while this runs. `partial_in_flight` prevents a second one starting before
    this one finishes (the ASR call is far slower than the ~500ms firing interval on a loaded
    CPU, and overlapping calls would only make that worse)."""
    try:
        audio = utt.concat()
        text = await transcribe_partial(resources.asr_model, audio)
        utt.partial_transcript = text
        await sink.send_partial_transcript(text, stability=0.5)
    finally:
        utt.partial_in_flight = False


async def _run_compaction(runtime: SessionRuntime, model: str) -> None:
    """Task 2.3d: "regenerated every 6 turns by MODEL_NARRATOR, during listening, never during
    thinking." Fired as a background task from `listening` (never awaited inline — compaction
    latency must never delay ingest, same reasoning as `_run_partial_transcript`)."""
    try:
        older, _recent = split_recent_and_older(runtime.persona_history)
        if not older:
            return
        runtime.persona_history_summary = await summarize_history(
            model, previous_summary=runtime.persona_history_summary, older_turns=older
        )
        runtime.turns_since_summary = 0
    finally:
        runtime.compaction_in_flight = False


def _current_utterance(runtime: SessionRuntime) -> UtteranceBuffer:
    """`runtime.current_utterance` is typed loosely (`object | None`) to avoid a session<->turn
    import cycle (session.py); this is the one place that narrows it back, only ever called
    from branches where the state machine guarantees it is already set."""
    if not isinstance(runtime.current_utterance, UtteranceBuffer):
        raise RuntimeError("expected an in-progress utterance for this state")
    return runtime.current_utterance


async def handle_speech_window(
    *,
    runtime: SessionRuntime,
    resources: PipelineResources,
    latency: LatencyRecorder,
    sink: WsTurnSink,
    window: np.ndarray,
    now_ms: float,
    semantic_checker: SemanticChecker,
) -> None:
    """Runs the VAD decision + endpointing cascade for one window while in idle/listening/
    endpointing. Spawns `process_turn` as a background task once the cascade decides END."""
    if runtime.vad is None:
        raise RuntimeError("handle_speech_window called before a VAD session was attached")
    is_speech = runtime.vad.observe(window)
    state = runtime.state_machine.state

    if state is ServerMachineState.idle:
        if not is_speech:
            return
        utt = UtteranceBuffer(start_ms=int(now_ms))
        utt.append(window)
        runtime.current_utterance = utt
        await sink.send_state_change("listening")
        return

    if state is ServerMachineState.listening:
        if not isinstance(runtime.current_utterance, UtteranceBuffer):
            # A slow ASR call inside `process_turn` can't actually be interrupted by
            # `task.cancel()` while it's blocked in `asyncio.to_thread` — cancellation only
            # takes effect once the underlying OS thread returns control to the event loop, so
            # a `thinking`-timeout-forced `idle` (timeouts.py::_handle_thinking_timeout) can race
            # a still-in-flight ASR call finishing and touching runtime state after this frame
            # loop has already moved on to a *new* utterance. Found live: `current_utterance`
            # ended up `None` while state still claimed `listening`/`endpointing`, and the old
            # unconditional `_current_utterance()` call turned that race into an unhandled
            # `RuntimeError` that crashed the whole connection. Recovering here — not crashing —
            # is the same "degrades before it dies" policy CLAUDE.md §6 applies everywhere else.
            logger.warning(
                "utterance_buffer_missing_recovering",
                session_id=str(runtime.session_id),
                state=state.value,
            )
            await sink.send_state_change("degraded", component="orchestration", recoverable=True)
            await sink.send_state_change("idle")
            return
        listening_utt = _current_utterance(runtime)
        listening_utt.append(window)
        if is_speech:
            listening_utt.last_voiced_monotonic = time.perf_counter()
        listening_utt.windows_since_partial += 1
        if (
            listening_utt.windows_since_partial >= PARTIAL_TRANSCRIPT_INTERVAL_WINDOWS
            and not listening_utt.partial_in_flight
        ):
            listening_utt.windows_since_partial = 0
            listening_utt.partial_in_flight = True
            asyncio.create_task(_run_partial_transcript(resources, sink, listening_utt))
        if (
            runtime.turns_since_summary >= get_settings().memory_compaction_every_n_turns
            and not runtime.compaction_in_flight
        ):
            runtime.compaction_in_flight = True
            # Task 2.3d: "regenerated ... by MODEL_NARRATOR" — deliberately not the persona
            # model; summarizing is a different role even when both happen to resolve to the
            # same underlying model today.
            asyncio.create_task(_run_compaction(runtime, get_settings().model_narrator))
        if not is_speech:
            await sink.send_state_change("endpointing")
        return

    if state is ServerMachineState.endpointing:
        if not isinstance(runtime.current_utterance, UtteranceBuffer):
            # Same race as the `listening` branch above, and `endpointing -> idle` is already a
            # legal transition (Task 2.1's table), so no `degraded` detour is needed here.
            logger.warning(
                "utterance_buffer_missing_recovering",
                session_id=str(runtime.session_id),
                state=state.value,
            )
            await sink.send_state_change("idle")
            return
        utt = _current_utterance(runtime)
        utt.append(window)
        if is_speech:
            utt.endpoint_state.silence_ms = 0.0
            utt.last_voiced_monotonic = time.perf_counter()
            await sink.send_state_change("listening")
            return

        utt.endpoint_state.silence_ms += WINDOW_MS
        utt.endpoint_state.utterance_duration_ms = now_ms - utt.start_ms
        utt.endpoint_state.transcript_tail = utt.partial_transcript[-120:]
        decision = await resolve_endpoint(utt.endpoint_state, semantic_checker)
        if decision is EndpointDecision.CONTINUE:
            return

        if is_utterance_too_short(utt.endpoint_state.utterance_duration_ms):
            runtime.current_utterance = None
            await sink.send_state_change("idle")
            return

        endpoint_detect_ms = (time.perf_counter() - utt.last_voiced_monotonic) * 1000
        end_ms = int(now_ms)
        turn_index = runtime.turn_index
        runtime.turn_index += 1
        runtime.current_utterance = None
        progress = TurnProgress()
        runtime.turn_progress = progress
        runtime.speaking_task = asyncio.create_task(
            process_turn(
                resources=resources,
                latency=latency,
                sink=sink,
                runtime=runtime,
                endpoint_detect_ms=endpoint_detect_ms,
                last_voiced_monotonic=utt.last_voiced_monotonic,
                session_id=runtime.session_id,
                turn_index=turn_index,
                utterance=utt,
                end_ms=end_ms,
                adaptive_threshold=runtime.adaptive_threshold,
                progress=progress,
            )
        )
        return


async def handle_interrupt_window(*, runtime: SessionRuntime, window: np.ndarray) -> bool:
    """Task 1.5d: sustained voiced audio (250ms) during `speaking` triggers a stop-on-speech
    interrupt. Returns True the instant the guard interval is crossed."""
    if runtime.vad is None:
        raise RuntimeError("handle_interrupt_window called before a VAD session was attached")
    is_speech = runtime.vad.observe(window)
    if is_speech:
        runtime.interrupt_guard_ms += WINDOW_MS
        if runtime.interrupt_guard_ms >= INTERRUPT_GUARD_MS:
            runtime.interrupt_guard_ms = 0.0
            return True
    else:
        runtime.interrupt_guard_ms = 0.0
    return False


async def do_interrupt(*, runtime: SessionRuntime, sink: WsTurnSink) -> None:
    """Cancels the in-flight `process_turn` task, records what was actually sent as the
    truncated persona turn, and returns to `listening` (Task 1.5d)."""
    from .core.ids import uuid7

    task = runtime.speaking_task
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    runtime.speaking_task = None

    progress: TurnProgress | None = runtime.turn_progress  # type: ignore[assignment]
    turn_id = progress.turn_id if progress and progress.turn_id else uuid7()
    truncated_text = " ".join(progress.sent_text_parts).strip() if progress else ""
    runtime.turn_progress = None

    # Task 2.1's table has no direct speaking -> listening edge any more: `interrupted` is a
    # real machine state now (docs/decisions/0008), so this is two hops, not one.
    runtime.state_machine.transition(ServerMachineState.interrupted)
    at_ms = runtime.elapsed_ms()
    await sink.send_interrupted(turn_id, at_ms, truncated_text)
    await sink.send_state_change("listening", turn_id=turn_id)
    await sink.persist_turn(
        turn_id=uuid7(),
        index=runtime.turn_index,
        speaker="persona",
        text=truncated_text,
        start_ms=at_ms,
        end_ms=at_ms,
        word_timings=[],
        truncated=True,
        asr_confidence=None,
    )
