"""docs/phase-5-BUILD.md TASK 5.4a — ablation-ladder rows 1-4. Each is a `predict(examples) ->
dict[turn_id, dict[criterion_key, float]]` function so train.py can score every row through the
exact same evaluation path (services/training/metrics.py) with no special-casing.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

import litellm
from pydantic import BaseModel
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_training_settings  # noqa: E402

from data import TrainingExample  # noqa: E402

Predictions = dict[str, dict[str, float]]


def majority_class(
    train: list[TrainingExample], predict_for: list[TrainingExample], criteria: list[str]
) -> Predictions:
    """Row 1: "The floor." Predicts each criterion's most common training-split score (ties
    broken by the smaller value, so the prediction stays inside the rubric's own scale
    deterministically rather than depending on dict ordering).
    """
    majority: dict[str, float] = {}
    for criterion in criteria:
        train_scores = [
            round(ex.scores[criterion]) for ex in train if criterion in ex.scores
        ]
        if not train_scores:
            majority[criterion] = 3.0  # rubric midpoint - no training signal for this criterion
            continue
        counts: dict[int, int] = {}
        for s in train_scores:
            counts[s] = counts.get(s, 0) + 1
        best = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
        majority[criterion] = float(best[0])
    return {ex.turn_id: dict(majority) for ex in predict_for}


def _feature_vector(ex: TrainingExample) -> list[float]:
    f = ex.features
    return [
        float(f.word_count),
        float(f.duration_ms),
        float(f.wpm),
        float(f.filler_rate),
        float(f.longest_pause_ms),
        float(f.speech_ratio),
    ]


def deterministic_ridge(
    train: list[TrainingExample], predict_for: list[TrainingExample], criteria: list[str]
) -> Predictions:
    """Row 2: "Deterministic features only + ridge regression." docs/phase-5-LEARN.md §9:
    "startlingly competitive on concision" — a fitted linear model per criterion, features from
    services/training/data.py's DeterministicFeatures (real turn_metrics when available, a
    disclosed text-only estimate otherwise).
    """
    predictions: Predictions = {ex.turn_id: {} for ex in predict_for}
    for criterion in criteria:
        labeled = [(ex, ex.scores[criterion]) for ex in train if criterion in ex.scores]
        if len(labeled) < 3:
            # Not enough labelled training examples to fit anything meaningful - fall back to
            # the training split's mean rather than fitting on noise, and say so is implicit in
            # this being a real, if degenerate, ridge fit path.
            fallback = statistics.fmean(s for _, s in labeled) if labeled else 3.0
            for ex in predict_for:
                predictions[ex.turn_id][criterion] = fallback
            continue
        x = [_feature_vector(ex) for ex, _ in labeled]
        y = [s for _, s in labeled]
        model = Ridge(alpha=1.0)
        model.fit(x, y)
        preds = model.predict([_feature_vector(ex) for ex in predict_for])
        for ex, pred in zip(predict_for, preds, strict=True):
            predictions[ex.turn_id][criterion] = float(min(5.0, max(1.0, pred)))
    return predictions


class _JudgmentOut(BaseModel):
    score: int


async def frontier_score_one(
    question: str, answer: str, criterion_key: str, anchors: dict[str, str], *, few_shot: bool
) -> float:
    anchor_block = "\n".join(f"{point}: {desc}" for point, desc in sorted(anchors.items()))
    few_shot_block = ""
    if few_shot:
        few_shot_block = (
            "\n\nExample: a rambling, unstructured answer with no clear beginning or end "
            "scores 1-2. An answer with a clear situation-action-outcome arc and a close that "
            "returns to the question scores 4-5.\n"
        )
    prompt = (
        f"Score the candidate's answer on criterion '{criterion_key}' using this 1-5 scale:\n"
        f"{anchor_block}{few_shot_block}\n\nQuestion: {question}\nAnswer: {answer}\n\n"
        "Return only the integer score."
    )
    settings = get_training_settings()
    response = await litellm.acompletion(
        model=settings.training_generator_model,
        messages=[{"role": "user", "content": prompt}],
        response_format=_JudgmentOut,
        temperature=0.0,
    )
    parsed = _JudgmentOut.model_validate_json(response.choices[0].message.content)
    return float(min(5, max(1, parsed.score)))


async def frontier_prompted(
    predict_for: list[TrainingExample],
    criteria: list[str],
    anchors_by_criterion: dict[str, dict[str, str]],
    *,
    few_shot: bool,
) -> Predictions:
    """Rows 3/4: zero-shot / few-shot frontier baseline. Real litellm calls — this is
    `services/coach`'s exact PromptedScorer approach in miniature, kept independent per
    docs/decisions/0003's established convention rather than importing across services.
    """
    predictions: Predictions = {}
    for ex in predict_for:
        predictions[ex.turn_id] = {}
        for criterion in criteria:
            score = await frontier_score_one(
                ex.question,
                ex.answer,
                criterion,
                anchors_by_criterion.get(criterion, {}),
                few_shot=few_shot,
            )
            predictions[ex.turn_id][criterion] = score
    return predictions
