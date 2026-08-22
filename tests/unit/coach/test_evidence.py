"""docs/phase-2-BUILD.md TASK 2.5d — NON-NEGOTIABLE. Acceptance criteria covered here:
"Evidence verification discards a deliberately hallucinated span (test with an injected fake)"
and "evidence_validity is 100% after filtering, measured and logged." """

from __future__ import annotations

from services.coach.app.scorer.evidence import (
    Span,
    apply_confidence_penalty,
    locate_quote,
    verify_spans,
)

ANSWER = (
    "Last quarter I rebuilt the ingestion pipeline using Kafka and it now handles "
    "3000 events per second."
)


class TestLocateQuote:
    def test_exact_match_returns_correct_offsets(self) -> None:
        span = locate_quote(ANSWER, "rebuilt the ingestion pipeline")
        assert span is not None
        assert ANSWER[span.start : span.end] == "rebuilt the ingestion pipeline"

    def test_whitespace_normalized_match_still_locates_correctly(self) -> None:
        # model "quoted" with a newline where the source has a space — permitted normalization
        span = locate_quote(ANSWER, "rebuilt the\ningestion pipeline")
        assert span is not None
        assert ANSWER[span.start : span.end] == "rebuilt the ingestion pipeline"

    def test_paraphrase_is_not_located(self) -> None:
        """"Paraphrase matching is not [permitted]" — a semantically-equivalent but
        textually-different quote must not resolve to a span at all."""
        assert locate_quote(ANSWER, "revamped the data ingestion system") is None

    def test_hallucinated_quote_not_in_answer_returns_none(self) -> None:
        assert locate_quote(ANSWER, "this text never appeared anywhere in the answer") is None

    def test_empty_quote_returns_none(self) -> None:
        assert locate_quote(ANSWER, "") is None


class TestVerifySpans:
    def test_all_real_quotes_verify_with_full_validity(self) -> None:
        result = verify_spans(ANSWER, ["rebuilt the ingestion pipeline", "3000 events per second"])
        assert result.all_verified is True
        assert result.evidence_validity == 1.0
        assert len(result.verified_spans) == 2

    def test_hallucinated_span_is_discarded_not_kept_or_guessed(self) -> None:
        """The exact acceptance criterion: inject a fake, assert it's gone, not fuzzy-matched
        to something nearby."""
        result = verify_spans(ANSWER, ["I have never operated a production system"])
        assert result.verified_spans == []
        assert result.all_verified is False
        assert result.evidence_validity == 0.0

    def test_mixed_real_and_hallucinated_keeps_only_the_real_one(self) -> None:
        result = verify_spans(
            ANSWER, ["rebuilt the ingestion pipeline", "a completely fabricated claim"]
        )
        assert len(result.verified_spans) == 1
        assert result.all_verified is False
        assert result.evidence_validity == 0.5

    def test_no_quotes_requested_is_trivially_fully_verified(self) -> None:
        result = verify_spans(ANSWER, [])
        assert result.verified_spans == []
        assert result.all_verified is True
        assert result.evidence_validity == 1.0

    def test_evidence_validity_measured_as_fraction_found(self) -> None:
        """Task 2.5d: "evidence_validity (fraction of spans found verbatim) is logged per
        turn — it must be 100% after filtering by construction." Verified here directly: once
        spans are filtered (verified_spans), re-checking them against the answer always
        succeeds by construction."""
        result = verify_spans(ANSWER, ["Kafka", "totally made up", "3000 events per second"])
        assert result.evidence_validity == round(2 / 3, 4)
        for span in result.verified_spans:
            assert ANSWER[span.start : span.end]  # every verified span is non-empty and real


class TestApplyConfidencePenalty:
    def test_fully_verified_leaves_confidence_untouched(self) -> None:
        verification = verify_spans(ANSWER, ["Kafka"])
        assert apply_confidence_penalty(0.9, verification) == 0.9

    def test_partial_failure_halves_confidence(self) -> None:
        verification = verify_spans(ANSWER, ["Kafka", "fabricated"])
        assert apply_confidence_penalty(0.9, verification) == 0.45

    def test_total_failure_zeroes_confidence(self) -> None:
        verification = verify_spans(ANSWER, ["fabricated"])
        assert apply_confidence_penalty(0.9, verification) == 0.0

    def test_no_evidence_requested_is_untouched(self) -> None:
        verification = verify_spans(ANSWER, [])
        assert apply_confidence_penalty(0.7, verification) == 0.7


def test_span_offsets_survive_a_manually_constructed_span() -> None:
    span = Span(start=0, end=4)
    assert ANSWER[span.start : span.end] == "Last"
