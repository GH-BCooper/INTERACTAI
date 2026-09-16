#!/usr/bin/env python3
"""docs/phase-5-BUILD.md TASK 5.3d — model pre-labelling, training split ONLY. Writes
`pre_labels` rows (never `annotations` — a pre-label is a suggestion, not a completed human
judgement; see services/api/app/models/pre_label.py's docstring). The admin queue
(services/api/app/services/annotate_service.py::get_queue) already refuses to surface a
pre-label for anything but a train-split item; this script enforces the same rule on the write
side too, so a bug in one enforcement point doesn't leak an eval-split suggestion into the tool.

Usage: uv run --directory services/training python annotate/pre_label.py [--criteria a,b,c]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataset"))
from baselines import frontier_score_one  # noqa: E402
from config import get_training_settings  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.models import (  # noqa: E402  # noqa: E402
    DatasetMember,
    DatasetRevision,
    PreLabel,
    RubricCriterion,
    Scenario,
    Turn,
)
from app.models import Session as SessionModel  # noqa: E402


async def _preceding_persona_text(db: AsyncSession, session_id: object, index: int) -> str:
    result = await db.execute(
        select(Turn.text)
        .where(Turn.session_id == session_id, Turn.speaker == "persona", Turn.index < index)
        .order_by(Turn.index.desc())
        .limit(1)
    )
    return result.scalar_one_or_none() or ""


async def pre_label(*, criteria_filter: list[str] | None) -> int:
    settings = get_training_settings()
    engine = create_async_engine(settings.database_url)
    written = 0
    try:
        async with AsyncSession(engine) as db:
            revision_result = await db.execute(
                select(DatasetRevision.hash).order_by(DatasetRevision.created_at.desc()).limit(1)
            )
            revision_hash = revision_result.scalar_one_or_none()
            if revision_hash is None:
                print("No dataset revision exists yet.", file=sys.stderr)
                return 0

            # TASK 5.3d: "Training split only. Never the evaluation split." — the WHERE clause,
            # not a filter applied after the fact.
            stmt = (
                select(
                    DatasetMember.turn_id,
                    Turn.text,
                    Turn.text_scrubbed,
                    Turn.index,
                    Turn.session_id,
                    RubricCriterion.key,
                    RubricCriterion.anchor_descriptors,
                )
                .join(Turn, Turn.id == DatasetMember.turn_id)
                .join(SessionModel, SessionModel.id == DatasetMember.session_id)
                .join(Scenario, Scenario.id == SessionModel.scenario_id)
                .join(RubricCriterion, RubricCriterion.rubric_id == Scenario.rubric_id)
                .where(
                    DatasetMember.dataset_revision_hash == revision_hash,
                    DatasetMember.split == "train",
                )
            )
            rows = (await db.execute(stmt)).all()

            for turn_id, text, text_scrubbed, index, session_id, criterion_key, anchors in rows:
                if criteria_filter and criterion_key not in criteria_filter:
                    continue
                question = await _preceding_persona_text(db, session_id, index)
                answer = text_scrubbed or text
                score = await frontier_score_one(
                    question, answer, criterion_key, anchors, few_shot=True
                )
                stmt_insert = pg_insert(PreLabel).values(
                    turn_id=turn_id,
                    criterion_key=criterion_key,
                    score=int(score),
                    model_version=f"pre-label:{settings.training_generator_model}",
                )
                stmt_insert = stmt_insert.on_conflict_do_update(
                    index_elements=["turn_id", "criterion_key"],
                    set_={
                        "score": stmt_insert.excluded.score,
                        "model_version": stmt_insert.excluded.model_version,
                    },
                )
                await db.execute(stmt_insert)
                written += 1

            await db.commit()
            print(f"wrote {written} pre-labels (train split only) for revision {revision_hash}")
            return written
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--criteria", type=str, default="")
    args = parser.parse_args()
    criteria_filter = [c.strip() for c in args.criteria.split(",")] if args.criteria else None
    asyncio.run(pre_label(criteria_filter=criteria_filter))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
