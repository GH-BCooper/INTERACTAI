from __future__ import annotations

from services.realtime.app.persona.vagueness import is_answer_vague


class TestIsAnswerVague:
    def test_short_answer_is_vague(self) -> None:
        assert is_answer_vague(word_count=5, filler_rate=0.0) is True

    def test_substantive_low_filler_answer_is_not_vague(self) -> None:
        assert is_answer_vague(word_count=50, filler_rate=0.02) is False

    def test_high_filler_rate_is_vague_even_if_long(self) -> None:
        assert is_answer_vague(word_count=100, filler_rate=0.2) is True

    def test_exactly_at_the_word_boundary_is_not_vague(self) -> None:
        assert is_answer_vague(word_count=15, filler_rate=0.0) is False
