"""docs/phase-4-BUILD.md TASK 4.5b acceptance criteria: "PII scrubber catches names, employers,
emails, phones and salary figures on a fixture" and "Pseudonyms are stable within a session."
"""

from __future__ import annotations

from services.coach.app.privacy.scrub import PseudonymTracker, scrub_session_turns, scrub_text

FIXTURE_TURN_1 = (
    "My name is Sarah Chen and I currently work as a backend engineer at Stripe, based in "
    "San Francisco."
)
FIXTURE_TURN_2 = (
    "You can reach Sarah Chen at sarah.chen@example.com or on +1 (415) 555-0199. Her current "
    "base salary is $145,000 a year, and her last offer from Anthropic was for 165k."
)


class TestScrubText:
    def test_catches_a_person_name(self) -> None:
        result = scrub_text(FIXTURE_TURN_1, PseudonymTracker())
        assert "Sarah Chen" not in result
        assert "[PERSON_1]" in result

    def test_catches_an_employer(self) -> None:
        result = scrub_text(FIXTURE_TURN_1, PseudonymTracker())
        assert "Stripe" not in result
        assert "[ORG_1]" in result

    def test_catches_a_location(self) -> None:
        result = scrub_text(FIXTURE_TURN_1, PseudonymTracker())
        assert "San Francisco" not in result
        assert "[LOCATION_1]" in result

    def test_catches_an_email_address(self) -> None:
        result = scrub_text(FIXTURE_TURN_2, PseudonymTracker())
        assert "sarah.chen@example.com" not in result
        assert "[EMAIL_1]" in result

    def test_catches_a_phone_number(self) -> None:
        result = scrub_text(FIXTURE_TURN_2, PseudonymTracker())
        assert "415" not in result
        assert "[PHONE_1]" in result

    def test_catches_a_dollar_salary_figure(self) -> None:
        result = scrub_text(FIXTURE_TURN_2, PseudonymTracker())
        assert "145,000" not in result
        assert "[SALARY_" in result

    def test_catches_a_shorthand_k_salary_figure(self) -> None:
        result = scrub_text("The other offer was 165k.", PseudonymTracker())
        assert "165k" not in result
        assert "[SALARY_1]" in result

    def test_leaves_ordinary_text_untouched(self) -> None:
        text = "I think the project went reasonably well, with a few rough edges."
        assert scrub_text(text, PseudonymTracker()) == text

    def test_leaves_ordinary_numbers_untouched(self) -> None:
        text = "We shipped 3 features and fixed 42 bugs that sprint."
        assert scrub_text(text, PseudonymTracker()) == text

    def test_empty_string_is_a_no_op(self) -> None:
        assert scrub_text("", PseudonymTracker()) == ""


class TestPseudonymStability:
    def test_same_name_gets_the_same_pseudonym_across_calls_sharing_a_tracker(self) -> None:
        tracker = PseudonymTracker()
        first = scrub_text("Sarah Chen joined the call.", tracker)
        second = scrub_text("Sarah Chen then left early.", tracker)
        assert "[PERSON_1]" in first
        assert "[PERSON_1]" in second

    def test_different_names_get_different_pseudonyms(self) -> None:
        tracker = PseudonymTracker()
        first = scrub_text("Sarah Chen led the project.", tracker)
        second = scrub_text("Miguel Torres reviewed it.", tracker)
        assert "[PERSON_1]" in first
        assert "[PERSON_2]" in second

    def test_a_fresh_tracker_does_not_share_state_with_another(self) -> None:
        result = scrub_text("Sarah Chen led the project.", PseudonymTracker())
        assert "[PERSON_1]" in result  # not [PERSON_2] or higher, from some other test's tracker


class TestScrubSessionTurns:
    def test_scrubs_every_turn_and_keeps_pseudonyms_stable_across_turns(self) -> None:
        turns: list[dict[str, object]] = [
            {"id": "turn-1", "text": FIXTURE_TURN_1},
            {"id": "turn-2", "text": FIXTURE_TURN_2},
        ]
        result = scrub_session_turns(turns)
        assert set(result.keys()) == {"turn-1", "turn-2"}
        assert "[PERSON_1]" in result["turn-1"]
        assert "[PERSON_1]" in result["turn-2"]  # "me" in turn 2 refers back to Sarah Chen
        assert "Sarah Chen" not in result["turn-1"]
        assert "Sarah Chen" not in result["turn-2"]

    def test_a_persona_turn_with_no_pii_passes_through_unchanged(self) -> None:
        turns: list[dict[str, object]] = [
            {"id": "turn-1", "text": "Tell me about a time you led a project."}
        ]
        result = scrub_session_turns(turns)
        assert result["turn-1"] == "Tell me about a time you led a project."
