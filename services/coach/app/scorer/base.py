"""docs/phase-2-BUILD.md TASK 2.5b: the Scorer protocol — "the interfaces built here must not
change in Phase 5 — only the scorer implementation swaps." `PromptedScorer` (prompted.py, this
phase) and `FinetunedScorer` (finetuned.py, Phase 5's stub) both implement this; no caller may
know which is in use (`report/build.py` selects one by config and never branches on the type).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Span:
    """Char offsets into the answer text — same shape `turn_scores.evidence_spans` stores
    (services/api/app/models/turn.py: "{start, end} char offsets into turns.text")."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class RubricCriterion:
    """Coach's own copy of what it needs from `rubric_criteria` — deliberately not api's ORM
    class (docs/decisions/0003's reasoning applies to coach too)."""

    key: str
    name: str
    description: str
    anchor_descriptors: dict[str, str]  # "1".."5" -> observable description


@dataclass(frozen=True, slots=True)
class CriterionScore:
    score: float | None  # None when confidence is 0 (Task 2.5's "not enough signal")
    confidence: float  # 0-1
    evidence_spans: list[Span] = field(default_factory=list)
    rationale: str | None = None


class Scorer(Protocol):
    version: str

    async def score(
        self, question: str, answer: str, criterion: RubricCriterion
    ) -> CriterionScore: ...

    async def score_batch(
        self, question: str, answer: str, criteria: list[RubricCriterion]
    ) -> list[CriterionScore]:
        """Task 2.5c: "score all criteria for one turn in a single call where the model
        supports it; fall back to per-criterion calls." Part of the Protocol (not just an
        optional extension `hasattr`-checked by callers) so every caller can rely on it
        existing — an implementation with no real batching support can satisfy this with the
        trivial per-criterion loop below; `PromptedScorer` overrides it with a real one call."""
        return [await self.score(question, answer, c) for c in criteria]
