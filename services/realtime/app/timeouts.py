"""State timeout supervision (docs/phase-2-BUILD.md TASK 2.1, "every state has one"). The pure
decision of *whether* a state has timed out lives on `StateMachine.is_expired()`
(state_machine.py) precisely so it's testable with a fake clock and no event loop; this module
is the live side — a per-runtime poll loop that acts on that decision.

A poll loop rather than one `asyncio.wait_for`/timer per state was a deliberate choice: state
transitions in this codebase happen from several call sites (`frame_pipeline.py`, `turn.py`,
`main.py`), and a timer-per-state design would need every one of them to cancel/reschedule a
handle on every transition. A single watchdog reading `is_expired()` on a short poll interval
gets the same effective latency (well under any of Task 2.1's timeout values) with one place to
reason about instead of N.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .core.logging import get_logger
from .schemas.ws import ServerMachineState
from .session import SessionRuntime
from .sink import WsTurnSink
from .turn import PipelineResources
from .turn import float32_to_int16 as _f32_to_i16

logger = get_logger(__name__)

POLL_INTERVAL_S = 0.25
IDLE_ABANDON_MS = 120_000.0

OnIdleAbandon = Callable[[], Awaitable[None]]


async def _handle_idle_prompt(
    runtime: SessionRuntime, resources: PipelineResources, sink: WsTurnSink
) -> None:
    """SP-09, Task 2.1's `idle` 20s soft timeout: nudge the user, don't end anything. Fires at
    most once per idle *visit* — `runtime.idle_prompted` resets on every transition away from
    idle (see `_reset_per_visit_flags`), so a still-silent user gets nudged again next visit
    rather than spammed every 250ms poll tick forever."""
    if runtime.idle_prompted:
        return
    runtime.idle_prompted = True
    clip = resources.idle_prompt_cache.get(runtime.voice_id)
    if clip is None:
        return
    from .core.ids import uuid7

    turn_id = uuid7()
    await sink.send_audio_chunk(turn_id, 0, _f32_to_i16(clip.pcm), clip.sample_rate, True)


async def _handle_idle_abandon(runtime: SessionRuntime, on_idle_abandon: OnIdleAbandon) -> None:
    """Task 2.1's `idle` 120s hard ceiling — cumulative across the session, not one visit (see
    `SessionRuntime.idle_accumulated_ms`'s docstring). `on_idle_abandon` is
    `main.py::_begin_closing` bound with `end_reason="user_abandoned"` — full session
    termination (upload, DB close, `session_closed`, socket close) needs the registry and DB
    session this module deliberately doesn't have, same reasoning as `sink.py`'s narrow
    `SocketLike` protocol."""
    logger.info("idle_abandon_timeout", session_id=str(runtime.session_id))
    await on_idle_abandon()


async def _handle_endpointing_timeout(runtime: SessionRuntime, sink: WsTurnSink) -> None:
    """Task 2.1: "the cascade must never hang." In normal operation the cascade always resolves
    well under 200ms (the semantic check alone has an 80ms hard timeout — cascade.py); reaching
    this handler means something outside the cascade's own bookkeeping stalled. Forcing
    `thinking` here without a finalized utterance would leave `process_turn` with nothing to
    transcribe, so this degrades rather than fabricates a turn."""
    logger.warning("endpointing_watchdog_forced", session_id=str(runtime.session_id))
    await sink.send_degraded("transport", "Endpoint decision took too long.", True)
    await sink.send_state_change("degraded", component="transport", recoverable=True)
    await sink.send_state_change("listening")


async def _cancel_turn_task(runtime: SessionRuntime) -> None:
    """Shared by the `thinking`/`speaking` timeout handlers: cancel the in-flight
    `process_turn` task and swallow whatever it raises on unwind — a cancelled task raising
    something other than `CancelledError` from its own cleanup is expected (e.g. a TTS call mid
    `await`) and is not this handler's problem to surface twice; `process_turn` and its callees
    already log their own failures."""
    task = runtime.speaking_task
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass  # the expected outcome of cancelling it — not a failure to log
    except Exception as exc:  # noqa: BLE001 — deliberately broad, see docstring
        logger.info("turn_task_cancelled", session_id=str(runtime.session_id), error=str(exc))


async def _handle_thinking_timeout(runtime: SessionRuntime, sink: WsTurnSink) -> None:
    """Task 2.1's `thinking` 5s timeout: degrade, play the holding line (already the TTS
    fallback path's job once a chunk is attempted — here nothing has been synthesized yet, so
    this handler's job is narrower: stop waiting on a stuck persona call and let the turn
    resolve via the degraded path rather than hang the session). One retry is modeled as "the
    next turn is allowed to try the primary model again" (`thinking_retry_used` gates it),
    matching Task 2.1's "retry once, then fallback model" without re-entering the same
    in-flight (and already-cancelled) call."""
    await _cancel_turn_task(runtime)
    if runtime.thinking_retry_used:
        runtime.persona_use_local_for_remainder = True
    runtime.thinking_retry_used = True
    await sink.send_degraded("persona", "The persona model took too long to respond.", True)
    await sink.send_state_change("degraded", component="persona", recoverable=True)
    await sink.send_state_change("idle")


async def _handle_speaking_timeout(runtime: SessionRuntime, sink: WsTurnSink) -> None:
    """Task 2.1's `speaking` timeout, approximated as "no new audio chunk for 5s" — see
    docs/decisions/0008. Stops playback (client-side, once it sees `degraded`) and returns to
    `idle` via `degraded`, same as the "every chunk failed" branch in `turn.py`."""
    await _cancel_turn_task(runtime)
    await sink.send_degraded("tts", "Playback stalled.", True)
    await sink.send_state_change("degraded", component="tts", recoverable=True)
    await sink.send_state_change("idle")


def _reset_per_visit_flags(runtime: SessionRuntime, new_state: ServerMachineState) -> None:
    if new_state is not ServerMachineState.idle:
        runtime.idle_prompted = False


async def run_state_watchdog(
    runtime: SessionRuntime,
    resources: PipelineResources,
    sink: WsTurnSink,
    *,
    on_idle_abandon: OnIdleAbandon,
    on_distress_exit: OnIdleAbandon,
    poll_interval_s: float = POLL_INTERVAL_S,
) -> None:
    """One instance per live session, started alongside the receive loop and cancelled on
    disconnect/finalize (same lifecycle as `LatencyRecorder`'s periodic flush — see
    `main.py::_receive_loop`). `closing`'s 30s timeout is deliberately NOT handled here — it's
    enforced as a bounded `asyncio.wait_for` inside `main.py::_begin_closing` itself, which is a
    simpler and more directly testable way to bound "how long finalize is allowed to hang" than
    routing it back through a poll loop that has no handle on the finalize task."""
    last_seen_state = runtime.state_machine.state
    while True:
        await asyncio.sleep(poll_interval_s)
        sm = runtime.state_machine
        if sm.state != last_seen_state:
            _reset_per_visit_flags(runtime, sm.state)
            last_seen_state = sm.state

        if runtime.distress_exit_pending:
            # Task 2.6 (AS-07): `process_turn` only sets this once the persona has *finished*
            # speaking its distress-exit line — checked ahead of the normal `idle` handling
            # below so a session that lands in `idle` for this reason never gets treated as an
            # ordinary quiet moment (no idle-prompt nudge, no accumulating toward the ordinary
            # 120s abandon timeout first).
            logger.info("distress_exit_triggered", session_id=str(runtime.session_id))
            await on_distress_exit()
            return  # the session is ending — nothing left for this watchdog to supervise

        if sm.state is ServerMachineState.idle:
            runtime.idle_accumulated_ms += poll_interval_s * 1000
            if runtime.idle_accumulated_ms >= IDLE_ABANDON_MS:
                await _handle_idle_abandon(runtime, on_idle_abandon)
                return  # the session is ending — nothing left for this watchdog to supervise
            if sm.elapsed_in_state_ms() >= 20_000.0 and not runtime.idle_prompted:
                await _handle_idle_prompt(runtime, resources, sink)
            continue

        if sm.state is ServerMachineState.speaking:
            last_chunk = runtime.last_chunk_sent_monotonic
            if last_chunk is not None and (sm.clock() - last_chunk) * 1000 >= 5_000.0:
                await _handle_speaking_timeout(runtime, sink)
            continue

        if sm.state in (ServerMachineState.closing, ServerMachineState.closed):
            return  # supervised elsewhere / terminal

        if not sm.is_expired():
            continue

        if sm.state is ServerMachineState.endpointing:
            await _handle_endpointing_timeout(runtime, sink)
        elif sm.state is ServerMachineState.thinking:
            await _handle_thinking_timeout(runtime, sink)
