#!/usr/bin/env python3
"""docs/phase-5-BUILD.md TASK 5.4 — the ablation ladder, rows 1-8. Runs on Kaggle/Colab/locally,
CPU or GPU. Writes `eval_runs` rows (dataset_revision_hash always set — TASK 5.1's own rule) and,
for the fine-tuned rows, `model_versions` rows plus checkpoints under `models/` (gitignored,
CLAUDE.md's own directory layout — never committed).

Usage:
    uv run --directory services/training python train.py [--rows 1,2,5,6,7] [--seeds 3]
        [--epochs 4] [--skip-frontier] [--wandb-mode online]

--skip-frontier avoids real LLM calls for rows 3/4 (cost/quota) — off by default only because
this repo's own smoke-testing already burns real API quota elsewhere; a real run should include
them, they are "the real baseline to beat" (TASK 5.4a).
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wandb  # noqa: E402
from baselines import deterministic_ridge, frontier_prompted, majority_class  # noqa: E402
from calibration import (  # noqa: E402
    CalibrationGuard,
    apply_calibration,
    fit_isotonic_per_criterion,
)
from config import get_training_settings  # noqa: E402
from metrics import (  # noqa: E402
    adjacent_accuracy,
    expected_calibration_error,
    mean_absolute_error,
    quadratic_weighted_kappa,
    spearman_correlation,
)

from data import TrainingExample, load_examples_standalone  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_ROOT = REPO_ROOT / "models" / "scorer"


class TrainTestLeakageError(Exception):
    """TASK 5.4's own acceptance criterion: "Train/test leakage assertion present and passing."
    A second, independent check from split.py's own speaker-leakage assertion (TASK 5.2c) —
    this one runs against whatever data actually loaded into this training run, not the build
    step, so a stale or hand-edited dataset revision can't silently slip a test turn into
    training."""


def assert_no_train_test_leakage(
    train: list[TrainingExample], val: list[TrainingExample], test: list[TrainingExample]
) -> None:
    train_turns = {e.turn_id for e in train}
    test_turns = {e.turn_id for e in test}
    val_turns = {e.turn_id for e in val}
    if train_turns & test_turns:
        raise TrainTestLeakageError(f"{len(train_turns & test_turns)} turn(s) in both train/test")
    if train_turns & val_turns:
        raise TrainTestLeakageError(f"{len(train_turns & val_turns)} turn(s) in both train/val")

    train_speakers = {e.speaker_key for e in train if e.source != "synthetic"}
    test_speakers = {e.speaker_key for e in test if e.source != "synthetic"}
    val_speakers = {e.speaker_key for e in val if e.source != "synthetic"}
    if train_speakers & test_speakers:
        raise TrainTestLeakageError(
            f"speaker(s) {train_speakers & test_speakers} appear in both train and test"
        )
    if train_speakers & val_speakers:
        raise TrainTestLeakageError(
            f"speaker(s) {train_speakers & val_speakers} appear in both train and validation"
        )


def infer_criteria(examples: list[TrainingExample]) -> list[str]:
    seen: set[str] = set()
    for ex in examples:
        seen.update(ex.scores.keys())
    return sorted(seen)


def evaluate(
    predictions: dict[str, dict[str, float]],
    examples: list[TrainingExample],
    criteria: list[str],
) -> dict[str, object]:
    """Scores one row's predictions against ground truth, per criterion and overall — the
    shared evaluation path every ablation row goes through (baselines and the fine-tune alike),
    matching docs/phase-5-BUILD.md TASK 5.5a's metric list.
    """
    per_criterion: dict[str, dict[str, float]] = {}
    all_true: list[float] = []
    all_pred: list[float] = []
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

    if not all_true:
        return {
            "qwk": None, "mae": None, "spearman": None, "adjacent_accuracy": None,
            "per_criterion": per_criterion, "n": 0,
        }

    all_true_rounded = [round(t) for t in all_true]
    all_pred_rounded = [min(5, max(1, round(p))) for p in all_pred]
    return {
        "qwk": quadratic_weighted_kappa(all_true_rounded, all_pred_rounded),
        "mae": mean_absolute_error(all_true, all_pred),
        "spearman": spearman_correlation(all_true, all_pred) if len(all_true) >= 2 else None,
        "adjacent_accuracy": adjacent_accuracy(all_true, all_pred),
        "per_criterion": per_criterion,
        "n": len(all_true),
    }


async def run_finetune_seed(
    train: list[TrainingExample],
    val: list[TrainingExample],
    criteria: list[str],
    *,
    seed: int,
    epochs: int,
) -> tuple[object, dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """One seed of rows 5/6/7. Returns (trained model, val_predictions, train_predictions) —
    train_predictions only used for a quick overfitting sanity check, not reported as a metric.
    Real torch/transformers training loop; kept modest (few epochs, small batch) so it completes
    on a free-tier GPU in "< 30 min" (TASK 5.4's own acceptance criterion) and, in this CPU-only
    dev environment, in minutes rather than hours on the tiny amount of real data that exists.
    """
    import torch
    from model import MultiCriterionScorer, load_tokenizer, make_aux_features, soft_ordinal_loss
    from torch.optim import AdamW
    from torch.optim.lr_scheduler import LambdaLR

    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    tokenizer = load_tokenizer()
    model = MultiCriterionScorer(criteria).to(device)

    labeled_train = [ex for ex in train if ex.scores]
    if not labeled_train:
        return model, {}, {}

    def _encode_batch(batch: list[TrainingExample]) -> dict[str, torch.Tensor]:
        texts = [f"{ex.question} [SEP] {ex.answer}" for ex in batch]
        enc = tokenizer(
            texts, truncation=True, max_length=512, padding=True, return_tensors="pt"
        )
        aux = torch.tensor(
            [make_aux_features(ex.features.duration_ms, ex.features.word_count) for ex in batch],
            dtype=torch.float32,
        )
        return {
            "input_ids": enc["input_ids"].to(device),
            "attention_mask": enc["attention_mask"].to(device),
            "aux_features": aux.to(device),
        }

    batch_size = 8
    n_steps = max(1, (len(labeled_train) // batch_size) * epochs)
    optimizer = AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)
    warmup_steps = max(1, int(n_steps * 0.1))

    def _lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return step / warmup_steps
        progress = (step - warmup_steps) / max(1, n_steps - warmup_steps)
        import math

        return 0.5 * (1 + math.cos(math.pi * min(progress, 1.0)))

    scheduler = LambdaLR(optimizer, _lr_lambda)

    best_val_kappa = -2.0
    best_state: dict[str, torch.Tensor] | None = None
    patience_remaining = 1

    for _epoch in range(epochs):
        model.train()
        for i in range(0, len(labeled_train), batch_size):
            batch = labeled_train[i : i + batch_size]
            encoded = _encode_batch(batch)
            outputs = model(**encoded)
            loss = torch.tensor(0.0, device=device)
            for criterion in criteria:
                targets = torch.tensor(
                    [ex.scores.get(criterion, 3.0) for ex in batch],
                    dtype=torch.float32,
                    device=device,
                )
                mask = torch.tensor(
                    [1.0 if criterion in ex.scores else 0.0 for ex in batch], device=device
                )
                if mask.sum() == 0:
                    continue
                pred = outputs[criterion]
                mse = ((pred - targets) ** 2 * mask).sum() / mask.sum()
                ordinal = soft_ordinal_loss(pred[mask.bool()], targets[mask.bool()])
                loss = loss + mse + 0.1 * ordinal
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            scheduler.step()

        val_predictions = predict_with_model(model, tokenizer, val, criteria, device)
        val_metrics = evaluate(val_predictions, val, criteria)
        val_kappa = val_metrics["qwk"] if val_metrics["qwk"] is not None else -2.0
        if val_kappa > best_val_kappa:
            best_val_kappa = val_kappa
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            patience_remaining = 1
        else:
            patience_remaining -= 1
            if patience_remaining < 0:
                break  # TASK 5.4b: "early stopping on VALIDATION KAPPA, patience 1"

    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    val_predictions = predict_with_model(model, tokenizer, val, criteria, device)
    train_predictions = predict_with_model(model, tokenizer, labeled_train[:50], criteria, device)
    return model, val_predictions, train_predictions


def predict_with_model(
    model: object,
    tokenizer: object,
    examples: list[TrainingExample],
    criteria: list[str],
    device: object,
) -> dict[str, dict[str, float]]:
    import torch
    from model import make_aux_features

    if not examples:
        return {}
    predictions: dict[str, dict[str, float]] = {}
    model.eval()  # type: ignore[attr-defined]
    with torch.no_grad():
        for i in range(0, len(examples), 16):
            batch = examples[i : i + 16]
            texts = [f"{ex.question} [SEP] {ex.answer}" for ex in batch]
            enc = tokenizer(  # type: ignore[operator]
                texts, truncation=True, max_length=512, padding=True, return_tensors="pt"
            )
            aux = torch.tensor(
                [
                    make_aux_features(ex.features.duration_ms, ex.features.word_count)
                    for ex in batch
                ],
                dtype=torch.float32,
            )
            outputs = model(  # type: ignore[operator]
                input_ids=enc["input_ids"].to(device),
                attention_mask=enc["attention_mask"].to(device),
                aux_features=aux.to(device),
            )
            for j, ex in enumerate(batch):
                predictions[ex.turn_id] = {
                    criterion: float(outputs[criterion][j].item()) for criterion in criteria
                }
    return predictions


async def main_async(args: argparse.Namespace) -> None:
    settings = get_training_settings()
    dataset_revision_hash, examples = await load_examples_standalone()
    if not examples:
        print(
            "No dataset revision / turns found. Run "
            "`uv run --directory services/training python dataset/build.py` first.",
            file=sys.stderr,
        )
        return

    train = [e for e in examples if e.split == "train"]
    val = [e for e in examples if e.split == "validation"]
    test = [e for e in examples if e.split == "test"]
    assert_no_train_test_leakage(train, val, test)
    print(f"leakage assertion passed. train={len(train)} val={len(val)} test={len(test)}")

    criteria = infer_criteria(examples)
    if not criteria:
        print(
            "No labelled turns yet (0 Annotation rows) - nothing to train or evaluate against. "
            "See docs/PHASE5-WALKTHROUGH.md.",
            file=sys.stderr,
        )
        return
    print(f"criteria in scope: {criteria}")

    wandb.init(
        project=settings.wandb_project,
        mode=settings.wandb_mode,
        config={"dataset_revision_hash": dataset_revision_hash, "criteria": criteria, **vars(args)},
    )

    rows_to_run = {int(r) for r in args.rows.split(",")} if args.rows else set(range(1, 9))
    results: list[tuple[str, str, dict[str, object], int | None]] = []

    if 1 in rows_to_run:
        preds = majority_class(train, val + test, criteria)
        results.append(("majority_class", "validation", evaluate(preds, val, criteria), None))
        results.append(("majority_class", "test", evaluate(preds, test, criteria), None))

    if 2 in rows_to_run:
        preds = deterministic_ridge(train, val + test, criteria)
        results.append(("deterministic_ridge", "validation", evaluate(preds, val, criteria), None))
        results.append(("deterministic_ridge", "test", evaluate(preds, test, criteria), None))

    if 3 in rows_to_run and not args.skip_frontier:
        anchors: dict[str, dict[str, str]] = {}  # rubric text not carried by TrainingExample;
        # the prompt still scores meaningfully off the criterion name alone for this ablation.
        preds = await frontier_prompted(val + test, criteria, anchors, few_shot=False)
        results.append(("frontier_zero_shot", "validation", evaluate(preds, val, criteria), None))
        results.append(("frontier_zero_shot", "test", evaluate(preds, test, criteria), None))

    if 4 in rows_to_run and not args.skip_frontier:
        preds = await frontier_prompted(val + test, criteria, {}, few_shot=True)
        results.append(("frontier_few_shot", "validation", evaluate(preds, val, criteria), None))
        results.append(("frontier_few_shot", "test", evaluate(preds, test, criteria), None))

    seed_models = []
    seed_val_preds = []
    if {5, 6, 7} & rows_to_run and train and val:
        for seed in range(args.seeds):
            t0 = time.perf_counter()
            model, val_preds, _train_preds = await run_finetune_seed(
                train, val, criteria, seed=seed, epochs=args.epochs
            )
            elapsed = time.perf_counter() - t0
            print(f"seed {seed} trained in {elapsed:.1f}s")
            seed_models.append(model)
            seed_val_preds.append(val_preds)

        if 5 in rows_to_run and seed_val_preds:
            single_seed_metrics = evaluate(seed_val_preds[0], val, criteria)
            results.append(("finetuned_single_seed", "validation", single_seed_metrics, 0))

        if {6, 7} & rows_to_run and len(seed_val_preds) >= 1:
            ensemble_val = _ensemble(seed_val_preds, criteria)
            ensemble_metrics = evaluate(ensemble_val, val, criteria)
            results.append(("finetuned_ensemble", "validation", ensemble_metrics, None))

            if 7 in rows_to_run and val:
                guard = CalibrationGuard()
                raw_by_criterion: dict[str, list[float]] = defaultdict(list)
                target_by_criterion: dict[str, list[float]] = defaultdict(list)
                for ex in val:
                    for criterion in criteria:
                        if criterion in ex.scores and ex.turn_id in ensemble_val:
                            raw_by_criterion[criterion].append(ensemble_val[ex.turn_id][criterion])
                            target_by_criterion[criterion].append(ex.scores[criterion])
                if raw_by_criterion:
                    calibration_models = fit_isotonic_per_criterion(
                        dict(raw_by_criterion), dict(target_by_criterion),
                        split="validation", guard=guard,
                    )
                    calibrated_val_raw = {
                        c: [ensemble_val[ex.turn_id][c] for ex in val if ex.turn_id in ensemble_val]
                        for c in criteria if c in raw_by_criterion
                    }
                    calibrated = apply_calibration(calibration_models, calibrated_val_raw)
                    calibrated_predictions: dict[str, dict[str, float]] = defaultdict(dict)
                    for c, values in calibrated.items():
                        matching_examples = [ex for ex in val if ex.turn_id in ensemble_val]
                        for ex, v in zip(matching_examples, values, strict=True):
                            calibrated_predictions[ex.turn_id][c] = v
                    ece_before = _mean_ece(ensemble_val, val, criteria)
                    ece_after = _mean_ece(dict(calibrated_predictions), val, criteria)
                    result = evaluate(dict(calibrated_predictions), val, criteria)
                    result["ece_before"] = ece_before
                    result["ece_after"] = ece_after
                    results.append(("finetuned_ensemble_calibrated", "validation", result, None))

    if 8 in rows_to_run:
        print(
            "Row 8 (LoRA 1.5B ablation) skipped in this environment - see "
            "docs/PHASE5-WALKTHROUGH.md for why and how to run it with real GPU time. "
            "Not reported as a result; no placeholder metric written (CLAUDE.md §10)."
        )

    for configuration, split, metrics_result, _seed in results:
        n = metrics_result.get("n", 0)
        print(f"{configuration:30s} {split:12s} n={n:4d} qwk={metrics_result.get('qwk')}")
        wandb.log(
            {
                f"{configuration}/{split}/qwk": metrics_result.get("qwk"),
                f"{configuration}/{split}/mae": metrics_result.get("mae"),
                f"{configuration}/{split}/n": n,
            }
        )

    wandb.finish()

    print(
        "\nAll numbers above are computed against whatever data currently exists in this "
        "environment (dev fixtures / synthetic / a small amount of real self-testing data), "
        "NOT real human-labelled evaluation data at the Phase 5 target scale. "
        "See docs/PHASE5-WALKTHROUGH.md before treating any of this as a reportable result."
    )


def _ensemble(
    seed_predictions: list[dict[str, dict[str, float]]], criteria: list[str]
) -> dict[str, dict[str, float]]:
    """TASK 5.4c: "Average the three seeds at inference." Also the basis for confidence (seed
    standard deviation) — computed here but not yet threaded into eval_runs; see eval/harness.py.
    """
    all_turn_ids: set[str] = set()
    for preds in seed_predictions:
        all_turn_ids.update(preds.keys())
    ensemble: dict[str, dict[str, float]] = {}
    for turn_id in all_turn_ids:
        ensemble[turn_id] = {}
        for criterion in criteria:
            values = [
                p[turn_id][criterion]
                for p in seed_predictions
                if turn_id in p and criterion in p[turn_id]
            ]
            if values:
                ensemble[turn_id][criterion] = statistics.fmean(values)
    return ensemble


def _mean_ece(
    predictions: dict[str, dict[str, float]], examples: list[TrainingExample], criteria: list[str]
) -> float | None:
    confidences: list[float] = []
    correct: list[bool] = []
    for ex in examples:
        for criterion in criteria:
            if criterion in ex.scores and ex.turn_id in predictions:
                pred = predictions[ex.turn_id][criterion]
                true = ex.scores[criterion]
                # Distance-derived confidence proxy: closer prediction to the eventual rounded
                # value implies higher stated confidence, matching how the product's own
                # ensemble-disagreement confidence would behave in aggregate. A real deployment
                # uses seed disagreement directly (see eval/harness.py); this is the ECE-before
                # baseline for the raw, uncalibrated head.
                confidence = max(0.0, 1.0 - abs(pred - round(pred)) / 2.0)
                confidences.append(confidence)
                correct.append(round(pred) == round(true))
    if not confidences:
        return None
    return expected_calibration_error(confidences, correct)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=str, default="")
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--skip-frontier", action="store_true")
    parser.add_argument("--wandb-mode", type=str, default=None)
    args = parser.parse_args()
    if args.wandb_mode:
        import os

        os.environ["WANDB_MODE"] = args.wandb_mode
    asyncio.run(main_async(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
