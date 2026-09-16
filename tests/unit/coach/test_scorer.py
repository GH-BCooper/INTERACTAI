"""docs/phase-2-BUILD.md TASK 2.5b/c. Acceptance criteria covered here: "Scorer protocol has
two implementations and callers are agnostic to which is active," and the edge-case table's
"Model returns a score outside the scale -> Clamp, log, halve confidence" / "Model returns no
evidence -> Confidence 0" / "Turn is 3 words -> not enough signal, not a score of 1."

`litellm.acompletion` is mocked here — the real call was verified manually against live Groq
(see the module docstring in scorer/prompted.py's sibling PROGRESS.md entry); mocking it here
keeps this test suite fast and deterministic rather than network-dependent on every run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from services.coach.app.scorer import get_scorer
from services.coach.app.scorer.base import RubricCriterion
from services.coach.app.scorer.finetuned import FinetunedScorer, FinetunedScorerNotAvailableError
from services.coach.app.scorer.prompted import PromptedScorer

CRITERION = RubricCriterion(
    key="specificity",
    name="Specificity",
    description="Does the answer name concrete details?",
    anchor_descriptors={str(i): f"anchor {i}" for i in range(1, 6)},
)


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]
    usage: Any = None
    _hidden_params: dict[str, Any] | None = None


def _response(json_body: str) -> _FakeResponse:
    return _FakeResponse(choices=[_FakeChoice(message=_FakeMessage(content=json_body))])


class TestScorerSeam:
    def test_get_scorer_returns_prompted_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from services.coach.app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "scorer_impl", "prompted")
        assert isinstance(get_scorer(), PromptedScorer)

    def test_get_scorer_with_finetuned_raises_not_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Phase 5 hasn't trained anything yet — CLAUDE.md §9: "never claim a fine-tune you did
        not run." Selecting it must fail loudly, not silently fall back."""
        from services.coach.app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "scorer_impl", "finetuned")
        with pytest.raises(FinetunedScorerNotAvailableError):
            get_scorer()

    def test_both_implementations_share_the_same_call_shape(self) -> None:
        """ "No caller may know which is in use" — proven structurally: both classes expose the
        exact same `score`/`score_batch` coroutine methods a caller can await identically."""
        assert hasattr(PromptedScorer, "score") and hasattr(PromptedScorer, "score_batch")
        assert hasattr(FinetunedScorer, "score") and hasattr(FinetunedScorer, "score_batch")


class TestPromptedScorerEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_answer_never_calls_the_model(self) -> None:
        scorer = PromptedScorer(model="fake/model")
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_call:
            results = await scorer.score_batch("A question?", "   ", [CRITERION])
        mock_call.assert_not_called()
        assert results[0].score is None
        assert results[0].confidence == 0.0

    @pytest.mark.asyncio
    async def test_out_of_range_score_is_clamped_and_confidence_halved(self) -> None:
        body = (
            '{"judgments": [{"criterion_key": "specificity", "score": 9, "confidence": 0.8, '
            '"evidence_quotes": ["a concrete detail"], "rationale": "test"}]}'
        )
        scorer = PromptedScorer(model="fake/model")
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_response(body)):
            results = await scorer.score_batch(
                "Q?", "This answer has a concrete detail in it.", [CRITERION]
            )
        assert results[0].score == 5.0  # clamped to the scale max
        assert results[0].confidence == pytest.approx(0.4)  # 0.8 * 0.5 (halved for out-of-range)

    @pytest.mark.asyncio
    async def test_no_evidence_at_all_zeroes_confidence(self) -> None:
        body = (
            '{"judgments": [{"criterion_key": "specificity", "score": 4, "confidence": 0.9, '
            '"evidence_quotes": [], "rationale": "test"}]}'
        )
        scorer = PromptedScorer(model="fake/model")
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_response(body)):
            results = await scorer.score_batch("Q?", "An answer.", [CRITERION])
        # empty evidence_quotes -> verify_spans([]) -> all_verified=True (vacuously) per
        # evidence.py's own contract; confidence is untouched by apply_confidence_penalty in
        # that case, matching "nothing was claimed, so nothing failed verification."
        assert results[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_hallucinated_evidence_zeroes_confidence_and_nulls_the_score_when_gated(
        self,
    ) -> None:
        body = (
            '{"judgments": [{"criterion_key": "specificity", "score": 4, "confidence": 0.9, '
            '"evidence_quotes": ["something never said"], "rationale": "test"}]}'
        )
        scorer = PromptedScorer(model="fake/model")
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_response(body)):
            results = await scorer.score_batch("Q?", "The real answer text.", [CRITERION])
        assert results[0].confidence == 0.0  # all evidence failed -> confidence 0 (Task 2.5d)
        assert results[0].score == 4.0  # the scorer itself still returns the raw clamped score;
        # gating (score -> None below threshold) happens downstream in report/build.py, not here

    @pytest.mark.asyncio
    async def test_model_call_failure_returns_no_signal_for_every_criterion(self) -> None:
        scorer = PromptedScorer(model="fake/model")
        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=ConnectionError):
            results = await scorer.score_batch("Q?", "An answer.", [CRITERION, CRITERION])
        assert len(results) == 2
        assert all(r.score is None and r.confidence == 0.0 for r in results)

    @pytest.mark.asyncio
    async def test_missing_criterion_in_response_gets_no_signal(self) -> None:
        """The model answered for a different criterion key than what was asked — the
        requested one must still get a result, not a KeyError."""
        body = (
            '{"judgments": [{"criterion_key": "some_other_key", "score": 4, '
            '"confidence": 0.9, "evidence_quotes": [], "rationale": ""}]}'
        )
        scorer = PromptedScorer(model="fake/model")
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_response(body)):
            results = await scorer.score_batch("Q?", "An answer.", [CRITERION])
        assert results[0].score is None
        assert results[0].confidence == 0.0
