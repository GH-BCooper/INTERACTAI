"""Session pinning (Task 1.1): `SessionRuntime` owns everything the socket, the state machine
and the turn pipeline need across the session's lifetime; `SessionRegistry` is the process-wide
`dict[UUID, SessionRuntime]` that makes "which server holds this session" answerable without a
network round trip.

A session is pinned to exactly one process for its lifetime (CLAUDE.md §2: realtime is
stateful) — there is deliberately no cross-process handoff. If the process restarts, the
runtime is gone and `resume` must fail fast (`ORCHESTRATION_SESSION_LOST`), never pretend.
"""

from __future__ import annotations

import asyncio
import time
import uuid as std_uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from .audio.ingest import IngestRateLimiter, SequenceTracker, SessionWavWriter
from .endpointing.cascade import AdaptiveThresholdTracker
from .state_machine import StateMachine
from .vad.silero import FrameAccumulator, HysteresisVad, SileroVad


class SocketLike(Protocol):
    async def send_text(self, data: str) -> None: ...
    async def send_bytes(self, data: bytes) -> None: ...


@dataclass
class SessionRuntime:
    """One live (or recently-live, within the resume grace window) session. Everything here is
    in-process memory only — nothing about a runtime survives a process restart by design."""

    session_id: std_uuid.UUID
    user_id: std_uuid.UUID
    websocket: SocketLike
    state_machine: StateMachine = field(default_factory=StateMachine)
    seq_tracker: SequenceTracker = field(default_factory=SequenceTracker)
    rate_limiter: IngestRateLimiter = field(default_factory=IngestRateLimiter)
    wav_writer: SessionWavWriter | None = None

    server_seq: int = 0
    client_seq_seen: int = -1
    turn_index: int = 0

    session_start_monotonic: float = field(default_factory=time.monotonic)
    connected_at: float = field(default_factory=time.monotonic)
    disconnected_at: float | None = None
    finalized: bool = False

    # ── Turn pipeline state (Task 1.3-1.6) — None/absent until a VAD session is attached ────
    vad: HysteresisVad | None = None
    frame_accumulator: FrameAccumulator = field(default_factory=FrameAccumulator)
    adaptive_threshold: AdaptiveThresholdTracker = field(default_factory=AdaptiveThresholdTracker)
    current_utterance: object | None = None  # turn.UtteranceBuffer; typed loosely to avoid a cycle
    speaking_task: asyncio.Task[None] | None = None
    turn_progress: object | None = None  # turn.TurnProgress; same reason
    latency_recorder: object | None = None  # metrics.latency.LatencyRecorder; same reason
    interrupt_guard_ms: float = 0.0
    muted: bool = False
    persona_stub: bool = False
    voice_id: str = "en_US-lessac-medium"

    # ── Task 2.1: state timeout supervision ──────────────────────────────────────────────────
    # Cumulative time spent in `idle` across the whole session (not "time since this visit
    # began" — that's `state_machine.elapsed_in_state_ms()`). Task 2.1's 120s "end session,
    # user_abandoned" timeout is defined as a session total, so it lives here, not on the
    # per-visit StateMachine. Incremented by the watchdog poll loop (timeouts.py).
    idle_accumulated_ms: float = 0.0
    idle_prompted: bool = False
    # "no forward progress" proxy for the `speaking` timeout — see docs/decisions/0008.
    last_chunk_sent_monotonic: float | None = None
    thinking_retry_used: bool = False
    closing_started_monotonic: float | None = None

    # ── Task 2.1 degraded / 2.3e: persona model fallback for the rest of the session ────────
    # Once True, every subsequent persona call uses MODEL_PERSONA_LOCAL instead of MODEL_PERSONA
    # (Task 2.1's degraded table: "Persona model 429 / error -> switch to MODEL_PERSONA_LOCAL for
    # the remainder of the session"). Session-lifetime, not turn-lifetime, on purpose.
    persona_use_local_for_remainder: bool = False
    asr_use_downgraded_for_remainder: bool = False

    # ── Task 2.3: persona agent state, lives on the runtime (not the DB) while the session is
    # live — mirrored to `sessions.question_plan` at checkpoints so a resumed session can read
    # it back, but the in-memory copy here is authoritative during the session itself.
    question_plan: dict[str, object] | None = None
    persona_history: list[dict[str, str]] = field(default_factory=list)
    persona_history_summary: str = ""
    turns_since_summary: int = 0
    recent_persona_questions: list[str] = field(default_factory=list)
    backchannel_turns_used: int = 0
    last_turn_was_backchannel: bool = False
    # PersonaContext (persona/prompt.py); typed loosely to avoid a session<->persona import
    # cycle risk, same reasoning as current_utterance/turn_progress above. Set once at hello
    # time from `sessions.brief` (Task 0.5's frozen brief), never mutated after.
    persona_context: object | None = None
    compaction_in_flight: bool = False
    # Live-run finding (docs/decisions/0008): the opening-line delivery task
    # (persona/opening.py) and the frame-ingest loop start concurrently. A replay client (or a
    # real user who starts talking immediately) can push the state machine from `idle` to
    # `listening` before the opening line gets to make its own `idle -> thinking` transition,
    # which is illegal and crashes the warm-up task. Gates VAD/state processing in
    # `_receive_messages` until warm-up finishes — raw frames are still written to disk
    # immediately regardless (Task 1.2c's crash-safety is untouched). Starts True whenever
    # there is nothing to wait for (persona_stub, or no PersonaContext at all).
    warm_up_complete: bool = True

    # ── Task 2.6 (AS-07): distress exit ──────────────────────────────────────────────────────
    # Set by `turn.py::process_turn` once the persona has *finished speaking* a real distress-
    # exit reply (never mid-speech — cutting the persona's own caring message off partway
    # through would defeat the point of it). `timeouts.py`'s watchdog polls this and ends the
    # session with `end_reason="distress_exit"` once it sees it, the same indirection
    # `on_idle_abandon` already uses to reach `main.py::_begin_closing` without this module
    # importing main.py.
    distress_exit_pending: bool = False

    # ── Task 2.2d: coach enqueue ─────────────────────────────────────────────────────────────
    # turn_ids whose `score_turn` enqueue failed (Redis unreachable) and must be retried once,
    # at session close — never silently dropped (Task 2.2d's own acceptance criterion).
    pending_score_turn_ids: list[std_uuid.UUID] = field(default_factory=list)

    # ── Task 2.2a: resume — replay of missed control messages ───────────────────────────────
    # Every JSON control message actually sent, newest last, capped at 100 (Task 2.2a: "a
    # bounded ring buffer (last 100 messages)"). Audio is deliberately never buffered here
    # (Task 2.2a: "stale audio in a live conversation is worse than silence").
    sent_message_log: deque[tuple[int, str]] = field(default_factory=lambda: deque(maxlen=100))

    # ── Task 2.2c: periodic checkpoint upload ────────────────────────────────────────────────
    last_checkpoint_monotonic: float | None = None

    def attach_vad(self, vad_session: object) -> None:
        self.vad = HysteresisVad(vad=SileroVad(vad_session))

    def next_server_seq(self) -> int:
        seq = self.server_seq
        self.server_seq += 1
        return seq

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.session_start_monotonic) * 1000)

    def mark_disconnected(self) -> None:
        self.disconnected_at = time.monotonic()

    def mark_reconnected(self, websocket: SocketLike) -> None:
        self.websocket = websocket
        self.disconnected_at = None


Finalizer = Callable[[SessionRuntime], Awaitable[None]]


class SessionRegistry:
    """The in-process `dict[UUID, SessionRuntime]` (Task 1.1). One instance per realtime
    process, held on `app.state`. `clock` is injectable so tests can exercise the 90s resume
    grace window without real sleeping."""

    def __init__(
        self,
        *,
        resume_grace_s: float = 90.0,
        sweep_interval_s: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._runtimes: dict[std_uuid.UUID, SessionRuntime] = {}
        self._resume_grace_s = resume_grace_s
        self._sweep_interval_s = sweep_interval_s
        self._clock = clock
        self._sweeper_task: asyncio.Task[None] | None = None

    def __len__(self) -> int:
        return len(self._runtimes)

    def get(self, session_id: std_uuid.UUID) -> SessionRuntime | None:
        return self._runtimes.get(session_id)

    def try_register(self, runtime: SessionRuntime) -> bool:
        """Task 1.1 edge case: "Second socket for a live session" -> reject the new one,
        existing socket authoritative. Returns False if a live (non-finalized) runtime already
        holds this session_id."""
        existing = self._runtimes.get(runtime.session_id)
        if existing is not None and not existing.finalized:
            return False
        self._runtimes[runtime.session_id] = runtime
        return True

    def is_within_resume_grace(self, session_id: std_uuid.UUID) -> bool:
        runtime = self._runtimes.get(session_id)
        if runtime is None or runtime.finalized or runtime.disconnected_at is None:
            return False
        return (self._clock() - runtime.disconnected_at) <= self._resume_grace_s

    async def finalize(self, session_id: std_uuid.UUID, finalizer: Finalizer) -> None:
        """Idempotent (Task 1.1: "finalising twice must not produce two report jobs") — a
        runtime already finalized, or already gone, is a no-op."""
        runtime = self._runtimes.get(session_id)
        if runtime is None or runtime.finalized:
            return
        runtime.finalized = True
        try:
            await finalizer(runtime)
        finally:
            self._runtimes.pop(session_id, None)

    def sweep_expired(self) -> list[std_uuid.UUID]:
        now = self._clock()
        return [
            sid
            for sid, rt in self._runtimes.items()
            if rt.disconnected_at is not None
            and not rt.finalized
            and (now - rt.disconnected_at) > self._resume_grace_s
        ]

    async def start_sweeper(self, finalizer: Finalizer) -> None:
        async def _loop() -> None:
            while True:
                await asyncio.sleep(self._sweep_interval_s)
                for sid in self.sweep_expired():
                    await self.finalize(sid, finalizer)

        self._sweeper_task = asyncio.create_task(_loop())

    async def stop_sweeper(self) -> None:
        if self._sweeper_task is None:
            return
        self._sweeper_task.cancel()
        try:
            await self._sweeper_task
        except asyncio.CancelledError:
            pass
        self._sweeper_task = None
