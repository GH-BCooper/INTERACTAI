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
    generate_persona_reply,
    trim_to_last_complete_clause,
)
from services.realtime.app.persona.prompt import STATIC_TEXT, DynamicContext, PersonaContext

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
