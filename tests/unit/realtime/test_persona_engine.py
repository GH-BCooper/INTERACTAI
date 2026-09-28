"""docs/phase-2-BUILD.md TASK 2.3e: streaming and enforcement. `litellm.acompletion` is mocked
here (a real streaming call is exercised live in test_persona_live.py) so this suite stays fast
and deterministic while covering every edge case in Task 2.3's table."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from services.realtime.app.persona.difficulty import parse_difficulty_params
from services.realtime.app.persona.engine import (
    MAX_GENERATION_ATTEMPTS,
    PersonaReplyResult,
    generate_persona_reply,
    trim_to_last_complete_clause,
)
from services.realtime.app.persona.prompt import STATIC_TEXT, DynamicContext, PersonaContext
from services.realtime.app.persona.safety import is_distress_exit_reply

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
    persona_brief="A staff engineer who interviews often.",
    scenario_brief="A backend system design screen.",
    opening_strategy="Ask about the hardest thing they shipped.",
    target_minutes=20,
    difficulty=DIFFICULTY,
)
DYNAMIC_CTX = DynamicContext(candidate_speech="I rebuilt the ingestion pipeline.")


class TestTrimToLastCompleteClause:
    def test_already_complete_sentence_is_unchanged(self) -> None:
        assert trim_to_last_complete_clause("What did you build?") == "What did you build?"

    def test_mid_sentence_cutoff_trims_to_last_boundary(self) -> None:
        text = "That's interesting. What made it hard was the sca"
        assert trim_to_last_complete_clause(text) == "That's interesting."

    def test_no_boundary_at_all_returns_text_unchanged(self) -> None:
        text = "just some fragment with no punctuation at all"
        assert trim_to_last_complete_clause(text) == text

    def test_trailing_whitespace_is_stripped(self) -> None:
        assert trim_to_last_complete_clause("Okay.   ") == "Okay."

    def test_empty_string_returns_empty(self) -> None:
        assert trim_to_last_complete_clause("") == ""


class _FakeStreamChunk:
    def __init__(self, content: str | None, usage: Any = None) -> None:
        self.choices = [_FakeChoice(content)] if content is not None else []
        self.usage = usage


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.delta = _FakeDelta(content)


class _FakeDelta:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


async def _fake_stream(deltas: list[str]) -> Any:
    for d in deltas:
        yield _FakeStreamChunk(d)
    yield _FakeStreamChunk(None, usage=_FakeUsage(100, len(deltas)))


class TestGeneratePersonaReply:
    @pytest.mark.asyncio
    async def test_clean_reply_returned_on_first_attempt(self) -> None:
        async def fake_acompletion(**kwargs: Any) -> Any:
            return _fake_stream(["What made ", "that migration ", "hard?"])

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_persona_reply(
                model="fake/model",
                max_tokens=180,
                persona_context=PERSONA_CTX,
                dynamic_context=DYNAMIC_CTX,
                static_prompt_text=STATIC_TEXT,
                turn_index=0,
            )
        assert result.text == "What made that migration hard?"
        assert result.attempts == 1
        assert result.used_canned_deflection is False
        assert result.violations == []

    @pytest.mark.asyncio
    async def test_empty_reply_retries_once_then_uses_second_attempt(self) -> None:
        calls = {"n": 0}

        async def fake_acompletion(**kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                return _fake_stream([])
            return _fake_stream(["Go on, ", "what happened next?"])

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_persona_reply(
                model="fake/model",
                max_tokens=180,
                persona_context=PERSONA_CTX,
                dynamic_context=DYNAMIC_CTX,
                static_prompt_text=STATIC_TEXT,
                turn_index=0,
            )
        assert result.text == "Go on, what happened next?"
        assert result.attempts == 2
        assert result.used_canned_deflection is False

    @pytest.mark.asyncio
    async def test_rubric_leak_triggers_regeneration_then_canned_deflection(self) -> None:
        """Task 2.3e: "If it fails twice, use a canned in-character deflection." Every attempt
        here leaks a criterion name, so both attempts fail and the result must be the canned
        fallback, never the leaking text."""

        async def fake_acompletion(**kwargs: Any) -> Any:
            return _fake_stream(["Your specificity ", "was strong there."])

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_persona_reply(
                model="fake/model",
                max_tokens=180,
                persona_context=PERSONA_CTX,
                dynamic_context=DYNAMIC_CTX,
                static_prompt_text=STATIC_TEXT,
                turn_index=0,
            )
        assert result.used_canned_deflection is True
        assert result.attempts == MAX_GENERATION_ATTEMPTS
        assert "specificity" not in result.text.lower()
        assert any(v.startswith("rubric_leak") for v in result.violations)

    @pytest.mark.asyncio
    async def test_two_questions_triggers_regeneration_and_succeeds_on_retry(self) -> None:
        calls = {"n": 0}

        async def fake_acompletion(**kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                return _fake_stream(["What broke? ", "And why?"])
            return _fake_stream(["What broke first?"])

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_persona_reply(
                model="fake/model",
                max_tokens=180,
                persona_context=PERSONA_CTX,
                dynamic_context=DYNAMIC_CTX,
                static_prompt_text=STATIC_TEXT,
                turn_index=0,
            )
        assert result.text == "What broke first?"
        assert result.attempts == 2

    @pytest.mark.asyncio
    async def test_model_call_exception_does_not_raise_and_falls_back(self) -> None:
        async def fake_acompletion(**kwargs: Any) -> Any:
            raise ConnectionError("network down")

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_persona_reply(
                model="fake/model",
                max_tokens=180,
                persona_context=PERSONA_CTX,
                dynamic_context=DYNAMIC_CTX,
                static_prompt_text=STATIC_TEXT,
                turn_index=1,
            )
        assert result.used_canned_deflection is True
        assert result.text  # never empty, even on total failure
        # A provider failure must NOT be reported as `empty_reply`. It was, until 2026-09-27, and
        # that single conflation invalidated two hosted Level 2 runs: 48 of 72 replies in
        # eval_runs 01a0e409 looked like a reasoning model starving itself of output tokens and
        # were in fact Groq rate-limit errors. A run that cannot tell "the provider was down" from
        # "the persona said nothing" publishes a number about the wrong thing.
        assert result.violations == ["generation_error:ConnectionError"] * 2
        assert "empty_reply" not in result.violations
        # ...and the flag `turn.py`/`opening.py` route the MODEL_PERSONA_LOCAL failover off
        # (Task 2.1's degraded table) is set, which is the whole point of keeping the two reasons
        # apart. Before this existed, the switch was only reachable from the `thinking` timeout,
        # so a 429 — which returns in under 100ms and never trips a timeout — left the session
        # speaking canned deflections for the rest of its life (docs/decisions/0030).
        assert result.failed_on_provider_error is True

    @pytest.mark.asyncio
    async def test_a_genuinely_empty_generation_is_still_reported_as_empty_reply(self) -> None:
        """The other side of the distinction above: the provider answered fine, the model just
        produced no content. Same user-visible outcome, completely different fix."""

        async def fake_acompletion(**kwargs: Any) -> Any:
            return _fake_stream([])

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_persona_reply(
                model="fake/model",
                max_tokens=180,
                persona_context=PERSONA_CTX,
                dynamic_context=DYNAMIC_CTX,
                static_prompt_text=STATIC_TEXT,
                turn_index=1,
            )
        assert result.used_canned_deflection is True
        assert result.violations == ["empty_reply", "empty_reply"]
        assert not any(v.startswith("generation_error") for v in result.violations)
        # A reachable provider that produced nothing is not a provider failure: sending the
        # same prompt to a different model is not the fix, so no failover.
        assert result.failed_on_provider_error is False

    @pytest.mark.asyncio
    async def test_a_safety_violation_then_a_provider_error_is_not_a_provider_failure(
        self,
    ) -> None:
        """The boundary case for the failover flag. The provider demonstrably worked on the
        first attempt — the model just broke character — so the second attempt erroring is not
        evidence that a different provider would help. Failing over here would abandon the
        hosted model for the rest of the session on the strength of one transient blip."""
        calls = {"n": 0}

        async def fake_acompletion(**kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                return _fake_stream(["Why did you do that? And what would you change?"])
            raise ConnectionError("network down")

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_persona_reply(
                model="fake/model",
                max_tokens=180,
                persona_context=PERSONA_CTX,
                dynamic_context=DYNAMIC_CTX,
                static_prompt_text=STATIC_TEXT,
                turn_index=1,
            )
        assert result.used_canned_deflection is True
        assert result.violations == ["multiple_questions", "generation_error:ConnectionError"]
        assert result.failed_on_provider_error is False

    @pytest.mark.asyncio
    async def test_word_cap_truncation_trimmed_to_last_clause(self) -> None:
        async def fake_acompletion(**kwargs: Any) -> Any:
            return _fake_stream(["That's fair. ", "What made it har"])  # cut mid-word

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_persona_reply(
                model="fake/model",
                max_tokens=10,
                persona_context=PERSONA_CTX,
                dynamic_context=DYNAMIC_CTX,
                static_prompt_text=STATIC_TEXT,
                turn_index=0,
            )
        assert result.text == "That's fair."


class TestDistressBackstopWhenNoReplyIsAvailable:
    """AS-07's last line of defence: when every generation attempt failed there is no model reply
    to judge, and the canned deflection is the one answer that must never reach someone
    describing real danger. Observed on 2026-09-28 with the hosted model's daily quota exhausted:
    "I don't think I want to be alive after this." was answered with "Let's stay focused on the
    conversation — go ahead and answer the question." (docs/decisions/0032)."""

    @staticmethod
    async def _dead_provider_reply(candidate_speech: str) -> PersonaReplyResult:
        async def fake_acompletion(**kwargs: Any) -> Any:
            raise ConnectionError("provider down")

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            return await generate_persona_reply(
                model="fake/model",
                max_tokens=180,
                persona_context=PERSONA_CTX,
                dynamic_context=DynamicContext(candidate_speech=candidate_speech),
                static_prompt_text=STATIC_TEXT,
                turn_index=1,
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "distress_text",
        [
            "I don't want to be here anymore, I don't think I want to be alive after this.",
            "Honestly I've been thinking about hurting myself and this isn't helping.",
            "I need to stop, someone is here and I'm scared, I don't feel safe right now.",
        ],
    )
    async def test_real_distress_gets_the_exit_not_a_deflection(self, distress_text: str) -> None:
        result = await self._dead_provider_reply(distress_text)
        assert is_distress_exit_reply(result.text), result.text
        assert result.used_canned_deflection is False
        # Must NOT route to the MODEL_PERSONA_LOCAL failover: the care line is already correct
        # and deterministic, and a second provider is a chance to say something worse.
        assert result.failed_on_provider_error is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "stress_text",
        [
            "I'm really nervous, sorry, give me a second.",
            "This is hard, I'm blanking on the details right now.",
            "Ugh, I'm bombing this, can we move on?",
            "We killed the old pipeline and I rebuilt the ingestion path.",
        ],
    )
    async def test_ordinary_interview_stress_does_not_trigger_the_exit(
        self, stress_text: str
    ) -> None:
        """The false positive that matters: ending a real practice session over ordinary nerves,
        or over violent-sounding engineering idiom ("we killed the old pipeline")."""
        result = await self._dead_provider_reply(stress_text)
        assert not is_distress_exit_reply(result.text), result.text
        assert result.used_canned_deflection is True
