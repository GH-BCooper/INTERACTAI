"""Loads training examples from the latest dataset revision. Shared by train.py (ablation
ladder) and eval/harness.py (make eval) so both read the exact same rows the exact same way —
the single most important property for "a metric you cannot attribute to a dataset version is
not reproducible" (docs/phase-5-BUILD.md TASK 5.2d).
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_training_settings  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.models import (  # noqa: E402  # noqa: E402
    Annotation,
    DatasetMember,
    DatasetRevision,
    Turn,
    TurnMetrics,
)

# A conservative, transcript-plausible filler list — good enough for the row-2 deterministic
# baseline's fallback estimator (see DeterministicFeatures.from_text_fallback below); the real
# figure, when turn_metrics exists, always wins.
_FILLER_WORDS = re.compile(r"\b(um|uh|erm|you know|i guess|like|sort of|kind of)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DeterministicFeatures:
    word_count: int
    duration_ms: int
    wpm: float
    filler_rate: float
    longest_pause_ms: int
    speech_ratio: float
    source: str  # "turn_metrics" (real, measured) or "text_fallback" (estimated - see below)

    @staticmethod
    def from_text_fallback(text: str, duration_ms: int) -> DeterministicFeatures:
        """Used only when no `turn_metrics` row exists for a turn — true for every synthetic
        and dev-fixture turn (no real audio pipeline ever ran for them) and for any turn from
        before Phase 1's instrumentation. wpm/filler_rate are estimated from text and an assumed
        duration, not measured; longest_pause_ms and speech_ratio have no text-only proxy and
        are reported as 0 / 1.0 rather than a fabricated guess (CLAUDE.md §10).
        """
        words = text.split()
        word_count = len(words)
        minutes = max(duration_ms, 1) / 60_000
        wpm = word_count / minutes if minutes > 0 else 0.0
        filler_count = len(_FILLER_WORDS.findall(text))
        filler_rate = filler_count / word_count if word_count > 0 else 0.0
        return DeterministicFeatures(
            word_count=word_count,
            duration_ms=duration_ms,
            wpm=wpm,
            filler_rate=filler_rate,
            longest_pause_ms=0,
            speech_ratio=1.0,
            source="text_fallback",
        )


@dataclass(frozen=True, slots=True)
class TrainingExample:
    turn_id: str
    session_id: str
    speaker_key: str
    split: str
    source: str
    question: str
    answer: str
    features: DeterministicFeatures
    # criterion_key -> mean human/annotator score. Turns with zero labels are still returned
    # (a caller may want to know they exist) but have an empty dict here.
    scores: dict[str, float] = field(default_factory=dict)


async def _preceding_persona_text(db: AsyncSession, session_id: object, index: int) -> str:
    result = await db.execute(
        select(Turn.text)
        .where(Turn.session_id == session_id, Turn.speaker == "persona", Turn.index < index)
        .order_by(Turn.index.desc())
        .limit(1)
    )
    text = result.scalar_one_or_none()
    return text or ""


async def load_examples(
    db: AsyncSession, *, dataset_revision_hash: str | None = None
) -> tuple[str, list[TrainingExample]]:
    """Returns (dataset_revision_hash, examples). Uses the latest revision when none is given."""
    if dataset_revision_hash is None:
        revision_result = await db.execute(
            select(DatasetRevision.hash).order_by(DatasetRevision.created_at.desc()).limit(1)
        )
        dataset_revision_hash = revision_result.scalar_one_or_none()
    if dataset_revision_hash is None:
        return "", []

    members_result = await db.execute(
        select(DatasetMember).where(DatasetMember.dataset_revision_hash == dataset_revision_hash)
    )
    members = list(members_result.scalars().all())
    if not members:
        return dataset_revision_hash, []

    turn_ids = [m.turn_id for m in members]
    turns_result = await db.execute(select(Turn).where(Turn.id.in_(turn_ids)))
    turns_by_id = {t.id: t for t in turns_result.scalars().all()}

    metrics_result = await db.execute(select(TurnMetrics).where(TurnMetrics.turn_id.in_(turn_ids)))
    metrics_by_turn_id = {m.turn_id: m for m in metrics_result.scalars().all()}

    annotations_result = await db.execute(
        select(Annotation.turn_id, Annotation.criterion_key, Annotation.score).where(
            Annotation.turn_id.in_(turn_ids)
        )
    )
    scores_by_turn: dict[object, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for turn_id, criterion_key, score in annotations_result.all():
        scores_by_turn[turn_id][criterion_key].append(score)

    examples: list[TrainingExample] = []
    for member in members:
        turn = turns_by_id.get(member.turn_id)
        if turn is None:
            continue  # deleted since the revision was built; skip rather than fail the load
        question = await _preceding_persona_text(db, member.session_id, turn.index)
        answer = turn.text_scrubbed or turn.text

        turn_metric = metrics_by_turn_id.get(member.turn_id)
        if turn_metric is not None:
            features = DeterministicFeatures(
                word_count=turn_metric.word_count,
                duration_ms=turn.end_ms - turn.start_ms,
                wpm=turn_metric.wpm,
                filler_rate=turn_metric.filler_rate,
                longest_pause_ms=turn_metric.longest_pause_ms,
                speech_ratio=turn_metric.speech_ratio,
                source="turn_metrics",
            )
        else:
            features = DeterministicFeatures.from_text_fallback(answer, turn.end_ms - turn.start_ms)

        criterion_scores = {
            key: sum(vals) / len(vals) for key, vals in scores_by_turn.get(turn.id, {}).items()
        }

        examples.append(
            TrainingExample(
                turn_id=str(member.turn_id),
                session_id=str(member.session_id),
                speaker_key=member.speaker_key,
                split=member.split,
                source=member.source,
                question=question,
                answer=answer,
                features=features,
                scores=criterion_scores,
            )
        )
    return dataset_revision_hash, examples


async def load_examples_standalone(
    dataset_revision_hash: str | None = None,
) -> tuple[str, list[TrainingExample]]:
    """Entry point for scripts that don't already hold an AsyncSession (train.py's CLI, eval
    harness's CLI)."""
    settings = get_training_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(engine) as db:
            return await load_examples(db, dataset_revision_hash=dataset_revision_hash)
    finally:
        await engine.dispose()
