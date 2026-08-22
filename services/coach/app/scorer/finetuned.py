"""docs/phase-2-BUILD.md TASK 2.5b: the Phase 5 seam. "Two implementations: PromptedScorer
(now) and FinetunedScorer (Phase 5). Selected by config. No caller may know which is in use."

Deliberately just the interface, not a working scorer — CLAUDE.md §9's own rule: "Never claim
a fine-tune you did not run." Building this out is Phase 5's job (docs/phase-5-BUILD.md), once
the human-labelled evaluation set exists to train and benchmark it against. Instantiating this
now raises rather than silently falling back to something else, so `scorer_impl=finetuned` in
config fails loudly instead of quietly scoring with a model that was never trained.
"""

from __future__ import annotations

from .base import CriterionScore, RubricCriterion


class FinetunedScorerNotAvailableError(Exception):
    pass


class FinetunedScorer:
    version = "finetuned:not-trained-yet"

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise FinetunedScorerNotAvailableError(
            "FinetunedScorer has no trained weights yet — Phase 5 builds and benchmarks this. "
            "Set COACH_SCORER_IMPL=prompted until then."
        )

    async def score(
        self, question: str, answer: str, criterion: RubricCriterion
    ) -> CriterionScore:  # pragma: no cover - unreachable until Phase 5
        raise FinetunedScorerNotAvailableError

    async def score_batch(
        self, question: str, answer: str, criteria: list[RubricCriterion]
    ) -> list[CriterionScore]:  # pragma: no cover - unreachable until Phase 5
        raise FinetunedScorerNotAvailableError
