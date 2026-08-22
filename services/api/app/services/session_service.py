from __future__ import annotations

import uuid as std_uuid

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.exceptions import NotFoundError, RateLimitedError
from ..core.rate_limit import enforce_rate_limit
from ..models import Report, Session, User
from . import content_service, user_service

ACTIVE_STATUSES = ("created", "active")


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
