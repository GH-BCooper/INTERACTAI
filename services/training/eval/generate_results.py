#!/usr/bin/env python3
"""docs/phase-5-BUILD.md TASK 5.5e — generates docs/RESULTS.md from the real `eval_runs` +
`dataset_revisions` tables (never hand-assembled). "Every row carries mean +/- std across
seeds. The human ceiling is the first row, always." IAA (the human ceiling) comes from
services/training/annotate/iaa.py's own computation, run fresh here rather than trusting a
possibly-stale docs/IAA_REPORT.md on disk.

Usage: uv run --directory services/training python eval/generate_results.py
"""

from __future__ import annotations

import asyncio
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "annotate"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataset"))
from config import get_training_settings  # noqa: E402
from iaa import compute_iaa  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.models import DatasetRevision, EvalRun  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_PATH = REPO_ROOT / "docs" / "RESULTS.md"

# The literal row order/labels from docs/phase-5-BUILD.md TASK 5.5e's own table.
CONFIGURATION_LABELS = {
    "majority_class": "Majority class",
    "deterministic_ridge": "Deterministic features + ridge",
    "frontier_zero_shot": "Frontier zero-shot",
    "frontier_few_shot": "Frontier few-shot (baseline)",
    "finetuned_single_seed": "Fine-tuned encoder, 1 seed",
    "finetuned_ensemble": "Fine-tuned encoder, 3-seed ens.",
    "finetuned_ensemble_calibrated": "+ isotonic calibration <- SHIPPED",
    "lora_1_5b": "LoRA 1.5B (not shipped)",
}
ROW_ORDER = list(CONFIGURATION_LABELS.keys())


async def _fetch_rows(dataset_revision_hash: str | None) -> list[EvalRun]:
    settings = get_training_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(engine) as db:
            stmt = select(EvalRun).where(EvalRun.split == "test", EvalRun.published.is_(True))
            if dataset_revision_hash:
                stmt = stmt.where(EvalRun.dataset_revision_hash == dataset_revision_hash)
            result = await db.execute(stmt)
            return list(result.scalars().all())
    finally:
        await engine.dispose()


async def _latest_dataset_revision() -> DatasetRevision | None:
    settings = get_training_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(engine) as db:
            result = await db.execute(
                select(DatasetRevision).order_by(DatasetRevision.created_at.desc()).limit(1)
            )
            return result.scalar_one_or_none()
    finally:
        await engine.dispose()


def _mean_std(values: list[float]) -> str:
    if not values:
        return "TODO: measure"
    if len(values) == 1:
        return f"{values[0]:.3f}"
    return f"{statistics.fmean(values):.3f} +/- {statistics.pstdev(values):.3f}"


async def generate() -> str:
    revision = await _latest_dataset_revision()
    revision_hash = revision.hash if revision else None
    eval_rows = await _fetch_rows(revision_hash)
    iaa = await compute_iaa()

    by_configuration: dict[str, list[EvalRun]] = defaultdict(list)
    for row in eval_rows:
        by_configuration[row.configuration].append(row)

    lines = ["# Results (Task 5.5e)", ""]
    lines.append(f"Generated: {datetime.now(UTC).isoformat()}")
    lines.append(f"Dataset revision: `{revision_hash or 'none'}`")
    lines.append("")

    if iaa["status"] != "computed" or iaa["overall_qwk"] is None:
        lines.append(
            "**No real human inter-annotator agreement figure exists in this environment "
            "yet.** docs/PHASE5-WALKTHROUGH.md explains why (no recruited-session data, no "
            "second independent human annotator) and what to do about it. Every number below "
            "is reported honestly against whatever data currently exists, which is NOT the "
            "target Phase 5 dataset — none of it should be read as a real Phase 5 result."
        )
    lines.append("")
    lines.append(
        "| Configuration | QWK | MAE | Spearman | Adj. acc | ECE | Cost/session | Latency |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")

    ceiling_qwk = iaa["overall_qwk"]
    ceiling_str = f"{ceiling_qwk:.3f}" if ceiling_qwk is not None else "TODO: measure"
    lines.append(f"| Human ceiling (2 annotators) | {ceiling_str} | - | - | - | - | - | - |")

    for configuration in ROW_ORDER:
        rows = by_configuration.get(configuration, [])
        label = CONFIGURATION_LABELS[configuration]
        if not rows:
            lines.append(f"| {label} | TODO: measure | | | | | | |")
            continue
        qwk = _mean_std([r.qwk for r in rows if r.qwk is not None])
        mae = _mean_std([r.mae for r in rows if r.mae is not None])
        spearman = _mean_std([r.spearman for r in rows if r.spearman is not None])
        adjacent = _mean_std([r.adjacent_accuracy for r in rows if r.adjacent_accuracy is not None])
        ece = _mean_std([r.ece for r in rows if r.ece is not None])
        cost = _mean_std([r.mean_cost_cents for r in rows if r.mean_cost_cents is not None])
        latency = _mean_std([r.mean_latency_ms for r in rows if r.mean_latency_ms is not None])
        lines.append(
            f"| {label} | {qwk} | {mae} | {spearman} | {adjacent} | {ece} | {cost} | {latency} |"
        )

    lines.append("")
    lines.append("## Weakest criteria and failure cases")
    lines.append("")
    weakest_found = False
    for configuration, rows in by_configuration.items():
        for row in rows:
            if not row.per_criterion:
                continue
            weakest_found = True
            worst = min(row.per_criterion.items(), key=lambda kv: kv[1].get("qwk", 1.0))
            worst_qwk = worst[1].get("qwk")
            lines.append(
                f"- `{configuration}`: weakest criterion is `{worst[0]}` (qwk={worst_qwk})"
            )
    if not weakest_found:
        lines.append(
            "No per-criterion breakdown exists yet - no eval_runs row has been published "
            "against real labelled data."
        )

    lines.append("")
    lines.append("## Honest fallback (Task 5.6)")
    lines.append("")
    lines.append(
        "If the numbers above are placeholders or come from smoke-test data: the prompted "
        "scorer (`services/coach/app/scorer/prompted.py`) is what ships today, labelled "
        "explicitly as the baseline. `docs/PHASE5-WALKTHROUGH.md` is the concrete next-steps "
        "document for collecting real data and training a real fine-tune on top of the "
        "infrastructure built this phase."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    content = asyncio.run(generate())
    RESULTS_PATH.write_text(content, encoding="utf-8")
    print(f"wrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
