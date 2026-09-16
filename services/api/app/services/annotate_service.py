"""docs/phase-5-BUILD.md TASK 5.3 — the admin-only annotation tool. Reads from whatever the most
recent `dataset_revisions` row (services/training/dataset/build.py) says is in scope; writes
ordinary `Annotation` rows through the same table Task 3.4e's self-serve control uses, just from
a cross-session admin queue instead of a single user's own report.
"""

from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import NotFoundError, ValidationAppError
from ..core.s3 import presign_get_url
from ..models import (
    Annotation,
    DatasetMember,
    DatasetRevision,
    PreLabel,
    Rubric,
    RubricCriterion,
    Scenario,
    Turn,
    User,
)
from ..models import Session as SessionModel
from ..schemas.annotate import AnnotationProgress, AnnotationQueueItem, AnnotationSubmit


async def _latest_dataset_revision(db: AsyncSession) -> DatasetRevision | None:
    result = await db.execute(
        select(DatasetRevision).order_by(DatasetRevision.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def _preceding_persona_turn_text(
    db: AsyncSession, session_id: std_uuid.UUID, index: int
) -> str:
    result = await db.execute(
        select(Turn.text)
        .where(Turn.session_id == session_id, Turn.speaker == "persona", Turn.index < index)
        .order_by(Turn.index.desc())
        .limit(1)
    )
    text = result.scalar_one_or_none()
    return text or "(no preceding question found)"


async def get_queue(
    db: AsyncSession, admin: User, *, limit: int, pre_labelled: bool
) -> list[AnnotationQueueItem]:
    """TASK 5.3b: "Randomise across criteria and sessions" — `ORDER BY random()` in SQL, which
    is exactly that: a fresh shuffle spanning both dimensions on every fetch, not a per-session
    or per-criterion block. Excludes any (turn, criterion) this admin has already labelled at
    any round, so the same person is never shown an item twice, which is what makes a second
    admin account labelling the same double-labelled item genuinely independent.
    """
    revision = await _latest_dataset_revision(db)
    if revision is None:
        return []

    already_done = select(Annotation.turn_id, Annotation.criterion_key).where(
        Annotation.annotator_id == admin.id
    )

    stmt = (
        select(
            DatasetMember.turn_id,
            DatasetMember.session_id,
            DatasetMember.split,
            DatasetMember.double_labeled,
            Turn.text,
            Turn.text_scrubbed,
            Turn.index.label("turn_index"),
            Turn.start_ms,
            Turn.end_ms,
            SessionModel.recording_key,
            RubricCriterion.key.label("criterion_key"),
            RubricCriterion.name.label("criterion_name"),
            RubricCriterion.anchor_descriptors,
        )
        .join(Turn, Turn.id == DatasetMember.turn_id)
        .join(SessionModel, SessionModel.id == DatasetMember.session_id)
        .join(Scenario, Scenario.id == SessionModel.scenario_id)
        .join(Rubric, Rubric.id == Scenario.rubric_id)
        .join(RubricCriterion, RubricCriterion.rubric_id == Rubric.id)
        .where(DatasetMember.dataset_revision_hash == revision.hash)
        .where(tuple_(DatasetMember.turn_id, RubricCriterion.key).notin_(already_done))
        .order_by(func.random())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    pre_label_by_key: dict[tuple[std_uuid.UUID, str], int] = {}
    if pre_labelled:
        train_turn_ids = {row.turn_id for row in rows if row.split == "train"}
        if train_turn_ids:
            pre_label_rows = (
                await db.execute(
                    select(PreLabel.turn_id, PreLabel.criterion_key, PreLabel.score).where(
                        PreLabel.turn_id.in_(train_turn_ids)
                    )
                )
            ).all()
            pre_label_by_key = {(r.turn_id, r.criterion_key): r.score for r in pre_label_rows}

    items = []
    for row in rows:
        question = await _preceding_persona_turn_text(db, row.session_id, row.turn_index)
        answer_is_scrubbed = row.text_scrubbed is not None
        audio_url = presign_get_url(row.recording_key) if row.recording_key else None
        # TASK 5.3d: pre-labelling is train-split only, enforced here — never for
        # validation/test regardless of what the caller asked for.
        pre_label_score = (
            pre_label_by_key.get((row.turn_id, row.criterion_key)) if row.split == "train" else None
        )
        items.append(
            AnnotationQueueItem(
                turn_id=row.turn_id,
                session_id=row.session_id,
                question=question,
                answer_text=row.text_scrubbed if answer_is_scrubbed else row.text,
                answer_is_scrubbed=answer_is_scrubbed,
                audio_url=audio_url,
                audio_start_ms=row.start_ms,
                audio_end_ms=row.end_ms,
                criterion_key=row.criterion_key,
                criterion_name=row.criterion_name,
                anchor_descriptors=row.anchor_descriptors,
                split=row.split,
                double_labeled=row.double_labeled,
                pre_label_score=pre_label_score,
            )
        )
    return items


async def submit_annotation(db: AsyncSession, admin: User, body: AnnotationSubmit) -> Annotation:
    """TASK 5.3d: "the interface must not default to accept" — enforced here, not just in the
    frontend: if a pre-label existed for this (turn, criterion) and the submitted score matches
    it exactly, that's recorded as-is (an annotator is allowed to genuinely agree), but the
    submission must have come through this endpoint with an explicit score either way. There is
    no separate "accept the suggestion" action anywhere in this API — only "submit a score."
    """
    turn_result = await db.execute(select(Turn.id).where(Turn.id == body.turn_id))
    if turn_result.scalar_one_or_none() is None:
        raise NotFoundError("Turn not found.")

    pre_label_row = (
        await db.execute(
            select(PreLabel.score, PreLabel.model_version).where(
                PreLabel.turn_id == body.turn_id, PreLabel.criterion_key == body.criterion_key
            )
        )
    ).first()

    max_round_result = await db.execute(
        select(func.max(Annotation.round)).where(
            Annotation.turn_id == body.turn_id,
            Annotation.annotator_id == admin.id,
            Annotation.criterion_key == body.criterion_key,
        )
    )
    max_round = max_round_result.scalar_one()
    next_round = (max_round if max_round is not None else 0) + 1

    session_id_result = await db.execute(select(Turn.session_id).where(Turn.id == body.turn_id))
    session_id = session_id_result.scalar_one()

    expected_pre_label_score = pre_label_row.score if pre_label_row is not None else None
    if body.pre_label_score != expected_pre_label_score:
        raise ValidationAppError(
            "pre_label_score does not match the current pre-label for this item - refetch the "
            "queue before submitting (it may have changed, or this is a stale client state)."
        )

    annotation = Annotation(
        session_id=session_id,
        turn_id=body.turn_id,
        annotator_id=admin.id,
        criterion_key=body.criterion_key,
        round=next_round,
        score=body.score,
        notes=body.notes,
        pre_labelled=pre_label_row is not None,
        pre_label_score=pre_label_row.score if pre_label_row is not None else None,
    )
    db.add(annotation)
    await db.flush()
    return annotation


async def get_progress(db: AsyncSession) -> AnnotationProgress:
    revision = await _latest_dataset_revision(db)
    if revision is None:
        return AnnotationProgress(
            dataset_revision_hash=None,
            total_candidate_pairs=0,
            labeled_pairs=0,
            double_labeled_target=200,
            double_labeled_with_two_annotators=0,
            disagreements_pending_adjudication=0,
        )

    total_pairs_result = await db.execute(
        select(func.count())
        .select_from(DatasetMember)
        .join(SessionModel, SessionModel.id == DatasetMember.session_id)
        .join(Scenario, Scenario.id == SessionModel.scenario_id)
        .join(Rubric, Rubric.id == Scenario.rubric_id)
        .join(RubricCriterion, RubricCriterion.rubric_id == Rubric.id)
        .where(DatasetMember.dataset_revision_hash == revision.hash)
    )
    total_candidate_pairs = total_pairs_result.scalar_one()

    distinct_pairs_subquery = (
        select(Annotation.turn_id, Annotation.criterion_key).distinct().subquery()
    )
    labeled_result = await db.execute(select(func.count()).select_from(distinct_pairs_subquery))
    labeled_pairs = labeled_result.scalar_one()

    double_labeled_turn_ids_result = await db.execute(
        select(DatasetMember.turn_id).where(
            DatasetMember.dataset_revision_hash == revision.hash,
            DatasetMember.double_labeled.is_(True),
        )
    )
    double_labeled_turn_ids = {row[0] for row in double_labeled_turn_ids_result.all()}

    if double_labeled_turn_ids:
        annotator_counts_result = await db.execute(
            select(
                Annotation.turn_id,
                Annotation.criterion_key,
                func.count(func.distinct(Annotation.annotator_id)),
            )
            .where(Annotation.turn_id.in_(double_labeled_turn_ids))
            .group_by(Annotation.turn_id, Annotation.criterion_key)
        )
        rows = annotator_counts_result.all()
        with_two = sum(1 for _, _, n in rows if n >= 2)

        disagreement_count = 0
        for turn_id, criterion_key, n in rows:
            if n < 2:
                continue
            scores_result = await db.execute(
                select(Annotation.score)
                .where(Annotation.turn_id == turn_id, Annotation.criterion_key == criterion_key)
                .distinct()
            )
            scores = [s for (s,) in scores_result.all()]
            if scores and (max(scores) - min(scores)) > 1:
                disagreement_count += 1
    else:
        with_two = 0
        disagreement_count = 0

    return AnnotationProgress(
        dataset_revision_hash=revision.hash,
        total_candidate_pairs=total_candidate_pairs,
        labeled_pairs=labeled_pairs,
        double_labeled_target=len(double_labeled_turn_ids),
        double_labeled_with_two_annotators=with_two,
        disagreements_pending_adjudication=disagreement_count,
    )
