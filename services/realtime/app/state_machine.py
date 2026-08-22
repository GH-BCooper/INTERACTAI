"""The turn/connection state machine (docs/phase-2-BUILD.md TASK 2.1) — replaces Phase 1's
ad-hoc version (docs/decisions/0001). Transition table and timeouts are DATA, not control flow
(Task 2.1's own requirement), so both are testable without a socket, a DB or a clock.

Four deliberate, documented deviations from Task 2.1's literal transition table —
`connecting` kept, `endpointing -> idle` kept, `aborted` implemented as a same-state
transition, `idle -> thinking` added for the scripted opening line — are explained in
docs/decisions/0008-phase-2-state-machine.md. Read that file before changing the table below.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .schemas.ws import ClientState, ServerMachineState

S = ServerMachineState

# ── The transition table — data, not control flow (Task 2.1 requirement) ──────────────────────
_TRANSITIONS: dict[ServerMachineState, frozenset[ServerMachineState]] = {
    S.connecting: frozenset({S.idle, S.closed}),
    # `idle -> thinking` is a second deliberate addition — see docs/decisions/0008 point 3
    # (Task 2.3f's scripted opening line: the persona speaks before any user utterance exists,
    # so there is no `endpointing -> thinking` hop to ride; idle is the only state it can start
    # from).
    S.idle: frozenset({S.listening, S.thinking, S.closing, S.degraded}),
    S.listening: frozenset({S.endpointing, S.listening, S.closing, S.degraded}),
    # `endpointing -> idle` is a deliberate addition, not in Task 2.1's literal table — see
    # docs/decisions/0008-phase-2-state-machine.md point 2 (Task 1.3c's minimum-utterance guard).
    S.endpointing: frozenset({S.thinking, S.listening, S.idle, S.closing, S.degraded}),
    S.thinking: frozenset({S.speaking, S.degraded, S.closing}),
    S.speaking: frozenset({S.idle, S.interrupted, S.degraded, S.closing}),
    S.interrupted: frozenset({S.listening, S.closing}),
    S.closing: frozenset({S.closed}),
    S.degraded: frozenset(
        {S.idle, S.listening, S.endpointing, S.thinking, S.speaking, S.interrupted, S.closing}
    ),
    S.closed: frozenset(),
}

_CLIENT_STATE_MAP: dict[ServerMachineState, ClientState] = {
    S.connecting: ClientState.your_turn,
    S.idle: ClientState.your_turn,
    S.listening: ClientState.your_turn,
    S.endpointing: ClientState.your_turn,
    S.thinking: ClientState.thinking,
    S.speaking: ClientState.speaking,
    S.interrupted: ClientState.your_turn,
    S.degraded: ClientState.connection_trouble,
    S.closing: ClientState.ended,
    S.closed: ClientState.ended,
}

# Task 2.1's timeout table. `None` = no timeout for that state. `idle` carries two: a soft
# "prompt the user" nudge and a hard "abandon the session" ceiling — the second is cumulative
# idle time across the whole session, not time-in-this-visit, so it is NOT modeled here; see
# `SessionRuntime.idle_accumulated_ms` in session.py and docs/decisions/0008 for why.
STATE_TIMEOUT_MS: dict[ServerMachineState, float | None] = {
    S.connecting: None,
    S.idle: 20_000.0,  # SP-09: persona prompts the user
    S.listening: None,  # ENDPOINT_MAX_TURN_MS is enforced by the endpointing cascade itself
    # Task 2.1 states this as "200ms — the cascade must never hang," but the cascade's own
    # legitimate design (Task 1.3b) can hold `endpointing` for far longer than that on purpose:
    # up to ENDPOINT_MAX_SILENCE_MS (900ms) of silence-accumulation, plus up to
    # MAX_EXTENSIONS_PER_UTTERANCE (2) filler/syntax extensions (300ms/250ms), plus the 80ms
    # semantic-check timeout — around 1.5s of genuine, working dwell time in the worst case.
    # A literal 200ms watchdog was verified LIVE (docs/decisions/0008, live-run section) to
    # fire repeatedly during completely ordinary cascade operation, not actual hangs. 2000ms
    # gives real margin above the legitimate worst case while still catching a true stall.
    S.endpointing: 2_000.0,
    # Task 2.1 states this as 5000ms. Live batch evidence (docs/decisions/0008, Phase 2 addendum)
    # is unambiguous that 5000ms is too tight on this project's actual CPU-only dev hardware:
    # `asr_finalize` alone (faster-whisper base.en/int8) measured 2.5-8.2s across runs, so ASR by
    # itself frequently consumes the *entire* budget before a persona reply — real or stub — has
    # any chance to run at all. A clean 55-turn batch with nothing else competing for the machine
    # completed **0 of 55** turns at 5000ms; every one hit this watchdog and degraded. 12000ms
    # gives real margin above the worst observed ASR call plus a persona TTFT on top, while still
    # catching a genuinely hung call rather than waiting forever.
    S.thinking: 12_000.0,
    S.speaking: 5_000.0,  # approximated as "no new audio chunk for 5s" — see decisions/0008
    S.interrupted: None,
    S.closing: 30_000.0,
    S.degraded: None,
    S.closed: None,
}


class IllegalTransitionError(Exception):
    def __init__(self, frm: ServerMachineState, to: ServerMachineState) -> None:
        super().__init__(f"illegal transition {frm.value} -> {to.value}")
        self.frm = frm
        self.to = to


@dataclass
class DegradedInfo:
    """Populated when `state is degraded`, so callers that need "what failed" don't have to
    thread it through separately. The `degraded` WS message (Task 0.3) is still the wire
    carrier of this — this is the server-side mirror of what was last sent."""

    component: str
    recoverable: bool


@dataclass
class StateTransitionRecord:
    frm: ServerMachineState
    to: ServerMachineState
    at_monotonic: float
    duration_in_state_ms: float


@dataclass
class StateMachine:
    state: ServerMachineState = S.connecting
    history: list[StateTransitionRecord] = field(default_factory=list)
    degraded_info: DegradedInfo | None = None
    clock: Callable[[], float] = field(default=time.monotonic, repr=False, compare=False)
    entered_at: float = field(default=0.0)

    def __post_init__(self) -> None:
        if self.entered_at == 0.0:
            self.entered_at = self.clock()

    def can_transition(self, to: ServerMachineState) -> bool:
        return to in _TRANSITIONS[self.state]

    def transition(
        self, to: ServerMachineState, *, degraded_info: DegradedInfo | None = None
    ) -> ServerMachineState:
        if not self.can_transition(to):
            raise IllegalTransitionError(self.state, to)
        now = self.clock()
        self.history.append(
            StateTransitionRecord(
                frm=self.state,
                to=to,
                at_monotonic=now,
                duration_in_state_ms=(now - self.entered_at) * 1000,
            )
        )
        self.state = to
        self.entered_at = now
        self.degraded_info = degraded_info if to is S.degraded else None
        return self.state

    def client_state(self) -> ClientState:
        return _CLIENT_STATE_MAP[self.state]

    def elapsed_in_state_ms(self, now: float | None = None) -> float:
        return ((now if now is not None else self.clock()) - self.entered_at) * 1000

    def is_expired(self, now: float | None = None) -> bool:
        """Task 2.1's timeout table. `speaking` is deliberately excluded here — its timeout is
        "no forward progress," not "time in state," and is checked separately by the caller
        against `SessionRuntime.last_chunk_sent_monotonic` (docs/decisions/0008)."""
        timeout_ms = STATE_TIMEOUT_MS[self.state]
        if timeout_ms is None or self.state is S.speaking:
            return False
        return self.elapsed_in_state_ms(now) >= timeout_ms
