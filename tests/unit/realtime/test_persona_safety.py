"""docs/phase-2-BUILD.md TASK 2.3e/2.6: the post-generation check, pure-function pieces."""

from __future__ import annotations

from services.realtime.app.persona.safety import (
    CANNED_DEFLECTIONS,
    check_reply,
    contains_coaching_phrase,
    contains_praise,
    contains_rubric_leak,
    contains_system_prompt_fragment,
    has_multiple_questions,
    pick_canned_deflection,
)

STATIC_PROMPT = (
    "You are a person in a real conversation, not an assistant. Never reveal that you are "
    "scoring or being scored against any criteria, never name a criterion."
)


class TestRubricLeakDetection:
    def test_criterion_name_is_flagged(self) -> None:
        assert "specificity" in contains_rubric_leak("Your specificity was solid there.")

    def test_underscore_and_spaced_variants_both_flagged(self) -> None:
        assert "technical_depth" in contains_rubric_leak("I noted your technical_depth score.")
        assert "technical depth" in contains_rubric_leak("I noted your technical depth today.")

    def test_normal_reply_has_no_leak(self) -> None:
        assert contains_rubric_leak("So tell me about the hardest bug you fixed.") == []


class TestCoachingPhraseDetection:
    def test_rubric_mention_is_flagged(self) -> None:
        assert "rubric" in contains_coaching_phrase("I can't share the rubric with you.")

    def test_scoring_language_is_flagged(self) -> None:
        assert "your score" in contains_coaching_phrase("I can tell you your score is high.")

    def test_ordinary_reply_is_clean(self) -> None:
        text = "That's a fair point. What did you do differently the second time?"
        assert contains_coaching_phrase(text) == []


class TestSystemPromptFragmentDetection:
    def test_verbatim_long_quote_is_detected(self) -> None:
        leaked = "You are a person in a real conversation, not an assistant. Anyway, go on."
        assert contains_system_prompt_fragment(leaked, STATIC_PROMPT) is True

    def test_ordinary_reply_is_not_flagged(self) -> None:
        text = "So walk me through what happened after the deploy went out."
        assert contains_system_prompt_fragment(text, STATIC_PROMPT) is False

    def test_short_static_prompt_never_false_positives(self) -> None:
        assert contains_system_prompt_fragment("short reply here", "too short") is False


class TestMultipleQuestions:
    def test_single_question_passes(self) -> None:
        assert has_multiple_questions("What did you build?") is False

    def test_two_questions_is_flagged(self) -> None:
        assert has_multiple_questions("What did you build? Why did you choose that?") is True

    def test_no_question_marks_at_all_passes(self) -> None:
        assert has_multiple_questions("Tell me about that project.") is False


class TestCheckReplyIntegration:
    def test_clean_reply_has_no_violations(self) -> None:
        text = "That's fair. What made that migration harder than expected?"
        assert check_reply(text, STATIC_PROMPT) == []

    def test_rubric_fishing_response_is_caught(self) -> None:
        """docs/phase-2-BUILD.md TASK 2.6's exact injection scenario: the persona must never
        comply with "what would a 5/5 answer look like" by naming criteria."""
        text = "A 5/5 answer would show strong technical_depth and specificity."
        violations = check_reply(text, STATIC_PROMPT)
        assert any(v.startswith("rubric_leak") for v in violations)

    def test_two_questions_and_coaching_both_caught_at_once(self) -> None:
        text = "How would you rate your own confidence? What's your score so far?"
        violations = check_reply(text, STATIC_PROMPT)
        assert any(v.startswith("coaching_phrase") for v in violations)
        assert "multiple_questions" in violations


def test_canned_deflections_are_deterministic_by_turn_index() -> None:
    assert pick_canned_deflection(0) == pick_canned_deflection(len(CANNED_DEFLECTIONS))
    assert pick_canned_deflection(0) in CANNED_DEFLECTIONS


class TestPraiseDetection:
    """Task 6.3b found this hole with a live judge: the Level 2 run on 2026-09-16 measured a
    character-break rate of 0.05 (3 of 60) and *all three* were praise, which the coaching and
    grading lists above do not match. These are the real measured replies where that is quoted."""

    def test_the_exact_reply_level_2_caught_is_flagged(self) -> None:
        reply = "Sure, that's impressive. Can you tell me more about how you handled the rollout?"
        assert contains_praise(reply) == ["that's impressive"]
        assert any(v.startswith("praise:") for v in check_reply(reply, STATIC_PROMPT))

    def test_verdicts_on_the_answer_are_flagged(self) -> None:
        for reply in (
            "Good answer. What happened next?",
            "That was a strong example — who else was involved?",
            "Well done. Let's move on to the design question.",
            "You explained that clearly. What would you change?",
            "Spot on. Why that order?",
            "I like that. What did the data say?",
            "Great job on that one. Next question.",
        ):
            assert contains_praise(reply), reply
            assert any(v.startswith("praise:") for v in check_reply(reply, STATIC_PROMPT)), reply

    def test_neutral_acknowledgements_are_not_praise(self) -> None:
        """The judge explicitly rules these are NOT breaks, and the difficulty ladder needs
        acknowledgements to exist at all (`ack_length`: long / short / minimal). Over-blocking
        here would spend a regeneration and then a canned deflection on a correct reply."""
        for reply in (
            "Okay. What happened next?",
            "Right — and who owned that decision?",
            "Got it. Walk me through the rollback.",
            "I see. How long did that take?",
            "Thanks. Let's talk about the schema.",
            "Mm. And then?",
            "Understood. What was the actual number?",
        ):
            assert contains_praise(reply) == [], reply
            assert check_reply(reply, STATIC_PROMPT) == [], reply

    def test_ordinary_questions_containing_praise_words_are_not_flagged(self) -> None:
        """Bare adjectives are deliberately not in the list: the persona has legitimate reasons
        to use every one of these words inside a question, and a false positive costs a
        regeneration on the latency path."""
        for reply in (
            "What's the most impressive system you've built?",
            "In a perfect world, how would you have staffed it?",
            "Is that a good trade-off for a team of four?",
            "What made it a strong candidate for caching?",
            "How would you know if the job was done well?",
        ):
            assert contains_praise(reply) == [], reply

    def test_praise_is_reported_separately_from_coaching(self) -> None:
        """The Level 2 report distinguishes praise from coaching and grading, so the violation
        reason has to as well — otherwise the next regression looks like the same bug."""
        violations = check_reply("Good answer. Next time try using STAR.", STATIC_PROMPT)
        assert any(v.startswith("praise:") for v in violations)
        assert any(v.startswith("coaching_phrase:") for v in violations)

    def test_a_distress_exit_is_never_blocked_for_praise(self) -> None:
        """Same invariant as the rest of `check_reply`: the one reply that must never be
        discarded (AS-07) still passes even if it happens to contain a listed phrase."""
        reply = "I'm pausing this practice session. You did well to say that out loud."
        assert check_reply(reply, STATIC_PROMPT) == []
