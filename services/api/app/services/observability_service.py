"""Phase 6 TASK 6.1 — the observability page's read model.

Every percentile here is computed by Postgres over the raw rows (`percentile_cont`), never by
combining other percentiles. In particular the latency header reads `stage = 'e2e'` directly:
per-stage percentiles do not add (CLAUDE.md §8), and summing them would over-state the tail.
"""

from __future__ import annotations

import uuid as std_uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Select, and_, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import NotFoundError
from ..models import (
    LatencyEvent,
    ModelCall,
    Persona,
    Scenario,
    Session,
    Turn,
    TurnScore,
    User,
)
from ..models.observability import LATENCY_STAGES

E2E_TARGET_P95_MS = 1400.0
# Pipeline order, not alphabetical (TASK 6.1b). e2e is the header, not a stage in the stack.
PIPELINE_STAGES = tuple(s for s in LATENCY_STAGES if s != "e2e")
FRONTIER_PRICING_PATH = (
    Path(__file__).resolve().parents[4] / "content" / "pricing" / "frontier.yaml"
)


def _window_start(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _filtered_latency(
    stmt: Select[Any], *, days: int, family: str | None, host_class: str | None
) -> Select[Any]:
    stmt = stmt.where(LatencyEvent.created_at >= _window_start(days))
    if host_class:
        stmt = stmt.where(LatencyEvent.host_class == host_class)
    if family:
        stmt = (
            stmt.join(Session, Session.id == LatencyEvent.session_id)
            .join(Scenario, Scenario.id == Session.scenario_id)
            .where(Scenario.family == family)
        )
    return stmt


def _percentiles() -> list[Any]:
    d = LatencyEvent.duration_ms
    return [
        func.percentile_cont(0.5).within_group(d).label("p50"),
        func.percentile_cont(0.9).within_group(d).label("p90"),
        func.percentile_cont(0.95).within_group(d).label("p95"),
        func.count().label("n"),
    ]


async def latency_header(
    db: AsyncSession, *, days: int, family: str | None, host_class: str | None
) -> dict[str, Any]:
    overall_stmt = _filtered_latency(
        select(*_percentiles()).where(LatencyEvent.stage == "e2e"),
        days=days,
        family=family,
        host_class=host_class,
    )
    overall = (await db.execute(overall_stmt)).one()

    bucket = func.date_trunc("day", LatencyEvent.created_at).label("bucket")
    series_stmt = (
        _filtered_latency(
            select(bucket, *_percentiles()).where(LatencyEvent.stage == "e2e"),
            days=days,
            family=family,
            host_class=host_class,
        )
        .group_by(bucket)
        .order_by(bucket)
    )
    series = (await db.execute(series_stmt)).all()

    families = await db.execute(select(Scenario.family).distinct().order_by(Scenario.family))
    hosts = await db.execute(
        select(LatencyEvent.host_class).where(LatencyEvent.host_class.is_not(None)).distinct()
    )
    return {
        "target_p95_ms": E2E_TARGET_P95_MS,
        "overall": {"p50": overall.p50, "p90": overall.p90, "p95": overall.p95, "n": overall.n},
        "series": [
            {"bucket": r.bucket.isoformat(), "p50": r.p50, "p90": r.p90, "p95": r.p95, "n": r.n}
            for r in series
        ],
        "families": [f for (f,) in families.all()],
        "host_classes": sorted(h for (h,) in hosts.all()),
    }


async def stage_breakdown(
    db: AsyncSession, *, days: int, family: str | None, host_class: str | None
) -> list[dict[str, Any]]:
    stmt = _filtered_latency(
        select(LatencyEvent.stage, *_percentiles()).where(LatencyEvent.stage != "e2e"),
        days=days,
        family=family,
        host_class=host_class,
    ).group_by(LatencyEvent.stage)
    by_stage = {r.stage: r for r in (await db.execute(stmt)).all()}
    return [
        {
            "stage": stage,
            "p50": by_stage[stage].p50 if stage in by_stage else None,
            "p95": by_stage[stage].p95 if stage in by_stage else None,
            "n": by_stage[stage].n if stage in by_stage else 0,
        }
        for stage in PIPELINE_STAGES
    ]


async def recent_turns(db: AsyncSession, *, limit: int) -> list[dict[str, Any]]:
    """Turns that have an e2e measurement, slowest-first within the newest `limit` — the list
    the waterfall's turn picker draws from."""
    stmt = (
        select(
            LatencyEvent.turn_id,
            LatencyEvent.session_id,
            LatencyEvent.duration_ms,
            LatencyEvent.created_at,
        )
        .where(LatencyEvent.stage == "e2e")
        .order_by(desc(LatencyEvent.created_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "turn_id": str(r.turn_id),
            "session_id": str(r.session_id),
            "e2e_ms": r.duration_ms,
            "created_at": r.created_at.isoformat(),
        }
        for r in sorted(rows, key=lambda r: r.duration_ms, reverse=True)
    ]


def _model_call_out(c: ModelCall) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "session_id": str(c.session_id),
        "turn_id": str(c.turn_id) if c.turn_id else None,
        "role": c.role,
        "model": c.model,
        "prompt_version": c.prompt_version,
        "tokens_in": c.tokens_in,
        "tokens_out": c.tokens_out,
        "ttft_ms": c.ttft_ms,
        "total_latency_ms": c.total_latency_ms,
        "cost_cents": float(c.cost_cents),
        "cached": c.cached,
        "created_at": c.created_at.isoformat(),
    }


# Which model role, if any, a latency stage is attributable to (TASK 6.1c "click a stage -> see
# the associated model_calls row if any").
STAGE_MODEL_ROLE = {"endpoint_detect": "endpointer", "model_ttft": "persona"}


async def turn_waterfall(db: AsyncSession, turn_id: std_uuid.UUID) -> dict[str, Any]:
    events = (
        (await db.execute(select(LatencyEvent).where(LatencyEvent.turn_id == turn_id)))
        .scalars()
        .all()
    )
    if not events:
        raise NotFoundError("No latency events recorded for this turn.")
    session_id = events[0].session_id
    session = await db.get(Session, session_id)
    durations = {e.stage: e.duration_ms for e in events}

    user_turn = (
        await db.execute(select(Turn).where(Turn.session_id == session_id, Turn.id == turn_id))
    ).scalar_one_or_none()
    persona_turn = None
    if user_turn is not None:
        persona_turn = (
            await db.execute(
                select(Turn)
                .where(
                    Turn.session_id == session_id,
                    Turn.speaker == "persona",
                    Turn.index > user_turn.index,
                )
                .order_by(asc(Turn.index))
                .limit(1)
            )
        ).scalar_one_or_none()

    calls = (
        (
            await db.execute(
                select(ModelCall).where(
                    ModelCall.session_id == session_id,
                    (ModelCall.turn_id == turn_id)
                    | (ModelCall.turn_id == (persona_turn.id if persona_turn else turn_id)),
                )
            )
        )
        .scalars()
        .all()
    )
    calls_by_role: dict[str, list[dict[str, Any]]] = {}
    for c in calls:
        calls_by_role.setdefault(c.role, []).append(_model_call_out(c))

    voice_id = None
    if session is not None:
        scenario = await db.get(Scenario, session.scenario_id)
        if scenario is not None and scenario.persona_id is not None:
            persona = await db.get(Persona, scenario.persona_id)
            voice_id = persona.voice_id if persona else None

    return {
        "turn_id": str(turn_id),
        "session_id": str(session_id),
        "e2e_ms": durations.get("e2e"),
        "stages": [
            {
                "stage": stage,
                "duration_ms": durations.get(stage),
                "model_calls": calls_by_role.get(STAGE_MODEL_ROLE.get(stage, ""), []),
            }
            for stage in PIPELINE_STAGES
        ],
        "all_model_calls": [_model_call_out(c) for c in calls],
        "user_text": user_turn.text if user_turn else None,
        "user_start_ms": user_turn.start_ms if user_turn else None,
        "user_end_ms": user_turn.end_ms if user_turn else None,
        "persona_turn_id": str(persona_turn.id) if persona_turn else None,
        "persona_text": persona_turn.text if persona_turn else None,
        "persona_voice_id": voice_id,
        "recording_available": bool(session and session.recording_key),
    }


MODEL_CALL_SORTS = {
    "created_at": ModelCall.created_at,
    "total_latency_ms": ModelCall.total_latency_ms,
    "ttft_ms": ModelCall.ttft_ms,
    "cost_cents": ModelCall.cost_cents,
    "tokens_in": ModelCall.tokens_in,
    "tokens_out": ModelCall.tokens_out,
}


async def list_model_calls(
    db: AsyncSession,
    *,
    role: str | None,
    model: str | None,
    cached: bool | None,
    prompt_version: str | None,
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    conditions = []
    if role:
        conditions.append(ModelCall.role == role)
    if model:
        conditions.append(ModelCall.model.ilike(f"%{model}%"))
    if cached is not None:
        conditions.append(ModelCall.cached.is_(cached))
    if prompt_version:
        conditions.append(ModelCall.prompt_version == prompt_version)
    where = and_(*conditions) if conditions else None

    column = MODEL_CALL_SORTS.get(sort, ModelCall.created_at)
    stmt = select(ModelCall)
    count_stmt = select(func.count()).select_from(ModelCall)
    cache_stmt = select(ModelCall.cached, func.count()).group_by(ModelCall.cached)
    if where is not None:
        stmt, count_stmt, cache_stmt = (
            stmt.where(where),
            count_stmt.where(where),
            cache_stmt.where(where),
        )
    stmt = (
        stmt.order_by(desc(column) if order == "desc" else asc(column)).limit(limit).offset(offset)
    )

    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()
    cache_counts = {bool(k): v for k, v in (await db.execute(cache_stmt)).all()}
    return {
        "items": [_model_call_out(c) for c in rows],
        "total": total,
        "cache_hits": cache_counts.get(True, 0),
        "cache_misses": cache_counts.get(False, 0),
    }


def load_frontier_pricing(path: Path = FRONTIER_PRICING_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


def counterfactual_cents(
    *,
    turn_scores: int,
    mean_tokens_in: float | None,
    mean_tokens_out: float | None,
    pricing: dict[str, Any],
) -> float | None:
    """TASK 6.1e: every turn_score priced as if a frontier model had produced it. Token counts
    per scoring call are the *measured* means from this deployment's own scorer calls — if none
    were ever recorded the counterfactual is unknown (`None`), never an estimate."""
    if mean_tokens_in is None or mean_tokens_out is None:
        return None
    per_call_usd = (
        mean_tokens_in * pricing["input_usd_per_mtok"]
        + mean_tokens_out * pricing["output_usd_per_mtok"]
    ) / 1_000_000
    return float(turn_scores * per_call_usd * 100)


async def cost_panel(db: AsyncSession) -> dict[str, Any]:
    pricing = load_frontier_pricing()
    month = func.date_trunc("month", ModelCall.created_at).label("month")

    per_month = (
        await db.execute(
            select(month, func.sum(ModelCall.cost_cents)).group_by(month).order_by(month)
        )
    ).all()
    per_session = (
        await db.execute(
            select(ModelCall.session_id, func.sum(ModelCall.cost_cents).label("c"))
            .group_by(ModelCall.session_id)
            .order_by(desc("c"))
            .limit(20)
        )
    ).all()
    per_user = (
        await db.execute(
            select(User.email, func.sum(ModelCall.cost_cents).label("c"))
            .join(Session, Session.id == ModelCall.session_id)
            .join(User, User.id == Session.user_id)
            .group_by(User.email)
            .order_by(desc("c"))
            .limit(20)
        )
    ).all()

    actual_total = float(
        (await db.execute(select(func.coalesce(func.sum(ModelCall.cost_cents), 0)))).scalar_one()
    )
    scoring_actual = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(ModelCall.cost_cents), 0)).where(
                    ModelCall.role == "judge"
                )
            )
        ).scalar_one()
    )
    n_scores = (await db.execute(select(func.count()).select_from(TurnScore))).scalar_one()
    means = (
        await db.execute(
            select(func.avg(ModelCall.tokens_in), func.avg(ModelCall.tokens_out)).where(
                ModelCall.role == "judge"
            )
        )
    ).one()
    counterfactual = counterfactual_cents(
        turn_scores=n_scores,
        mean_tokens_in=float(means[0]) if means[0] is not None else None,
        mean_tokens_out=float(means[1]) if means[1] is not None else None,
        pricing=pricing,
    )
    ratio = (
        counterfactual / scoring_actual
        if counterfactual is not None and scoring_actual > 0
        else None
    )
    return {
        "actual_total_cents": actual_total,
        "scoring_actual_cents": scoring_actual,
        "turn_scores": n_scores,
        "counterfactual_cents": counterfactual,
        "ratio": ratio,
        "frontier": {
            "model": pricing["model"],
            "input_usd_per_mtok": pricing["input_usd_per_mtok"],
            "output_usd_per_mtok": pricing["output_usd_per_mtok"],
            "as_of": str(pricing["as_of"]),
        },
        "per_month": [{"month": m.isoformat(), "cents": float(c or 0)} for m, c in per_month],
        "per_session": [{"session_id": str(s), "cents": float(c or 0)} for s, c in per_session],
        "per_user": [{"user": e, "cents": float(c or 0)} for e, c in per_user],
    }
