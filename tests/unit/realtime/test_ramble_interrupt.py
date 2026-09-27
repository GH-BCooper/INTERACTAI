"""Task 2.3c's `interrupt_over_words`, at the wiring level rather than the pure-function level
(`test_endpointing.py::TestRambleWordCap` covers the cascade helper itself).

Why this file exists: Level 2 persona adherence (Task 6.3b) measured the interruption rate at
**0.0 on every tier, hard included**, against a deliberate >120-word ramble. The cap was rendered
into the brief layer as a sentence and nothing in `services/realtime` enforced it, so the top of
the difficulty ladder was decorative — which the Phase 6 spec calls a defect in as many words.
The other two hard-tier parameters were already enforced in code; this one is now too.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest

from services.realtime.app.frame_pipeline import _ramble_word_cap, handle_interrupt_window
from services.realtime.app.persona.difficulty import parse_difficulty_params
from services.realtime.app.persona.prompt import PersonaContext
from services.realtime.app.session import SessionRuntime

GENTLE = {"followups_on_vague": 0, "hint_after_pause_ms": 4000, "ack_length": "long"}
STANDARD = {"followups_on_vague": 1, "ack_length": "short"}
HARD = {
    "followups_on_vague": 3,
    "interrupt_over_words": 120,
    "ack_length": "minimal",
    "silence_after_answer_ms": 1500,
    "challenge_claims": True,
    "time_pressure": True,
}


class _FakeSocket:
    async def send_text(self, data: str) -> None:  # pragma: no cover
        pass

    async def send_bytes(self, data: bytes) -> None:  # pragma: no cover
        pass


class _AlwaysSpeechVad:
    """Stands in for the Silero wrapper. Every window is speech, which is the situation a ramble
    interrupt creates by definition: we cut the candidate off mid-sentence, so they are still
    talking while the persona starts to speak."""

    def observe(self, window: np.ndarray) -> bool:
        return True


def _runtime(difficulty: dict[str, object] | None) -> SessionRuntime:
    rt = SessionRuntime(session_id=uuid.uuid4(), user_id=uuid.uuid4(), websocket=_FakeSocket())
    if difficulty is not None:
        rt.persona_context = PersonaContext(
            persona_name="Dana",
            persona_archetype="hiring manager",
            persona_temperament="brisk",
            persona_brief="brief",
            scenario_brief="scenario",
            opening_strategy="open with the rollout",
            target_minutes=10,
            difficulty=parse_difficulty_params(difficulty),
        )
    return rt


class TestTheCapComesFromTheTier:
    def test_hard_reports_its_cap(self) -> None:
        assert _ramble_word_cap(_runtime(HARD)) == 120

    def test_gentle_and_standard_report_no_cap(self) -> None:
        assert _ramble_word_cap(_runtime(GENTLE)) is None
        assert _ramble_word_cap(_runtime(STANDARD)) is None

    def test_a_session_with_no_compiled_brief_reports_no_cap(self) -> None:
        """The CLI harness and `persona_stub` sessions have no `PersonaContext` at all. They must
        read as "never interrupt" rather than raising on the frame path."""
        assert _ramble_word_cap(_runtime(None)) is None


class TestStopOnSpeechIsSuppressedDuringTheInterruption:
    """Found while wiring this up, and the reason the flag exists at all: the persona interrupts,
    the candidate is still finishing their sentence, and ordinary stop-on-speech (Task 1.5d) would
    read that trailing speech as a barge-in and cancel the interruption the instant it began — so
    the one escalation the hard tier has would still never be heard, and the fix would measure as
    fixed while being useless."""

    @pytest.mark.asyncio
    async def test_speech_during_a_ramble_interruption_never_triggers_a_barge_in(self) -> None:
        rt = _runtime(HARD)
        rt.vad = _AlwaysSpeechVad()  # type: ignore[assignment]
        rt.ramble_interrupt_active = True
        window = np.zeros(320, dtype=np.float32)

        for _ in range(100):  # far past INTERRUPT_GUARD_MS worth of sustained speech
            assert await handle_interrupt_window(runtime=rt, window=window) is False

        assert rt.interrupt_guard_ms == 0.0

    @pytest.mark.asyncio
    async def test_an_ordinary_barge_in_still_works_once_the_flag_clears(self) -> None:
        """The suppression must be scoped to the interruption reply, not disable barge-in for the
        rest of the session."""
        rt = _runtime(HARD)
        rt.vad = _AlwaysSpeechVad()  # type: ignore[assignment]
        rt.ramble_interrupt_active = False
        window = np.zeros(320, dtype=np.float32)

        fired = False
        for _ in range(100):
            if await handle_interrupt_window(runtime=rt, window=window):
                fired = True
                break
        assert fired
