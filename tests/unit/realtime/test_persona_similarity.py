"""docs/phase-2-BUILD.md TASK 2.3's acceptance criterion: "No repeated questions across a
20-turn session." See services/realtime/app/persona/similarity.py's module docstring for why
this is Jaccard similarity, not real embeddings."""

from __future__ import annotations

from services.realtime.app.persona.similarity import is_repeated_question, jaccard_similarity


class TestJaccardSimilarity:
    def test_identical_questions_are_fully_similar(self) -> None:
        assert jaccard_similarity("What did you build?", "What did you build?") == 1.0

    def test_near_duplicate_question_is_highly_similar(self) -> None:
        sim = jaccard_similarity(
            "What was the hardest part of that migration?",
            "What was the hardest part of the migration?",
        )
        assert sim >= 0.9

    def test_unrelated_questions_are_dissimilar(self) -> None:
        sim = jaccard_similarity(
            "What did you build?", "How do you handle conflict with a teammate?"
        )
        assert sim < 0.3

    def test_both_empty_after_stopword_removal_is_fully_similar(self) -> None:
        assert jaccard_similarity("the a an", "an the a") == 1.0

    def test_one_empty_after_stopword_removal_is_not_similar(self) -> None:
        assert jaccard_similarity("the a an", "Kafka pipeline throughput") == 0.0


class TestIsRepeatedQuestion:
    def test_flags_a_near_duplicate_of_a_recent_question(self) -> None:
        recent = ["What did you build?", "Why did you choose Kafka?"]
        assert is_repeated_question("What did you build?", recent) is True

    def test_does_not_flag_a_genuinely_new_question(self) -> None:
        recent = ["What did you build?"]
        assert is_repeated_question("How did the team react to that change?", recent) is False

    def test_empty_history_never_flags_anything(self) -> None:
        assert is_repeated_question("What did you build?", []) is False
