from __future__ import annotations

import uuid as std_uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.exceptions import NotFoundError, RateLimitedError
from ..core.rate_limit import enforce_rate_limit
from ..core.s3 import presign_get_url
from ..models import (
    Annotation,
    Consent,
    Report,
    Session,
    SessionScore,
    Turn,
    TurnMetrics,
    TurnScore,
    User,
)
from ..models.consent import CURRENT_CONSENT_VERSION
from ..schemas.session import (
    AnnotationCreate,
    NextActionOut,
    RecordingOut,
    ReportOut,
    SessionOut,
    SessionScoreOut,
    TurnMetricsOut,
    TurnOut,
    TurnScoreOut,
    WordTimingOut,
)
from . import content_service, user_service

ACTIVE_STATUSES = ("created", "active")
RETRY_TARGET_MINUTES = 5  # the shortest TARGET_MINUTES_CHOICES tier — Task 3.4f: "a short session"

# Mirrors services/coach/app/deterministic/metrics.py's DELIVERY_CRITERION_KEY. Duplicated as a
# literal rather than imported — api and coach are independent uv workspace members (CLAUDE.md
# §2, docs/decisions/0003 applied the same way across every pair of these services) and neither
# imports the other's application code.
DELIVERY_CRITERION_KEY = "delivery"
DELIVERY_CRITERION_NAME = "Delivery"
DELIVERY_ANCHOR_DESCRIPTORS = {
    "1": "Pace, filler rate, answer length and talk-time share are all well outside a "
    "comfortable interview range.",
    "2": "Two or more of pace, fillers, length and talk-time share are noticeably off.",
    "3": "Delivery is serviceable — one dimension, often pace or length, drifts outside the "
    "target range.",
    "4": "Delivery is comfortable throughout, with only a minor deviation in one dimension.",
    "5": "Pace, filler rate, answer length and talk-time share are all comfortably within range.",
}


async def count_active_sessions(db: AsyncSession, user_id: std_uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Session)
        .where(Session.user_id == user_id, Session.status.in_(ACTIVE_STATUSES))
    )
    return int(result.scalar_one())


async def _compile_brief(
    db: AsyncSession,
    *,
    scenario_id: std_uuid.UUID,
    difficulty: str,
    target_minutes: int,
    focus_areas: list[str],
    resume_text_override: str | None,
) -> dict[str, object]:
    settings = get_settings()
    scenario = await content_service.get_scenario(db, scenario_id)
    if scenario is None:
        raise NotFoundError("Scenario not found.")

    persona = (
        await content_service.get_persona(db, scenario.persona_id) if scenario.persona_id else None
    )
    rubric = (
        await content_service.get_rubric(db, scenario.rubric_id) if scenario.rubric_id else None
    )
    difficulty_params = scenario.difficulty_params.get(difficulty, {})

    # The frozen brief: resolved persona prompt reference, opening strategy, rubric id,
    # difficulty parameters and budget caps — immutable for the session's lifetime
    # (docs/phase-0-BUILD.md TASK 0.5, "Session creation requirements").
    #
    # docs/phase-2-BUILD.md TASK 2.3a's layered prompt assembly runs in services/realtime,
    # which never imports api's content_service or touches the personas/scenarios tables
    # directly (docs/decisions/0003: independent workspace members). The actual persona/
    # scenario brief TEXT is embedded here, not just their ids/slugs, so the frozen brief is
    # genuinely self-contained and reproducible — re-editing content/personas or content/
    # scenarios later and re-seeding must never change what an already-created session says.
    return {
        "scenario_slug": scenario.slug,
        "scenario_title": scenario.title,
        "scenario_family": scenario.family,
        "scenario_brief": scenario.brief,
        "persona_id": str(persona.id) if persona else None,
        "persona_slug": persona.slug if persona else None,
        "persona_name": persona.name if persona else None,
        "persona_archetype": persona.archetype if persona else None,
        "persona_temperament": persona.temperament if persona else None,
        "persona_brief": persona.brief if persona else None,
        "persona_prompt_ref": f"persona:{persona.slug}" if persona else None,
        "persona_voice_id": persona.voice_id if persona else None,
        "opening_strategy": scenario.opening_strategy,
        "rubric_id": str(rubric.id) if rubric else None,
        "rubric_slug": rubric.slug if rubric else None,
        "difficulty": difficulty,
        "difficulty_params": difficulty_params,
        "target_minutes": target_minutes,
        "focus_areas": focus_areas,
        "budget_caps": {
            "max_tokens_per_turn": settings.max_tokens_per_turn,
            "max_tokens_per_session": settings.max_tokens_per_session,
        },
        "resume_text_snapshot": resume_text_override,
    }


async def create_session(
    db: AsyncSession,
    redis: Redis,
    user: User,
    *,
    scenario_id: std_uuid.UUID,
    difficulty: str,
    target_minutes: int,
    focus_areas: list[str],
    resume_text_override: str | None,
    recording_consent: bool | None = None,
    training_consent: bool | None = None,
) -> Session:
    settings = get_settings()

    active = await count_active_sessions(db, user.id)
    if active >= settings.max_concurrent_sessions:
        raise RateLimitedError(retry_after_seconds=60)  # unblocks by ending an active session

    await enforce_rate_limit(
        redis,
        f"sessions_hour:{user.id}",
        limit=settings.max_sessions_per_hour,
        window_seconds=3600,
    )
    await enforce_rate_limit(
        redis,
        f"sessions_day:{user.id}",
        limit=settings.max_sessions_per_day,
        window_seconds=86400,
    )

    resume_text = resume_text_override
    if resume_text is None:
        profile = await user_service.get_profile(db, user.id)
        resume_text = profile.resume_text if profile else None

    brief = await _compile_brief(
        db,
        scenario_id=scenario_id,
        difficulty=difficulty,
        target_minutes=target_minutes,
        focus_areas=focus_areas,
        resume_text_override=resume_text,
    )

    session = Session(
        user_id=user.id,
        scenario_id=scenario_id,
        status="created",
        target_minutes=target_minutes,
        focus_areas=focus_areas,
        resume_text_override=resume_text_override,
        brief=brief,
    )
    db.add(session)
    await db.flush()

    # Task 4.5a: a Consent row for every session, not only the recruited-session flow's
    # explicit screen — recording is always on (capture is how the product works at all);
    # training_consent falls back to the account's own Settings > Privacy default when the
    # caller doesn't override it explicitly.
    db.add(
        Consent(
            session_id=session.id,
            recording_consent=recording_consent if recording_consent is not None else True,
            training_consent=(
                training_consent if training_consent is not None else user.training_consent
            ),
            consent_version=CURRENT_CONSENT_VERSION,
        )
    )
    await db.flush()
    return session


async def list_sessions(
    db: AsyncSession, user_id: std_uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Session], int]:
    total_result = await db.execute(
        select(func.count()).select_from(Session).where(Session.user_id == user_id)
    )
    total = int(total_result.scalar_one())

    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id)
        .order_by(Session.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def get_session_by_id(db: AsyncSession, session_id: std_uuid.UUID) -> Session | None:
    return await db.get(Session, session_id)


async def get_report(db: AsyncSession, session_id: std_uuid.UUID) -> Report | None:
    result = await db.execute(select(Report).where(Report.session_id == session_id))
    return result.scalar_one_or_none()


# ── Phase 3: report/replay surface ───────────────────────────────────────────────────────────


def session_to_out(session: Session) -> SessionOut:
    return SessionOut(
        id=session.id,
        scenario_id=session.scenario_id,
        status=session.status,
        end_reason=session.end_reason,
        target_minutes=session.target_minutes,
        focus_areas=session.focus_areas,
        started_at=session.started_at,
        ended_at=session.ended_at,
        duration_ms=session.duration_ms,
        created_at=session.created_at,
        recording_available=session.recording_key is not None,
        retry_of_session_id=session.retry_of_session_id,
        retry_of_turn_id=session.retry_of_turn_id,
    )


def report_to_out(report: Report) -> ReportOut:
    return ReportOut(
        id=report.id,
        session_id=report.session_id,
        status=report.status,
        summary=report.summary,
        strengths=report.strengths,
        growth_areas=report.growth_areas,
        next_actions=[
            NextActionOut(
                text=str(a["text"]),
                turn_id=std_uuid.UUID(str(a["turn_id"])) if a.get("turn_id") else None,
            )
            for a in report.next_actions
        ],
        highlight_turn_id=report.highlight_turn_id,
        lowlight_turn_id=report.lowlight_turn_id,
        low_sample_size=report.low_sample_size,
        generated_at=report.generated_at,
    )


async def list_turns_with_scores(db: AsyncSession, session_id: std_uuid.UUID) -> list[TurnOut]:
    """Task 3.3/3.4: everything the transcript, delivery panel and replay need for every turn in
    one call. Three plain selects on `session_id` (Turn's own partitioning is on `created_at`,
    transparent to a query that never touches the partition key directly) joined in Python
    rather than a SQL join, since `turn_metrics`/`turn_scores` key off a bare `turn_id` column
    with no FK to `turns` (docs/decisions/0002) — there is no join condition the database could
    verify anyway."""
    turns_result = await db.execute(
        select(Turn).where(Turn.session_id == session_id).order_by(Turn.index, Turn.created_at)
    )
    turns = list(turns_result.scalars().all())

    metrics_result = await db.execute(
        select(TurnMetrics).where(TurnMetrics.session_id == session_id)
    )
    metrics_by_turn = {m.turn_id: m for m in metrics_result.scalars().all()}

    scores_result = await db.execute(select(TurnScore).where(TurnScore.session_id == session_id))
    scores_by_turn: dict[std_uuid.UUID, list[TurnScore]] = defaultdict(list)
    for s in scores_result.scalars().all():
        scores_by_turn[s.turn_id].append(s)

    out: list[TurnOut] = []
    for t in turns:
        metrics = metrics_by_turn.get(t.id)
        out.append(
            TurnOut(
                id=t.id,
                index=t.index,
                speaker=cast(Literal["user", "persona"], t.speaker),
                text=t.text,
                text_scrubbed=t.text_scrubbed,
                start_ms=t.start_ms,
                end_ms=t.end_ms,
                word_timings=[
                    WordTimingOut(
                        word=str(wt["word"]),
                        start_ms=int(wt["start_ms"]),  # type: ignore[call-overload]
                        end_ms=int(wt["end_ms"]),  # type: ignore[call-overload]
                    )
                    for wt in t.word_timings
                ],
                truncated=t.truncated,
                asr_confidence=t.asr_confidence,
                metrics=TurnMetricsOut.model_validate(metrics) if metrics is not None else None,
                scores=[
                    TurnScoreOut(
                        criterion_key=s.criterion_key,
                        score=s.score,
                        confidence=s.confidence,
                        evidence_spans=s.evidence_spans,
                        model_version=s.model_version,
                    )
                    for s in scores_by_turn.get(t.id, [])
                ],
            )
        )
    return out


async def list_session_scores(db: AsyncSession, session: Session) -> list[SessionScoreOut]:
    """Task 3.3d: the score panel's rows, each carrying the rubric's own anchor text — "the same
    words the annotator saw" — joined in from content, not duplicated into `session_scores` at
    write time."""
    rubric_id_raw = session.brief.get("rubric_id") if session.brief else None
    criteria_by_key: dict[str, tuple[str, dict[str, str], int]] = {}
    if rubric_id_raw:
        rubric = await content_service.get_rubric(db, std_uuid.UUID(str(rubric_id_raw)))
        if rubric is not None:
            criteria_by_key = {
                c.key: (c.name, c.anchor_descriptors, c.display_order) for c in rubric.criteria
            }

    result = await db.execute(select(SessionScore).where(SessionScore.session_id == session.id))
    rows = list(result.scalars().all())

    scored: list[tuple[int, SessionScoreOut]] = []
    for row in rows:
        if row.criterion_key in criteria_by_key:
            name, anchors, order = criteria_by_key[row.criterion_key]
        elif row.criterion_key == DELIVERY_CRITERION_KEY:
            name, anchors, order = DELIVERY_CRITERION_NAME, DELIVERY_ANCHOR_DESCRIPTORS, 1_000_000
        else:
            name, anchors, order = row.criterion_key.replace("_", " ").title(), {}, 999_999
        scored.append(
            (
                order,
                SessionScoreOut(
                    criterion_key=row.criterion_key,
                    name=name,
                    aggregate_score=row.aggregate_score,
                    confidence=row.confidence,
                    percentile_vs_self=row.percentile_vs_self,
                    evidence_turn_ids=[std_uuid.UUID(t) for t in row.evidence_turn_ids],
                    anchor_descriptors=anchors,
                ),
            )
        )
    scored.sort(key=lambda pair: pair[0])
    return [item for _, item in scored]


def get_recording(session: Session) -> RecordingOut:
    """Task 3.3a/3.3f. Mints a presigned URL against the stored key — api never reads the
    object's bytes itself (CLAUDE.md §2). `None` fields mean no recording exists for this
    session (never captured, or storage unconfigured); the report UI must degrade gracefully,
    never show an error (Task 3.4's edge-case table: "Recording deleted (retention expired)")."""
    if session.recording_key is None or session.recording_format is None:
        return RecordingOut(
            url=None, format=None, peaks=session.peaks, duration_ms=session.duration_ms
        )
    url = presign_get_url(session.recording_key)
    return RecordingOut(
        url=url,
        format=cast(Literal["wav", "opus"], session.recording_format),
        peaks=session.peaks,
        duration_ms=session.duration_ms,
    )


async def create_annotation(
    db: AsyncSession, session: Session, user: User, body: AnnotationCreate
) -> Annotation:
    """Task 3.4e. `round` auto-increments per (turn, annotator, criterion) so the same reviewer
    can label the same turn again on a later visit without colliding on the DB's uniqueness
    constraint — "This is how the training set grows... every time you review your own
    session.\""""
    turn_result = await db.execute(
        select(Turn).where(Turn.id == body.turn_id, Turn.session_id == session.id)
    )
    if turn_result.scalar_one_or_none() is None:
        raise NotFoundError("Turn not found in this session.")

    max_round_result = await db.execute(
        select(func.max(Annotation.round)).where(
            Annotation.turn_id == body.turn_id,
            Annotation.annotator_id == user.id,
            Annotation.criterion_key == body.criterion_key,
        )
    )
    max_round = max_round_result.scalar_one()
    next_round = (max_round if max_round is not None else 0) + 1

    annotation = Annotation(
        session_id=session.id,
        turn_id=body.turn_id,
        annotator_id=user.id,
        criterion_key=body.criterion_key,
        round=next_round,
        score=body.score,
        notes=body.notes,
    )
    db.add(annotation)
    await db.flush()
    return annotation


async def create_retry_session(
    db: AsyncSession, redis: Redis, user: User, original_session: Session, turn_id: std_uuid.UUID
) -> Session:
    """Task 3.4f: "Re-run a single question in isolation... in the same scenario, at the same
    difficulty, and links the result back to the original turn." `turn_id` is the user's answer
    turn being retried; the "question" re-asked is the persona turn immediately preceding it —
    found the same way services/coach/app/report/build.py's `_find_preceding_question` does,
    reimplemented here rather than imported since api and coach are independent workspace
    members (docs/decisions/0003) with no shared query layer. Overriding `opening_strategy` to
    that exact question text is what makes the persona's scripted opener (Task 2.3f) ask it
    verbatim — no change to services/realtime's persona pipeline was needed for this feature."""
    settings = get_settings()

    active = await count_active_sessions(db, user.id)
    if active >= settings.max_concurrent_sessions:
        raise RateLimitedError(retry_after_seconds=60)
    await enforce_rate_limit(
        redis, f"sessions_hour:{user.id}", limit=settings.max_sessions_per_hour, window_seconds=3600
    )
    await enforce_rate_limit(
        redis, f"sessions_day:{user.id}", limit=settings.max_sessions_per_day, window_seconds=86400
    )

    turn_result = await db.execute(
        select(Turn).where(Turn.id == turn_id, Turn.session_id == original_session.id)
    )
    target_turn = turn_result.scalar_one_or_none()
    if target_turn is None or target_turn.speaker != "user":
        raise NotFoundError("That turn is not a user answer in this session.")

    preceding_result = await db.execute(
        select(Turn)
        .where(
            Turn.session_id == original_session.id,
            Turn.speaker == "persona",
            Turn.index < target_turn.index,
        )
        .order_by(Turn.index.desc())
        .limit(1)
    )
    preceding = preceding_result.scalar_one_or_none()
    fallback_question = str(original_session.brief.get("opening_strategy", ""))
    question_text = preceding.text if preceding is not None else fallback_question

    brief = dict(original_session.brief)
    brief["opening_strategy"] = question_text
    brief["target_minutes"] = RETRY_TARGET_MINUTES
    brief["retry_of_session_id"] = str(original_session.id)
    brief["retry_of_turn_id"] = str(target_turn.id)

    retry_session = Session(
        user_id=user.id,
        scenario_id=original_session.scenario_id,
        status="created",
        target_minutes=RETRY_TARGET_MINUTES,
        focus_areas=original_session.focus_areas,
        resume_text_override=original_session.resume_text_override,
        brief=brief,
        retry_of_session_id=original_session.id,
        retry_of_turn_id=target_turn.id,
    )
    db.add(retry_session)
    await db.flush()

    original_consent_result = await db.execute(
        select(Consent).where(Consent.session_id == original_session.id)
    )
    original_consent = original_consent_result.scalar_one_or_none()
    db.add(
        Consent(
            session_id=retry_session.id,
            recording_consent=(
                original_consent.recording_consent if original_consent is not None else True
            ),
            training_consent=(
                original_consent.training_consent
                if original_consent is not None
                else user.training_consent
            ),
            consent_version=CURRENT_CONSENT_VERSION,
        )
    )
    await db.flush()
    return retry_session


def compute_overall_score(scores: list[SessionScore]) -> tuple[float | None, float]:
    """Confidence-weighted mean across *judged* criteria only — `delivery` is deterministic
    arithmetic, not a rubric judgement, so folding it into "overall score" would blur exactly
    the arithmetic-vs-judgement line CLAUDE.md §5 draws. `None` (never a fabricated number) when
    no criterion has enough signal to contribute (CLAUDE.md §10)."""
    signal = [
        s
        for s in scores
        if s.criterion_key != DELIVERY_CRITERION_KEY and s.aggregate_score is not None
    ]
    if not signal:
        return None, 0.0
    weights: list[float] = [float(s.confidence) for s in signal]
    total_weight = sum(weights)
    if total_weight <= 0:
        return None, 0.0
    values: list[float] = [float(s.aggregate_score) for s in signal]  # type: ignore[arg-type]
    weighted_sum = sum(v * w for v, w in zip(values, weights, strict=True))
    return round(weighted_sum / total_weight, 2), round(total_weight / len(signal), 4)


RECENT_ATTEMPTS_CAP = 10


@dataclass(frozen=True, slots=True)
class ScenarioAttemptSummary:
    session_id: std_uuid.UUID
    created_at: datetime
    overall_score: float | None


@dataclass(frozen=True, slots=True)
class ScenarioAttempts:
    count: int
    best_score: float | None
    recent: list[ScenarioAttemptSummary]  # newest first, capped at RECENT_ATTEMPTS_CAP


async def get_scenario_attempts(
    db: AsyncSession, user_id: std_uuid.UUID
) -> dict[std_uuid.UUID, ScenarioAttempts]:
    """Task 4.2's scenario library card ("the user's own best score if attempted") and detail
    page ("previous attempts with scores"). Keyed by scenario_id."""
    sessions_result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id, Session.status == "closed")
        .order_by(Session.created_at.desc())
    )
    sessions = list(sessions_result.scalars().all())
    if not sessions:
        return {}

    session_ids = [s.id for s in sessions]
    scores_result = await db.execute(
        select(SessionScore).where(SessionScore.session_id.in_(session_ids))
    )
    scores_by_session: dict[std_uuid.UUID, list[SessionScore]] = defaultdict(list)
    for row in scores_result.scalars().all():
        scores_by_session[row.session_id].append(row)

    by_scenario: dict[std_uuid.UUID, list[ScenarioAttemptSummary]] = defaultdict(list)
    for s in sessions:  # newest first, matching the query order above
        overall, _confidence = compute_overall_score(scores_by_session.get(s.id, []))
        by_scenario[s.scenario_id].append(
            ScenarioAttemptSummary(session_id=s.id, created_at=s.created_at, overall_score=overall)
        )

    out: dict[std_uuid.UUID, ScenarioAttempts] = {}
    for scenario_id, attempts in by_scenario.items():
        scored = [a.overall_score for a in attempts if a.overall_score is not None]
        out[scenario_id] = ScenarioAttempts(
            count=len(attempts),
            best_score=max(scored) if scored else None,
            recent=attempts[:RECENT_ATTEMPTS_CAP],
        )
    return out


async def mark_report_viewed(db: AsyncSession, session: Session) -> None:
    """Task 4.1: the dashboard's attention panel surfaces "an unread report" — this is the one
    place that fact ever changes, fired as a side effect of the report route actually returning
    a ready report (never re-cleared; "read" is a one-way fact)."""
    if session.report_viewed_at is None:
        session.report_viewed_at = datetime.now(UTC)
        await db.flush()


async def practice_minutes_this_week(db: AsyncSession, user_id: std_uuid.UUID) -> int:
    """Sidebar meter (Task 3.1: "practice-minutes-this-week meter pinned at the bottom").
    Calendar week starting Monday 00:00 UTC — a fixed, explainable boundary rather than a
    rolling 7 days, so the number resets predictably instead of drifting by the hour."""
    now = datetime.now(UTC)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.coalesce(func.sum(Session.duration_ms), 0)).where(
            Session.user_id == user_id,
            Session.created_at >= week_start,
            Session.duration_ms.is_not(None),
        )
    )
    raw_total = result.scalar_one()
    total_ms = raw_total if raw_total is not None else 0
    return total_ms // 60_000
