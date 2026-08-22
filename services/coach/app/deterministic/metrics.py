"""docs/phase-2-BUILD.md TASK 2.5a: deterministic metrics, run before any model is invoked.
"Free, always correct, and they carry a surprising share of the report's perceived value."

Pure functions throughout — no DB, no model, no IO. Inputs are exactly `turn_metrics`'s columns
(CLAUDE.md §5: "No model ever writes here"), so this module never has anything to trust or
verify; the numbers are already ground truth by construction.

`DELIVERY_MODEL_VERSION` is what gets written to `turn_scores.model_version` for these rows —
"deterministic" rather than a real model name, so a report reader (and `model_calls`'s absence
for these rows) can immediately tell this score cost nothing and involved no model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DELIVERY_MODEL_VERSION = "deterministic-v1"
DELIVERY_CRITERION_KEY = "delivery"


@dataclass(frozen=True, slots=True)
class DeliveryTargets:
    """Configurable target bands (Task 2.5a: "scored against a configurable target band").
    Not scenario-specific — no scenario in content/scenarios/*.yaml carries a target answer
    length or pace band today, and CLAUDE.md §10 forbids inventing a number that isn't measured
    or authored; these are deliberately generic, reasonable defaults for a spoken interview
    answer, overridable by construction (every function below takes `targets` as a parameter)."""

    wpm_band: tuple[float, float] = (110.0, 170.0)
    filler_rate_threshold: float = 0.06
    answer_length_band_words: tuple[int, int] = (40, 220)
    min_speech_ratio: float = 0.5


def _band_score(value: float, low: float, high: float) -> float:
    """1-5, linear falloff outside [low, high], 5 inside it. Symmetric: equally far outside on
    either side scores the same — being fast and terse is not treated as better than being slow
    and rambling just because "under" sorts first numerically."""
    if low <= value <= high:
        return 5.0
    span = high - low
    if span <= 0:
        return 5.0
    distance = (low - value) if value < low else (value - high)
    penalty = min(4.0, (distance / span) * 4.0)
    return round(5.0 - penalty, 2)


def _threshold_score(value: float, threshold: float, *, higher_is_worse: bool) -> float:
    """1-5, 5 at/under (or at/over, for higher_is_worse=False) the threshold, falling off
    linearly to 1 at 3x the threshold — used for filler rate, where there's no "too low"."""
    if higher_is_worse:
        if value <= threshold:
            return 5.0
        excess = value - threshold
        penalty = min(4.0, (excess / max(threshold, 0.01)) * 4.0)
        return round(5.0 - penalty, 2)
    if value >= threshold:
        return 5.0
    deficit = threshold - value
    penalty = min(4.0, (deficit / max(threshold, 0.01)) * 4.0)
    return round(5.0 - penalty, 2)


DEFAULT_DELIVERY_TARGETS = DeliveryTargets()


def score_pace(wpm: float, targets: DeliveryTargets = DEFAULT_DELIVERY_TARGETS) -> float:
    low, high = targets.wpm_band
    return _band_score(wpm, low, high)


def score_filler(filler_rate: float, targets: DeliveryTargets = DEFAULT_DELIVERY_TARGETS) -> float:
    return _threshold_score(filler_rate, targets.filler_rate_threshold, higher_is_worse=True)


def score_answer_length(
    word_count: int, targets: DeliveryTargets = DEFAULT_DELIVERY_TARGETS
) -> float:
    low, high = targets.answer_length_band_words
    return _band_score(float(word_count), float(low), float(high))


def score_speech_ratio(
    speech_ratio: float, targets: DeliveryTargets = DEFAULT_DELIVERY_TARGETS
) -> float:
    return _threshold_score(speech_ratio, targets.min_speech_ratio, higher_is_worse=False)


@dataclass(frozen=True, slots=True)
class DeliveryScore:
    score: float  # 1-5, the average of the four sub-scores
    sub_scores: dict[str, float] = field(default_factory=dict)


def compute_delivery_score(
    turn_metrics: dict[str, Any], targets: DeliveryTargets = DEFAULT_DELIVERY_TARGETS
) -> DeliveryScore:
    """Task 2.5a: pace + filler rate + answer length + speech ratio -> one `delivery` score,
    "with no model involvement at all." A 3-word turn ("I don't know") still gets a real
    deterministic score here — the *rubric* criteria are what gate to "not enough signal" on a
    turn that short (Task 2.5's edge-case table), because those need the model to have had
    something to judge; delivery is pure arithmetic and is never gated."""
    sub_scores = {
        "pace": score_pace(float(turn_metrics["wpm"]), targets),
        "filler": score_filler(float(turn_metrics["filler_rate"]), targets),
        "answer_length": score_answer_length(int(turn_metrics["word_count"]), targets),
        "speech_ratio": score_speech_ratio(float(turn_metrics["speech_ratio"]), targets),
    }
    overall = round(sum(sub_scores.values()) / len(sub_scores), 2)
    return DeliveryScore(score=overall, sub_scores=sub_scores)


def compute_question_coverage(turns: list[dict[str, Any]]) -> float:
    """Task 2.5a: "question coverage." Session-level, not per-turn — coverage is "of the
    questions the persona asked, how many got a real answer," which only means something across
    the whole turn sequence. A persona turn counts as a question if it ends in "?" (the persona
    prompt requires "ask one question at a time," Task 2.3a, so this is a reliable signal); it
    counts as covered if the very next turn is a non-empty, non-truncated user turn. Returns a
    fraction in [0, 1]; the caller decides how (or whether) to fold this into a displayed score.
    """
    persona_questions = 0
    covered = 0
    for i, turn in enumerate(turns):
        if turn["speaker"] != "persona":
            continue
        text = str(turn["text"]).strip()
        if not text.endswith("?"):
            continue
        persona_questions += 1
        if i + 1 < len(turns):
            nxt = turns[i + 1]
            if nxt["speaker"] == "user" and str(nxt["text"]).strip() and not nxt["truncated"]:
                covered += 1
    if persona_questions == 0:
        return 1.0  # nothing was asked -> vacuously fully covered, not zero
    return round(covered / persona_questions, 4)
