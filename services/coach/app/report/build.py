"""The two ARQ job bodies (docs/phase-2-BUILD.md TASK 2.2d/2.5): `score_turn` and
`generate_report`. Thin orchestration — every piece of actual logic (deterministic metrics,
evidence verification, aggregation, narrative post-checks) lives in its own pure-function
module and is unit-tested there; this module wires DB reads/writes around those calls.
"""

from __future__ import annotations

import uuid as std_uuid
from datetime import UTC, datetime
from typing import Any

from ..core.config import get_settings
from ..core.logging import get_logger
from ..db.repository import (
    get_past_session_scores_for_family,
    get_rubric,
    get_rubric_criteria,
    get_scenario_family,
    get_session,
    get_turn,
    get_turn_metrics,
    get_turn_scores_for_session,
    get_turns_for_session,
    insert_model_call,
    upsert_report,
    upsert_session_score,
    upsert_turn_score,
)
from ..db.session import get_sessionmaker
from ..deterministic.metrics import (
    DELIVERY_CRITERION_KEY,
    DELIVERY_MODEL_VERSION,
    compute_delivery_score,
)
from ..narrator.narrator import CriterionForNarrative, generate_narrative
from ..scorer import RubricCriterion, get_scorer
from .aggregation import (
    aggregate_criterion,
    gate_score,
    percentile_vs_self,
    pick_highlight_and_lowlight,
)

logger = get_logger(__name__)

LOW_SAMPLE_SIZE_THRESHOLD = 3  # Task 2.5's own example: "Session has 2 turns"
GENERATE_REPORT_MAX_WAIT_ATTEMPTS = 12  # ~60s at the 5s defer below
GENERATE_REPORT_DEFER_S = 5


def _find_preceding_question(
    turns: list[dict[str, Any]], user_turn: dict[str, Any], fallback: str
) -> str:
    """The "question" a user turn is answering is the most recent persona turn strictly before
    it — turns from the same exchange share an `index` (see `get_turns_for_session`'s
    docstring), so this is never the same-index persona reply, which comes *after*. `fallback`
    (the scenario's `opening_strategy`) covers the first exchange, before any persona turn has
    been persisted — Task 2.3f's scripted opening will change this once it exists."""
    candidates = [
        t
        for t in turns
        if t["speaker"] == "persona" and int(t["index"]) < int(user_turn["index"])
    ]
    if not candidates:
        return fallback
    best = max(candidates, key=lambda t: (int(t["index"]), t["created_at"]))
    return str(best["text"])


async def score_turn(ctx: dict[str, Any], *, session_id: str, turn_id: str) -> None:
    """Task 2.2d/2.5a-d. Off the latency path entirely (CLAUDE.md §2) — this only ever runs in
    the ARQ worker process, never in services/realtime."""
    del ctx
    settings = get_settings()
    sid, tid = std_uuid.UUID(session_id), std_uuid.UUID(turn_id)
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as db:
        turn = await get_turn(db, tid)
        session = await get_session(db, sid)
        metrics_row = await get_turn_metrics(db, tid)
        rubric_id_raw = (session or {}).get("brief", {}).get("rubric_id") if session else None
        criteria_rows = (
            await get_rubric_criteria(db, std_uuid.UUID(rubric_id_raw)) if rubric_id_raw else []
        )
        all_turns = await get_turns_for_session(db, sid) if session else []

    if turn is None or session is None or turn["speaker"] != "user":
        logger.warning(
            "score_turn_skipped_no_turn_or_session", session_id=session_id, turn_id=turn_id
        )
        return

    # Task 2.5a: deterministic delivery score, before any model call, always (if metrics exist).
    if metrics_row is not None:
        delivery = compute_delivery_score(metrics_row)
        async with sessionmaker() as db:
            await upsert_turn_score(
                db,
                session_id=sid,
                turn_id=tid,
                criterion_key=DELIVERY_CRITERION_KEY,
                # turn_scores.score is Integer (matches the rubric's 1-5 anchor scale); the
                # exact fractional delivery score (e.g. 3.25) is rounded to the nearest point
                # for storage, same as every rubric criterion's score already is.
                score=round(delivery.score),
                confidence=1.0,
                evidence_spans=[],
                model_version=DELIVERY_MODEL_VERSION,
                rationale=None,
            )

    if not criteria_rows:
        logger.info("score_turn_no_rubric_criteria", session_id=session_id, turn_id=turn_id)
        return

    criteria = [
        RubricCriterion(
            key=r["key"],
            name=r["name"],
            description=r["description"],
            anchor_descriptors=r["anchor_descriptors"],
        )
        for r in criteria_rows
    ]
    opening_strategy = str(session.get("brief", {}).get("opening_strategy", ""))
    question = _find_preceding_question(all_turns, turn, fallback=opening_strategy)
    answer = str(turn["text"])

    scorer = get_scorer()
    results = await scorer.score_batch(question, answer, criteria)

    asr_confidence = turn.get("asr_confidence")
    async with sessionmaker() as db:
        for criterion, result in zip(criteria, results, strict=True):
            confidence = result.confidence
            if asr_confidence is not None:
                # Task 2.5's edge case: "ASR confidence was low for a turn -> Propagate: cap
                # scoring confidence at the ASR confidence." A misheard answer can't earn a more
                # confident score than the transcript itself deserves.
                confidence = min(confidence, float(asr_confidence))
            gated_score, _is_gated = gate_score(
                result.score, confidence, settings.confidence_threshold
            )
            evidence_spans = [{"start": s.start, "end": s.end} for s in result.evidence_spans]
            await upsert_turn_score(
                db,
                session_id=sid,
                turn_id=tid,
                criterion_key=criterion.key,
                score=round(gated_score) if gated_score is not None else None,
                confidence=confidence,
                evidence_spans=evidence_spans,
                model_version=scorer.version,
                rationale=result.rationale,
            )

        stats = getattr(scorer, "last_call_stats", None)
        model_name = getattr(scorer, "model", scorer.version)
        if stats is not None:
            await insert_model_call(
                db,
                session_id=sid,
                turn_id=tid,
                role="judge",
                model=model_name,
                prompt_version=scorer.version,
                tokens_in=stats.tokens_in,
                tokens_out=stats.tokens_out,
                ttft_ms=None,
                total_latency_ms=stats.total_latency_ms,
                cost_cents=stats.cost_cents,
                cached=stats.cached,
            )

    logger.info(
        "score_turn_complete",
        session_id=session_id,
        turn_id=turn_id,
        criteria_scored=len(criteria),
    )


async def generate_report(ctx: dict[str, Any], *, session_id: str, wait_attempt: int = 0) -> None:
    """Task 2.2d/2.5e-g. `wait_attempt` implements "a dependency on all outstanding score_turn
    jobs for that session" (Task 2.2d) as consumer-side polling: if any answered turn is missing
    its scores yet, this re-enqueues itself a bounded number of times rather than either racing
    ahead with partial data immediately or waiting forever on a job that may never arrive."""
    settings = get_settings()
    sid = std_uuid.UUID(session_id)
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as db:
        session = await get_session(db, sid)
        if session is None:
            logger.warning("generate_report_session_not_found", session_id=session_id)
            return
        turns = await get_turns_for_session(db, sid)
        existing_scores = await get_turn_scores_for_session(db, sid)

    user_turns = [t for t in turns if t["speaker"] == "user" and str(t["text"]).strip()]
    scored_turn_ids = {str(r["turn_id"]) for r in existing_scores}
    unscored = [t for t in user_turns if str(t["id"]) not in scored_turn_ids]

    if unscored and wait_attempt < GENERATE_REPORT_MAX_WAIT_ATTEMPTS:
        redis = ctx.get("redis")
        if redis is not None:
            await redis.enqueue_job(
                "generate_report",
                session_id=session_id,
                wait_attempt=wait_attempt + 1,
                _defer_by=GENERATE_REPORT_DEFER_S,
            )
            return

    all_truncated = bool(user_turns) and all(bool(t["truncated"]) for t in user_turns)
    low_sample_size = len(user_turns) < LOW_SAMPLE_SIZE_THRESHOLD

    rubric_id_raw = session.get("brief", {}).get("rubric_id")
    rubric_slug = session.get("brief", {}).get("rubric_slug", "")

    if all_truncated or rubric_id_raw is None:
        async with sessionmaker() as db:
            await upsert_report(
                db,
                session_id=sid,
                status="ready",
                summary=(
                    "This session ended before any complete answers were captured, so there is "
                    "nothing to score. Try again when you can finish a full session."
                    if all_truncated
                    else "This scenario has no rubric configured, so this session cannot be scored."
                ),
                strengths=[],
                growth_areas=[],
                next_actions=[],
                highlight_turn_id=None,
                lowlight_turn_id=None,
                low_sample_size=low_sample_size,
                narrator_model_version=None,
                generated_at=datetime.now(UTC),
            )
        logger.info(
            "generate_report_degenerate_session",
            session_id=session_id,
            all_truncated=all_truncated,
        )
        return

    async with sessionmaker() as db:
        rubric = await get_rubric(db, std_uuid.UUID(rubric_id_raw))
        criteria_rows = await get_rubric_criteria(db, std_uuid.UUID(rubric_id_raw))
        all_turn_scores = await get_turn_scores_for_session(db, sid)
        family = await get_scenario_family(db, std_uuid.UUID(str(session["scenario_id"])))

    policy = (rubric or {}).get("aggregation_policy", {}) or {}
    min_turns_with_signal = int(policy.get("min_turns_with_signal", 2))

    criterion_keys = [r["key"] for r in criteria_rows] + [DELIVERY_CRITERION_KEY]
    criteria_for_narrative: list[CriterionForNarrative] = []
    async with sessionmaker() as db:
        for key in criterion_keys:
            rows_for_key = [r for r in all_turn_scores if r["criterion_key"] == key]
            aggregate = aggregate_criterion(
                key,
                rows_for_key,
                confidence_threshold=settings.confidence_threshold,
                min_turns_with_signal=min_turns_with_signal,
            )
            past_scores: list[float] = []
            if aggregate.aggregate_score is not None and family is not None:
                past_scores = await get_past_session_scores_for_family(
                    db,
                    user_id=std_uuid.UUID(str(session["user_id"])),
                    family=family,
                    criterion_key=key,
                    exclude_session_id=sid,
                )
            pct = (
                percentile_vs_self(aggregate.aggregate_score, past_scores)
                if aggregate.aggregate_score is not None
                else None
            )
            if key == DELIVERY_CRITERION_KEY:
                score_model_version = DELIVERY_MODEL_VERSION
            elif rows_for_key:
                score_model_version = str(rows_for_key[0]["model_version"])
            else:
                score_model_version = "none"
            await upsert_session_score(
                db,
                session_id=sid,
                criterion_key=key,
                aggregate_score=aggregate.aggregate_score,
                confidence=aggregate.confidence,
                evidence_turn_ids=aggregate.evidence_turn_ids,
                model_version=score_model_version,
                percentile_vs_self=pct,
            )

            name = next((r["name"] for r in criteria_rows if r["key"] == key), "Delivery")
            evidence_quotes = []
            if rows_for_key:
                best_row = max(rows_for_key, key=lambda r: float(r["confidence"]))
                best_turn_id = str(best_row["turn_id"])
                turn_text = next((t["text"] for t in turns if str(t["id"]) == best_turn_id), "")
                evidence_quotes = [
                    str(turn_text)[span["start"] : span["end"]]
                    for span in best_row["evidence_spans"]
                ]
            criteria_for_narrative.append(
                CriterionForNarrative(
                    key=key,
                    name=name,
                    score=aggregate.aggregate_score,
                    evidence_quotes=evidence_quotes,
                )
            )

    highlight_turn_id, lowlight_turn_id = pick_highlight_and_lowlight(
        all_turn_scores, confidence_threshold=settings.confidence_threshold
    )
    highlight_text = next((t["text"] for t in turns if str(t["id"]) == highlight_turn_id), None)
    lowlight_text = next((t["text"] for t in turns if str(t["id"]) == lowlight_turn_id), None)

    narrative, call_stats = await generate_narrative(
        scenario_title=rubric_slug or "practice session",
        rubric_name=(rubric or {}).get("name", rubric_slug or "rubric"),
        criteria=criteria_for_narrative,
        highlight_turn_id=highlight_turn_id,
        highlight_text=str(highlight_text) if highlight_text else None,
        lowlight_turn_id=lowlight_turn_id,
        lowlight_text=str(lowlight_text) if lowlight_text else None,
        low_sample_size=low_sample_size,
    )

    async with sessionmaker() as db:
        await upsert_report(
            db,
            session_id=sid,
            status="ready",
            summary=narrative.summary,
            strengths=narrative.strengths,
            growth_areas=narrative.growth_areas,
            next_actions=narrative.next_actions,
            highlight_turn_id=std_uuid.UUID(highlight_turn_id) if highlight_turn_id else None,
            lowlight_turn_id=std_uuid.UUID(lowlight_turn_id) if lowlight_turn_id else None,
            low_sample_size=low_sample_size,
            narrator_model_version=narrative.model_version,
            generated_at=datetime.now(UTC),
        )
        if call_stats is not None:
            await insert_model_call(
                db,
                session_id=sid,
                turn_id=None,
                role="narrator",
                model=narrative.model_version or settings.model_narrator,
                prompt_version=narrative.model_version,
                tokens_in=call_stats.tokens_in,
                tokens_out=call_stats.tokens_out,
                ttft_ms=None,
                total_latency_ms=call_stats.total_latency_ms,
                cost_cents=call_stats.cost_cents,
                cached=call_stats.cached,
            )

    logger.info("generate_report_complete", session_id=session_id, low_sample_size=low_sample_size)
