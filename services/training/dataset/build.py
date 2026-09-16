#!/usr/bin/env python3
"""docs/phase-5-BUILD.md TASK 5.2 — assembles the dataset, splits it, hashes it.

    services/training/dataset/build.py assembles turns from three sources with a `source` tag

Usage:
    uv run --directory services/training python dataset/build.py [--synthetic N] [--dev-fixtures]

--synthetic N   generate N real synthetic turns per scenario per quality level (1-5) via a real
                LLM call (dataset/synthetic.py) before building. Costs real API calls; omit to
                build only from whatever real, training-consented turns already exist.
--dev-fixtures  seed a small number of clearly-marked, non-real placeholder sessions first (see
                dev_fixtures.py) so the rest of the Phase 5 pipeline (annotation queue, training,
                eval) has enough rows to run through end-to-end as a smoke test. NEVER used to
                produce a number that could be mistaken for a real result — every fixture row is
                tagged and every summary this script prints says so.

Honest state of this environment (see docs/PHASE5-WALKTHROUGH.md): Phase 4's Day 17 recruited
sessions were never run, so the "recruited" source is expected to be empty here, and "self" is
whatever this project's own live-testing sessions across Phases 0-4 happened to produce under a
training_consent=true session. This script's job is to be correct about assembling *whatever
real data exists*, not to invent data that doesn't (CLAUDE.md §10).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # services/training
from config import get_training_settings  # noqa: E402
from records import TurnRecord  # noqa: E402
from split import (  # noqa: E402
    assert_no_speaker_leakage,
    compute_dataset_revision_hash,
    enforce_synthetic_cap,
    mark_double_labeled,
    source_breakdown,
    split_counts,
    split_dataset,
)
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.models import (  # noqa: E402
    Annotation,
    Consent,
    DatasetMember,
    DatasetRevision,
    Scenario,
    Turn,
    User,
)
from app.models import (
    Session as SessionModel,
)

DOUBLE_LABELED_TARGET = 200


async def _resolve_self_and_synthetic_user_ids(
    db: AsyncSession,
) -> tuple[object | None, object | None, list[str]]:
    """Returns (self_user_id, synthetic_user_id, warnings). See config.py's
    `training_self_user_email` docstring for the fallback rule."""
    settings = get_training_settings()
    warnings: list[str] = []

    synthetic_result = await db.execute(
        select(User.id).where(User.email == settings.synthetic_user_email)
    )
    synthetic_user_id = synthetic_result.scalar_one_or_none()

    if settings.training_self_user_email:
        self_result = await db.execute(
            select(User.id).where(User.email == settings.training_self_user_email)
        )
        self_user_id = self_result.scalar_one_or_none()
        if self_user_id is None:
            warnings.append(
                f"TRAINING_SELF_USER_EMAIL={settings.training_self_user_email!r} matches no "
                "user - every real user will be tagged 'recruited' instead of 'self'."
            )
        return self_user_id, synthetic_user_id, warnings

    real_users_result = await db.execute(
        select(User.id, User.created_at)
        .where(User.email != settings.synthetic_user_email)
        .order_by(User.created_at)
    )
    real_users = real_users_result.all()
    if len(real_users) == 0:
        warnings.append("No real (non-synthetic) users exist yet - nothing will be tagged 'self'.")
        return None, synthetic_user_id, warnings
    if len(real_users) > 1:
        warnings.append(
            f"{len(real_users)} real users exist and TRAINING_SELF_USER_EMAIL is unset - "
            "defaulting 'self' to the earliest-created account and tagging the rest "
            "'recruited'. Set TRAINING_SELF_USER_EMAIL in .env to be explicit."
        )
    return real_users[0][0], synthetic_user_id, warnings


async def _fetch_eligible_turns(
    db: AsyncSession, self_user_id: object | None, synthetic_user_id: object | None
) -> tuple[list[TurnRecord], list[str]]:
    """TASK 5.2a: turns from a session with an explicit `training_consent=true` Consent row
    (Task 4.5a: no consent row is NOT the same as consent), `speaker='user'` (the persona's own
    turns are never scored against the rubric), and `training_excluded=false` — the last check
    happens in SQL as the filter, and TASK 5.2a's "hard requirement" (excluded turns must be
    *recorded*, not just silently dropped) is satisfied by the separate excluded-turns query
    below.
    """
    result = await db.execute(
        select(
            Turn.id,
            Turn.session_id,
            SessionModel.user_id,
            SessionModel.brief,
        )
        .join(SessionModel, Turn.session_id == SessionModel.id)
        .join(Consent, Consent.session_id == SessionModel.id)
        .where(
            Turn.speaker == "user",
            Turn.training_excluded.is_(False),
            Consent.training_consent.is_(True),
        )
    )
    rows = result.all()

    turns: list[TurnRecord] = []
    for turn_id, session_id, user_id, brief in rows:
        source = "synthetic" if user_id == synthetic_user_id else (
            "self" if user_id == self_user_id else "recruited"
        )
        speaker_key = f"synthetic:{session_id}" if source == "synthetic" else str(user_id)
        quality_level = brief.get("quality_level") if source == "synthetic" and brief else None
        turns.append(
            TurnRecord(
                turn_id=str(turn_id),
                session_id=str(session_id),
                speaker_key=speaker_key,
                source=source,
                synthetic_quality_level=quality_level,
            )
        )

    excluded_result = await db.execute(
        select(Turn.id)
        .join(SessionModel, Turn.session_id == SessionModel.id)
        .join(Consent, Consent.session_id == SessionModel.id)
        .where(
            Turn.speaker == "user",
            Turn.training_excluded.is_(True),
            Consent.training_consent.is_(True),
        )
    )
    excluded_ids = [str(row[0]) for row in excluded_result.all()]

    return turns, excluded_ids


async def _attach_existing_scores(
    db: AsyncSession, turns: list[TurnRecord]
) -> tuple[list[TurnRecord], list[str]]:
    """Fills in `.scores` from any Annotation rows already collected (Task 5.3), for
    stratification reporting only — never used to decide inclusion/exclusion. Returns the
    (possibly-unchanged) turns and the list of Annotation ids that back the returned scores,
    which is exactly the `label_ids` half of TASK 5.2d's `(turn_ids, label_ids, split
    assignment)` hash.
    """
    if not turns:
        return turns, []
    turn_id_strs = {t.turn_id for t in turns}
    result = await db.execute(
        select(Annotation.id, Annotation.turn_id, Annotation.criterion_key, Annotation.score)
    )
    by_turn: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    label_ids: list[str] = []
    for annotation_id, turn_id, criterion_key, score in result.all():
        turn_id_str = str(turn_id)
        if turn_id_str not in turn_id_strs:
            continue
        by_turn[turn_id_str][criterion_key].append(float(score))
        label_ids.append(str(annotation_id))

    updated = []
    for t in turns:
        criterion_scores = by_turn.get(t.turn_id)
        if criterion_scores:
            means = {k: sum(v) / len(v) for k, v in criterion_scores.items()}
            updated.append(
                TurnRecord(
                    turn_id=t.turn_id,
                    session_id=t.session_id,
                    speaker_key=t.speaker_key,
                    source=t.source,
                    scores=means,
                    synthetic_quality_level=t.synthetic_quality_level,
                )
            )
        else:
            updated.append(t)
    return updated, label_ids


def _report_stratification(assignments, turns_by_id) -> str:  # type: ignore[no-untyped-def]
    """TASK 5.2c: "Stratify by criterion score distribution so all splits span the scale." With
    real labels this checks and reports the span; with none yet (the expected state before
    Task 5.3 has run) it says so honestly instead of pretending the check passed.
    """
    by_split_criterion: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    any_scores = False
    for a in assignments:
        record = turns_by_id.get(a.turn_id)
        if record and record.scores:
            any_scores = True
            for criterion, score in record.scores.items():
                by_split_criterion[a.split][criterion].add(round(score))
    if not any_scores:
        return (
            "no labels exist yet - stratification cannot be checked until Task 5.3 annotation "
            "has produced scores; re-run this build after labelling to verify span."
        )
    lines = []
    for split in ("train", "validation", "test"):
        for criterion, points in by_split_criterion.get(split, {}).items():
            lines.append(f"{split}/{criterion}: scores seen = {sorted(points)}")
    return "; ".join(lines) if lines else "labels exist but none fall in the current turn pool"


async def build(*, synthetic_per_level: int, dev_fixtures: bool) -> str:
    settings = get_training_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(engine) as db:
            if dev_fixtures:
                from dev_fixtures import seed_dev_fixtures

                await seed_dev_fixtures(db)
                await db.commit()

            if synthetic_per_level > 0:
                from synthetic import generate_batch
                from write_synthetic import write_synthetic_turns

                scenario_query = select(
                    Scenario.id, Scenario.family, Scenario.difficulty, Scenario.brief
                )
                scenario_rows = (await db.execute(scenario_query)).all()
                scenarios = [
                    {
                        "id": str(s.id),
                        "family": s.family,
                        "difficulty": s.difficulty,
                        "brief": s.brief,
                    }
                    for s in scenario_rows
                ]
                if not scenarios:
                    print(
                        "WARNING: no scenarios found in the database - run `make seed` first. "
                        "Skipping synthetic generation.",
                        file=sys.stderr,
                    )
                else:
                    generated = await generate_batch(
                        scenarios, per_scenario_per_level=synthetic_per_level
                    )
                    await write_synthetic_turns(db, generated)
                    await db.commit()
                    print(f"generated {len(generated)} synthetic turns via real LLM calls.")

            self_user_id, synthetic_user_id, warnings = await _resolve_self_and_synthetic_user_ids(
                db
            )
            for w in warnings:
                print(f"WARNING: {w}", file=sys.stderr)

            turns, excluded_ids = await _fetch_eligible_turns(db, self_user_id, synthetic_user_id)
            turns, label_ids = await _attach_existing_scores(db, turns)

            if not turns:
                print(
                    "0 eligible turns found (no session has an explicit training_consent=true "
                    "Consent row yet, or --synthetic/--dev-fixtures were not passed). See "
                    "docs/PHASE5-WALKTHROUGH.md.",
                    file=sys.stderr,
                )

            assignments = split_dataset(turns)
            assignments = enforce_synthetic_cap(assignments)
            assert_no_speaker_leakage(assignments)

            eligible_for_double_label = sorted(
                (a for a in assignments if a.split in ("validation", "test")),
                key=lambda a: a.turn_id,
            )
            double_labeled_ids = {
                a.turn_id for a in eligible_for_double_label[:DOUBLE_LABELED_TARGET]
            }
            assignments = mark_double_labeled(assignments, double_labeled_ids)

            turns_by_id = {t.turn_id: t for t in turns}
            revision_hash = compute_dataset_revision_hash(assignments, label_ids)
            counts = split_counts(assignments)
            breakdown = source_breakdown(assignments)
            speaker_count = len({t.speaker_key for t in turns if t.source != "synthetic"})
            stratification_note = _report_stratification(assignments, turns_by_id)

            notes = (
                f"double-labeled subset: {len(double_labeled_ids)}/{DOUBLE_LABELED_TARGET} "
                f"target reached. stratification: {stratification_note}"
            )
            if dev_fixtures:
                notes += (
                    " | THIS REVISION INCLUDES --dev-fixtures PLACEHOLDER DATA — see "
                    "docs/PHASE5-WALKTHROUGH.md before treating any downstream metric as real."
                )

            await db.execute(
                delete(DatasetMember).where(DatasetMember.dataset_revision_hash == revision_hash)
            )
            stmt = pg_insert(DatasetRevision).values(
                hash=revision_hash,
                turn_count=len(assignments),
                label_count=len(label_ids),
                speaker_count=speaker_count,
                source_breakdown=breakdown,
                split_counts=counts,
                excluded_turn_ids=excluded_ids,
                notes=notes,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["hash"],
                set_={
                    "turn_count": stmt.excluded.turn_count,
                    "label_count": stmt.excluded.label_count,
                    "speaker_count": stmt.excluded.speaker_count,
                    "source_breakdown": stmt.excluded.source_breakdown,
                    "split_counts": stmt.excluded.split_counts,
                    "excluded_turn_ids": stmt.excluded.excluded_turn_ids,
                    "notes": stmt.excluded.notes,
                },
            )
            await db.execute(stmt)

            if assignments:
                await db.execute(
                    pg_insert(DatasetMember).values(
                        [
                            {
                                "dataset_revision_hash": revision_hash,
                                "turn_id": a.turn_id,
                                "session_id": a.session_id,
                                "speaker_key": a.speaker_key,
                                "split": a.split,
                                "source": a.source,
                                "double_labeled": a.double_labeled,
                                "synthetic_quality_level": (
                                    turns_by_id[a.turn_id].synthetic_quality_level
                                ),
                            }
                            for a in assignments
                        ]
                    )
                )

            await db.commit()

            print(f"dataset_revision {revision_hash}")
            print(f"  turns: {len(assignments)} | labels so far: {len(label_ids)}")
            print(f"  sources: {breakdown}")
            print(f"  splits: {counts}")
            print(f"  distinct real speakers: {speaker_count}")
            print(f"  excluded (training_excluded=true): {len(excluded_ids)}")
            print(f"  double-labeled subset: {len(double_labeled_ids)} turns")
            if speaker_count < 8:
                print(
                    f"  WARNING: {speaker_count} distinct real speakers is below the Phase 5 "
                    "target of >= 8 (docs/phase-5-BUILD.md definition of done). "
                    "See docs/PHASE5-WALKTHROUGH.md.",
                    file=sys.stderr,
                )
            if len(assignments) < 1000:
                print(
                    f"  WARNING: {len(assignments)} turns is below the Phase 5 target of "
                    ">= 1,000. See docs/PHASE5-WALKTHROUGH.md.",
                    file=sys.stderr,
                )
            return revision_hash
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--synthetic",
        type=int,
        default=0,
        metavar="N",
        help="generate N real synthetic turns per scenario per quality level (1-5) first",
    )
    parser.add_argument(
        "--dev-fixtures",
        action="store_true",
        help="seed clearly-marked placeholder consented sessions first (never real data)",
    )
    args = parser.parse_args()
    asyncio.run(build(synthetic_per_level=args.synthetic, dev_fixtures=args.dev_fixtures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
