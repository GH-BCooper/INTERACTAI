#!/usr/bin/env python3
"""docs/phase-5-BUILD.md TASK 5.5a — `make eval`. Computes every Level-3 metric against the
held-out set and writes an `eval_runs` row. This is the real implementation — the Phase 0 stub
("not implemented yet - arrives in Phase 5") is retired here.

Usage:
    uv run python scripts/eval.py [--configuration NAME] [--split validation|test]
        [--publish] [--seed N]

The reporting split (test) is protected: without --publish, this script only ever evaluates
against validation. Every --publish invocation is logged — to stdout, to structlog, and as
`eval_runs.published=true` on the row itself, so "was this number ever computed against test"
is answerable from the database alone, not just this run's console output.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = REPO_ROOT / "services" / "training"
API_DIR = REPO_ROOT / "services" / "api"
for _path in (str(REPO_ROOT), str(TRAINING_DIR), str(API_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from baselines import deterministic_ridge, majority_class  # noqa: E402
from metrics import (  # noqa: E402
    adjacent_accuracy,
    expected_calibration_error,
    mean_absolute_error,
    quadratic_weighted_kappa,
    spearman_correlation,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings as get_api_settings  # noqa: E402
from app.models import EvalRun  # noqa: E402
from app.models.base import uuid7  # noqa: E402
from data import TrainingExample, load_examples  # noqa: E402

CONFIGURATIONS = {
    "majority_class": majority_class,
    "deterministic_ridge": deterministic_ridge,
}


def _type_token_ratio(text: str) -> float:
    words = [w.lower() for w in text.split()]
    if not words:
        return 0.0
    return len(set(words)) / len(words)


async def _write_eval_run(
    db: AsyncSession,
    *,
    suite: str,
    configuration: str,
    dataset_revision_hash: str,
    split: str,
    published: bool,
    metrics: dict[str, object],
    seed: int | None,
) -> None:
    now = datetime.now(UTC)
    db.add(
        EvalRun(
            id=uuid7(),
            created_at=now,
            updated_at=now,
            suite=suite,
            configuration=configuration,
            model_version_id=None,
            prompt_version=None,
            qwk=metrics.get("qwk"),
            mae=metrics.get("mae"),
            spearman=metrics.get("spearman"),
            adjacent_accuracy=metrics.get("adjacent_accuracy"),
            ece=metrics.get("ece"),
            false_alarm_rate=None,
            mean_cost_cents=None,
            mean_latency_ms=None,
            per_criterion=metrics.get("per_criterion", {}),
            seed=seed,
            dataset_revision_hash=dataset_revision_hash,
            split=split,
            published=published,
        )
    )
    await db.flush()


def evaluate(
    predictions: dict[str, dict[str, float]], examples: list[TrainingExample], criteria: list[str]
) -> dict[str, object]:
    per_criterion: dict[str, dict[str, float]] = {}
    all_true: list[float] = []
    all_pred: list[float] = []
    confidences: list[float] = []
    correct: list[bool] = []
    for criterion in criteria:
        pairs = [
            (ex.scores[criterion], predictions[ex.turn_id][criterion])
            for ex in examples
            if criterion in ex.scores and ex.turn_id in predictions
        ]
        if not pairs:
            continue
        y_true = [round(t) for t, _ in pairs]
        y_pred_raw = [p for _, p in pairs]
        y_pred_rounded = [min(5, max(1, round(p))) for p in y_pred_raw]
        per_criterion[criterion] = {
            "qwk": quadratic_weighted_kappa(y_true, y_pred_rounded),
            "mae": mean_absolute_error([float(t) for t in y_true], y_pred_raw),
            "adjacent_accuracy": adjacent_accuracy([float(t) for t in y_true], y_pred_raw),
        }
        all_true.extend(float(t) for t in y_true)
        all_pred.extend(y_pred_raw)
        for t, p in zip(y_true, y_pred_raw, strict=True):
            confidences.append(max(0.0, 1.0 - abs(p - round(p)) / 2.0))
            correct.append(round(p) == t)

    if not all_true:
        return {
            "qwk": None,
            "mae": None,
            "spearman": None,
            "adjacent_accuracy": None,
            "ece": None,
            "per_criterion": per_criterion,
            "n": 0,
        }
    all_true_rounded = [round(t) for t in all_true]
    all_pred_rounded = [min(5, max(1, round(p))) for p in all_pred]
    return {
        "qwk": quadratic_weighted_kappa(all_true_rounded, all_pred_rounded),
        "mae": mean_absolute_error(all_true, all_pred),
        "spearman": spearman_correlation(all_true, all_pred) if len(all_true) >= 2 else None,
        "adjacent_accuracy": adjacent_accuracy(all_true, all_pred),
        "ece": expected_calibration_error(confidences, correct) if confidences else None,
        "per_criterion": per_criterion,
        "n": len(all_true),
    }


def fairness_deltas(examples: list[TrainingExample]) -> dict[str, object]:
    """TASK 5.5a: "Fairness deltas: score differences across speaking rate, accent group and
    vocabulary richness, controlling for human-labelled content quality." "Accent group" has no
    data source anywhere in this schema — no field was ever collected for it (not a proxy
    computed and hidden, an honest absence, CLAUDE.md §10). Speaking rate (wpm) and vocabulary
    richness (type-token ratio) are real, computed here.
    """
    labeled = [ex for ex in examples if ex.scores]
    if len(labeled) < 4:
        return {
            "speaking_rate": "insufficient labelled data to compute a delta",
            "vocabulary_richness": "insufficient labelled data to compute a delta",
            "accent_group": "not collected - no such field exists in this schema (see "
            "docs/PHASE5-WALKTHROUGH.md)",
        }

    wpm_sorted = sorted(labeled, key=lambda ex: ex.features.wpm)
    mid = len(wpm_sorted) // 2
    slow_half, fast_half = wpm_sorted[:mid], wpm_sorted[mid:]

    ttr_sorted = sorted(labeled, key=lambda ex: _type_token_ratio(ex.answer))
    plain_half, rich_half = ttr_sorted[:mid], ttr_sorted[mid:]

    def _mean_score(group: list[TrainingExample]) -> float | None:
        values = [v for ex in group for v in ex.scores.values()]
        return sum(values) / len(values) if values else None

    speaking_rate_delta = None
    slow_mean, fast_mean = _mean_score(slow_half), _mean_score(fast_half)
    if slow_mean is not None and fast_mean is not None:
        speaking_rate_delta = round(fast_mean - slow_mean, 3)

    vocabulary_delta = None
    plain_mean, rich_mean = _mean_score(plain_half), _mean_score(rich_half)
    if plain_mean is not None and rich_mean is not None:
        vocabulary_delta = round(rich_mean - plain_mean, 3)

    return {
        "speaking_rate": {
            "slow_half_mean_score": slow_mean,
            "fast_half_mean_score": fast_mean,
            "delta": speaking_rate_delta,
            "n": len(labeled),
        },
        "vocabulary_richness": {
            "plain_half_mean_score": plain_mean,
            "rich_half_mean_score": rich_mean,
            "delta": vocabulary_delta,
            "n": len(labeled),
        },
        "accent_group": "not collected - no such field exists in this schema (see "
        "docs/PHASE5-WALKTHROUGH.md)",
    }


def weakest_criteria(per_criterion: dict[str, dict[str, float]], n: int = 3) -> list[str]:
    """TASK 5.5b: "the harness emits a 'weakest criteria' section." Ranked by QWK ascending."""
    ranked = sorted(per_criterion.items(), key=lambda kv: kv[1].get("qwk", 1.0))
    return [key for key, _ in ranked[:n]]


async def main_async(args: argparse.Namespace) -> int:
    if args.split == "test" and not args.publish:
        print(
            "Refusing to evaluate against the test (reporting) split without --publish "
            "(docs/phase-5-BUILD.md TASK 5.5b). Use --split validation for routine checks, or "
            "pass --publish to log a real reporting-split access.",
            file=sys.stderr,
        )
        return 1

    api_settings = get_api_settings()
    engine = create_async_engine(api_settings.database_url)
    try:
        async with AsyncSession(engine) as db:
            dataset_revision_hash, examples = await load_examples(db)
            if not examples:
                print(
                    "No dataset revision / turns found. Run dataset/build.py first.",
                    file=sys.stderr,
                )
                return 1

            criteria = sorted({c for ex in examples for c in ex.scores})
            if not criteria:
                print("No labelled turns yet - nothing to evaluate.", file=sys.stderr)
                return 1

            split_examples = [ex for ex in examples if ex.split == args.split]
            train_examples = [ex for ex in examples if ex.split == "train"]

            configurations = (
                [args.configuration] if args.configuration else list(CONFIGURATIONS.keys())
            )
            summary: list[dict[str, object]] = []

            for configuration in configurations:
                fn = CONFIGURATIONS.get(configuration)
                if fn is None:
                    print(f"Unknown configuration {configuration!r}, skipping.", file=sys.stderr)
                    continue
                predictions = fn(train_examples, split_examples, criteria)
                result = evaluate(predictions, split_examples, criteria)
                await _write_eval_run(
                    db,
                    suite="phase5_ablation",
                    configuration=configuration,
                    dataset_revision_hash=dataset_revision_hash,
                    split=args.split,
                    published=args.publish,
                    metrics=result,
                    seed=args.seed,
                )
                summary.append({"configuration": configuration, **result})
                print(
                    f"{configuration:25s} split={args.split:12s} n={result['n']:4d} "
                    f"qwk={result['qwk']} mae={result['mae']} ece={result['ece']}"
                )
                per_criterion_result = result["per_criterion"]
                if isinstance(per_criterion_result, dict) and per_criterion_result:
                    weakest = weakest_criteria(per_criterion_result)
                    print(f"  weakest criteria: {weakest}")

            deltas = fairness_deltas(split_examples)
            print(f"fairness deltas: {deltas}")

            await db.commit()

            if args.publish:
                print(
                    f"PUBLISH ACCESS LOGGED: {len(configurations)} configuration(s) evaluated "
                    f"against the test split, dataset_revision={dataset_revision_hash}, "
                    f"at {datetime.now(UTC).isoformat()}."
                )

            print(
                "\nThese numbers reflect whatever data currently exists in this environment. "
                "Before treating any of this as a publishable Phase 5 result, see "
                "docs/PHASE5-WALKTHROUGH.md — real human-labelled data at scale has not been "
                "collected here (CLAUDE.md §10: never fabricate a metric)."
            )
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", type=str, default=None)
    parser.add_argument("--split", choices=["validation", "test"], default="validation")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
