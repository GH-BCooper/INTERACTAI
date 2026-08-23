"""Task 4.1/4.4: the dashboard's recommendation + progress strip + attention panel, and the
progress page's trends. Every number here is either deterministic arithmetic or a fixed rule
over stored data — CLAUDE.md §10 ("never fabricate a metric") and Task 4.1's own "Deterministic
and explainable — no model call" apply to all of it.
"""

from __future__ import annotations

import uuid as std_uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Report, Scenario, Session, SessionScore, User
from ..schemas.progress import (
    AttentionItemOut,
    CriterionTrendOut,
    CriterionTrendPointOut,
    DashboardOut,
    PersonalBestOut,
    ProgressOut,
    ProgressStripOut,
    RecentSessionOut,
    RecommendationOut,
    ScenarioAttemptOut,
    ScenarioProgressOut,
    WeakestDimensionOut,
    WeeklyVolumePointOut,
)
from . import content_service, session_service, user_service
from .session_service import DELIVERY_CRITERION_KEY, compute_overall_score

DIFFICULTY_LADDER = ("gentle", "standard", "hard")
GOAL_TO_FAMILY = {
    "job_interview": "behavioural",
    "technical_interview": "technical",
    "salary_negotiation": "negotiation",
}
FALLBACK_FAMILY = "behavioural"
STALLED_ATTEMPT_THRESHOLD = 3
TREND_WINDOW = 3
MIN_TREND_POINTS = 2  # a trend needs at least two data points to mean anything

# (created_at, score, session_id, family)
_CriterionPoint = tuple[datetime, float, std_uuid.UUID, str]


def _week_start(moment: datetime) -> datetime:
    """Calendar week starting Monday 00:00 UTC — same fixed boundary as
    session_service.practice_minutes_this_week, so every weekly figure in the app resets on the
    same clock."""
    return (moment - timedelta(days=moment.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


async def _closed_sessions_with_scenario(
    db: AsyncSession, user_id: std_uuid.UUID
) -> list[tuple[Session, Scenario]]:
    result = await db.execute(
        select(Session, Scenario)
        .join(Scenario, Scenario.id == Session.scenario_id)
        .where(Session.user_id == user_id, Session.status == "closed")
        .order_by(Session.created_at.asc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def _scores_by_session(
    db: AsyncSession, session_ids: list[std_uuid.UUID]
) -> dict[std_uuid.UUID, list[SessionScore]]:
    if not session_ids:
        return {}
    result = await db.execute(select(SessionScore).where(SessionScore.session_id.in_(session_ids)))
    out: dict[std_uuid.UUID, list[SessionScore]] = defaultdict(list)
    for row in result.scalars().all():
        out[row.session_id].append(row)
    return out


async def _criterion_names(db: AsyncSession) -> dict[str, str]:
    rubrics = await content_service.list_rubrics(db)
    names: dict[str, str] = {}
    for rubric in rubrics:
        for criterion in rubric.criteria:
            names[criterion.key] = criterion.name
    return names


def _display_name(names: dict[str, str], key: str) -> str:
    return names.get(key, key.replace("_", " ").title())


async def _criterion_history(
    db: AsyncSession, user_id: std_uuid.UUID, *, family: str | None = None
) -> dict[str, list[_CriterionPoint]]:
    """criterion_key -> chronological (oldest first) score points, `delivery` excluded (it's
    arithmetic, not a judged rubric dimension — CLAUDE.md §5)."""
    sessions = await _closed_sessions_with_scenario(db, user_id)
    if family is not None:
        sessions = [(s, sc) for s, sc in sessions if sc.family == family]
    scores_by_session = await _scores_by_session(db, [s.id for s, _ in sessions])

    history: dict[str, list[_CriterionPoint]] = defaultdict(list)
    for session, scenario in sessions:
        for row in scores_by_session.get(session.id, []):
            if row.criterion_key == DELIVERY_CRITERION_KEY or row.aggregate_score is None:
                continue
            history[row.criterion_key].append(
                (session.created_at, float(row.aggregate_score), session.id, scenario.family)
            )
    return history


def _trend(points: list[_CriterionPoint]) -> float | None:
    """Newest minus oldest of the last `TREND_WINDOW` data points. Negative = declining,
    0 = stable, positive = improving — a plain difference is exactly what Task 4.4's own
    worked example needs: "A criterion at 5 and declining is more urgent than one at 4 and
    stable," which `min(trend)` alone (declining < stable < improving) already gets right
    without any extra weighting by absolute level."""
    if len(points) < MIN_TREND_POINTS:
        return None
    window = points[-TREND_WINDOW:]
    return round(window[-1][1] - window[0][1], 3)


async def weakest_trending_criterion(
    db: AsyncSession, user_id: std_uuid.UUID, *, family: str | None = None
) -> tuple[float, str, str] | None:
    """Returns (trend, criterion_key, family_of_most_recent_datapoint) for the criterion with
    the lowest (most negative) trend, or None if no criterion yet has the two data points a
    trend requires."""
    history = await _criterion_history(db, user_id, family=family)
    best: tuple[float, str, str] | None = None
    for key, points in history.items():
        trend = _trend(points)
        if trend is None:
            continue
        if best is None or trend < best[0]:
            best = (trend, key, points[-1][3])
    return best


async def _families_with_content(db: AsyncSession) -> list[str]:
    result = await db.execute(select(Scenario.family).distinct())
    return sorted({row[0] for row in result.all()})


async def _pick_scenario(db: AsyncSession, *, family: str, difficulty: str) -> Scenario | None:
    result = await db.execute(
        select(Scenario)
        .where(Scenario.family == family, Scenario.difficulty == difficulty)
        .order_by(Scenario.slug)
        .limit(1)
    )
    scenario = result.scalar_one_or_none()
    if scenario is not None:
        return scenario
    # That exact family/difficulty tier isn't seeded — fall back to any scenario in the family
    # rather than recommending nothing (CLAUDE.md §10 forbids fabricating a metric, not
    # degrading gracefully to a slightly different real scenario).
    fallback_result = await db.execute(
        select(Scenario).where(Scenario.family == family).order_by(Scenario.slug).limit(1)
    )
    return fallback_result.scalar_one_or_none()


# ── Task 4.1 — recommendation ────────────────────────────────────────────────────────────────


async def get_recommendation(db: AsyncSession, user: User) -> RecommendationOut:
    """The five-rule ladder from docs/phase-4-BUILD.md TASK 4.1, in order. Every branch either
    returns with a human-readable reason or falls through to the next rule — never a silent
    empty recommendation."""
    incomplete_result = await db.execute(
        select(Session)
        .where(Session.user_id == user.id, Session.status.in_(("created", "active")))
        .order_by(Session.created_at.desc())
        .limit(1)
    )
    incomplete = incomplete_result.scalar_one_or_none()
    if incomplete is not None:
        return RecommendationOut(
            kind="continue_session",
            reason="You have a session in progress — pick up right where you left off.",
            session_id=incomplete.id,
            scenario_id=incomplete.scenario_id,
        )

    names = await _criterion_names(db)
    trend = await weakest_trending_criterion(db, user.id)
    if trend is not None:
        trend_value, criterion_key, family = trend
        if trend_value < 0:
            scenario = await _pick_scenario(db, family=family, difficulty="standard")
            if scenario is not None:
                name = _display_name(names, criterion_key)
                return RecommendationOut(
                    kind="start_scenario",
                    reason=(
                        f"{name} has been your weakest dimension over your last few sessions — "
                        f"{family} scenarios exercise it directly."
                    ),
                    scenario_id=scenario.id,
                )

    families_available = await _families_with_content(db)
    attempted_result = await db.execute(
        select(Scenario.family)
        .join(Session, Session.scenario_id == Scenario.id)
        .where(Session.user_id == user.id)
        .distinct()
    )
    attempted_families = {row[0] for row in attempted_result.all()}
    never_attempted = [f for f in families_available if f not in attempted_families]
    if never_attempted:
        family = never_attempted[0]
        scenario = await _pick_scenario(db, family=family, difficulty="standard")
        if scenario is not None:
            return RecommendationOut(
                kind="start_scenario",
                reason=(
                    f"You haven't tried a {family} scenario yet — a good way to see where "
                    "you stand."
                ),
                scenario_id=scenario.id,
            )

    last_result = await db.execute(
        select(Session, Scenario)
        .join(Scenario, Scenario.id == Session.scenario_id)
        .where(Session.user_id == user.id, Session.status == "closed")
        .order_by(Session.created_at.desc())
        .limit(1)
    )
    last_row = last_result.first()
    if last_row is not None:
        _last_session, last_scenario = last_row
        if last_scenario.difficulty in DIFFICULTY_LADDER:
            idx = DIFFICULTY_LADDER.index(last_scenario.difficulty)
            if idx < len(DIFFICULTY_LADDER) - 1:
                next_difficulty = DIFFICULTY_LADDER[idx + 1]
                scenario = await _pick_scenario(
                    db, family=last_scenario.family, difficulty=next_difficulty
                )
                if scenario is not None and scenario.difficulty == next_difficulty:
                    return RecommendationOut(
                        kind="start_scenario",
                        reason=(
                            f"You've completed {last_scenario.family} at "
                            f"{last_scenario.difficulty} — try {next_difficulty} next."
                        ),
                        scenario_id=scenario.id,
                    )

    profile = await user_service.get_profile(db, user.id)
    goal = profile.goal if profile else None
    fallback_family = GOAL_TO_FAMILY.get(goal or "", FALLBACK_FAMILY)
    if fallback_family not in families_available and families_available:
        fallback_family = families_available[0]
    scenario = await _pick_scenario(db, family=fallback_family, difficulty="gentle")
    return RecommendationOut(
        kind="start_scenario",
        reason="A good place to start — you can change the difficulty and length before you begin.",
        scenario_id=scenario.id if scenario is not None else None,
    )


# ── Task 4.1 — dashboard ─────────────────────────────────────────────────────────────────────


async def _attention_item(
    db: AsyncSession, user: User, names: dict[str, str]
) -> AttentionItemOut | None:
    """Exactly one of three signals, first match wins (docs/phase-4-BUILD.md TASK 4.1: "Empty
    if none apply; do not invent something to fill it.")."""
    unread_result = await db.execute(
        select(Session)
        .join(Report, Report.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.status == "closed",
            Report.status == "ready",
            Session.report_viewed_at.is_(None),
        )
        .order_by(Session.created_at.desc())
        .limit(1)
    )
    unread = unread_result.scalar_one_or_none()
    if unread is not None:
        title = str(unread.brief.get("scenario_title", "your last session"))
        return AttentionItemOut(
            kind="unread_report", text=f"Your report for {title} is ready.", session_id=unread.id
        )

    sessions = await _closed_sessions_with_scenario(db, user.id)
    scores_by_session = await _scores_by_session(db, [s.id for s, _ in sessions])
    by_scenario: dict[std_uuid.UUID, list[tuple[Scenario, float | None]]] = defaultdict(list)
    for session, scenario in sessions:
        overall, _confidence = compute_overall_score(scores_by_session.get(session.id, []))
        by_scenario[session.scenario_id].append((scenario, overall))
    for scenario_id, attempts in by_scenario.items():
        if len(attempts) < STALLED_ATTEMPT_THRESHOLD:
            continue
        scored = [a for a in attempts if a[1] is not None]
        if len(scored) < STALLED_ATTEMPT_THRESHOLD:
            continue
        first_score = scored[0][1]
        later_best = max(a[1] for a in scored[1:])  # type: ignore[type-var]
        if first_score is not None and later_best is not None and later_best <= first_score:
            title = attempts[0][0].title
            return AttentionItemOut(
                kind="stalled_scenario",
                text=f"You've attempted {title} {len(attempts)} times without improving.",
                scenario_id=scenario_id,
            )

    trend = await weakest_trending_criterion(db, user.id)
    if trend is not None and trend[0] < 0:
        name = _display_name(names, trend[1])
        return AttentionItemOut(
            kind="declining_criterion",
            text=f"{name} has been trending down over your last sessions.",
        )

    return None


async def get_dashboard(db: AsyncSession, user: User) -> DashboardOut:
    recommendation = await get_recommendation(db, user)

    now = datetime.now(UTC)
    week_start = _week_start(now)
    sessions_this_week_result = await db.execute(
        select(Session).where(
            Session.user_id == user.id,
            Session.status == "closed",
            Session.created_at >= week_start,
        )
    )
    sessions_this_week = len(list(sessions_this_week_result.scalars().all()))
    total_minutes = await session_service.practice_minutes_this_week(db, user.id)

    recent_result = await db.execute(
        select(Session)
        .where(Session.user_id == user.id, Session.status == "closed")
        .order_by(Session.created_at.desc())
        .limit(5)
    )
    recent_five = list(recent_result.scalars().all())
    scores_by_session = await _scores_by_session(db, [s.id for s in recent_five])

    overall_score: float | None = None
    delta: float | None = None
    if recent_five:
        overall_score, _confidence = compute_overall_score(
            scores_by_session.get(recent_five[0].id, [])
        )
        if len(recent_five) >= 2:
            previous_overall, _ = compute_overall_score(
                scores_by_session.get(recent_five[1].id, [])
            )
            if overall_score is not None and previous_overall is not None:
                delta = round(overall_score - previous_overall, 2)

    names = await _criterion_names(db)
    trend = await weakest_trending_criterion(db, user.id)
    weakest_name = _display_name(names, trend[1]) if trend is not None else None

    recent_out = [
        RecentSessionOut(
            id=s.id,
            scenario_title=str(s.brief.get("scenario_title", "Practice session")),
            created_at=s.created_at,
            duration_ms=s.duration_ms,
            overall_score=compute_overall_score(scores_by_session.get(s.id, []))[0],
            report_read=s.report_viewed_at is not None,
        )
        for s in recent_five
    ]

    attention = await _attention_item(db, user, names)

    return DashboardOut(
        recommendation=recommendation,
        progress_strip=ProgressStripOut(
            sessions_this_week=sessions_this_week,
            total_minutes_this_week=total_minutes,
            overall_score=overall_score,
            overall_score_delta=delta,
            weakest_criterion_name=weakest_name,
        ),
        recent_sessions=recent_out,
        attention=attention,
    )


# ── Task 4.2 — scenario library "your best score" ────────────────────────────────────────────


async def get_scenario_progress(
    db: AsyncSession, user: User
) -> dict[std_uuid.UUID, ScenarioProgressOut]:
    raw = await session_service.get_scenario_attempts(db, user.id)
    return {
        scenario_id: ScenarioProgressOut(
            attempts=attempts.count,
            best_score=attempts.best_score,
            recent_attempts=[
                ScenarioAttemptOut(
                    session_id=a.session_id, created_at=a.created_at, overall_score=a.overall_score
                )
                for a in attempts.recent
            ],
        )
        for scenario_id, attempts in raw.items()
    }


# ── Task 4.4 — progress page ─────────────────────────────────────────────────────────────────


def _weekly_volume(sessions: list[tuple[Session, Scenario]]) -> list[WeeklyVolumePointOut]:
    minutes_by_week: dict[datetime, int] = defaultdict(int)
    sessions_by_week: dict[datetime, int] = defaultdict(int)
    for session, _scenario in sessions:
        week = _week_start(session.created_at)
        minutes_by_week[week] += (session.duration_ms or 0) // 60_000
        sessions_by_week[week] += 1
    return [
        WeeklyVolumePointOut(
            week_start=week, minutes=minutes_by_week[week], sessions=sessions_by_week[week]
        )
        for week in sorted(minutes_by_week)
    ]


async def get_progress(db: AsyncSession, user: User, family: str | None) -> ProgressOut:
    families_available = await _families_with_content(db)
    all_sessions = await _closed_sessions_with_scenario(db, user.id)
    families_attempted = sorted({sc.family for _, sc in all_sessions})

    resolved_family = family
    if resolved_family is None:
        # Task 4.4: "The default filter is the most-practised family, never 'all'."
        counts = Counter(sc.family for _, sc in all_sessions)
        resolved_family = (
            counts.most_common(1)[0][0]
            if counts
            else (families_available[0] if families_available else FALLBACK_FAMILY)
        )

    names = await _criterion_names(db)
    history = await _criterion_history(db, user.id, family=resolved_family)

    criterion_trends = [
        CriterionTrendOut(
            criterion_key=key,
            name=_display_name(names, key),
            points=[
                CriterionTrendPointOut(session_id=sid, created_at=created, score=score)
                for created, score, sid, _fam in points
            ],
        )
        for key, points in sorted(history.items())
    ]

    weakest = await weakest_trending_criterion(db, user.id, family=resolved_family)
    weakest_out = None
    if weakest is not None:
        trend_value, key, _fam = weakest
        name = _display_name(names, key)
        weakest_out = WeakestDimensionOut(
            criterion_key=key,
            name=name,
            trend=trend_value,
            next_action=f"Practise another {resolved_family} scenario focused on {name.lower()}.",
        )

    personal_bests: list[PersonalBestOut] = []
    for key, points in sorted(history.items()):
        best_point = max(points, key=lambda p: p[1])
        personal_bests.append(
            PersonalBestOut(
                criterion_key=key,
                name=_display_name(names, key),
                score=best_point[1],
                session_id=best_point[2],
                achieved_at=best_point[0],
            )
        )

    return ProgressOut(
        family=resolved_family,
        families_available=families_available,
        criterion_trends=criterion_trends,
        weekly_volume=_weekly_volume(all_sessions),
        families_attempted=families_attempted,
        families_never_attempted=[f for f in families_available if f not in families_attempted],
        weakest_dimension=weakest_out,
        personal_bests=personal_bests,
    )
