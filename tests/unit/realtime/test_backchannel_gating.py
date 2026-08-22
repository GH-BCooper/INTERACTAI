"""docs/phase-2-BUILD.md TASK 2.4 point 3 (PA-10): "Pre-synthesised acknowledgement plays the
instant endpointing fires. Constraints: at most 1 in 3 turns, never twice consecutively, never
at hard difficulty, never before a wrap-up. Config-driven so it can be cut." `should_play_
backchannel` in turn.py is the pure gate that enforces all four; this file covers each in
isolation plus the config kill-switch. The actual playback wiring in `process_turn` (deciding,
sending the cached clip, and keeping `e2e`/`tts_first_chunk` measuring the real reply rather
than the backchannel) is exercised live via the CLI harness, not re-mocked here — see
docs/PROGRESS.md's Phase 2 latency section.
"""

from __future__ import annotations

import uuid

import pytest

from services.realtime.app.persona.difficulty import parse_difficulty_params
from services.realtime.app.persona.prompt import PersonaContext
from services.realtime.app.session import SessionRuntime
from services.realtime.app.turn import should_play_backchannel


class _FakeSocket:
    async def send_text(self, data: str) -> None:  # pragma: no cover
        pass

    async def send_bytes(self, data: bytes) -> None:  # pragma: no cover
        pass


def _runtime(**overrides: object) -> SessionRuntime:
    defaults: dict[str, object] = {
        "session_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "websocket": _FakeSocket(),
    }
    defaults.update(overrides)
    return SessionRuntime(**defaults)  # type: ignore[arg-type]


def _persona_context(
    *, challenge_claims: bool = False, time_pressure: bool = False
) -> PersonaContext:
    difficulty = parse_difficulty_params(
        {
            "followups_on_vague": 1,
            "hint_after_pause_ms": None,
            "interrupt_over_words": None,
            "ack_length": "short",
            "silence_after_answer_ms": 0,
            "challenge_claims": challenge_claims,
            "time_pressure": time_pressure,
        }
    )
    return PersonaContext(
        persona_name="Elena Kovac",
        persona_archetype="interviewer",
        persona_temperament="blunt",
        persona_brief="A staff engineer who interviews often.",
        scenario_brief="A backend system design screen.",
        opening_strategy="Ask about the hardest thing they shipped.",
        target_minutes=20,
        difficulty=difficulty,
    )


class TestShouldPlayBackchannel:
    def test_first_turn_is_never_eligible(self) -> None:
        # (0 used + 1) / (0 + 1) = 1.0 > 1/3 — a cold start can't justify a backchannel yet;
        # the rate cap naturally defers the first one until there's turn history to dilute it.
        rt = _runtime()
        assert (
            should_play_backchannel(runtime=rt, persona_context=_persona_context(), turn_index=0)
            is False
        )

    def test_third_turn_is_first_eligible_from_a_cold_start(self) -> None:
        # (0 used + 1) / (2 + 1) = 1/3 exactly, at the cap -> eligible.
        rt = _runtime()
        assert (
            should_play_backchannel(runtime=rt, persona_context=_persona_context(), turn_index=2)
            is True
        )

    def test_no_persona_context_never_plays(self) -> None:
        rt = _runtime()
        assert should_play_backchannel(runtime=rt, persona_context=None, turn_index=0) is False

    def test_hard_difficulty_challenge_claims_never_plays(self) -> None:
        rt = _runtime()
        ctx = _persona_context(challenge_claims=True)
        assert should_play_backchannel(runtime=rt, persona_context=ctx, turn_index=0) is False

    def test_hard_difficulty_time_pressure_never_plays(self) -> None:
        rt = _runtime()
        ctx = _persona_context(time_pressure=True)
        assert should_play_backchannel(runtime=rt, persona_context=ctx, turn_index=0) is False

    def test_never_twice_consecutively(self) -> None:
        rt = _runtime(last_turn_was_backchannel=True, backchannel_turns_used=1)
        assert (
            should_play_backchannel(runtime=rt, persona_context=_persona_context(), turn_index=1)
            is False
        )

    def test_never_before_a_wrap_up(self) -> None:
        exhausted_plan = {"topics": [{"id": "t0", "topic": "x", "status": "done"}]}
        rt = _runtime(question_plan=exhausted_plan)
        assert (
            should_play_backchannel(runtime=rt, persona_context=_persona_context(), turn_index=3)
            is False
        )

    def test_rate_cap_blocks_once_at_the_ceiling(self) -> None:
        # 1 used out of 3 so far (already at the 1/3 cap) -> a 2nd on turn_index=3 is 2/4 = 0.5
        rt = _runtime(backchannel_turns_used=1, last_turn_was_backchannel=False)
        assert (
            should_play_backchannel(runtime=rt, persona_context=_persona_context(), turn_index=3)
            is False
        )

    def test_rate_cap_allows_when_still_under_the_ceiling(self) -> None:
        # 1 used out of 5 so far -> a 2nd on turn_index=5 is 2/6 = 1/3 exactly, at the cap
        rt = _runtime(backchannel_turns_used=1, last_turn_was_backchannel=False)
        assert (
            should_play_backchannel(runtime=rt, persona_context=_persona_context(), turn_index=5)
            is True
        )

    def test_disabled_via_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from services.realtime.app.core import config as config_module

        settings = config_module.get_settings()
        monkeypatch.setattr(settings, "backchannel_enabled", False)
        rt = _runtime()
        assert (
            should_play_backchannel(runtime=rt, persona_context=_persona_context(), turn_index=0)
            is False
        )
