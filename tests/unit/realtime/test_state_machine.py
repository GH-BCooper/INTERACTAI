"""Every transition and every illegal transition, one row per state (CLAUDE.md §7). The table
under test here is docs/phase-2-BUILD.md Task 2.1's, with the four deliberate deviations
documented in docs/decisions/0008-phase-2-state-machine.md (`connecting` kept,
`endpointing -> idle` kept, `aborted` implemented as `listening -> listening`, `idle -> thinking`
added for the scripted opening line)."""

from __future__ import annotations

import pytest

from services.realtime.app.schemas.ws import ClientState
from services.realtime.app.schemas.ws import ServerMachineState as S
from services.realtime.app.state_machine import (
    STATE_TIMEOUT_MS,
    DegradedInfo,
    IllegalTransitionError,
    StateMachine,
)

LEGAL = [
    (S.connecting, S.idle),
    (S.connecting, S.closed),
    (S.idle, S.listening),
    (S.idle, S.thinking),
    (S.idle, S.closing),
    (S.idle, S.degraded),
    (S.listening, S.endpointing),
    (S.listening, S.listening),
    (S.listening, S.closing),
    (S.listening, S.degraded),
    (S.endpointing, S.thinking),
    (S.endpointing, S.listening),
    (S.endpointing, S.idle),
    (S.endpointing, S.closing),
    (S.endpointing, S.degraded),
    (S.thinking, S.speaking),
    (S.thinking, S.degraded),
    (S.thinking, S.closing),
    (S.speaking, S.idle),
    (S.speaking, S.interrupted),
    (S.speaking, S.degraded),
    (S.speaking, S.closing),
    (S.interrupted, S.listening),
    (S.interrupted, S.closing),
    (S.closing, S.closed),
    (S.degraded, S.idle),
    (S.degraded, S.listening),
    (S.degraded, S.endpointing),
    (S.degraded, S.thinking),
    (S.degraded, S.speaking),
    (S.degraded, S.interrupted),
    (S.degraded, S.closing),
]

ILLEGAL = [
    (S.connecting, S.listening),
    (S.connecting, S.speaking),
    (S.connecting, S.interrupted),
    (S.idle, S.endpointing),
    (S.idle, S.speaking),
    (S.idle, S.interrupted),
    (S.idle, S.closed),
    (S.listening, S.thinking),
    (S.listening, S.speaking),
    (S.listening, S.idle),
    (S.listening, S.interrupted),
    (S.endpointing, S.speaking),
    (S.endpointing, S.interrupted),
    (S.thinking, S.idle),
    (S.thinking, S.listening),
    (S.thinking, S.endpointing),
    (S.thinking, S.interrupted),
    (S.speaking, S.endpointing),
    (S.speaking, S.thinking),
    (S.speaking, S.listening),  # must go through `interrupted`, not directly (Task 2.1)
    (S.interrupted, S.idle),
    (S.interrupted, S.speaking),
    (S.interrupted, S.degraded),
    (S.closing, S.idle),
    (S.closing, S.degraded),
    (S.closing, S.closing),
    (S.degraded, S.degraded),
    (S.degraded, S.closed),
    (S.degraded, S.connecting),
    (S.closed, S.idle),
    (S.closed, S.listening),
    (S.closed, S.connecting),
    (S.closed, S.degraded),
    (S.closed, S.closing),
]


@pytest.mark.parametrize(("frm", "to"), LEGAL)
def test_legal_transition(frm: S, to: S) -> None:
    sm = StateMachine(state=frm)
    assert sm.can_transition(to) is True
    assert sm.transition(to) == to
    assert sm.state == to
    assert len(sm.history) == 1
    assert sm.history[0].frm == frm
    assert sm.history[0].to == to


@pytest.mark.parametrize(("frm", "to"), ILLEGAL)
def test_illegal_transition_rejected(frm: S, to: S) -> None:
    sm = StateMachine(state=frm)
    assert sm.can_transition(to) is False
    with pytest.raises(IllegalTransitionError):
        sm.transition(to)
    assert sm.state == frm  # rejected transition must not mutate state
    assert sm.history == []


def test_every_state_covered_by_at_least_one_legal_and_one_illegal_case() -> None:
    covered_legal = {frm for frm, _ in LEGAL}
    covered_illegal = {frm for frm, _ in ILLEGAL}
    for state in S:
        if state is not S.closed:  # closed has no legal exits by design
            assert state in covered_legal, f"{state} missing a legal-transition test"
        assert state in covered_illegal, f"{state} missing an illegal-transition test"


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (S.connecting, ClientState.your_turn),
        (S.idle, ClientState.your_turn),
        (S.listening, ClientState.your_turn),
        (S.endpointing, ClientState.your_turn),
        (S.thinking, ClientState.thinking),
        (S.speaking, ClientState.speaking),
        (S.interrupted, ClientState.your_turn),
        (S.degraded, ClientState.connection_trouble),
        (S.closing, ClientState.ended),
        (S.closed, ClientState.ended),
    ],
)
def test_client_state_collapse(state: S, expected: ClientState) -> None:
    assert StateMachine(state=state).client_state() == expected


def test_closed_is_terminal() -> None:
    sm = StateMachine(state=S.closed)
    for candidate in S:
        assert sm.can_transition(candidate) is False


def test_degraded_info_recorded_on_entry_and_cleared_on_exit() -> None:
    sm = StateMachine(state=S.thinking)
    sm.transition(S.degraded, degraded_info=DegradedInfo(component="persona", recoverable=True))
    assert sm.degraded_info == DegradedInfo(component="persona", recoverable=True)
    sm.transition(S.idle)
    assert sm.degraded_info is None


def test_degraded_info_ignored_when_target_is_not_degraded() -> None:
    """Passing degraded_info for a non-degraded target is a caller bug, not a crash — the
    field simply isn't stored, since it's only meaningful attached to `degraded` itself."""
    sm = StateMachine(state=S.thinking)
    sm.transition(S.speaking, degraded_info=DegradedInfo(component="tts", recoverable=True))
    assert sm.degraded_info is None


# ── Timeouts (Task 2.1: "every state has one") ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "state",
    [S.idle, S.endpointing, S.thinking, S.closing],
)
def test_state_has_a_configured_timeout(state: S) -> None:
    assert STATE_TIMEOUT_MS[state] is not None


@pytest.mark.parametrize(
    "state",
    [S.connecting, S.listening, S.interrupted, S.degraded, S.closed],
)
def test_state_has_no_generic_timeout_by_design(state: S) -> None:
    """`listening`'s bound is enforced by ENDPOINT_MAX_TURN_MS inside the endpointing cascade
    itself (Task 1.3c), not the state machine; `speaking`'s is handled separately (see
    `test_speaking_excluded_from_is_expired` below) — both deliberate, not oversights."""
    assert STATE_TIMEOUT_MS[state] is None


def test_is_expired_forces_expiry_for_every_timed_state() -> None:
    fake_now = [0.0]
    for state, timeout_ms in STATE_TIMEOUT_MS.items():
        if timeout_ms is None or state is S.speaking:
            continue
        sm = StateMachine(state=state, clock=lambda: fake_now[0])
        assert sm.is_expired() is False
        fake_now[0] = timeout_ms / 1000 - 0.001
        assert sm.is_expired() is False, f"{state} expired too early"
        fake_now[0] = timeout_ms / 1000 + 0.001
        assert sm.is_expired() is True, f"{state} did not expire"
        fake_now[0] = 0.0


def test_speaking_excluded_from_is_expired() -> None:
    """`speaking`'s timeout is "no new audio chunk for 5s," not "5s in state" — approximated
    outside the pure state machine (docs/decisions/0008). `is_expired()` must never fire for it
    on its own, or the watchdog would double-count against `last_chunk_sent_monotonic`."""
    sm = StateMachine(state=S.speaking, clock=lambda: 999_999.0)
    assert sm.is_expired() is False


def test_elapsed_in_state_ms_resets_on_transition() -> None:
    fake_now = [0.0]
    sm = StateMachine(state=S.idle, clock=lambda: fake_now[0])
    fake_now[0] = 10.0
    assert sm.elapsed_in_state_ms() == pytest.approx(10_000.0)
    sm.transition(S.listening)
    assert sm.elapsed_in_state_ms() == pytest.approx(0.0)
