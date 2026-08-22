"""docs/phase-2-BUILD.md TASK 2.5a acceptance criterion: "Deterministic metrics computed
before any model call, and match hand-computed fixture values exactly." """

from __future__ import annotations

from services.coach.app.deterministic.metrics import (
    DeliveryTargets,
    compute_delivery_score,
    compute_question_coverage,
    score_answer_length,
    score_filler,
    score_pace,
    score_speech_ratio,
)

TARGETS = DeliveryTargets()


class TestBandedScores:
    def test_pace_in_band_scores_5(self) -> None:
        assert score_pace(140.0, TARGETS) == 5.0

    def test_pace_far_below_band_scores_low(self) -> None:
        # band is (110, 170); 30 wpm is 80 below the low edge, span=60 -> penalty capped at 4
        assert score_pace(30.0, TARGETS) == 1.0

    def test_pace_just_below_band_scores_between_1_and_5(self) -> None:
        # 100 is 10 below low edge (110), span=60 -> penalty = 10/60*4 = 0.666..
        assert score_pace(100.0, TARGETS) == 4.33

    def test_answer_length_in_band_scores_5(self) -> None:
        assert score_answer_length(100, TARGETS) == 5.0

    def test_answer_length_zero_words_is_penalized_but_not_floored(self) -> None:
        # band (40, 220), span=180; 0 words is 40 below the low edge -> penalty = 40/180*4 =
        # 0.888..; score = 5 - 0.89 = 4.11. The band is wide enough that even total silence
        # can't reach the floor on this dimension alone — word_count=0 can be at most 40 below
        # the low edge, never lower, so the maximum possible penalty here is capped structurally
        # by the band width, not by clamping logic.
        assert score_answer_length(0, TARGETS) == 4.11


class TestThresholdScores:
    def test_filler_at_threshold_scores_5(self) -> None:
        assert score_filler(0.06, TARGETS) == 5.0

    def test_filler_zero_scores_5(self) -> None:
        assert score_filler(0.0, TARGETS) == 5.0

    def test_filler_way_over_threshold_scores_1(self) -> None:
        assert score_filler(0.30, TARGETS) == 1.0

    def test_speech_ratio_at_minimum_scores_5(self) -> None:
        assert score_speech_ratio(0.5, TARGETS) == 5.0

    def test_speech_ratio_zero_scores_1(self) -> None:
        assert score_speech_ratio(0.0, TARGETS) == 1.0


class TestComputeDeliveryScore:
    def test_all_dimensions_in_band_scores_5(self) -> None:
        metrics = {
            "wpm": 140.0,
            "filler_rate": 0.0,
            "word_count": 100,
            "speech_ratio": 0.9,
        }
        result = compute_delivery_score(metrics, TARGETS)
        assert result.score == 5.0
        assert result.sub_scores == {
            "pace": 5.0,
            "filler": 5.0,
            "answer_length": 5.0,
            "speech_ratio": 5.0,
        }

    def test_hand_computed_mixed_fixture(self) -> None:
        # wpm=30 -> 1.0 (far below band, penalty capped at 4); filler=0.06 -> 5.0 (at
        # threshold); word_count=0 -> 4.11 (see test_answer_length_zero_words_is_penalized_but_
        # not_floored); speech_ratio=0.5 -> 5.0 (at minimum).
        # Average = (1 + 5 + 4.11 + 5) / 4 = 3.7775 -> rounds to 3.78
        metrics = {"wpm": 30.0, "filler_rate": 0.06, "word_count": 0, "speech_ratio": 0.5}
        result = compute_delivery_score(metrics, TARGETS)
        assert result.sub_scores == {
            "pace": 1.0,
            "filler": 5.0,
            "answer_length": 4.11,
            "speech_ratio": 5.0,
        }
        assert result.score == 3.78

    def test_never_calls_a_model_pure_arithmetic_only(self) -> None:
        """No network/model dependency exists to stub out — this test documents the
        requirement by construction: the function signature takes only a plain dict and
        returns instantly with no await."""
        import inspect

        assert not inspect.iscoroutinefunction(compute_delivery_score)


class TestQuestionCoverage:
    def test_every_question_answered_is_full_coverage(self) -> None:
        turns = [
            {"speaker": "persona", "text": "What did you build?", "index": 0, "truncated": False},
            {"speaker": "user", "text": "A pipeline.", "index": 0, "truncated": False},
            {"speaker": "persona", "text": "Why Kafka?", "index": 1, "truncated": False},
            {"speaker": "user", "text": "Throughput.", "index": 1, "truncated": False},
        ]
        assert compute_question_coverage(turns) == 1.0

    def test_unanswered_question_reduces_coverage(self) -> None:
        turns = [
            {"speaker": "persona", "text": "What did you build?", "index": 0, "truncated": False},
            {"speaker": "user", "text": "A pipeline.", "index": 0, "truncated": False},
            {"speaker": "persona", "text": "Why Kafka?", "index": 1, "truncated": False},
            # no answer follows — session ended mid-question
        ]
        assert compute_question_coverage(turns) == 0.5

    def test_truncated_answer_does_not_count_as_covered(self) -> None:
        turns = [
            {"speaker": "persona", "text": "What did you build?", "index": 0, "truncated": False},
            {"speaker": "user", "text": "A pipe", "index": 0, "truncated": True},
        ]
        assert compute_question_coverage(turns) == 0.0

    def test_no_questions_asked_is_vacuously_full_coverage(self) -> None:
        assert compute_question_coverage([]) == 1.0

    def test_non_question_persona_statements_are_not_counted(self) -> None:
        turns = [
            {"speaker": "persona", "text": "Interesting.", "index": 0, "truncated": False},
            {"speaker": "user", "text": "Thanks.", "index": 0, "truncated": False},
        ]
        assert compute_question_coverage(turns) == 1.0  # 0 questions asked
