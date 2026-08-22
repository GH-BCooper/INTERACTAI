"""docs/phase-2-BUILD.md TASK 2.3a: layered prompt assembly. "Assembly order is load-bearing.
Static -> semi-static -> dynamic, in that order... Anything variable placed above them destroys
prefix caching silently." """

from __future__ import annotations

from services.realtime.app.persona.difficulty import parse_difficulty_params
from services.realtime.app.persona.prompt import (
    STATIC_TEXT,
    DynamicContext,
    PersonaContext,
    assemble_messages,
    render_brief,
    render_dynamic,
)

DIFFICULTY = parse_difficulty_params(
    {
        "followups_on_vague": 1,
        "hint_after_pause_ms": None,
        "interrupt_over_words": None,
        "ack_length": "short",
        "silence_after_answer_ms": 0,
    }
)

PERSONA_CTX = PersonaContext(
    persona_name="Elena Kovac",
    persona_archetype="interviewer",
    persona_temperament="blunt",
    persona_brief="You are a staff engineer who interviews often.",
    scenario_brief="A backend system design screen.",
    opening_strategy="Ask about the hardest thing they shipped.",
    target_minutes=20,
    difficulty=DIFFICULTY,
)


class TestAssemblyOrder:
    def test_three_messages_in_static_brief_dynamic_order(self) -> None:
        dynamic_ctx = DynamicContext(candidate_speech="I rebuilt the pipeline.")
        messages = assemble_messages(PERSONA_CTX, dynamic_ctx)
        assert len(messages) == 3
        assert messages[0]["content"] == STATIC_TEXT
        assert messages[1]["content"] == render_brief(PERSONA_CTX)
        assert messages[2]["content"] == render_dynamic(dynamic_ctx)

    def test_static_and_brief_are_system_role_dynamic_is_user(self) -> None:
        dynamic_ctx = DynamicContext(candidate_speech="hello")
        messages = assemble_messages(PERSONA_CTX, dynamic_ctx)
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "system"
        assert messages[2]["role"] == "user"

    def test_static_and_brief_are_byte_identical_across_different_dynamic_content(self) -> None:
        """The actual prefix-caching-safety property: the static+brief prefix must not change
        even when the dynamic (per-turn) content varies wildly — otherwise there is no stable
        prefix for a provider to cache at all."""
        msgs_1 = assemble_messages(PERSONA_CTX, DynamicContext(candidate_speech="Answer one."))
        msgs_2 = assemble_messages(
            PERSONA_CTX,
            DynamicContext(
                candidate_speech="A completely different, much longer answer with other words.",
                recent_turns=[{"speaker": "user", "text": "prior turn"}],
                history_summary="some summary",
                elapsed_minutes=5,
                plan_topic="system design",
                pending_obligation="a number",
            ),
        )
        assert msgs_1[0]["content"] == msgs_2[0]["content"]
        assert msgs_1[1]["content"] == msgs_2[1]["content"]
        assert msgs_1[2]["content"] != msgs_2[2]["content"]


class TestStaticLayerContent:
    def test_contains_the_required_imperatives(self) -> None:
        """Task 2.3a: the static layer "must contain, as imperatives" several specific rules."""
        lowered = STATIC_TEXT.lower()
        assert "never" in lowered and "evaluate" in lowered
        assert "rubric" in lowered or "criteri" in lowered
        assert "one question at a time" in lowered
        assert "distress" in lowered or "danger" in lowered

    def test_wraps_candidate_speech_in_untrusted_tags(self) -> None:
        assert "<candidate_speech>" in STATIC_TEXT


class TestBriefRendering:
    def test_includes_persona_and_scenario_content(self) -> None:
        brief = render_brief(PERSONA_CTX)
        assert "Elena Kovac" in brief
        assert "staff engineer" in brief
        assert "backend system design screen" in brief

    def test_includes_difficulty_instructions(self) -> None:
        brief = render_brief(PERSONA_CTX)
        assert "follow up" in brief.lower()

    def test_never_mentions_the_rubric(self) -> None:
        """The brief renders persona/scenario/difficulty content only — never the rubric,
        which the persona must never know exists (CLAUDE.md §7/§9)."""
        brief = render_brief(PERSONA_CTX)
        assert "rubric" not in brief.lower()
        assert "criterion" not in brief.lower() and "criteria" not in brief.lower()

    def test_focus_areas_included_when_present(self) -> None:
        ctx = PersonaContext(
            persona_name=PERSONA_CTX.persona_name,
            persona_archetype=PERSONA_CTX.persona_archetype,
            persona_temperament=PERSONA_CTX.persona_temperament,
            persona_brief=PERSONA_CTX.persona_brief,
            scenario_brief=PERSONA_CTX.scenario_brief,
            opening_strategy=PERSONA_CTX.opening_strategy,
            target_minutes=PERSONA_CTX.target_minutes,
            difficulty=PERSONA_CTX.difficulty,
            focus_areas=["system design", "leadership"],
        )
        brief = render_brief(ctx)
        assert "system design" in brief and "leadership" in brief


class TestDynamicRendering:
    def test_wraps_candidate_speech(self) -> None:
        dynamic = render_dynamic(DynamicContext(candidate_speech="test answer"))
        assert "<candidate_speech>test answer</candidate_speech>" in dynamic

    def test_recent_turns_rendered_with_speaker_labels(self) -> None:
        ctx = DynamicContext(
            candidate_speech="ok",
            recent_turns=[
                {"speaker": "persona", "text": "What did you build?"},
                {"speaker": "user", "text": "A pipeline."},
            ],
        )
        dynamic = render_dynamic(ctx)
        assert "You: What did you build?" in dynamic
        assert "Candidate: A pipeline." in dynamic

    def test_history_summary_included_when_present(self) -> None:
        dynamic = render_dynamic(
            DynamicContext(candidate_speech="ok", history_summary="Covered system design.")
        )
        assert "Covered system design." in dynamic

    def test_pending_obligation_included_when_present(self) -> None:
        dynamic = render_dynamic(
            DynamicContext(candidate_speech="ok", pending_obligation="the actual latency number")
        )
        assert "the actual latency number" in dynamic
