#!/usr/bin/env python3
"""docs/phase-5-BUILD.md TASK 5.3c: inter-annotator agreement on the 200-turn double-labelled
subset. "Compute it first" — this is the ceiling every model metric in docs/RESULTS.md is
reported beside.

Convention this script documents and relies on (not spelled out verbatim in the phase doc,
since the doc's schema doesn't distinguish round-by-annotator from round-by-attempt): for a
given (turn_id, criterion_key) pair, each distinct `annotator_id` contributes one score — its
*latest* round if that annotator revisited the item more than once. When exactly two distinct
annotators have labelled a pair, IAA uses both directly. When a third distinct annotator has
also labelled it (TASK 5.3c: "Disagreements greater than one point go to an adjudication
round"), the *third* annotator's score is treated as the adjudicated ground truth and the pair
is excluded from the raw two-rater IAA computation — adjudication resolves a disagreement, it
doesn't average it away.

Usage: uv run --directory services/training python annotate/iaa.py [--write-report]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataset"))
from config import get_training_settings  # noqa: E402
from metrics import quadratic_weighted_kappa  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.models import Annotation, DatasetMember, DatasetRevision  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = REPO_ROOT / "docs" / "IAA_REPORT.md"


async def _latest_double_labeled_turn_ids(db: AsyncSession) -> tuple[str | None, set[str]]:
    revision_result = await db.execute(
        select(DatasetRevision.hash).order_by(DatasetRevision.created_at.desc()).limit(1)
    )
    revision_hash = revision_result.scalar_one_or_none()
    if revision_hash is None:
        return None, set()
    members_result = await db.execute(
        select(DatasetMember.turn_id).where(
            DatasetMember.dataset_revision_hash == revision_hash,
            DatasetMember.double_labeled.is_(True),
        )
    )
    return revision_hash, {str(row[0]) for row in members_result.all()}


async def compute_iaa() -> dict[str, object]:
    settings = get_training_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(engine) as db:
            revision_hash, double_labeled_ids = await _latest_double_labeled_turn_ids(db)
            if not double_labeled_ids:
                return {
                    "dataset_revision_hash": revision_hash,
                    "double_labeled_turns": 0,
                    "status": "no double-labeled turns exist yet",
                    "per_criterion": {},
                    "overall_qwk": None,
                    "adjudicated_pairs": 0,
                    "pairs_missing_a_second_annotator": 0,
                }

            annotations_result = await db.execute(
                select(
                    Annotation.turn_id,
                    Annotation.criterion_key,
                    Annotation.annotator_id,
                    Annotation.round,
                    Annotation.score,
                    Annotation.created_at,
                ).where(Annotation.turn_id.in_(double_labeled_ids))
            )
            rows = annotations_result.all()

            # latest round per (turn, criterion, annotator)
            latest: dict[tuple[str, str, str], tuple[int, int]] = {}
            for turn_id, criterion_key, annotator_id, round_, score, _created_at in rows:
                key = (str(turn_id), criterion_key, str(annotator_id))
                if key not in latest or latest[key][0] < round_:
                    latest[key] = (round_, score)

            by_pair: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
            for (turn_id, criterion_key, annotator_id), (_round, score) in latest.items():
                by_pair[(turn_id, criterion_key)][annotator_id] = score

            per_criterion_true: dict[str, list[int]] = defaultdict(list)
            per_criterion_pred: dict[str, list[int]] = defaultdict(list)
            adjudicated_pairs = 0
            missing_second = 0

            for (_turn_id, criterion_key), annotator_scores in by_pair.items():
                if len(annotator_scores) < 2:
                    missing_second += 1
                    continue
                # Deterministic order (sorted by annotator_id) so the "first two" are stable
                # across runs regardless of dict iteration order.
                ordered = sorted(annotator_scores.items())
                if len(ordered) >= 3:
                    adjudicated_pairs += 1
                    continue  # resolved by adjudication, excluded from raw IAA per docstring
                (_a1, s1), (_a2, s2) = ordered[0], ordered[1]
                per_criterion_true[criterion_key].append(s1)
                per_criterion_pred[criterion_key].append(s2)

            per_criterion_qwk: dict[str, float] = {}
            all_true: list[int] = []
            all_pred: list[int] = []
            for criterion_key in per_criterion_true:
                true_scores = per_criterion_true[criterion_key]
                pred_scores = per_criterion_pred[criterion_key]
                per_criterion_qwk[criterion_key] = quadratic_weighted_kappa(
                    true_scores, pred_scores
                )
                all_true.extend(true_scores)
                all_pred.extend(pred_scores)

            overall_qwk = quadratic_weighted_kappa(all_true, all_pred) if all_true else None

            return {
                "dataset_revision_hash": revision_hash,
                "double_labeled_turns": len(double_labeled_ids),
                "pairs_with_two_annotators": len(all_true),
                "status": "computed",
                "per_criterion": per_criterion_qwk,
                "overall_qwk": overall_qwk,
                "adjudicated_pairs": adjudicated_pairs,
                "pairs_missing_a_second_annotator": missing_second,
            }
    finally:
        await engine.dispose()


def render_report(result: dict[str, object]) -> str:
    lines = ["# Inter-annotator agreement (Task 5.3c)", ""]
    lines.append(f"Dataset revision: `{result['dataset_revision_hash']}`")
    lines.append(f"Double-labeled turns in this revision: {result['double_labeled_turns']}")
    lines.append("")
    if result["status"] != "computed":
        lines.append(f"**Status: {result['status']}.** No IAA figure exists yet.")
        return "\n".join(lines) + "\n"

    pairs_with_two = result["pairs_with_two_annotators"]
    lines.append(f"Pairs with exactly two independent annotators: {pairs_with_two}")
    lines.append(
        f"Pairs resolved by adjudication (3rd annotator, excluded from raw IAA): "
        f"{result['adjudicated_pairs']}"
    )
    lines.append(
        f"Pairs still missing a second annotator: {result['pairs_missing_a_second_annotator']}"
    )
    lines.append("")
    overall_qwk_value = result["overall_qwk"]
    overall_line = (
        f"**Overall QWK: {overall_qwk_value:.3f}**"
        if overall_qwk_value is not None
        else "Overall QWK: n/a"
    )
    lines.append(overall_line)
    lines.append("")
    lines.append("| Criterion | QWK |")
    lines.append("|---|---|")
    per_criterion = result["per_criterion"]
    if not isinstance(per_criterion, dict):
        raise TypeError("per_criterion must be a dict")
    for criterion, qwk in sorted(per_criterion.items()):
        lines.append(f"| {criterion} | {qwk:.3f} |")
    lines.append("")
    overall = result["overall_qwk"]
    if overall is not None and overall < 0.5:
        lines.append(
            "> **Below 0.5.** docs/phase-5-BUILD.md TASK 5.3c: \"fix the rubric anchors before "
            "training anything.\" A model cannot be more consistent than its labels."
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(compute_iaa())
    report = render_report(result)
    print(report)
    if args.write_report:
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
