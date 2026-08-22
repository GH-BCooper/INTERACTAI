"""docs/phase-2-BUILD.md TASK 2.3c: difficulty as parameters, not three prompts."""

from __future__ import annotations

from services.realtime.app.persona.difficulty import (
    DifficultyParams,
    parse_difficulty_params,
    render_difficulty_instructions,
)

GENTLE_RAW = {
    "followups_on_vague": 0,
    "hint_after_pause_ms": 4000,
    "interrupt_over_words": None,
    "ack_length": "long",
    "silence_after_answer_ms": 0,
}
STANDARD_RAW = {
    "followups_on_vague": 1,
    "hint_after_pause_ms": None,
    "interrupt_over_words": None,
    "ack_length": "short",
    "silence_after_answer_ms": 0,
}
HARD_RAW = {
    "followups_on_vague": 3,
    "hint_after_pause_ms": None,
    "interrupt_over_words": 120,
    "ack_length": "minimal",
    "silence_after_answer_ms": 1500,
    "challenge_claims": True,
    "time_pressure": True,
}


class TestParseDifficultyParams:
    def test_gentle_tier_parses_exactly(self) -> None:
        params = parse_difficulty_params(GENTLE_RAW)
        assert params == DifficultyParams(
            followups_on_vague=0,
            hint_after_pause_ms=4000,
            interrupt_over_words=None,
            ack_length="long",
            silence_after_answer_ms=0,
            challenge_claims=False,
            time_pressure=False,
        )

    def test_hard_tier_parses_exactly(self) -> None:
        params = parse_difficulty_params(HARD_RAW)
        assert params == DifficultyParams(
            followups_on_vague=3,
            hint_after_pause_ms=None,
            interrupt_over_words=120,
            ack_length="minimal",
            silence_after_answer_ms=1500,
            challenge_claims=True,
            time_pressure=True,
        )

    def test_missing_challenge_claims_and_time_pressure_default_false(self) -> None:
        params = parse_difficulty_params(STANDARD_RAW)
        assert params.challenge_claims is False
        assert params.time_pressure is False


class TestRenderDifficultyInstructions:
    def test_gentle_and_hard_produce_measurably_different_text(self) -> None:
        """Task 2.3's acceptance criterion: "Gentle vs hard differ measurably" — the most basic
        possible proof is that the rendered instructions are not the same string, and that
        hard-specific behaviors appear only in hard's rendering."""
        gentle_text = render_difficulty_instructions(parse_difficulty_params(GENTLE_RAW))
        hard_text = render_difficulty_instructions(parse_difficulty_params(HARD_RAW))
        assert gentle_text != hard_text
        assert "challenge" not in gentle_text.lower()
        assert "challenge" in hard_text.lower()
        assert "interrupt" not in gentle_text.lower()
        assert "interrupt" in hard_text.lower()

    def test_zero_followups_produces_accept_and_move_on_instruction(self) -> None:
        text = render_difficulty_instructions(parse_difficulty_params(GENTLE_RAW))
        assert "accept it and move on" in text.lower()

    def test_nonzero_followups_states_the_cap(self) -> None:
        text = render_difficulty_instructions(parse_difficulty_params(HARD_RAW))
        assert "3 follow-up" in text

    def test_no_interrupt_instruction_when_interrupt_over_words_is_none(self) -> None:
        text = render_difficulty_instructions(parse_difficulty_params(STANDARD_RAW))
        assert "interrupt" not in text.lower()

    def test_ack_length_instruction_present_for_every_tier(self) -> None:
        for raw in (GENTLE_RAW, STANDARD_RAW, HARD_RAW):
            text = render_difficulty_instructions(parse_difficulty_params(raw))
            assert "acknowledge" in text.lower()

    def test_long_silence_after_answer_produces_deliberate_pause_instruction(self) -> None:
        text = render_difficulty_instructions(parse_difficulty_params(HARD_RAW))
        assert "deliberate pause" in text.lower()

    def test_zero_silence_after_answer_has_no_pause_instruction(self) -> None:
        text = render_difficulty_instructions(parse_difficulty_params(GENTLE_RAW))
        assert "deliberate pause" not in text.lower()
