"""docs/phase-2-BUILD.md TASK 2.5e/2.5f. Acceptance criteria covered here: "Confidence gating
renders not enough signal on a 3-word turn" and "Aggregation policy read from the rubric, not
hardcoded" (the latter proven by `aggregate_criterion` taking `min_turns_with_signal` as a
parameter, never a module constant it could fall back to silently)."""

from __future__ import annotations

import uuid

from services.coach.app.report.aggregation import (
    aggregate_criterion,
    gate_score,
    percentile_vs_self,
    pick_highlight_and_lowlight,
)

CONFIDENCE_THRESHOLD = 0.6


class TestGateScore:
    def test_above_threshold_passes_through(self) -> None:
        score, is_gated = gate_score(4.0, 0.8, CONFIDENCE_THRESHOLD)
        assert score == 4.0
        assert is_gated is False

    def test_below_threshold_gates_to_not_enough_signal(self) -> None:
        """The 3-word-turn acceptance criterion: a scorer might still return *a* score for
        "I don't know," but low confidence must gate it to None regardless of what the number
        was — CLAUDE.md §1.6: "not enough signal, never a number.\""""
        score, is_gated = gate_score(3.0, 0.2, CONFIDENCE_THRESHOLD)
        assert score is None
        assert is_gated is True

    def test_none_score_is_always_gated_even_at_high_confidence(self) -> None:
        score, is_gated = gate_score(None, 0.99, CONFIDENCE_THRESHOLD)
        assert score is None
        assert is_gated is True

    def test_exactly_at_threshold_passes(self) -> None:
        score, is_gated = gate_score(3.0, CONFIDENCE_THRESHOLD, CONFIDENCE_THRESHOLD)
        assert score == 3.0
        assert is_gated is False


def _row(score: float | None, confidence: float, turn_id: str | None = None) -> dict[str, object]:
    return {"score": score, "confidence": confidence, "turn_id": turn_id or str(uuid.uuid4())}


class TestAggregateCriterion:
    def test_weighted_by_confidence(self) -> None:
        # both rows above CONFIDENCE_THRESHOLD (0.6) so both count as "signal"
        rows = [_row(5.0, 1.0), _row(3.0, 0.7)]
        result = aggregate_criterion(
            "structure", rows, confidence_threshold=CONFIDENCE_THRESHOLD, min_turns_with_signal=2
        )
        # (5*1.0 + 3*0.7) / (1.0+0.7) = 7.1/1.7 = 4.1765 -> 4.18
        assert result.aggregate_score == 4.18
        assert result.confidence == round(min(1.0, 1.7 / 2), 4)

    def test_below_min_turns_with_signal_is_not_enough_signal(self) -> None:
        """"Criteria with insufficient turn-level signal aggregate to not enough signal rather
        than to a partial average over two turns" — here, over *one*."""
        rows = [_row(5.0, 1.0)]
        result = aggregate_criterion(
            "structure", rows, confidence_threshold=CONFIDENCE_THRESHOLD, min_turns_with_signal=2
        )
        assert result.aggregate_score is None
        assert result.confidence == 0.0

    def test_min_turns_with_signal_is_a_parameter_not_hardcoded(self) -> None:
        """Proves the rubric's aggregation_policy genuinely controls behavior: the exact same
        two-row input aggregates differently purely because the policy value passed in
        differs — nothing in this function assumes a fixed threshold."""
        rows = [_row(4.0, 0.9), _row(4.0, 0.9)]
        strict = aggregate_criterion(
            "structure", rows, confidence_threshold=CONFIDENCE_THRESHOLD, min_turns_with_signal=3
        )
        lenient = aggregate_criterion(
            "structure", rows, confidence_threshold=CONFIDENCE_THRESHOLD, min_turns_with_signal=2
        )
        assert strict.aggregate_score is None
        assert lenient.aggregate_score == 4.0

    def test_gated_turn_rows_are_excluded_from_signal(self) -> None:
        """A row with score=None (already gated at the turn level) contributes nothing, even
        if its confidence happens to be high — it never had a number to weight in."""
        rows = [_row(5.0, 0.9), _row(None, 0.9)]
        result = aggregate_criterion(
            "structure", rows, confidence_threshold=CONFIDENCE_THRESHOLD, min_turns_with_signal=2
        )
        assert result.aggregate_score is None  # only 1 real signal row, needs 2

    def test_low_confidence_rows_excluded_even_with_a_score(self) -> None:
        rows = [_row(5.0, 0.9), _row(4.0, 0.1)]
        result = aggregate_criterion(
            "structure", rows, confidence_threshold=CONFIDENCE_THRESHOLD, min_turns_with_signal=2
        )
        assert result.aggregate_score is None

    def test_evidence_turn_ids_track_the_signal_rows(self) -> None:
        rows = [_row(5.0, 0.9, "turn-a"), _row(4.0, 0.9, "turn-b")]
        result = aggregate_criterion(
            "structure", rows, confidence_threshold=CONFIDENCE_THRESHOLD, min_turns_with_signal=2
        )
        assert set(result.evidence_turn_ids) == {"turn-a", "turn-b"}


class TestPercentileVsSelf:
    def test_no_history_returns_none_not_a_fabricated_number(self) -> None:
        assert percentile_vs_self(4.0, []) is None

    def test_percentile_computed_against_past_scores(self) -> None:
        # 4.0 is >= 2 of the 4 past scores (3.0, 3.5) -> 2/4 = 0.5
        assert percentile_vs_self(4.0, [3.0, 3.5, 4.5, 5.0]) == 0.5

    def test_best_ever_score_is_100th_percentile(self) -> None:
        assert percentile_vs_self(5.0, [3.0, 4.0, 4.5]) == 1.0

    def test_worst_ever_score_is_low_percentile(self) -> None:
        assert percentile_vs_self(1.0, [3.0, 4.0, 4.5]) == 0.0


class TestPickHighlightAndLowlight:
    def test_picks_highest_and_lowest_average_turn(self) -> None:
        rows = [
            _row(5.0, 0.9, "best"),
            _row(5.0, 0.9, "best"),
            _row(1.0, 0.9, "worst"),
            _row(1.0, 0.9, "worst"),
        ]
        highlight, lowlight = pick_highlight_and_lowlight(
            rows, confidence_threshold=CONFIDENCE_THRESHOLD
        )
        assert highlight == "best"
        assert lowlight == "worst"

    def test_only_one_qualifying_turn_has_no_lowlight_contrast(self) -> None:
        rows = [_row(4.0, 0.9, "only-turn")]
        highlight, lowlight = pick_highlight_and_lowlight(
            rows, confidence_threshold=CONFIDENCE_THRESHOLD
        )
        assert highlight == "only-turn"
        assert lowlight is None

    def test_no_qualifying_rows_returns_none_none(self) -> None:
        rows = [_row(4.0, 0.1, "low-confidence-only")]
        highlight, lowlight = pick_highlight_and_lowlight(
            rows, confidence_threshold=CONFIDENCE_THRESHOLD
        )
        assert (highlight, lowlight) == (None, None)
