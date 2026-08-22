"""Task 2.5b: `Scorer` selection by config — "No caller may know which is in use." Every caller
in this codebase gets its scorer through `get_scorer()`, never by importing `PromptedScorer` or
`FinetunedScorer` directly."""

from __future__ import annotations

from ..core.config import get_settings
from .base import CriterionScore, RubricCriterion, Scorer, Span
from .finetuned import FinetunedScorer
from .prompted import PromptedScorer

__all__ = [
    "CriterionScore",
    "RubricCriterion",
    "Scorer",
    "Span",
    "get_scorer",
]


def get_scorer() -> Scorer:
    impl = get_settings().scorer_impl
    if impl == "finetuned":
        return FinetunedScorer()
    if impl == "prompted":
        return PromptedScorer()
    raise ValueError(f"unknown scorer_impl: {impl!r}")
