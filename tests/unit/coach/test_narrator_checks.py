"""docs/phase-2-BUILD.md TASK 2.5g's two post-checks. Acceptance criterion covered directly:
"Narrative never contradicts a score (test with a forced contradiction)."""

from __future__ import annotations

from services.coach.app.narrator.checks import (
    find_contradicting_numbers,
    find_generic_encouragement,
)


class TestFindGenericEncouragement:
    def test_blocklisted_phrase_is_flagged(self) -> None:
        hits = find_generic_encouragement("Great job on that answer, really solid work.")
        assert "great job" in hits

    def test_case_insensitive(self) -> None:
        assert find_generic_encouragement("WELL DONE overall.") == ["well done"]

    def test_multiple_hits_all_reported(self) -> None:
        hits = find_generic_encouragement("Nice work! Keep it up and well done.")
        assert set(hits) == {"nice work", "keep it up", "well done"}

    def test_specific_feedback_is_not_flagged(self) -> None:
        text = "Your answer named Kafka and gave a concrete throughput number, which is specific."
        assert find_generic_encouragement(text) == []

    def test_substring_that_is_not_the_full_phrase_is_not_flagged(self) -> None:
        # "job" alone (as in "the job market") should not trigger "great job"/"good job"
        assert find_generic_encouragement("The job market for backend roles is competitive.") == []


class TestFindContradictingNumbers:
    def test_matching_score_is_not_a_contradiction(self) -> None:
        assert find_contradicting_numbers("Your structure scored 4/5 this session.", {4.0}) == []

    def test_forced_contradiction_is_detected(self) -> None:
        """The exact acceptance criterion: force a contradiction and assert it's caught."""
        contradictions = find_contradicting_numbers(
            "Your structure was excellent, a clean 5/5.", {2.0}
        )
        assert contradictions == ["5"]

    def test_out_of_5_phrasing_also_detected(self) -> None:
        contradictions = find_contradicting_numbers("You scored 3 out of 5 on concision.", {4.0})
        assert contradictions == ["3"]

    def test_no_numeric_claims_is_never_a_contradiction(self) -> None:
        text = "Your structure was clear and easy to follow."
        assert find_contradicting_numbers(text, {2.0}) == []

    def test_multiple_scores_all_valid_no_contradiction(self) -> None:
        text = "Structure scored 4/5 and concision scored 3/5."
        assert find_contradicting_numbers(text, {4.0, 3.0}) == []

    def test_empty_valid_scores_flags_any_number_mentioned(self) -> None:
        """A session with nothing but gated ("not enough signal") criteria has no valid scores
        at all — any X/5 claim in that narrative is necessarily fabricated."""
        assert find_contradicting_numbers("You got a 5/5 overall.", set()) == ["5"]
