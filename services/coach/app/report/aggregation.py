"""docs/phase-2-BUILD.md TASK 2.5e/2.5f: confidence gating and turn -> session aggregation.

Pure functions, operating on plain dicts shaped like `turn_scores`/`session_scores` rows (not
ORM objects — this module has no DB dependency, matching every other "the logic is testable
without touching the database" module in this repo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_MIN_TURNS_WITH_SIGNAL = 2


def gate_score(
    score: float | None, confidence: float, threshold: float
) -> tuple[float | None, bool]:
    """Task 2.5e: "Below CONFIDENCE_THRESHOLD, the criterion renders as 'not enough signal',
    never a number... A wrong score is far more damaging than a missing one." Returns
    `(displayed_score, is_gated)` — the single choke point every score (turn- or session-level)
    passes through before it's allowed to reach `turn_scores.score` / `session_scores.
    aggregate_score` or a report."""
    if score is None or confidence < threshold:
        return None, True
    return score, False


@dataclass(frozen=True, slots=True)
class SessionCriterionAggregate:
    criterion_key: str
    aggregate_score: float | None
    confidence: float
    evidence_turn_ids: list[str] = field(default_factory=list)
    percentile_vs_self: float | None = None


def aggregate_criterion(
    criterion_key: str,
    turn_rows: list[dict[str, Any]],
    *,
    confidence_threshold: float,
    min_turns_with_signal: int = DEFAULT_MIN_TURNS_WITH_SIGNAL,
) -> SessionCriterionAggregate:
    """Task 2.5f: "Weighted roll-up from turn scores to session scores... Criteria with
    insufficient turn-level signal aggregate to *not enough signal* rather than to a partial
    average over two turns." `turn_rows` are this criterion's `turn_scores` rows for one
    session — already-gated rows (`score is None`) are automatically excluded from "signal,"
    since a gated turn score contributed no number to begin with."""
    signal_rows = [
        r
        for r in turn_rows
        if r.get("score") is not None and float(r["confidence"]) >= confidence_threshold
    ]
    if len(signal_rows) < min_turns_with_signal:
        return SessionCriterionAggregate(
            criterion_key=criterion_key, aggregate_score=None, confidence=0.0
        )

    total_weight = sum(float(r["confidence"]) for r in signal_rows)
    weighted_sum = sum(float(r["score"]) * float(r["confidence"]) for r in signal_rows)
    aggregate_score = round(weighted_sum / total_weight, 2)
    session_confidence = round(min(1.0, total_weight / len(signal_rows)), 4)
    evidence_turn_ids = [str(r["turn_id"]) for r in signal_rows]
    return SessionCriterionAggregate(
        criterion_key=criterion_key,
        aggregate_score=aggregate_score,
        confidence=session_confidence,
        evidence_turn_ids=evidence_turn_ids,
    )


def percentile_vs_self(current_score: float, past_scores: list[float]) -> float | None:
    """Task 2.5f: "computed against the user's own history for the same scenario family."
    `None` — not 0, not a fabricated midpoint — when there is no history yet (CLAUDE.md §10:
    never fabricate a metric); a first session in a family has nothing to compare against."""
    if not past_scores:
        return None
    at_or_below = sum(1 for s in past_scores if s <= current_score)
    return round(at_or_below / len(past_scores), 4)


def pick_highlight_and_lowlight(
    turn_scores: list[dict[str, Any]], *, confidence_threshold: float
) -> tuple[str | None, str | None]:
    """Task 2.5g: "Highlight and lowlight turn selection: highest and lowest weighted turn
    scores with sufficient confidence." Averaged across every criterion scored for that turn,
    since a single turn carries multiple criterion scores and the report picks one turn to
    hold up as strongest/weakest overall, not per-criterion."""
    by_turn: dict[str, list[float]] = {}
    for r in turn_scores:
        if r.get("score") is not None and float(r["confidence"]) >= confidence_threshold:
            by_turn.setdefault(str(r["turn_id"]), []).append(float(r["score"]))

    if not by_turn:
        return None, None

    avg_by_turn = {tid: sum(scores) / len(scores) for tid, scores in by_turn.items()}
    highlight = max(avg_by_turn, key=lambda t: avg_by_turn[t])
    lowlight = min(avg_by_turn, key=lambda t: avg_by_turn[t])
    if highlight == lowlight:
        return highlight, None  # only one qualifying turn — no meaningful contrast to draw
    return highlight, lowlight
