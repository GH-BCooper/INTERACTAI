"""Phase 6 TASK 6.2 — the evaluations page's read model.

The per-case grid and the comparison view are computed from the tables that already hold the
truth — `annotations` (human labels), `turn_scores` (the live scorer) and `shadow_scores` (any
candidate scored in shadow) — never from a cached copy that could drift from them.
"""

from __future__ import annotations

import uuid as std_uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Annotation,
    DeploymentEvent,
    EvalRun,
    ModelVersion,
    ShadowScore,
    Turn,
    TurnScore,
)


def _version_out(v: ModelVersion) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "role": v.role,
        "name": v.name,
        "base_model": v.base_model,
        "adapter_key": v.adapter_key,
        "dataset_revision_hash": v.dataset_revision_hash,
        "metrics": v.metrics,
        "status": v.status,
        "seed_count": v.seed_count,
        "created_at": v.created_at.isoformat(),
    }


async def list_versions(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        (
            await db.execute(
                select(ModelVersion).order_by(ModelVersion.role, desc(ModelVersion.created_at))
            )
        )
        .scalars()
        .all()
    )
    return [_version_out(v) for v in rows]


def _run_out(r: EvalRun) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "suite": r.suite,
        "configuration": r.configuration,
        "model_version_id": str(r.model_version_id) if r.model_version_id else None,
        "prompt_version": r.prompt_version,
        "qwk": r.qwk,
        "mae": r.mae,
        "spearman": r.spearman,
        "adjacent_accuracy": r.adjacent_accuracy,
        "ece": r.ece,
        "mean_cost_cents": r.mean_cost_cents,
        "mean_latency_ms": r.mean_latency_ms,
        "metrics": r.metrics,
        "host_class": r.host_class,
        "dataset_revision_hash": r.dataset_revision_hash,
        "split": r.split,
        "published": r.published,
        "created_at": r.created_at.isoformat(),
    }


async def list_runs(db: AsyncSession, *, suite: str | None, limit: int) -> list[dict[str, Any]]:
    stmt = select(EvalRun).order_by(desc(EvalRun.created_at)).limit(limit)
    if suite:
        stmt = stmt.where(EvalRun.suite == suite)
    return [_run_out(r) for r in (await db.execute(stmt)).scalars().all()]


async def regression_series(db: AsyncSession) -> dict[str, Any]:
    runs = (await db.execute(select(EvalRun).order_by(asc(EvalRun.created_at)))).scalars().all()
    markers = (
        (await db.execute(select(DeploymentEvent).order_by(asc(DeploymentEvent.created_at))))
        .scalars()
        .all()
    )
    return {
        "runs": [_run_out(r) for r in runs],
        "deployments": [
            {
                "id": str(m.id),
                "kind": m.kind,
                "label": m.label,
                "created_at": m.created_at.isoformat(),
            }
            for m in markers
        ],
    }


async def per_case_grid(
    db: AsyncSession, *, model_version: str | None, limit: int
) -> dict[str, Any]:
    """One row per (turn, criterion) that has at least one human label and a model score.
    `disagreement` = |model score - mean human label|; default order is that, descending — the
    interesting cases first (TASK 6.2)."""
    human = (
        select(
            Annotation.turn_id,
            Annotation.criterion_key,
            func.avg(Annotation.score).label("human_mean"),
            func.array_agg(Annotation.score).label("human_scores"),
        )
        .group_by(Annotation.turn_id, Annotation.criterion_key)
        .subquery()
    )
    stmt = (
        select(
            TurnScore.session_id,
            TurnScore.turn_id,
            TurnScore.criterion_key,
            TurnScore.score,
            TurnScore.confidence,
            TurnScore.model_version,
            human.c.human_mean,
            human.c.human_scores,
            func.abs(TurnScore.score - human.c.human_mean).label("disagreement"),
        )
        .join(
            human,
            (human.c.turn_id == TurnScore.turn_id)
            & (human.c.criterion_key == TurnScore.criterion_key),
        )
        .where(TurnScore.score.is_not(None))
        .order_by(desc("disagreement"))
        .limit(limit)
    )
    if model_version:
        stmt = stmt.where(TurnScore.model_version == model_version)
    rows = (await db.execute(stmt)).all()
    turn_ids = {r.turn_id for r in rows}
    texts: dict[std_uuid.UUID, str] = {}
    if turn_ids:
        for tid, text in (
            await db.execute(select(Turn.id, Turn.text).where(Turn.id.in_(turn_ids)))
        ).all():
            texts[tid] = text
    return {
        "items": [
            {
                "session_id": str(r.session_id),
                "turn_id": str(r.turn_id),
                "criterion_key": r.criterion_key,
                "model_score": r.score,
                "confidence": r.confidence,
                "model_version": r.model_version,
                "human_mean": float(r.human_mean),
                "human_scores": list(r.human_scores),
                "disagreement": float(r.disagreement),
                "turn_text": texts.get(r.turn_id),
            }
            for r in rows
        ]
    }


async def score_versions(db: AsyncSession) -> list[str]:
    live = (await db.execute(select(TurnScore.model_version).distinct())).scalars().all()
    shadow = (await db.execute(select(ShadowScore.model_version).distinct())).scalars().all()
    return sorted(set(live) | set(shadow))


async def compare_versions(
    db: AsyncSession, *, version_a: str, version_b: str, limit: int
) -> dict[str, Any]:
    """Two scorer versions over identical (turn, criterion) cases. A version's scores may live
    in `turn_scores` (it was live) or `shadow_scores` (it ran in shadow) — both are read. Rows
    where the two disagree come first, largest gap first."""

    async def scores_for(version: str) -> dict[tuple[std_uuid.UUID, str], int | None]:
        out: dict[tuple[std_uuid.UUID, str], int | None] = {}
        for model in (TurnScore, ShadowScore):
            rows = await db.execute(
                select(model.turn_id, model.criterion_key, model.score).where(
                    model.model_version == version
                )
            )
            for tid, key, score in rows.all():
                out[(tid, key)] = score
        return out

    a, b = await scores_for(version_a), await scores_for(version_b)
    shared = set(a) & set(b)
    items: list[dict[str, Any]] = []
    for tid, key in shared:
        sa, sb = a[(tid, key)], b[(tid, key)]
        items.append(
            {
                "turn_id": str(tid),
                "criterion_key": key,
                "score_a": sa,
                "score_b": sb,
                "gap": abs(sa - sb) if sa is not None and sb is not None else None,
                # A null on exactly one side (one abstained below the confidence threshold) is a
                # disagreement too.
                "disagrees": sa != sb,
            }
        )
    items.sort(key=lambda i: (not i["disagrees"], -(i["gap"] or 0)))
    by_criterion: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    disagreements = 0
    for i in items:
        counts = by_criterion[str(i["criterion_key"])]
        counts[0] += 1
        if i["disagrees"]:
            counts[1] += 1
            disagreements += 1
    return {
        "version_a": version_a,
        "version_b": version_b,
        "shared_cases": len(items),
        "disagreements": disagreements,
        "per_criterion": {
            k: {"cases": v[0], "disagreements": v[1]} for k, v in by_criterion.items()
        },
        "items": items[:limit],
    }


async def speech_panel(db: AsyncSession) -> list[dict[str, Any]]:
    """Latest Level 1 run per host class (TASK 6.2 speech component panel)."""
    runs = (
        (
            await db.execute(
                select(EvalRun).where(EvalRun.suite == "speech").order_by(desc(EvalRun.created_at))
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, EvalRun] = {}
    for r in runs:
        latest.setdefault(r.host_class or "unspecified", r)
    return [_run_out(r) for r in latest.values()]
