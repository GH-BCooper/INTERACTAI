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


def get_scorer(*, impl: str | None = None) -> Scorer:
    """`impl` overrides the configured `scorer_impl` — used only by shadow mode
    (docs/phase-5-BUILD.md TASK 5.5d), which deliberately instantiates a *different*
    configuration from the primary scorer for live comparison. Every ordinary caller omits it
    and gets the configured primary, exactly as before."""
    impl = impl or get_settings().scorer_impl
    if impl == "finetuned":
        return FinetunedScorer()
    if impl == "prompted":
        return PromptedScorer()
    raise ValueError(f"unknown scorer_impl: {impl!r}")
