"""Repository functions — no raw SQL at call sites (CLAUDE.md §5), only these.

`upsert_turn_score`/`upsert_session_score`/`upsert_report` are the idempotency Task 2.2d/2.5
require ("Running score_turn twice produces one row, not two"). They target the actual DB
UniqueConstraints from the Phase 0 migration — `turn_scores` is unique on
`(turn_id, criterion_key)` and `session_scores` on `(session_id, criterion_key)`, NOT
`(turn_id, criterion_key, model_version)` as Task 2.5b's prose literally says. Postgres'
`ON CONFLICT` target must match an existing constraint exactly, and widening a Phase 0 table's
constraint for this is unnecessary: there is only ever one *current* score per turn+criterion by
design (a rescore with a new `model_version` should replace the old score, not coexist with it),
so upserting on the narrower, already-frozen key is both correct and idempotent for the actual
requirement — re-running `score_turn` with the *same* model_version is trivially a no-op-shaped
overwrite, which is what "produces one row, not two" asks for.
"""

from __future__ import annotations

import uuid as std_uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.ids import uuid7
from .tables import (
    failed_jobs,
    model_calls,
    reports,
    rubric_criteria,
    rubrics,
    scenarios,
    session_scores,
    sessions,
    shadow_scores,
    turn_metrics,
    turn_scores,
    turns,
)


async def get_session(db: AsyncSession, session_id: std_uuid.UUID) -> dict[str, Any] | None:
    result = await db.execute(select(sessions).where(sessions.c.id == session_id))
    row = result.mappings().first()
    return dict(row) if row is not None else None


async def get_turn(db: AsyncSession, turn_id: std_uuid.UUID) -> dict[str, Any] | None:
    result = await db.execute(select(turns).where(turns.c.id == turn_id))
    row = result.mappings().first()
    return dict(row) if row is not None else None


async def get_turns_for_session(
    db: AsyncSession, session_id: std_uuid.UUID
) -> list[dict[str, Any]]:
    """Ordered by `(index, created_at)`, not `index` alone: the user turn and the persona reply
    for one exchange share the same `index` (services/realtime/app/turn.py persists both with
    `index=turn_index`), so `created_at` is the only thing that orders them relative to each
    other — the user turn is always written first."""
    result = await db.execute(
        select(turns)
        .where(turns.c.session_id == session_id)
        .order_by(turns.c.index, turns.c.created_at)
    )
    return [dict(row) for row in result.mappings().all()]


async def get_turn_metrics(db: AsyncSession, turn_id: std_uuid.UUID) -> dict[str, Any] | None:
    result = await db.execute(select(turn_metrics).where(turn_metrics.c.turn_id == turn_id))
    row = result.mappings().first()
    return dict(row) if row is not None else None


async def get_rubric(db: AsyncSession, rubric_id: std_uuid.UUID) -> dict[str, Any] | None:
    result = await db.execute(select(rubrics).where(rubrics.c.id == rubric_id))
    row = result.mappings().first()
    return dict(row) if row is not None else None


async def get_rubric_criteria(
    db: AsyncSession, rubric_id: std_uuid.UUID
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(rubric_criteria)
        .where(rubric_criteria.c.rubric_id == rubric_id)
        .order_by(rubric_criteria.c.display_order)
    )
    return [dict(row) for row in result.mappings().all()]


async def upsert_turn_score(
    db: AsyncSession,
    *,
    session_id: std_uuid.UUID,
    turn_id: std_uuid.UUID,
    criterion_key: str,
    score: int | None,
    confidence: float,
    evidence_spans: list[dict[str, int]],
    model_version: str,
    rationale: str | None,
) -> None:
    now = datetime.now(UTC)
    stmt = insert(turn_scores).values(
        id=uuid7(),
        created_at=now,
        updated_at=now,
        session_id=session_id,
        turn_id=turn_id,
        criterion_key=criterion_key,
        score=score,
        confidence=confidence,
        evidence_spans=evidence_spans,
        model_version=model_version,
        rationale=rationale,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[turn_scores.c.turn_id, turn_scores.c.criterion_key],
        set_={
            "score": stmt.excluded.score,
            "confidence": stmt.excluded.confidence,
            "evidence_spans": stmt.excluded.evidence_spans,
            "model_version": stmt.excluded.model_version,
            "rationale": stmt.excluded.rationale,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    await db.commit()


async def insert_shadow_score(
    db: AsyncSession,
    *,
    session_id: std_uuid.UUID,
    turn_id: std_uuid.UUID,
    criterion_key: str,
    score: int | None,
    confidence: float,
    model_version: str,
) -> None:
    """docs/phase-5-BUILD.md TASK 5.5d — see shadow_scores' unique constraint
    (turn_id, criterion_key, model_version): unlike turn_scores, a shadow score genuinely does
    coexist across model_versions, since the whole point is comparing them over time. Idempotent
    per (turn, criterion, model_version) — a retried job overwrites its own prior attempt rather
    than accumulating duplicates.
    """
    now = datetime.now(UTC)
    stmt = insert(shadow_scores).values(
        id=uuid7(),
        created_at=now,
        updated_at=now,
        session_id=session_id,
        turn_id=turn_id,
        criterion_key=criterion_key,
        score=score,
        confidence=confidence,
        model_version=model_version,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            shadow_scores.c.turn_id,
            shadow_scores.c.criterion_key,
            shadow_scores.c.model_version,
        ],
        set_={
            "score": stmt.excluded.score,
            "confidence": stmt.excluded.confidence,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    await db.commit()


async def get_turn_scores_for_session(
    db: AsyncSession, session_id: std_uuid.UUID
) -> list[dict[str, Any]]:
    result = await db.execute(select(turn_scores).where(turn_scores.c.session_id == session_id))
    return [dict(row) for row in result.mappings().all()]


async def upsert_session_score(
    db: AsyncSession,
    *,
    session_id: std_uuid.UUID,
    criterion_key: str,
    aggregate_score: float | None,
    confidence: float,
    evidence_turn_ids: list[str],
    model_version: str,
    percentile_vs_self: float | None,
) -> None:
    now = datetime.now(UTC)
    stmt = insert(session_scores).values(
        id=uuid7(),
        created_at=now,
        updated_at=now,
        session_id=session_id,
        criterion_key=criterion_key,
        aggregate_score=aggregate_score,
        confidence=confidence,
        evidence_turn_ids=evidence_turn_ids,
        model_version=model_version,
        percentile_vs_self=percentile_vs_self,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[session_scores.c.session_id, session_scores.c.criterion_key],
        set_={
            "aggregate_score": stmt.excluded.aggregate_score,
            "confidence": stmt.excluded.confidence,
            "evidence_turn_ids": stmt.excluded.evidence_turn_ids,
            "model_version": stmt.excluded.model_version,
            "percentile_vs_self": stmt.excluded.percentile_vs_self,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    await db.commit()


async def set_turns_scrubbed_text(db: AsyncSession, scrubbed_by_turn_id: dict[str, str]) -> None:
    """Task 4.5b: writes `turns.text_scrubbed` for every turn in one session, in one
    executemany-shaped batch. Never touches `text` — the unscrubbed original every other report/
    replay/evidence-span surface reads stays exactly as it was."""
    if not scrubbed_by_turn_id:
        return
    now = datetime.now(UTC)
    for turn_id_str, scrubbed_text in scrubbed_by_turn_id.items():
        await db.execute(
            turns.update()
            .where(turns.c.id == std_uuid.UUID(turn_id_str))
            .values(text_scrubbed=scrubbed_text, updated_at=now)
        )
    await db.commit()


async def get_scenario_family(db: AsyncSession, scenario_id: std_uuid.UUID) -> str | None:
    result = await db.execute(select(scenarios.c.family).where(scenarios.c.id == scenario_id))
    row = result.first()
    return str(row[0]) if row is not None else None


async def get_past_session_scores_for_family(
    db: AsyncSession,
    *,
    user_id: std_uuid.UUID,
    family: str,
    criterion_key: str,
    exclude_session_id: std_uuid.UUID,
) -> list[float]:
    """Task 2.5f: `percentile_vs_self` — "computed against the user's own history for the same
    scenario family." Joins through `sessions.scenario_id` -> `scenarios.family`."""
    result = await db.execute(
        select(session_scores.c.aggregate_score)
        .join(sessions, sessions.c.id == session_scores.c.session_id)
        .join(scenarios, scenarios.c.id == sessions.c.scenario_id)
        .where(
            sessions.c.user_id == user_id,
            scenarios.c.family == family,
            session_scores.c.criterion_key == criterion_key,
            session_scores.c.session_id != exclude_session_id,
            session_scores.c.aggregate_score.is_not(None),
        )
    )
    return [float(row[0]) for row in result.all()]


async def upsert_report(
    db: AsyncSession,
    *,
    session_id: std_uuid.UUID,
    status: str,
    summary: str | None,
    strengths: list[str],
    growth_areas: list[str],
    next_actions: list[dict[str, Any]],
    highlight_turn_id: std_uuid.UUID | None,
    lowlight_turn_id: std_uuid.UUID | None,
    low_sample_size: bool,
    narrator_model_version: str | None,
    generated_at: datetime | None,
) -> None:
    now = datetime.now(UTC)
    stmt = insert(reports).values(
        id=uuid7(),
        created_at=now,
        updated_at=now,
        session_id=session_id,
        status=status,
        summary=summary,
        strengths=strengths,
        growth_areas=growth_areas,
        next_actions=next_actions,
        highlight_turn_id=highlight_turn_id,
        lowlight_turn_id=lowlight_turn_id,
        low_sample_size=low_sample_size,
        narrator_model_version=narrator_model_version,
        generated_at=generated_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[reports.c.session_id],
        set_={
            "status": stmt.excluded.status,
            "summary": stmt.excluded.summary,
            "strengths": stmt.excluded.strengths,
            "growth_areas": stmt.excluded.growth_areas,
            "next_actions": stmt.excluded.next_actions,
            "highlight_turn_id": stmt.excluded.highlight_turn_id,
            "lowlight_turn_id": stmt.excluded.lowlight_turn_id,
            "low_sample_size": stmt.excluded.low_sample_size,
            "narrator_model_version": stmt.excluded.narrator_model_version,
            "generated_at": stmt.excluded.generated_at,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    await db.commit()


async def insert_model_call(
    db: AsyncSession,
    *,
    session_id: std_uuid.UUID,
    turn_id: std_uuid.UUID | None,
    role: str,
    model: str,
    prompt_version: str | None,
    tokens_in: int,
    tokens_out: int,
    ttft_ms: float | None,
    total_latency_ms: float,
    cost_cents: float,
    cached: bool,
) -> None:
    now = datetime.now(UTC)
    await db.execute(
        model_calls.insert().values(
            id=uuid7(),
            created_at=now,
            updated_at=now,
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            model=model,
            prompt_version=prompt_version,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            ttft_ms=ttft_ms,
            total_latency_ms=total_latency_ms,
            cost_cents=cost_cents,
            cached=cached,
        )
    )
    await db.commit()


async def insert_failed_job(
    db: AsyncSession,
    *,
    session_id: std_uuid.UUID,
    turn_id: std_uuid.UUID | None,
    job_name: str,
    payload: dict[str, Any],
    error: str,
    attempts: int,
) -> None:
    now = datetime.now(UTC)
    await db.execute(
        failed_jobs.insert().values(
            id=uuid7(),
            created_at=now,
            updated_at=now,
            session_id=session_id,
            turn_id=turn_id,
            job_name=job_name,
            payload=payload,
            error=error,
            attempts=attempts,
        )
    )
    await db.commit()
